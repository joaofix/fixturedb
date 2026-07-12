"""Tier 1/Tier 2 agent-commit discovery for `discover-commits --dataset a --tier2`.

Consolidates the old phase_1a/1b/1c/1d scripts (which relayed state through
intermediate JSON files on disk) into two direct function calls returning
in-memory results. Tier 1 assessment and Tier 2 discovery both operate on
`db/corpus.db` -- the one piece of state this pipeline keeps with no CSV
mirror (see collection/paths.py's module docstring and the CLI-redesign
plan). This module is only reached when a caller opts in via `--tier2`; the
default pipeline never touches `db/corpus.db`.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .config import CLONES_DIR
from .logging_utils import get_logger
from .tiered_agent_corpus_scanner import (
    Tier1Assessment,
    Tier1RepositoryScanner,
    Tier2RepoMatcher,
)

logger = get_logger(__name__)


def load_corpus_repos(corpus_db: Path) -> list[dict]:
    """Load analysed/cloned repos from `corpus.db` (id, full_name, clone_url, status, stars, language)."""
    conn = sqlite3.connect(corpus_db)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(
            """
            SELECT id, full_name, clone_url, status, stars, language
            FROM repositories
            WHERE status IN ('analysed', 'cloned')
            ORDER BY full_name
            """
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def resolve_clone_path(repo_name: str, clones_dir: Path) -> Path | None:
    """Find a repo's on-disk clone directory, trying both naming conventions in use."""
    candidate = clones_dir / repo_name.replace("/", "__")
    if candidate.exists():
        return candidate
    candidate = clones_dir / repo_name.split("/")[-1]
    if candidate.exists():
        return candidate
    return None


def assess_tier1_yield(
    corpus_db: Path, clones_dir: Path = CLONES_DIR
) -> Tier1Assessment:
    """Scan corpus.db's repos for agent commits and assess whether Tier 1 alone
    meets the statistical-power thresholds (TIER1_MINIMUM_REPOS_WITH_AGENT /
    TIER1_MINIMUM_AGENT_COMMITS). Fuses old phases 1A + 1C.
    """
    if not corpus_db.exists():
        raise FileNotFoundError(
            f"corpus.db not found at {corpus_db}. Run `python -m collection paired` first."
        )
    if not clones_dir.exists():
        raise FileNotFoundError(f"clones directory not found at {clones_dir}.")

    corpus_repos = load_corpus_repos(corpus_db)
    if not corpus_repos:
        logger.warning("No repositories found in corpus.db")

    resolved = []
    for repo in corpus_repos:
        repo_name = repo["full_name"]
        clone_path = resolve_clone_path(repo_name, clones_dir)
        resolved.append({"name": repo_name, "path": str(clone_path or "")})

    scanner = Tier1RepositoryScanner(corpus_db_path=corpus_db)
    return scanner.assess_tier1(resolved)


def discover_tier2_repos(
    corpus_db: Path,
    exclude: set[str],
    target_count: int,
    clones_dir: Path = CLONES_DIR,
    language: str | None = None,
) -> list[dict]:
    """Discover supplementary repos via SEART-based candidate matching + verification.

    Fuses old phase 1D. Returns a list of dicts with `repo_name`,
    `agent_commit_count`, `commits`, and `discovery_tier` (always 2) -- the
    caller merges these into `datasets/a/repos/{lang}_repo.csv`.
    """
    if target_count <= 0:
        return []
    matcher = Tier2RepoMatcher(corpus_db_path=corpus_db, clones_dir=clones_dir)
    verified = matcher.collect_matched_agent_commits(
        target_repo_count=target_count,
        exclude_repo_names=exclude,
        language=language,
        show_progress=True,
    )
    return [
        {
            "repo_name": repo_name,
            "agent_commit_count": len(commits),
            "commits": commits,
            "discovery_tier": 2,
        }
        for repo_name, commits in verified.items()
    ]
