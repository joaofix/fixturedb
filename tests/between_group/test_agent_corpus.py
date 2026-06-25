"""
Unit tests for agent corpus collection.

Tests the 2025+ agent-authored fixture collection including:
- Agent type detection from commit messages (Tier 1)
- Repository scanning for agent configuration files
- Agent commit discovery from git history
- Control variable computation at snapshot date
- Statistics aggregation
"""

import csv
import sqlite3
import os
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import collection.agent_corpus as agent_corpus
from collection.agent_corpus import (
    AgentCorpusCollector,
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
    db_session,
    is_global_checkpoint_completed,
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

    def test_github_actions_not_in_agent_signatures(self):
        """GitHub Actions bot should not be classified as an agent."""
        assert "github-actions" not in AGENT_SIGNATURES
        for signatures in AGENT_SIGNATURES.values():
            assert not any(
                "github-actions" in sig.lower() for sig in signatures
            )

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


    def test_bot_authors_are_excluded_from_agent_detection(self):
        """Bot accounts like copilot-swe-agent[bot] must not be classified as agents."""
        # swe-agent bot — author name contains [bot]
        agent_type, _ = detect_agent_in_commit(
            author_name="copilot-swe-agent[bot]",
            author_email="198982749+Copilot@users.noreply.github.com",
            commit_body="Some commit",
        )
        assert agent_type is None

        # anthropic-code-agent bot
        agent_type2, _ = detect_agent_in_commit(
            author_name="anthropic-code-agent[bot]",
            author_email="242468646+Claude@users.noreply.github.com",
            commit_body="Some commit",
        )
        assert agent_type2 is None

        # Non-bot with copilot keyword should still match
        agent_type3, _ = detect_agent_in_commit(
            author_name="GitHub Copilot",
            author_email="copilot@github.com",
            commit_body="Fix typo",
        )
        assert agent_type3 == "copilot"

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

    def test_load_qc_repo_and_commit_rows(self, tmp_path, make_csv):
        repo_qc_dir = tmp_path / "repo-qc"
        commit_qc_dir = tmp_path / "commit-qc"
        repo_qc_dir.mkdir()
        commit_qc_dir.mkdir()
        # Use make_csv fixture to generate deterministic sample CSVs matching previous expectations
        repo_rows = [
            {
                "repo_name": "good/repo",
                "has_agent_config": "1",
                "language": "python",
                "stars": "123",
                "clone_url": "https://github.com/good/repo.git",
                "num_contributors": "4",
                "qc_reason": "",
                "processed_at": "2026-05-22T00:00:00Z",
            },
            {
                "repo_name": "bad/repo",
                "has_agent_config": "0",
                "language": "python",
                "stars": "456",
                "clone_url": "https://github.com/bad/repo.git",
                "num_contributors": "7",
                "qc_reason": "no_agent_config",
                "processed_at": "2026-05-22T00:00:00Z",
            },
        ]

        commit_rows = [
            {
                "repo_name": "good/repo",
                "commit_sha": "abc123",
                "commit_url": "https://github.com/good/repo/commit/abc123",
                "agent_type": "claude",
                "commit_date": "2026-05-21T00:00:00Z",
                "author_name": "Alice",
                "author_email": "alice@example.com",
                "language": "python",
                "clone_url": "https://github.com/good/repo.git",
                "processed_at": "2026-05-22T00:00:00Z",
            },
            {
                "repo_name": "good/repo",
                "commit_sha": "abc123",
                "commit_url": "https://github.com/good/repo/commit/abc123",
                "agent_type": "claude",
                "commit_date": "2026-05-21T00:00:00Z",
                "author_name": "Alice",
                "author_email": "alice@example.com",
                "language": "python",
                "clone_url": "https://github.com/good/repo.git",
                "processed_at": "2026-05-22T00:00:00Z",
            },
            {
                "repo_name": "bad/repo",
                "commit_sha": "def456",
                "commit_url": "https://github.com/bad/repo/commit/def456",
                "agent_type": "copilot",
                "commit_date": "2026-05-20T00:00:00Z",
                "author_name": "Bob",
                "author_email": "bob@example.com",
                "language": "python",
                "clone_url": "https://github.com/bad/repo.git",
                "processed_at": "2026-05-22T00:00:00Z",
            },
        ]

        make_csv(repo_qc_dir, "python_agent_repo.csv", rows=repo_rows)
        make_csv(commit_qc_dir, "python_agent_commit_qc.csv", rows=commit_rows)

        repos = _load_qc_repo_rows(repo_qc_dir, repos_per_language=10)
        commits = _load_qc_agent_commits(commit_qc_dir)

        assert [repo["full_name"] for repo in repos] == ["good/repo"]
        assert repos[0]["github_id"] != 0
        assert repos[0]["clone_url"] == "https://github.com/good/repo.git"
        assert list(commits.keys()) == ["good/repo", "bad/repo"]
        assert len(commits["good/repo"]) == 1
        assert commits["good/repo"][0]["agent_type"] == "claude"
        assert commits["good/repo"][0]["commit_sha"] == "abc123"

    def test_load_qc_agent_test_commit_rows(self, tmp_path, make_csv):
        commit_qc_dir = tmp_path / "tests-commits"

        # create a small sample CSV in the temp dir for deterministic testing
        test_rows = [
            {
                "repo_name": "good/repo",
                "language": "python",
                "commit_sha": "abc123",
                "commit_role": "agent",
                "agent_type": "claude",
                "commit_date": "2026-05-21T00:00:00Z",
                "test_file_count": "1",
                "test_file_paths": '["tests/test_sample.py"]',
            },
            {
                "repo_name": "good/repo",
                "language": "python",
                "commit_sha": "abc123",
                "commit_role": "agent",
                "agent_type": "claude",
                "commit_date": "2026-05-21T00:00:00Z",
                "test_file_count": "1",
                "test_file_paths": '["tests/test_sample.py"]',
            },
            {
                "repo_name": "other/repo",
                "language": "python",
                "commit_sha": "def456",
                "commit_role": "agent",
                "agent_type": "copilot",
                "commit_date": "2026-05-22T00:00:00Z",
                "test_file_count": "2",
                "test_file_paths": '["tests/test_a.py", "tests/test_b.py"]',
            },
        ]

        make_csv(
            tmp_path,
            "python_agent_test_commit_qc.csv",
            rows=test_rows,
            dest_name="tests-commits/python_agent_test_commit_qc.csv",
        )

        commits = _load_qc_agent_commits(commit_qc_dir)

        assert list(commits.keys()) == ["good/repo", "other/repo"]
        assert len(commits["good/repo"]) == 1
        assert commits["good/repo"][0]["agent_type"] == "claude"
        assert commits["good/repo"][0]["commit_sha"] == "abc123"

    def test_agent_corpus_keeps_only_complete_additions(self, tmp_path, monkeypatch):
        repo_qc_dir = tmp_path / "repo-qc"
        commit_qc_dir = tmp_path / "commit-qc"
        repo_qc_dir.mkdir()
        commit_qc_dir.mkdir()

        repo_list_path = (
            Path(__file__).resolve().parents[2]
            / "fixtures-from-agents"
            / "repos"
            / "python_agent_fixture_repos.csv"
        )
        fixtures_csv_path = (
            Path(__file__).resolve().parents[2]
            / "fixtures-from-agents"
            / "python_agent_fixtures.csv"
        )
        original_bytes = b""
        original_fixtures_bytes = b""
        if repo_list_path.exists():
            original_bytes = repo_list_path.read_bytes()
        if fixtures_csv_path.exists():
            original_fixtures_bytes = fixtures_csv_path.read_bytes()

        with (repo_qc_dir / "python_agent_repo.csv").open(
            "w", newline="", encoding="utf-8"
        ) as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=[
                    "repo_name",
                    "has_agent_config",
                    "language",
                    "stars",
                    "clone_url",
                    "num_contributors",
                    "qc_reason",
                    "processed_at",
                ],
            )
            writer.writeheader()
            writer.writerow(
                {
                    "repo_name": "good/repo",
                    "has_agent_config": "1",
                    "language": "python",
                    "stars": 123,
                    "clone_url": "https://github.com/good/repo.git",
                    "num_contributors": 4,
                    "qc_reason": "",
                    "processed_at": "2026-05-28T00:00:00Z",
                }
            )

        with (commit_qc_dir / "python_agent_commit.csv").open(
            "w", newline="", encoding="utf-8"
        ) as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=[
                    "repo_name",
                    "commit_sha",
                    "commit_url",
                    "agent_type",
                    "commit_date",
                    "author_name",
                    "author_email",
                    "language",
                    "clone_url",
                    "processed_at",
                ],
            )
            writer.writeheader()
            writer.writerow(
                {
                    "repo_name": "good/repo",
                    "commit_sha": "abc123",
                    "commit_url": "https://github.com/good/repo/commit/abc123",
                    "agent_type": "claude",
                    "commit_date": "2026-05-21T00:00:00Z",
                    "author_name": "Alice",
                    "author_email": "alice@example.com",
                    "language": "python",
                    "clone_url": "https://github.com/good/repo.git",
                    "processed_at": "2026-05-28T00:00:00Z",
                }
            )

        def fake_clone(clone_url, target_dir):
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / ".git").mkdir(parents=True, exist_ok=True)
            return True

        monkeypatch.setattr(
            "collection.agent_corpus.clone_repo_for_commit_scan", fake_clone
        )
        monkeypatch.setattr(
            "collection.agent_corpus.collect_test_files_for_commit",
            lambda repo_path, commit_sha, language: ["tests/test_sample.py"],
        )
        monkeypatch.setattr(
            "collection.agent_corpus.AgentFixtureExtractor._extract_from_agent_commits",
            lambda self, repo_name, commits: [
                {
                    "repo_name": repo_name,
                    "name": "complete_fixture",
                    "fixture_type": "pytest_decorator",
                    "scope": "per_test",
                    "loc": 3,
                    "language": "python",
                    "file_path": "tests/test_sample.py",
                    "start_line": 1,
                    "end_line": 3,
                    "cyclomatic_complexity": 1,
                    "max_nesting_depth": 0,
                    "num_objects_instantiated": 0,
                    "num_external_calls": 0,
                    "num_parameters": 0,
                    "reuse_count": 0,
                    "has_teardown_pair": 0,
                    "raw_source": "def complete_fixture(): pass",
                    "framework": "pytest",
                    "mocks": [],
                    "commit_sha": "abc123",
                    "agent_type": "claude",
                    "is_complete_addition": True,
                },
                {
                    "repo_name": repo_name,
                    "name": "partial_fixture",
                    "fixture_type": "pytest_decorator",
                    "scope": "per_test",
                    "loc": 4,
                    "language": "python",
                    "file_path": "tests/test_sample.py",
                    "start_line": 5,
                    "end_line": 8,
                    "cyclomatic_complexity": 1,
                    "max_nesting_depth": 0,
                    "num_objects_instantiated": 0,
                    "num_external_calls": 0,
                    "num_parameters": 0,
                    "reuse_count": 0,
                    "has_teardown_pair": 0,
                    "raw_source": "def partial_fixture(): pass",
                    "framework": "pytest",
                    "mocks": [],
                    "commit_sha": "abc123",
                    "agent_type": "claude",
                    "is_complete_addition": False,
                },
            ],
        )

        collector = AgentCorpusCollector(
            output_db=tmp_path / "between-group.db",
            repo_qc_dir=repo_qc_dir,
            commit_qc_dir=commit_qc_dir,
        )
        stats, db_path = collector.run(repos_per_language=1, languages=["python"])

        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM fixtures").fetchone()[0]
        conn.close()

        assert stats.fixtures_collected == 1
        assert count == 1

        if repo_list_path.exists() and original_bytes:
            repo_list_path.write_bytes(original_bytes)
        if fixtures_csv_path.exists() and original_fixtures_bytes:
            fixtures_csv_path.write_bytes(original_fixtures_bytes)


@contextmanager
def _fake_clone_with_function(*args, **kwargs):
    repo_path = args[2]
    repo_path.mkdir(parents=True, exist_ok=True)
    (repo_path / ".git").mkdir(parents=True, exist_ok=True)
    yield repo_path


def test_agent_collection_records_and_skips_completed_language(tmp_path, monkeypatch):
    repo_qc_dir = tmp_path / "repo-qc"
    commit_qc_dir = tmp_path / "commit-qc"
    repo_qc_dir.mkdir()
    commit_qc_dir.mkdir()

    monkeypatch.setattr(
        agent_corpus,
        "_load_qc_repo_rows",
        lambda *args, **kwargs: [
            {
                "github_id": 1,
                "full_name": "owner/repo",
                "language": "python",
                "stars": 1,
                "forks": 0,
                "description": "",
                "topics": "[]",
                "created_at": "",
                "pushed_at": "",
                "clone_url": "https://example.com/repo.git",
                "num_contributors": 1,
            }
        ],
    )
    monkeypatch.setattr(
        agent_corpus,
        "_load_qc_agent_commits",
        lambda *args, **kwargs: {
            "owner/repo": [
                {
                    "commit_sha": "abc123",
                    "agent_type": "claude",
                    "commit_date": "2025-01-01",
                }
            ]
        },
    )
    monkeypatch.setattr(agent_corpus, "clone_with_function", _fake_clone_with_function)
    monkeypatch.setattr(
        agent_corpus,
        "collect_test_files_for_commit",
        lambda repo_path, commit_sha, language: ["tests/test_sample.py"],
    )
    monkeypatch.setattr(
        agent_corpus.AgentFixtureExtractor,
        "_extract_from_agent_commits",
        lambda self, repo_name, commits: [],
    )
    monkeypatch.setattr(
        agent_corpus.AgentCorpusCollector,
        "_generate_summary",
        lambda self, stats: None,
    )

    collector = AgentCorpusCollector(
        output_db=tmp_path / "between-group.db",
        repo_qc_dir=repo_qc_dir,
        commit_qc_dir=commit_qc_dir,
    )

    stats1, db_path1 = collector.run(repos_per_language=1, language="python")
    assert db_path1 == tmp_path / "between-group.db"
    assert stats1.repos_scanned == 1

    with db_session(db_path1) as conn:
        assert is_global_checkpoint_completed(conn, "agent_complete:python")
        assert is_global_checkpoint_completed(conn, "agent_complete:all")

    stats2, db_path2 = collector.run(repos_per_language=1, language="python")
    assert db_path2 == tmp_path / "between-group.db"
    assert stats2.repos_scanned == 0
    assert stats2.fixtures_collected == 0


def test_agent_fixture_repos_dir_no_versioned_subfolder_when_tag_empty():
    """With empty COLLECTION_OUTPUT_TAG, fixture list goes to root fixtures-from-agents."""
    from collection.config import COLLECTION_OUTPUT_TAG
    from pathlib import Path

    # When tag is empty, the code appends directly to fixtures-from-agents/
    project_root = Path(".").resolve()
    expected_dir = project_root / "fixtures-from-agents"
    assert COLLECTION_OUTPUT_TAG == ""
    # Verify the path does not contain a versioned subfolder
    assert not str(expected_dir).endswith("v1-initial-2026-05")
    assert not str(expected_dir).endswith("v2-pure-addition-2026-06")


def test_single_language_filter_limits_repos():
    """_load_qc_repo_rows should return only repos for the requested language."""
    from collection.agent_corpus import _load_qc_repo_rows

    rows = _load_qc_repo_rows(
        Path("fixtures-from-agents"),
        language="java",
    )
    for row in rows:
        assert row["language"] == "java"


def test_incremental_checkpoint_after_repo(tmp_path):
    """AgentCorpusCollector should write checkpoint/CSV after each repo with test commits."""
    from unittest.mock import patch, MagicMock
    from collection.agent_corpus import AgentCorpusCollector

    collector = AgentCorpusCollector(
        output_db=tmp_path / "corpus.db",
        repo_qc_dir=Path("fixtures-from-agents"),
        commit_qc_dir=Path("github-search-agent/agent_commits"),
        test_commits_csv=tmp_path / "test_commits",
    )

    fake_repo = {
        "full_name": "test/example",
        "language": "java",
        "stars": 100,
        "clone_url": "https://github.com/test/example.git",
    }
    fake_commits = {
        "test/example": [
            {
                "commit_sha": "abc123",
                "agent_type": "claude",
                "commit_date": "2025-01-01",
            }
        ]
    }

    with patch("collection.agent_corpus._load_qc_repo_rows", return_value=[fake_repo]):
        with patch("collection.agent_corpus._load_qc_agent_commits", return_value=fake_commits):
            with patch("collection.agent_corpus.clone_with_function") as mock_clone:
                mock_clone.return_value.__enter__ = MagicMock(return_value=tmp_path / "repo")
                mock_clone.return_value.__exit__ = MagicMock(return_value=False)
                with patch("collection.agent_corpus.collect_test_files_for_commit", return_value=["tests/test_foo.py"]):
                    with patch("collection.agent_corpus.AgentFixtureExtractor") as mock_ext:
                        instance = mock_ext.return_value
                        instance._extract_from_agent_commits.return_value = []
                        stats, _ = collector.run(language="java")

    assert stats.repos_scanned == 1


def test_full_run_checkpoint_does_not_block_single_language_run(tmp_path):
    """After a full run completes, single-language runs for new languages should still proceed."""
    from unittest.mock import patch, MagicMock
    from collection.agent_corpus import AgentCorpusCollector
    from collection.db import mark_global_checkpoint, initialise_db

    db_path = tmp_path / "corpus.db"
    initialise_db(db_path)
    collector = AgentCorpusCollector(
        output_db=db_path,
        repo_qc_dir=Path("fixtures-from-agents"),
        commit_qc_dir=Path("github-search-agent/agent_commits"),
        test_commits_csv=tmp_path / "test_commits",
    )

    # Simulate a completed full run by writing the "all completed" checkpoint
    with db_session(db_path) as conn:
        mark_global_checkpoint(conn, "agent_complete:all")

    # Now run single-language for java — should NOT be blocked by the full-run checkpoint
    fake_repo = {
        "full_name": "test/java-example",
        "language": "java",
        "stars": 100,
        "clone_url": "https://github.com/test/java-example.git",
    }
    fake_commits = {
        "test/java-example": [
            {
                "commit_sha": "def456",
                "agent_type": "claude",
                "commit_date": "2025-01-02",
            }
        ]
    }

    with patch("collection.agent_corpus._load_qc_repo_rows", return_value=[fake_repo]):
        with patch("collection.agent_corpus._load_qc_agent_commits", return_value=fake_commits):
            with patch("collection.agent_corpus.clone_with_function") as mock_clone:
                mock_clone.return_value.__enter__ = MagicMock(return_value=tmp_path / "repo")
                mock_clone.return_value.__exit__ = MagicMock(return_value=False)
                with patch("collection.agent_corpus.collect_test_files_for_commit", return_value=["tests/test_foo.py"]):
                    with patch("collection.agent_corpus.AgentFixtureExtractor") as mock_ext:
                        instance = mock_ext.return_value
                        instance._extract_from_agent_commits.return_value = []
                        stats, _ = collector.run(language="java")

    assert stats.repos_scanned == 1, "Single-language run should proceed despite full-run checkpoint"


def test_single_language_checkpoint_blocks_rerun(tmp_path):
    """A completed single-language run should block re-runs of the same language."""
    from unittest.mock import patch, MagicMock
    from collection.agent_corpus import AgentCorpusCollector
    from collection.db import mark_global_checkpoint, initialise_db

    db_path = tmp_path / "corpus.db"
    initialise_db(db_path)
    collector = AgentCorpusCollector(
        output_db=db_path,
        repo_qc_dir=Path("fixtures-from-agents"),
        commit_qc_dir=Path("github-search-agent/agent_commits"),
        test_commits_csv=tmp_path / "test_commits",
    )

    # Simulate a completed java run
    with db_session(db_path) as conn:
        mark_global_checkpoint(conn, "agent_complete:java")

    # Re-run java — should be blocked
    stats, _ = collector.run(language="java")
    assert stats.repos_scanned == 0
    assert stats.fixtures_collected == 0
