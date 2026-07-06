from pathlib import Path

from collection import agent_patterns as ap


def test_path_matches_pattern_case_insensitive():
    assert ap.path_matches_pattern(Path("README.md"), "readme.md")


def test_path_matches_pattern_glob():
    assert ap.path_matches_pattern(Path(".copilot-ABC.md"), ".copilot-*.md")
    assert ap.path_matches_pattern(Path("subdir/.copilot-xyz.md"), ".copilot-*.md")


def test_path_matches_pattern_dir_marker():
    p = Path("anthropic/config.yaml")
    assert ap.path_matches_pattern(p, "anthropic/")
    # should not match substring-only
    assert not ap.path_matches_pattern(Path("someanthropic/file"), "anthropic/")


def test_iter_exact_filename_patterns_excludes_globs_and_dirs():
    exact = ap.iter_exact_filename_patterns(ap.PAPER_AGENT_CONFIG_PATTERNS)
    assert "CLAUDE.md" in exact
    assert ".claude/" not in exact
    assert ".copilot-*.md" not in exact


def test_repo_contains_patterns_detects_files_and_dirs(tmp_path):
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    # file matching copilot exact name
    (repo / "copilot_instructions.md").write_text("x")
    # directory marker for anthropic
    (repo / "anthropic").mkdir()
    (repo / "anthropic" / "config.yaml").write_text("y")

    assert ap.repo_contains_patterns(repo, ap.PAPER_AGENT_CONFIG_PATTERNS)


def test_repo_contains_patterns_matches_lightweight_aliases(tmp_path):
    repo = tmp_path / "repo2"
    repo.mkdir()
    (repo / "claude.config").write_text("z")
    assert ap.repo_contains_patterns(repo, ap.LIGHTWEIGHT_AGENT_CONFIG_PATTERNS)


def test_repo_contains_patterns_returns_false_if_missing(tmp_path):
    assert not ap.repo_contains_patterns(
        tmp_path / "does-not-exist", ap.PAPER_AGENT_CONFIG_PATTERNS
    )


def test_repo_contains_patterns_returns_matched_pattern_string(tmp_path):
    """The matched pattern (e.g. the specific config filename) is returned,
    not just a bool -- validation_sampling.py surfaces it as detection_signal
    evidence for repo-detection review."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "CLAUDE.md").write_text("x")

    matched = ap.repo_contains_patterns(repo, ap.PAPER_AGENT_CONFIG_PATTERNS)

    assert matched == "CLAUDE.md"


def test_repo_contains_patterns_returns_none_if_missing(tmp_path):
    assert (
        ap.repo_contains_patterns(tmp_path / "does-not-exist", ap.PAPER_AGENT_CONFIG_PATTERNS)
        is None
    )


def test_iter_exact_filename_patterns_uniqueness():
    files = ap.iter_exact_filename_patterns(ap.LIGHTWEIGHT_AGENT_CONFIG_PATTERNS)
    # ensure there are no duplicates
    assert len(files) == len(set(files))
