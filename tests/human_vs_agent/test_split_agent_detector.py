"""
Unit tests for FixtureDB split Phase 1A/1B.
"""

import tempfile
from pathlib import Path

import pytest

from collection.agent_detector import (
    AgentCommitVerificationResult,
    AgentCommitVerifier,
    AgentFileDetectionResult,
    AgentFileScanner,
)


class TestAgentFileDetectionResult:
    def test_total_agent_files_is_derived(self):
        result = AgentFileDetectionResult(
            repo_name="repo",
            agents_found={"claude": [".cursorrules"], "copilot": [".copilot"]},
        )

        assert result.total_agent_files == 2


class TestAgentFileScanner:
    def test_scan_repository_finds_agent_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            clones_dir = Path(tmpdir)
            repo_with_agent = clones_dir / "repo_with_agent"
            repo_with_agent.mkdir()
            (repo_with_agent / ".cursorrules").touch()

            scanner = AgentFileScanner(clones_dir=clones_dir)
            result = scanner.scan_repository("repo_with_agent")

            assert result.repo_name == "repo_with_agent"
            assert result.agents_found

    def test_scan_all_filters_empty_repositories(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            clones_dir = Path(tmpdir)
            repo_with_agent = clones_dir / "repo_with_agent"
            repo_with_agent.mkdir()
            (repo_with_agent / ".cursorrules").touch()

            repo_without_agent = clones_dir / "repo_without_agent"
            repo_without_agent.mkdir()

            scanner = AgentFileScanner(clones_dir=clones_dir)
            results = scanner.scan_all(show_progress=False)

            assert isinstance(results, dict)
            assert "repo_without_agent" not in results

    def test_get_summary_reports_counts(self):
        scanner = AgentFileScanner(clones_dir=Path(tempfile.mkdtemp()))
        results = {
            "repo_with_agent": AgentFileDetectionResult(
                repo_name="repo_with_agent",
                agents_found={
                    "claude": [".cursorrules"],
                    "copilot": [".copilot"],
                },
            )
        }

        summary = scanner.get_summary(results)

        assert summary["total_repositories_with_agents"] == 1
        assert summary["total_agent_files_found"] == 2
        assert summary["repositories_with_multiple_agents"] == 1


class TestAgentCommitVerificationResult:
    def test_total_agent_commits_is_derived(self):
        result = AgentCommitVerificationResult(
            repo_name="repo",
            agent_commits={"abc123": "claude", "def456": "copilot"},
        )

        assert result.total_agent_commits == 2


class TestAgentCommitVerifier:
    def test_parse_commits_and_detect_agents(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            verifier = AgentCommitVerifier(clones_dir=Path(tmpdir))

            git_output = (
                "abc123\n"
                "2023-01-01 10:00:00 +0000\n"
                "GitHub Actions\n"
                "bot@example.com\n"
                "Fix tests\n"
                "Co-authored-by: Claude <claude@example.com>\n"
                "---END_COMMIT---\n"
                "def456\n"
                "2023-01-02 10:00:00 +0000\n"
                "Human Dev\n"
                "human@example.com\n"
                "Regular commit\n"
                "---END_COMMIT---\n"
            )

            commits = verifier._parse_commits(git_output)
            assert len(commits) == 2
            assert commits[0]["sha"] == "abc123"
            assert verifier._detect_agent_in_commit(commits[0]) == "claude"
            assert verifier._detect_agent_in_commit(commits[1]) is None

    def test_get_verification_summary_reports_totals(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            verifier = AgentCommitVerifier(clones_dir=Path(tmpdir))
            results = {
                "repo_with_agent": AgentCommitVerificationResult(
                    repo_name="repo_with_agent",
                    agent_commits={"abc123": "claude", "def456": "copilot"},
                )
            }

            summary = verifier.get_verification_summary(results)

            assert summary["total_repositories_verified"] == 1
            assert summary["total_agent_commits_found"] == 2
            assert summary["agent_commit_counts"]["claude"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
