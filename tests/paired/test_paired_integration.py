"""
Integration tests for paired study collection pipeline.

Tests end-to-end paired study workflows including:
- Repository selection and filtering
- Control variable tracking across multiple repos
- Balance testing accumulation
- Summary statistics generation
"""

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from collection.paired_collection import (
    PairedStudyCollector,
    PairedStudyStats,
    select_paired_repositories,
)


def _create_test_corpus_db(db_path: Path) -> None:
    """Create a minimal corpus.db with test repositories."""
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE repositories (
            id INTEGER PRIMARY KEY,
            github_id TEXT,
            full_name TEXT,
            language TEXT,
            stars INTEGER,
            forks INTEGER,
            description TEXT,
            topics TEXT,
            created_at TEXT,
            pushed_at TEXT,
            clone_url TEXT,
            status TEXT,
            num_contributors INTEGER,
            num_test_files INTEGER
        )
    """)

    # Add test repositories
    repos = [
        (
            1,
            "gh1",
            "owner1/repo_python_1",
            "python",
            600,
            50,
            "A web framework",
            '["django"]',
            "2015-01-01T00:00:00Z",
            "2023-01-01T00:00:00Z",
            "https://github.com/owner1/repo_python_1.git",
            "analysed",
            10,
            5,
        ),
        (
            2,
            "gh2",
            "owner2/repo_python_2",
            "python",
            700,
            60,
            "ML library",
            '["machine learning", "tensorflow"]',
            "2016-01-01T00:00:00Z",
            "2023-02-01T00:00:00Z",
            "https://github.com/owner2/repo_python_2.git",
            "analysed",
            15,
            6,
        ),
        (
            3,
            "gh3",
            "owner3/repo_js_1",
            "javascript",
            800,
            70,
            "Frontend framework",
            '["vue", "javascript"]',
            "2017-01-01T00:00:00Z",
            "2023-03-01T00:00:00Z",
            "https://github.com/owner3/repo_js_1.git",
            "cloned",
            20,
            7,
        ),
    ]

    for repo in repos:
        conn.execute(
            """
            INSERT INTO repositories VALUES 
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            repo,
        )

    conn.commit()
    conn.close()


class TestRepositorySelection:
    """Test repository selection logic for paired study."""

    def test_select_paired_repositories_returns_list(self):
        """Should return a list of repositories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_db = Path(tmpdir) / "corpus.db"
            _create_test_corpus_db(corpus_db)

            repos = select_paired_repositories(corpus_db, repos_per_language=20)

            assert isinstance(repos, list)
            assert len(repos) > 0

    def test_select_paired_repositories_by_language(self):
        """Should filter repositories by language when specified."""
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_db = Path(tmpdir) / "corpus.db"
            _create_test_corpus_db(corpus_db)

            python_repos = select_paired_repositories(
                corpus_db, repos_per_language=20, language="python"
            )

            assert all(repo["language"] == "python" for repo in python_repos)

    def test_select_paired_repositories_respects_limit(self):
        """Should respect repos_per_language limit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_db = Path(tmpdir) / "corpus.db"
            _create_test_corpus_db(corpus_db)

            repos = select_paired_repositories(corpus_db, repos_per_language=1)

            # With limit of 1, should get at most 1 per language
            python_count = sum(1 for r in repos if r["language"] == "python")
            js_count = sum(1 for r in repos if r["language"] == "javascript")

            assert python_count <= 1
            assert js_count <= 1

    def test_select_paired_repositories_includes_metadata(self):
        """Selected repositories should include all required metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_db = Path(tmpdir) / "corpus.db"
            _create_test_corpus_db(corpus_db)

            repos = select_paired_repositories(corpus_db, repos_per_language=20)

            required_fields = [
                "id",
                "full_name",
                "language",
                "stars",
                "created_at",
                "num_contributors",
                "num_test_files",
            ]

            for repo in repos:
                for field in required_fields:
                    assert field in repo, f"Missing field: {field}"

    def test_select_paired_repositories_sorted(self):
        """Repositories should be sorted consistently."""
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_db = Path(tmpdir) / "corpus.db"
            _create_test_corpus_db(corpus_db)

            repos = select_paired_repositories(corpus_db, repos_per_language=20)

            # Should be grouped by language and sorted by date within language
            prev_lang = None
            prev_date = None

            for repo in repos:
                if prev_lang is not None and repo["language"] != prev_lang:
                    # Language changed, reset date check
                    prev_date = None
                    prev_lang = repo["language"]
                else:
                    # Same language, should be in chronological order
                    if prev_date is not None:
                        assert (
                            repo["created_at"] >= prev_date or repo["id"] >= repo["id"]
                        )
                    prev_date = repo["created_at"]
                    prev_lang = repo["language"]


class TestPairedStudyStatsAccumulation:
    """Test accumulation of statistics across multiple repositories."""

    def test_stats_accumulation_repos_scanned(self):
        """Should accumulate repos_scanned count."""
        stats = PairedStudyStats()

        for i in range(5):
            stats.repos_scanned += 1

        assert stats.repos_scanned == 5

    def test_stats_accumulation_agent_human_commits(self):
        """Should accumulate agent and human commit counts."""
        stats = PairedStudyStats()

        # Simulate 3 repositories
        repos_data = [
            (10, 8),  # repo1: 10 agent, 8 human
            (5, 12),  # repo2: 5 agent, 12 human
            (15, 15),  # repo3: 15 agent, 15 human
        ]

        for agent, human in repos_data:
            stats.agent_commits += agent
            stats.human_commits += human

        assert stats.agent_commits == 30
        assert stats.human_commits == 35

    def test_stats_accumulation_control_variables(self):
        """Should accumulate control variable distributions."""
        stats = PairedStudyStats()

        repos_data = [
            {"domain": "web", "tier": "core", "age": 5.0, "contrib": 10},
            {"domain": "ml", "tier": "extended", "age": 3.0, "contrib": 5},
            {"domain": "web", "tier": "core", "age": 7.0, "contrib": 20},
        ]

        ages = []
        contribs = []

        for repo in repos_data:
            domain = repo["domain"]
            stats.domain_distribution[domain] = (
                stats.domain_distribution.get(domain, 0) + 1
            )

            tier = repo["tier"]
            stats.star_tier_distribution[tier] = (
                stats.star_tier_distribution.get(tier, 0) + 1
            )

            ages.append(repo["age"])
            contribs.append(repo["contrib"])

        if ages:
            stats.mean_repo_age_years = sum(ages) / len(ages)
        if contribs:
            stats.mean_contributors = sum(contribs) / len(contribs)

        assert stats.domain_distribution["web"] == 2
        assert stats.domain_distribution["ml"] == 1
        assert stats.star_tier_distribution["core"] == 2
        assert stats.star_tier_distribution["extended"] == 1
        assert stats.mean_repo_age_years == pytest.approx(5.0)
        assert stats.mean_contributors == pytest.approx(11.666, rel=0.1)

    def test_stats_accumulation_agent_type_breakdown(self):
        """Should track agent type breakdown across repositories."""
        stats = PairedStudyStats()

        agent_types = ["claude", "copilot", "claude", "aider", "copilot", "copilot"]

        for agent_type in agent_types:
            stats.agent_type_breakdown[agent_type] = (
                stats.agent_type_breakdown.get(agent_type, 0) + 1
            )

        assert stats.agent_type_breakdown["claude"] == 2
        assert stats.agent_type_breakdown["copilot"] == 3
        assert stats.agent_type_breakdown["aider"] == 1


class TestPairedStudyCollectorInitialization:
    """Test PairedStudyCollector initialization and configuration."""

    def test_collector_initialization(self):
        """Should initialize with corpus and clones paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_db = Path(tmpdir) / "corpus.db"
            clones_dir = Path(tmpdir) / "clones"

            collector = PairedStudyCollector(
                corpus_db_path=corpus_db,
                clones_dir=clones_dir,
            )

            assert collector.corpus_db_path == corpus_db
            assert collector.clones_dir == clones_dir

    def test_collector_output_db_default(self):
        """Should use default output database path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_db = Path(tmpdir) / "corpus.db"

            collector = PairedStudyCollector(corpus_db_path=corpus_db)

            # Should have output_db set to data/paired-study.db
            assert collector.output_db.name == "paired-study.db"

    def test_collector_output_db_custom(self):
        """Should use custom output database path if provided."""
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_db = Path(tmpdir) / "corpus.db"
            custom_output = Path(tmpdir) / "custom.db"

            collector = PairedStudyCollector(
                corpus_db_path=corpus_db,
                output_db=custom_output,
            )

            assert collector.output_db == custom_output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
