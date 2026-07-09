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


def match_agent_keyword(
    text: str, signatures: Mapping[str, Iterable[str]]
) -> str | None:
    """Return the first agent whose keyword matches text as a whole word/phrase.

    Word-boundary matching (not a bare substring `in` check) so a short
    keyword like "cline" doesn't match inside an unrelated compound word or
    surname (e.g. "McLine"). This does NOT protect against a keyword that is
    *also* a common standalone first name or word (e.g. a human commit
    author literally named "Devin", or a commit message mentioning a text
    "cursor") -- no purely textual heuristic on freely-editable author/
    commit-message text can fully rule that out. See
    collection/heuristics/agent_heuristics.yaml's module comment for this
    known, inherent limitation of name-based Tier 1/Tier 2 detection.
    """
    text_lower = text.lower()
    for agent_type, keywords in signatures.items():
        for keyword in keywords:
            pattern = r"\b" + re.escape(keyword.lower()) + r"\b"
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
