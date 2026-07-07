"""Diff-purity gates: is a commit/file's test-file diff 100% additions?

Used by `AgentFixtureExtractor` to enforce the "only extract fixtures that
were completely added, never modified" rule central to the agent-corpus
methodology. Two implementations exist for the same question — PyDriller's
parsed `ModifiedFile`/`Commit` objects (`is_pure_addition`,
`commit_is_pure_addition`) and raw unified-diff text parsing
(`_raw_diff_file_is_pure_addition`, `_raw_diff_commit_is_pure_addition`) —
because some call sites only have raw `git show` output, not a PyDriller
`Commit` object.
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
            parts = line.split()
            if len(parts) >= 4:
                a_path = parts[2][2:]  # strip "a/"
                b_path = parts[3][2:]  # strip "b/"
                if b_path == file_path or a_path == file_path:
                    in_target = True
                    old_path = a_path
                    new_path = b_path
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

    for line in lines:
        if line.startswith("diff --git"):
            current_file = None
            current_test_lang = None
            in_hunk = False
            parts = line.split()
            if len(parts) >= 4:
                b_path = parts[3][2:]  # strip "b/"
                current_file = b_path
                path_obj = Path(current_file)
                lang = get_language_static(path_obj)
                if lang != "unknown" and is_test_file_path(current_file, lang):
                    current_test_lang = lang
            continue

        if current_file is None:
            continue

        # Rename / copy / delete markers
        if line.startswith("rename from ") or line.startswith("rename to "):
            if current_test_lang is not None:
                return False
            continue

        if line.startswith("copy from ") or line.startswith("copy to "):
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
