"""RQ5 (Agent Configuration Files): how often do root-level agent
configuration files (AGENTS.md, CLAUDE.md) mention test-related and
fixture-related guidance, for the repositories that contribute at least one
fixture to Dataset A (agent-created fixtures)?

The corpus is read from `datasets/a/fixtures/*_fixtures.csv`. The snapshot
is the last commit on or before `--snapshot-date`, a required argument: the
date of the new Dataset A collection is not fixed yet, so there is no default.
Every run records its snapshot date in the database's `scan_meta` table, and
a run refuses to continue with a different date.

Every artifact here is `rq5_`/`rq5-`-prefixed: this module (run directly via
`python -m collection.rq5_agent_file_scan --snapshot-date YYYY-MM-DD`), its
database (`db/rq5_agent_files.db`), its keyword catalog
(`collection/heuristics/rq5_agent_file_keywords.yaml`), and its review
outputs (`rq5/`). `collection/research_questions/rq5.py` reads this
database to write the RQ5 report.

**Why the GitHub API, not a clone:** this scan needs the content of 0 to 2
root-level files per repository. GitHub's API returns those without cloning,
so the scan stays fast whatever the size of the repository. Per repository it
needs three answers, which the batched GraphQL path (`process_repos_graphql()`)
gets in one aliased query for up to `GRAPHQL_BATCH_SIZE` repositories:

1. The cutoff commit: the latest default-branch commit at or before
   `<snapshot_date>T23:59:59Z` (replaces a clone + PyDriller's commit walk).
2. The root tree entries at that commit, non-recursive (replaces `git ls-tree`;
   "look only at the repository root" falls out of the query, not something
   this code has to enforce).
3. The text of each matched root file (replaces `git show <sha>:<path>`), read
   in a second batched query. A truncated text is re-read in full through the
   REST blob endpoint.

The REST path (`process_repo()`, one repository per call) is kept for
`retry_failed_repos()` and for the truncated-text fallback. It records the same
rows as the GraphQL path; `tests/collection/test_rq5_graphql.py` checks that on
the same scenarios.

This makes the whole scan immune to repo size -- a behemoth like
`WebKit/WebKit` or `JetBrains/intellij-community` (both of which cost RQ1
repeated 600s clone timeouts) costs exactly the same handful of small
JSON responses as a tiny repo, since nothing beyond 2 root files is ever
fetched. It also eliminates an entire class of problems RQ1's clone-based
approach needed: no disk space, no `ENAMETOOLONG`, no shallow-clone edge cases, no orphaned clones.

**Symlinks need no special-casing, confirmed against a real example:** a
blob's content is just bytes, regardless of what the file represents --
the Git Blobs API returns a symlink's raw blob content (the literal
link-target text) exactly like any other blob, with no "type" branching
needed anywhere in this module. Verified directly against `pnpm/pnpm`'s
real root `CLAUDE.md`, which is genuinely a symlink to `AGENTS.md`:
fetching its blob returns the literal string `"AGENTS.md"`, not
`AGENTS.md`'s own content -- byte-for-byte what the original git-clone
implementation's `git show` gave for the equivalent local test case. This
is exactly the desired behavior per the project's own spec: search a
pointer file as its own file, never resolve it.

**Known difference from RQ1's cutoff-commit rule:** the API filters commits by
UTC time. RQ1 compares each commit's date in its own timezone. For a commit
close to UTC midnight on the cutoff date, the two rules can pick different
commits. GitHub's API does not return a commit's original timezone, so the two
rules cannot be made identical without a clone. The effect is limited to a
window of about 14 hours on the cutoff date. Root agent-config files change over
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

**CSV shape:** the db keeps every column for every table, but
`write_csv_outputs()`'s two manual-review CSVs (`agent_files.csv`,
`agent_file_matches.csv` -- `repo_scan.csv` isn't a review artifact, so it
keeps everything) are trimmed to essentials, each carrying a `github_url`
a reviewer can click straight from the spreadsheet: `agent_files.csv`
links to the file itself; `agent_file_matches.csv` links to the *exact
matched line* via a `#L<line_number>` anchor, computed with a join back
to `agent_files.github_url` at write time rather than stored as a second,
redundant copy of that URL on every match row.

**Rate limiting:** GitHub's REST API allows 5,000 authenticated requests an
hour per token, and 60 without authentication. GraphQL has a separate budget of
5,000 points an hour per token, and a batch of 25 repositories costs about 2 to
3 points, so the GraphQL path is far from the limit. A run needs `GITHUB_TOKEN`.
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
    run_with_deadline,
)

logger = get_logger(__name__)

RQ5_LANGUAGES: tuple[str, ...] = ("java", "javascript", "python", "typescript")

CATALOG_PATH = paths.ROOT_DIR / "collection" / "heuristics" / "rq5_agent_file_keywords.yaml"

# The Dataset A fixture CSVs (one per language). A repository's presence in
# any of them puts it in the RQ5 corpus.
DATASET_A_FIXTURES_DIR = paths.stage_dir("a", "fixtures")

DB_PATH = paths.DB_ROOT / "rq5_agent_files.db"
CSV_OUTPUT_DIR = paths.ROOT_DIR / "rq5"
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

# A watchdog around each repository. Each call already has its own timeout,
# but `requests` does not always honour its timeout (for example during DNS
# resolution). The watchdog costs nothing when nothing goes wrong.

PROCESS_REPO_TIMEOUT_SECONDS = 300

NTFY_TOPIC = "joaofix_fixturedb"

REPO_TABLE_NAME = "repo_scan"
FILE_TABLE_NAME = "agent_files"
MATCH_TABLE_NAME = "agent_file_matches"
META_TABLE_NAME = "scan_meta"

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS {META_TABLE_NAME} (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS {REPO_TABLE_NAME} (
    repo_name        TEXT PRIMARY KEY,
    language         TEXT NOT NULL,
    fetch_ok         INTEGER NOT NULL DEFAULT 0,
    commit_sha       TEXT,
    commit_date      TEXT,
    num_agent_files  INTEGER NOT NULL DEFAULT 0,
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
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_name      TEXT NOT NULL,
    file_name      TEXT NOT NULL,
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
    """Create all three RQ5 tables if they don't exist yet. Safe to call
    every run -- never drops or truncates existing rows."""
    with db_session(db_path) as conn:
        conn.executescript(SCHEMA)


def load_rq5_keyword_catalog(path: Path = CATALOG_PATH) -> dict[str, Any]:
    """Load the target-file/keyword catalog. Kept as a plain,
    standalone loader (not wired into `collection/heuristics/__init__.py`'s
    loader machinery) -- that module's loaders feed the main agent/fixture
    *detection* pipeline; this catalog has an entirely different consumer
    and shape, and gains nothing from sharing that machinery."""
    with path.open("r", encoding="utf-8") as fh:
        catalog = yaml.safe_load(fh)
    missing = set(catalog["ardic_test_keywords"]) - set(catalog["test_keywords"])
    if missing:
        raise ValueError(f"ardic_test_keywords must be a subset of test_keywords; missing: {sorted(missing)}")
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
    (`find_cutoff_commit_via_api()` etc.), and silently reusing that for
    "couldn't tell, GitHub throttled us" is exactly the bug class this
    module's rate-limiting fix exists to avoid (see
    `TARGET_REQUESTS_PER_HOUR`'s docstring). `process_repo()` catches this
    specifically and records a distinct `rate_limited` error_reason."""


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


def find_cutoff_commit_via_api(
    repo_name: str, snapshot_date: str, *, token: str = GITHUB_TOKEN, rate_limiter: _RateLimiter | None = None
) -> dict[str, str] | None:
    """The latest commit at or before `snapshot_date` (UTC-normalized --
    see module docstring's "Known, accepted difference" section), via
    GitHub's commits-list endpoint. `None` if the repo has no such commit,
    doesn't exist, or the request fails for a non-rate-limit reason --
    raises `RateLimitExhausted` (uncaught here) if it's specifically rate
    limiting, so `process_repo()` can tell the two apart."""
    url = f"{GITHUB_API_BASE}/repos/{repo_name}/commits"
    params = {"until": f"{snapshot_date}T23:59:59Z", "per_page": 1}
    response = _api_get(url, token=token, params=params, rate_limiter=rate_limiter)
    if response is None or response.status_code != 200:
        return None
    data = response.json()
    if not data:
        return None
    commit = data[0]
    return {"sha": commit["sha"], "date": commit["commit"]["author"]["date"][:10]}


def list_root_tree_via_api(
    repo_name: str, sha: str, *, token: str = GITHUB_TOKEN, rate_limiter: _RateLimiter | None = None
) -> list[dict[str, Any]] | None:
    """Root-level tree entries at `sha`, via GitHub's Git Trees API --
    non-recursive by default, which is exactly "look only at the
    repository root, do not search subdirectories." Each entry has
    `path`, `mode`, `type` ("blob"/"tree"), and `sha` (the blob's own sha,
    used directly by `read_blob_via_api()` -- no second, path-based
    lookup needed to resolve a matched entry to its blob). `None` on a
    non-rate-limit failure (bad sha, repo gone); see
    `find_cutoff_commit_via_api()`'s docstring for the rate-limit case."""
    url = f"{GITHUB_API_BASE}/repos/{repo_name}/git/trees/{sha}"
    response = _api_get(url, token=token, rate_limiter=rate_limiter)
    if response is None or response.status_code != 200:
        return None
    return response.json().get("tree", [])


def read_blob_via_api(
    repo_name: str, blob_sha: str, *, token: str = GITHUB_TOKEN, rate_limiter: _RateLimiter | None = None
) -> str | None:
    """Raw content of a blob, via GitHub's Git Blobs API. A blob's bytes
    are returned as-is regardless of what the file represents -- see
    module docstring for why this needs no symlink special-casing,
    confirmed against a real symlinked file. Decoded permissively
    (`errors="replace"`) since a malformed/non-UTF-8 file must never
    crash the scan -- `None` only on a non-rate-limit fetch failure or an
    unexpected (non-base64) encoding, never a decoding exception; see
    `find_cutoff_commit_via_api()`'s docstring for the rate-limit case."""
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


def find_target_files_at_commit(
    tree_entries: list[dict[str, Any]], target_files: list[str]
) -> list[tuple[str, str, str]]:
    """Case-insensitive match of `target_files` against `tree_entries`
    (as returned by `list_root_tree_via_api()`). Returns
    `(on_disk_name, canonical_file_type, blob_sha)` triples --
    `on_disk_name` preserves whatever case the repo actually used (e.g.
    "agents.md"), `canonical_file_type` is always the catalog's own
    spelling (e.g. "AGENTS.md"), matching this module's "file name" (as
    committed) vs. "file type" (canonical bucket) distinction. A "tree"
    entry (a subdirectory literally named e.g. "AGENTS.md") is
    deliberately excluded -- only a blob is a file to read.
    """
    canonical_by_casefold = {name.casefold(): name for name in target_files}
    found: list[tuple[str, str, str]] = []
    for entry in tree_entries:
        if entry.get("type") != "blob":
            continue
        name = entry.get("path", "")
        canonical = canonical_by_casefold.get(name.casefold())
        if canonical is not None:
            found.append((name, canonical, entry["sha"]))
    return found


def _repo_row(
    repo_name: str,
    language: str,
    scanned_at: str,
    *,
    fetch_ok: bool,
    error_reason: str | None = None,
    commit_sha: str | None = None,
    commit_date: str | None = None,
    num_agent_files: int = 0,
) -> dict[str, Any]:
    return {
        "repo_name": repo_name,
        "language": language,
        "fetch_ok": 1 if fetch_ok else 0,
        "commit_sha": commit_sha,
        "commit_date": commit_date,
        "num_agent_files": num_agent_files,
        "error_reason": error_reason,
        "scanned_at": scanned_at,
    }


def _scan_result(
    repo_row: dict[str, Any],
    files: list[dict[str, Any]] | None = None,
    matches: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {"repo": repo_row, "files": files or [], "matches": matches or []}


def _records_for_matched_files(
    repo_name: str,
    language: str,
    commit_sha: str,
    matched: list[tuple[str, str, str]],
    *,
    read_content: Callable[[str], str | None],
    test_patterns: dict[str, re.Pattern],
    fixture_patterns: dict[str, re.Pattern],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Scan each matched root file (see `find_target_files_at_commit()`) and
    return its `agent_files` rows and `agent_file_matches` rows. `read_content`
    maps a blob sha to the file's text, or `None` when it cannot be read; an
    unreadable file is skipped, as the REST path always did. Shared by
    `process_repo()` and `process_repos_graphql()` so both record exactly the
    same rows."""
    files: list[dict[str, Any]] = []
    matches: list[dict[str, Any]] = []
    for on_disk_name, file_type, blob_sha in matched:
        content = read_content(blob_sha)
        if content is None:
            logger.debug("[RQ5 scan] failed reading %s in %s", on_disk_name, repo_name)
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
                "commit_sha": commit_sha,
                "has_test": bool(test_matches),
                "has_fixture": bool(fixture_matches),
                "test_match_count": len(test_matches),
                "fixture_match_count": len(fixture_matches),
                "matched_test_keywords": ",".join(matched_test_keywords),
                "matched_fixture_keywords": ",".join(matched_fixture_keywords),
                "github_url": f"https://github.com/{repo_name}/blob/{commit_sha}/{on_disk_name}",
            }
        )
        for match in test_matches:
            matches.append({"repo_name": repo_name, "file_name": on_disk_name, "keyword_list": "test", **match})
        for match in fixture_matches:
            matches.append({"repo_name": repo_name, "file_name": on_disk_name, "keyword_list": "fixture", **match})
    return files, matches


# GraphQL batching. The REST path costs about two requests per repository (the
# cutoff commit, the root tree, one request per matched file), so a full run is
# roughly 2 x repositories requests against a 5,000-per-hour quota. The GraphQL
# endpoint answers the same questions for a whole batch of repositories in one
# request, and has its own point budget. Measured on 224 repositories with the
# snapshot 2026-03-01: identical output to the REST path, 17 GraphQL points in
# total, against 500 REST requests.
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
            " tree { entries { name type oid } } } } } } } }"
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
                {"path": entry["name"], "type": entry["type"], "sha": entry["oid"]}
                for entry in (commit["tree"] or {}).get("entries", [])
            ],
        }
    return outcomes


def _fetch_blobs(
    pairs: list[tuple[str, str]], *, token: str, rate_limiter: _RateLimiter | None
) -> dict[tuple[str, str], str | None]:
    """Text of each `(repo_name, blob_sha)`, or `None` when unreadable. Binary
    blobs are unreadable, as on the REST path. A truncated text is re-read in
    full through the REST blob endpoint, so the scan never sees a partial file."""
    if not pairs:
        return {}
    payload = _graphql_post(_blob_query(pairs), {}, token=token, rate_limiter=rate_limiter)
    data = payload.get("data") or {}
    texts: dict[tuple[str, str], str | None] = {}
    for index, pair in enumerate(pairs):
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
    """The same scan as `process_repo()`, for a batch of repositories in a
    handful of GraphQL requests instead of about two REST requests each (see
    the GraphQL section above). Returns one result per repository in `repos`,
    in the same shape `process_repo()` returns. Never raises: a rate-limited
    batch records every repository as `rate_limited`, and any other failure
    records them as `tree_fetch_failed`. Both reasons are retryable, and
    neither is recorded as a confirmed negative."""
    catalog = catalog or load_rq5_keyword_catalog()
    target_files = catalog["target_files"]
    test_patterns = _build_patterns(catalog["test_keywords"])
    fixture_patterns = _build_patterns(catalog["fixture_keywords"])
    scanned_at = datetime.now(timezone.utc).isoformat()

    def _fail(repo: dict, error_reason: str) -> dict[str, Any]:
        return _scan_result(
            _repo_row(repo["repo_name"], repo["language"], scanned_at, fetch_ok=False, error_reason=error_reason)
        )

    try:
        cutoffs = _fetch_cutoffs(repos, snapshot_date, token=token, rate_limiter=rate_limiter)
        matched_by_repo: dict[str, list[tuple[str, str, str]]] = {}
        pairs: list[tuple[str, str]] = []
        for repo in repos:
            outcome = cutoffs[repo["repo_name"]]
            if "sha" not in outcome:
                continue
            matched = find_target_files_at_commit(outcome["entries"], target_files)
            matched_by_repo[repo["repo_name"]] = matched
            pairs.extend((repo["repo_name"], blob_sha) for _, _, blob_sha in matched)
        blobs = _fetch_blobs(pairs, token=token, rate_limiter=rate_limiter)
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
        files, matches = _records_for_matched_files(
            repo_name,
            repo["language"],
            outcome["sha"],
            matched_by_repo[repo_name],
            read_content=lambda blob_sha, name=repo_name: blobs.get((name, blob_sha)),
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
            num_agent_files=len(files),
        )
        results.append(_scan_result(repo_row, files, matches))
    return results


def process_repo(
    repo: dict,
    *,
    snapshot_date: str,
    token: str = GITHUB_TOKEN,
    catalog: dict[str, Any] | None = None,
    rate_limiter: _RateLimiter | None = None,
) -> dict[str, Any]:
    """Resolve `repo`'s cutoff commit and keyword-scan whichever of
    `catalog`'s `target_files` exist at the repo's root as of that
    commit -- entirely via GitHub's REST API, no clone of any kind (see
    module docstring). `run_scan()` uses `process_repos_graphql()` instead;
    this per-repository path serves `retry_failed_repos()`. Never raises -- any failure is captured as a
    zero-filled row with `fetch_ok=0` and `error_reason` set, so one bad
    repo can never crash a ~24.7k-repo run. Runs in a worker thread when
    called via `run_parallel_per_repo()` -- touches no shared DB
    connection or other non-thread-safe resource.

    `catalog` defaults to loading `CATALOG_PATH` fresh when omitted --
    callers processing many repos in one run (`run_scan()`) should load it
    once and pass it through, both for efficiency and so every repo in one
    run is measured against the exact same catalog contents.

    `rate_limiter`, when given, is forwarded to every API call this repo
    makes (see `TARGET_REQUESTS_PER_HOUR`'s docstring). If *any* of them
    exhausts its retries on rate limiting, the whole repo is abandoned
    with `error_reason="rate_limited"` -- including mid-way through the
    per-file loop, deliberately discarding whatever files were already
    read rather than persisting a partial, falsely-confident
    `fetch_ok=1` row that looks like "this repo has only N agent files"
    when the truth is "N were read before GitHub cut us off."
    """
    catalog = catalog or load_rq5_keyword_catalog()
    target_files = catalog["target_files"]
    test_patterns = _build_patterns(catalog["test_keywords"])
    fixture_patterns = _build_patterns(catalog["fixture_keywords"])

    repo_name = repo["repo_name"]
    language = repo["language"]
    scanned_at = datetime.now(timezone.utc).isoformat()

    def _fail(error_reason: str) -> dict[str, Any]:
        return _scan_result(
            _repo_row(repo_name, language, scanned_at, fetch_ok=False, error_reason=error_reason)
        )

    try:
        cutoff = find_cutoff_commit_via_api(repo_name, snapshot_date, token=token, rate_limiter=rate_limiter)
        if cutoff is None:
            return _fail("no_commit_at_or_before_cutoff")

        tree_entries = list_root_tree_via_api(repo_name, cutoff["sha"], token=token, rate_limiter=rate_limiter)
        if tree_entries is None:
            return _fail("tree_fetch_failed")

        matched = find_target_files_at_commit(tree_entries, target_files)
        files, matches = _records_for_matched_files(
            repo_name,
            language,
            cutoff["sha"],
            matched,
            read_content=lambda blob_sha: read_blob_via_api(
                repo_name, blob_sha, token=token, rate_limiter=rate_limiter
            ),
            test_patterns=test_patterns,
            fixture_patterns=fixture_patterns,
        )
    except RateLimitExhausted:
        return _fail("rate_limited")

    repo_row = _repo_row(
        repo_name,
        language,
        scanned_at,
        fetch_ok=True,
        commit_sha=cutoff["sha"],
        commit_date=cutoff["date"],
        num_agent_files=len(files),
    )
    return _scan_result(repo_row, files, matches)


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
                (repo_name, language, fetch_ok, commit_sha, commit_date,
                 num_agent_files, error_reason, scanned_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(repo_name) DO UPDATE SET
                language=excluded.language,
                fetch_ok=excluded.fetch_ok,
                commit_sha=excluded.commit_sha,
                commit_date=excluded.commit_date,
                num_agent_files=excluded.num_agent_files,
                error_reason=excluded.error_reason,
                scanned_at=excluded.scanned_at
            """,
            (
                repo_row["repo_name"],
                repo_row["language"],
                repo_row["fetch_ok"],
                repo_row["commit_sha"],
                repo_row["commit_date"],
                repo_row["num_agent_files"],
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
                     line_context, line_before_2, line_before_1, line_after_1,
                     line_after_2, in_code_block)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        m["repo_name"],
                        m["file_name"],
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
                    for m in matches
                ],
            )


REPO_CSV_FIELDNAMES: tuple[str, ...] = (
    "repository",
    "commit_sha",
    "agent_files_found",
    "has_test",
    "has_test_ardic",
    "has_fixture",
    "matched_fixture_terms",
)
CODING_SHEET_FIELDNAMES: tuple[str, ...] = (
    "repository",
    "file_name",
    "line_number",
    "matched_term",
    "line_before_2",
    "line_before_1",
    "matched_line",
    "line_after_1",
    "line_after_2",
    "in_code_block",
    "category",
    "about_fixtures",
    "notes",
)
SKIPPED_CSV_FIELDNAMES: tuple[str, ...] = ("repository", "language", "error_reason")
REPOSITORY_SHEET_NAME = "rq5_repository_coding_sheet.csv"
REPOSITORY_CODING_COLUMNS: tuple[str, ...] = (
    "code_fixture_guidance",
    "evidence_row_id",
    "category",
    "notes",
)
REPOSITORY_SHEET_FIELDNAMES: tuple[str, ...] = (
    "repository",
    "primary_language",
    "fixture_match_count",
    "fixture_snippets",
    *REPOSITORY_CODING_COLUMNS,
)
CODE_FIXTURE_GUIDANCE_VALUES: tuple[str, ...] = ("yes", "no", "unsure")
# Ardic et al.'s themes for agent-file testing guidance.
CATEGORY_VALUES: tuple[str, ...] = (
    "location_placement",
    "strategy",
    "tips",
    "avoidance",
    "example",
    "framework_environment",
    "other",
)
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
_SNIPPET_ID_RE = re.compile(r"^\[(\d+)\]", re.MULTILINE)


def load_repo_guidance(
    ardic_terms: set[str] | frozenset[str], db_path: Path = DB_PATH
) -> list[dict[str, Any]]:
    """One record per analyzed repository (`fetch_ok=1`), folding its root
    agent files with logical OR. A repository with no agent file is included
    with every flag False. Repository is the unit every RQ5 statistic counts.

    `has_test_ardic` is true when a root agent file matches at least one of
    `ardic_terms` (a subset of the test keywords, so it is computed from the
    stored test matches, not from a second scan)."""
    with db_session(db_path) as conn:
        repos = conn.execute(
            f"SELECT repo_name, language, commit_sha FROM {REPO_TABLE_NAME} "
            "WHERE fetch_ok = 1 ORDER BY repo_name"
        ).fetchall()
        files = conn.execute(
            f"SELECT repo_name, file_name, has_test, has_fixture, matched_test_keywords, "
            f"matched_fixture_keywords FROM {FILE_TABLE_NAME} ORDER BY repo_name, file_name"
        ).fetchall()

    by_repo: dict[str, dict[str, Any]] = {
        repo_name: {
            "repository": repo_name,
            "language": language,
            "commit_sha": commit_sha,
            "agent_files": [],
            "has_test": False,
            "has_test_ardic": False,
            "has_fixture": False,
            "fixture_terms": set(),
            "test_terms": set(),
        }
        for repo_name, language, commit_sha in repos
    }
    for repo_name, file_name, has_test, has_fixture, test_terms, fixture_terms in files:
        record = by_repo.get(repo_name)
        if record is None:
            continue
        record["agent_files"].append(file_name)
        record["has_test"] = record["has_test"] or bool(has_test)
        record["has_fixture"] = record["has_fixture"] or bool(has_fixture)
        matched_test = {t for t in test_terms.split(",") if t}
        record["test_terms"] |= matched_test
        record["has_test_ardic"] = record["has_test_ardic"] or bool(matched_test & set(ardic_terms))
        record["fixture_terms"] |= {t for t in fixture_terms.split(",") if t}
    return list(by_repo.values())


def load_fixture_match_rows(db_path: Path = DB_PATH) -> list[tuple]:
    """Every fixture-keyword match, in the row order of
    `rq5_fixture_coding_sheet.csv`. A match's row id is its 1-based position
    in this list (the sheet's Nth data row)."""
    with db_session(db_path) as conn:
        return conn.execute(
            f"""
            SELECT repo_name, file_name, line_number, keyword, line_before_2,
                   line_before_1, line_context, line_after_1, line_after_2, in_code_block
            FROM {MATCH_TABLE_NAME}
            WHERE keyword_list = 'fixture'
            ORDER BY repo_name, file_name, line_number, keyword
            """
        ).fetchall()


def snippet_row_ids(snippets: str) -> set[int]:
    """The match row ids prefixed to each snippet of a `fixture_snippets` cell."""
    return {int(m) for m in _SNIPPET_ID_RE.findall(snippets)}


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
    match_rows: list[tuple],
    db_path: Path = DB_PATH,
    output_dir: Path = CSV_OUTPUT_DIR,
) -> Path:
    """Write `rq5_repository_coding_sheet.csv`: one row per repository with at
    least one fixture match. `fixture_snippets` holds every one of the
    repository's matched lines, one per line of the cell, as
    `[<row id>] <term> | <file>:<line> | <matched line>`, ordered by
    `SNIPPET_TERM_ORDER`, then file and line. The coding columns are empty.

    Raises rather than overwrite a sheet that already holds manual coding."""
    path = output_dir / REPOSITORY_SHEET_NAME
    if _has_manual_coding(path):
        raise ValueError(f"{path} already holds manual coding; refusing to overwrite it")

    with db_session(db_path) as conn:
        languages = dict(conn.execute(f"SELECT repo_name, language FROM {REPO_TABLE_NAME}").fetchall())

    term_rank = {term: rank for rank, term in enumerate(SNIPPET_TERM_ORDER)}
    by_repo: dict[str, list[tuple]] = {}
    for row_id, row in enumerate(match_rows, start=1):
        repo_name, file_name, line_number, keyword = row[0], row[1], row[2], row[3]
        by_repo.setdefault(repo_name, []).append((row_id, keyword, file_name, line_number, row[6]))

    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(REPOSITORY_SHEET_FIELDNAMES)
        for repo_name in sorted(by_repo):
            matches = sorted(
                by_repo[repo_name],
                key=lambda m: (term_rank.get(m[1], len(term_rank)), m[2], m[3], m[0]),
            )
            snippets = "\n".join(
                f"[{row_id}] {keyword} | {file_name}:{line_number} | {line}"
                for row_id, keyword, file_name, line_number, line in matches
            )
            writer.writerow([repo_name, languages.get(repo_name, ""), len(matches), snippets, "", "", "", ""])
    return path


def write_rq5_readme(output_dir: Path = CSV_OUTPUT_DIR) -> Path:
    """Write `README.md` for the review outputs, including the allowed values
    of the repository-level coding columns."""
    categories = "\n".join(f"- `{value}`" for value in CATEGORY_VALUES)
    text = f"""# RQ5 review outputs

Written by `python -m collection.rq5_agent_file_scan`. Manual coding is done
in `{REPOSITORY_SHEET_NAME}`; `python -m collection.research_questions.rq5_coding`
reads it once every row is coded.

## Files

- `rq5_repositories.csv`: one row per analyzed repository.
- `rq5_fixture_coding_sheet.csv`: one row per fixture-keyword match, with two
  lines of context on each side. A match's **row id** is its 1-based position
  among the data rows (row id N is spreadsheet row N+1, below the header).
- `{REPOSITORY_SHEET_NAME}`: one row per repository with at least one fixture
  match. `fixture_snippets` lists all of the repository's matched lines, each
  prefixed with its row id, ordered by term ({", ".join(SNIPPET_TERM_ORDER)}),
  then file and line. The order is only a reading order, not a classification.
- `rq5_skipped_repositories.csv`: repositories that could not be analyzed.

## Coding columns of `{REPOSITORY_SHEET_NAME}`

- `code_fixture_guidance`: {" / ".join(f"`{v}`" for v in CODE_FIXTURE_GUIDANCE_VALUES)}.
  Whether the repository's agent files give guidance about test fixtures as code.
- `evidence_row_id`: the match row id that confirmed `yes`. Required for `yes`.
- `category`: required for `yes`. One or more of the values below, separated by
  `;`. The values are the themes of Ardic et al. (SCAM 2026).
- `notes`: free text.

Allowed `category` values:

{categories}
"""
    path = output_dir / "README.md"
    path.write_text(text, encoding="utf-8")
    return path


def write_review_outputs(
    ardic_terms: set[str] | frozenset[str],
    db_path: Path = DB_PATH,
    output_dir: Path = CSV_OUTPUT_DIR,
) -> dict[str, Path]:
    """Write the RQ5 review outputs into `output_dir`:

    - `rq5_repositories.csv`: one row per analyzed repository (commit SHA,
      agent files found, the test/Ardic/fixture flags, matched fixture terms).
    - `rq5_fixture_coding_sheet.csv`: one row per fixture-keyword match, with
      two lines of context on each side and empty columns for manual coding.
    - `rq5_repository_coding_sheet.csv`: one row per repository with a
      fixture match, see `write_repository_coding_sheet()`.
    - `rq5_skipped_repositories.csv`: every repository that could not be
      analyzed, with the reason.
    - `README.md`: the files and the allowed manual-coding values.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}

    repo_path = output_dir / "rq5_repositories.csv"
    with repo_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(REPO_CSV_FIELDNAMES)
        for record in load_repo_guidance(ardic_terms, db_path):
            writer.writerow(
                [
                    record["repository"],
                    record["commit_sha"],
                    ";".join(record["agent_files"]),
                    int(record["has_test"]),
                    int(record["has_test_ardic"]),
                    int(record["has_fixture"]),
                    ",".join(sorted(record["fixture_terms"])),
                ]
            )
    written["repositories"] = repo_path

    match_rows = load_fixture_match_rows(db_path)
    with db_session(db_path) as conn:
        skipped_rows = conn.execute(
            f"SELECT repo_name, language, error_reason FROM {REPO_TABLE_NAME} "
            "WHERE fetch_ok = 0 ORDER BY repo_name"
        ).fetchall()

    sheet_path = output_dir / "rq5_fixture_coding_sheet.csv"
    with sheet_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(CODING_SHEET_FIELDNAMES)
        for row in match_rows:
            repo_name, file_name, line_number, keyword, before_2, before_1, matched, after_1, after_2, in_block = row
            writer.writerow(
                [
                    repo_name,
                    file_name,
                    line_number,
                    keyword,
                    before_2,
                    before_1,
                    matched,
                    after_1,
                    after_2,
                    bool(in_block),
                    "",
                    "",
                    "",
                ]
            )
    written["coding_sheet"] = sheet_path
    written["repository_sheet"] = write_repository_coding_sheet(match_rows, db_path, output_dir)
    written["readme"] = write_rq5_readme(output_dir)

    skipped_path = output_dir / "rq5_skipped_repositories.csv"
    with skipped_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(SKIPPED_CSV_FIELDNAMES)
        writer.writerows(skipped_rows)
    written["skipped"] = skipped_path
    return written


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
    through every `process_repo()` call, so a run's repos are all measured
    against the exact same keyword/target-file set even if the catalog
    file is hand-edited between runs.

    `target_requests_per_hour` builds one `_RateLimiter` shared by every
    worker thread for the whole run (see that class's and
    `TARGET_REQUESTS_PER_HOUR`'s docstrings) -- `None` or `0` disables
    throttling entirely (every test in this module that calls `run_scan()`
    mocks `process_repo()` out, so this never actually matters for them;
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
    process_repo_timeout_seconds: float = PROCESS_REPO_TIMEOUT_SECONDS,
    token: str = GITHUB_TOKEN,
    catalog_path: Path = CATALOG_PATH,
    target_requests_per_hour: float | None = TARGET_REQUESTS_PER_HOUR,
    notify: bool = True,
) -> dict[str, int]:
    """Re-attempt every repo currently recorded with one of
    `error_reasons` (default: `REPAIRABLE_ERROR_REASONS`) against the
    *already-collected* db, rather than a from-scratch re-run of all
    ~24.7k repos.

    Each repo is re-run through the exact same `process_repo()` (now
    using the fixed `_is_rate_limited()`) and persisted via the same
    `persist_result()` upsert `run_scan()` uses -- a repo that still
    fails simply keeps (or gets a fresh) `fetch_ok=0` row, identical in
    shape to a first-pass failure; nothing here can touch an already-
    successful `fetch_ok=1` row, since only repos matching
    `error_reasons` are selected in the first place.

    No per-language chunking (unlike `run_scan()`) -- a repair pass is
    expected to be a small fraction of the corpus, so one
    `notify` push at the end is enough.
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

    def _compute(repo: dict) -> dict:
        ok, result = run_with_deadline(
            process_repo,
            repo,
            snapshot_date=snapshot_date,
            token=token,
            catalog=catalog,
            rate_limiter=rate_limiter,
            timeout_seconds=process_repo_timeout_seconds,
        )
        if ok:
            return result
        logger.warning(
            "[RQ5 retry] %s exceeded the %ds per-repo deadline -- abandoning",
            repo["repo_name"],
            process_repo_timeout_seconds,
        )
        return _scan_result(
            _repo_row(
                repo["repo_name"],
                repo["language"],
                datetime.now(timezone.utc).isoformat(),
                fetch_ok=False,
                error_reason="timeout",
            )
        )

    def _persist(result: dict) -> None:
        persist_result(result, db_path)
        if result["repo"]["fetch_ok"]:
            counters["recovered"] += 1
        else:
            counters["still_failed"] += 1

    run_parallel_per_repo(targets, _compute, _persist, workers, desc="[RQ5 retry]")

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
        help="YYYY-MM-DD. Each repository's root agent files are read at its last "
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
    ardic_terms = set(load_rq5_keyword_catalog()["ardic_test_keywords"])
    if args.retry_failed:
        counts = retry_failed_repos(
            workers=args.workers,
            target_requests_per_hour=target_rate,
            snapshot_date=args.snapshot_date,
        )
        write_review_outputs(ardic_terms)
        print(f"[RQ5 retry] done: {counts}")
        return
    counts = run_scan(
        fixtures_dir=args.fixtures_dir,
        workers=args.workers,
        target_requests_per_hour=target_rate,
        snapshot_date=args.snapshot_date,
    )
    write_review_outputs(ardic_terms)
    print(f"[RQ5 scan] done: {counts}")


if __name__ == "__main__":
    main()
