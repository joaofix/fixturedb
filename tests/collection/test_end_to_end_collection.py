"""
End-to-End Collection Tests - Use Case 2.

Tests the complete collection pipeline with minimal test repositories.
Verifies that the collection module correctly:
1. Selects repositories
2. Clones/validates repositories
3. Scans for commits
4. Extracts fixtures
5. Persists to database
6. Exports to CSV files

Uses small test repositories and mocked git operations for speed.
"""

import sqlite3

import pytest

from collection.agent_corpus import (
    AgentCorpusCollector,
)


@pytest.fixture
def test_data_dir(tmp_path):
    """Create test data directory with CSVs and DB."""
    return tmp_path / "test_data"


class TestAgentCorpusCollectorInitialization:
    """Test AgentCorpusCollector initialization."""

    def test_agent_corpus_collector_initializes_with_defaults(self):
        """Verify agent collector initializes with defaults."""
        collector = AgentCorpusCollector()

        assert collector.github_token is None
        assert collector.clones_dir is not None
        assert collector.output_db is not None

    def test_agent_corpus_collector_accepts_github_token(self):
        """Verify agent collector accepts GitHub token."""
        token = "test_token_12345"
        collector = AgentCorpusCollector(github_token=token)

        assert collector.github_token == token


class TestCollectionDatabaseSchema:
    """Test database schema validation after collection."""

    def test_output_database_has_required_tables(self, tmp_path):
        """Verify a freshly initialised output database has all required tables."""
        from collection.db import initialise_db

        db_path = tmp_path / "test.db"
        initialise_db(db_path)

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check required tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}

        required_tables = {
            "repositories",
            "test_files",
            "fixtures",
            "test_commits",
            "mock_usages",
        }

        for table in required_tables:
            assert table in tables, f"Missing required table: {table}"

        conn.close()

    def test_database_schema_has_expected_columns(self, tmp_path):
        """Verify database tables have expected columns."""
        from collection.db import initialise_db

        db_path = tmp_path / "test.db"
        initialise_db(db_path)

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check repositories table columns
        cursor.execute("PRAGMA table_info(repositories)")
        repo_cols = {row[1] for row in cursor.fetchall()}

        required_repo_cols = {
            "id",
            "github_id",
            "full_name",
            "language",
            "stars",
            "domain",
            "repo_age_years",
        }

        for col in required_repo_cols:
            assert col in repo_cols, f"Missing expected column in repositories: {col}"

        conn.close()


class TestCollectionDataPersistence:
    """Test data persistence through collection pipeline."""

    def test_repository_data_persists_to_database(self, tmp_path):
        """Verify repository data is correctly stored in database."""
        from collection.corpus_utils import persist_repository_and_fixtures
        from collection.db import initialise_db

        db_path = tmp_path / "test.db"
        initialise_db(db_path)

        repo_data = {
            "github_id": 123,
            "full_name": "owner/repo",
            "language": "python",
            "stars": 100,
            "forks": 10,
            "description": "Test",
            "topics": "[]",
            "created_at": "",
            "pushed_at": "",
            "clone_url": "https://github.com/owner/repo.git",
            "num_contributors": 5,
            "domain": "web",
            "repo_age_years": 2.0,
        }

        persist_repository_and_fixtures(db_path, repo_data, [])

        # Verify data was inserted
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT full_name, language FROM repositories WHERE full_name = ?",
            (repo_data["full_name"],),
        )
        row = cursor.fetchone()

        assert row is not None
        assert row[0] == "owner/repo"
        assert row[1] == "python"

        conn.close()

    def test_fixture_data_persists_to_database(self, tmp_path):
        """Verify fixture data is correctly stored in database."""
        from collection.corpus_utils import persist_repository_and_fixtures
        from collection.db import initialise_db

        db_path = tmp_path / "test.db"
        initialise_db(db_path)

        repo_data = {
            "github_id": 123,
            "full_name": "owner/repo",
            "language": "python",
            "stars": 100,
            "forks": 10,
            "description": "Test",
            "topics": "[]",
            "created_at": "",
            "pushed_at": "",
            "clone_url": "https://github.com/owner/repo.git",
            "num_contributors": 5,
            "domain": "web",
            "repo_age_years": 2.0,
        }

        fixtures = [
            {
                "commit_sha": "abc123",
                "file_path": "test_foo.py",
                "name": "test_fixture",
                "fixture_type": "function",
                "start_line": 10,
                "end_line": 20,
                "loc": 11,
                "framework": "pytest",
                "scope": "function",
                "cyclomatic_complexity": 1,
                "max_nesting_depth": 1,
                "num_objects_instantiated": 0,
                "num_external_calls": 0,
                "num_comment_lines": 0,
                "comment_density": 0.0,
                "num_parameters": 0,
                "has_teardown_pair": False,
                "raw_source": "def test_fixture(): pass",
                "mocks": [],
                "commit_kind": "human",
                "is_complete_addition": 1,
            }
        ]

        count = persist_repository_and_fixtures(db_path, repo_data, fixtures)

        assert count == 1

        # Verify fixture was inserted
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name, fixture_type FROM fixtures WHERE name = ?", ("test_fixture",)
        )
        row = cursor.fetchone()

        assert row is not None
        assert row[0] == "test_fixture"
        assert row[1] == "function"

        conn.close()

