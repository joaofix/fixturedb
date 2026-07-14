"""Tests for AgentFileScanner / AgentFileDetectionResult (collection/agent_signal_primitives.py).

Previously had zero test coverage, which is how two real bugs (mislabeled
"claude" patterns, and total_agent_files always computing to 0) went
undetected -- see the fixes in the same commit as this test file.
"""


from collection.agent_signal_primitives import (
    AgentFileDetectionResult,
    AgentFileScanner,
)


def test_total_agent_files_reflects_agents_found():
    """Regression test: total_agent_files used to be computed once in
    __post_init__, before scan_repository() ever populates agents_found --
    so it was permanently stuck at 0 regardless of what was actually found.
    It's now a property, computed on access."""
    result = AgentFileDetectionResult(repo_name="example/repo")
    assert result.total_agent_files == 0

    result.agents_found["claude"] = ["CLAUDE.md", ".claude"]
    assert result.total_agent_files == 2

    result.agents_found["cursor"] = [".cursorrules"]
    assert result.total_agent_files == 3


def test_scan_repository_detects_claude_config(tmp_path):
    """Regression test: AGENT_FILE_PATTERNS["claude"] used to contain
    Cursor's own file patterns (.cursorrules, .cursorignore, .cursor), not
    Claude's -- a repo with real Claude config files was never attributed
    to "claude" at all."""
    repo = tmp_path / "myorg__myrepo"
    repo.mkdir()
    (repo / "CLAUDE.md").write_text("# instructions")
    claude_dir = repo / ".claude"
    claude_dir.mkdir()
    (claude_dir / "settings.json").write_text("{}")

    scanner = AgentFileScanner(clones_dir=tmp_path)
    result = scanner.scan_repository("myorg__myrepo")

    assert "claude" in result.agents_found
    assert result.total_agent_files > 0


def test_scan_repository_no_agent_files(tmp_path):
    repo = tmp_path / "empty__repo"
    repo.mkdir()
    scanner = AgentFileScanner(clones_dir=tmp_path)
    result = scanner.scan_repository("empty__repo")
    assert result.agents_found == {}
    assert result.total_agent_files == 0


def test_scan_repository_recognizes_agents_outside_old_hardcoded_list(tmp_path):
    """Regression test: this scanner used to match against its own
    hardcoded ~9-agent AGENT_FILE_PATTERNS dict, out of sync with
    GitHubAgentFileChecker's ~60-agent LIGHTWEIGHT_AGENT_CONFIG_PATTERNS
    catalog used one class up in this same module for the pre-clone API
    check -- a repo with e.g. Windsurf's config file would pass that API
    pre-filter, then be silently rejected here in Tier2RepoMatcher's local
    re-scan (`if agent_files.total_agent_files <= 0: continue`), since
    Windsurf was never in the old hardcoded dict. Now both checks share one
    catalog, so this must be found."""
    repo = tmp_path / "myorg__myrepo"
    repo.mkdir()
    (repo / ".windsurfrules").write_text("rules")

    scanner = AgentFileScanner(clones_dir=tmp_path)
    result = scanner.scan_repository("myorg__myrepo")

    assert "windsurf" in result.agents_found
    assert result.total_agent_files > 0


def test_scan_repository_ignores_vendored_dependency_config(tmp_path):
    """Regression test: an agent-config-shaped file inside node_modules (a
    vendored dependency's own docs) must not count as this repo's own
    agent-config signal."""
    repo = tmp_path / "myorg__myrepo"
    vendor = repo / "node_modules" / "some-package"
    vendor.mkdir(parents=True)
    (vendor / "CLAUDE.md").write_text("vendor's own docs")

    scanner = AgentFileScanner(clones_dir=tmp_path)
    result = scanner.scan_repository("myorg__myrepo")

    assert result.agents_found == {}
    assert result.total_agent_files == 0
