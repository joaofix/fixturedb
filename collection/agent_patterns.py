"""Shared agent detection patterns and helpers.

The actual agent catalogs (which config files and commit signatures signal
which agent) live in collection/heuristics/agent_heuristics.yaml, not here —
this module loads that data file and derives the shapes existing callers
expect. Adding or updating an agent is a YAML edit, not a Python change; see
that file's header comment for the schema.
"""

from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path
from typing import Iterable, Mapping

from .heuristics import load_agent_heuristics
from .logging_utils import get_logger

logger = get_logger(__name__)

PAPER_AGENT_REPOSITORY_LANGUAGES = {"python", "javascript", "typescript", "java"}

# Directories never worth descending into when scanning a repo's own working
# tree for agent config files: dependency/vendor trees can ship a file that
# coincidentally matches an agent-config pattern (e.g. some vendored
# package's own CLAUDE.md, unrelated to whether *this* repo used Claude),
# and .git's internal object/hook files are neither an agent signal nor
# worth the I/O cost of walking on every scan.
_EXCLUDED_DIR_NAMES = frozenset(
    {
        ".git",
        "node_modules",
        "vendor",
        "venv",
        ".venv",
        "build",
        "dist",
        "target",
        ".tox",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
    }
)

_HEURISTICS = load_agent_heuristics()

# Commit author/email + co-authored-by trailer substrings, per agent.
AGENT_SIGNATURES = _HEURISTICS["commit_signatures"]

# Full config-file/directory catalog, per agent (broad/lightweight scans).
LIGHTWEIGHT_AGENT_CONFIG_PATTERNS = _HEURISTICS["file_based"]

# Subset of the file-based catalog used for the paper's strict
# repo-qualification filter.
PAPER_AGENT_CONFIG_PATTERNS = {
    agent: patterns
    for agent, patterns in _HEURISTICS["file_based"].items()
    if agent in _HEURISTICS["paper_scope"]
}

# Flat list of commit author/email patterns identifying CI/automation bot
# accounts (dependabot, renovate, github-actions, etc.) rather than a human
# or one of the coding agents in AGENT_SIGNATURES -- loaded from
# collection/heuristics/agent-mining/bots.csv. See that file and
# is_bot_author() below.
BOT_PATTERNS: list[str] = _HEURISTICS["bot_patterns"]

# Flat list of author/email patterns identifying specific, individually-
# verified real humans whose name or email collides with an
# AGENT_SIGNATURES keyword -- loaded from
# collection/heuristics/agent-mining/known_human_collisions.csv. See that
# file and is_known_human_author() below.
KNOWN_HUMAN_COLLISION_PATTERNS: list[str] = _HEURISTICS[
    "known_human_collision_patterns"
]


def _compile_boundary_pattern(pattern: str) -> re.Pattern[str]:
    """Compile one regex-ready catalog pattern (bots.csv or
    known_human_collisions.csv) into a case-insensitive regex.

    Unlike match_agent_keyword's AGENT_SIGNATURES patterns, these are NOT
    passed through re.escape() -- both source CSVs' pattern columns are
    already regex-ready (e.g. "dependabot\\[bot\\]" has its brackets
    pre-escaped in the source file itself), so re-escaping here would
    double-escape the backslashes and break every bracketed pattern. The
    same asymmetric boundary logic as match_agent_keyword still applies --
    a boundary assertion is only added on a side whose adjacent literal
    character is itself a word character, so a pattern ending in "]" (e.g.
    a bot pattern like the ones above) isn't broken by a trailing \\b that
    can never match right after a non-word character.
    """
    prefix = r"(?<!\w)" if re.match(r"\w", pattern) else ""
    suffix = r"(?!\w)" if re.search(r"\w$", pattern) else ""
    return re.compile(prefix + pattern + suffix, re.IGNORECASE)


_BOT_REGEXES = [_compile_boundary_pattern(pattern) for pattern in BOT_PATTERNS]
_HUMAN_COLLISION_REGEXES = [
    _compile_boundary_pattern(pattern) for pattern in KNOWN_HUMAN_COLLISION_PATTERNS
]


def is_bot_author(text: str) -> bool:
    """Return True if text (typically "{author_name} {author_email}") matches
    a known CI/automation bot pattern from
    collection/heuristics/agent-mining/bots.csv.

    Used to exclude bot-authored commits from both the human baseline and
    the agent corpus -- a bot account is neither a human developer nor one
    of the coding agents tracked in AGENT_SIGNATURES.
    """
    return any(regex.search(text) for regex in _BOT_REGEXES)


def is_known_human_author(text: str) -> bool:
    """Return True if text (typically "{author_name} {author_email}") matches
    a specific, individually-verified real human author from
    collection/heuristics/agent-mining/known_human_collisions.csv whose
    identity collides with an agent keyword (e.g. a Django core developer
    literally named "Claude" colliding with the Claude agent's own
    author-identity pattern).

    Unlike is_bot_author(), this does NOT mean "exclude this commit
    outright" -- it means "do not trust author-identity matching for this
    specific person" (see detect_agent_in_commit() in utils.py, which
    checks this only for the author-name/author-email steps, after the
    trailer check: a genuine Co-authored-by trailer on one of these
    authors' commits still counts, since a trailer is a deliberate,
    structured signal independent of the freely-editable author field this
    exclusion guards against).
    """
    return any(regex.search(text) for regex in _HUMAN_COLLISION_REGEXES)


def path_matches_pattern(
    path: Path | str, pattern: str, is_dir: bool = True
) -> bool:
    """Case-insensitive path matching with support for glob patterns and dir markers.

    is_dir tells whether `path` is actually a directory. It defaults to True
    (preserving old behavior for callers that can't cheaply determine this),
    but callers that know the real filesystem/API entry type should pass it:
    a dir-marker pattern (one ending in "/", e.g. ".cursor/") is meant to
    signal "this agent's config directory exists", not "some plain file
    happens to share that directory's name" -- without this check, a file
    literally named e.g. ".cursor" (not a directory) would false-positive
    match.
    """
    path_obj = Path(path)
    pattern_cf = pattern.casefold()
    path_str_cf = str(path_obj).casefold()

    if pattern.endswith("/"):
        if not is_dir:
            return False
        # Split into segments so multi-segment dir markers (e.g.
        # ".github/instructions/") are matched as a contiguous run of path
        # components, not compared whole against a single component (which
        # could never match, since path_obj.parts never contains "/").
        needle_parts = tuple(p for p in pattern_cf.rstrip("/").split("/") if p)
        if not needle_parts:
            return False
        path_parts_cf = tuple(part.casefold() for part in path_obj.parts)
        n = len(needle_parts)
        return any(
            path_parts_cf[i : i + n] == needle_parts
            for i in range(len(path_parts_cf) - n + 1)
        )

    # match exact filename, filename globs, or full-path globs (all casefolded)
    name_cf = path_obj.name.casefold()
    return (
        name_cf == pattern_cf
        or fnmatch.fnmatchcase(name_cf, pattern_cf)
        or fnmatch.fnmatchcase(path_str_cf, pattern_cf)
    )


def repo_contains_patterns(
    repo_path: Path, patterns: Mapping[str, Iterable[str]]
) -> str | None:
    """Return the first pattern matched by a path in repo_path, or None.

    Truthiness is unchanged for existing callers (a matched pattern string is
    truthy, None is falsy) -- this just avoids discarding which pattern
    actually matched (e.g. the specific agent-config filename found).
    """
    if not repo_path.exists():
        return None

    all_entries: list[tuple[Path, bool]] = []  # (path, is_dir)
    for dirpath, dirnames, filenames in os.walk(repo_path):
        dirnames[:] = [d for d in dirnames if d not in _EXCLUDED_DIR_NAMES]
        base = Path(dirpath)
        for d in dirnames:
            all_entries.append((base / d, True))
        for f in filenames:
            all_entries.append((base / f, False))

    for pattern_list in patterns.values():
        for pattern in pattern_list:
            for found_path, is_dir in all_entries:
                if path_matches_pattern(
                    found_path.relative_to(repo_path), pattern, is_dir=is_dir
                ):
                    return pattern
    return None


def scan_cloned_repo_for_agent_configs(repo_path: Path) -> str | None:
    """
    Check if a cloned repo contains any agent config files.

    Args:
        repo_path: Path to cloned repository

    Returns:
        The matched config-file pattern (e.g. "CLAUDE.md") if found, else None.
    """
    if not repo_path.exists():
        return None

    try:
        return repo_contains_patterns(repo_path, PAPER_AGENT_CONFIG_PATTERNS)
    except Exception as e:
        logger.debug(f"Error scanning for agent files in {repo_path}: {e}")
        return None


def match_agent_keyword(
    text: str, signatures: Mapping[str, Iterable[str]]
) -> str | None:
    """Return the first agent whose keyword matches text as a whole word/phrase.

    Word-boundary matching (not a bare substring `in` check) so a short
    keyword doesn't match inside an unrelated compound word or surname (e.g.
    "gemini" inside "McGeminicorp"). This does NOT protect against a keyword
    that is *also* a common standalone first name or word (e.g. a human
    commit author literally named "Claude", or a commit message mentioning a
    text "cursor") -- no purely textual heuristic on freely-editable author/
    commit-message text can fully rule that out. See
    collection/heuristics/agent_heuristics.yaml's module comment for this
    known, inherent limitation of name-based Tier 1/Tier 2 detection.

    Boundary assertions are only applied on a side whose adjacent keyword
    character is itself a word character. A plain `\\b` on both sides breaks
    for keywords that start or end in punctuation (e.g. "Codex (gpt-5.2-codex)"
    or "factory-droid[bot]", both real entries in agent_authors.csv): `\\b`
    right after a closing ")" requires a *word* character on the other side
    to form a boundary, so it never matches at end-of-string or before a
    space/newline -- exactly where a commit author field would end. Using
    `(?<!\\w)`/`(?!\\w)` only where the keyword's own edge is a word character
    avoids that false negative while keeping identical behavior for ordinary
    alphanumeric keywords.
    """
    text_lower = text.lower()
    for agent_type, keywords in signatures.items():
        for keyword in keywords:
            keyword_lower = keyword.lower()
            prefix = r"(?<!\w)" if re.match(r"\w", keyword_lower) else ""
            suffix = r"(?!\w)" if re.search(r"\w$", keyword_lower) else ""
            pattern = prefix + re.escape(keyword_lower) + suffix
            if re.search(pattern, text_lower):
                return agent_type
    return None


def iter_exact_filename_patterns(patterns: Mapping[str, Iterable[str]]) -> list[str]:
    """Return only filename patterns that can be used with GitHub filename: search."""
    exact_files = []
    for pattern_list in patterns.values():
        for pattern in pattern_list:
            if pattern.endswith("/"):
                continue
            if "*" in pattern or "?" in pattern:
                continue
            exact_files.append(pattern)
    return list(dict.fromkeys(exact_files))
