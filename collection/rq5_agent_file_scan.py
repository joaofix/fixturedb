"""RQ5 (Agent Configuration Files): how often do agent configuration files
mention test-related and fixture-related guidance, for the repositories that
contribute at least one fixture to Dataset A (agent-created fixtures)?

Files searched: every guidance file in the repository's tree at the snapshot
commit -- a file named AGENTS.md, CLAUDE.md or GEMINI.md (case-insensitive),
at the root or in any subdirectory. References between files are not
followed. A file under a dependency, build or cache directory (`node_modules`,
`vendor`, `build`, ...) is not read. Both lists are in
`collection/heuristics/rq5_agent_guidance_files.yaml`.

A guidance file that is a symbolic link is read through its target (followed
within the tree, at most `MAX_SYMLINK_HOPS` links). A link whose target is
already read (e.g. CLAUDE.md -> AGENTS.md) is not read again, so each real file
is counted once; a link that leaves the tree or points at nothing is not read.

The corpus is read from `datasets/a/fixtures/*_fixtures.csv`. The snapshot
is the last commit on or before `--snapshot-date`, a required argument: the
date of the new Dataset A collection is not fixed yet, so there is no default.
Every run records its snapshot date in the database's `scan_meta` table, and
a run refuses to continue with a different date.

Every artifact here is `rq5_`/`rq5-`-prefixed: this module (run directly via
`python -m collection.rq5_agent_file_scan --snapshot-date YYYY-MM-DD`), its
database (`db/rq5_agent_files.db`), its keyword catalog
(`collection/heuristics/rq5_agent_file_keywords.yaml`), and its review
outputs (`research-questions/rq5/`). `collection/research_questions/rq5.py`
reads this database to write the RQ5 report.

**Why the GitHub API, not a clone:** this scan needs the file list of each
repository and the content of a few Markdown files. GitHub's API returns both
without cloning, so the scan stays fast whatever the size of the repository.
Per batch of `GRAPHQL_BATCH_SIZE` repositories:

1. The cutoff commit: the latest default-branch commit at or before
   `<snapshot_date>T23:59:59Z`, with its root tree entries (one GraphQL query).
2. The full file list at that commit: one REST request per repository
   (`fetch_tree_via_api()`, the recursive Git Trees endpoint). GitHub truncates
   the listing of a very large tree; the tree is then split into one listing
   per subdirectory, split again where still truncated (`fetch_full_tree()`),
   skipping excluded directories.
3. The text of each guidance file (and of each symbolic link, to follow it),
   in batched GraphQL queries. A truncated text is re-read in full through the
   REST blob endpoint (`read_blob_via_api()`).

No disk space, no `ENAMETOOLONG`, no shallow-clone edge cases, no orphaned
clones -- the problems RQ1's clone-based approach had to handle.

**Known difference from RQ1's cutoff-commit rule:** the API filters commits by
UTC time. RQ1 compares each commit's date in its own timezone. For a commit
close to UTC midnight on the cutoff date, the two rules can pick different
commits. GitHub's API does not return a commit's original timezone, so the two
rules cannot be made identical without a clone. The effect is limited to a
window of about 14 hours on the cutoff date. Guidance files change over
weeks, so the file content is almost always the same either way.

**Column naming note:** `repo_scan.fetch_ok` (and `_repo_row()`'s/
`run_scan()`'s `fetch_ok` naming) deliberately does NOT reuse RQ1's
`clone_ok` name, even though the two tables are structurally similar --
nothing here is ever cloned, and reusing that name would be actively
misleading for anyone reading this schema without this module's
docstring in front of them.

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

**Rate limiting:** GitHub's REST API allows 5,000 authenticated requests an
hour per token, and 60 without authentication. GraphQL has a separate budget of
5,000 points an hour per token. A run costs about one REST request per
repository (its file list) plus a few GraphQL points per batch, so it stays
within both budgets. A run needs `GITHUB_TOKEN`.
The scan paces its requests below the hourly limit, and it retries on both the
hourly and the secondary (burst) limits. See `_is_rate_limited()` and
`_retry_wait_seconds()`.

python -m collection.rq5_agent_file_scan
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import posixpath
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import requests
import yaml

from . import paths
from .config import GITHUB_TOKEN
from .db import db_session
from .logging_utils import configure_logging, get_logger
from .parallel_utils import run_parallel_per_repo
from .rq1_prevalence_scan import (
    _notify,
    _write_progress,
    add_file_logging,
)

logger = get_logger(__name__)

RQ5_LANGUAGES: tuple[str, ...] = ("java", "javascript", "python", "typescript")

CATALOG_PATH = paths.ROOT_DIR / "collection" / "heuristics" / "rq5_agent_file_keywords.yaml"
# Guidance file names and excluded directories.
GUIDANCE_CATALOG_PATH = paths.ROOT_DIR / "collection" / "heuristics" / "rq5_agent_guidance_files.yaml"

# The Dataset A fixture CSVs (one per language). A repository's presence in
# any of them puts it in the RQ5 corpus.
DATASET_A_FIXTURES_DIR = paths.stage_dir("a", "fixtures")

DB_PATH = paths.DB_ROOT / "rq5_agent_files.db"
CSV_OUTPUT_DIR = paths.ROOT_DIR / "research-questions" / "rq5"
PROGRESS_PATH = paths.DB_ROOT / "rq5_agent_files_progress.json"
PROGRESS_LOG_EVERY = 50
LOG_PATH = paths.DB_ROOT / "rq5_agent_files.log"

# The snapshot date is a required run argument (--snapshot-date). It has no
# default because the new Dataset A collection has no build date yet.
SNAPSHOT_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# No disk/subprocess overhead per repo anymore (just a couple of small
# HTTP calls) -- higher than RQ1's clone-bound default is safe. Worker
# The worker count does not set the request rate. The rate limiter does (see
# TARGET_REQUESTS_PER_HOUR). The worker count only sets how many repositories
# wait for their turn.
DEFAULT_WORKERS = 20

GITHUB_API_BASE = "https://api.github.com"
API_TIMEOUT_SECONDS = 15
API_MAX_RETRIES = 3

# Rate limiting, in three parts:
# 1. `_RateLimiter` paces every request in `_api_get()` to
#    `TARGET_REQUESTS_PER_HOUR`. That target is a margin below 5,000, because
#    request timing jitters across threads. The primary limit is not reached
#    in normal operation.
# 2. `_retry_wait_seconds()` reads `X-RateLimit-Reset` when `Retry-After` is
#    missing. The hourly-quota 403 sends the reset time in that header.
# 3. A repository that still hits the limit gets the `rate_limited` error
#    reason (`RateLimitExhausted`). It can be retried later, and it is never
#    counted as a confirmed negative. (`RateLimitExhausted`) so any
#    repo that still hits this is cleanly identifiable and retryable
#    later, never silently mixed into a "confirmed negative" bucket.
TARGET_REQUESTS_PER_HOUR = 4000.0

NTFY_TOPIC = "joaofix_fixturedb"

REPO_TABLE_NAME = "repo_scan"
FILE_TABLE_NAME = "agent_files"
MATCH_TABLE_NAME = "agent_file_matches"
META_TABLE_NAME = "scan_meta"

# Where a guidance file is: at the repository root, or in a subdirectory.
LOCATION_ROOT = "root"
LOCATION_NESTED = "nested"
LOCATIONS: tuple[str, ...] = (LOCATION_ROOT, LOCATION_NESTED)

# Git's file mode for a symbolic link. REST returns it as a string, GraphQL as
# an integer.
SYMLINK_MODE = 0o120000
MAX_SYMLINK_HOPS = 5

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS {META_TABLE_NAME} (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS {REPO_TABLE_NAME} (
    repo_name           TEXT PRIMARY KEY,
    language            TEXT NOT NULL,
    fetch_ok            INTEGER NOT NULL DEFAULT 0,
    commit_sha          TEXT,
    commit_date         TEXT,
    num_guidance_files  INTEGER NOT NULL DEFAULT 0,
    num_root_files      INTEGER NOT NULL DEFAULT 0,
    tree_truncated      INTEGER NOT NULL DEFAULT 0,
    error_reason        TEXT,
    scanned_at          TEXT NOT NULL
);

-- One row per guidance file read. file_path is repository-relative; location
-- is root or nested. symlink_target is the real file read when file_path is a
-- symbolic link, else empty.
CREATE TABLE IF NOT EXISTS {FILE_TABLE_NAME} (
    repo_name                 TEXT NOT NULL,
    file_path                 TEXT NOT NULL,
    file_name                 TEXT NOT NULL,
    file_type                 TEXT NOT NULL,
    location                  TEXT NOT NULL,
    symlink_target            TEXT NOT NULL DEFAULT '',
    language                  TEXT NOT NULL,
    commit_sha                TEXT NOT NULL,
    has_test                  INTEGER NOT NULL DEFAULT 0,
    has_fixture                INTEGER NOT NULL DEFAULT 0,
    test_match_count          INTEGER NOT NULL DEFAULT 0,
    fixture_match_count       INTEGER NOT NULL DEFAULT 0,
    matched_test_keywords     TEXT NOT NULL DEFAULT '',
    matched_fixture_keywords  TEXT NOT NULL DEFAULT '',
    github_url                TEXT NOT NULL,
    PRIMARY KEY (repo_name, file_path)
);

CREATE TABLE IF NOT EXISTS {MATCH_TABLE_NAME} (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_name      TEXT NOT NULL,
    file_path      TEXT NOT NULL,
    location       TEXT NOT NULL,
    keyword_list   TEXT NOT NULL,
    keyword        TEXT NOT NULL,
    line_number    INTEGER NOT NULL,
    line_context   TEXT NOT NULL,
    line_before_2  TEXT NOT NULL DEFAULT '',
    line_before_1  TEXT NOT NULL DEFAULT '',
    line_after_1   TEXT NOT NULL DEFAULT '',
    line_after_2   TEXT NOT NULL DEFAULT '',
    in_code_block  INTEGER NOT NULL DEFAULT 0
);
"""

_FENCE_RE = re.compile(r"^(`{3,}|~{3,})")


def initialise_rq5_db(db_path: Path = DB_PATH) -> None:
    """Create the RQ5 tables if they don't exist yet. Safe to call every run --
    never drops or truncates existing rows. Raises on a database written by an
    earlier version of the scan (a different schema): start a new database."""
    with db_session(db_path) as conn:
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({FILE_TABLE_NAME})").fetchall()}
        if columns and "location" not in columns:
            raise ValueError(f"{db_path} was written by an earlier RQ5 scan; move it away and rescan")
        conn.executescript(SCHEMA)


def load_guidance_catalog(path: Path = GUIDANCE_CATALOG_PATH) -> tuple[list[str], list[str]]:
    """`(guidance_file_names, excluded_dir_names)` from the guidance file
    catalog. Raises on a name that is not a bare `.md` file name, on a
    duplicate (case-insensitive), or on an excluded directory that is a path."""
    with path.open("r", encoding="utf-8") as fh:
        catalog = yaml.safe_load(fh)
    names = list(catalog["guidance_files"])
    excluded = list(catalog["excluded_dirs"])
    for name in names:
        if "/" in name or not name.lower().endswith(".md"):
            raise ValueError(f"guidance file names must be bare .md names, got {name!r}")
    folded = [name.casefold() for name in names]
    duplicates = sorted({name for name in folded if folded.count(name) > 1})
    if duplicates:
        raise ValueError(f"duplicate guidance file names: {duplicates}")
    for directory in excluded:
        if "/" in directory or not directory:
            raise ValueError(f"excluded directories must be bare directory names, got {directory!r}")
    return names, excluded


def load_rq5_keyword_catalog(
    path: Path = CATALOG_PATH, guidance_path: Path = GUIDANCE_CATALOG_PATH
) -> dict[str, Any]:
    """Load the keyword catalog, plus `guidance_files` and `excluded_dirs` from
    the guidance file catalog. Kept as a plain,
    standalone loader (not wired into `collection/heuristics/__init__.py`'s
    loader machinery) -- that module's loaders feed the main agent/fixture
    *detection* pipeline; this catalog has an entirely different consumer
    and shape, and gains nothing from sharing that machinery."""
    with path.open("r", encoding="utf-8") as fh:
        catalog = yaml.safe_load(fh)
    catalog["guidance_files"], catalog["excluded_dirs"] = load_guidance_catalog(guidance_path)
    return catalog


def _build_keyword_pattern(keyword: str) -> re.Pattern:
    """Case-insensitive, word-boundary-respecting regex for one catalog
    keyword. A keyword containing a literal space (e.g. "test setup") is
    split on spaces and re-joined with an optional space-or-hyphen between
    each pair of words, so "test setup"/"test-setup"/"testsetup" all
    match the same catalog entry -- a single-token keyword (including a
    camelCase one like "beforeEach") is matched literally instead, since
    it isn't a "multi-word term" in the catalog's own representation.

    Use this tolerance carefully: it was dropped entirely for "before
    each"/"after each"/"before all"/"after all" (see the catalog's
    exclusions) because allowing the bare-space form made them
    collide with ordinary English ("before each commit", "after each
    fix") having nothing to do with the test lifecycle hooks they were
    meant to catch -- a multi-word catalog entry is only safe when the
    plain-English phrasing itself is already unlikely outside this
    context (e.g. "test setup" rarely means anything else).

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
    lines = [line.strip() for line in content.splitlines()]
    for index, stripped in enumerate(lines):
        current_in_fence = in_fence
        for keyword, pattern in patterns.items():
            for _ in pattern.finditer(lines[index]):
                matches.append(
                    {
                        "keyword": keyword,
                        "line_number": index + 1,
                        "line_context": stripped,
                        "line_before_2": _line_at(lines, index - 2),
                        "line_before_1": _line_at(lines, index - 1),
                        "line_after_1": _line_at(lines, index + 1),
                        "line_after_2": _line_at(lines, index + 2),
                        "in_code_block": current_in_fence,
                    }
                )
        if _FENCE_RE.match(stripped):
            in_fence = not in_fence
    return matches


def _line_at(lines: list[str], index: int) -> str:
    """The stripped line at `index`, or "" outside the file (used for the
    two-lines-either-side context of each match)."""
    return lines[index] if 0 <= index < len(lines) else ""


def scan_file_content(
    content: str,
    *,
    test_patterns: dict[str, re.Pattern],
    fixture_patterns: dict[str, re.Pattern],
) -> dict[str, list[dict[str, Any]]]:
    """Pure counting/matching logic for one already-fetched file's text --
    independent of the network, so it's directly unit-testable without a
    real API call."""
    return {
        "test_matches": find_keyword_matches(content, test_patterns),
        "fixture_matches": find_keyword_matches(content, fixture_patterns),
    }


class RateLimitExhausted(Exception):
    """Raised by `_api_get()` when every retry was consumed by a rate-
    limited response. Deliberately an exception, not a `None` return --
    `None` already means "genuinely not found" to every caller
    (`read_blob_via_api()`), and silently reusing that for
    "couldn't tell, GitHub throttled us" is exactly the bug class this
    module's rate-limiting fix exists to avoid (see
    `TARGET_REQUESTS_PER_HOUR`'s docstring). `process_repos_graphql()` catches
    this specifically and records a distinct `rate_limited` error_reason."""


class _RateLimiter:
    """Thread-safe, fixed-interval pacing limiter: blocks each caller just
    long enough that the long-run average call rate never exceeds
    `rate_per_second`, no matter how many worker threads call `acquire()`
    concurrently. Deliberately simple -- no burst allowance. A classic
    token bucket would let a burst of calls fire back-to-back after an
    idle period; bursts are exactly what risks tripping GitHub's
    secondary (abuse-detection) rate limit, a separate, less precisely
    documented limit from the primary hourly quota this targets. Every
    `acquire()` call reserves the next evenly-spaced slot instead.
    """

    def __init__(self, rate_per_second: float) -> None:
        self._interval = 1.0 / rate_per_second
        self._lock = threading.Lock()
        self._next_allowed_at = time.monotonic()

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            wait = self._next_allowed_at - now
            self._next_allowed_at = max(now, self._next_allowed_at) + self._interval
        if wait > 0:
            time.sleep(wait)


def _retry_wait_seconds(response: requests.Response, attempt: int) -> float:
    """How long to wait before retrying a rate-limited response.

    Prefers `Retry-After`, which the secondary limit sends. Falls back to
    `X-RateLimit-Reset`, a Unix timestamp, which the hourly-quota limit sends.
    Falls back to a short exponential backoff when neither header is usable.
    """
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return max(float(retry_after), 0.5)
        except ValueError:
            pass
    reset_at = response.headers.get("X-RateLimit-Reset")
    if reset_at:
        try:
            wait = float(reset_at) - time.time()
        except ValueError:
            wait = -1
        if wait > 0:
            return wait + 1  # small buffer past the exact reset instant
    return min(2**attempt, 30)


def _is_rate_limited(response: requests.Response | None) -> bool:
    """True for a 429, or a 403 that is GitHub's rate limiting rather than a
    genuine permission or not-found 403.

    The primary hourly limit sends a 403 with `X-RateLimit-Remaining: 0`. The
    secondary (abuse) limit sends no remaining-quota header, so it is detected
    by `Retry-After`. A 403 with neither is a real permission error. It is not
    retried, because retries would never succeed.
    """
    if response is None:
        return False
    if response.status_code == 429:
        return True
    if response.status_code != 403:
        return False
    if response.headers.get("X-RateLimit-Remaining") == "0":
        return True
    return response.headers.get("Retry-After") is not None


def _api_headers(token: str) -> dict[str, str]:
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"
    return headers


def _api_get(
    url: str,
    *,
    token: str,
    params: dict[str, Any] | None = None,
    timeout: int = API_TIMEOUT_SECONDS,
    max_retries: int = API_MAX_RETRIES,
    rate_limiter: _RateLimiter | None = None,
) -> requests.Response | None:
    """GET `url`, retrying with backoff on a rate-limited response. Both
    the *detection* (`_is_rate_limited()`, above) and the *wait duration*
    (`_retry_wait_seconds()`, above) are this module's own local
    functions -- see each one's docstring for why neither reuses
    `GitHubAgentFileChecker`'s equivalents as-is, even though that
    class's own callers still do.

    When `rate_limiter` is given, every attempt (including retries) calls
    its `acquire()` first, pacing this call -- and therefore every real
    caller sharing the same limiter instance -- to a safe target rate.
    `None` (the default) means unthrottled, which every test in this
    module relies on; only `run_scan()`'s real entrypoint passes a real
    one.

    Returns the raw `Response` for any outcome short of exhausted rate-
    limit retries or a network-level exception (including a 404 --
    callers decide what that means for their own endpoint). Raises
    `RateLimitExhausted` if every retry was consumed by a rate-limited
    response; returns `None` for a network-level exception (a different,
    not-necessarily-recoverable-by-retrying failure)."""
    headers = _api_headers(token)
    for attempt in range(max_retries + 1):
        if rate_limiter is not None:
            rate_limiter.acquire()
        try:
            response = requests.get(url, headers=headers, params=params, timeout=timeout)
        except requests.RequestException as exc:
            logger.debug("[RQ5 scan] request failed for %s: %s", url, exc)
            return None
        if _is_rate_limited(response):
            if attempt < max_retries:
                wait_seconds = _retry_wait_seconds(response, attempt)
                logger.warning(
                    "[RQ5 scan] rate limited fetching %s (attempt %d/%d); retrying in %.1fs",
                    url,
                    attempt + 1,
                    max_retries + 1,
                    wait_seconds,
                )
                time.sleep(wait_seconds)
                continue
            logger.warning("[RQ5 scan] rate limited fetching %s; exhausted retries", url)
            raise RateLimitExhausted(url)
        return response
    raise RateLimitExhausted(url)


def read_blob_via_api(
    repo_name: str, blob_sha: str, *, token: str = GITHUB_TOKEN, rate_limiter: _RateLimiter | None = None
) -> str | None:
    """Raw content of a blob, via GitHub's Git Blobs API. A blob's bytes
    are returned as-is regardless of what the file represents (a symbolic
    link's blob is its target path). Decoded permissively
    (`errors="replace"`) since a malformed/non-UTF-8 file must never
    crash the scan -- `None` only on a non-rate-limit fetch failure or an
    unexpected (non-base64) encoding, never a decoding exception. Raises
    `RateLimitExhausted` when GitHub keeps rate limiting the request."""
    url = f"{GITHUB_API_BASE}/repos/{repo_name}/git/blobs/{blob_sha}"
    response = _api_get(url, token=token, rate_limiter=rate_limiter)
    if response is None or response.status_code != 200:
        return None
    data = response.json()
    if data.get("encoding") != "base64":
        return None
    try:
        raw = base64.b64decode(data["content"])
    except Exception:
        return None
    return raw.decode("utf-8", errors="replace")


TREE_TIMEOUT_SECONDS = 60


def fetch_tree_via_api(
    repo_name: str,
    tree_sha: str,
    *,
    recursive: bool = True,
    token: str = GITHUB_TOKEN,
    rate_limiter: _RateLimiter | None = None,
) -> tuple[list[dict[str, Any]], bool] | None:
    """`(entries, truncated)` for the tree `tree_sha` (a commit or tree sha),
    through the Git Trees endpoint: every entry's `path` (relative to that
    tree), `type` (`blob`, `tree` or `commit` for a submodule), `mode` and
    `sha` -- at every depth when `recursive`, else the direct children only.
    `truncated` is GitHub's flag for a listing cut short. `None` when the
    request fails. Raises `RateLimitExhausted` when GitHub keeps rate limiting
    the request."""
    url = f"{GITHUB_API_BASE}/repos/{repo_name}/git/trees/{tree_sha}"
    response = _api_get(
        url,
        token=token,
        params={"recursive": "1"} if recursive else None,
        timeout=TREE_TIMEOUT_SECONDS,
        rate_limiter=rate_limiter,
    )
    if response is None or response.status_code != 200:
        return None
    try:
        data = response.json()
        entries = [
            {"path": e["path"], "type": e["type"], "mode": e.get("mode"), "sha": e["sha"]} for e in data["tree"]
        ]
    except (ValueError, KeyError, TypeError):
        return None
    return entries, bool(data.get("truncated"))


def _is_symlink(mode: Any) -> bool:
    try:
        return int(str(mode), 8) == SYMLINK_MODE if isinstance(mode, str) else int(mode) == SYMLINK_MODE
    except (TypeError, ValueError):
        return False


def is_excluded(path: str, excluded_dirs: set[str] | frozenset[str]) -> bool:
    """Whether any directory of `path` (not the file name itself) is excluded."""
    return any(part in excluded_dirs for part in path.split("/")[:-1])


TreeFetcher = Callable[[str, bool], "tuple[list[dict[str, Any]], bool] | None"]


def fetch_full_tree(
    tree_sha: str, fetch: TreeFetcher, excluded_dirs: set[str] | frozenset[str]
) -> tuple[list[dict[str, Any]], bool] | None:
    """`(entries, split)`: every entry of the tree `tree_sha`, at every depth,
    with paths relative to it. `fetch(sha, recursive)` is
    `fetch_tree_via_api()` for one repository.

    GitHub truncates a recursive listing of a very large tree. The tree is then
    split: its direct children are listed, and each child directory is fetched
    the same way (recursively, split again only if it is itself truncated).
    Excluded directories are not fetched. `split` says whether that happened.
    `None` when any request fails."""
    fetched = fetch(tree_sha, True)
    if fetched is None:
        return None
    entries, truncated = fetched
    if not truncated:
        return entries, False
    children = fetch(tree_sha, False)
    if children is None:
        return None
    result = list(children[0])
    for child in children[0]:
        if child["type"] != "tree" or child["path"] in excluded_dirs:
            continue
        sub = fetch_full_tree(child["sha"], fetch, excluded_dirs)
        if sub is None:
            return None
        result += [{**entry, "path": f"{child['path']}/{entry['path']}"} for entry in sub[0]]
    return result, True


def find_guidance_files(
    entries: list[dict[str, Any]], guidance_files: list[str], excluded_dirs: set[str] | frozenset[str]
) -> list[dict[str, Any]]:
    """The guidance files among `entries` (a whole tree, see
    `fetch_tree_via_api()`): blobs whose name matches a catalog name
    case-insensitively, at any depth, outside excluded directories. Each has
    `path` (as committed), `file_type` (the catalog spelling), `sha` and
    `symlink`. A directory named like a guidance file is not a file. Sorted by
    path."""
    canonical = {name.casefold(): name for name in guidance_files}
    found = []
    for entry in entries:
        if entry["type"] != "blob" or is_excluded(entry["path"], excluded_dirs):
            continue
        file_type = canonical.get(entry["path"].rsplit("/", 1)[-1].casefold())
        if file_type is not None:
            found.append(
                {"path": entry["path"], "file_type": file_type, "sha": entry["sha"], "symlink": _is_symlink(entry["mode"])}
            )
    return sorted(found, key=lambda f: f["path"])


def resolve_symlinks(
    files: list[dict[str, Any]],
    entries: list[dict[str, Any]],
    read_links: Callable[[list[str]], dict[str, str | None]],
) -> list[dict[str, Any]]:
    """The files to read for one repository's guidance `files` (see
    `find_guidance_files()`), each with `path`, `file_type`, `blob_sha` (the
    blob to read) and `symlink_target` (the real path read, empty for a regular
    file).

    A symbolic link is followed within the tree (`entries`), at most
    `MAX_SYMLINK_HOPS` links; `read_links` maps link blob shas to their text.
    Each real file is read once: a regular guidance file first, then links in
    path order, skipping a link whose target is already read. A link that
    leaves the repository, or points at a missing path, a directory or a link
    chain too long, is dropped."""
    by_path = {e["path"]: e for e in entries}
    to_read = [
        {"path": f["path"], "file_type": f["file_type"], "blob_sha": f["sha"], "symlink_target": ""}
        for f in files
        if not f["symlink"]
    ]
    read_paths = {f["path"] for f in to_read}
    pending = {f["path"]: (f["path"], f["sha"]) for f in files if f["symlink"]}
    resolved: dict[str, tuple[str, str] | None] = {}
    for _ in range(MAX_SYMLINK_HOPS):
        if not pending:
            break
        texts = read_links(sorted({sha for _, sha in pending.values()}))
        still_pending: dict[str, tuple[str, str]] = {}
        for link_path, (current, sha) in pending.items():
            text = (texts.get(sha) or "").strip()
            target = posixpath.normpath(posixpath.join(posixpath.dirname(current), text)) if text else ""
            entry = by_path.get(target) if text and not text.startswith("/") and not target.startswith("..") else None
            if entry is None or entry["type"] != "blob":
                resolved[link_path] = None
            elif _is_symlink(entry["mode"]):
                still_pending[link_path] = (target, entry["sha"])
            else:
                resolved[link_path] = (target, entry["sha"])
        pending = still_pending
    for link_path in pending:
        resolved[link_path] = None

    for f in files:
        if not f["symlink"]:
            continue
        outcome = resolved.get(f["path"])
        if outcome is None or outcome[0] in read_paths:
            continue
        target, sha = outcome
        read_paths.add(target)
        to_read.append({"path": f["path"], "file_type": f["file_type"], "blob_sha": sha, "symlink_target": target})
    return sorted(to_read, key=lambda f: f["path"])


def location_of(path: str) -> str:
    return LOCATION_ROOT if "/" not in path else LOCATION_NESTED


def _repo_row(
    repo_name: str,
    language: str,
    scanned_at: str,
    *,
    fetch_ok: bool,
    error_reason: str | None = None,
    commit_sha: str | None = None,
    commit_date: str | None = None,
    num_guidance_files: int = 0,
    num_root_files: int = 0,
    tree_truncated: bool = False,
) -> dict[str, Any]:
    return {
        "repo_name": repo_name,
        "language": language,
        "fetch_ok": 1 if fetch_ok else 0,
        "commit_sha": commit_sha,
        "commit_date": commit_date,
        "num_guidance_files": num_guidance_files,
        "num_root_files": num_root_files,
        "tree_truncated": 1 if tree_truncated else 0,
        "error_reason": error_reason,
        "scanned_at": scanned_at,
    }


def _scan_result(
    repo_row: dict[str, Any],
    files: list[dict[str, Any]] | None = None,
    matches: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {"repo": repo_row, "files": files or [], "matches": matches or []}


def _records_for_files(
    repo_name: str,
    language: str,
    commit_sha: str,
    to_scan: list[dict[str, str]],
    *,
    read_content: Callable[[str], str | None],
    test_patterns: dict[str, re.Pattern],
    fixture_patterns: dict[str, re.Pattern],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Scan each file of `to_scan` (see `resolve_symlinks()`) and return its
    `agent_files` rows and `agent_file_matches` rows. `read_content` maps a blob
    sha to the file's text, or `None` when it cannot be read; an unreadable file
    is skipped. Root and nested files are scanned with the same keywords and
    rules."""
    files: list[dict[str, Any]] = []
    matches: list[dict[str, Any]] = []
    for item in to_scan:
        content = read_content(item["blob_sha"])
        if content is None:
            logger.debug("[RQ5 scan] failed reading %s in %s", item["path"], repo_name)
            continue

        scanned = scan_file_content(content, test_patterns=test_patterns, fixture_patterns=fixture_patterns)
        test_matches = scanned["test_matches"]
        fixture_matches = scanned["fixture_matches"]
        location = location_of(item["path"])
        # A link's lines are linked at its target, where GitHub shows them.
        url_path = item["symlink_target"] or item["path"]
        files.append(
            {
                "repo_name": repo_name,
                "file_path": item["path"],
                "file_name": item["path"].rsplit("/", 1)[-1],
                "file_type": item["file_type"],
                "location": location,
                "symlink_target": item["symlink_target"],
                "language": language,
                "commit_sha": commit_sha,
                "has_test": bool(test_matches),
                "has_fixture": bool(fixture_matches),
                "test_match_count": len(test_matches),
                "fixture_match_count": len(fixture_matches),
                "matched_test_keywords": ",".join(sorted({m["keyword"] for m in test_matches})),
                "matched_fixture_keywords": ",".join(sorted({m["keyword"] for m in fixture_matches})),
                "github_url": f"https://github.com/{repo_name}/blob/{commit_sha}/{url_path}",
            }
        )
        for keyword_list, found in (("test", test_matches), ("fixture", fixture_matches)):
            for match in found:
                matches.append(
                    {
                        "repo_name": repo_name,
                        "file_path": item["path"],
                        "location": location,
                        "keyword_list": keyword_list,
                        **match,
                    }
                )
    return files, matches


# GraphQL batching. The cutoff commits and the file texts of a whole batch of
# repositories come in one GraphQL request each, which has its own point budget;
# only the recursive file list costs one REST request per repository.
GRAPHQL_URL = f"{GITHUB_API_BASE}/graphql"
GRAPHQL_BATCH_SIZE = 25
_BLOB_FIELDS = "text isBinary isTruncated"


class GraphQLError(Exception):
    """A GraphQL request failed in a way that retrying will not fix: a transport
    error, an unexpected HTTP status, or a body that is not JSON. Caught by
    `process_repos_graphql()`, which records the batch as `tree_fetch_failed`."""


def _split_repo_name(repo_name: str) -> tuple[str, str]:
    owner, sep, name = repo_name.partition("/")
    if not sep or not owner or not name:
        raise GraphQLError(f"not an owner/name repository: {repo_name!r}")
    return owner, name


def _graphql_rate_limited(payload: dict[str, Any]) -> bool:
    return any(error.get("type") == "RATE_LIMITED" for error in payload.get("errors") or [])


def _graphql_post(query: str, variables: dict[str, Any], *, token: str, rate_limiter: _RateLimiter | None) -> dict:
    """POST one GraphQL query, retrying on rate limiting with the same wait rule
    as `_api_get()`. Raises `RateLimitExhausted` when every retry is spent,
    `GraphQLError` on any other failure, and returns the parsed body otherwise."""
    headers = {"Accept": "application/vnd.github+json", "Authorization": f"bearer {token}"}
    body = {"query": query, "variables": variables}
    for attempt in range(API_MAX_RETRIES + 1):
        if rate_limiter is not None:
            rate_limiter.acquire()
        try:
            response = requests.post(GRAPHQL_URL, json=body, headers=headers, timeout=API_TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            raise GraphQLError(f"transport error: {exc}") from exc

        payload = None
        if response.status_code == 200:
            try:
                payload = response.json()
            except ValueError as exc:
                raise GraphQLError("GraphQL response is not JSON") from exc

        if _is_rate_limited(response) or (payload is not None and _graphql_rate_limited(payload)):
            if attempt < API_MAX_RETRIES:
                wait_seconds = _retry_wait_seconds(response, attempt)
                logger.warning(
                    "[RQ5 scan] GraphQL rate limited (attempt %d/%d); retrying in %.1fs",
                    attempt + 1,
                    API_MAX_RETRIES,
                    wait_seconds,
                )
                time.sleep(wait_seconds)
                continue
            raise RateLimitExhausted(GRAPHQL_URL)

        if payload is None:
            raise GraphQLError(f"GraphQL HTTP {response.status_code}")
        return payload
    raise RateLimitExhausted(GRAPHQL_URL)


def _cutoff_query(repos: list[dict], snapshot_date: str) -> str:
    """One aliased query: for each repository, the latest default-branch commit
    at or before the snapshot, with its root tree entries."""
    aliases = []
    for index, repo in enumerate(repos):
        owner, name = _split_repo_name(repo["repo_name"])
        aliases.append(
            f"r{index}: repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) {{"
            " defaultBranchRef { target { ... on Commit {"
            " history(first: 1, until: $until) { nodes { oid authoredDate"
            " tree { entries { name type mode oid } } } } } } } }"
        )
    return "query($until: GitTimestamp!) { " + " ".join(aliases) + " }"


def _blob_query(pairs: list[tuple[str, str]]) -> str:
    aliases = []
    for index, (repo_name, blob_sha) in enumerate(pairs):
        owner, name = _split_repo_name(repo_name)
        aliases.append(
            f"b{index}: repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) {{"
            f" object(oid: {json.dumps(blob_sha)}) {{ ... on Blob {{ {_BLOB_FIELDS} }} }} }}"
        )
    return "query { " + " ".join(aliases) + " }"


def _fetch_cutoffs(
    repos: list[dict], snapshot_date: str, *, token: str, rate_limiter: _RateLimiter | None
) -> dict[str, dict[str, Any]]:
    """Per repository: `{"sha", "date", "entries"}` for the cutoff commit, or
    `{"error_reason"}`. A repository with no commit at or before the snapshot
    (missing, empty, or with no such history) gets the same reason the REST
    path records for it."""
    payload = _graphql_post(
        _cutoff_query(repos, snapshot_date),
        {"until": f"{snapshot_date}T23:59:59Z"},
        token=token,
        rate_limiter=rate_limiter,
    )
    data = payload.get("data") or {}
    errors_by_alias: dict[str, set[str]] = {}
    for error in payload.get("errors") or []:
        path = error.get("path") or [""]
        errors_by_alias.setdefault(path[0], set()).add(error.get("type", ""))

    outcomes: dict[str, dict[str, Any]] = {}
    for index, repo in enumerate(repos):
        alias = f"r{index}"
        node = data.get(alias)
        if node is None:
            if "NOT_FOUND" in errors_by_alias.get(alias, set()):
                outcomes[repo["repo_name"]] = {"error_reason": "no_commit_at_or_before_cutoff"}
            else:
                outcomes[repo["repo_name"]] = {"error_reason": "tree_fetch_failed"}
            continue
        target = (node.get("defaultBranchRef") or {}).get("target") or {}
        commits = ((target.get("history") or {}).get("nodes")) or []
        if not commits:
            outcomes[repo["repo_name"]] = {"error_reason": "no_commit_at_or_before_cutoff"}
            continue
        commit = commits[0]
        outcomes[repo["repo_name"]] = {
            "sha": commit["oid"],
            "date": commit["authoredDate"][:10],
            "entries": [
                {"path": entry["name"], "type": entry["type"], "mode": entry.get("mode"), "sha": entry["oid"]}
                for entry in (commit["tree"] or {}).get("entries", [])
            ],
        }
    return outcomes


# Most aliases put in one GraphQL request when reading files, so a batch with
# many guidance files stays within GitHub's response-size and node limits.
GRAPHQL_MAX_ALIASES = 50


def _chunks(items: list, size: int) -> list[list]:
    return [items[start : start + size] for start in range(0, len(items), size)]


def _fetch_blobs(
    pairs: list[tuple[str, str]], *, token: str, rate_limiter: _RateLimiter | None
) -> dict[tuple[str, str], str | None]:
    """Text of each `(repo_name, blob_sha)`, or `None` when unreadable. Binary
    blobs are unreadable. A truncated text is re-read in full through the REST
    blob endpoint, so the scan never sees a partial file."""
    texts: dict[tuple[str, str], str | None] = {}
    for chunk in _chunks(list(dict.fromkeys(pairs)), GRAPHQL_MAX_ALIASES):
        payload = _graphql_post(_blob_query(chunk), {}, token=token, rate_limiter=rate_limiter)
        data = payload.get("data") or {}
        for index, pair in enumerate(chunk):
            obj = (data.get(f"b{index}") or {}).get("object") or {}
            if obj.get("isBinary"):
                texts[pair] = None
            elif obj.get("isTruncated"):
                texts[pair] = read_blob_via_api(pair[0], pair[1], token=token, rate_limiter=rate_limiter)
            else:
                texts[pair] = obj.get("text")
    return texts


def process_repos_graphql(
    repos: list[dict],
    *,
    snapshot_date: str,
    token: str = GITHUB_TOKEN,
    catalog: dict[str, Any] | None = None,
    rate_limiter: _RateLimiter | None = None,
) -> list[dict[str, Any]]:
    """Scan a batch of repositories. Per repository:

    1. the snapshot commit and its root tree (`_fetch_cutoffs()`, one GraphQL
       query for the batch);
    2. the full file list at that commit (`fetch_full_tree()`, REST): a
       listing GitHub truncated is split into one listing per subdirectory;
    3. the guidance files in it (`find_guidance_files()`), symbolic links
       followed (`resolve_symlinks()`), each real file read once;
    4. the keyword scan of each file.

    Returns one result per repository in `repos` (`_scan_result()`). Never
    raises: a rate-limited batch records every repository as `rate_limited`,
    any other batch failure records them as `tree_fetch_failed`, and so does a
    repository whose file list could not be fetched. Both reasons are
    retryable, and neither is recorded as a confirmed negative."""
    catalog = catalog or load_rq5_keyword_catalog()
    guidance_files = catalog["guidance_files"]
    excluded_dirs = frozenset(catalog["excluded_dirs"])
    test_patterns = _build_patterns(catalog["ardic_test_keywords"])
    fixture_patterns = _build_patterns(catalog["fixture_keywords"])
    scanned_at = datetime.now(timezone.utc).isoformat()

    def _fail(repo: dict, error_reason: str) -> dict[str, Any]:
        return _scan_result(
            _repo_row(repo["repo_name"], repo["language"], scanned_at, fetch_ok=False, error_reason=error_reason)
        )

    def _read_blobs(pairs: list[tuple[str, str]]) -> dict[tuple[str, str], str | None]:
        return _fetch_blobs(pairs, token=token, rate_limiter=rate_limiter)

    try:
        cutoffs = _fetch_cutoffs(repos, snapshot_date, token=token, rate_limiter=rate_limiter)
        commit_by_repo = {
            repo["repo_name"]: cutoffs[repo["repo_name"]]["sha"]
            for repo in repos
            if "sha" in cutoffs[repo["repo_name"]]
        }

        trees: dict[str, list[dict[str, Any]]] = {}
        truncated: set[str] = set()
        for name, commit_sha in commit_by_repo.items():
            fetched = fetch_full_tree(
                commit_sha,
                lambda sha, recursive, name=name: fetch_tree_via_api(
                    name, sha, recursive=recursive, token=token, rate_limiter=rate_limiter
                ),
                excluded_dirs,
            )
            if fetched is None:
                cutoffs[name] = {"error_reason": "tree_fetch_failed"}
                continue
            trees[name], split = fetched
            if split:
                truncated.add(name)

        to_read: dict[str, list[dict[str, Any]]] = {}
        for name, entries in trees.items():
            files = find_guidance_files(entries, guidance_files, excluded_dirs)
            to_read[name] = resolve_symlinks(
                files,
                entries,
                lambda shas, name=name: {sha: text for (_, sha), text in _read_blobs([(name, s) for s in shas]).items()},
            )
        texts = _read_blobs([(name, f["blob_sha"]) for name, files in to_read.items() for f in files])
    except RateLimitExhausted:
        return [_fail(repo, "rate_limited") for repo in repos]
    except GraphQLError as exc:
        logger.warning("[RQ5 scan] GraphQL batch of %d failed: %s", len(repos), exc)
        return [_fail(repo, "tree_fetch_failed") for repo in repos]

    results: list[dict[str, Any]] = []
    for repo in repos:
        repo_name = repo["repo_name"]
        outcome = cutoffs[repo_name]
        if "sha" not in outcome:
            results.append(_fail(repo, outcome["error_reason"]))
            continue
        files, matches = _records_for_files(
            repo_name,
            repo["language"],
            outcome["sha"],
            to_read[repo_name],
            read_content=lambda blob_sha, name=repo_name: texts.get((name, blob_sha)),
            test_patterns=test_patterns,
            fixture_patterns=fixture_patterns,
        )
        repo_row = _repo_row(
            repo_name,
            repo["language"],
            scanned_at,
            fetch_ok=True,
            commit_sha=outcome["sha"],
            commit_date=outcome["date"],
            num_guidance_files=len(files),
            num_root_files=sum(1 for f in files if f["location"] == LOCATION_ROOT),
            tree_truncated=repo_name in truncated,
        )
        results.append(_scan_result(repo_row, files, matches))
    return results


def load_corpus(fixtures_dir: Path = DATASET_A_FIXTURES_DIR) -> list[dict[str, str]]:
    """The RQ5 corpus: every repository with at least one fixture in Dataset
    A, read from `<fixtures_dir>/*_fixtures.csv`. Each entry has `repo_name`
    and `language` (the language of the fixture file the repo first appears
    in, in filename order). A repo that appears under two languages keeps
    the first and is logged once."""
    corpus: dict[str, dict[str, str]] = {}
    conflicts: set[str] = set()
    for path in sorted(fixtures_dir.glob("*_fixtures.csv")):
        with path.open("r", encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                repo_name, language = row["repo_name"], row["language"]
                existing = corpus.get(repo_name)
                if existing is None:
                    corpus[repo_name] = {"repo_name": repo_name, "language": language}
                elif existing["language"] != language:
                    conflicts.add(repo_name)
    for repo_name in sorted(conflicts):
        logger.warning(
            "[RQ5 corpus] %s has fixtures in more than one language; keeping %s",
            repo_name,
            corpus[repo_name]["language"],
        )
    return list(corpus.values())


def validated_snapshot_date(value: str | None) -> str:
    """`value` as a YYYY-MM-DD string that is a real calendar date. Raises
    `ValueError` for a missing or malformed date -- there is deliberately no
    default."""
    if not value or not SNAPSHOT_DATE_PATTERN.match(value):
        raise ValueError(f"snapshot date must be YYYY-MM-DD, got {value!r}")
    datetime.strptime(value, "%Y-%m-%d")
    return value


def record_scan_meta(snapshot_date: str, db_path: Path = DB_PATH) -> None:
    """Store the run's snapshot date in `scan_meta`.
    Raises if the database already holds a different snapshot date, so a
    resumed run can never mix repositories scanned at two dates."""
    with db_session(db_path) as conn:
        row = conn.execute(f"SELECT value FROM {META_TABLE_NAME} WHERE key = 'snapshot_date'").fetchone()
        if row is not None and row[0] != snapshot_date:
            raise ValueError(
                f"{db_path.name} was scanned at snapshot {row[0]}; refusing to continue at {snapshot_date}"
            )
        conn.execute(
            f"INSERT OR REPLACE INTO {META_TABLE_NAME} (key, value) VALUES ('snapshot_date', ?)",
            (snapshot_date,),
        )


def load_scan_meta(db_path: Path = DB_PATH) -> dict[str, str]:
    """The `scan_meta` key/value pairs, or {} if the database does not exist."""
    if not db_path.exists():
        return {}
    with db_session(db_path) as conn:
        return dict(conn.execute(f"SELECT key, value FROM {META_TABLE_NAME}").fetchall())


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
    """Upsert one repo's `repo_scan` row, and fully replace its file and match
    rows (delete-then-insert) -- so re-processing the same repo (a
    retried run, or a deliberate single-repo re-scan) never duplicates or leaves
    stale rows behind."""
    repo_row = result["repo"]
    repo_name = repo_row["repo_name"]

    with db_session(db_path) as conn:
        conn.execute(
            f"""
            INSERT INTO {REPO_TABLE_NAME}
                (repo_name, language, fetch_ok, commit_sha, commit_date,
                 num_guidance_files, num_root_files, tree_truncated, error_reason, scanned_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(repo_name) DO UPDATE SET
                language=excluded.language,
                fetch_ok=excluded.fetch_ok,
                commit_sha=excluded.commit_sha,
                commit_date=excluded.commit_date,
                num_guidance_files=excluded.num_guidance_files,
                num_root_files=excluded.num_root_files,
                tree_truncated=excluded.tree_truncated,
                error_reason=excluded.error_reason,
                scanned_at=excluded.scanned_at
            """,
            (
                repo_name,
                repo_row["language"],
                repo_row["fetch_ok"],
                repo_row["commit_sha"],
                repo_row["commit_date"],
                repo_row["num_guidance_files"],
                repo_row["num_root_files"],
                repo_row["tree_truncated"],
                repo_row["error_reason"],
                repo_row["scanned_at"],
            ),
        )
        for table in (FILE_TABLE_NAME, MATCH_TABLE_NAME):
            conn.execute(f"DELETE FROM {table} WHERE repo_name = ?", (repo_name,))

        conn.executemany(
            f"""
            INSERT INTO {FILE_TABLE_NAME}
                (repo_name, file_path, file_name, file_type, location, symlink_target,
                 language, commit_sha, has_test, has_fixture, test_match_count,
                 fixture_match_count, matched_test_keywords, matched_fixture_keywords, github_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    f["repo_name"],
                    f["file_path"],
                    f["file_name"],
                    f["file_type"],
                    f["location"],
                    f["symlink_target"],
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
                for f in result["files"]
            ],
        )
        conn.executemany(
            f"""
            INSERT INTO {MATCH_TABLE_NAME}
                (repo_name, file_path, location, keyword_list, keyword, line_number,
                 line_context, line_before_2, line_before_1, line_after_1,
                 line_after_2, in_code_block)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    m["repo_name"],
                    m["file_path"],
                    m["location"],
                    m["keyword_list"],
                    m["keyword"],
                    m["line_number"],
                    m["line_context"],
                    m["line_before_2"],
                    m["line_before_1"],
                    m["line_after_1"],
                    m["line_after_2"],
                    1 if m["in_code_block"] else 0,
                )
                for m in result["matches"]
            ],
        )


REPO_CSV_FIELDNAMES: tuple[str, ...] = (
    "repository",
    "commit_sha",
    "num_guidance_files",
    "guidance_files",
    "has_root_file",
    "has_test",
    "has_fixture",
    "has_fixture_root",
    "has_fixture_nested",
    "matched_fixture_terms",
)
FIXTURE_MATCHES_FIELDNAMES: tuple[str, ...] = (
    "repository",
    "file_path",
    "location",
    "line_number",
    "matched_term",
    "line_before_2",
    "line_before_1",
    "matched_line",
    "line_after_1",
    "line_after_2",
    "in_code_block",
)
SKIPPED_CSV_FIELDNAMES: tuple[str, ...] = ("repository", "language", "error_reason")
FIXTURE_MATCHES_CSV_NAME = "rq5_fixture_matches.csv"
REPOSITORY_SHEET_NAME = "rq5_repository_coding_sheet.csv"
SNIPPETS_MARKDOWN_NAME = "rq5_snippets.md"
REPOSITORY_CODING_COLUMNS: tuple[str, ...] = (
    "decision",
    "notes",
)
REPOSITORY_SHEET_FIELDNAMES: tuple[str, ...] = (
    "repository",
    "primary_language",
    "fixture_match_count",
    "fixture_location",
    *REPOSITORY_CODING_COLUMNS,
)
DECISION_VALUES: tuple[str, ...] = ("yes", "no", "unsure")
# Reading order of a repository's snippets in the repository-level sheet.
# Only an order, not a classification.
SNIPPET_TERM_ORDER: tuple[str, ...] = (
    "conftest",
    "beforeEach",
    "afterEach",
    "beforeAll",
    "afterAll",
    "test setup",
    "setup and teardown",
    "fixture",
    "fixtures",
)


def load_repo_guidance(db_path: Path = DB_PATH) -> list[dict[str, Any]]:
    """One record per analyzed repository (`fetch_ok=1`). Repository is the unit
    every RQ5 statistic counts.

    `guidance_files` lists the repository's guidance files (any depth) and
    `root_files` those at the root; a repository with none is included with
    every flag False. `has_test`, `has_fixture` and the matched terms fold,
    with logical OR, all of its guidance files; `has_fixture_root` and
    `has_fixture_nested` are per location."""
    with db_session(db_path) as conn:
        repos = conn.execute(
            f"SELECT repo_name, language, commit_sha FROM {REPO_TABLE_NAME} "
            "WHERE fetch_ok = 1 ORDER BY repo_name"
        ).fetchall()
        files = conn.execute(
            f"SELECT repo_name, file_path, location, has_test, has_fixture, matched_test_keywords, "
            f"matched_fixture_keywords FROM {FILE_TABLE_NAME} ORDER BY repo_name, file_path"
        ).fetchall()

    by_repo: dict[str, dict[str, Any]] = {
        repo_name: {
            "repository": repo_name,
            "language": language,
            "commit_sha": commit_sha,
            "guidance_files": [],
            "root_files": [],
            "has_test": False,
            "has_fixture": False,
            "has_fixture_root": False,
            "has_fixture_nested": False,
            "fixture_terms": set(),
            "test_terms": set(),
        }
        for repo_name, language, commit_sha in repos
    }
    for repo_name, file_path, location, has_test, has_fixture, test_terms, fixture_terms in files:
        record = by_repo.get(repo_name)
        if record is None:
            continue
        record["guidance_files"].append(file_path)
        if location == LOCATION_ROOT:
            record["root_files"].append(file_path)
        record[f"has_fixture_{location}"] = record[f"has_fixture_{location}"] or bool(has_fixture)
        record["has_test"] = record["has_test"] or bool(has_test)
        record["has_fixture"] = record["has_fixture"] or bool(has_fixture)
        record["test_terms"] |= {t for t in test_terms.split(",") if t}
        record["fixture_terms"] |= {t for t in fixture_terms.split(",") if t}
    return list(by_repo.values())


def load_fixture_match_rows(db_path: Path = DB_PATH) -> list[dict[str, Any]]:
    """Every fixture-keyword match, in the row order of
    `rq5_fixture_matches.csv`: by repository, root files before nested
    files, then path, line and term. A match's row id is its 1-based position
    in this list (the sheet's Nth data row)."""
    with db_session(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT repo_name, file_path, location, line_number, keyword, line_before_2,
                   line_before_1, line_context, line_after_1, line_after_2, in_code_block
            FROM {MATCH_TABLE_NAME}
            WHERE keyword_list = 'fixture'
            ORDER BY repo_name, CASE location WHEN '{LOCATION_ROOT}' THEN 0 ELSE 1 END,
                     file_path, line_number, keyword
            """
        ).fetchall()
    keys = (
        "repo_name", "file_path", "location", "line_number", "keyword", "line_before_2",
        "line_before_1", "line_context", "line_after_1", "line_after_2", "in_code_block",
    )
    return [dict(zip(keys, row, strict=True)) for row in rows]


def _fixture_location(locations: set[str]) -> str:
    """`root`, `nested` or `root+nested` for a repository's fixture matches."""
    return "+".join(location for location in LOCATIONS if location in locations)


def _has_manual_coding(path: Path) -> bool:
    if not path.exists():
        return False
    with path.open("r", encoding="utf-8", newline="") as fh:
        return any(
            (row.get(column) or "").strip()
            for row in csv.DictReader(fh)
            for column in REPOSITORY_CODING_COLUMNS
        )


def write_repository_coding_sheet(
    match_rows: list[dict[str, Any]],
    db_path: Path = DB_PATH,
    output_dir: Path = CSV_OUTPUT_DIR,
) -> Path:
    """Write `rq5_repository_coding_sheet.csv`: one row per repository with at
    least one fixture match in its guidance files, in the order of the sections
    of `rq5_snippets.md` (where the matches are read). `fixture_location` says
    where its matches are (`root`, `nested` or `root+nested`). The
    coding columns are empty. The matched lines are deliberately not in the
    sheet: a repository can have more text than a spreadsheet cell holds
    (32,767 characters in Excel).

    Raises rather than overwrite a sheet that already holds manual coding."""
    path = output_dir / REPOSITORY_SHEET_NAME
    if _has_manual_coding(path):
        raise ValueError(f"{path} already holds manual coding; refusing to overwrite it")

    with db_session(db_path) as conn:
        languages = dict(conn.execute(f"SELECT repo_name, language FROM {REPO_TABLE_NAME}").fetchall())

    by_repo: dict[str, list[dict[str, Any]]] = {}
    for row in match_rows:
        by_repo.setdefault(row["repo_name"], []).append(row)

    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=REPOSITORY_SHEET_FIELDNAMES)
        writer.writeheader()
        for repo_name in sorted(by_repo):
            matches = by_repo[repo_name]
            writer.writerow(
                {
                    "repository": repo_name,
                    "primary_language": languages.get(repo_name, ""),
                    "fixture_match_count": len(matches),
                    "fixture_location": _fixture_location({m["location"] for m in matches}),
                    **dict.fromkeys(REPOSITORY_CODING_COLUMNS, ""),
                }
            )
    return path


def _fence(lines: list[str]) -> str:
    """A backtick fence longer than any backtick run inside `lines`."""
    longest = max((len(run) for line in lines for run in re.findall(r"`+", line)), default=0)
    return "`" * max(3, longest + 1)


def write_snippets_markdown(
    match_rows: list[dict[str, Any]],
    db_path: Path = DB_PATH,
    output_dir: Path = CSV_OUTPUT_DIR,
) -> Path:
    """Write `rq5_snippets.md`, a read-only view of the repository coding sheet:
    one numbered section per repository, in the sheet's row order, listing
    every matched line with its row id(s), its location (root or nested file),
    a GitHub link to that line at the scanned commit, and two lines of context
    on each side. A line matching several terms is shown once, with every row
    id. Lines follow `SNIPPET_TERM_ORDER` (by the line's first term), then
    location (root first), path and line."""
    with db_session(db_path) as conn:
        languages = dict(conn.execute(f"SELECT repo_name, language FROM {REPO_TABLE_NAME}").fetchall())
        urls = {
            (repo_name, file_path): url
            for repo_name, file_path, url in conn.execute(
                f"SELECT repo_name, file_path, github_url FROM {FILE_TABLE_NAME}"
            ).fetchall()
        }

    term_rank = {term: rank for rank, term in enumerate(SNIPPET_TERM_ORDER)}
    location_rank = {location: rank for rank, location in enumerate(LOCATIONS)}
    by_repo: dict[str, dict[tuple[str, int], dict[str, Any]]] = {}
    for row_id, row in enumerate(match_rows, start=1):
        line = by_repo.setdefault(row["repo_name"], {}).setdefault(
            (row["file_path"], row["line_number"]),
            {
                "ids": [],
                "terms": [],
                "location": row["location"],
                "context": (
                    row["line_before_2"],
                    row["line_before_1"],
                    row["line_context"],
                    row["line_after_1"],
                    row["line_after_2"],
                ),
                "in_code_block": bool(row["in_code_block"]),
            },
        )
        line["ids"].append(row_id)
        line["terms"].append(row["keyword"])

    parts = [
        "# RQ5 fixture snippets",
        "",
        f"Read-only companion to `{REPOSITORY_SHEET_NAME}`: code in the CSV, read here.",
        "Repository N below is data row N of the sheet (spreadsheet row N+1).",
        "Row ids are the data rows of `rq5_fixture_matches.csv`. Each line says",
        "whether it comes from a guidance file at the root or in a subdirectory",
        "(nested). `>` marks the matched line.",
        "",
    ]
    for number, repo_name in enumerate(sorted(by_repo), start=1):
        lines = sorted(
            by_repo[repo_name].items(),
            key=lambda item: (
                min(term_rank.get(t, len(term_rank)) for t in item[1]["terms"]),
                location_rank[item[1]["location"]],
                item[0][0],
                item[0][1],
            ),
        )
        match_count = sum(len(line["ids"]) for _, line in lines)
        locations = _fixture_location({line["location"] for _, line in lines})
        parts += [
            f"## {number}. {repo_name}",
            "",
            f"{languages.get(repo_name, '')} · {match_count} fixture "
            f"{'match' if match_count == 1 else 'matches'} · {locations}",
            "",
        ]
        for (file_path, line_number), line in lines:
            ids = ", ".join(str(i) for i in line["ids"])
            terms = ", ".join(sorted(set(line["terms"]), key=lambda t: term_rank.get(t, len(term_rank))))
            location = f"{file_path}:{line_number}"
            url = urls.get((repo_name, file_path))
            link = f"[{location}]({url}#L{line_number})" if url else location
            block = " · in a fenced code block" if line["in_code_block"] else ""
            before_2, before_1, matched, after_1, after_2 = line["context"]
            body = [f"  {before_2}", f"  {before_1}", f"> {matched}", f"  {after_1}", f"  {after_2}"]
            fence = _fence(body)
            parts += [
                f"**[{ids}]** {terms} · {line['location']} · {link}{block}",
                "",
                f"{fence}text",
                *body,
                fence,
                "",
            ]

    path = output_dir / SNIPPETS_MARKDOWN_NAME
    path.write_text("\n".join(parts), encoding="utf-8")
    return path


def write_rq5_readme(output_dir: Path = CSV_OUTPUT_DIR) -> Path:
    """Write `README.md` for the review outputs, including the allowed values
    of the repository-level coding columns."""
    text = f"""# RQ5 review outputs

Written by `python -m collection.rq5_agent_file_scan`. Manual coding is done
in `{REPOSITORY_SHEET_NAME}`; `python -m collection.research_questions.rq5_coding`
reads it once every row is coded.

Files searched: every guidance file of each repository, a file named
{", ".join(load_guidance_catalog()[0])} (case-insensitive) at the root or in any
subdirectory, outside dependency, build and cache directories. References
between files are not followed. Both lists are in
`collection/heuristics/rq5_agent_guidance_files.yaml`.

## Files

- `rq5_repositories.csv`: one row per analyzed repository, with its guidance
  files and whether the fixture match is in root or nested files.
- `rq5_fixture_matches.csv`: one row per fixture-keyword match, with the file
  path, its location (`root` or `nested`) and two lines of context on each side.
  Not coded: it is the lookup for a snippet's context. A match's **row id** is
  its 1-based position among the data rows (row id N is spreadsheet row N+1,
  below the header).
- `{REPOSITORY_SHEET_NAME}`: the coding sheet, one row per repository with at
  least one fixture match. `fixture_location` says whether the matches are in
  root files, nested files or both. The matched lines are not in the sheet;
  read them in `{SNIPPETS_MARKDOWN_NAME}`.
- `{SNIPPETS_MARKDOWN_NAME}`: the matched lines, for reading while coding.
  Repository N is data row N of the sheet; each matched line has its row id(s)
  in `rq5_fixture_matches.csv`, its location, a GitHub link and two lines of
  context on each side, ordered by term ({", ".join(SNIPPET_TERM_ORDER)}), then
  location, path and line. The order is only a reading order, not a
  classification.
- `rq5_skipped_repositories.csv`: repositories that could not be analyzed.

A new scan keeps the coding already in the sheet: see `carry_over_coding()` in
`collection/rq5_agent_file_scan.py`.

## Coding columns of `{REPOSITORY_SHEET_NAME}`

- `decision`: {" / ".join(f"`{v}`" for v in DECISION_VALUES)}. One verdict per
  repository, over all of its guidance files.
  - `yes`: at least one match is about test fixtures: fixture code
    (pytest fixtures, `conftest.py`, `beforeEach`/`afterEach`, setUp/tearDown,
    ...) or fixtures used by tests (fixture files, test data). It may be
    inferred from the terms near the match instead of stated explicitly; do
    not be pedantic. Description counts as guidance: in an agent configuration
    file, a statement about how fixtures are done is an instruction to the
    agent. One such match is enough.
  - `no`: no match is about testing, e.g. a product or domain term named
    "fixture", a contract, a changelog entry, or a link to a setup document.
  - `unsure`: a match might be about test fixtures but its surrounding lines
    do not settle it.

  Decide from the matched lines and the lines around them only, as an average
  developer reading many unfamiliar projects: do not look elsewhere in the
  repository, and do not rely on specialist knowledge of the project, its
  language or its frameworks.
- `notes`: free text.

## Category coding

The fixture guidance of the repositories coded `yes` is categorized on a random
sample, with this study's own categories: see `rq5_category_sample.csv`,
`rq5_category_codebook.yaml` and `rq5_agreement_sheet.csv`, written by
`python -m collection.rq5_category_sample`. The instructions are in
`CATEGORY_CODING.md`.
"""
    path = output_dir / "README.md"
    path.write_text(text, encoding="utf-8")
    return path


CODING_BACKUP_DIR = paths.DB_ROOT


def write_review_outputs(
    db_path: Path = DB_PATH,
    output_dir: Path = CSV_OUTPUT_DIR,
    backup_dir: Path = CODING_BACKUP_DIR,
) -> dict[str, Path]:
    """Write the RQ5 review outputs into `output_dir`:

    - `rq5_repositories.csv`: one row per analyzed repository (commit SHA,
      guidance files, the test/fixture flags, matched fixture terms).
    - `rq5_fixture_matches.csv`: one row per fixture-keyword match, with path,
      location and two lines of context on each side. Not coded; the lookup for
      row ids.
    - `rq5_repository_coding_sheet.csv`: one row per repository with a
      fixture match, see `write_repository_coding_sheet()`.
    - `rq5_snippets.md`: a read-only view of the repository sheet, see
      `write_snippets_markdown()`.
    - `rq5_skipped_repositories.csv`: every repository that could not be
      analyzed, with the reason.
    - `README.md`: the files and the allowed manual-coding values.

    When the sheet in `output_dir` already holds coding, it and its
    `rq5_fixture_matches.csv` are first copied into `backup_dir`, and the
    coding is carried over into the new sheet (`carry_over_coding()`). The
    outcome per repository is written next to the backup.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    sheet_path = output_dir / REPOSITORY_SHEET_NAME
    matches_path = output_dir / FIXTURE_MATCHES_CSV_NAME
    backup = _back_up_coding(sheet_path, matches_path, backup_dir) if _has_manual_coding(sheet_path) else None
    if backup is not None:
        sheet_path.unlink()

    repo_path = output_dir / "rq5_repositories.csv"
    with repo_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(REPO_CSV_FIELDNAMES)
        for record in load_repo_guidance(db_path):
            writer.writerow(
                [
                    record["repository"],
                    record["commit_sha"],
                    len(record["guidance_files"]),
                    ";".join(record["guidance_files"]),
                    int(bool(record["root_files"])),
                    int(record["has_test"]),
                    int(record["has_fixture"]),
                    int(record["has_fixture_root"]),
                    int(record["has_fixture_nested"]),
                    ",".join(sorted(record["fixture_terms"])),
                ]
            )
    written["repositories"] = repo_path

    match_rows = load_fixture_match_rows(db_path)
    with matches_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(FIXTURE_MATCHES_FIELDNAMES)
        for row in match_rows:
            writer.writerow(
                [
                    row["repo_name"],
                    row["file_path"],
                    row["location"],
                    row["line_number"],
                    row["keyword"],
                    row["line_before_2"],
                    row["line_before_1"],
                    row["line_context"],
                    row["line_after_1"],
                    row["line_after_2"],
                    bool(row["in_code_block"]),
                ]
            )
    written["fixture_matches"] = matches_path
    written["snippets"] = write_snippets_markdown(match_rows, db_path, output_dir)
    written["repository_sheet"] = write_repository_coding_sheet(match_rows, db_path, output_dir)
    if backup is not None:
        old_sheet, old_matches = backup
        outcome = carry_over_coding(old_sheet, sheet_path, old_matches=old_matches, new_matches=matches_path)
        written["carry_over"] = _write_carry_over_report(old_sheet, outcome)
    written["readme"] = write_rq5_readme(output_dir)

    with db_session(db_path) as conn:
        skipped_rows = conn.execute(
            f"SELECT repo_name, language, error_reason FROM {REPO_TABLE_NAME} "
            "WHERE fetch_ok = 0 ORDER BY repo_name"
        ).fetchall()
    skipped_path = output_dir / "rq5_skipped_repositories.csv"
    with skipped_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(SKIPPED_CSV_FIELDNAMES)
        writer.writerows(skipped_rows)
    written["skipped"] = skipped_path
    return written


def _back_up_coding(sheet_path: Path, matches_path: Path, backup_dir: Path) -> tuple[Path, Path]:
    """Copy the coded sheet and its match CSV into `backup_dir`, under
    timestamped names, and return the two copies."""
    if not matches_path.exists():
        raise ValueError(f"{sheet_path} holds coding but {matches_path} is missing; cannot carry the coding over")
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    old_sheet = backup_dir / f"rq5_coding_sheet_backup_{stamp}.csv"
    old_matches = backup_dir / f"rq5_fixture_matches_backup_{stamp}.csv"
    old_sheet.write_bytes(sheet_path.read_bytes())
    old_matches.write_bytes(matches_path.read_bytes())
    return old_sheet, old_matches


def _write_carry_over_report(old_sheet: Path, outcome: dict[str, list[str]]) -> Path:
    """`<backup>_carry_over.csv`: each coded repository of the old sheet with
    its outcome (`unchanged`, `matches_changed` or `removed`) and its old
    decision and notes."""
    with old_sheet.open("r", encoding="utf-8", newline="") as fh:
        old_rows = {row["repository"]: row for row in csv.DictReader(fh)}
    path = old_sheet.with_name(old_sheet.stem + "_carry_over.csv")
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(("repository", "outcome", *REPOSITORY_CODING_COLUMNS))
        for key, repos in outcome.items():
            for repo in repos:
                writer.writerow((repo, key, *(old_rows[repo].get(c, "") for c in REPOSITORY_CODING_COLUMNS)))
    return path


def fixture_match_keys(matches_csv: Path) -> dict[str, set[tuple[str, str, str, str]]]:
    """Per repository, `(term, path, line, text)` for each fixture match in a
    `rq5_fixture_matches.csv`, ignoring row ids (which renumber between scans)
    and the location label. A file written before file paths were recorded
    has `file_name` in place of `file_path`."""
    keys: dict[str, set[tuple[str, str, str, str]]] = {}
    with matches_csv.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            path = row.get("file_path") or row.get("file_name") or ""
            keys.setdefault(row["repository"], set()).add(
                (row["matched_term"], path, row["line_number"], row["matched_line"])
            )
    return keys


def carry_over_coding(
    old_sheet: Path, new_sheet: Path, *, old_matches: Path, new_matches: Path
) -> dict[str, list[str]]:
    """Copy manual coding from `old_sheet` into the freshly written `new_sheet`.

    A repository coded in `old_sheet` and still in `new_sheet` keeps its
    decision and notes exactly as they were, whether or not its
    fixture matches changed. A repository coded before but absent from
    `new_sheet` (it no longer has a fixture match) is dropped. A repository new
    to `new_sheet` stays uncoded.

    `old_matches` and `new_matches` (the `rq5_fixture_matches.csv` written with
    each sheet) only label the outcome: `unchanged` (same matches, ignoring row
    ids), `matches_changed`, or `removed`. Raises if `new_sheet` already holds
    coding."""
    with old_sheet.open("r", encoding="utf-8", newline="") as fh:
        old_rows = {
            row["repository"]: row
            for row in csv.DictReader(fh)
            if any((row.get(column) or "").strip() for column in REPOSITORY_CODING_COLUMNS)
        }
    with new_sheet.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = list(reader.fieldnames or [])
        new_rows = list(reader)
    if any((row.get(column) or "").strip() for row in new_rows for column in REPOSITORY_CODING_COLUMNS):
        raise ValueError(f"{new_sheet} already holds coding")
    old_keys, new_keys = fixture_match_keys(old_matches), fixture_match_keys(new_matches)

    outcome: dict[str, list[str]] = {"unchanged": [], "matches_changed": [], "removed": []}
    present = {row["repository"] for row in new_rows}
    outcome["removed"] = sorted(repo for repo in old_rows if repo not in present)
    for row in new_rows:
        old = old_rows.get(row["repository"])
        if old is None:
            continue
        row.update({column: old.get(column, "") for column in REPOSITORY_CODING_COLUMNS})
        same = old_keys.get(row["repository"], set()) == new_keys.get(row["repository"], set())
        outcome["unchanged" if same else "matches_changed"].append(row["repository"])

    with new_sheet.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(new_rows)
    return outcome


def run_scan(
    corpus: list[dict[str, str]] | None = None,
    fixtures_dir: Path = DATASET_A_FIXTURES_DIR,
    db_path: Path = DB_PATH,
    progress_path: Path = PROGRESS_PATH,
    workers: int = DEFAULT_WORKERS,
    snapshot_date: str | None = None,
    log_every: int = PROGRESS_LOG_EVERY,
    notify: bool = True,
    token: str = GITHUB_TOKEN,
    catalog_path: Path = CATALOG_PATH,
    target_requests_per_hour: float | None = TARGET_REQUESTS_PER_HOUR,
    batch_size: int = GRAPHQL_BATCH_SIZE,
) -> dict[str, int]:
    """Scan every not-yet-scanned repo in the corpus (`corpus`, or
    `load_corpus(fixtures_dir)` when omitted) at `snapshot_date`, persisting
    each result immediately. Resumable by construction (`db_path`'s own rows
    are the checkpoint -- see `load_scanned_repo_names()`). Logs a progress
    line and refreshes `progress_path` every `log_every` completions, and
    (when `notify`) pushes one ntfy.sh notification per `RQ5_LANGUAGES`
    chunk finished plus one final push -- same operational shape as
    `rq1_prevalence_scan.run_scan()`, for the same reasons (this is an
    equally long, equally unattended run over the same ~24.7k repos, even
    though each individual repo is now far cheaper).

    The catalog is loaded once here (not once per repo) and threaded
    through every `process_repos_graphql()` call, so a run's repos are all measured
    against the exact same keyword/target-file set even if the catalog
    file is hand-edited between runs.

    `target_requests_per_hour` builds one `_RateLimiter` shared by every
    worker thread for the whole run (see that class's and
    `TARGET_REQUESTS_PER_HOUR`'s docstrings) -- `None` or `0` disables
    throttling entirely (every test in this module that calls `run_scan()`
    mocks the GitHub calls out, so this never actually matters for them;
    it matters for a real run, where the default keeps the whole run
    safely under GitHub's primary rate limit regardless of `workers`).
    """
    snapshot_date = validated_snapshot_date(snapshot_date)
    initialise_rq5_db(db_path)
    catalog = load_rq5_keyword_catalog(catalog_path)
    record_scan_meta(snapshot_date, db_path)
    rate_limiter = _RateLimiter(target_requests_per_hour / 3600) if target_requests_per_hour else None
    universe = corpus if corpus is not None else load_corpus(fixtures_dir)
    already_done = load_scanned_repo_names(db_path)
    pending = [r for r in universe if r["repo_name"] not in already_done]

    logger.info(
        "[RQ5 scan] %d repos total, %d already scanned, %d pending",
        len(universe),
        len(already_done),
        len(pending),
    )

    started_at = datetime.now(timezone.utc)
    counters = {"completed": 0, "fetch_ok": 0, "fetch_failed": 0, "agent_files_found": 0}

    def _compute(batch: list[dict]) -> list[dict]:
        return process_repos_graphql(
            batch,
            snapshot_date=snapshot_date,
            token=token,
            catalog=catalog,
            rate_limiter=rate_limiter,
        )

    def _persist_batch(results: list[dict]) -> None:
        for result in results:
            _persist(result)

    def _persist(result: dict) -> None:
        persist_result(result, db_path)

        counters["completed"] += 1
        if result["repo"]["fetch_ok"]:
            counters["fetch_ok"] += 1
        else:
            counters["fetch_failed"] += 1
        counters["agent_files_found"] += len(result["files"])

        is_last = counters["completed"] == len(pending)
        if log_every <= 0 or (counters["completed"] % log_every != 0 and not is_last):
            return

        elapsed = max((datetime.now(timezone.utc) - started_at).total_seconds(), 0.0001)
        rate = counters["completed"] / elapsed
        remaining = len(pending) - counters["completed"]
        eta_seconds = remaining / rate if rate > 0 else None

        logger.info(
            "[RQ5 scan] %d/%d done (%d fetch_ok, %d fetch_failed, %d agent files found) -- "
            "%.2f repos/s, ETA %s",
            counters["completed"],
            len(pending),
            counters["fetch_ok"],
            counters["fetch_failed"],
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
                "fetch_ok": counters["fetch_ok"],
                "fetch_failed": counters["fetch_failed"],
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
        batches = [chunk[start : start + batch_size] for start in range(0, len(chunk), batch_size)]
        run_parallel_per_repo(batches, _compute, _persist_batch, workers, desc=f"[RQ5 scan {language}]")
        if notify:
            _notify(
                f"RQ5 scan {idx}/{len(RQ5_LANGUAGES)}: {language} done -- "
                f"{counters['completed']}/{len(pending)} total "
                f"({counters['fetch_ok']} fetch_ok, {counters['fetch_failed']} fetch_failed, "
                f"{counters['agent_files_found']} agent files found)"
            )

    if notify:
        _notify(
            f"RQ5 scan: all done -- {counters['completed']}/{len(pending)} total "
            f"({counters['fetch_ok']} fetch_ok, {counters['fetch_failed']} fetch_failed, "
            f"{counters['agent_files_found']} agent files found)"
        )

    return {"total": len(universe), "already_done": len(already_done), "scanned_this_run": len(pending)}


# error_reasons worth re-attempting. Each one is plausibly an artifact of the
# fetch step, not of the repository's root contents. Mirrors rq1_prevalence_scan.REPAIRABLE_ERROR_REASONS's own
# reasoning and naming convention.
REPAIRABLE_ERROR_REASONS: tuple[str, ...] = (
    "no_commit_at_or_before_cutoff",
    "tree_fetch_failed",
    "timeout",
    "rate_limited",
)


def load_repos_needing_retry(
    error_reasons: tuple[str, ...] = REPAIRABLE_ERROR_REASONS,
    *,
    db_path: Path = DB_PATH,
    corpus: list[dict[str, str]] | None = None,
    fixtures_dir: Path = DATASET_A_FIXTURES_DIR,
) -> list[dict]:
    """Every repo currently persisted with `fetch_ok=0` and an
    `error_reason` in `error_reasons` -- cross-referenced back against the
    corpus to recover each one's `language`/`clone_url` (not stored
    on a failed row). Empty list if the db doesn't exist yet, or nothing
    matches."""
    if not db_path.exists():
        return []
    with db_session(db_path) as conn:
        placeholders = ", ".join("?" for _ in error_reasons)
        rows = conn.execute(
            f"SELECT repo_name FROM {REPO_TABLE_NAME} WHERE fetch_ok = 0 AND error_reason IN ({placeholders})",
            error_reasons,
        ).fetchall()
    target_names = {r[0] for r in rows}
    if not target_names:
        return []
    universe = corpus if corpus is not None else load_corpus(fixtures_dir)
    return [repo for repo in universe if repo["repo_name"] in target_names]


def retry_failed_repos(
    error_reasons: tuple[str, ...] = REPAIRABLE_ERROR_REASONS,
    *,
    corpus: list[dict[str, str]] | None = None,
    fixtures_dir: Path = DATASET_A_FIXTURES_DIR,
    db_path: Path = DB_PATH,
    workers: int = DEFAULT_WORKERS,
    snapshot_date: str | None = None,
    token: str = GITHUB_TOKEN,
    catalog_path: Path = CATALOG_PATH,
    target_requests_per_hour: float | None = TARGET_REQUESTS_PER_HOUR,
    batch_size: int = GRAPHQL_BATCH_SIZE,
    notify: bool = True,
) -> dict[str, int]:
    """Re-attempt every repo currently recorded with one of `error_reasons`
    (default: `REPAIRABLE_ERROR_REASONS`) against the *already-collected* db,
    rather than a from-scratch re-run.

    The repos go through the same batched `process_repos_graphql()` as
    `run_scan()`, so a recovered repo gets its guidance files exactly as a
    first-pass one, and are persisted with the same `persist_result()`
    upsert. A repo that still fails keeps (or gets a fresh) `fetch_ok=0` row;
    nothing here can touch an already-successful `fetch_ok=1` row, since only
    repos matching `error_reasons` are selected in the first place.

    No per-language chunking (unlike `run_scan()`) -- a repair pass is expected
    to be a small fraction of the corpus, so one `notify` push at the end is
    enough.
    """
    snapshot_date = validated_snapshot_date(snapshot_date)
    catalog = load_rq5_keyword_catalog(catalog_path)
    record_scan_meta(snapshot_date, db_path)
    rate_limiter = _RateLimiter(target_requests_per_hour / 3600) if target_requests_per_hour else None
    targets = load_repos_needing_retry(
        error_reasons, db_path=db_path, corpus=corpus, fixtures_dir=fixtures_dir
    )
    logger.info(
        "[RQ5 retry] %d repos selected for retry (reasons: %s)",
        len(targets),
        ", ".join(error_reasons),
    )

    counters = {"attempted": len(targets), "recovered": 0, "still_failed": 0}

    def _compute(batch: list[dict]) -> list[dict]:
        return process_repos_graphql(
            batch, snapshot_date=snapshot_date, token=token, catalog=catalog, rate_limiter=rate_limiter
        )

    def _persist_batch(results: list[dict]) -> None:
        for result in results:
            persist_result(result, db_path)
            if result["repo"]["fetch_ok"]:
                counters["recovered"] += 1
            else:
                counters["still_failed"] += 1

    batches = _chunks(targets, batch_size)
    run_parallel_per_repo(batches, _compute, _persist_batch, workers, desc="[RQ5 retry]")

    if notify:
        _notify(
            f"RQ5 retry: {counters['recovered']}/{counters['attempted']} repos recovered "
            f"({counters['still_failed']} still failed)"
        )

    return counters


def main() -> None:
    parser = argparse.ArgumentParser(
        description="RQ5 agent-configuration-file keyword scan over the repositories "
        "that contribute a fixture to Dataset A. Reads entirely via the GitHub API "
        "(GraphQL batches) -- no cloning."
    )
    parser.add_argument(
        "--snapshot-date",
        required=True,
        help="YYYY-MM-DD. Each repository's guidance files are read at its last "
        "commit on or before this date. Required: there is no default.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        help=f"Concurrent workers (default: {DEFAULT_WORKERS})",
    )
    parser.add_argument(
        "--max-requests-per-hour",
        type=float,
        default=TARGET_REQUESTS_PER_HOUR,
        help=f"Target GitHub API request rate, paced regardless of --workers "
        f"(default: {TARGET_REQUESTS_PER_HOUR:.0f}, a margin below GitHub's "
        "5,000/hour authenticated ceiling). Pass 0 to disable throttling "
        "entirely (not recommended).",
    )
    parser.add_argument(
        "--fixtures-dir",
        type=Path,
        default=DATASET_A_FIXTURES_DIR,
        help="Directory of Dataset A *_fixtures.csv files that define the corpus "
        f"(default: {DATASET_A_FIXTURES_DIR}). Point it at an earlier build to scan "
        "that build's repositories instead.",
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Re-attempt repos currently recorded as fetch_ok=0 for a recoverable "
        f"reason ({', '.join(REPAIRABLE_ERROR_REASONS)}) against the existing db, "
        "instead of scanning the whole corpus.",
    )
    args = parser.parse_args()

    configure_logging()
    add_file_logging(LOG_PATH)
    if not GITHUB_TOKEN:
        logger.warning(
            "[RQ5 scan] No GITHUB_TOKEN found -- GitHub's unauthenticated REST "
            "API rate limit is 60 requests/hour, far too low for a corpus of "
            "thousands of repos x ~2 requests each. This run will be impractically "
            "slow without a token in .env."
        )
    target_rate = args.max_requests_per_hour or None
    if args.retry_failed:
        counts = retry_failed_repos(
            workers=args.workers,
            target_requests_per_hour=target_rate,
            snapshot_date=args.snapshot_date,
        )
        write_review_outputs()
        print(f"[RQ5 retry] done: {counts}")
        return
    counts = run_scan(
        fixtures_dir=args.fixtures_dir,
        workers=args.workers,
        target_requests_per_hour=target_rate,
        snapshot_date=args.snapshot_date,
    )
    write_review_outputs()
    print(f"[RQ5 scan] done: {counts}")


if __name__ == "__main__":
    main()
