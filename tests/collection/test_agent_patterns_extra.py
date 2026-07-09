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


def test_path_matches_pattern_multi_segment_dir_marker():
    """Regression: a dir-marker pattern with more than one path segment
    (e.g. ".github/instructions/", copilot's real custom-instructions
    convention) previously could never match anything -- the code stripped
    only the trailing "/" and compared the whole remaining string
    (".github/instructions") against a SINGLE path component, but
    Path.parts never contains "/", so the comparison was always False."""
    p = Path(".github/instructions/setup.md")
    assert ap.path_matches_pattern(p, ".github/instructions/", is_dir=True)
    assert ap.path_matches_pattern(
        Path(".github/instructions"), ".github/instructions/", is_dir=True
    )
    # nested deeper still matches (contiguous run, not required at root)
    assert ap.path_matches_pattern(
        Path("sub/.github/instructions/x.md"), ".github/instructions/", is_dir=True
    )
    # a single matching segment out of order/incomplete must not match
    assert not ap.path_matches_pattern(
        Path("instructions/.github/x.md"), ".github/instructions/", is_dir=True
    )
    assert not ap.path_matches_pattern(
        Path(".github/other/x.md"), ".github/instructions/", is_dir=True
    )


def test_path_matches_pattern_dir_marker_rejects_plain_file():
    """Regression test: a dir-marker pattern (e.g. ".claude/") must not
    match a plain FILE that merely happens to share the directory's name --
    only a real directory entry should count. is_dir defaults to True (old
    behavior, for callers with no filesystem/API type info), so this must
    be explicitly passed as False to exercise the fix."""
    assert ap.path_matches_pattern(Path(".claude"), ".claude/", is_dir=True)
    assert not ap.path_matches_pattern(Path(".claude"), ".claude/", is_dir=False)


def test_repo_contains_patterns_detects_multi_segment_dir_marker(tmp_path):
    """End-to-end regression for the .github/instructions/ catalog entry
    (copilot's real custom-instructions convention, in PAPER_AGENT_CONFIG_PATTERNS
    since copilot is in paper_scope) -- previously silently unmatchable."""
    repo = tmp_path / "repo"
    (repo / ".github" / "instructions").mkdir(parents=True)
    (repo / ".github" / "instructions" / "setup.md").write_text("x")

    matched = ap.repo_contains_patterns(repo, {"copilot": [".github/instructions/"]})

    assert matched == ".github/instructions/"


def test_repo_contains_patterns_dir_marker_rejects_plain_file(tmp_path):
    """Regression test (end-to-end via the real filesystem): a plain file
    named ".claude" (not a directory -- .claude/ has no bare-name sibling
    pattern in the catalog, unlike .cursor) must not satisfy the ".claude/"
    pattern."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".claude").write_text("just a file, not a directory")
    assert ap.repo_contains_patterns(repo, ap.PAPER_AGENT_CONFIG_PATTERNS) is None

    (repo / ".claude").unlink()
    (repo / ".claude").mkdir()
    assert ap.repo_contains_patterns(repo, ap.PAPER_AGENT_CONFIG_PATTERNS) == ".claude/"


def test_repo_contains_patterns_ignores_vendored_dependency_config(tmp_path):
    """Regression test: an agent-config-shaped file inside node_modules (a
    vendored dependency's own docs, unrelated to whether *this* repo used
    the agent) must not count, and .git internals must not be walked into
    either."""
    repo = tmp_path / "repo"
    vendor = repo / "node_modules" / "some-package"
    vendor.mkdir(parents=True)
    (vendor / "CLAUDE.md").write_text("vendor's own docs")

    assert ap.repo_contains_patterns(repo, ap.PAPER_AGENT_CONFIG_PATTERNS) is None

    # A real, top-level CLAUDE.md in the same repo must still be found.
    (repo / "CLAUDE.md").write_text("this repo's own instructions")
    assert ap.repo_contains_patterns(repo, ap.PAPER_AGENT_CONFIG_PATTERNS) == "CLAUDE.md"


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
    # directory marker for claude's .anthropic/ (dotfile convention)
    (repo / ".anthropic").mkdir()
    (repo / ".anthropic" / "config.yaml").write_text("y")

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
