import pytest

from collection.conventional_commits import COMMIT_TYPES, classify_commit_type


@pytest.mark.parametrize(
    "message,expected",
    [
        ("feat: add new parser", "feat"),
        ("fix: handle null pointer", "fix"),
        ("docs: update README", "docs"),
        ("refactor: simplify config loader", "refactor"),
        ("test: add fixture for parser", "test"),
        ("chore: bump dependency versions", "chore"),
        ("style: reformat with black", "style"),
        # Case-insensitive type matching
        ("Feat: add support for X", "feat"),
        ("FIX: crash on startup", "fix"),
        # Scoped types
        ("feat(parser): support trailing commas", "feat"),
        ("fix(auth): reject expired tokens", "fix"),
        # Breaking-change marker
        ("feat!: drop support for Python 2", "feat"),
        ("feat(api)!: remove deprecated endpoint", "feat"),
    ],
)
def test_classify_commit_type_known_types(message, expected):
    assert classify_commit_type(message) == expected


@pytest.mark.parametrize(
    "message",
    [
        "perf: speed up query",
        "build: update CI pipeline",
        "ci: add workflow",
        "revert: revert previous commit",
    ],
)
def test_classify_commit_type_unknown_prefix_is_other(message):
    assert classify_commit_type(message) == "other"


@pytest.mark.parametrize(
    "message",
    [
        "",
        "   ",
        "Fix bug in the parser",
        "Merge pull request #123 from foo/bar",
        "Update test_foo.py",
        "Added a new fixture",
    ],
)
def test_classify_commit_type_non_conventional_is_none(message):
    assert classify_commit_type(message) == "none"


@pytest.mark.parametrize(
    "message",
    [
        "randomword: fix stuff",
        "wip: work in progress",
        "release: cut v1.2.3",
    ],
)
def test_classify_commit_type_colon_shaped_but_unrecognized_type_is_none(message):
    """A colon-terminated prefix that isn't one of the recognized Conventional
    Commits types (the fixed feat/fix/.../perf/ci/build/revert allowlist)
    does not match at all -- unlike an arbitrary word, it must not be
    classified as "other"."""
    assert classify_commit_type(message) == "none"


def test_classify_commit_type_uses_subject_line_only():
    message = (
        "test: add fixture for parser\n\n"
        "Co-authored-by: Claude <claude@anthropic.com>"
    )
    assert classify_commit_type(message) == "test"


def test_classify_commit_type_ignores_conventional_looking_body():
    # The subject line does not follow Conventional Commits, even though a
    # later line looks like it would.
    message = "Add parser support\n\nfeat: this line should be ignored"
    assert classify_commit_type(message) == "none"


def test_commit_types_constant_matches_expected_categories():
    assert COMMIT_TYPES == [
        "feat",
        "fix",
        "docs",
        "refactor",
        "test",
        "chore",
        "style",
        "other",
        "none",
    ]
