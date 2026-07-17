"""Shared repo-deduplication logic: clustering, tie-break, CSV output.

A "cluster" is a set of repos that share some identity key -- a commit SHA
at a given reference date (`dedupe_dataset_c_repos.py`, resolved via a live
GitHub API lookup), or a repo's current HEAD SHA (`agent_repository_counter.py`,
already present in the raw SEART data for free). How the key is obtained is
each caller's own concern; this module only knows how to group repos that
already have one, pick a survivor, and write the result. Kept in one place
so the two call sites can't drift on the tie-break rule or output schema.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .csv_adapter import get_adapter

OUTPUT_FIELDNAMES = [
    "repo_to_remove",
    "repo_to_keep",
    "shared_commit_sha",
    "cluster_size",
    "language",
    "stars_removed",
    "stars_kept",
]


def pick_cluster_survivor(repos: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the repo to keep from a cluster of duplicates.

    Highest `stars` wins; ties broken by lowest `github_id` (the
    earlier-created GitHub repo object). Both fields are expected to be
    present and coercible to int; missing/unparseable values sort last on
    stars and last on github_id (i.e. never preferred over a repo with a
    real value).

    A single-repo "cluster" just returns that repo -- callers don't need to
    special-case cluster size 1.
    """
    if not repos:
        raise ValueError("pick_cluster_survivor() called with an empty cluster")

    def _stars(repo: dict[str, Any]) -> int:
        try:
            return int(repo.get("stars") or 0)
        except (TypeError, ValueError):
            return 0

    def _github_id(repo: dict[str, Any]) -> int:
        try:
            value = repo.get("github_id")
            return int(value) if value not in (None, "") else 2**63
        except (TypeError, ValueError):
            return 2**63

    return min(repos, key=lambda r: (-_stars(r), _github_id(r)))


def _repo_name(repo: dict[str, Any]) -> str | None:
    return repo.get("repo_name") or repo.get("full_name")


def find_duplicate_clusters(
    repos: list[dict[str, Any]],
    key_fn: Callable[[dict[str, Any]], str | None],
) -> list[dict[str, Any]]:
    """Group `repos` by `key_fn(repo)` and return one row per repo that
    should be removed as a duplicate.

    `key_fn` returns whatever identity key applies (a commit SHA, typically)
    for a single repo dict, or a falsy value if unknown/unavailable -- a
    falsy key is never treated as a match, so it can never cause two
    unrelated repos to look like duplicates of each other (a missing/failed
    lookup means "keep this repo", not "cluster it with other unknowns").

    Returns rows shaped for `write_duplicate_repos_csv()`:
    {repo_to_remove, repo_to_keep, shared_commit_sha, cluster_size,
    language, stars_removed, stars_kept}. Survivor picked via
    `pick_cluster_survivor()` (highest stars, tie-break lowest github_id).
    """
    by_key: dict[str, list[dict[str, Any]]] = {}
    for repo in repos:
        key = key_fn(repo)
        if not key:
            continue
        by_key.setdefault(key, []).append(repo)

    output_rows: list[dict[str, Any]] = []
    for key, cluster in by_key.items():
        if len(cluster) < 2:
            continue
        survivor = pick_cluster_survivor(cluster)
        for repo in cluster:
            if repo is survivor:
                continue
            output_rows.append(
                {
                    "repo_to_remove": _repo_name(repo),
                    "repo_to_keep": _repo_name(survivor),
                    "shared_commit_sha": key,
                    "cluster_size": len(cluster),
                    "language": repo.get("language", ""),
                    "stars_removed": repo.get("stars", ""),
                    "stars_kept": survivor.get("stars", ""),
                }
            )
    return output_rows


def write_duplicate_repos_csv(rows: list[dict[str, Any]], output_path: Path) -> None:
    get_adapter().write_dicts(output_path, rows, OUTPUT_FIELDNAMES)
