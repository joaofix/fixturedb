"""RQ1 (Fixture Prevalence) data collection: how common are tests, fixtures,
setup, and teardown across the *raw* ~24.7k-repo universe in
`github-search-raw/*.csv.gz`, independent of any Dataset A/B/C filtering?

Deliberately separate from the Dataset A/B/C pipeline -- this is not a 4th
dataset. Every artifact here is `rq1_`/`rq1-`-prefixed so it can never be
mistaken for part of that pipeline: this module (`rq1_prevalence_scan.py`,
not wired into the `--dataset {a,b,c}` verb system -- run directly via
`python -m collection.rq1_prevalence_scan`), its database (`db/
rq1_prevalence.db`, never `db/{a,b,c}.db`), and its CSV output
(`rq1-prevalence/`, a sibling of `datasets/`, not nested inside it).
`collection/research_questions/rq1.py` is the only other thing that reads
this db -- it renders the two paper tables from it, same role rq2.py/rq3.py/
rq4.py play for db/a.db + db/c.db.

**Temporal pinning (2026-09-xx methodology discussion):** Dataset A and C
were both collected within hours of each other, `db/a.db`/`db/c.db`'s
`repositories.collected_at` maxing at 2026-09-07/2026-09-08. Scanning this
raw universe at "whenever this script happens to run" would let every repo
accrue a few more weeks of commits that A/C never saw, skewing this RQ's
numbers slightly ahead of the rest of the paper's reference point. So this
scan pins every repo to the same `RQ1_CUTOFF_DATE` instead of current HEAD
-- a shallow clone bounded by `RQ1_SHALLOW_SINCE` (verified non-truncated,
falls back to a full clone automatically if it was -- see
`clone_primitives.clone_repo_for_commit_scan`), then `dataset_c.
find_cutoff_commit()` (already a plain `cutoff_date` parameter, not
hardcoded to Dataset C's own cutoff) finds the latest commit at or before
that date, which gets checked out before scanning.

**Why no extra quality floor is needed for the "floor applied" variant:**
`github-search-raw/details.txt`'s SEART crawl ran 2026-08-11, *before*
RQ1_CUTOFF_DATE -- and `min_stars`/`min_commits`/`min_non_blank_loc` in
`study_parameters.yaml` are identical to the SEART crawl's own filters. A
repo only gains commits/LOC over time, so every repo in this raw universe
already trivially clears those two floors as of RQ1_CUTOFF_DATE too. The
only floor that changes which repos qualify is `min_test_files` -- and
that's exactly this scan's own `num_test_files` column, so the "floor
applied" paper table is just a `WHERE num_test_files >= MIN_TEST_FILES`
filter over this same scan's results, not a second, separately-collected
population.

**Why counts are grouped by the repo's own tagged language, not each
fixture's own detected language:** unlike Dataset C's cross-language-
leakage handling (`find_test_files_with_language()`), this scan uses
`find_test_files_at_commit(repo_path, language=repo_language)` --
restricted to one language. A stray test file in a different language than
the repo's own tag is simply not counted at all, rather than leaking into
a different language's bucket. This keeps each language row's denominator
exactly "repos SEART tagged as that language," with no double-counting
risk across Table 1/2's four language rows.

Deliberately NOT persisting fixture-level rows (raw_source, LOC, cyclomatic
complexity, mocks, ...) -- RQ1 only needs counts, so storing ~24.7k repos'
worth of full fixture metrics would be pure waste. `fixture_role` (setup/
teardown/setup_and_teardown/other) is read off each extracted fixture
dict (already computed at extraction time by the shared extractor) and
immediately folded into `num_setup`/`num_teardown`, nothing else is kept.
A `setup_and_teardown` fixture counts toward *both* -- same convention
`research_questions/rq3.py` already uses for its own setup/teardown
tables, for consistency.

python -m collection.rq1_prevalence_scan
"""

from __future__ import annotations

import csv
import gzip
import json
import logging
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import paths
from .clone_primitives import (
    _output_requests_credentials,
    clone_repo_for_commit_scan,
    run_git_no_prompt,
)
from .config import CLONES_DIR
from .dataset_c import find_cutoff_commit, find_test_files_at_commit
from .db import db_session
from .ephemeral_clone import clone_with_function
from .fixture_extractor import AgentFixtureExtractor
from .logging_utils import configure_logging, get_logger
from .parallel_utils import run_parallel_per_repo

logger = get_logger(__name__)

RQ1_LANGUAGES: tuple[str, ...] = ("java", "javascript", "python", "typescript")

# See module docstring's "Temporal pinning" section for why these exist at
# all, rather than just scanning current HEAD.
RQ1_CUTOFF_DATE = "2026-09-08"
RQ1_SHALLOW_SINCE = "2026-07-01"

# Deliberately much tighter than clone_repo_for_commit_scan()'s own hardcoded
# 300s -- see _full_clone_with_timeout()'s docstring for why.
FALLBACK_CLONE_TIMEOUT_SECONDS = 90

DB_PATH = paths.DB_ROOT / "rq1_prevalence.db"
CSV_OUTPUT_DIR = paths.ROOT_DIR / "rq1-prevalence"
DUPLICATES_PATH = paths.RAW_SEARCH_DIR / "duplicate_repos_by_current_commit.csv"
PROGRESS_PATH = paths.DB_ROOT / "rq1_prevalence_progress.json"
PROGRESS_LOG_EVERY = 50
LOG_PATH = paths.DB_ROOT / "rq1_prevalence.log"

TABLE_NAME = "repo_prevalence"

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
    repo_name       TEXT PRIMARY KEY,
    language        TEXT NOT NULL,
    clone_ok        INTEGER NOT NULL DEFAULT 0,
    num_test_files  INTEGER NOT NULL DEFAULT 0,
    num_fixtures    INTEGER NOT NULL DEFAULT 0,
    num_setup       INTEGER NOT NULL DEFAULT 0,
    num_teardown    INTEGER NOT NULL DEFAULT 0,
    error_reason    TEXT,
    scanned_at      TEXT NOT NULL
);
"""

_CSV_FIELDNAMES = [
    "repo_name",
    "language",
    "clone_ok",
    "num_test_files",
    "num_fixtures",
    "num_setup",
    "num_teardown",
    "error_reason",
    "scanned_at",
]


def initialise_rq1_db(db_path: Path = DB_PATH) -> None:
    """Create `repo_prevalence` if it doesn't exist yet. Safe to call every
    run -- never drops or truncates existing rows (plain `CREATE TABLE IF
    NOT EXISTS`, no migrations needed for a single, never-yet-changed
    table)."""
    with db_session(db_path) as conn:
        conn.executescript(SCHEMA)


def load_duplicate_repo_names(duplicates_path: Path = DUPLICATES_PATH) -> set[str]:
    """`repo_name`s to drop entirely -- byte-identical duplicates-at-HEAD of
    another repo already in the pool. Reads `github-search-raw/
    duplicate_repos_by_current_commit.csv` as a static artifact (no live
    API calls) -- the same file `agent_repository_counter.py`'s
    `_dedupe_by_last_commit_sha()` filters Dataset A's own candidate pool
    with. Missing file -> empty set, not an error (lets this run against a
    `github-search-raw/` checkout that predates that artifact)."""
    if not duplicates_path.exists():
        return set()
    with duplicates_path.open(encoding="utf-8", newline="") as fh:
        return {
            row["repo_to_remove"].strip()
            for row in csv.DictReader(fh)
            if (row.get("repo_to_remove") or "").strip()
        }


def load_raw_universe(
    raw_dir: Path = paths.RAW_SEARCH_DIR,
    duplicates_path: Path = DUPLICATES_PATH,
) -> list[dict]:
    """Every repo across all 4 `github-search-raw/*.csv.gz` files, minus
    known duplicates -- the full raw population this RQ measures
    prevalence over, independent of any Dataset A/B/C filtering ("before
    repo filtering").

    Mirrors `select_dataset_c_repos.select_repos()`'s row-reading (name +
    language fallback to the file's own language bucket) minus its
    created-date window -- this RQ has no temporal selection on *which*
    repos qualify, only a fixed scan date (see module docstring) for
    *how* each qualifying repo is measured.

    A repo_name appearing in more than one language file (shouldn't
    happen -- each SEART export is itself language-partitioned -- but
    cheap to guard) is kept only once, under whichever file it's first
    encountered in (files iterated in sorted/deterministic order).
    """
    to_remove = load_duplicate_repo_names(duplicates_path)
    repos: list[dict] = []
    seen: set[str] = set()
    for csv_path in sorted(raw_dir.glob("*.csv.gz"), key=lambda p: p.name):
        file_lang = csv_path.stem.split(".")[0].lower()
        with gzip.open(csv_path, "rt", encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                name = (row.get("name") or "").strip()
                if not name or "/" not in name:
                    continue
                if name in to_remove or name in seen:
                    continue
                seen.add(name)
                language = (row.get("mainLanguage") or file_lang).strip().lower()
                repos.append(
                    {
                        "repo_name": name,
                        "language": language,
                        "clone_url": f"https://github.com/{name}.git",
                    }
                )
    return repos


def scan_working_tree(
    repo_path: Path,
    language: str,
    *,
    cutoff_sha: str = "",
    cutoff_date: str = "",
) -> dict[str, int]:
    """Core counting logic, independent of git/network: given an
    already-checked-out working tree and the repo's own tagged
    `language`, count test files and fixtures restricted to that one
    language (see module docstring for why `find_test_files_at_commit()`,
    not the cross-language `find_test_files_with_language()`).

    `cutoff_sha`/`cutoff_date` are threaded through only as metadata on
    each extracted fixture dict (`AgentFixtureExtractor.
    _extract_from_snapshot_file()`'s own contract) -- not used for
    filtering, and never persisted here, so tests exercising this function
    standalone can safely omit them.
    """
    test_files = find_test_files_at_commit(repo_path, language=language)
    num_fixtures = 0
    num_setup = 0
    num_teardown = 0

    extractor = AgentFixtureExtractor(
        clones_dir=repo_path.parent, source_db=None, start_date="1970-01-01"
    )
    for test_file in test_files:
        try:
            fixtures = extractor._extract_from_snapshot_file(
                repo_path=repo_path,
                file_path=test_file,
                language=language,
                cutoff_commit_sha=cutoff_sha,
                cutoff_commit_date=cutoff_date,
            )
        except Exception as exc:
            logger.debug(
                "[RQ1] Failed to extract fixtures from %s in %s: %s",
                test_file,
                repo_path,
                exc,
            )
            continue
        for fixture in fixtures:
            num_fixtures += 1
            role = fixture.get("fixture_role", "other")
            if role in ("setup", "setup_and_teardown"):
                num_setup += 1
            if role in ("teardown", "setup_and_teardown"):
                num_teardown += 1

    return {
        "num_test_files": len(test_files),
        "num_fixtures": num_fixtures,
        "num_setup": num_setup,
        "num_teardown": num_teardown,
    }


def _result_row(
    repo_name: str,
    language: str,
    scanned_at: str,
    *,
    clone_ok: bool,
    error_reason: str | None = None,
    counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    counts = counts or {"num_test_files": 0, "num_fixtures": 0, "num_setup": 0, "num_teardown": 0}
    return {
        "repo_name": repo_name,
        "language": language,
        "clone_ok": 1 if clone_ok else 0,
        "num_test_files": counts["num_test_files"],
        "num_fixtures": counts["num_fixtures"],
        "num_setup": counts["num_setup"],
        "num_teardown": counts["num_teardown"],
        "error_reason": error_reason,
        "scanned_at": scanned_at,
    }


def _full_clone_with_timeout(clone_url: str, target_dir: Path, *, timeout: int = FALLBACK_CLONE_TIMEOUT_SECONDS) -> bool:
    """A plain (non-shallow) clone with an explicit, tight timeout -- used
    only as `_clone_with_shallow_fallback()`'s own second attempt, never
    as a general-purpose clone primitive.

    Deliberately does NOT call `clone_repo_for_commit_scan(shallow_since=
    None)` for this: that function's own timeout is a hardcoded 300s, and
    it can itself internally retry once more (on a truncated-but-
    succeeded shallow clone), chaining up to ~600s before ever returning
    to its caller. A toy run (2026-10-02) showed one repo taking 673s
    total under concurrent load, yet cloning the exact same repo in
    isolation -- both shallow and full -- took under 10s each; the cost
    is from contention stacking multiple 300s-bounded attempts, not any
    single repo being genuinely hard to clone. This function exists to
    bound *this scan's own* contribution to that worst case tightly
    (real clones complete in single-digit seconds even for sizable repos,
    so `FALLBACK_CLONE_TIMEOUT_SECONDS` is already generous) without
    touching the shared, already-proven `clone_primitives.py` that
    Dataset A/B/C depend on -- reuses its `run_git_no_prompt()`/
    `_output_requests_credentials()` building blocks instead of
    duplicating that safety logic.
    """
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        args = [
            "git",
            "clone",
            "--filter=blob:limit=10m",
            "--single-branch",
            "--no-tags",
            clone_url,
            str(target_dir),
        ]
        result = run_git_no_prompt(args, capture_output=True, text=True, timeout=timeout)
        if _output_requests_credentials(result.stderr):
            return False
        return bool(
            result.returncode == 0
            and target_dir.exists()
            and (list(target_dir.glob(".git")) or list(target_dir.iterdir()))
        )
    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return False


def _clone_with_shallow_fallback(clone_url: str, target_dir: Path, *, shallow_since: str) -> bool:
    """Try a `--shallow-since` clone first (cheap for repos with recent
    activity); if it fails outright, fall back to one tightly-timed-out
    full clone attempt (`_full_clone_with_timeout()`).

    `clone_repo_for_commit_scan()` already retries as a full clone when a
    shallow clone *succeeds but is truncated* (`_shallow_clone_is_truncated`)
    -- this covers the other failure mode it doesn't: git can fail hard
    (observed: "fatal: error processing shallow info: 4") when
    `shallow_since` lands after EVERY commit the repo actually has, which
    is common and unremarkable -- most of this scan's ~24.7k-repo universe
    isn't necessarily active as of `shallow_since`, not just pathological
    repos. Empirically ~47% of a random sample hit this on a first pass
    (toy run, 2026-10-01) -- and a full clone of one of them took 4.6s and
    51MB, confirming these are ordinary repos, not large/complex-history
    ones. A genuinely pathological repo (e.g. an AOSP mirror) is still
    expected to fail or time out on the full-clone fallback too -- a
    bounded, acceptable cost for a rare case, not a reason to skip the
    fallback for the common one.
    """
    if clone_repo_for_commit_scan(clone_url, target_dir, shallow_since=shallow_since):
        return True
    if target_dir.exists():
        shutil.rmtree(target_dir, ignore_errors=True)
    return _full_clone_with_timeout(clone_url, target_dir)


def process_repo(
    repo: dict,
    clones_dir: Path,
    *,
    cutoff_date: str = RQ1_CUTOFF_DATE,
    shallow_since: str = RQ1_SHALLOW_SINCE,
) -> dict[str, Any]:
    """Clone (shallow-since, pinned to `cutoff_date`), checkout, and scan
    one repo. Never raises -- any failure (clone/no-history-at-cutoff/
    checkout/scan) is captured as a zero-filled row with `clone_ok=0` and
    `error_reason` set, so one bad repo can never crash a ~24.7k-repo run.
    Runs in a worker thread when called via `run_parallel_per_repo()` --
    touches no shared DB connection or other non-thread-safe resource.
    """
    repo_name = repo["repo_name"]
    language = repo["language"]
    clone_url = repo["clone_url"]
    repo_path = clones_dir / repo_name.replace("/", "__")
    scanned_at = datetime.now(timezone.utc).isoformat()

    def _clone_fn(url: str, target: Path) -> bool:
        return _clone_with_shallow_fallback(url, target, shallow_since=shallow_since)

    with clone_with_function(_clone_fn, clone_url, repo_path) as managed_path:
        if managed_path is None:
            return _result_row(repo_name, language, scanned_at, clone_ok=False, error_reason="clone_failed")

        cutoff = find_cutoff_commit(managed_path, cutoff_date=cutoff_date)
        if cutoff is None:
            return _result_row(
                repo_name, language, scanned_at, clone_ok=False, error_reason="no_commit_at_or_before_cutoff"
            )

        try:
            subprocess.run(
                ["git", "-C", str(managed_path), "checkout", cutoff["sha"], "--force"],
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except Exception as exc:
            return _result_row(
                repo_name, language, scanned_at, clone_ok=False, error_reason=f"checkout_failed: {exc}"
            )

        try:
            counts = scan_working_tree(
                managed_path, language, cutoff_sha=cutoff["sha"], cutoff_date=cutoff["date"]
            )
        except Exception as exc:
            return _result_row(
                repo_name, language, scanned_at, clone_ok=False, error_reason=f"scan_failed: {exc}"
            )

        return _result_row(repo_name, language, scanned_at, clone_ok=True, counts=counts)


def load_scanned_repo_names(db_path: Path = DB_PATH) -> set[str]:
    """`repo_name`s already persisted -- the resume mechanism. Simpler than
    Dataset C's hand-rolled JSON checkpoint: since every repo's row is
    persisted immediately as it completes (see `run_scan()`), "already
    done" is just "already has a row," no separate checkpoint file
    needed."""
    if not db_path.exists():
        return set()
    with db_session(db_path) as conn:
        try:
            rows = conn.execute(f"SELECT repo_name FROM {TABLE_NAME}").fetchall()
        except Exception:
            return set()
    return {r[0] for r in rows}


def persist_result(result: dict[str, Any], db_path: Path = DB_PATH) -> None:
    """Upsert one repo's row by `repo_name` -- re-processing the same repo
    (e.g. a retried run) replaces its row rather than duplicating it."""
    with db_session(db_path) as conn:
        conn.execute(
            f"""
            INSERT INTO {TABLE_NAME}
                (repo_name, language, clone_ok, num_test_files, num_fixtures,
                 num_setup, num_teardown, error_reason, scanned_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(repo_name) DO UPDATE SET
                language=excluded.language,
                clone_ok=excluded.clone_ok,
                num_test_files=excluded.num_test_files,
                num_fixtures=excluded.num_fixtures,
                num_setup=excluded.num_setup,
                num_teardown=excluded.num_teardown,
                error_reason=excluded.error_reason,
                scanned_at=excluded.scanned_at
            """,
            (
                result["repo_name"],
                result["language"],
                result["clone_ok"],
                result["num_test_files"],
                result["num_fixtures"],
                result["num_setup"],
                result["num_teardown"],
                result["error_reason"],
                result["scanned_at"],
            ),
        )


def write_csv_outputs(db_path: Path = DB_PATH, output_dir: Path = CSV_OUTPUT_DIR) -> dict[str, Path]:
    """One `{language}_repo_prevalence.csv` per `RQ1_LANGUAGES`, the CSV
    "real, reviewable output" counterpart to `db/rq1_prevalence.db`,
    matching `datasets/a/fixtures/*.csv`'s per-language-file shape."""
    output_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    with db_session(db_path) as conn:
        for language in RQ1_LANGUAGES:
            rows = conn.execute(
                f"SELECT {', '.join(_CSV_FIELDNAMES)} FROM {TABLE_NAME} "
                "WHERE language = ? ORDER BY repo_name",
                (language,),
            ).fetchall()
            out_path = output_dir / f"{language}_repo_prevalence.csv"
            with out_path.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(_CSV_FIELDNAMES)
                writer.writerows(rows)
            written[language] = out_path
    return written


def _write_progress(progress_path: Path, state: dict[str, Any]) -> None:
    """JSON progress snapshot for a multi-hour run -- cheap to `cat`/`jq`
    for a point-in-time status check without touching the DB, same role
    `dataset_c.py`'s `_write_dataset_c_progress()` plays there.

    Resume itself doesn't depend on this file: `db_path`'s own rows ARE
    the real checkpoint (a killed/crashed run just restarts `run_scan()`,
    which skips every `repo_name` `load_scanned_repo_names()` already
    finds -- see that function's docstring). This file exists purely for
    visibility into a run that can take hours, same as `run_scan()`'s
    periodic `logger.info()` progress line below.
    """
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    with progress_path.open("w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=2)
        fh.flush()


def run_scan(
    raw_dir: Path = paths.RAW_SEARCH_DIR,
    duplicates_path: Path = DUPLICATES_PATH,
    clones_dir: Path = CLONES_DIR,
    db_path: Path = DB_PATH,
    progress_path: Path = PROGRESS_PATH,
    workers: int = 12,
    cutoff_date: str = RQ1_CUTOFF_DATE,
    shallow_since: str = RQ1_SHALLOW_SINCE,
    log_every: int = PROGRESS_LOG_EVERY,
) -> dict[str, int]:
    """Scan every not-yet-scanned repo in the raw universe, persisting each
    result immediately. Resumable by construction (see
    `load_scanned_repo_names()`'s and `_write_progress()`'s docstrings for
    why no separate checkpoint file is needed for correctness -- `db_path`
    itself is the checkpoint). Logs a progress line and refreshes
    `progress_path` every `log_every` completions and once more at the
    end, so a multi-hour run can be monitored without querying the DB.
    """
    initialise_rq1_db(db_path)
    universe = load_raw_universe(raw_dir, duplicates_path)
    already_done = load_scanned_repo_names(db_path)
    pending = [r for r in universe if r["repo_name"] not in already_done]

    logger.info(
        "[RQ1 scan] %d repos total, %d already scanned, %d pending",
        len(universe),
        len(already_done),
        len(pending),
    )

    started_at = datetime.now(timezone.utc)
    counters = {"completed": 0, "clone_ok": 0, "clone_failed": 0}

    def _compute(repo: dict) -> dict:
        return process_repo(repo, clones_dir, cutoff_date=cutoff_date, shallow_since=shallow_since)

    def _persist(result: dict) -> None:
        persist_result(result, db_path)

        counters["completed"] += 1
        if result["clone_ok"]:
            counters["clone_ok"] += 1
        else:
            counters["clone_failed"] += 1

        is_last = counters["completed"] == len(pending)
        if log_every <= 0 or (counters["completed"] % log_every != 0 and not is_last):
            return

        elapsed = max((datetime.now(timezone.utc) - started_at).total_seconds(), 0.0001)
        rate = counters["completed"] / elapsed
        remaining = len(pending) - counters["completed"]
        eta_seconds = remaining / rate if rate > 0 else None

        logger.info(
            "[RQ1 scan] %d/%d done (%d clone_ok, %d clone_failed) -- %.2f repos/s, ETA %s",
            counters["completed"],
            len(pending),
            counters["clone_ok"],
            counters["clone_failed"],
            rate,
            f"{eta_seconds / 60:.0f}min" if eta_seconds is not None else "unknown",
        )
        _write_progress(
            progress_path,
            {
                "total_repos": len(universe),
                "already_done_at_start": len(already_done),
                "pending_this_run": len(pending),
                "completed_this_run": counters["completed"],
                "clone_ok": counters["clone_ok"],
                "clone_failed": counters["clone_failed"],
                "started_at": started_at.isoformat(),
                "last_updated_at": datetime.now(timezone.utc).isoformat(),
                "elapsed_seconds": elapsed,
                "repos_per_second": rate,
                "estimated_remaining_seconds": eta_seconds,
            },
        )

    run_parallel_per_repo(pending, _compute, _persist, workers, desc="[RQ1 scan]")

    return {"total": len(universe), "already_done": len(already_done), "scanned_this_run": len(pending)}


def add_file_logging(log_path: Path = LOG_PATH) -> None:
    """Attach a durable file handler on top of `configure_logging()`'s
    console-only handler -- this scan can run for hours, and a plain
    terminal session (no nohup/tmux) dying would otherwise take every log
    line with it, leaving only `db_path`/`progress_path`'s point-in-time
    snapshots. Appends (the default `logging.FileHandler` mode) rather
    than truncating, so a resumed run's log history survives a restart,
    same "never wipe prior progress" principle `db_path`/`progress_path`
    already follow.

    This durable log is still not a substitute for running the scan
    itself under `nohup .../tmux`/`screen` -- a killed *process* loses
    all logging regardless of where it's written; this only protects
    against losing output that the process DID produce.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_path)
    handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    logging.getLogger().addHandler(handler)


def main() -> None:
    configure_logging()
    add_file_logging()
    counts = run_scan()
    write_csv_outputs()
    print(f"[RQ1 scan] done: {counts}")


if __name__ == "__main__":
    main()
