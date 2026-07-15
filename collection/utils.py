"""Shared utilities for the collection module.

Consolidates duplicated code patterns used across multiple files.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Iterable, Mapping

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Agent trailer / co-author regex
# ---------------------------------------------------------------------------
import re

AGENT_TRAILER_RE = re.compile(
    # "co-?authored-?by" (both hyphens optional) rather than a literal
    # "co-authored-by": some agents emit "Coauthored-by"/"Co-authoredby"
    # with a hyphen missing on either side -- a real, empirically observed
    # variant (see labri-progress/agent-mining's _iter_coauthors()), not a
    # hypothetical one. assisted-by/generated-by are this project's own
    # additional trailer conventions and are matched literally, since no
    # equivalent hyphen-variant has been observed for those.
    r"^\s*(?:co-?authored-?by|assisted-by|generated-by):\s*(.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)

# ---------------------------------------------------------------------------
# Commit-level agent detection
# ---------------------------------------------------------------------------
from .agent_patterns import (
    AGENT_SIGNATURES,
    PAPER_AGENT_REPOSITORY_LANGUAGES,
    is_bot_author,
    is_known_human_author,
    match_agent_keyword,
)


def detect_agent_in_commit(
    author_name: str,
    author_email: str,
    message: str,
    signatures: Mapping[str, Iterable[str]] = AGENT_SIGNATURES,
) -> str | None:
    """Detect agent authorship from a single commit's metadata.

    Checks in order, first match wins:
    1. Bot status (author name/email against bots.csv) -- never overridable
       by a later signal. A bot-authored commit whose message happens to
       contain an agent-style trailer (e.g. a templated "Generated-by:"
       line some tooling stamps onto dependency-bump commits) must still be
       excluded as bot, not misattributed to that agent.
    2. Co-authored-by/Assisted-by/Generated-by trailer (AGENT_TRAILER_RE) --
       the least collision-prone signal, since it's a deliberate,
       structured convention only agents/tooling emit, unlike author
       identity below, a freely-editable field real humans also populate.
    3. Author name (skipped for known human/agent-name collisions -- see
       is_known_human_author() below).
    4. Author email (same skip).

    Deliberately does NOT scan the free-text commit message body outside
    the trailer: a prose mention of an agent's name (e.g. "Revert a bad
    Claude suggestion", or "Fix cursor blinking bug" -- "cursor" the UI
    element, not the agent) is not evidence of agent authorship, and
    scanning it produced verified false positives during this project's own
    review. The trailer/author-identity fields above are the legitimate
    signal.

    Returns None for both "no agent detected" and "bot-authored" -- no
    current caller needs to distinguish the two through this function
    alone; a caller that does should call is_bot_author() itself.

    This is the single implementation shared by Tier 1
    (`Tier1RepositoryScanner` in tiered_agent_corpus_scanner.py, the
    corpus's primary detection method) and Tier 2 (`AgentCommitVerifier` in
    agent_signal_primitives.py, supplementary discovery). Each used to carry
    its own independently hand-rolled copy of this same priority order --
    already flagged as a recurring failure mode elsewhere in this codebase
    (see tiered_agent_corpus_scanner.py's `_is_test_file_path` docstring for
    a prior, already-fixed instance of the same pattern): a fix applied to
    one copy (e.g. checking bot status before the trailer, or the
    AGENT_TRAILER_RE hyphen-tolerance fix) had to be independently
    rediscovered and reapplied to the other, and the two disagreed on
    priority between author name and email until this consolidation (one
    checked them as a single combined string, the other as two separate,
    ordered fields -- see git history for the fix if the distinction
    matters for a specific commit).

    Matching is word-boundary-based (not a bare substring check),
    case-insensitive. This prevents a keyword from matching inside an
    unrelated compound word/surname (e.g. "cline" inside "McLine"), but
    cannot distinguish a keyword that is *also* a common standalone first
    name (e.g. an author literally named "Devin") -- see
    agent_heuristics.yaml's module comment for this known, inherent
    limitation of name-based matching in general. Checking the trailer
    before author identity (see order above) avoids this collision
    whenever a commit has both a colliding author name and a correct,
    unambiguous trailer. For the specific, individually-verified
    collisions this project has actually found in its own corpus (as
    opposed to the general risk any name could theoretically pose),
    is_known_human_author() additionally skips steps 3/4 outright -- see
    collection/heuristics/agent-mining/known_human_collisions.csv.
    """
    if is_bot_author(f"{author_name} {author_email}"):
        return None

    if message:
        for trailer_value in AGENT_TRAILER_RE.findall(message):
            agent_type = match_agent_keyword(trailer_value, signatures)
            if agent_type:
                return agent_type

    if is_known_human_author(f"{author_name} {author_email}"):
        return None

    agent_type = match_agent_keyword(author_name, signatures)
    if agent_type:
        return agent_type

    return match_agent_keyword(author_email, signatures)


# ---------------------------------------------------------------------------
# Repo ID helpers
# ---------------------------------------------------------------------------


def _stable_repo_id(full_name: str) -> int:
    """Derive a stable synthetic repository ID from a repository slug."""
    digest = hashlib.md5(full_name.encode("utf-8")).hexdigest()
    return int(digest[:12], 16)


# ---------------------------------------------------------------------------
# Language filter helpers
# ---------------------------------------------------------------------------
def _normalize_language_filters(
    languages: list[str] | None = None,
    language: str | None = None,
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
