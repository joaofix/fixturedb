"""RQ5 (Agent Configuration Files) data collection: how often do root-level
agent configuration files (AGENTS.md, CLAUDE.md, ...) mention test-related
and fixture-related guidance, across the same raw ~24.7k-repo universe
RQ1 measures (`github-search-raw/*.csv.gz`), independent of any Dataset
A/B/C filtering?

Deliberately separate from the Dataset A/B/C pipeline, and from RQ1's own
collection -- not a 4th/5th dataset. Every artifact here is
`rq5_`/`rq5-`-prefixed: this module (`rq5_agent_file_scan.py`, run directly
via `python -m collection.rq5_agent_file_scan`), its database
(`db/rq5_agent_files.db`, never `db/{a,b,c}.db` or `db/rq1_prevalence.db`),
its keyword catalog (`collection/heuristics/rq5_agent_file_keywords.yaml`),
and its CSV output (`rq5-agent-files/`, a sibling of `datasets/`).
`collection/research_questions/rq5.py` is the only other thing that reads
this db -- it renders RQ5's findings report from it, same role rq1.py plays
for `db/rq1_prevalence.db`.

**Reuse, not reimplementation, of RQ1's proven collection infra:** this
scan's corpus (the full raw universe, minus known duplicates), temporal
pinning (same `RQ1_CUTOFF_DATE`/`RQ1_SHALLOW_SINCE`), cloning (shallow with
a tightly-timed-out full-clone fallback), GitHub authentication, the
in-process watchdog timeout, and the resumable "db row = checkpoint"
pattern are *exactly* RQ1's own, already production-hardened through two
real incidents (see `rq1_prevalence_scan.py`'s module docstring: a 6+ hour
freeze, and a rate-limiting/auth-scheme bug). Re-deriving any of that here
would risk reintroducing bugs already fixed once. This module imports
those pieces directly from `rq1_prevalence_scan.py` rather than
duplicating them -- `rq1_prevalence_scan.py` itself is left completely
unmodified (it may be mid-run on a remote server collecting RQ1's real
data while this module is written), so this is read-only reuse, never a
shared refactor of that file.

**Lighter per-repo cost than RQ1:** RQ1 needs a full working-tree checkout
because it tree-sitter-parses every test file. RQ5 only needs the content
of at most a couple of root-level files at one pinned commit, so it never
checks out a working tree at all -- `git ls-tree <sha>` (non-recursive,
satisfying "repository root only, no subdirectories") lists root entries,
and `git show <sha>:<path>` reads a matched file's blob content directly.
This also gives "don't follow a symlink" for free: `git show` on a symlink
blob (mode 120000) returns the literal link-target text, the same as any
other blob -- never the content of whatever it points to.

**Why grouping is by the repo's own tagged language:** same reasoning as
RQ1 -- see that module's docstring. This scan's own `language` column on
both `repo_scan` and `agent_files` is the repo's SEART-tagged language,
not anything inferred from the file content.

**Why match-level detail IS persisted here** (unlike RQ1's deliberate
"counts only" choice): RQ1 only ever needs aggregate counts for its paper
tables. RQ5's whole purpose includes manual review (telling "fixture" the
setup/teardown sense apart from "fixture" the test-data-file sense), which
needs the actual keyword/line/context/code-block-membership for every
match, not just a tally. Persisted immediately per repo (`agent_files`/
`agent_file_matches`, alongside `repo_scan`) rather than accumulated in
memory for the whole run, for the same crash-safety reason RQ1 persists
per-repo rather than per-language-chunk.

python -m collection.rq5_agent_file_scan
"""

from __future__ import annotations

import argparse
import csv
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from . import paths
from .config import CLONES_DIR
from .dataset_c import find_cutoff_commit
from .db import db_session
from .ephemeral_clone import clone_with_function
from .logging_utils import configure_logging, get_logger
from .parallel_utils import run_parallel_per_repo
from .rq1_prevalence_scan import (
    DUPLICATES_PATH,
    _clone_with_shallow_fallback,
    _notify,
    _write_progress,
    add_file_logging,
    github_auth_env,
    load_raw_universe,
    run_with_deadline,
)
from .rq1_prevalence_scan import RQ1_CUTOFF_DATE as RQ5_CUTOFF_DATE
from .rq1_prevalence_scan import RQ1_SHALLOW_SINCE as RQ5_SHALLOW_SINCE

logger = get_logger(__name__)

RQ5_LANGUAGES: tuple[str, ...] = ("java", "javascript", "python", "typescript")

CATALOG_PATH = paths.ROOT_DIR / "collection" / "heuristics" / "rq5_agent_file_keywords.yaml"

DB_PATH = paths.DB_ROOT / "rq5_agent_files.db"
CSV_OUTPUT_DIR = paths.ROOT_DIR / "rq5-agent-files"
PROGRESS_PATH = paths.DB_ROOT / "rq5_agent_files_progress.json"
PROGRESS_LOG_EVERY = 50
LOG_PATH = paths.DB_ROOT / "rq5_agent_files.log"
DEFAULT_WORKERS = 12

# Same reasoning as RQ1's PROCESS_REPO_TIMEOUT_SECONDS -- find_cutoff_commit()'s
# PyDriller traversal is the dominant per-repo cost here too (no tree-sitter
# parsing step to add on top, unlike RQ1), so the same watchdog is needed,
# with the same generous budget.
PROCESS_REPO_TIMEOUT_SECONDS = 600

# Individual `git ls-tree`/`git show` calls against an already-local clone
# (no network) -- generous, but still bounded so a pathological object
# store can't hang a worker indefinitely.
GIT_READ_TIMEOUT_SECONDS = 30

NTFY_TOPIC = "joaofix_fixturedb"

REPO_TABLE_NAME = "repo_scan"
FILE_TABLE_NAME = "agent_files"
MATCH_TABLE_NAME = "agent_file_matches"

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS {REPO_TABLE_NAME} (
    repo_name        TEXT PRIMARY KEY,
    language         TEXT NOT NULL,
    clone_ok         INTEGER NOT NULL DEFAULT 0,
    commit_sha       TEXT,
    commit_date      TEXT,
    num_agent_files  INTEGER NOT NULL DEFAULT 0,
    catalog_version  INTEGER,
    error_reason     TEXT,
    scanned_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS {FILE_TABLE_NAME} (
    repo_name                 TEXT NOT NULL,
    file_name                 TEXT NOT NULL,
    file_type                 TEXT NOT NULL,
    language                  TEXT NOT NULL,
    commit_sha                TEXT NOT NULL,
    has_test                  INTEGER NOT NULL DEFAULT 0,
    has_fixture                INTEGER NOT NULL DEFAULT 0,
    test_match_count          INTEGER NOT NULL DEFAULT 0,
    fixture_match_count       INTEGER NOT NULL DEFAULT 0,
    matched_test_keywords     TEXT NOT NULL DEFAULT '',
    matched_fixture_keywords  TEXT NOT NULL DEFAULT '',
    github_url                TEXT NOT NULL,
    PRIMARY KEY (repo_name, file_name)
);

CREATE TABLE IF NOT EXISTS {MATCH_TABLE_NAME} (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_name     TEXT NOT NULL,
    file_name     TEXT NOT NULL,
    keyword_list  TEXT NOT NULL,
    keyword       TEXT NOT NULL,
    line_number   INTEGER NOT NULL,
    line_context  TEXT NOT NULL,
    in_code_block INTEGER NOT NULL DEFAULT 0
);
"""

_FILE_CSV_FIELDNAMES = [
    "repo_name",
    "file_name",
    "file_type",
    "language",
    "commit_sha",
    "has_test",
    "has_fixture",
    "test_match_count",
    "fixture_match_count",
    "matched_test_keywords",
    "matched_fixture_keywords",
    "github_url",
]

_MATCH_CSV_FIELDNAMES = [
    "repo_name",
    "file_name",
    "keyword_list",
    "keyword",
    "line_number",
    "line_context",
    "in_code_block",
]

_REPO_CSV_FIELDNAMES = [
    "repo_name",
    "language",
    "clone_ok",
    "commit_sha",
    "commit_date",
    "num_agent_files",
    "catalog_version",
    "error_reason",
    "scanned_at",
]

_FENCE_RE = re.compile(r"^(`{3,}|~{3,})")


def initialise_rq5_db(db_path: Path = DB_PATH) -> None:
    """Create all three RQ5 tables if they don't exist yet. Safe to call
    every run -- never drops or truncates existing rows."""
    with db_session(db_path) as conn:
        conn.executescript(SCHEMA)


def load_rq5_keyword_catalog(path: Path = CATALOG_PATH) -> dict[str, Any]:
    """Load the versioned target-file/keyword catalog. Kept as a plain,
    standalone loader (not wired into `collection/heuristics/__init__.py`'s
    loader machinery) -- that module's loaders feed the main agent/fixture
    *detection* pipeline; this catalog has an entirely different consumer
    and shape, and gains nothing from sharing that machinery."""
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _build_keyword_pattern(keyword: str) -> re.Pattern:
    """Case-insensitive, word-boundary-respecting regex for one catalog
    keyword. A keyword containing a literal space (e.g. "before each") is
    split on spaces and re-joined with an optional space-or-hyphen between
    each pair of words, so "before each"/"before-each"/"beforeeach" all
    match the same catalog entry -- a single-token keyword (including a
    camelCase one like "beforeEach") is matched literally instead, since
    it isn't a "multi-word term" in the catalog's own representation.

    `\\b` at both ends is what keeps "test" from matching inside "latest"/
    "contest"/"attestation" -- every catalog keyword starts and ends with
    an alphanumeric character, so this is always a valid boundary.
    """
    words = keyword.split(" ")
    escaped = [re.escape(word) for word in words]
    body = r"[-\s]?".join(escaped)
    return re.compile(rf"\b{body}\b", re.IGNORECASE)


def _build_patterns(keywords: list[str]) -> dict[str, re.Pattern]:
    return {keyword: _build_keyword_pattern(keyword) for keyword in keywords}


def find_keyword_matches(content: str, patterns: dict[str, re.Pattern]) -> list[dict[str, Any]]:
    """Every occurrence (not just every keyword) of any `patterns` key in
    `content`, with line number, trimmed line context, and whether that
    line falls inside a fenced code block (``` or ~~~ delimited, toggled
    per line -- the delimiter line itself is attributed to the fence state
    *before* it toggles, an inconsequential edge case since a bare fence
    marker line never itself contains a catalog keyword)."""
    matches: list[dict[str, Any]] = []
    in_fence = False
    for line_number, line in enumerate(content.splitlines(), start=1):
        stripped = line.strip()
        current_in_fence = in_fence
        for keyword, pattern in patterns.items():
            for _ in pattern.finditer(line):
                matches.append(
                    {
                        "keyword": keyword,
                        "line_number": line_number,
                        "line_context": stripped,
                        "in_code_block": current_in_fence,
                    }
                )
        if _FENCE_RE.match(stripped):
            in_fence = not in_fence
    return matches


def list_root_tree_entries(
    repo_path: Path, sha: str, *, timeout: int = GIT_READ_TIMEOUT_SECONDS
) -> list[tuple[str, str]]:
    """`(name, type)` for every entry in `sha`'s root tree -- `git ls-tree`
    (no `-r`) is non-recursive by construction, which is exactly "look only
    at the repository root, do not search subdirectories." Raises on
    failure (bad sha, corrupt object, git itself missing) -- the caller
    turns that into a `clone_ok=0` row, same as any other per-repo failure.
    """
    result = subprocess.run(
        ["git", "-C", str(repo_path), "ls-tree", sha],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git ls-tree failed: {result.stderr.strip()}")
    entries: list[tuple[str, str]] = []
    for line in result.stdout.splitlines():
        meta, sep, name = line.partition("\t")
        if not sep:
            continue
        meta_parts = meta.split()
        if len(meta_parts) < 2:
            continue
        entries.append((name, meta_parts[1]))
    return entries


def read_file_at_commit(
    repo_path: Path, sha: str, file_name: str, *, timeout: int = GIT_READ_TIMEOUT_SECONDS
) -> str | None:
    """Content of `file_name` as it existed at `sha`, read directly from
    the git object store (`git show <sha>:<path>`) -- no working-tree
    checkout involved, and (see module docstring) a symlink's own blob
    content, not whatever it points to. Decoded permissively
    (`errors="replace"`) since a malformed/non-UTF-8 agent config file must
    never crash the scan -- `None` only on a git-level failure (path
    genuinely absent from that tree), not a decoding issue."""
    result = subprocess.run(
        ["git", "-C", str(repo_path), "show", f"{sha}:{file_name}"],
        capture_output=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        return None
    return result.stdout.decode("utf-8", errors="replace")


def find_target_files_at_commit(
    repo_path: Path, sha: str, target_files: list[str]
) -> list[tuple[str, str]]:
    """Case-insensitive match of `target_files` against `sha`'s root-level
    blob entries. Returns `(on_disk_name, canonical_file_type)` pairs --
    `on_disk_name` preserves whatever case the repo actually used (e.g.
    "agents.md"), `canonical_file_type` is always the catalog's own
    spelling (e.g. "AGENTS.md"), matching this module's "file name" (as
    committed) vs. "file type" (canonical bucket) distinction. A tree
    entry of type "tree" (a subdirectory literally named e.g. "AGENTS.md")
    is deliberately excluded -- only a blob is a file to read.
    """
    canonical_by_casefold = {name.casefold(): name for name in target_files}
    found: list[tuple[str, str]] = []
    for name, obj_type in list_root_tree_entries(repo_path, sha):
        if obj_type != "blob":
            continue
        canonical = canonical_by_casefold.get(name.casefold())
        if canonical is not None:
            found.append((name, canonical))
    return found


def scan_file_content(
    content: str,
    *,
    test_patterns: dict[str, re.Pattern],
    fixture_patterns: dict[str, re.Pattern],
) -> dict[str, list[dict[str, Any]]]:
    """Pure counting/matching logic for one already-fetched file's text --
    independent of git/network, so it's directly unit-testable without a
    real clone."""
    return {
        "test_matches": find_keyword_matches(content, test_patterns),
        "fixture_matches": find_keyword_matches(content, fixture_patterns),
    }


def _repo_row(
    repo_name: str,
    language: str,
    scanned_at: str,
    catalog_version: int | None,
    *,
    clone_ok: bool,
    error_reason: str | None = None,
    commit_sha: str | None = None,
    commit_date: str | None = None,
    num_agent_files: int = 0,
) -> dict[str, Any]:
    return {
        "repo_name": repo_name,
        "language": language,
        "clone_ok": 1 if clone_ok else 0,
        "commit_sha": commit_sha,
        "commit_date": commit_date,
        "num_agent_files": num_agent_files,
        "catalog_version": catalog_version,
        "error_reason": error_reason,
        "scanned_at": scanned_at,
    }


def _scan_result(
    repo_row: dict[str, Any],
    files: list[dict[str, Any]] | None = None,
    matches: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {"repo": repo_row, "files": files or [], "matches": matches or []}


def process_repo(
    repo: dict,
    clones_dir: Path,
    *,
    cutoff_date: str = RQ5_CUTOFF_DATE,
    shallow_since: str = RQ5_SHALLOW_SINCE,
    extra_env: dict[str, str] | None = None,
    catalog: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Clone (shallow-since, pinned to `cutoff_date` -- identical policy to
    RQ1's own `process_repo()`), locate `catalog`'s `target_files` at the
    repo's root as of the cutoff commit, and keyword-scan each one found.
    Never raises -- any failure is captured as a zero-filled row with
    `clone_ok=0` and `error_reason` set. Runs in a worker thread when
    called via `run_parallel_per_repo()`.

    `catalog` defaults to loading `CATALOG_PATH` fresh when omitted --
    callers processing many repos in one run (`run_scan()`) should load it
    once and pass it through, both for efficiency and so every repo in one
    run is measured against the exact same catalog contents.
    """
    catalog = catalog or load_rq5_keyword_catalog()
    target_files = catalog["target_files"]
    test_patterns = _build_patterns(catalog["test_keywords"])
    fixture_patterns = _build_patterns(catalog["fixture_keywords"])
    catalog_version = catalog.get("version")

    repo_name = repo["repo_name"]
    language = repo["language"]
    clone_url = repo["clone_url"]
    repo_path = clones_dir / repo_name.replace("/", "__")
    scanned_at = datetime.now(timezone.utc).isoformat()

    def _fail(error_reason: str) -> dict[str, Any]:
        return _scan_result(
            _repo_row(repo_name, language, scanned_at, catalog_version, clone_ok=False, error_reason=error_reason)
        )

    def _clone_fn(url: str, target: Path) -> bool:
        return _clone_with_shallow_fallback(url, target, shallow_since=shallow_since, extra_env=extra_env)

    with clone_with_function(_clone_fn, clone_url, repo_path) as managed_path:
        if managed_path is None:
            return _fail("clone_failed")

        cutoff = find_cutoff_commit(managed_path, cutoff_date=cutoff_date)
        if cutoff is None:
            return _fail("no_commit_at_or_before_cutoff")

        try:
            matched = find_target_files_at_commit(managed_path, cutoff["sha"], target_files)
        except Exception as exc:
            return _fail(f"ls_tree_failed: {exc}")

        files: list[dict[str, Any]] = []
        matches: list[dict[str, Any]] = []
        for on_disk_name, file_type in matched:
            try:
                content = read_file_at_commit(managed_path, cutoff["sha"], on_disk_name)
            except Exception as exc:
                logger.debug(
                    "[RQ5 scan] failed reading %s in %s: %s", on_disk_name, repo_name, exc
                )
                continue
            if content is None:
                continue

            scanned = scan_file_content(content, test_patterns=test_patterns, fixture_patterns=fixture_patterns)
            test_matches = scanned["test_matches"]
            fixture_matches = scanned["fixture_matches"]
            matched_test_keywords = sorted({m["keyword"] for m in test_matches})
            matched_fixture_keywords = sorted({m["keyword"] for m in fixture_matches})

            files.append(
                {
                    "repo_name": repo_name,
                    "file_name": on_disk_name,
                    "file_type": file_type,
                    "language": language,
                    "commit_sha": cutoff["sha"],
                    "has_test": bool(test_matches),
                    "has_fixture": bool(fixture_matches),
                    "test_match_count": len(test_matches),
                    "fixture_match_count": len(fixture_matches),
                    "matched_test_keywords": ",".join(matched_test_keywords),
                    "matched_fixture_keywords": ",".join(matched_fixture_keywords),
                    "github_url": f"https://github.com/{repo_name}/blob/{cutoff['sha']}/{on_disk_name}",
                }
            )
            for match in test_matches:
                matches.append({"repo_name": repo_name, "file_name": on_disk_name, "keyword_list": "test", **match})
            for match in fixture_matches:
                matches.append(
                    {"repo_name": repo_name, "file_name": on_disk_name, "keyword_list": "fixture", **match}
                )

        repo_row = _repo_row(
            repo_name,
            language,
            scanned_at,
            catalog_version,
            clone_ok=True,
            commit_sha=cutoff["sha"],
            commit_date=cutoff["date"],
            num_agent_files=len(files),
        )
        return _scan_result(repo_row, files, matches)


def load_scanned_repo_names(db_path: Path = DB_PATH) -> set[str]:
    """Same resume mechanism as RQ1's own -- `repo_scan`'s rows are the
    checkpoint, no separate checkpoint file needed."""
    if not db_path.exists():
        return set()
    with db_session(db_path) as conn:
        try:
            rows = conn.execute(f"SELECT repo_name FROM {REPO_TABLE_NAME}").fetchall()
        except Exception:
            return set()
    return {r[0] for r in rows}


def persist_result(result: dict[str, Any], db_path: Path = DB_PATH) -> None:
    """Upsert one repo's `repo_scan` row, and fully replace its
    `agent_files`/`agent_file_matches` rows (delete-then-insert) -- so
    re-processing the same repo (a retried run, or a deliberate single-repo
    re-scan) never duplicates or leaves stale match rows behind."""
    repo_row = result["repo"]
    files = result["files"]
    matches = result["matches"]
    repo_name = repo_row["repo_name"]

    with db_session(db_path) as conn:
        conn.execute(
            f"""
            INSERT INTO {REPO_TABLE_NAME}
                (repo_name, language, clone_ok, commit_sha, commit_date,
                 num_agent_files, catalog_version, error_reason, scanned_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(repo_name) DO UPDATE SET
                language=excluded.language,
                clone_ok=excluded.clone_ok,
                commit_sha=excluded.commit_sha,
                commit_date=excluded.commit_date,
                num_agent_files=excluded.num_agent_files,
                catalog_version=excluded.catalog_version,
                error_reason=excluded.error_reason,
                scanned_at=excluded.scanned_at
            """,
            (
                repo_row["repo_name"],
                repo_row["language"],
                repo_row["clone_ok"],
                repo_row["commit_sha"],
                repo_row["commit_date"],
                repo_row["num_agent_files"],
                repo_row["catalog_version"],
                repo_row["error_reason"],
                repo_row["scanned_at"],
            ),
        )

        conn.execute(f"DELETE FROM {FILE_TABLE_NAME} WHERE repo_name = ?", (repo_name,))
        conn.execute(f"DELETE FROM {MATCH_TABLE_NAME} WHERE repo_name = ?", (repo_name,))

        if files:
            conn.executemany(
                f"""
                INSERT INTO {FILE_TABLE_NAME}
                    (repo_name, file_name, file_type, language, commit_sha,
                     has_test, has_fixture, test_match_count, fixture_match_count,
                     matched_test_keywords, matched_fixture_keywords, github_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        f["repo_name"],
                        f["file_name"],
                        f["file_type"],
                        f["language"],
                        f["commit_sha"],
                        1 if f["has_test"] else 0,
                        1 if f["has_fixture"] else 0,
                        f["test_match_count"],
                        f["fixture_match_count"],
                        f["matched_test_keywords"],
                        f["matched_fixture_keywords"],
                        f["github_url"],
                    )
                    for f in files
                ],
            )

        if matches:
            conn.executemany(
                f"""
                INSERT INTO {MATCH_TABLE_NAME}
                    (repo_name, file_name, keyword_list, keyword, line_number,
                     line_context, in_code_block)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        m["repo_name"],
                        m["file_name"],
                        m["keyword_list"],
                        m["keyword"],
                        m["line_number"],
                        m["line_context"],
                        1 if m["in_code_block"] else 0,
                    )
                    for m in matches
                ],
            )


def write_csv_outputs(db_path: Path = DB_PATH, output_dir: Path = CSV_OUTPUT_DIR) -> dict[str, Path]:
    """Three CSVs, the "real, reviewable output" counterpart to
    `db/rq5_agent_files.db`: `repo_scan.csv` (every repo attempted, incl.
    skipped ones and why), `agent_files.csv` (per-file, the user-facing
    table this RQ is built around), and `agent_file_matches.csv` (per-match
    detail, for manual review)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    with db_session(db_path) as conn:
        for table, fieldnames, filename in (
            (REPO_TABLE_NAME, _REPO_CSV_FIELDNAMES, "repo_scan.csv"),
            (FILE_TABLE_NAME, _FILE_CSV_FIELDNAMES, "agent_files.csv"),
            (MATCH_TABLE_NAME, _MATCH_CSV_FIELDNAMES, "agent_file_matches.csv"),
        ):
            rows = conn.execute(f"SELECT {', '.join(fieldnames)} FROM {table}").fetchall()
            out_path = output_dir / filename
            with out_path.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(fieldnames)
                writer.writerows(rows)
            written[table] = out_path
    return written


def run_scan(
    raw_dir: Path = paths.RAW_SEARCH_DIR,
    duplicates_path: Path = DUPLICATES_PATH,
    clones_dir: Path = CLONES_DIR,
    db_path: Path = DB_PATH,
    progress_path: Path = PROGRESS_PATH,
    workers: int = DEFAULT_WORKERS,
    cutoff_date: str = RQ5_CUTOFF_DATE,
    shallow_since: str = RQ5_SHALLOW_SINCE,
    log_every: int = PROGRESS_LOG_EVERY,
    notify: bool = True,
    process_repo_timeout_seconds: float = PROCESS_REPO_TIMEOUT_SECONDS,
    extra_env: dict[str, str] | None = None,
    catalog_path: Path = CATALOG_PATH,
) -> dict[str, int]:
    """Scan every not-yet-scanned repo in the raw universe, persisting each
    result immediately. Resumable by construction (`db_path`'s own rows
    are the checkpoint -- see `load_scanned_repo_names()`). Logs a progress
    line and refreshes `progress_path` every `log_every` completions, and
    (when `notify`) pushes one ntfy.sh notification per `RQ5_LANGUAGES`
    chunk finished plus one final push -- identical operational shape to
    `rq1_prevalence_scan.run_scan()`, for the same reasons (this is an
    equally long, equally unattended multi-hour run over the same ~24.7k
    repos).

    The catalog is loaded once here (not once per repo) and threaded
    through every `process_repo()` call, so a run's repos are all measured
    against the exact same keyword/target-file set even if the catalog
    file is hand-edited between runs (the next run would then see a new
    `catalog_version` and should be treated as a fresh collection, not
    resumed, if the edit changes who it was mid-run -- not handled
    automatically, as it only matters for pre-run human judgement).
    """
    initialise_rq5_db(db_path)
    catalog = load_rq5_keyword_catalog(catalog_path)
    universe = load_raw_universe(raw_dir, duplicates_path)
    already_done = load_scanned_repo_names(db_path)
    pending = [r for r in universe if r["repo_name"] not in already_done]

    logger.info(
        "[RQ5 scan] %d repos total, %d already scanned, %d pending",
        len(universe),
        len(already_done),
        len(pending),
    )

    started_at = datetime.now(timezone.utc)
    counters = {"completed": 0, "clone_ok": 0, "clone_failed": 0, "agent_files_found": 0}

    def _compute(repo: dict) -> dict:
        ok, result = run_with_deadline(
            process_repo,
            repo,
            clones_dir,
            cutoff_date=cutoff_date,
            shallow_since=shallow_since,
            extra_env=extra_env,
            catalog=catalog,
            timeout_seconds=process_repo_timeout_seconds,
        )
        if ok:
            return result
        logger.warning(
            "[RQ5 scan] %s exceeded the %ds per-repo deadline -- abandoning",
            repo["repo_name"],
            process_repo_timeout_seconds,
        )
        return _scan_result(
            _repo_row(
                repo["repo_name"],
                repo["language"],
                datetime.now(timezone.utc).isoformat(),
                catalog.get("version"),
                clone_ok=False,
                error_reason="timeout",
            )
        )

    def _persist(result: dict) -> None:
        persist_result(result, db_path)

        counters["completed"] += 1
        if result["repo"]["clone_ok"]:
            counters["clone_ok"] += 1
        else:
            counters["clone_failed"] += 1
        counters["agent_files_found"] += len(result["files"])

        is_last = counters["completed"] == len(pending)
        if log_every <= 0 or (counters["completed"] % log_every != 0 and not is_last):
            return

        elapsed = max((datetime.now(timezone.utc) - started_at).total_seconds(), 0.0001)
        rate = counters["completed"] / elapsed
        remaining = len(pending) - counters["completed"]
        eta_seconds = remaining / rate if rate > 0 else None

        logger.info(
            "[RQ5 scan] %d/%d done (%d clone_ok, %d clone_failed, %d agent files found) -- "
            "%.2f repos/s, ETA %s",
            counters["completed"],
            len(pending),
            counters["clone_ok"],
            counters["clone_failed"],
            counters["agent_files_found"],
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
                "agent_files_found": counters["agent_files_found"],
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

    for idx, language in enumerate(RQ5_LANGUAGES, start=1):
        chunk = pending_by_language.get(language, [])
        logger.info(
            "[RQ5 scan] language %d/%d: %s (%d repos pending in this chunk)",
            idx,
            len(RQ5_LANGUAGES),
            language,
            len(chunk),
        )
        run_parallel_per_repo(chunk, _compute, _persist, workers, desc=f"[RQ5 scan {language}]")
        if notify:
            _notify(
                f"RQ5 scan {idx}/{len(RQ5_LANGUAGES)}: {language} done -- "
                f"{counters['completed']}/{len(pending)} total "
                f"({counters['clone_ok']} clone_ok, {counters['clone_failed']} clone_failed, "
                f"{counters['agent_files_found']} agent files found)"
            )

    if notify:
        _notify(
            f"RQ5 scan: all done -- {counters['completed']}/{len(pending)} total "
            f"({counters['clone_ok']} clone_ok, {counters['clone_failed']} clone_failed, "
            f"{counters['agent_files_found']} agent files found)"
        )

    return {"total": len(universe), "already_done": len(already_done), "scanned_this_run": len(pending)}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="RQ5 agent-configuration-file keyword scan over the raw repo "
        "universe (github-search-raw/*.csv.gz), independent of Dataset A/B/C."
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        help=f"Concurrent clone workers (default: {DEFAULT_WORKERS})",
    )
    args = parser.parse_args()

    configure_logging()
    add_file_logging(LOG_PATH)
    extra_env = github_auth_env()
    if not extra_env:
        logger.warning(
            "[RQ5 scan] No GITHUB_TOKEN found -- cloning unauthenticated. See "
            "rq1_prevalence_scan.github_auth_env()'s docstring for why this "
            "risks GitHub rate-limiting on a sustained high-volume run."
        )
    counts = run_scan(workers=args.workers, extra_env=extra_env)
    write_csv_outputs()
    print(f"[RQ5 scan] done: {counts}")


if __name__ == "__main__":
    main()
