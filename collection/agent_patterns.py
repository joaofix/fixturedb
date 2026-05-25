"""Shared agent detection patterns and helpers."""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Iterable, Mapping

PAPER_AGENT_REPOSITORY_LANGUAGES = {"python", "javascript", "typescript", "java"}

PAPER_AGENT_CONFIG_PATTERNS = {
    "claude": ["CLAUDE.md", ".claudeignore", ".claude/", "anthropic/"],
    "cursor": ["CURSOR.md", ".cursor/", ".cursorrules"],
    "copilot": [
        "copilot_instructions.md",
        "copilot-instructions.md",
        ".copilot-*.md",
        ".copilotignore",
        ".copilot/",
    ],
}

LIGHTWEIGHT_AGENT_CONFIG_PATTERNS = {
    "claude": [
        ".cursorrules",
        ".claudeignore",
        "CLAUDE.md",
        "claude.config",
        ".claude/",
        "anthropic/",
    ],
    "cursor": [
        ".cursorrules",
        ".cursor",
        ".cursorignore",
        "CURSOR.md",
        "cursor.config",
        ".cursor/",
    ],
    "copilot": [
        "copilot_instructions.md",
        ".copilot-instructions.md",
        ".copilotignore",
        ".copilot-*.md",
        ".copilot/",
    ],
    "aider": [".aider.conf", ".aider-config", "aider.config"],
    "openhands": [".openhands.config", ".openhands"],
    "devin": [".devin.config", ".devin"],
    "cline": [".cline.config", ".cline"],
}

AGENT_SIGNATURES = {
    "claude": ["claude", "anthropic"],
    "cursor": ["cursor"],
    "copilot": ["copilot", "github.com/apps/github-copilot", "github copilot"],
    "aider": ["aider"],
    "openhands": ["openhands"],
    "devin": ["devin ai", "devin"],
    "jules": ["google jules", "jules"],
    "cline": ["cline"],
    "junie": ["junie"],
    "gemini": ["gemini"],
    "coderabbit": ["coderabbit"],
    "windsurf": ["windsurf"],
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
) -> bool:
    """Return True if any path in repo_path matches any of the provided patterns."""
    if not repo_path.exists():
        return False

    all_paths = list(repo_path.rglob("*"))
    for pattern_list in patterns.values():
        for pattern in pattern_list:
            for found_path in all_paths:
                if path_matches_pattern(found_path.relative_to(repo_path), pattern):
                    return True
    return False


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
