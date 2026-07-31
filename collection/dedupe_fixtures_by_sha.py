"""Cross-repo-name duplicate-commit cleanup for Dataset B's already-extracted
fixtures -- a recurring cleanup step, not a one-time fix.

`dedupe_commits_by_sha.py --dataset b` cleans `datasets/b/test-commits/*.csv`,
but `extract-fixtures --dataset b` (`HumanCorpusCollector`) never reads that
file. It resolves its own repo list from `datasets/b/repos/*.csv` and, for
every repo, independently re-clones and re-scans the repo's full commit
history from scratch (`_process_human_repository` -> `_scan_and_extract`,
its own `Tier1RepositoryScanner` call) -- so a commit shared by two org-
transferred/renamed repo_names (e.g. `phidatahq/phidata` /
`agno-agi/agno`, same repo, diverged history, not caught by
`agent_repository_counter.py`'s current-HEAD-only repo-level dedup) gets
extracted twice, once under each name, regardless of what the -- unrelated,
never-consulted -- test-commits CSV says. Confirmed empirically on a real
run: 36.6% of Dataset B's python fixtures shared a commit_sha with another
repo_id (`internal-docs/methodology-improvements/repo-deduplication.md`,
section 9).

Restructuring `extract-fixtures --dataset b` to consume the deduped
test-commits CSV instead of independently rescanning (mirroring how
Dataset A's extractor already works, and how this problem doesn't exist for
A) would make this a one-time fix like `dedupe_commits_by_sha.py` already
is for A -- but it's a real refactor (extraction currently also derives
`agent_adoption_intensity` as a side effect of the full rescan, which would
need its own data path), deliberately deferred. Until then, this module
does the same job as `dedupe_commits_by_sha.py` -- same duplicate-detection
logic (`find_duplicate_commit_rows`/`pick_cluster_survivor`), same
commit-SHA-as-proof-of-shared-history reasoning -- just aimed at the
fixture output instead of the commit-level input, and run *after*
`extract-fixtures --dataset b` instead of before. It also cascades into
`db/b.db`'s `fixtures`/`mock_usages` tables (not just the CSVs, since by
this point fixtures already exist there), and re-syncs the denormalized
aggregate columns (`test_files.num_fixtures`/`total_fixture_loc`,
`repositories.num_fixtures`/`num_mock_usages`) for every repo touched --
those are snapshot columns `set_repo_analysed()`/`update_test_file_counts()`
write once at persist time, not kept live, so deleting fixture rows without
re-syncing them would leave them stale.

Safe to run repeatedly: a clean state (nothing duplicated) finds nothing to
remove and leaves every file/table untouched.

    python -m collection.dedupe_fixtures_by_sha --dataset b

Run after every `extract-fixtures --dataset b` invocation (including
per-language re-runs), not just once.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from . import paths
from .csv_adapter import get_adapter
from .db import db_session
from .dedupe_commits_by_sha import dedupe_commit_csvs
from .logging_utils import configure_logging, get_logger

logger = get_logger(__name__)

AUDIT_FILENAME = "duplicate_fixtures_removed.csv"

DATASET_SHAPES: dict[str, dict[str, str]] = {
    "b": {"fixtures_pattern": "*_fixtures.csv"},
}


def _cascade_remove_from_db(
    output_db: Path, removed_pairs: set[tuple[str, str]]
) -> dict[str, int]:
    """Delete fixtures/mock_usages rows matching (commit_sha, repo_removed)
    pairs from output_db, then re-sync the denormalized aggregate columns
    for every repo/file touched (see module docstring for why)."""
    fixtures_deleted = 0
    mock_usages_deleted = 0
    affected_repo_ids: set[int] = set()
    affected_file_ids: set[int] = set()

    with db_session(output_db) as conn:
        for commit_sha, repo_removed in removed_pairs:
            if not commit_sha or not repo_removed:
                continue
            repo_row = conn.execute(
                "SELECT id FROM repositories WHERE full_name = ?", (repo_removed,)
            ).fetchone()
            if repo_row is None:
                continue
            repo_id = repo_row["id"]

            fixture_rows = conn.execute(
                "SELECT id, file_id FROM fixtures WHERE repo_id = ? AND commit_sha = ?",
                (repo_id, commit_sha),
            ).fetchall()
            if not fixture_rows:
                continue

            fixture_ids = [r["id"] for r in fixture_rows]
            affected_repo_ids.add(repo_id)
            affected_file_ids.update(r["file_id"] for r in fixture_rows)

            placeholders = ",".join("?" for _ in fixture_ids)
            mock_usages_deleted += conn.execute(
                f"DELETE FROM mock_usages WHERE fixture_id IN ({placeholders})",
                fixture_ids,
            ).rowcount
            fixtures_deleted += conn.execute(
                f"DELETE FROM fixtures WHERE id IN ({placeholders})",
                fixture_ids,
            ).rowcount

        for file_id in affected_file_ids:
            counts = conn.execute(
                "SELECT COUNT(*) AS n, COALESCE(SUM(loc), 0) AS total_loc "
                "FROM fixtures WHERE file_id = ?",
                (file_id,),
            ).fetchone()
            conn.execute(
                "UPDATE test_files SET num_fixtures = ?, total_fixture_loc = ? WHERE id = ?",
                (counts["n"], counts["total_loc"], file_id),
            )

        for repo_id in affected_repo_ids:
            fixture_count = conn.execute(
                "SELECT COUNT(*) AS n FROM fixtures WHERE repo_id = ?", (repo_id,)
            ).fetchone()["n"]
            mock_count = conn.execute(
                "SELECT COUNT(*) AS n FROM mock_usages WHERE repo_id = ?", (repo_id,)
            ).fetchone()["n"]
            conn.execute(
                "UPDATE repositories SET num_fixtures = ?, num_mock_usages = ? WHERE id = ?",
                (fixture_count, mock_count, repo_id),
            )

    return {
        "fixtures_deleted": fixtures_deleted,
        "mock_usages_deleted": mock_usages_deleted,
        "repos_resynced": len(affected_repo_ids),
        "files_resynced": len(affected_file_ids),
    }


def dedupe_fixtures_and_db(
    fixtures_dir: Path,
    repos_dir: Path,
    output_db: Path,
    *,
    pattern: str,
    audit_output_path: Path,
) -> dict[str, Any]:
    """Remove cross-repo-name duplicate commits' fixtures from
    `fixtures_dir`'s CSVs and cascade the same removal into `output_db`'s
    fixtures/mock_usages tables. Reuses `dedupe_commit_csvs()` unchanged for
    the CSV side -- it already filters by (commit_sha, repo_name) pairs
    regardless of how many rows in a file share one commit_sha, which is
    exactly the fixtures-CSV shape (multiple fixtures per commit).
    """
    csv_summary = dedupe_commit_csvs(
        fixtures_dir, repos_dir, pattern=pattern, audit_output_path=audit_output_path
    )

    db_summary = {
        "fixtures_deleted": 0,
        "mock_usages_deleted": 0,
        "repos_resynced": 0,
        "files_resynced": 0,
    }
    if csv_summary["duplicate_rows_removed"]:
        adapter = get_adapter()
        removed_pairs = {
            (
                (row.get("commit_sha") or "").strip(),
                (row.get("repo_removed") or "").strip(),
            )
            for row in adapter.read_dicts(audit_output_path)
        }
        db_summary = _cascade_remove_from_db(output_db, removed_pairs)

    return {**csv_summary, **db_summary}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Remove commits duplicated across repo_names sharing history "
            "(org transfers/renames) from an already-extracted dataset's "
            "fixture CSVs and DB. Recurring cleanup, not a one-time fix -- "
            "run after every extract-fixtures --dataset b invocation, see "
            "this module's docstring."
        )
    )
    parser.add_argument("--dataset", choices=sorted(DATASET_SHAPES), required=True)
    parser.add_argument(
        "--datasets-root",
        type=Path,
        default=paths.DATASETS_ROOT,
        help="Root of the datasets/ tree (default: %(default)s)",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Path to the dataset's DB (default: db/{dataset}.db)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_logging(fmt="%(message)s")
    args = build_parser().parse_args(argv)

    shape = DATASET_SHAPES[args.dataset]
    fixtures_dir = paths.stage_dir(args.dataset, "fixtures", root=args.datasets_root)
    repos_dir = paths.stage_dir(args.dataset, "repos", root=args.datasets_root)
    output_db = args.db or paths.db_path(args.dataset)
    audit_path = fixtures_dir / AUDIT_FILENAME

    summary = dedupe_fixtures_and_db(
        fixtures_dir,
        repos_dir,
        output_db,
        pattern=shape["fixtures_pattern"],
        audit_output_path=audit_path,
    )
    logger.info(
        "[dedupe-fixtures-%s] %d/%d fixture CSV row(s) removed as cross-repo-name "
        "duplicates (%d distinct commits); DB: %d fixture(s)/%d mock_usage(s) "
        "removed, %d repo(s)/%d file(s) re-synced -> %s",
        args.dataset,
        summary["duplicate_rows_removed"],
        summary["total_commit_rows_before"],
        summary["distinct_duplicate_commits"],
        summary["fixtures_deleted"],
        summary["mock_usages_deleted"],
        summary["repos_resynced"],
        summary["files_resynced"],
        summary["audit_csv"] or "(none removed)",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
