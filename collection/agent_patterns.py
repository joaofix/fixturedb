"""Shared agent detection patterns and helpers.

The actual agent catalogs (which config files and commit signatures signal
which agent) live in collection/heuristics/agent_heuristics.yaml, not here —
this module loads that data file and derives the shapes existing callers
expect. Adding or updating an agent is a YAML edit, not a Python change; see
that file's header comment for the schema.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Iterable, Mapping

from .heuristics import load_agent_heuristics

PAPER_AGENT_REPOSITORY_LANGUAGES = {"python", "javascript", "typescript", "java"}

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


def path_matches_pattern(path: Path | str, pattern: str) -> bool:
    """Case-insensitive path matching with support for glob patterns and dir markers."""
    path_obj = Path(path)
    pattern_cf = pattern.casefold()
    path_str_cf = str(path_obj).casefold()

    if pattern.endswith("/"):
        needle = pattern_cf.rstrip("/")
        return any(part.casefold() == needle for part in path_obj.parts)

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

    all_paths = list(repo_path.rglob("*"))
    for pattern_list in patterns.values():
        for pattern in pattern_list:
            for found_path in all_paths:
                if path_matches_pattern(found_path.relative_to(repo_path), pattern):
                    return pattern
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
