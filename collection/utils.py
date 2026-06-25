"""Shared utilities for the collection module.

Consolidates duplicated code patterns used across multiple files.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Agent trailer / co-author regex
# ---------------------------------------------------------------------------
import re

AGENT_TRAILER_RE = re.compile(
    r"^\s*(?:co-authored-by|assisted-by|generated-by):\s*(.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)

# ---------------------------------------------------------------------------
# Repo ID helpers
# ---------------------------------------------------------------------------
from .agent_patterns import PAPER_AGENT_REPOSITORY_LANGUAGES


def _stable_repo_id(full_name: str) -> int:
    """Derive a stable synthetic repository ID from a repository slug."""
    digest = hashlib.md5(full_name.encode("utf-8")).hexdigest()
    return int(digest[:12], 16)


# ---------------------------------------------------------------------------
# Language filter helpers
# ---------------------------------------------------------------------------
def _normalize_language_filters(
    languages: Optional[list[str]] = None,
    language: Optional[str] = None,
) -> list[str] | None:
    """Normalize and validate language filter arguments.

    Returns a deduplicated list of valid language strings, or None if
    no valid languages were provided.
    """
    selected: list[str] = []
    candidates: list[str] = list(languages or [])
    if language:
        candidates.append(language)

    for candidate in candidates:
        normalized = (candidate or "").strip().lower()
        if not normalized or normalized not in PAPER_AGENT_REPOSITORY_LANGUAGES:
            continue
        if normalized not in selected:
            selected.append(normalized)

    return selected or None


# ---------------------------------------------------------------------------
# Repo-row construction
# --------------------------------------------------------------------------
def build_repo_row(
    repo_name: str,
    language: str,
    *,
    stars: int | str = 0,
    forks: int = 0,
    description: str = "",
    topics: str = "[]",
    clone_url: str = "",
    num_contributors: int | str = 0,
    repo_id: int | None = None,
    created_at: str = "",
    pushed_at: str = "",
) -> dict:
    """Build a normalized repository row dict for CSV/DB insertion.

    This replaces the duplicated repo-row construction logic that appears
    in agent_corpus.py, human_corpus.py, agent_fixture_counter.py, and
    agent_repository_counter.py.
    """
    repo_id_val = repo_id if repo_id is not None else _stable_repo_id(repo_name)
    safe_stars = int(float(stars or 0))
    safe_contributors = int(float(num_contributors or 0))
    safe_clone_url = (clone_url or f"https://github.com/{repo_name}.git").strip()

    return {
        "id": repo_id_val,
        "github_id": repo_id_val,
        "full_name": repo_name,
        "language": language,
        "stars": safe_stars,
        "forks": forks,
        "description": description,
        "topics": topics,
        "created_at": created_at,
        "pushed_at": pushed_at,
        "clone_url": safe_clone_url,
        "num_contributors": safe_contributors,
    }


# ---------------------------------------------------------------------------
# Date helper
# ---------------------------------------------------------------------------
def _date_only(value: str) -> str:
    """Extract YYYY-MM-DD from an ISO timestamp string."""
    value = (value or "").strip()
    if not value:
        return ""
    return value[:10]
