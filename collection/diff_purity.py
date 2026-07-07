"""Diff-purity gates: is a commit/file's test-file diff 100% additions?

Used by `AgentFixtureExtractor` to enforce the "only extract fixtures that
were completely added, never modified" rule central to the agent-corpus
methodology. `AgentFixtureExtractor` itself always has a PyDriller `Commit`
object in hand and uses the PyDriller-based `is_pure_addition`/
`commit_is_pure_addition` (structured `ModifiedFile.diff_parsed`/
`.change_type`, not text parsing). The raw-unified-diff-text equivalents
(`_raw_diff_file_is_pure_addition`, `_raw_diff_commit_is_pure_addition`) are
kept as general-purpose utilities for any future caller that only has raw
`git show`/`git diff` text and no repo/PyDriller access (e.g. a diff blob
from an API payload) -- exercised directly by their own exhaustive test
suite (`tests/test_fixture_extractor_small.py`), not by the production
pipeline.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from .language_utils import get_language_static
from .test_commit_utils import is_test_file_path

_HUNK_HEADER_RE = re.compile(
    r"^@@ -(?P<old_start>\d+)(?:,\d+)? \+(?P<new_start>\d+)(?:,\d+)? @@"
)

# Matches an unrenamed file's "diff --git a/<path> b/<path>" header, where
# <path> is identical on both sides. Naively space-splitting this line
# breaks when <path> itself contains a space (the two paths become
# impossible to tell apart); a backreference lets the regex engine find the
# correct split by construction, since the path text after "a/" must
# reappear verbatim after "b/". A renamed file (different old/new path)
# won't match this at all -- which is fine, since a rename is rejected
# regardless further down, whether or not its exact paths were captured.
_UNRENAMED_DIFF_GIT_HEADER_RE = re.compile(r"^diff --git a/(?P<path>.+) b/(?P=path)$")


def is_pure_addition(modified_file) -> bool:
    """Return True if the modified file's diff contains exclusively added lines.

    A file is considered a "pure addition" when:
    - It was not renamed, deleted, or copied (change_type not in RENAME/DELETE/COPY)
    - Its diff_parsed contains no deleted lines

    This uses PyDriller's ModifiedFile.diff_parsed and ModifiedFile.change_type.
    """
    from pydriller.domain.commit import ModificationType

    if modified_file.change_type in (
        ModificationType.RENAME,
        ModificationType.DELETE,
        ModificationType.COPY,
    ):
        return False

    diff_parsed = modified_file.diff_parsed
    if diff_parsed.get("deleted"):
        return False

    return True


def _raw_diff_file_is_pure_addition(diff_text: str, file_path: str) -> bool:
    """Check whether *file_path*'s chunk in a unified diff has no deletions or renames.

    Parses raw ``git show`` / ``git diff`` output and returns True only when
    the file's diff contains exclusively added lines (no ``-`` lines in hunks)
    and the old/new paths are identical (no rename).
    """
    lines = diff_text.splitlines()
    in_target = False
    in_hunk = False
    old_path = None
    new_path = None

    for line in lines:
        if line.startswith("diff --git"):
            in_target = False
            in_hunk = False
            match = _UNRENAMED_DIFF_GIT_HEADER_RE.match(line)
            if match:
                path = match.group("path")
                if path == file_path:
                    in_target = True
                    old_path = path
                    new_path = path
            # A renamed file's header (differing a/ and b/ paths) won't
            # match _UNRENAMED_DIFF_GIT_HEADER_RE at all -- in_target simply
            # stays False for that block. That's fine: if file_path is the
            # rename's old or new name, this file's chunk is then treated as
            # "not found" rather than "found but renamed", but the caller
            # gets the same answer (False) either way, since the final
            # `old_path is None` check below also returns False.
            continue

        if not in_target:
            continue

        # Rename / copy / delete markers
        if line.startswith("rename from ") or line.startswith("rename to "):
            return False

        if line.startswith("copy from ") or line.startswith("copy to "):
            return False

        if line.startswith("deleted file mode"):
            return False

        if _HUNK_HEADER_RE.match(line):
            in_hunk = True
            continue

        # The "--- a/path"/"+++ b/path" file headers only ever appear before
        # the first hunk. Once inside a hunk, a line's first character alone
        # is the diff marker -- the rest is raw file content that can itself
        # start with any characters, including more dashes (e.g. a deleted
        # SQL/Lua "-- comment" or Markdown "---" divider renders as a
        # "---"-prefixed hunk line). Gating this check on in_hunk (rather
        # than matching "--- "/"+++ " unconditionally) is what lets such a
        # deletion still be recognized as a deletion below, instead of being
        # mistaken for a file header and silently skipped.
        if not in_hunk and (line.startswith("--- ") or line.startswith("+++ ")):
            continue

        # Hunk lines: a deletion line means the file is not a pure addition.
        if in_hunk and line.startswith("-"):
            return False

        # Once we hit the next file header, we're done with this file's chunk
        # (but the loop already handles this via the diff --git check above)

    # If we never found the file in the diff, treat as not pure
    if old_path is None:
        return False

    # Cross-check: if old_path != new_path, it's effectively a rename
    if old_path != new_path:
        return False

    return True


def commit_is_pure_addition(commit) -> bool:
    """Return True only if every test file in *commit* is a pure addition.

    Iterates over ``commit.modified_files``, ignores non-test files, and
    returns False if any test file has deletions, is a DELETE, or is a RENAME.
    Uses PyDriller's ``ModifiedFile.diff_parsed`` and ``ModificationType``.
    """
    from pydriller.domain.commit import ModificationType

    for modified_file in commit.modified_files:
        filename = modified_file.new_path or modified_file.old_path or ""
        path_obj = Path(filename)
        language = get_language_static(path_obj)
        if language == "unknown" or not is_test_file_path(str(filename), language):
            continue

        if modified_file.change_type in (
            ModificationType.RENAME,
            ModificationType.DELETE,
            ModificationType.COPY,
        ):
            return False

        diff_parsed = modified_file.diff_parsed
        if diff_parsed.get("deleted"):
            return False

    return True


def _raw_diff_commit_is_pure_addition(diff_text: str) -> bool:
    """Return True only if every test file in *diff_text* is a pure addition.

    Parses raw ``git show`` / ``git diff`` output.  For each file found in the
    diff, if the file is a test file and its hunk(s) contain any ``-`` line
    (deletion), or if it is a rename/delete, return False.
    Non-test files are ignored.
    """
    lines = diff_text.splitlines()
    current_file: Optional[str] = None
    current_test_lang: Optional[str] = None
    in_hunk = False

    def _lang_for(path: str) -> Optional[str]:
        lang = get_language_static(Path(path))
        if lang != "unknown" and is_test_file_path(path, lang):
            return lang
        return None

    for line in lines:
        if line.startswith("diff --git"):
            current_file = None
            current_test_lang = None
            in_hunk = False
            # The common (unrenamed) case is resolved robustly even if the
            # path contains a space (see _UNRENAMED_DIFF_GIT_HEADER_RE's
            # docstring). A renamed/copied file (differing a/ and b/ paths)
            # falls back to a plain split here -- if that guess is wrong
            # because the path *also* contains a space, it self-corrects
            # below via the "rename to "/"copy to " marker line, which
            # carries a single, unambiguous path.
            match = _UNRENAMED_DIFF_GIT_HEADER_RE.match(line)
            if match:
                current_file = match.group("path")
            else:
                parts = line.split()
                if len(parts) >= 4:
                    current_file = parts[3][2:]  # strip "b/"
            if current_file is not None:
                current_test_lang = _lang_for(current_file)
            continue

        if current_file is None:
            continue

        # Rename / copy / delete markers. "rename to "/"copy to " give the
        # definitive new path directly (one path, no ambiguity) -- re-derive
        # current_test_lang from it in case the diff --git header's fallback
        # split above guessed wrong for a renamed/copied path containing a
        # space.
        if line.startswith("rename to ") or line.startswith("copy to "):
            prefix_len = len("rename to ") if line.startswith("rename to ") else len(
                "copy to "
            )
            current_file = line[prefix_len:].strip()
            current_test_lang = _lang_for(current_file)
            if current_test_lang is not None:
                return False
            continue

        if line.startswith("rename from ") or line.startswith("copy from "):
            if current_test_lang is not None:
                return False
            continue

        if line.startswith("deleted file mode"):
            if current_test_lang is not None:
                return False
            continue

        if _HUNK_HEADER_RE.match(line):
            in_hunk = True
            continue

        # See the matching comment in _raw_diff_file_is_pure_addition: the
        # "--- a/path"/"+++ b/path" file headers only appear before the first
        # hunk, so this check must not fire once inside a hunk, or a deleted
        # line whose own content starts with "--"/"---" (e.g. a SQL/Lua "--"
        # comment or a Markdown "---" divider) would be mistaken for a file
        # header and silently skipped instead of being counted as a deletion.
        if not in_hunk and (line.startswith("--- ") or line.startswith("+++ ")):
            continue

        # A deletion line in a hunk
        if in_hunk and line.startswith("-"):
            if current_test_lang is not None:
                return False

    return True


@dataclass(frozen=True)
class DiffLineMap:
    """Per-file map of new-file line numbers to diff states."""

    line_states: Dict[int, str]

    def fixture_is_completely_added(self, start_line: int, end_line: int) -> bool:
        """Return True only if every line in the fixture span is newly added."""
        if start_line <= 0 or end_line < start_line:
            return False

        for line_no in range(start_line, end_line + 1):
            if self.line_states.get(line_no) != "added":
                return False

        return True
