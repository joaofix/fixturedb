"""Focused tests for agent repository/config detection logic."""

from pathlib import Path

from collection.agent_corpus import scan_cloned_repo_for_agent_configs
from collection.agent_detector import GitHubAgentFileChecker


def _make_repo(tmp_path: Path, repo_name: str = "owner__repo") -> Path:
    repo_root = tmp_path / "clones"
    repo_root.mkdir()
    repo_path = repo_root / repo_name
    repo_path.mkdir()
    return repo_path


def test_scan_cloned_repo_for_agent_configs_is_case_insensitive(tmp_path):
    repo_path = _make_repo(tmp_path)
    (repo_path / "CLAUDE.MD").write_text("# Claude instructions\n")

    assert scan_cloned_repo_for_agent_configs(repo_path) is True


def test_scan_cloned_repo_for_agent_configs_matches_copilot_wildcard(tmp_path):
    repo_path = _make_repo(tmp_path)
    (repo_path / ".copilot-SETUP.md").write_text("# Copilot\n")

    assert scan_cloned_repo_for_agent_configs(repo_path) is True


def test_scan_cloned_repo_for_agent_configs_matches_nested_directory(tmp_path):
    repo_path = _make_repo(tmp_path)
    nested = repo_path / "anthropic"
    nested.mkdir()
    (nested / "README.md").write_text("# Anthropic\n")

    assert scan_cloned_repo_for_agent_configs(repo_path) is True


def test_github_api_checker_recurses_one_level_for_nested_configs(monkeypatch):
    checker = GitHubAgentFileChecker()

    responses = {
        ("owner/repo", ""): [
            {"name": "docs", "path": "docs", "type": "dir"},
        ],
        ("owner/repo", "docs"): [
            {"name": "CLAUDE.MD", "path": "docs/CLAUDE.MD", "type": "file"},
        ],
    }

    def fake_get_repo_contents(full_repo_name, path="", ref="HEAD", timeout=5):
        return responses.get((full_repo_name, path), [])

    monkeypatch.setattr(checker, "_get_repo_contents", fake_get_repo_contents)

    has_files, found = checker.has_agent_config_files("owner/repo")

    assert has_files is True
    assert any("CLAUDE" in item.upper() for item in found)
