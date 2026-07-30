"""Cross-repo-name commit deduplication for Datasets A and B.

Some repos in Dataset A's candidate pool are the same underlying repository
counted under more than one `repo_name` -- org transfers and renames whose
git history has since diverged, so `agent_repository_counter.py`'s
current-HEAD-commit dedup (`_dedupe_by_last_commit_sha`, deliberately
conservative -- see that function's docstring) doesn't catch them. Real
example found in the 2026-07-25 Dataset A collection: `camunda-cloud/zeebe`,
`camunda/zeebe`, and `camunda/camunda` are the same project, all three
present as separate repos, together accounting for thousands of duplicated
commits. Since Dataset B's repo pool is resolved from Dataset A's own
output, it inherits the same duplication -- and, scanning each repo's real
git history live rather than reusing Dataset A's classification, rediscovers
the same commits independently under each name.

Repo-level filtering (deciding in advance which repo_names are "the same
repo") needs a full historical commit-set comparison to do safely -- get it
wrong and a repo_name with some genuinely unique commits loses all of them.
This module sidesteps that: a git commit SHA is a content hash (tree +
parents + metadata), so if the exact same `commit_sha` shows up under two
different `repo_name`s in already-collected commit data, that's proof
positive they share history up to that commit -- no historical analysis
needed, and a commit that's genuinely unique to one repo_name simply never
collides, so it's never touched.

For each commit_sha shared by more than one repo_name, exactly one
repo_name's copy survives (highest `stars`, tie-broken by earliest
`created_at` -- see `pick_cluster_survivor()` in repo_dedup_utils.py); the
other repo_name(s)' rows for that same commit_sha are removed. Runs
independently per dataset, on that dataset's own already-collected
commit-level CSVs -- Dataset B does its own live commit scan of each repo
rather than reusing Dataset A's, so it needs its own pass, not just a
downstream consequence of deduping Dataset A's.

    python -m collection.dedupe_commits_by_sha --dataset a
    python -m collection.dedupe_commits_by_sha --dataset b

Run this after commit-level data exists (discover-commits for A,
filter-test-commits for B) and before extract-fixtures, so duplicate
commits are never even used to generate fixtures in the first place. If
fixtures/db already exist for a dataset (as with a retroactive fix), this
tool only touches the commit-level CSVs -- cascading the removal into
already-extracted fixtures/db rows is a separate, explicit step (see
internal-docs/methodology-improvements/repo-deduplication.md).
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any

from . import paths
from .csv_adapter import get_adapter
from .logging_utils import configure_logging, get_logger
from .repo_dedup_utils import pick_cluster_survivor

logger = get_logger(__name__)

AUDIT_FIELDNAMES = [
    "commit_sha",
    "repo_removed",
    "repo_kept",
    "language",
    "cluster_size",
    "stars_removed",
    "stars_kept",
]

# Per-dataset shape: which commit-level CSVs to dedupe, and where the
# matching repo metadata (stars, created_at) lives. Dataset A's own commit
# discovery writes commits/*_commit.csv; Dataset B has no separate
# "discover all commits" stage, so its earliest commit-level artifact is
# test-commits/*_human_test_commit.csv (filter-test-commits' own output).
DATASET_SHAPES: dict[str, dict[str, str]] = {
    "a": {"commit_stage": "commits", "commit_pattern": "*_commit.csv"},
    "b": {"commit_stage": "test-commits", "commit_pattern": "*_human_test_commit.csv"},
}

AUDIT_FILENAME = "duplicate_commits_removed.csv"


def _load_repo_metadata(repos_dir: Path) -> dict[str, dict[str, Any]]:
    """{repo_name: {"stars": ..., "created_at": ...}} from an
    already-collected datasets/{dataset}/repos/*.csv directory."""
    adapter = get_adapter()
    metadata: dict[str, dict[str, Any]] = {}
    for csv_path in sorted(Path(repos_dir).glob("*_repo.csv"), key=lambda p: p.name):
        for row in adapter.read_dicts(csv_path):
            name = (row.get("repo_name") or "").strip()
            if name and name not in metadata:
                metadata[name] = {
                    "stars": row.get("stars"),
                    "created_at": row.get("created_at"),
                }
    return metadata


def find_duplicate_commit_rows(
    commit_rows: list[dict[str, Any]],
    repo_metadata: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Group `commit_rows` (each needs `repo_name`, `commit_sha`) by
    commit_sha; for any commit_sha shared by more than one distinct
    repo_name, pick a survivor repo_name and return one audit row per
    non-survivor row for that commit_sha.

    A commit_sha touched by only one repo_name -- the overwhelming
    majority -- is never inspected further, so it can never be flagged:
    this can only remove a row that has a real, exact duplicate elsewhere
    in `commit_rows`, never a commit that's genuinely unique to its repo.

    Survivor pick uses `repo_metadata` (stars, tie-broken by earliest
    created_at) via `pick_cluster_survivor()` -- the same tie-break rule
    already used by `dedupe_dataset_c_repos.py` and
    `agent_repository_counter.py`'s own dedup mechanisms, just with
    `created_at` instead of `github_id` as the tie-break field, since
    commit-level CSVs were never joined against a repo's numeric GitHub ID.
    A repo_name missing from `repo_metadata` (shouldn't happen for real
    collected data, but not fatal) is treated as 0 stars / sorts last on
    the tie-break, so it never wins against a repo with real metadata.
    """
    by_sha: dict[str, list[dict[str, Any]]] = {}
    for row in commit_rows:
        sha = (row.get("commit_sha") or "").strip()
        if sha:
            by_sha.setdefault(sha, []).append(row)

    removed: list[dict[str, Any]] = []
    for sha, rows in by_sha.items():
        distinct_repos = sorted({(r.get("repo_name") or "").strip() for r in rows} - {""})
        if len(distinct_repos) < 2:
            continue

        candidates = [
            {"repo_name": name, **repo_metadata.get(name, {})} for name in distinct_repos
        ]
        survivor = pick_cluster_survivor(
            candidates, tie_break_key=lambda r: r.get("created_at") or "9999"
        )
        survivor_name = survivor["repo_name"]
        survivor_stars = repo_metadata.get(survivor_name, {}).get("stars", "")

        seen_removed_repos: set[str] = set()
        for row in rows:
            repo_name = (row.get("repo_name") or "").strip()
            if not repo_name or repo_name == survivor_name or repo_name in seen_removed_repos:
                continue
            seen_removed_repos.add(repo_name)
            removed.append(
                {
                    "commit_sha": sha,
                    "repo_removed": repo_name,
                    "repo_kept": survivor_name,
                    "language": row.get("language", ""),
                    "cluster_size": len(distinct_repos),
                    "stars_removed": repo_metadata.get(repo_name, {}).get("stars", ""),
                    "stars_kept": survivor_stars,
                }
            )
    return removed


def dedupe_commit_csvs(
    commits_dir: Path,
    repos_dir: Path,
    *,
    pattern: str,
    audit_output_path: Path,
) -> dict[str, Any]:
    """Remove cross-repo-name duplicate commits from every `pattern`-matching
    CSV under `commits_dir`, rewriting each file in place (same schema,
    minus the removed rows) and writing an audit CSV of what was removed
    and why. A file with nothing removed is left untouched.
    """
    adapter = get_adapter()
    repo_metadata = _load_repo_metadata(repos_dir)

    csv_paths = sorted(Path(commits_dir).glob(pattern), key=lambda p: p.name)
    rows_by_file: dict[Path, list[dict[str, Any]]] = {}
    fieldnames_by_file: dict[Path, list[str]] = {}
    all_rows: list[dict[str, Any]] = []
    for csv_path in csv_paths:
        rows = list(adapter.read_dicts(csv_path))
        rows_by_file[csv_path] = rows
        with csv_path.open("r", encoding="utf-8", newline="") as fh:
            fieldnames_by_file[csv_path] = next(csv.reader(fh), [])
        all_rows.extend(rows)

    removed_rows = find_duplicate_commit_rows(all_rows, repo_metadata)
    to_remove = {(r["commit_sha"], r["repo_removed"]) for r in removed_rows}

    for csv_path, rows in rows_by_file.items():
        if not to_remove:
            break
        kept = [
            row
            for row in rows
            if ((row.get("commit_sha") or "").strip(), (row.get("repo_name") or "").strip())
            not in to_remove
        ]
        if len(kept) != len(rows):
            adapter.write_dicts(csv_path, kept, fieldnames_by_file[csv_path])
            logger.info(
                "[dedupe-commits] %s: %d -> %d rows (%d duplicate commit row(s) removed)",
                csv_path.name,
                len(rows),
                len(kept),
                len(rows) - len(kept),
            )

    if removed_rows:
        adapter.write_dicts(audit_output_path, removed_rows, AUDIT_FIELDNAMES)

    return {
        "total_commit_rows_before": len(all_rows),
        "duplicate_rows_removed": len(removed_rows),
        "distinct_duplicate_commits": len({r["commit_sha"] for r in removed_rows}),
        "audit_csv": str(audit_output_path) if removed_rows else None,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Remove commits duplicated across repo_names sharing history "
            "(org transfers/renames) from an already-collected dataset's "
            "commit-level CSVs. Run after commit collection, before "
            "extract-fixtures."
        )
    )
    parser.add_argument("--dataset", choices=sorted(DATASET_SHAPES), required=True)
    parser.add_argument(
        "--datasets-root",
        type=Path,
        default=paths.DATASETS_ROOT,
        help="Root of the datasets/ tree (default: %(default)s)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_logging(fmt="%(message)s")
    args = build_parser().parse_args(argv)

    shape = DATASET_SHAPES[args.dataset]
    commits_dir = paths.stage_dir(args.dataset, shape["commit_stage"], root=args.datasets_root)
    repos_dir = paths.stage_dir(args.dataset, "repos", root=args.datasets_root)
    audit_path = commits_dir / AUDIT_FILENAME

    summary = dedupe_commit_csvs(
        commits_dir, repos_dir, pattern=shape["commit_pattern"], audit_output_path=audit_path
    )
    logger.info(
        "[dedupe-commits-%s] %d/%d commit rows removed as cross-repo-name "
        "duplicates (%d distinct commits) -> %s",
        args.dataset,
        summary["duplicate_rows_removed"],
        summary["total_commit_rows_before"],
        summary["distinct_duplicate_commits"],
        summary["audit_csv"] or "(none removed)",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
