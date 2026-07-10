from pathlib import Path

import pytest

from collection import agent_patterns as ap


def make_match_name(pattern: str) -> str:
    """Produce a concrete filename that should match the given pattern."""
    if pattern.endswith("/"):
        return pattern.rstrip("/")
    if "*" in pattern or "?" in pattern:
        # replace wildcards with a concrete token
        return pattern.replace("*", "MATCH").replace("?", "X")
    return pattern


@pytest.mark.parametrize(
    "mapping", [ap.PAPER_AGENT_CONFIG_PATTERNS, ap.LIGHTWEIGHT_AGENT_CONFIG_PATTERNS]
)
def test_all_patterns_have_matching_root_and_nested(mapping, tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()

    counter = 0
    for _agent, patterns in mapping.items():
        for pattern in patterns:
            counter += 1
            name = make_match_name(pattern)
            # A "file" pattern containing its own "/" (e.g. ".jetbrains/instructions.md")
            # is only meant to match at that exact relative path from the repo
            # root -- unlike a bare filename or a dir-marker (matched by
            # directory name anywhere in the path), matching the full
            # fnmatch'd relative path string means it can't also match once
            # nested under an extra directory. So it gets root-only coverage.
            is_multi_segment_file = not pattern.endswith("/") and "/" in name
            # create each pattern in its own subdirectory to avoid collisions
            base = repo / f"unit_{counter}"
            base.mkdir(parents=True, exist_ok=True)
            if pattern.endswith("/"):
                (base / name).mkdir(parents=True, exist_ok=True)
                (base / "nested" / name).mkdir(parents=True, exist_ok=True)
            elif is_multi_segment_file:
                (base / name).parent.mkdir(parents=True, exist_ok=True)
                (base / name).write_text("ok")
            else:
                (base / name).write_text("ok")
                (base / "nested").mkdir(parents=True, exist_ok=True)
                (base / "nested" / name).write_text("ok")

    # After creating all, assert repo_contains_patterns finds something for every mapping
    assert ap.repo_contains_patterns(repo, mapping)


def test_dir_marker_does_not_match_substring(tmp_path):
    repo = tmp_path / "r2"
    repo.mkdir()
    (repo / "someanthropic").mkdir()
    assert not ap.repo_contains_patterns(repo, {"x": ["anthropic/"]})


def test_path_matches_pattern_accepts_str_and_path():
    assert ap.path_matches_pattern("README.md", "readme.md")
    assert ap.path_matches_pattern(Path("README.md"), "readme.md")


def test_iter_exact_filename_patterns_contains_expected_files():
    exact_light = ap.iter_exact_filename_patterns(ap.LIGHTWEIGHT_AGENT_CONFIG_PATTERNS)
    # ensure some known exact files are present
    assert "claude.config" in exact_light or "CLAUDE.md" in exact_light


def test_agent_signatures_nonempty():
    # ensure signatures mapping contains entries for patterns we care about
    for key in ["claude", "copilot", "cursor"]:
        assert key in ap.AGENT_SIGNATURES and ap.AGENT_SIGNATURES[key]


def test_match_agent_keyword_handles_punctuation_ending_patterns():
    """Regression: a plain \\b on both sides of the escaped keyword breaks
    for a pattern ending in punctuation (e.g. agent_authors.csv's "Codex
    (gpt-5.2-codex)" or "factory-droid[bot]") -- \\b right after a
    non-word character like ")" requires a *word* character on the other
    side to form a boundary, so it silently never matches at end-of-string
    or before a space/newline, which is exactly where a commit author
    field ends. match_agent_keyword must only apply a boundary assertion
    on a side whose adjacent keyword character is itself a word character."""
    signatures = {
        "codex": ["Codex (gpt-5.2-codex)"],
        "factory_droid": ["factory-droid[bot]"],
    }
    assert (
        ap.match_agent_keyword("Author: Codex (gpt-5.2-codex)", signatures)
        == "codex"
    )
    assert (
        ap.match_agent_keyword(
            "Co-authored-by: factory-droid[bot] <noreply@github.com>", signatures
        )
        == "factory_droid"
    )


def test_match_agent_keyword_still_rejects_partial_word_match():
    """The punctuation-boundary fix must not regress plain alphanumeric
    keywords back to bare substring matching."""
    signatures = {"cline": ["cline"]}
    assert ap.match_agent_keyword("commit by McLine", signatures) is None
    assert ap.match_agent_keyword("commit by cline", signatures) == "cline"


def test_is_bot_author_matches_upstream_bracket_pattern():
    """dependabot\\[bot\\] in bots.csv is already regex-escaped by the
    upstream source -- is_bot_author must use it as-is, not re.escape() it
    a second time (which would require a literal backslash in the text and
    never match anything real)."""
    assert ap.is_bot_author("dependabot[bot] dependabot@users.noreply.github.com")


def test_is_bot_author_catches_our_verified_additions():
    """copilot-swe-agent[bot] and anthropic-code-agent[bot] are real bot
    accounts observed in this project's own corpus, individually appended
    to bots.csv after the upstream boundary because they're missing from
    labri-progress/agent-mining's list and their names contain an agent
    keyword (would otherwise be misattributed as agent-authored, not
    excluded as bot -- see agent-detection.md's Known Limitations)."""
    assert ap.is_bot_author(
        "copilot-swe-agent[bot] 198982749+Copilot@users.noreply.github.com"
    )
    assert ap.is_bot_author(
        "anthropic-code-agent[bot] 242468646+Claude@users.noreply.github.com"
    )


def test_is_bot_author_does_not_catch_uncatalogued_bot_names():
    """Documented known limitation, not a bug: bots.csv's own additions are
    a short, explicit list of individually-verified accounts (see test
    above), not a generic "[bot]"-suffix catch-all (see
    docs/architecture/agent-detection.md's Known Limitations) -- a
    bracket-suffixed bot name in neither the upstream list nor that short
    addition is simply not detected, even though it follows the same
    suffix convention as many patterns that ARE listed."""
    assert not ap.is_bot_author("some-brand-new-app[bot] noreply@github.com")


def test_is_bot_author_matches_non_bracket_upstream_pattern():
    """Many upstream bots.csv rows have no brackets at all (e.g. "Renovate
    Bot", "dotnet bot") -- these were never caught by the old bare
    '"[bot]" in author_name' check this project used before adopting the
    upstream catalog."""
    assert ap.is_bot_author("Renovate Bot renovate@whitesourcesoftware.com")
    assert ap.is_bot_author("dotnet bot dotnet-bot@microsoft.com")


def test_is_bot_author_rejects_human_and_agent_authors():
    assert not ap.is_bot_author("Alice alice@anthropic.com")
    assert not ap.is_bot_author("GitHub Copilot copilot@github.com")
