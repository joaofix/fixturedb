"""Conventional Commits classification for agent commit messages.

Dataset A only: lets us check whether agent commits that actually produce
fixtures follow the Conventional Commits convention more (or less) often
than agents' general commit pattern, as reported in prior work (e.g. the
"Agentic Much?" paper's Section 10 analysis of Claude Code commits).
"""

import re

COMMIT_TYPES = [
    "feat",  # new feature
    "fix",  # bug fix
    "docs",  # documentation only
    "refactor",  # code change, no feature or fix
    "test",  # adding or correcting tests
    "chore",  # maintenance, dependencies, build
    "style",  # formatting, no logic change
    "other",  # follows convention but unknown type prefix
    "none",  # does not follow conventional commits at all
]

_KNOWN_TYPES = frozenset(COMMIT_TYPES) - {"other", "none"}

# type(scope)!: description -- scope and breaking-change "!" are optional.
_CONVENTIONAL_COMMIT_RE = re.compile(r"^([a-zA-Z][a-zA-Z0-9_-]*)(\([^)]*\))?!?:")


def classify_commit_type(commit_message: str) -> str:
    """Classify a commit message's subject line by Conventional Commits type.

    Only the first line (subject) is examined, matching standard Conventional
    Commits practice. Type matching is case-insensitive. Returns one of
    COMMIT_TYPES:
      - a known type (feat/fix/docs/refactor/test/chore/style) on prefix match
      - "other" if the subject follows the `type(scope)!: ` shape but the
        type itself isn't one of the known ones (e.g. perf, build, ci)
      - "none" if the subject doesn't follow Conventional Commits at all
    """
    if not commit_message or not commit_message.strip():
        return "none"

    subject = commit_message.strip().splitlines()[0].strip()
    match = _CONVENTIONAL_COMMIT_RE.match(subject)
    if not match:
        return "none"

    commit_type = match.group(1).lower()
    return commit_type if commit_type in _KNOWN_TYPES else "other"
