"""Tests human corpus collection for agent-enabled repositories including:
- Repository selection from agent-enabled repos (post-2025)
- Human fixture collection in same temporal window as agents
- Control variable computation
- Statistics aggregation
"""

import sqlite3
import subprocess
import tempfile
from pathlib import Path

from collection.config import AGENT_CORPUS_START_DATE
from collection.db import (
    classify_domain,
    compute_repo_age_at_date,
    compute_star_tier,
)
from collection.human_corpus import (
    HumanCorpusCollector,
    HumanCorpusStats,
    _human_fixtures_dir,
    select_human_corpus_repositories,
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

    # Add post-2025 repositories with agent config (should be included)
    agent_era_repos = [
        (
            1,
            "gh1",
            "owner1/repo_python_agent",
            "python",
            600,
            50,
            "A web framework",
            '["django"]',
            "2025-01-02T00:00:00Z",
            "2025-03-01T00:00:00Z",
            "https://github.com/owner1/repo_python_agent.git",
            "analysed",
            10,
            5,
        ),
        (
            2,
            "gh2",
            "owner2/repo_python_ml",
            "python",
            700,
            60,
            "ML library",
            '["machine learning"]',
            "2025-02-01T00:00:00Z",
            "2025-03-15T00:00:00Z",
            "https://github.com/owner2/repo_python_ml.git",
            "cloned",
            15,
            6,
        ),
        (
            3,
            "gh3",
            "owner3/repo_js_agent",
            "javascript",
            800,
            70,
            "Frontend framework",
            '["vue"]',
            "2025-04-01T00:00:00Z",
            "2025-05-01T00:00:00Z",
            "https://github.com/owner3/repo_js_agent.git",
            "analysed",
            20,
            7,
        ),
    ]

    # Add pre-2025 repositories (should NOT be included)
    old_repos = [
        (
            4,
            "gh4",
            "owner4/repo_python_old",
            "python",
            500,
            40,
            "Old library",
            '["async"]',
            "2020-01-01T00:00:00Z",
            "2025-01-01T00:00:00Z",
            "https://github.com/owner4/repo_python_old.git",
            "analysed",
            8,
            4,
        ),
        (
            5,
            "gh5",
            "owner5/repo_java_old",
            "java",
            300,
            30,
            "Android app",
            '["android"]',
            "2019-06-01T00:00:00Z",
            "2025-01-15T00:00:00Z",
            "https://github.com/owner5/repo_java_old.git",
            "analysed",
            5,
            2,
        ),
    ]

    for repo in agent_era_repos + old_repos:
        conn.execute(
            """
            INSERT INTO repositories VALUES 
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            repo,
        )

    conn.commit()
    conn.close()


class TestControlVariableComputation:
    """Test control variable computation at temporal snapshots."""

    def test_classify_domain_from_topics_web(self):
        """Domain classification should detect web framework topics."""
        topics = '["django", "flask", "rest-api"]'
        domain = classify_domain(topics, "")
        assert domain == "web"

    def test_classify_domain_from_topics_ml(self):
        """Domain classification should detect ML/AI topics."""
        topics = '["machine learning", "tensorflow", "deep learning"]'
        domain = classify_domain(topics, "")
        assert domain == "ml"

    def test_classify_domain_from_description_database(self):
        """Domain classification should detect database from description."""
        description = "A relational database with SQL support"
        domain = classify_domain("[]", description)
        assert domain == "database"

    def test_classify_domain_security_priority(self):
        """Domain classification should match first matching keyword."""
        # Note: "web" keywords are checked before "security"
        topics = '["django", "security"]'
        domain = classify_domain(topics, "")
        assert domain == "web"

    def test_classify_domain_default_other(self):
        """Unknown topics should classify as 'other'."""
        topics = '["random", "tags"]'
        domain = classify_domain(topics, "Some random description")
        assert domain == "other"

    def test_compute_star_tier_core(self):
        """Repositories with 500+ stars should be classified as 'core'."""
        tier = compute_star_tier(500)
        assert tier == "core"

        tier = compute_star_tier(1000)
        assert tier == "core"

    def test_compute_star_tier_extended(self):
        """Repositories with <500 stars should be classified as 'extended'."""
        tier = compute_star_tier(100)
        assert tier == "extended"

        tier = compute_star_tier(499)
        assert tier == "extended"

    def test_compute_star_tier_boundary(self):
        """Boundary case: exactly 500 stars should be 'core'."""
        tier = compute_star_tier(500)
        assert tier == "core"

    def test_compute_repo_age_years_at_snapshot_date(self):
        """Repository age should be computed relative to snapshot date."""
        # Repository created in 2015, snapshot at 2020-12-31
        created_at = "2015-01-01T00:00:00Z"
        snapshot_date = "2020-12-31T00:00:00Z"

        age = compute_repo_age_at_date(created_at, snapshot_date)

        # Should be 6 years old
        assert age is not None
        assert isinstance(age, float)
        assert 5.9 < age < 6.1  # Allow small floating point variance


class TestRepositorySelection:
    """Test repository selection for human corpus."""

    def test_select_human_corpus_repositories_returns_list(self):
        """Should return a list of pre-2021 repositories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_db = Path(tmpdir) / "corpus.db"
            _create_test_corpus_db(corpus_db)

            repos = select_human_corpus_repositories(corpus_db, repos_per_language=20)

            assert isinstance(repos, list)
            assert len(repos) == 3  # Only the pre-2021 repos

    def test_select_human_corpus_repositories_filters_by_date(self):
        """Should only select repositories created after AGENT_CORPUS_START_DATE."""
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_db = Path(tmpdir) / "corpus.db"
            _create_test_corpus_db(corpus_db)

            repos = select_human_corpus_repositories(corpus_db, repos_per_language=20)

            # Verify all repos are post-2025 (same temporal window as agents)
            for repo in repos:
                assert repo["created_at"] >= AGENT_CORPUS_START_DATE

    def test_select_human_corpus_repositories_by_language(self):
        """Should filter repositories by language when specified."""
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_db = Path(tmpdir) / "corpus.db"
            _create_test_corpus_db(corpus_db)

            python_repos = select_human_corpus_repositories(
                corpus_db, repos_per_language=20, language="python"
            )

            assert all(repo["language"] == "python" for repo in python_repos)
            assert len(python_repos) == 2

    def test_select_human_corpus_repositories_respects_limit(self):
        """Should respect repos_per_language limit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_db = Path(tmpdir) / "corpus.db"
            _create_test_corpus_db(corpus_db)

            repos = select_human_corpus_repositories(corpus_db, repos_per_language=1)

            # With limit=1, should get at most 1 per language
            python_repos = [r for r in repos if r["language"] == "python"]
            js_repos = [r for r in repos if r["language"] == "javascript"]

            assert len(python_repos) <= 1
            assert len(js_repos) <= 1

    def test_select_human_corpus_repositories_filters_by_status(self):
        """Should only select repositories with analysed or cloned status."""
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_db = Path(tmpdir) / "corpus.db"
            _create_test_corpus_db(corpus_db)

            repos = select_human_corpus_repositories(corpus_db, repos_per_language=20)

            # All should have analysed or cloned status
            assert all(repo["status"] in ("analysed", "cloned") for repo in repos)


class TestHumanCorpusStats:
    """Test HumanCorpusStats dataclass."""

    def test_stats_initialization(self):
        """Should initialize with default values."""
        stats = HumanCorpusStats()

        assert stats.repos_scanned == 0
        assert stats.repos_passed_qc == 0
        assert stats.fixtures_collected == 0
        assert isinstance(stats.repos_by_language, dict)

    def test_stats_to_dict(self):
        """Should convert to dictionary for JSON serialization."""
        stats = HumanCorpusStats(
            repos_scanned=10,
            repos_passed_qc=8,
            fixtures_collected=150,
        )

        stats_dict = stats.to_dict()

        assert stats_dict["repos_scanned"] == 10
        assert stats_dict["repos_passed_qc"] == 8
        assert stats_dict["fixtures_collected"] == 150
        assert "timestamp" not in stats_dict  # Stats don't have timestamp


class TestHumanCorpusTemporalBoundary:
    """Test that human corpus respects temporal boundary."""

    def test_human_corpus_temporal_window(self):
        """Human and agent corpus should use same temporal window (post-2025)."""
        assert AGENT_CORPUS_START_DATE.startswith("2025-01-01")

    def test_repositories_at_boundary_included(self):
        """Repositories created at or after AGENT_CORPUS_START_DATE should be included."""
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_db = Path(tmpdir) / "corpus.db"
            conn = sqlite3.connect(corpus_db)
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

            # Repository created exactly at temporal boundary
            conn.execute(
                """
                INSERT INTO repositories VALUES 
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    1,
                    "gh1",
                    "owner/repo",
                    "python",
                    100,
                    10,
                    "desc",
                    "[]",
                    AGENT_CORPUS_START_DATE,
                    "2023-12-01T00:00:00Z",
                    "https://github.com/owner/repo.git",
                    "analysed",
                    5,
                    2,
                ),
            )

            conn.commit()
            conn.close()

            repos = select_human_corpus_repositories(corpus_db, repos_per_language=20)

            # Should include repo at boundary
            assert len(repos) >= 1


def test_validate_quality_filters_passes_with_commits(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "-b", "main", str(repo)], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@example.com"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "Test"],
        check=True,
        capture_output=True,
    )
    (repo / "f.py").write_text("x = 1\n")
    subprocess.run(
        ["git", "-C", str(repo), "add", "f.py"], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "initial"],
        check=True,
        capture_output=True,
    )

    collector = HumanCorpusCollector(corpus_db_path=tmp_path / "corpus.db")
    passes, reason = collector._validate_quality_filters(repo, "python", "owner/repo")
    assert passes is True
    assert reason is None


def test_validate_quality_filters_fails_with_no_commits(tmp_path):
    repo = tmp_path / "empty_repo"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "-b", "main", str(repo)], check=True, capture_output=True
    )

    collector = HumanCorpusCollector(corpus_db_path=tmp_path / "corpus.db")
    passes, reason = collector._validate_quality_filters(repo, "python", "owner/repo")
    assert passes is False
    assert reason == "no_commits_in_agent_window"


def test_validate_quality_filters_returns_tuple(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "-b", "main", str(repo)], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@example.com"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "Test"],
        check=True,
        capture_output=True,
    )
    (repo / "f.py").write_text("x = 1\n")
    subprocess.run(
        ["git", "-C", str(repo), "add", "f.py"], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "initial"],
        check=True,
        capture_output=True,
    )

    collector = HumanCorpusCollector(corpus_db_path=tmp_path / "corpus.db")
    result = collector._validate_quality_filters(repo, "python", "owner/repo")
    assert isinstance(result, tuple)
    assert len(result) == 2
    assert isinstance(result[0], bool)
    assert result[1] is None or isinstance(result[1], str)


def test_human_fixtures_dir_no_versioned_subfolder_when_tag_empty():
    """With empty COLLECTION_OUTPUT_TAG, dir points directly to datasets/b/fixtures."""
    root = _human_fixtures_dir("b")
    assert str(root).endswith(str(Path("datasets") / "b" / "fixtures"))
