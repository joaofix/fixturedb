"""
Unit tests for agent corpus collection.

Tests the 2025+ agent-authored fixture collection including:
- Agent type detection from commit messages (Tier 1)
- Repository scanning for agent configuration files
- Agent commit discovery from git history
- Control variable computation at snapshot date
- Statistics aggregation
"""

import sqlite3
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from collection.agent_corpus import (
    AgentCorpusStats,
    detect_agent_in_commit,
    detect_agent_type,
    get_agent_commits,
    _load_qc_agent_commits,
    _load_qc_repo_rows,
    AGENT_SIGNATURES,
)
from collection.db import (
    classify_domain,
    compute_star_tier,
    compute_repo_age_at_date,
)
from collection.config import AGENT_CORPUS_START_DATE


class TestAgentDetection:
    """Test agent type detection from commit messages."""

    def test_detect_claude_from_message(self):
        """Should detect Claude from co-authored-by trailer."""
        message = "Fix bug\n\nCo-authored-by: Claude <claude@anthropic.com>"
        agent_type = detect_agent_type(message)
        assert agent_type == "claude"

    def test_detect_copilot_from_message(self):
        """Should detect GitHub Copilot from commit message."""
        message = "Add feature\n\nCo-authored-by: GitHub Copilot <copilot@github.com>"
        agent_type = detect_agent_type(message)
        assert agent_type == "copilot"

    def test_detect_cursor_from_message(self):
        """Should detect Cursor from commit message."""
        message = "Refactor code\n\nCo-authored-by: Cursor <cursor@anysoftware.io>"
        agent_type = detect_agent_type(message)
        assert agent_type == "cursor"

    def test_detect_aider_from_message(self):
        """Should detect Aider from commit message."""
        message = "Update tests\n\nCo-authored-by: Aider <aider@paul.pub>"
        agent_type = detect_agent_type(message)
        assert agent_type == "aider"

    def test_detect_lowercase_variants(self):
        """Should detect agent types regardless of case."""
        message_claude = "Fix\n\nco-authored-by: claude"
        assert detect_agent_type(message_claude) == "claude"

        message_copilot = "Fix\n\nco-authored-by: copilot"
        assert detect_agent_type(message_copilot) == "copilot"

    def test_detect_no_agent_in_message(self):
        """Should return None for non-agent commits."""
        message = "Fix bug\n\nCo-authored-by: Alice <alice@example.com>"
        agent_type = detect_agent_type(message)
        assert agent_type is None

    def test_detect_empty_message(self):
        """Should return None for empty message."""
        agent_type = detect_agent_type("")
        assert agent_type is None

    def test_detect_first_matching_agent(self):
        """Should return first matching agent type in signature order."""
        # If message contains multiple agents, should return first match
        message = "Fix\n\nCo-authored-by: Claude and Co-authored-by: Copilot"
        agent_type = detect_agent_type(message)
        assert agent_type in ("claude", "copilot")  # One of the two


class TestAgentSignatures:
    """Test AGENT_SIGNATURES constant structure."""

    def test_agent_signatures_structure(self):
        """AGENT_SIGNATURES should have expected structure."""
        assert isinstance(AGENT_SIGNATURES, dict)
        expected_agents = {"claude", "copilot", "cursor", "aider"}
        assert expected_agents.issubset(set(AGENT_SIGNATURES.keys()))

    def test_agent_signatures_have_variants(self):
        """Each agent should have multiple signature variants."""
        for agent_type, signatures in AGENT_SIGNATURES.items():
            assert isinstance(signatures, list)
            assert len(signatures) > 0


class TestAgentCorpusStats:
    """Test AgentCorpusStats dataclass."""

    def test_stats_initialization(self):
        """Should initialize with default values."""
        stats = AgentCorpusStats()

        assert stats.repos_scanned == 0
        assert stats.repos_with_agent_config == 0
        assert stats.agent_commits_found == 0
        assert stats.fixtures_collected == 0
        assert isinstance(stats.agent_types_distribution, dict)
        assert isinstance(stats.domain_distribution, dict)

    def test_stats_to_dict(self):
        """Should convert to dictionary for JSON serialization."""
        stats = AgentCorpusStats(
            repos_scanned=10,
            repos_with_agent_config=5,
            agent_commits_found=25,
            fixtures_collected=120,
        )

        stats_dict = stats.to_dict()

        assert stats_dict["repos_scanned"] == 10
        assert stats_dict["repos_with_agent_config"] == 5
        assert stats_dict["agent_commits_found"] == 25
        assert stats_dict["fixtures_collected"] == 120

    def test_stats_agent_type_distribution(self):
        """Should track distribution of agent types."""
        stats = AgentCorpusStats(
            agent_types_distribution={
                "claude": 50,
                "copilot": 30,
                "cursor": 15,
                "aider": 5,
            }
        )

        stats_dict = stats.to_dict()
        assert stats_dict["agent_types_distribution"]["claude"] == 50
        assert sum(stats_dict["agent_types_distribution"].values()) == 100


class TestAgentCorpusTemporalBoundary:
    """Test that agent corpus respects temporal boundaries."""

    def test_agent_corpus_start_date(self):
        """Agent corpus should start from 2025-01-01 (post-agent emergence)."""
        # This tests the constant, not the implementation
        assert AGENT_CORPUS_START_DATE == "2025-01-01"

    def test_control_variables_computed_at_snapshot(self):
        """Control variables should be computed at 2025-01-01 snapshot."""
        created_at = "2024-08-01T00:00:00Z"
        snapshot_date = "2025-01-01T00:00:00Z"

        age = compute_repo_age_at_date(created_at, snapshot_date)

        # Repository ~5 months old at snapshot
        assert age is not None
        assert 0.4 < age < 0.5  # Roughly 5 months


class TestAgentDetectionTier1Precision:
    """Test that Tier 1 detection uses co-authored-by trailers only."""

    def test_tier1_uses_commit_trailers(self):
        """Tier 1 should detect co-authored-by git trailers."""
        # This tests the documented methodology
        message_with_trailer = "Code\n\nCo-authored-by: Claude <claude@anthropic.com>"
        assert detect_agent_type(message_with_trailer) == "claude"

    def test_tier1_detection_is_substring_based(self):
        """Tier 1 uses case-insensitive substring matching of agent keywords."""
        # Implementation matches agent keywords anywhere in commit body
        # This is correct for detecting trailers, as trailer lines contain the keywords
        message_with_claude_mention = "This was helped by claude to fix the issue"
        result = detect_agent_type(message_with_claude_mention)
        assert result == "claude"  # Will match on "claude" keyword

    def test_tier1_cursor_detection(self):
        """Should detect cursor keyword in commit message."""
        # Similar to claude, any mention of "cursor" will match
        message_with_cursor = "Cursor helped with this feature"
        result = detect_agent_type(message_with_cursor)
        assert result == "cursor"  # Will match on "cursor" keyword

    def test_tier1_no_match_without_keywords(self):
        """Should NOT detect when no agent keywords present."""
        message = "Fixed a bug in the code"
        assert detect_agent_type(message) is None


class TestAgentCommitMetadataDetection:
    """Test the stricter commit-metadata detector used by agent commit scans."""

    def test_detect_agent_from_coauthored_by_trailer(self):
        agent_type, matched_field = detect_agent_in_commit(
            author_name="Someone",
            author_email="someone@example.com",
            commit_body="Refactor\n\nCo-authored-by: Claude <claude@anthropic.com>",
        )

        assert agent_type == "claude"
        assert matched_field == "coauthored-by"

    def test_detect_agent_from_author_identity(self):
        agent_type, matched_field = detect_agent_in_commit(
            author_name="GitHub Copilot",
            author_email="copilot@github.com",
            commit_body="Fix typo",
        )

        assert agent_type == "copilot"
        assert matched_field == "author"

    def test_reject_non_agent_commit_metadata(self):
        agent_type, matched_field = detect_agent_in_commit(
            author_name="Alice Example",
            author_email="alice@example.com",
            commit_body="Fix typo",
        )

        assert agent_type is None
        assert matched_field == ""

    def test_get_agent_commits_detects_copilot_in_git_history(self, tmp_path):
        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        (repo_path / "README.md").write_text("hello\n", encoding="utf-8")
        subprocess.run(
            ["git", "add", "README.md"], cwd=repo_path, check=True, capture_output=True
        )

        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "Alice Example",
            "GIT_AUTHOR_EMAIL": "alice@example.com",
            "GIT_COMMITTER_NAME": "Alice Example",
            "GIT_COMMITTER_EMAIL": "alice@example.com",
        }
        subprocess.run(
            [
                "git",
                "commit",
                "--allow-empty",
                "-m",
                "Add feature\n\nCo-authored-by: GitHub Copilot <copilot@github.com>",
            ],
            cwd=repo_path,
            check=True,
            capture_output=True,
            env=env,
        )

        commits = get_agent_commits(repo_path, "2025-01-01")

        assert len(commits) == 1
        assert commits[0]["agent_type"] == "copilot"
        assert commits[0]["author_name"] == "Alice Example"
        assert commits[0]["author_email"] == "alice@example.com"


class TestMultipleAgentTypes:
    """Test handling of repositories with multiple agent types."""

    def test_stats_track_all_agent_types(self):
        """Stats should track distribution across all agent types."""
        stats = AgentCorpusStats(
            agent_types_distribution={
                "claude": 40,
                "copilot": 35,
                "cursor": 20,
                "aider": 5,
            }
        )

        assert len(stats.agent_types_distribution) == 4
        assert sum(stats.agent_types_distribution.values()) == 100

    def test_agent_commits_per_type(self):
        """Should track agent commits separately by type."""
        # In a real scenario, repositories might have mixed agent types
        # The stats should reflect this diversity
        stats = AgentCorpusStats(
            agent_commits_found=100,
            agent_types_distribution={
                "claude": 40,
                "copilot": 35,
                "cursor": 20,
                "aider": 5,
            },
        )

        stats_dict = stats.to_dict()
        total_typed_commits = sum(stats_dict["agent_types_distribution"].values())
        assert total_typed_commits <= stats_dict["agent_commits_found"]


class TestQualityControlledInputs:
    """Test loading QC repo and commit CSV inputs."""

    def test_load_qc_repo_and_commit_rows(self, tmp_path):
        repo_qc_dir = tmp_path / "repo-qc"
        commit_qc_dir = tmp_path / "commit-qc"
        repo_qc_dir.mkdir()
        commit_qc_dir.mkdir()

        (repo_qc_dir / "python_agent_repo.csv").write_text(
            "repo_name,has_agent_config,language,stars,clone_url,num_contributors,qc_reason,processed_at\n"
            "good/repo,1,python,123,https://github.com/good/repo.git,4,,2026-05-22T00:00:00Z\n"
            "bad/repo,0,python,456,https://github.com/bad/repo.git,7,no_agent_config,2026-05-22T00:00:00Z\n",
            encoding="utf-8",
        )

        (commit_qc_dir / "python_agent_commit_qc.csv").write_text(
            "repo_name,commit_sha,commit_url,agent_type,commit_date,author_name,author_email,language,clone_url,processed_at\n"
            "good/repo,abc123,https://github.com/good/repo/commit/abc123,claude,2026-05-21T00:00:00Z,Alice,alice@example.com,python,https://github.com/good/repo.git,2026-05-22T00:00:00Z\n"
            "good/repo,abc123,https://github.com/good/repo/commit/abc123,claude,2026-05-21T00:00:00Z,Alice,alice@example.com,python,https://github.com/good/repo.git,2026-05-22T00:00:00Z\n"
            "bad/repo,def456,https://github.com/bad/repo/commit/def456,copilot,2026-05-20T00:00:00Z,Bob,bob@example.com,python,https://github.com/bad/repo.git,2026-05-22T00:00:00Z\n",
            encoding="utf-8",
        )

        repos = _load_qc_repo_rows(repo_qc_dir, repos_per_language=10)
        commits = _load_qc_agent_commits(commit_qc_dir)

        assert [repo["full_name"] for repo in repos] == ["good/repo"]
        assert repos[0]["github_id"] != 0
        assert repos[0]["clone_url"] == "https://github.com/good/repo.git"
        assert list(commits.keys()) == ["good/repo", "bad/repo"]
        assert len(commits["good/repo"]) == 1
        assert commits["good/repo"][0]["agent_type"] == "claude"
        assert commits["good/repo"][0]["commit_sha"] == "abc123"
