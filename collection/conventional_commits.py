"""Conventional Commits classification for commit messages.

Used for both Dataset A (agent) and Dataset B (human, same-repo) fixtures,
so we can compare how often each group's fixture-producing commits follow
the Conventional Commits convention -- and in which category -- against
prior work (e.g. the "Agentic Much?" paper's Section 10 analysis of Claude
Code commits).
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

# Recognized Conventional Commits type prefixes, including the 4 conventional
# types (perf/ci/build/revert) that aren't in COMMIT_TYPES' own categories
# but still count as "other" rather than "none". Anything outside this fixed
# list does not match at all, regardless of whether it's colon-shaped.
_RECOGNIZED_TYPES = _KNOWN_TYPES | {"perf", "ci", "build", "revert"}

# type(scope)!: description -- scope and breaking-change "!" are optional.
_CONVENTIONAL_COMMIT_RE = re.compile(
    r"^(" + "|".join(sorted(_RECOGNIZED_TYPES)) + r")(\([^)]+\))?!?:",
    re.IGNORECASE,
)


def classify_commit_type(commit_message: str) -> str:
    """Classify a commit message's subject line by Conventional Commits type.

    Only the first line (subject) is examined, matching standard Conventional
    Commits practice. Type matching is case-insensitive, and an optional
    `(scope)` and/or breaking-change `!` marker before the colon is allowed
    (e.g. `feat(parser)!: ...`). Returns one of COMMIT_TYPES:
      - a known type (feat/fix/docs/refactor/test/chore/style) on prefix match
      - "other" if the prefix is a recognized Conventional Commits type that
        isn't one of the 7 known ones (perf, ci, build, revert)
      - "none" if the subject's prefix isn't one of the recognized types at
        all (including arbitrary words that happen to be colon-terminated)
    """
    if not commit_message or not commit_message.strip():
        return "none"

    subject = commit_message.strip().splitlines()[0].strip()
    match = _CONVENTIONAL_COMMIT_RE.match(subject)
    if not match:
        return "none"

    commit_type = match.group(1).lower()
    return commit_type if commit_type in _KNOWN_TYPES else "other"
