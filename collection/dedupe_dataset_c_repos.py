"""Known-duplicate-repos detector for Dataset C.

Dataset C looks at exactly one commit per repo (the last commit at or before
`HUMAN_CORPUS_CUTOFF_DATE`). Two repos that resolve to the *same* commit at
that date have byte-identical git history up to that point -- a cryptographic
guarantee, not a heuristic (a commit SHA hashes its full content plus its
entire parent chain, so two genuinely different histories cannot produce the
same SHA by chance). Found via manual review of the 2026-07-17 Dataset C
collection: 16.2% of the whole corpus was duplicate content this way, the
worst single cluster being 5 OpenJDK-derived repos (`openjdk/jdk`,
`openjdk/loom`, `openjdk/valhalla`, `jetbrains/jetbrainsruntime`,
`sap/sapmachine`) all sharing one commit. Not catchable via GitHub's own
"exclude forks" -- confirmed every repo in every found cluster has
`isFork=false` in the raw SEART export; these are org transfers and
independently-created "shadow copies" (a raw `git push` of existing history
into a brand-new repo object), not repos GitHub's own fork bookkeeping knows
about.

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
extraction cutoff (confirmed via a real test against `callstack/linaria`,
where the API returned a commit 3 weeks earlier than the author-date-correct
one). This is safe to accept: a SHA match is still proof of identical content
regardless of which date field found it, so this can never produce a
false-positive dedup -- only a false negative if a cluster's shared history
diverges right around one member's rebase point.
"""

from __future__ import annotations

import argparse
import json
import sys
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

logger = get_logger(__name__)

DEFAULT_INPUT_DIR = stage_dir("c", "repos")
DEFAULT_OUTPUT_PATH = stage_dir("c", "repos") / "duplicate_repos.csv"
DEFAULT_CHECKPOINT_PATH = stage_dir("c", "repos") / "dedupe_dataset_c_repos.checkpoint.json"


def fetch_reference_commit_sha(
    repo_name: str,
    reference_date: str,
    github_token: str,
    *,
    timeout: int = 10,
    max_retries: int = 3,
) -> str | None:
    """Return the SHA of `repo_name`'s most recent commit at or before
    `reference_date` (ISO date, e.g. "2020-12-31"), or None if unavailable
    (private/deleted repo, no commits before that date, or the request
    failed after exhausting retries).

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
            elif e.response is not None and e.response.status_code == 404:
                logger.debug("[dedupe-c] Not found: %s", repo_name)
            else:
                status = e.response.status_code if e.response is not None else None
                logger.debug("[dedupe-c] HTTP %s: %s", status, repo_name)
            return None
        except requests.RequestException as e:
            logger.debug("[dedupe-c] Exception fetching %s: %s", repo_name, e)
            return None
    return None


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


def find_duplicate_clusters(
    repos: list[dict[str, Any]],
    reference_date: str,
    github_token: str,
    checkpoint_path: Path = DEFAULT_CHECKPOINT_PATH,
    *,
    fetch_fn=fetch_reference_commit_sha,
    checkpoint_every: int = 50,
) -> list[dict[str, Any]]:
    """Group `repos` by their commit at `reference_date`; return one row per
    repo that should be removed as a duplicate.

    `repos` items need `repo_name` (or `full_name`), `language`, `stars`,
    `github_id`. `fetch_fn` is injectable for tests (avoid real API calls).
    Resumable: `checkpoint_path` persists `{repo_name: sha_or_null}` as
    results come in, so an interrupted run doesn't re-fetch already-resolved
    repos. A `None` lookup result (API failure, no qualifying commit) means
    "keep this repo" -- it's never treated as a match, so it's never dropped.
    """
    resolved = _load_sha_checkpoint(checkpoint_path)
    sha_by_repo: dict[str, str | None] = {}
    fetched_since_checkpoint = 0

    for repo in repos:
        name = repo.get("repo_name") or repo.get("full_name")
        if not name:
            continue
        if name in resolved:
            sha_by_repo[name] = resolved[name]
            continue
        sha = fetch_fn(name, reference_date, github_token)
        sha_by_repo[name] = sha
        resolved[name] = sha
        fetched_since_checkpoint += 1
        if fetched_since_checkpoint >= checkpoint_every:
            _save_sha_checkpoint(checkpoint_path, resolved)
            fetched_since_checkpoint = 0

    _save_sha_checkpoint(checkpoint_path, resolved)

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

    rows = find_duplicate_clusters(
        repos,
        reference_date=args.reference_date,
        github_token=args.github_token,
        checkpoint_path=args.checkpoint,
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
