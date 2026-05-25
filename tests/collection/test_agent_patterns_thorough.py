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
    for agent, patterns in mapping.items():
        for pattern in patterns:
            counter += 1
            name = make_match_name(pattern)
            # create each pattern in its own subdirectory to avoid collisions
            base = repo / f"unit_{counter}"
            base.mkdir(parents=True, exist_ok=True)
            if pattern.endswith("/"):
                (base / name).mkdir(parents=True, exist_ok=True)
                (base / "nested" / name).mkdir(parents=True, exist_ok=True)
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
