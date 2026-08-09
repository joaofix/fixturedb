"""One-time backfill: populate `repositories.total_commits_since_agent_start`
for Dataset A repos collected before that column existed.

`agent_corpus.py`'s per-repo loop already computes this number live, via
`count_total_commits_since()` (`tiered_agent_corpus_scanner.py`), to derive
`agent_adoption_intensity` -- it just never persisted the count itself. This
script reuses the exact same clone shape (shallow-since `AGENT_CORPUS_START_
DATE`, blob-size-filtered) and the exact same counting function, so a
backfilled row means the same thing as a row a fresh `analyze` run would
produce -- not an independent/approximate reconstruction. (A GitHub-API
Link-header trick could get a same-shaped number without cloning, but the
API's commit list includes merge commits with no server-side way to exclude
them, which would silently disagree with `--no-merges` -- not used here for
that reason.)

Resumable by construction: `fetch_repos_missing_total_commits()` only ever
returns repos whose column is still NULL, and each successful repo is
written to the DB immediately (one UPDATE per repo, not batched at the end)
-- the DB row itself is the checkpoint, no separate JSON/CSV bookkeeping
needed. Repos that fail to (re-)clone (renamed/deleted/network trouble since
original collection) are left NULL rather than written as a wrong 0, and are
picked up again by the next run.
"""

import argparse
import concurrent.futures
import sqlite3
from pathlib import Path

from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(PROJECT_ROOT))

from collection import paths
from collection.cli_utils import add_since_arg, add_workers_arg
from collection.config import AGENT_CORPUS_START_DATE, shallow_clone_since
from collection.db import db_session, initialise_db
from collection.ephemeral_clone import temp_clone_commit_history
from collection.logging_utils import get_logger
from collection.tiered_agent_corpus_scanner import count_total_commits_since

logger = get_logger(__name__)


def fetch_repos_missing_total_commits(conn: sqlite3.Connection) -> list[dict]:
    """Repos still missing `total_commits_since_agent_start`. A repo already
    backfilled -- or freshly collected, since `agent_corpus.py` now always
    sets this field -- is never returned again."""
    rows = conn.execute(
        "SELECT id, full_name, clone_url, language FROM repositories "
        "WHERE total_commits_since_agent_start IS NULL"
    ).fetchall()
    return [dict(row) for row in rows]


def backfill_one(repo: dict, since: str) -> tuple[int, int | None]:
    """Clone *repo* and count its commits since *since*. Returns
    (repo_id, total_commits); total_commits is None if the repo couldn't be
    cloned at all, so the caller leaves the column NULL rather than writing
    a wrong 0 (0 should only ever mean "cloned fine, genuinely no commits in
    the window", matching `count_total_commits_since`'s own contract)."""
    repo_id = repo["id"]
    full_name = repo["full_name"]
    clone_url = repo.get("clone_url") or f"https://github.com/{full_name}.git"
    with temp_clone_commit_history(
        clone_url,
        full_name,
        prefix="backfill-total-commits-",
        timeout=300,
        shallow_since=shallow_clone_since(since),
    ) as repo_path:
        if repo_path is None:
            logger.warning(
                "[backfill-total-commits] Clone failed for %s -- leaving "
                "total_commits_since_agent_start NULL",
                full_name,
            )
            return repo_id, None
        total = count_total_commits_since(repo_path, since)
    return repo_id, total


def run(
    db_file: Path,
    since: str = AGENT_CORPUS_START_DATE,
    workers: int = 4,
) -> dict[str, int]:
    """Backfill every Dataset A repo in *db_file* missing
    `total_commits_since_agent_start`. Returns `{"updated": n, "failed": n}`.

    Calls `initialise_db()` first -- self-heals `total_commits_since_agent_
    start` onto a `db/a.db` collected before this column existed (`CREATE
    TABLE IF NOT EXISTS` is a no-op on an already-existing table, so the
    column would otherwise never appear and the query below would crash
    with "no such column"). Safe/idempotent on an already-migrated DB, same
    as every other collection entry point calling it."""
    initialise_db(db_file)
    with db_session(db_file) as conn:
        repos = fetch_repos_missing_total_commits(conn)

    logger.info(
        "[backfill-total-commits] %d repos missing total_commits_since_agent_start",
        len(repos),
    )
    updated = 0
    failed = 0

    workers = max(1, int(workers or 1))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(backfill_one, r, since): r for r in repos}
        with tqdm(total=len(futures), desc="backfill-total-commits", unit="repo") as pbar:
            for fut in concurrent.futures.as_completed(futures):
                repo = futures[fut]
                try:
                    repo_id, total = fut.result()
                except Exception:
                    logger.exception(
                        "[backfill-total-commits] Error backfilling %s",
                        repo.get("full_name"),
                    )
                    failed += 1
                    pbar.update(1)
                    continue

                if total is None:
                    failed += 1
                else:
                    with db_session(db_file) as conn:
                        conn.execute(
                            "UPDATE repositories SET total_commits_since_agent_start = ? "
                            "WHERE id = ?",
                            (total, repo_id),
                        )
                    updated += 1

                pbar.set_postfix(updated=updated, failed=failed)
                pbar.update(1)

    logger.info(
        "[backfill-total-commits] Done: %d updated, %d failed/skipped", updated, failed
    )
    return {"updated": updated, "failed": failed}


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Backfill repositories.total_commits_since_agent_start for "
            "Dataset A repos collected before that column existed."
        )
    )
    parser.add_argument(
        "--db", type=Path, default=paths.db_path("a"), help="Path to db/a.db"
    )
    add_since_arg(parser, default=AGENT_CORPUS_START_DATE)
    add_workers_arg(parser, default=4)
    args = parser.parse_args()

    result = run(args.db, since=args.since, workers=args.workers)
    print(
        f"Backfilled {result['updated']} repos ({result['failed']} failed/skipped) "
        f"in {args.db}"
    )


if __name__ == "__main__":
    main()
