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

**Why GitHub's REST API, not a clone (2026-10-03 design change):** the
first version of this module cloned every repo, reusing RQ1's shallow-
clone infra, purely out of convenience. That turned out to be far more
than this RQ actually needs: unlike RQ1 (which tree-sitter-parses
potentially hundreds of test files, and so genuinely needs a working
tree), RQ5 only ever needs the content of 0-2 specific root-level files.
That's a close-to-perfect fit for GitHub's Git Database API, which can
answer "what's at this commit's root" and "give me this one blob" without
ever materializing the rest of the repository. Concretely, per repo:

1. `GET /repos/{repo}/commits?until=<cutoff_date>T23:59:59Z&per_page=1`
   -- the cutoff commit (replaces a clone + PyDriller's commit walk).
2. `GET /repos/{repo}/git/trees/{sha}` -- root-level tree entries, non-
   recursive by default (replaces `git ls-tree`; "look only at the
   repository root" falls out of the API's own default behavior, not
   something this code has to enforce).
3. `GET /repos/{repo}/git/blobs/{blob_sha}` for each matched entry
   (replaces `git show <sha>:<path>`).

This makes the whole scan immune to repo size -- a behemoth like
`WebKit/WebKit` or `JetBrains/intellij-community` (both of which cost RQ1
repeated 600s clone timeouts) costs exactly the same handful of small
JSON responses as a tiny repo, since nothing beyond 2 root files is ever
fetched. It also eliminates an entire class of problems RQ1's clone-based
approach fought in production: no disk space, no `ENAMETOOLONG`, no
shallow-clone-truncation edge cases, no orphaned-clone cleanup.

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

**Known, accepted difference from RQ1's cutoff-commit semantics:**
`find_cutoff_commit_via_api()` filters by UTC-normalized commit
timestamps (`until=<date>T23:59:59Z`), while RQ1's `dataset_c.
find_cutoff_commit()` (PyDriller-based) compares each commit's date in
that commit's own *original* timezone offset. These are not always the
same commit: confirmed directly against `facebook/react`, where a commit
timestamped `2026-09-09T00:08:45+01:00` (so a UTC-based comparison
treats its UTC instant, `2026-09-08T23:08:45Z`, as being within the
cutoff day) has a local calendar date of `2026-09-09` in its own
timezone (so PyDriller, which never converts to UTC, correctly excludes
it instead). GitHub's REST API has no field anywhere that recovers a
commit's original offset -- confirmed by checking both the commits-list
and single-commit endpoints -- so exactly replicating PyDriller's
semantics via the API is not possible without a clone. This only matters
for a commit landing within the ~14-hour window around UTC midnight on
the exact cutoff date (the full range of UTC offsets); explicitly
accepted as immaterial for this RQ (reviewed and agreed 2026-10-03) --
root agent-config files change on the order of weeks/months, not hours,
so the rare repo where this shifts the chosen commit by one position is
essentially certain to still read the identical file content either way.

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

**CSV shape (2026-10-03):** the db keeps every column for every table, but
`write_csv_outputs()`'s two manual-review CSVs (`agent_files.csv`,
`agent_file_matches.csv` -- `repo_scan.csv` isn't a review artifact, so it
keeps everything) are trimmed to essentials, each carrying a `github_url`
a reviewer can click straight from the spreadsheet: `agent_files.csv`
links to the file itself; `agent_file_matches.csv` links to the *exact
matched line* via a `#L<line_number>` anchor, computed with a join back
to `agent_files.github_url` at write time rather than stored as a second,
redundant copy of that URL on every match row.

**Rate limiting:** GitHub's REST API allows 5,000 authenticated requests/
hour per token (vs. 60/hour unauthenticated -- far too low for ~24.7k
repos x ~2 requests each, so a real run requires `GITHUB_TOKEN`). Detects
and retries/backs off on both the primary (hourly quota) and secondary
(abuse-detection/burst) rate limits -- see `_is_rate_limited()`'s and
`_retry_wait_seconds()`'s own docstrings for the production incident that
made the secondary-limit case necessary, found auditing the real run's
results rather than before it ran. Paced proactively by `_RateLimiter`/
`TARGET_REQUESTS_PER_HOUR` below regardless, so this retry path should be
the exception, not the norm, in normal operation.

python -m collection.rq5_agent_file_scan
"""

from __future__ import annotations

import argparse
import base64
import csv
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
import yaml

from . import paths
from .config import GITHUB_TOKEN
from .db import db_session
from .logging_utils import configure_logging, get_logger
from .parallel_utils import run_parallel_per_repo
from .rq1_prevalence_scan import (
    DUPLICATES_PATH,
    _notify,
    _write_progress,
    add_file_logging,
    load_raw_universe,
    run_with_deadline,
)
from .rq1_prevalence_scan import RQ1_CUTOFF_DATE as RQ5_CUTOFF_DATE

logger = get_logger(__name__)

RQ5_LANGUAGES: tuple[str, ...] = ("java", "javascript", "python", "typescript")

CATALOG_PATH = paths.ROOT_DIR / "collection" / "heuristics" / "rq5_agent_file_keywords.yaml"

DB_PATH = paths.DB_ROOT / "rq5_agent_files.db"
CSV_OUTPUT_DIR = paths.ROOT_DIR / "rq5-agent-files"
PROGRESS_PATH = paths.DB_ROOT / "rq5_agent_files_progress.json"
PROGRESS_LOG_EVERY = 50
LOG_PATH = paths.DB_ROOT / "rq5_agent_files.log"

# No disk/subprocess overhead per repo anymore (just a couple of small
# HTTP calls) -- higher than RQ1's clone-bound default is safe. Worker
# count no longer controls the real request rate at all (see
# TARGET_REQUESTS_PER_HOUR/_RateLimiter below) -- it only controls how
# many repos are "in flight" waiting for their paced turn, so there's no
# rate-limit reason to keep this low.
DEFAULT_WORKERS = 20

GITHUB_API_BASE = "https://api.github.com"
API_TIMEOUT_SECONDS = 15
API_MAX_RETRIES = 3

# **Production incident avoided (2026-10-03, caught in the 100-repo toy
# run before the real run, not during it):** a plain burst of requests at
# DEFAULT_WORKERS concurrency measured ~13.7 requests/second -- about 10x
# GitHub's 5,000/hour authenticated budget's sustainable rate (~1.39/s).
# Left unthrottled, that burns the entire hourly quota in ~6 minutes, and
# `_api_get()`'s *reactive* retry (wait, then try again) was never enough
# to recover from that: GitHub's primary hourly-quota 403 doesn't reliably
# send `Retry-After` (that header is for the separate secondary/abuse-
# detection limit) -- it sends `X-RateLimit-Reset` instead, a Unix
# timestamp for the actual reset, up to an hour away. The original retry
# logic never read that header, so it fell back to a plain exponential
# backoff capped at 30s, exhausted `API_MAX_RETRIES` in well under a
# minute, and gave up -- silently recording the repo as a normal failure
# (`no_commit_at_or_before_cutoff`/`tree_fetch_failed`), indistinguishable
# from a genuine negative result. Exactly the same class of bug as RQ1's
# shallow-clone-hides-the-cutoff-commit incident: a transient/
# environmental failure conflated with a real one.
#
# Fixed with defense in depth, not just a bigger number:
# 1. `_RateLimiter` proactively paces every request at `_api_get()`'s own
#    call site to `TARGET_REQUESTS_PER_HOUR` (a deliberate margin below
#    5,000, not the limit itself -- real request timing has jitter across
#    worker threads that a target right at the edge would risk tipping
#    over), so the primary limit should never actually be hit in normal
#    operation, regardless of worker count.
# 2. `_retry_wait_seconds()` reads `X-RateLimit-Reset` as a fallback wait
#    time when `Retry-After` is absent, instead of silently capping at
#    30s -- defense in depth for the rare case the proactive limiter has a
#    gap (e.g. a previous run left the quota already low, or another
#    process shares the same token).
# 3. A distinct `rate_limited` error_reason (`RateLimitExhausted`) so any
#    repo that still hits this is cleanly identifiable and retryable
#    later, never silently mixed into a "confirmed negative" bucket.
TARGET_REQUESTS_PER_HOUR = 4000.0

# Generous relative to this module's actual worst case (a handful of small
# JSON calls, each already individually timeout-bound, plus rate-limit
# backoff) -- see run_with_deadline()'s own docstring (rq1_prevalence_scan.py)
# for the production incident that makes a watchdog worth keeping even when
# every individual call already has its own timeout: `requests`' timeout
# parameter has known edge cases (e.g. DNS resolution) where it doesn't
# always fire reliably, and this costs nothing when nothing goes wrong.
PROCESS_REPO_TIMEOUT_SECONDS = 300

NTFY_TOPIC = "joaofix_fixturedb"

REPO_TABLE_NAME = "repo_scan"
FILE_TABLE_NAME = "agent_files"
MATCH_TABLE_NAME = "agent_file_matches"

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS {REPO_TABLE_NAME} (
    repo_name        TEXT PRIMARY KEY,
    language         TEXT NOT NULL,
    fetch_ok         INTEGER NOT NULL DEFAULT 0,
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
    "file_type",
    "has_test",
    "has_fixture",
    "matched_test_keywords",
    "matched_fixture_keywords",
    "github_url",
]

_MATCH_CSV_FIELDNAMES = [
    "repo_name",
    "file_name",
    "keyword_list",
    "keyword",
    "line_context",
    "in_code_block",
    "github_url",
]

_REPO_CSV_FIELDNAMES = [
    "repo_name",
    "language",
    "fetch_ok",
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
    keyword. A keyword containing a literal space (e.g. "test setup") is
    split on spaces and re-joined with an optional space-or-hyphen between
    each pair of words, so "test setup"/"test-setup"/"testsetup" all
    match the same catalog entry -- a single-token keyword (including a
    camelCase one like "beforeEach") is matched literally instead, since
    it isn't a "multi-word term" in the catalog's own representation.

    Use this tolerance carefully: it was dropped entirely for "before
    each"/"after each"/"before all"/"after all" (catalog v2, see that
    file's own changelog) because allowing the bare-space form made them
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
    """How long to wait before retrying a rate-limited response. Prefers
    `Retry-After` (seconds -- what GitHub's secondary/abuse-detection
    limit sends), falls back to `X-RateLimit-Reset` (a Unix timestamp --
    what the *primary* hourly-quota limit sends instead, up to an hour
    away) when that header is absent, and only falls back further to a
    short exponential backoff if neither is present/parseable. See
    `TARGET_REQUESTS_PER_HOUR`'s docstring for the production incident
    (caught in a toy run, not a real one) this fixes: the original
    version of this function (`GitHubAgentFileChecker.
    _rate_limit_wait_seconds()`, still used as-is by that class's own
    callers -- this is a separate, local function, not a modification of
    that shared one) never read `X-RateLimit-Reset` at all, so it
    silently capped every wait at 30s even when the real reset was much
    further away.
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
    """True for a 429, or a 403 that is GitHub's rate limiting rather
    than a genuine permission/not-found 403.

    **Production incident (2026-10-03, found auditing the real run's
    results, not before it):** the original version of this check
    (`GitHubAgentFileChecker._is_rate_limited()`, still used as-is by
    that class's own callers -- this is a separate, local function, not
    a modification of that shared one) only recognized a 403 when
    `X-RateLimit-Remaining` was exactly `"0"` -- which is how the
    *primary* hourly-quota limit presents, but GitHub's own docs are
    explicit that the *secondary* (abuse-detection) limit does not: "there
    is no 'remaining' header that shows you your secondary rate limit
    quota" (only `Retry-After`, sometimes `X-RateLimit-Reset` -- see
    https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api).
    Under this scan's sustained 20-worker, 14-hour real run, secondary
    limiting evidently fired despite the proactive `_RateLimiter` keeping
    the *primary* budget nowhere near exhausted -- and every one of those
    403s fell straight through the old check as an ordinary non-200
    response, silently recorded as `no_commit_at_or_before_cutoff`/
    `tree_fetch_failed`/a dropped file rather than retried. Confirmed
    directly: re-querying a random sample of repos recorded as
    `no_commit_at_or_before_cutoff` found a real commit for ~1 in 3 of
    them on a plain, low-load re-check.

    A 403 with *neither* `Retry-After` nor a zeroed
    `X-RateLimit-Remaining` is still treated as NOT rate-limited -- that
    combination is what a genuine permission-denied response looks like,
    and must still surface as a real failure, not loop on retries that
    will never succeed."""
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
    repo_name: str, cutoff_date: str, *, token: str = GITHUB_TOKEN, rate_limiter: _RateLimiter | None = None
) -> dict[str, str] | None:
    """The latest commit at or before `cutoff_date` (UTC-normalized --
    see module docstring's "Known, accepted difference" section), via
    GitHub's commits-list endpoint. `None` if the repo has no such commit,
    doesn't exist, or the request fails for a non-rate-limit reason --
    raises `RateLimitExhausted` (uncaught here) if it's specifically rate
    limiting, so `process_repo()` can tell the two apart."""
    url = f"{GITHUB_API_BASE}/repos/{repo_name}/commits"
    params = {"until": f"{cutoff_date}T23:59:59Z", "per_page": 1}
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
    catalog_version: int | None,
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
    *,
    cutoff_date: str = RQ5_CUTOFF_DATE,
    token: str = GITHUB_TOKEN,
    catalog: dict[str, Any] | None = None,
    rate_limiter: _RateLimiter | None = None,
) -> dict[str, Any]:
    """Resolve `repo`'s cutoff commit and keyword-scan whichever of
    `catalog`'s `target_files` exist at the repo's root as of that
    commit -- entirely via GitHub's REST API, no clone of any kind (see
    module docstring). Never raises -- any failure is captured as a
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
    catalog_version = catalog.get("version")

    repo_name = repo["repo_name"]
    language = repo["language"]
    scanned_at = datetime.now(timezone.utc).isoformat()

    def _fail(error_reason: str) -> dict[str, Any]:
        return _scan_result(
            _repo_row(repo_name, language, scanned_at, catalog_version, fetch_ok=False, error_reason=error_reason)
        )

    try:
        cutoff = find_cutoff_commit_via_api(repo_name, cutoff_date, token=token, rate_limiter=rate_limiter)
        if cutoff is None:
            return _fail("no_commit_at_or_before_cutoff")

        tree_entries = list_root_tree_via_api(repo_name, cutoff["sha"], token=token, rate_limiter=rate_limiter)
        if tree_entries is None:
            return _fail("tree_fetch_failed")

        matched = find_target_files_at_commit(tree_entries, target_files)

        files: list[dict[str, Any]] = []
        matches: list[dict[str, Any]] = []
        for on_disk_name, file_type, blob_sha in matched:
            content = read_blob_via_api(repo_name, blob_sha, token=token, rate_limiter=rate_limiter)
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
                matches.append(
                    {"repo_name": repo_name, "file_name": on_disk_name, "keyword_list": "test", **match}
                )
            for match in fixture_matches:
                matches.append(
                    {"repo_name": repo_name, "file_name": on_disk_name, "keyword_list": "fixture", **match}
                )
    except RateLimitExhausted:
        return _fail("rate_limited")

    repo_row = _repo_row(
        repo_name,
        language,
        scanned_at,
        catalog_version,
        fetch_ok=True,
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
                (repo_name, language, fetch_ok, commit_sha, commit_date,
                 num_agent_files, catalog_version, error_reason, scanned_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(repo_name) DO UPDATE SET
                language=excluded.language,
                fetch_ok=excluded.fetch_ok,
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
                repo_row["fetch_ok"],
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
    skipped ones and why -- not a manual-review artifact, so it keeps
    every column) and the two actual manual-review surfaces, each
    trimmed to essentials with a `github_url` a reviewer can click
    straight from the spreadsheet: `agent_files.csv` (one row per agent
    file, linking to the file itself) and `agent_file_matches.csv` (one
    row per keyword occurrence, linking to the *exact matched line* via
    a `#L<line_number>` anchor -- computed by joining back to
    `agent_files.github_url` rather than storing a second, redundant
    copy of the file's own URL on every match row)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    with db_session(db_path) as conn:
        for table, fieldnames, filename in (
            (REPO_TABLE_NAME, _REPO_CSV_FIELDNAMES, "repo_scan.csv"),
            (FILE_TABLE_NAME, _FILE_CSV_FIELDNAMES, "agent_files.csv"),
        ):
            rows = conn.execute(f"SELECT {', '.join(fieldnames)} FROM {table}").fetchall()
            out_path = output_dir / filename
            with out_path.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(fieldnames)
                writer.writerows(rows)
            written[table] = out_path

        match_rows = conn.execute(
            f"""
            SELECT m.repo_name, m.file_name, m.keyword_list, m.keyword, m.line_context,
                   m.in_code_block, f.github_url || '#L' || m.line_number
            FROM {MATCH_TABLE_NAME} m
            JOIN {FILE_TABLE_NAME} f ON f.repo_name = m.repo_name AND f.file_name = m.file_name
            """
        ).fetchall()
        match_path = output_dir / "agent_file_matches.csv"
        with match_path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(_MATCH_CSV_FIELDNAMES)
            writer.writerows(match_rows)
        written[MATCH_TABLE_NAME] = match_path
    return written


# The catalog v1 -> v2 removal (see rq5_agent_file_keywords.yaml's own
# changelog comment for why) -- named here so prune_removed_keywords()'s
# real call site and this module's own tests share one source instead
# of two copies of the same four strings.
V1_TO_V2_REMOVED_FIXTURE_KEYWORDS: tuple[str, ...] = ("before each", "after each", "before all", "after all")

# The catalog v2 -> v3 removal (see rq5_agent_file_keywords.yaml's own
# changelog comment for why: the bare word "teardown" has the exact same
# defect "setup" was already excluded for -- it matches generic
# resource/UI/infra cleanup prose having nothing to do with tests).
V2_TO_V3_REMOVED_FIXTURE_KEYWORDS: tuple[str, ...] = ("teardown",)

# **Not a removal -- a reporting caveat, see collection/research_questions/
# rq5.py's conservative-subset metric.** Unlike every keyword above/removed
# so far, "fixture"/"fixtures" are not a false-positive-prone pattern match:
# they correctly find the literal word "fixture". The problem is semantic,
# not lexical, and the catalog can't fix it by word choice -- "fixture"
# genuinely has two senses in agent-config prose, and this study's object
# is only one of them. Manual sampling of 60 real matches (2026-10-03)
# found roughly a third were fixture-as-code ("functions decorated with
# @pytest.fixture", shared conftest.py fixtures) and over half were
# fixture-as-test-data-file ("tests/fixtures/*.json", "fixture.json",
# snapshot fixtures, Docker-based fixtures) -- the latter sense is
# explicitly out of scope for this study (fixtures-as-code only). Kept in
# the catalog regardless, since dropping them would also lose every real
# code-sense match, undercounting rather than fixing anything -- this
# constant exists purely so the report can additionally show a stricter,
# code-only-keyword count alongside the inclusive one.
AMBIGUOUS_FIXTURE_KEYWORDS: tuple[str, ...] = ("fixture", "fixtures")


def prune_removed_keywords(
    removed_keywords: tuple[str, ...],
    *,
    keyword_list: str = "fixture",
    new_catalog_version: int | None = None,
    db_path: Path = DB_PATH,
) -> dict[str, int]:
    """Retroactively remove `removed_keywords` (all from the same
    `keyword_list`, `"test"` or `"fixture"`) from an already-collected
    db, with no re-fetch from GitHub at all.

    This is correct, not an approximation: removing a keyword from the
    catalog can only ever shrink a match set, never grow it -- the file
    content itself didn't change, only which of its already-found
    occurrences still count. So "what `agent_files`/`agent_file_matches`
    would look like under the smaller catalog" is exactly "what they
    already look like, minus every match of the removed keywords" --
    nothing here needs the raw file text, which isn't even stored.

    Deletes the affected `agent_file_matches` rows, then recomputes
    `agent_files.has_<keyword_list>`/`<keyword_list>_match_count`/
    `matched_<keyword_list>_keywords` for every file from whatever
    matches remain. Pass `new_catalog_version` to also stamp every
    `repo_scan` row with it, documenting that the stored results are now
    consistent with that (smaller) catalog version -- correct to do
    unconditionally, since every repo's results shrink identically.

    Used once for catalog v1 -> v2 (see that YAML's own changelog
    comment for why "before each"/"after each"/"before all"/"after all"
    were removed) -- kept as a real, tested function rather than a
    throwaway script, so the same correction is available again if a
    future audit finds another keyword worth dropping.
    """
    has_col = f"has_{keyword_list}"
    count_col = f"{keyword_list}_match_count"
    matched_col = f"matched_{keyword_list}_keywords"

    with db_session(db_path) as conn:
        placeholders = ", ".join("?" for _ in removed_keywords)
        matches_deleted = conn.execute(
            f"DELETE FROM {MATCH_TABLE_NAME} WHERE keyword_list = ? AND keyword IN ({placeholders})",
            (keyword_list, *removed_keywords),
        ).rowcount

        file_rows = conn.execute(f"SELECT repo_name, file_name, {has_col} FROM {FILE_TABLE_NAME}").fetchall()
        files_changed = 0
        for repo_name, file_name, old_has_flag in file_rows:
            remaining = conn.execute(
                f"SELECT keyword FROM {MATCH_TABLE_NAME} "
                f"WHERE repo_name = ? AND file_name = ? AND keyword_list = ?",
                (repo_name, file_name, keyword_list),
            ).fetchall()
            keywords = sorted({k[0] for k in remaining})
            new_has_flag = 1 if keywords else 0
            if new_has_flag != old_has_flag:
                files_changed += 1
            conn.execute(
                f"UPDATE {FILE_TABLE_NAME} SET {has_col} = ?, {count_col} = ?, {matched_col} = ? "
                f"WHERE repo_name = ? AND file_name = ?",
                (new_has_flag, len(remaining), ",".join(keywords), repo_name, file_name),
            )

        if new_catalog_version is not None:
            conn.execute(f"UPDATE {REPO_TABLE_NAME} SET catalog_version = ?", (new_catalog_version,))

    return {
        "matches_deleted": matches_deleted,
        "files_examined": len(file_rows),
        "files_flag_changed": files_changed,
    }


def run_scan(
    raw_dir: Path = paths.RAW_SEARCH_DIR,
    duplicates_path: Path = DUPLICATES_PATH,
    db_path: Path = DB_PATH,
    progress_path: Path = PROGRESS_PATH,
    workers: int = DEFAULT_WORKERS,
    cutoff_date: str = RQ5_CUTOFF_DATE,
    log_every: int = PROGRESS_LOG_EVERY,
    notify: bool = True,
    process_repo_timeout_seconds: float = PROCESS_REPO_TIMEOUT_SECONDS,
    token: str = GITHUB_TOKEN,
    catalog_path: Path = CATALOG_PATH,
    target_requests_per_hour: float | None = TARGET_REQUESTS_PER_HOUR,
) -> dict[str, int]:
    """Scan every not-yet-scanned repo in the raw universe, persisting each
    result immediately. Resumable by construction (`db_path`'s own rows
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
    initialise_rq5_db(db_path)
    catalog = load_rq5_keyword_catalog(catalog_path)
    rate_limiter = _RateLimiter(target_requests_per_hour / 3600) if target_requests_per_hour else None
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
    counters = {"completed": 0, "fetch_ok": 0, "fetch_failed": 0, "agent_files_found": 0}

    def _compute(repo: dict) -> dict:
        ok, result = run_with_deadline(
            process_repo,
            repo,
            cutoff_date=cutoff_date,
            token=token,
            catalog=catalog,
            rate_limiter=rate_limiter,
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
                fetch_ok=False,
                error_reason="timeout",
            )
        )

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
        run_parallel_per_repo(chunk, _compute, _persist, workers, desc=f"[RQ5 scan {language}]")
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


# error_reasons worth re-attempting -- all four are plausibly an artifact
# of the fetch step itself (including the rate-limiting incident this
# module's docstring documents), not a property of the repo's real root
# contents. Mirrors rq1_prevalence_scan.REPAIRABLE_ERROR_REASONS's own
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
    raw_dir: Path = paths.RAW_SEARCH_DIR,
    duplicates_path: Path = DUPLICATES_PATH,
) -> list[dict]:
    """Every repo currently persisted with `fetch_ok=0` and an
    `error_reason` in `error_reasons` -- cross-referenced back against the
    raw universe to recover each one's `language`/`clone_url` (not stored
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
    universe = load_raw_universe(raw_dir, duplicates_path)
    return [repo for repo in universe if repo["repo_name"] in target_names]


def retry_failed_repos(
    error_reasons: tuple[str, ...] = REPAIRABLE_ERROR_REASONS,
    *,
    raw_dir: Path = paths.RAW_SEARCH_DIR,
    duplicates_path: Path = DUPLICATES_PATH,
    db_path: Path = DB_PATH,
    workers: int = DEFAULT_WORKERS,
    cutoff_date: str = RQ5_CUTOFF_DATE,
    process_repo_timeout_seconds: float = PROCESS_REPO_TIMEOUT_SECONDS,
    token: str = GITHUB_TOKEN,
    catalog_path: Path = CATALOG_PATH,
    target_requests_per_hour: float | None = TARGET_REQUESTS_PER_HOUR,
    notify: bool = True,
) -> dict[str, int]:
    """Re-attempt every repo currently recorded with one of
    `error_reasons` (default: `REPAIRABLE_ERROR_REASONS`) against the
    *already-collected* db, rather than a from-scratch re-run of all
    ~24.7k repos -- a cheap, targeted repair pass for the rate-limit-
    detection incident this module's docstring documents.

    Each repo is re-run through the exact same `process_repo()` (now
    using the fixed `_is_rate_limited()`) and persisted via the same
    `persist_result()` upsert `run_scan()` uses -- a repo that still
    fails simply keeps (or gets a fresh) `fetch_ok=0` row, identical in
    shape to a first-pass failure; nothing here can touch an already-
    successful `fetch_ok=1` row, since only repos matching
    `error_reasons` are selected in the first place.

    No per-language chunking (unlike `run_scan()`) -- a repair pass is
    expected to be a small fraction of the full universe, so one
    `notify` push at the end is enough.
    """
    catalog = load_rq5_keyword_catalog(catalog_path)
    rate_limiter = _RateLimiter(target_requests_per_hour / 3600) if target_requests_per_hour else None
    targets = load_repos_needing_retry(
        error_reasons, db_path=db_path, raw_dir=raw_dir, duplicates_path=duplicates_path
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
            cutoff_date=cutoff_date,
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
                catalog.get("version"),
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
        description="RQ5 agent-configuration-file keyword scan over the raw repo "
        "universe (github-search-raw/*.csv.gz), independent of Dataset A/B/C. "
        "Reads entirely via the GitHub REST API -- no cloning."
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
        "--retry-failed",
        action="store_true",
        help="Re-attempt repos currently recorded as fetch_ok=0 for a recoverable "
        f"reason ({', '.join(REPAIRABLE_ERROR_REASONS)}) against the existing db, "
        "instead of scanning the full universe.",
    )
    args = parser.parse_args()

    configure_logging()
    add_file_logging(LOG_PATH)
    if not GITHUB_TOKEN:
        logger.warning(
            "[RQ5 scan] No GITHUB_TOKEN found -- GitHub's unauthenticated REST "
            "API rate limit is 60 requests/hour, far too low for ~24.7k repos "
            "x ~2 requests each. This run will be impractically slow without "
            "a token in .env."
        )
    target_rate = args.max_requests_per_hour or None
    if args.retry_failed:
        counts = retry_failed_repos(workers=args.workers, target_requests_per_hour=target_rate)
        write_csv_outputs()
        print(f"[RQ5 retry] done: {counts}")
        return
    counts = run_scan(workers=args.workers, target_requests_per_hour=target_rate)
    write_csv_outputs()
    print(f"[RQ5 scan] done: {counts}")


if __name__ == "__main__":
    main()
