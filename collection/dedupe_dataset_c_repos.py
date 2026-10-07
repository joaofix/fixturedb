"""Known-duplicate-repos detector for Dataset C.

Dataset C looks at exactly one commit per repo (the last commit at or before
`HUMAN_CORPUS_CUTOFF_DATE`). Two repos that resolve to the *same* commit at
that date have byte-identical git history up to that point -- a cryptographic
guarantee, not a heuristic (a commit SHA hashes its full content plus its
entire parent chain, so two genuinely different histories cannot produce the
same SHA by chance). A real example: `openjdk/jdk`, `openjdk/loom`,
`openjdk/valhalla`, `jetbrains/jetbrainsruntime`, and `sap/sapmachine` all
share one commit -- five distinct `repo_name`s that are actually one
codebase. Not catchable via GitHub's own "exclude forks" -- every repo in
every found cluster has `isFork=false` in the raw SEART export; these are
org transfers and independently-created "shadow copies" (a raw `git push` of
existing history into a brand-new repo object), not repos GitHub's own fork
bookkeeping knows about. See `internal-docs/methodology-improvements/repo-deduplication.md`
for the full investigation.

This is a standalone tool, not part of the phase pipeline -- it never runs
automatically. Invoke it explicitly (`python -m
collection.dedupe_dataset_c_repos`) whenever there's a reason to (a SEART
data refresh, or Dataset C's candidate pool otherwise changing). It reads
Dataset C's already-selected candidate pool (`datasets/c/repos/*.csv`, the
output of `select_dataset_c_repos.select_repos()`) and writes a static
lookup table, `datasets/c/repos/duplicate_repos.csv`. Lives under
`datasets/c/`, not `github-search-raw/`, because the result is specific to
Dataset C's own `HUMAN_CORPUS_CUTOFF_DATE` -- a different reference date
(e.g. Dataset A's `AGENT_CORPUS_START_DATE`) produces a different list
entirely, so this isn't a property of the raw data itself the way
`agent_repository_counter.py`'s `lastCommitSHA`-based check is (that one
*does* live in `github-search-raw/`, as
`duplicate_repos_by_current_commit.csv` -- see that module). Consulted by
`select_dataset_c_repos.py` at build time -- a cheap CSV filter, no API
calls at runtime -- so the real cost here (one GitHub API call per
candidate repo) is paid once per re-run, not on every Dataset C build.

Known limitation: GitHub's commits API filters `until=` by *committer* date,
not author date like `dataset_c.py::find_cutoff_commit()` uses for the real
extraction cutoff. This is safe to accept: a SHA match is still proof of
identical content regardless of which date field found it, so this can never
produce a false-positive dedup -- only a false negative if a cluster's
shared history diverges right around one member's rebase point.

A separate, now-fixed failure mode: a transient lookup failure (rate limit
exhausted, network error) must never be cached as a definitive "no commit"
-- see `CommitLookupUnavailable` below. Cached indefinitely, that silently
and permanently hides a real duplicate from every future run.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path
from typing import Any

import requests

from .agent_signal_primitives import GitHubAgentFileChecker
from .config import GITHUB_TOKEN, HUMAN_CORPUS_CUTOFF_DATE
from .csv_adapter import get_adapter
from .logging_utils import configure_logging, get_logger
from .paths import stage_dir
from .repo_dedup_utils import (
    OUTPUT_FIELDNAMES,  # noqa: F401 -- re-exported
    write_duplicate_repos_csv,  # noqa: F401 -- re-exported
)
from .repo_dedup_utils import find_duplicate_clusters as _cluster_by_key
from .rq5_agent_file_scan import GraphQLError, RateLimitExhausted, _graphql_post

logger = get_logger(__name__)

DEFAULT_INPUT_DIR = stage_dir("c", "repos")
DEFAULT_OUTPUT_PATH = stage_dir("c", "repos") / "duplicate_repos.csv"
# GitHub allows 5,000 authenticated REST requests an hour. Stay below it, with the same
# margin the RQ5 scan uses, so that a retry storm cannot exhaust the budget.
DEFAULT_MAX_REQUESTS_PER_HOUR = 4000.0
DEFAULT_CHECKPOINT_PATH = stage_dir("c", "repos") / "dedupe_dataset_c_repos.checkpoint.json"


class CommitLookupUnavailable(Exception):
    """Raised by `fetch_reference_commit_sha` when a lookup could not be
    completed (rate limit exhausted, network error, unexpected HTTP status)
    -- as opposed to a definitive `None` (a 404, or a 200 with zero commits
    before the reference date), which IS safe to treat as final and cache.
    `find_duplicate_clusters` catches this and skips checkpointing the repo,
    so it's retried on the next invocation instead of being permanently (and
    possibly incorrectly) recorded as "no duplicate." Confirmed via a real
    Dataset C run: two repos (a renamed org, in both cases) got cached as a
    permanent `None` this way, hiding a real shared-commit duplicate from
    every subsequent run until the checkpoint was manually purged."""


class RequestPacer:
    """Spaces REST requests so that at most `max_per_hour` start in any hour.

    One pacer is shared by every lookup in a run, so the budget holds whatever
    the number of workers. A pause does not build up a burst: after a long
    pause, requests resume at the normal spacing. The clock and sleep functions
    are injectable for tests.
    """

    def __init__(self, max_per_hour: float, *, clock=time.monotonic, sleep=time.sleep) -> None:
        if max_per_hour <= 0:
            raise ValueError("max_per_hour must be positive")
        self._interval = 3600.0 / max_per_hour
        self._clock = clock
        self._sleep = sleep
        self._next_slot = 0.0
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            now = self._clock()
            slot = max(now, self._next_slot)
            if slot > now:
                self._sleep(slot - now)
            self._next_slot = slot + self._interval


def fetch_reference_commit_sha(
    repo_name: str,
    reference_date: str,
    github_token: str,
    *,
    timeout: int = 10,
    max_retries: int = 3,
    pacer: "RequestPacer | None" = None,
) -> str | None:
    """Return the SHA of `repo_name`'s most recent commit at or before
    `reference_date` (ISO date, e.g. "2020-12-31"), or None if there is
    definitively no such commit (repo not found, or a real 200 response with
    zero qualifying commits). Raises `CommitLookupUnavailable` if the lookup
    could not be completed at all (rate limit exhausted, network error,
    unexpected HTTP status) -- callers must not treat that the same as a
    definitive None.

    One GitHub API call: GET /repos/{repo_name}/commits?until=...&per_page=1.
    Retried/backed off using the same rate-limit handling
    GitHubAgentFileChecker already implements, rather than reimplementing it.
    """
    url = f"https://api.github.com/repos/{repo_name}/commits"
    params = {"until": f"{reference_date}T23:59:59Z", "per_page": 1}
    headers = {"Accept": "application/vnd.github.v3+json"}
    if github_token:
        headers["Authorization"] = f"token {github_token}"

    for attempt in range(max_retries + 1):
        try:
            if pacer is not None:
                pacer.acquire()
            response = requests.get(url, headers=headers, params=params, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            if isinstance(data, list) and data:
                return data[0].get("sha")
            return None
        except requests.HTTPError as e:
            if GitHubAgentFileChecker._is_rate_limited(e.response) and attempt < max_retries:
                wait_seconds = GitHubAgentFileChecker._rate_limit_wait_seconds(
                    e.response, attempt
                )
                logger.warning(
                    "[dedupe-c] Rate limited fetching %s (attempt %d/%d); retrying in %.1fs",
                    repo_name,
                    attempt + 1,
                    max_retries + 1,
                    wait_seconds,
                )
                time.sleep(wait_seconds)
                continue
            if GitHubAgentFileChecker._is_rate_limited(e.response):
                logger.warning("[dedupe-c] Rate limited fetching %s; exhausted retries", repo_name)
                raise CommitLookupUnavailable(f"rate limited: {repo_name}") from e
            if e.response is not None and e.response.status_code == 404:
                logger.debug("[dedupe-c] Not found: %s", repo_name)
                return None
            status = e.response.status_code if e.response is not None else None
            logger.debug("[dedupe-c] HTTP %s: %s", status, repo_name)
            raise CommitLookupUnavailable(f"HTTP {status}: {repo_name}") from e
        except requests.RequestException as e:
            logger.debug("[dedupe-c] Exception fetching %s: %s", repo_name, e)
            raise CommitLookupUnavailable(f"{repo_name}: {e}") from e
    raise CommitLookupUnavailable(f"exhausted retries: {repo_name}")


def _load_sha_checkpoint(checkpoint_path: Path) -> dict[str, str | None]:
    if not checkpoint_path.exists():
        return {}
    try:
        return json.loads(checkpoint_path.read_text(encoding="utf-8"))
    except Exception:
        logger.debug("[dedupe-c] Failed to load checkpoint %s; starting fresh", checkpoint_path)
        return {}


def _save_sha_checkpoint(checkpoint_path: Path, resolved: dict[str, str | None]) -> None:
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    with checkpoint_path.open("w", encoding="utf-8") as fh:
        json.dump(resolved, fh, ensure_ascii=False, indent=2)
        fh.flush()


# Sentinel for a lookup that could not be completed. Such a repository is kept for this
# run and not checkpointed, so it is retried on the next run.
UNAVAILABLE = object()

# Repositories per GraphQL request. One request costs about one point, against a
# separate 5,000-point hourly budget, so 25 per request keeps a large pool far below it.
GRAPHQL_LOOKUP_BATCH_SIZE = 25


def _commit_lookup_query(names: list[str]) -> str:
    """One aliased query: each repository's latest default-branch commit at or before
    $until, the same commit the REST lookup returns."""
    aliases = []
    for index, name in enumerate(names):
        owner, sep, repo = name.partition("/")
        if not sep or not owner or not repo:
            raise ValueError(f"not an owner/name repository: {name!r}")
        aliases.append(
            f"r{index}: repository(owner: {json.dumps(owner)}, name: {json.dumps(repo)}) {{"
            " defaultBranchRef { target { ... on Commit {"
            " history(first: 1, until: $until) { nodes { oid } } } } } }"
        )
    return "query($until: GitTimestamp!) { " + " ".join(aliases) + " }"


def fetch_reference_commit_shas_graphql(
    names: list[str],
    reference_date: str,
    github_token: str,
    *,
    pacer: "RequestPacer | None" = None,
) -> dict[str, Any]:
    """The same answer as fetch_reference_commit_sha(), for a batch of repositories in
    one GraphQL request. Maps each name to its commit SHA, to None (no commit at or
    before the date, or no such repository), or to UNAVAILABLE (the lookup failed).
    A failed request makes the whole batch UNAVAILABLE."""
    if not names:
        return {}
    try:
        payload = _graphql_post(
            _commit_lookup_query(names),
            {"until": f"{reference_date}T23:59:59Z"},
            token=github_token,
            rate_limiter=pacer,
        )
    except (RateLimitExhausted, GraphQLError) as exc:
        logger.warning("[dedupe-c] GraphQL lookup of %d repositories failed: %s", len(names), exc)
        return {name: UNAVAILABLE for name in names}

    data = payload.get("data") or {}
    errors_by_alias: dict[str, set[str]] = {}
    for error in payload.get("errors") or []:
        path = error.get("path") or [""]
        errors_by_alias.setdefault(path[0], set()).add(error.get("type", ""))

    out: dict[str, Any] = {}
    for index, name in enumerate(names):
        alias = f"r{index}"
        node = data.get(alias)
        if node is None:
            out[name] = None if "NOT_FOUND" in errors_by_alias.get(alias, set()) else UNAVAILABLE
            continue
        target = (node.get("defaultBranchRef") or {}).get("target") or {}
        commits = ((target.get("history") or {}).get("nodes")) or []
        out[name] = commits[0]["oid"] if commits else None
    return out


def _log_dedupe_progress(
    looked_up: int,
    to_look_up: int,
    cached: int,
    total: int,
    unavailable: int,
    started: float,
    log_every: int,
) -> None:
    """One progress line every `log_every` lookups, and on the last one, with a rate and an ETA."""
    if log_every <= 0 or (looked_up % log_every != 0 and looked_up != to_look_up):
        return
    elapsed = max(time.monotonic() - started, 1e-9)
    rate = looked_up / elapsed
    remaining = to_look_up - looked_up
    eta = f"{remaining / rate / 60:.0f}min" if rate > 0 and remaining > 0 else "0min"
    logger.info(
        "[dedupe-c] %d/%d repositories resolved (%d cached, %d looked up, %d unavailable) "
        "-- %.1f lookups/s, ETA %s",
        cached + looked_up,
        total,
        cached,
        looked_up,
        unavailable,
        rate,
        eta,
    )


def find_duplicate_clusters(
    repos: list[dict[str, Any]],
    reference_date: str,
    github_token: str,
    checkpoint_path: Path = DEFAULT_CHECKPOINT_PATH,
    *,
    fetch_fn=fetch_reference_commit_sha,
    checkpoint_every: int = 50,
    log_every: int = 1000,
    pacer: "RequestPacer | None" = None,
    batch_fetch_fn=None,
    batch_size: int = GRAPHQL_LOOKUP_BATCH_SIZE,
) -> list[dict[str, Any]]:
    """Group `repos` by their commit at `reference_date`; return one row per
    repo that should be removed as a duplicate.

    `repos` items need `repo_name` (or `full_name`), `language`, `stars`,
    `github_id`. `fetch_fn` is injectable for tests (avoid real API calls).
    Resumable: `checkpoint_path` persists `{repo_name: sha_or_null}` as
    results come in, so an interrupted run doesn't re-fetch already-resolved
    repos. A `None` lookup result (definitively no qualifying commit) means
    "keep this repo" -- it's never treated as a match, so it's never dropped.
    A `CommitLookupUnavailable` (rate limit exhausted, network error) is
    *not* cached -- the repo is treated as "keep" for this run only, and
    stays un-checkpointed so it's retried on the next invocation instead of
    being permanently, incorrectly recorded as "no duplicate."
    """
    resolved = _load_sha_checkpoint(checkpoint_path)
    sha_by_repo: dict[str, str | None] = {}
    names = [n for n in ((r.get("repo_name") or r.get("full_name")) for r in repos) if n]
    total = len(names)
    cached = sum(1 for n in names if n in resolved)
    to_look_up = total - cached
    logger.info(
        "[dedupe-c] %d repositories: %d already resolved from %s, %d to look up",
        total,
        cached,
        checkpoint_path,
        to_look_up,
    )

    state = {"looked_up": 0, "unavailable": 0, "since_checkpoint": 0}
    started = time.monotonic()

    def _settle(name: str, sha: Any) -> None:
        looked_up_now = state["looked_up"] + 1
        state["looked_up"] = looked_up_now
        if sha is UNAVAILABLE:
            logger.warning(
                "[dedupe-c] Could not resolve %s this run; will retry next run", name
            )
            sha_by_repo[name] = None
            state["unavailable"] += 1
        else:
            sha_by_repo[name] = sha
            resolved[name] = sha
            state["since_checkpoint"] += 1
            if state["since_checkpoint"] >= checkpoint_every:
                _save_sha_checkpoint(checkpoint_path, resolved)
                state["since_checkpoint"] = 0
        _log_dedupe_progress(
            looked_up_now, to_look_up, cached, total, state["unavailable"], started, log_every
        )

    pending = []
    for name in names:
        if name in resolved:
            sha_by_repo[name] = resolved[name]
        else:
            pending.append(name)

    if batch_fetch_fn is not None:
        for start_index in range(0, len(pending), batch_size):
            batch = pending[start_index:start_index + batch_size]
            results = batch_fetch_fn(batch, reference_date, github_token, pacer=pacer)
            for name in batch:
                _settle(name, results.get(name, UNAVAILABLE))
    else:
        extra = {"pacer": pacer} if pacer is not None else {}
        for name in pending:
            try:
                sha = fetch_fn(name, reference_date, github_token, **extra)
            except CommitLookupUnavailable:
                sha = UNAVAILABLE
            _settle(name, sha)

    _save_sha_checkpoint(checkpoint_path, resolved)
    logger.info(
        "[dedupe-c] summary: %d repositories -- %d from the checkpoint, %d looked up, "
        "%d unavailable (kept, retried next run)",
        total,
        cached,
        state["looked_up"],
        state["unavailable"],
    )

    return _cluster_by_key(repos, key_fn=lambda r: sha_by_repo.get(r.get("repo_name") or r.get("full_name")))


def _load_candidates(input_dir: Path) -> list[dict[str, Any]]:
    adapter = get_adapter()
    repos: list[dict[str, Any]] = []
    seen: set[str] = set()
    for csv_path in sorted(input_dir.glob("*_repo.csv"), key=lambda p: p.name):
        for row in adapter.read_dicts(csv_path):
            name = (row.get("repo_name") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            repos.append(row)
    return repos


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Find repos in Dataset C's candidate pool that share an identical "
            "commit at a reference date (default: HUMAN_CORPUS_CUTOFF_DATE), "
            "and write a static known-duplicates lookup table. Not part of the "
            "automatic pipeline -- run this by hand whenever there's a reason "
            "to (a SEART data refresh)."
        )
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help="Directory of {lang}_repo.csv files to dedupe (default: %(default)s)",
    )
    parser.add_argument(
        "--reference-date",
        default=HUMAN_CORPUS_CUTOFF_DATE,
        help="ISO date to check each repo's commit at/before (default: %(default)s)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Where to write the duplicate-repos CSV (default: %(default)s)",
    )
    parser.add_argument(
        "--lookup",
        choices=("rest", "graphql"),
        default="rest",
        help="How to look up each repository's commit at the reference date. 'rest' makes "
        "one REST request per repository (default). 'graphql' batches the lookups into "
        "GraphQL requests, which use a separate, much larger budget.",
    )
    parser.add_argument(
        "--max-requests-per-hour",
        type=float,
        default=DEFAULT_MAX_REQUESTS_PER_HOUR,
        help="Target GitHub REST request rate for the commit lookups, paced across "
        f"all lookups in the run (default: {DEFAULT_MAX_REQUESTS_PER_HOUR:.0f}, a margin "
        "below GitHub's 5,000/hour authenticated budget). 0 disables pacing.",
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=DEFAULT_CHECKPOINT_PATH,
        help="Resume checkpoint path (default: %(default)s)",
    )
    parser.add_argument(
        "--github-token",
        default=GITHUB_TOKEN,
        help="GitHub API token (default: GITHUB_TOKEN from .env)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_logging(fmt="%(message)s")
    args = build_parser().parse_args(argv)

    if not args.github_token:
        logger.warning(
            "[dedupe-c] No GITHUB_TOKEN set -- unauthenticated rate limit is "
            "60 req/hr, impractical for a full candidate pool. Set GITHUB_TOKEN "
            "in .env or pass --github-token."
        )

    repos = _load_candidates(args.input_dir)
    logger.info("[dedupe-c] Loaded %d candidate repos from %s", len(repos), args.input_dir)

    pacer = (
        RequestPacer(args.max_requests_per_hour) if args.max_requests_per_hour > 0 else None
    )
    rows = find_duplicate_clusters(
        repos,
        reference_date=args.reference_date,
        github_token=args.github_token,
        checkpoint_path=args.checkpoint,
        pacer=pacer,
        batch_fetch_fn=fetch_reference_commit_shas_graphql if args.lookup == "graphql" else None,
    )
    write_duplicate_repos_csv(rows, args.output)

    logger.info(
        "[dedupe-c] Found %d duplicate repos across %d clusters -> %s",
        len(rows),
        len({r["shared_commit_sha"] for r in rows}),
        args.output,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
