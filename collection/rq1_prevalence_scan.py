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

**Why counts are grouped by the repo's own tagged language, not each
fixture's own detected language:** unlike Dataset C's cross-language-
leakage handling (`find_test_files_with_language()`), this scan uses
`find_test_files_at_commit(repo_path, language=repo_language)` --
restricted to one language. A stray test file in a different language than
the repo's own tag is simply not counted at all, rather than leaking into
a different language's bucket. This keeps each language row's denominator
exactly "repos SEART tagged as that language," with no double-counting
risk across Table 1/2's four language rows.

**Production incident (2026-10-02, part 3 -- shallow clone hid the true
cutoff commit for most of the "no commit at or before cutoff" bucket):**
`RQ1_SHALLOW_SINCE` (2026-07-01) sits over 2 months *before*
`RQ1_CUTOFF_DATE` (2026-09-08), deliberately, so a truncated-but-trusted
shallow clone can't accidentally hide a real cutoff candidate close to the
boundary. But `clone_primitives._shallow_clone_is_truncated()` only
detects one specific failure mode: a shallow-boundary commit whose true
parent is *itself inside* the requested window (a graft hiding an
in-window commit). It does **not** detect a different, and in this run
far more common, failure mode: a repo with zero commits anywhere in
`[RQ1_SHALLOW_SINCE, RQ1_CUTOFF_DATE]` at all. For such a repo, the
`--shallow-since` clone's earliest visible commit is already *after*
`RQ1_CUTOFF_DATE`, so `find_cutoff_commit()` correctly finds no candidate
*inside that clone* -- but the real answer (a commit before
`RQ1_SHALLOW_SINCE`) sits just outside the shallow boundary, never
fetched at all. Confirmed directly: of 25 repos sampled from this run's
"no_commit_at_or_before_cutoff" rows, all 25 turned out to have a real
commit before `RQ1_CUTOFF_DATE` once cloned in full -- this bug, not a
quiet period, was almost certainly the cause for the overwhelming majority
of that bucket. `_resolve_cutoff_commit()` closes this: whenever
`find_cutoff_commit()` finds nothing AND the clone is shallow
(`.git/shallow` exists), the clone is discarded and redone in full before
"no commit found" is trusted. Repos that *did* get a cutoff commit from a
shallow clone were never at risk of a wrong (too-early) answer from this
bug -- by construction, if the true latest-commit-before-cutoff existed
inside the shallow window, it would have been found correctly; the bug
only ever produces a false *negative*, never a false commit SHA. Fixed
retroactively via `retry_failed_repos()` against the already-collected db
(see that function's own docstring) rather than a from-scratch re-run.

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

import argparse
import base64
import csv
import gzip
import json
import logging
import shutil
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from . import paths
from .clone_primitives import (
    _output_requests_credentials,
    clone_repo_for_commit_scan,
    run_git_no_prompt,
)
from .config import CLONES_DIR, GITHUB_TOKEN
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
DEFAULT_WORKERS = 12

# Hard wall-clock budget for one repo's entire process_repo() call (clone +
# checkout + find_cutoff_commit + scan_working_tree). See
# run_with_deadline()'s docstring for the production incident (2026-10-02)
# that made this necessary: every individual git subprocess call already
# has its own timeout, but find_cutoff_commit()'s PyDriller traversal and
# scan_working_tree()'s tree-sitter parsing had none -- a single repo stuck
# in either eventually exhausts run_parallel_per_repo()'s entire fixed-size
# worker pool over a long enough run. Generous relative to every real
# timing observed in testing (worst real case: ~180s for a large repo).
PROCESS_REPO_TIMEOUT_SECONDS = 600

# Same ntfy.sh topic internal-docs/RUN_COMMANDS.md's own curl -d pushes use
# between separate CLI invocations -- here it's one push per language chunk
# (plus one final push) from inside this single long-running script instead.
NTFY_TOPIC = "joaofix_fixturedb"

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


def github_auth_env(token: str = GITHUB_TOKEN) -> dict[str, str]:
    """Extra env vars authenticating every git clone in this scan against
    GitHub, when a token is available -- `{}` (unauthenticated, same as
    before) otherwise.

    Production incident (2026-10-02, part 1): running unauthenticated at
    `--workers 16` for ~2 hours, the java chunk succeeded at ~97%, but the
    following javascript chunk collapsed to ~10% -- GitHub throttling
    sustained high-volume unauthenticated clone traffic from one IP.
    Repos that failed on the server cloned instantly from an unrelated
    machine with the exact same command, confirming it was IP-level
    throttling, not the repos.

    Production incident (2026-10-02, part 2 -- the first fix was itself
    wrong): the first version of this function sent `Authorization:
    Bearer <token>`, which works for GitHub's REST API but is REJECTED by
    GitHub's git-over-HTTPS smart-HTTP endpoint with `remote: invalid
    credentials` / `fatal: Authentication failed` -- confirmed directly.
    That made every authenticated clone attempt fail instantly rather
    than slowly, which is exactly how an entire resumed run (java already
    done, the rest of javascript plus all of python and typescript)
    finished in ~13 minutes with 100% failures instead of the many hours
    it should have taken -- a worse outcome than being unauthenticated,
    confirmed by directly reproducing both the broken `Bearer` scheme and
    the correct one against a real clone. GitHub's git HTTP auth wants
    HTTP Basic, not Bearer: `Authorization: Basic
    base64("x-access-token:<token>")` -- any non-empty username works,
    `x-access-token` matches GitHub's own documented convention for
    token-based git auth. Confirmed working directly (real clone, exit 0)
    before trusting this a second time.

    Injects the header via the `GIT_CONFIG_COUNT`/`GIT_CONFIG_KEY_0`/
    `GIT_CONFIG_VALUE_0` env-var mechanism (git >= 2.31) rather than a
    `-c http.extraHeader=...` flag or embedding the token in the clone
    URL -- either of those would put the token in this process's own
    argv, visible to any other user on a shared server via a plain
    `ps aux`/`ps -ef`. An environment variable isn't (same reasoning
    `run_git_no_prompt()`'s `extra_env` parameter documents). The token
    is read once from `config.GITHUB_TOKEN` (loaded from `.env` by
    `config.py` itself) and never logged, printed, or persisted anywhere
    in this module.
    """
    if not token:
        return {}
    basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    return {
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "http.extraHeader",
        "GIT_CONFIG_VALUE_0": f"Authorization: Basic {basic}",
    }


def _full_clone_with_timeout(
    clone_url: str,
    target_dir: Path,
    *,
    timeout: int = FALLBACK_CLONE_TIMEOUT_SECONDS,
    extra_env: dict[str, str] | None = None,
) -> bool:
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
        result = run_git_no_prompt(
            args, capture_output=True, text=True, timeout=timeout, extra_env=extra_env
        )
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


def _clone_with_shallow_fallback(
    clone_url: str,
    target_dir: Path,
    *,
    shallow_since: str,
    extra_env: dict[str, str] | None = None,
) -> bool:
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
    if clone_repo_for_commit_scan(
        clone_url, target_dir, shallow_since=shallow_since, extra_env=extra_env
    ):
        return True
    if target_dir.exists():
        shutil.rmtree(target_dir, ignore_errors=True)
    return _full_clone_with_timeout(clone_url, target_dir, extra_env=extra_env)


def _resolve_cutoff_commit(
    repo_path: Path,
    clone_url: str,
    cutoff_date: str,
    *,
    extra_env: dict[str, str] | None = None,
) -> dict[str, str] | None:
    """`find_cutoff_commit(repo_path, cutoff_date)`, but never trusts a
    `None` result coming from a still-shallow clone (`.git/shallow`
    exists) -- see this module's "Production incident ... part 3"
    docstring section for the exact failure mode: a repo with zero
    commits inside `[shallow_since, cutoff_date]` has every commit in its
    shallow clone falling *after* `cutoff_date`, so `find_cutoff_commit()`
    correctly finds nothing *in that clone*, while the real
    latest-commit-before-cutoff sits just outside the shallow boundary,
    never fetched. On that ambiguous `None`, this discards the shallow
    clone and redoes it as a full clone before accepting "no commit
    found" as the real answer. A `None` from an already-full clone
    (`.git/shallow` absent) is trusted immediately -- that's a genuine
    answer, not an artifact of the shallow boundary.

    Returns `None` if there is genuinely no commit at or before
    `cutoff_date` (full history checked), or if the full-clone retry
    itself fails (network/size/timeout) -- the caller can't distinguish
    those two in isolation, but both correctly result in `clone_ok=0`.
    """
    cutoff = find_cutoff_commit(repo_path, cutoff_date=cutoff_date)
    if cutoff is not None:
        return cutoff
    if not (repo_path / ".git" / "shallow").exists():
        return None
    shutil.rmtree(repo_path, ignore_errors=True)
    if not _full_clone_with_timeout(clone_url, repo_path, extra_env=extra_env):
        return None
    return find_cutoff_commit(repo_path, cutoff_date=cutoff_date)


def process_repo(
    repo: dict,
    clones_dir: Path,
    *,
    cutoff_date: str = RQ1_CUTOFF_DATE,
    shallow_since: str = RQ1_SHALLOW_SINCE,
    extra_env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Clone (shallow-since, pinned to `cutoff_date`), checkout, and scan
    one repo. Never raises -- any failure (clone/no-history-at-cutoff/
    checkout/scan) is captured as a zero-filled row with `clone_ok=0` and
    `error_reason` set, so one bad repo can never crash a ~24.7k-repo run.
    Runs in a worker thread when called via `run_parallel_per_repo()` --
    touches no shared DB connection or other non-thread-safe resource.

    `extra_env` authenticates the clone (see `github_auth_env()`) -- `None`
    (the default) clones unauthenticated, same as before.
    """
    repo_name = repo["repo_name"]
    language = repo["language"]
    clone_url = repo["clone_url"]
    repo_path = clones_dir / repo_name.replace("/", "__")
    scanned_at = datetime.now(timezone.utc).isoformat()

    def _clone_fn(url: str, target: Path) -> bool:
        return _clone_with_shallow_fallback(url, target, shallow_since=shallow_since, extra_env=extra_env)

    with clone_with_function(_clone_fn, clone_url, repo_path) as managed_path:
        if managed_path is None:
            return _result_row(repo_name, language, scanned_at, clone_ok=False, error_reason="clone_failed")

        cutoff = _resolve_cutoff_commit(managed_path, clone_url, cutoff_date, extra_env=extra_env)
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


def _notify(message: str, *, topic: str = NTFY_TOPIC) -> None:
    """Best-effort ntfy.sh push -- same `curl -d ... ntfy.sh/joaofix_fixturedb`
    convention `internal-docs/RUN_COMMANDS.md` already uses between separate
    CLI invocations, just issued from inside this one long-running script.
    A notification failure (ntfy.sh down, no network) must never interrupt
    or fail a multi-hour scan -- every error is swallowed, logged at DEBUG
    only."""
    try:
        subprocess.run(
            ["curl", "-s", "-d", message, f"ntfy.sh/{topic}"],
            capture_output=True,
            timeout=15,
        )
    except Exception:
        logger.debug("[RQ1 scan] ntfy notification failed, continuing", exc_info=True)


def run_with_deadline(
    fn: Callable[..., dict[str, Any]], *args: Any, timeout_seconds: float, **kwargs: Any
) -> tuple[bool, dict[str, Any] | None]:
    """Run `fn(*args, **kwargs)` with a hard wall-clock deadline. Returns
    `(True, result)` if it finished in time, `(False, None)` if not.

    Production incident (2026-10-02): `process_repo()`'s git/network steps
    are all individually timeout-bound (clone, checkout), but
    `find_cutoff_commit()`'s PyDriller commit-history walk and
    `scan_working_tree()`'s tree-sitter parsing are pure in-process Python/
    C-extension work with no timeout at all. A real run froze for 6+ hours
    on exactly this: the process stayed alive and CPU-bound, but with zero
    git subprocess running and zero progress, because one repo's extraction
    step never returned. Worse than just one stuck repo: `run_parallel_per_
    repo()`'s `ThreadPoolExecutor` has a *fixed* worker count -- a thread
    that never returns permanently removes one worker from the pool, so
    over enough repos this eventually exhausts every worker and the whole
    scan stalls forever, exactly as happened.

    This runs `fn` in a daemon thread and only waits up to `timeout_seconds`
    for it. If it doesn't finish in time, this function gives up and
    returns immediately -- the underlying call, if genuinely stuck in
    code that can't be interrupted (a C extension not checking for Python
    signals), keeps running orphaned in the background rather than being
    forcibly killed (Python cannot safely kill a thread), but it can no
    longer block anything: the caller's own worker thread/slot is freed
    the moment this function returns, so a stuck repo costs one wasted
    thread, not the entire pipeline.
    """
    box: dict[str, Any] = {}

    def _target() -> None:
        box["result"] = fn(*args, **kwargs)

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()
    thread.join(timeout_seconds)
    if thread.is_alive():
        return False, None
    return True, box.get("result")


def run_scan(
    raw_dir: Path = paths.RAW_SEARCH_DIR,
    duplicates_path: Path = DUPLICATES_PATH,
    clones_dir: Path = CLONES_DIR,
    db_path: Path = DB_PATH,
    progress_path: Path = PROGRESS_PATH,
    workers: int = DEFAULT_WORKERS,
    cutoff_date: str = RQ1_CUTOFF_DATE,
    shallow_since: str = RQ1_SHALLOW_SINCE,
    log_every: int = PROGRESS_LOG_EVERY,
    notify: bool = True,
    process_repo_timeout_seconds: float = PROCESS_REPO_TIMEOUT_SECONDS,
    extra_env: dict[str, str] | None = None,
) -> dict[str, int]:
    """Scan every not-yet-scanned repo in the raw universe, persisting each
    result immediately. Resumable by construction (see
    `load_scanned_repo_names()`'s and `_write_progress()`'s docstrings for
    why no separate checkpoint file is needed for correctness -- `db_path`
    itself is the checkpoint). Logs a progress line and refreshes
    `progress_path` every `log_every` completions (see `_persist()` below).

    Processes one `RQ1_LANGUAGES` chunk at a time (workers still fully
    parallelized *within* each chunk -- every chunk vastly outnumbers
    `workers`, so this costs nothing in practice) rather than one single
    pass over every language interleaved, purely so `notify` (when True)
    can push one ntfy.sh notification per language finished, plus one
    final push -- a natural, cheap way to split a multi-hour run into a
    handful of "still alive, here's where it's at" pings, matching
    `internal-docs/RUN_COMMANDS.md`'s existing per-step notification
    convention. Set `notify=False` for tests/local runs that shouldn't
    hit the network.

    `extra_env` defaults to `None` here (not `github_auth_env()`) so a
    test calling `run_scan()` directly never implicitly authenticates --
    `main()` is the one real entrypoint that opts in explicitly.
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
        ok, result = run_with_deadline(
            process_repo,
            repo,
            clones_dir,
            cutoff_date=cutoff_date,
            shallow_since=shallow_since,
            extra_env=extra_env,
            timeout_seconds=process_repo_timeout_seconds,
        )
        if ok:
            return result
        logger.warning(
            "[RQ1 scan] %s exceeded the %ds per-repo deadline -- abandoning "
            "(the underlying work keeps running orphaned, but no longer "
            "blocks the scan)",
            repo["repo_name"],
            process_repo_timeout_seconds,
        )
        return _result_row(
            repo["repo_name"],
            repo["language"],
            datetime.now(timezone.utc).isoformat(),
            clone_ok=False,
            error_reason="timeout",
        )

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

    pending_by_language: dict[str, list[dict]] = {}
    for repo in pending:
        pending_by_language.setdefault(repo["language"], []).append(repo)

    for idx, language in enumerate(RQ1_LANGUAGES, start=1):
        chunk = pending_by_language.get(language, [])
        logger.info(
            "[RQ1 scan] language %d/%d: %s (%d repos pending in this chunk)",
            idx,
            len(RQ1_LANGUAGES),
            language,
            len(chunk),
        )
        run_parallel_per_repo(chunk, _compute, _persist, workers, desc=f"[RQ1 scan {language}]")
        if notify:
            _notify(
                f"RQ1 scan {idx}/{len(RQ1_LANGUAGES)}: {language} done -- "
                f"{counters['completed']}/{len(pending)} total "
                f"({counters['clone_ok']} clone_ok, {counters['clone_failed']} clone_failed)"
            )

    if notify:
        _notify(
            f"RQ1 scan: all done -- {counters['completed']}/{len(pending)} total "
            f"({counters['clone_ok']} clone_ok, {counters['clone_failed']} clone_failed)"
        )

    return {"total": len(universe), "already_done": len(already_done), "scanned_this_run": len(pending)}


# error_reasons worth re-attempting: all three are plausibly an artifact of
# the clone/network/timing step itself, not a property of the repo's real
# history -- "no_commit_at_or_before_cutoff" per the module docstring's
# "part 3" incident (now fixed via _resolve_cutoff_commit()), "clone_failed"/
# "timeout" as ordinary transient network/contention failures. A
# "scan_failed: ..." reason (e.g. the ENAMETOOLONG cases seen in the real
# run) is deliberately excluded here -- that is a deterministic local-
# filesystem limitation that will fail identically on every retry, not a
# one-off worth spending a retry attempt on.
REPAIRABLE_ERROR_REASONS: tuple[str, ...] = (
    "no_commit_at_or_before_cutoff",
    "clone_failed",
    "timeout",
)


def load_repos_needing_retry(
    error_reasons: tuple[str, ...] = REPAIRABLE_ERROR_REASONS,
    *,
    db_path: Path = DB_PATH,
    raw_dir: Path = paths.RAW_SEARCH_DIR,
    duplicates_path: Path = DUPLICATES_PATH,
) -> list[dict]:
    """Every repo currently persisted with `clone_ok=0` and an
    `error_reason` in `error_reasons` -- cross-referenced back against the
    raw universe to recover each one's `language`/`clone_url` (not stored
    on a failed row, since `_result_row()` zero-fills those on failure).
    Empty list if the db doesn't exist yet, or nothing matches."""
    if not db_path.exists():
        return []
    with db_session(db_path) as conn:
        placeholders = ", ".join("?" for _ in error_reasons)
        rows = conn.execute(
            f"SELECT repo_name FROM {TABLE_NAME} WHERE clone_ok = 0 AND error_reason IN ({placeholders})",
            error_reasons,
        ).fetchall()
    target_names = {r[0] for r in rows}
    if not target_names:
        return []
    universe = load_raw_universe(raw_dir, duplicates_path)
    return [repo for repo in universe if repo["repo_name"] in target_names]


def retry_failed_repos(
    error_reasons: tuple[str, ...] = REPAIRABLE_ERROR_REASONS,
    *,
    raw_dir: Path = paths.RAW_SEARCH_DIR,
    duplicates_path: Path = DUPLICATES_PATH,
    clones_dir: Path = CLONES_DIR,
    db_path: Path = DB_PATH,
    workers: int = DEFAULT_WORKERS,
    cutoff_date: str = RQ1_CUTOFF_DATE,
    shallow_since: str = RQ1_SHALLOW_SINCE,
    process_repo_timeout_seconds: float = PROCESS_REPO_TIMEOUT_SECONDS,
    extra_env: dict[str, str] | None = None,
    notify: bool = True,
) -> dict[str, int]:
    """Re-attempt every repo currently recorded with one of `error_reasons`
    (default: `REPAIRABLE_ERROR_REASONS`) against the *already-collected*
    db, rather than a from-scratch re-run of all ~24.7k repos -- a cheap,
    targeted repair pass for the "part 3" incident (see module docstring)
    plus ordinary transient clone failures/timeouts.

    Each repo is re-run through the exact same `process_repo()` (now using
    the fixed `_resolve_cutoff_commit()`) and persisted via the same
    `persist_result()` upsert `run_scan()` uses -- a repo that still fails
    simply keeps (or gets a fresh) `clone_ok=0` row, identical in shape to
    a first-pass failure; nothing here can corrupt an already-successful
    `clone_ok=1` row, since only repos matching `error_reasons` are
    selected in the first place.

    No per-language chunking (unlike `run_scan()`) -- a repair pass is
    expected to be a small fraction of the full universe, so one `notify`
    push at the end is enough.
    """
    targets = load_repos_needing_retry(
        error_reasons, db_path=db_path, raw_dir=raw_dir, duplicates_path=duplicates_path
    )
    logger.info(
        "[RQ1 retry] %d repos selected for retry (reasons: %s)",
        len(targets),
        ", ".join(error_reasons),
    )

    counters = {"attempted": len(targets), "recovered": 0, "still_failed": 0}

    def _compute(repo: dict) -> dict:
        ok, result = run_with_deadline(
            process_repo,
            repo,
            clones_dir,
            cutoff_date=cutoff_date,
            shallow_since=shallow_since,
            extra_env=extra_env,
            timeout_seconds=process_repo_timeout_seconds,
        )
        if ok:
            return result
        logger.warning(
            "[RQ1 retry] %s exceeded the %ds per-repo deadline -- abandoning",
            repo["repo_name"],
            process_repo_timeout_seconds,
        )
        return _result_row(
            repo["repo_name"],
            repo["language"],
            datetime.now(timezone.utc).isoformat(),
            clone_ok=False,
            error_reason="timeout",
        )

    def _persist(result: dict) -> None:
        persist_result(result, db_path)
        if result["clone_ok"]:
            counters["recovered"] += 1
        else:
            counters["still_failed"] += 1

    run_parallel_per_repo(targets, _compute, _persist, workers, desc="[RQ1 retry]")

    if notify:
        _notify(
            f"RQ1 retry: {counters['recovered']}/{counters['attempted']} repos recovered "
            f"({counters['still_failed']} still failed)"
        )

    return counters


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
    parser = argparse.ArgumentParser(
        description="RQ1 fixture-prevalence scan over the raw repo universe "
        "(github-search-raw/*.csv.gz), independent of Dataset A/B/C."
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        help=f"Concurrent clone workers (default: {DEFAULT_WORKERS})",
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Re-attempt repos currently recorded as clone_ok=0 for a recoverable "
        f"reason ({', '.join(REPAIRABLE_ERROR_REASONS)}) against the existing db, "
        "instead of scanning the full universe.",
    )
    args = parser.parse_args()

    configure_logging()
    add_file_logging()
    extra_env = github_auth_env()
    if not extra_env:
        logger.warning(
            "[RQ1 scan] No GITHUB_TOKEN found -- cloning unauthenticated. "
            "A sustained high-volume run is likely to hit GitHub's abuse "
            "rate limiting (see github_auth_env()'s docstring for the "
            "2026-10-02 incident this caused)."
        )
    if args.retry_failed:
        counts = retry_failed_repos(workers=args.workers, extra_env=extra_env)
        write_csv_outputs()
        print(f"[RQ1 retry] done: {counts}")
        return
    counts = run_scan(workers=args.workers, extra_env=extra_env)
    write_csv_outputs()
    print(f"[RQ1 scan] done: {counts}")


if __name__ == "__main__":
    main()
