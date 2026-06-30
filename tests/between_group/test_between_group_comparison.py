"""
Unit tests for between-group comparison and balance testing.

Tests statistical comparison of human vs agent corpora including:
- Chi-square tests for categorical variables (language, domain, star_tier)
- Mann-Whitney U tests for continuous variables (repo_age_years)
- Balance test interpretation (p >= 0.05 = balanced)
- Comparison results aggregation and reporting
"""

import sqlite3
import tempfile
from pathlib import Path

from collection.between_group_comparison import (
    BalanceTest,
    BetweenGroupComparison,
    compute_categorical_balance,
    compute_continuous_balance,
    get_agent_fixtures_by_variable,
    get_human_fixtures_by_variable,
)


def _create_test_between_group_db(db_path: Path) -> None:
    """Create a minimal between-group.db with test data."""
    conn = sqlite3.connect(db_path)

    # Create repositories table
    conn.execute("""
        CREATE TABLE repositories (
            id INTEGER PRIMARY KEY,
            github_id TEXT,
            language TEXT,
            domain TEXT,
            star_tier TEXT,
            repo_age_years REAL,
            created_at TEXT,
            num_contributors INTEGER,
            num_test_files INTEGER
        )
    """)

    # Create fixtures table
    conn.execute("""
        CREATE TABLE fixtures (
            id INTEGER PRIMARY KEY,
            repo_id INTEGER,
            commit_kind TEXT,
            commit_sha TEXT,
            agent_type TEXT,
            fixture_type TEXT,
            framework TEXT,
            path TEXT,
            FOREIGN KEY (repo_id) REFERENCES repositories(id)
        )
    """)

    # Add human repositories (pre-2021, snapshot at 2020-12-31)
    human_repos = [
        (1, "gh1", "python", "web", "core", 5.0, "2015-01-01T00:00:00Z", 10, 5),
        (2, "gh2", "python", "ml", "core", 4.0, "2016-01-01T00:00:00Z", 15, 6),
        (3, "gh3", "javascript", "web", "extended", 3.0, "2017-01-01T00:00:00Z", 8, 3),
        (4, "gh4", "java", "other", "extended", 6.0, "2014-01-01T00:00:00Z", 5, 2),
    ]

    for repo in human_repos:
        conn.execute(
            """
            INSERT INTO repositories VALUES 
            (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            repo,
        )

    # Add agent repositories (2025+, snapshot at 2025-01-01)
    agent_repos = [
        (5, "gh5", "python", "web", "core", 0.4, "2023-01-01T00:00:00Z", 7, 4),
        (6, "gh6", "python", "database", "core", 0.3, "2023-02-01T00:00:00Z", 6, 3),
        (7, "gh7", "javascript", "web", "extended", 0.2, "2023-03-01T00:00:00Z", 5, 2),
    ]

    for repo in agent_repos:
        conn.execute(
            """
            INSERT INTO repositories VALUES 
            (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            repo,
        )

    # Add human fixtures (10 per repo)
    for repo_id in [1, 2, 3, 4]:
        for i in range(10):
            conn.execute(
                """
                INSERT INTO fixtures VALUES
                (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    None,
                    repo_id,
                    "human",
                    f"sha{repo_id}_{i}",
                    None,
                    "unittest",
                    "pytest",
                    f"test_{i}.py",
                ),
            )

    # Add agent fixtures (8-10 per repo)
    for idx, repo_id in enumerate([5, 6, 7]):
        count = 10 if idx < 2 else 8
        for i in range(count):
            agent_type = ["claude", "copilot", "cursor"][idx]
            conn.execute(
                """
                INSERT INTO fixtures VALUES
                (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    None,
                    repo_id,
                    "agent",
                    f"sha{repo_id}_{i}",
                    agent_type,
                    "unittest",
                    "pytest",
                    f"test_{i}.py",
                ),
            )

    conn.commit()
    conn.close()


class TestBalanceTest:
    """Test BalanceTest result dataclass."""

    def test_balance_test_initialization(self):
        """Should initialize with required fields."""
        test = BalanceTest(
            variable="language",
            test_type="chi-square",
            p_value=0.42,
            is_balanced=True,
        )

        assert test.variable == "language"
        assert test.test_type == "chi-square"
        assert test.p_value == 0.42
        assert test.is_balanced is True

    def test_balance_test_to_dict(self):
        """Should convert to dictionary for JSON serialization."""
        test = BalanceTest(
            variable="star_tier",
            test_type="chi-square",
            p_value=0.85,
            is_balanced=True,
            statistic=1.25,
        )

        test_dict = test.to_dict()

        assert test_dict["variable"] == "star_tier"
        assert test_dict["p_value"] == 0.85
        assert test_dict["is_balanced"] is True

    def test_balance_test_interpretation_threshold(self):
        """p >= 0.05 should indicate balanced control variables."""
        balanced_test = BalanceTest(
            variable="domain",
            test_type="chi-square",
            p_value=0.06,
            is_balanced=True,
        )

        imbalanced_test = BalanceTest(
            variable="domain",
            test_type="chi-square",
            p_value=0.04,
            is_balanced=False,
        )

        assert balanced_test.is_balanced is True
        assert imbalanced_test.is_balanced is False


class TestCategoricalBalance:
    """Test chi-square balance testing for categorical variables."""

    def test_perfectly_balanced_distribution(self):
        """Perfectly balanced distributions should pass test."""
        human_dist = {"python": 100, "javascript": 100, "java": 100}
        agent_dist = {"python": 100, "javascript": 100, "java": 100}

        result = compute_categorical_balance(human_dist, agent_dist, "language")

        assert result.variable == "language"
        assert result.test_type == "chi-square"
        assert result.p_value >= 0.05  # Should be balanced
        assert bool(result.is_balanced) is True

    def test_severely_imbalanced_distribution(self):
        """Severely imbalanced distributions should fail test."""
        human_dist = {"python": 300, "javascript": 0, "java": 0}
        agent_dist = {"python": 100, "javascript": 100, "java": 100}

        result = compute_categorical_balance(human_dist, agent_dist, "language")

        assert result.variable == "language"
        assert result.p_value < 0.05  # Should be imbalanced
        assert bool(result.is_balanced) is False

    def test_chi_square_with_real_data(self):
        """Chi-square should handle realistic distribution differences."""
        human_dist = {"core": 70, "extended": 30}
        agent_dist = {"core": 65, "extended": 35}

        result = compute_categorical_balance(human_dist, agent_dist, "star_tier")

        assert result.test_type == "chi-square"
        assert result.p_value >= 0.05  # Should be balanced (similar distributions)

    def test_chi_square_with_missing_categories(self):
        """Chi-square should handle missing categories in one distribution."""
        human_dist = {"python": 50, "javascript": 50}
        agent_dist = {"python": 50, "javascript": 30, "java": 20}

        result = compute_categorical_balance(human_dist, agent_dist, "language")

        assert result.variable == "language"
        assert "p_value" in result.to_dict()

    def test_chi_square_with_empty_distribution(self):
        """Chi-square should handle empty distributions gracefully."""
        human_dist = {}
        agent_dist = {"python": 50}

        result = compute_categorical_balance(human_dist, agent_dist, "language")

        assert result.p_value == 1.0  # Insufficient data
        assert result.is_balanced is True  # Can't reject balance


class TestContinuousBalance:
    """Test Mann-Whitney U balance testing for continuous variables."""

    def test_identical_distributions(self):
        """Identical distributions should pass test."""
        human_values = [5.0, 5.0, 5.0, 5.0, 5.0]
        agent_values = [5.0, 5.0, 5.0, 5.0, 5.0]

        result = compute_continuous_balance(
            human_values, agent_values, "repo_age_years"
        )

        assert result.variable == "repo_age_years"
        assert result.test_type == "mann-whitney-u"
        assert result.is_balanced == True

    def test_similar_distributions(self):
        """Similar distributions should pass balance test."""
        human_values = [4.0, 5.0, 5.5, 6.0, 6.5]
        agent_values = [4.5, 5.0, 5.5, 6.0, 6.5]

        result = compute_continuous_balance(
            human_values, agent_values, "repo_age_years"
        )

        assert result.p_value >= 0.05  # Should be balanced
        assert result.is_balanced == True

    def test_different_distributions(self):
        """Clearly different distributions should fail test."""
        human_values = [1.0, 1.5, 2.0, 2.5, 3.0]  # Low age
        agent_values = [5.0, 5.5, 6.0, 6.5, 7.0]  # High age

        result = compute_continuous_balance(
            human_values, agent_values, "repo_age_years"
        )

        assert result.p_value < 0.05  # Should be imbalanced
        assert result.is_balanced == False

    def test_mann_whitney_with_empty_data(self):
        """Mann-Whitney U should handle empty data gracefully."""
        human_values = []
        agent_values = [5.0, 5.5, 6.0]

        result = compute_continuous_balance(
            human_values, agent_values, "repo_age_years"
        )

        # Should handle gracefully (probably return high p-value or special case)
        assert result.variable == "repo_age_years"


class TestVariableDistribution:
    """Test querying fixture distributions by control variables."""

    def test_get_human_fixtures_by_variable(self):
        """Should return distribution of human fixtures by variable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            _create_test_between_group_db(db_path)

            dist = get_human_fixtures_by_variable(db_path, "language")

            assert "python" in dist
            assert "javascript" in dist
            assert dist["python"] == 20  # 2 repos * 10 fixtures
            assert dist["javascript"] == 10  # 1 repo * 10 fixtures

    def test_get_agent_fixtures_by_variable(self):
        """Should return distribution of agent fixtures by variable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            _create_test_between_group_db(db_path)

            dist = get_agent_fixtures_by_variable(db_path, "language")

            assert "python" in dist
            assert "javascript" in dist
            assert dist["python"] == 20  # 2 repos * 10 fixtures
            assert dist["javascript"] == 8  # 1 repo * 8 fixtures

    def test_get_fixtures_by_domain(self):
        """Should work for domain variable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            _create_test_between_group_db(db_path)

            human_dist = get_human_fixtures_by_variable(db_path, "domain")
            agent_dist = get_agent_fixtures_by_variable(db_path, "domain")

            assert "web" in human_dist
            assert "ml" in human_dist
            assert "web" in agent_dist
            assert "database" in agent_dist

    def test_get_fixtures_by_star_tier(self):
        """Should work for star_tier variable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            _create_test_between_group_db(db_path)

            human_dist = get_human_fixtures_by_variable(db_path, "star_tier")
            agent_dist = get_agent_fixtures_by_variable(db_path, "star_tier")

            assert "core" in human_dist
            assert "extended" in human_dist
            assert sum(human_dist.values()) == 40  # 4 repos * 10 fixtures


class TestBetweenGroupComparison:
    """Test BetweenGroupComparison result aggregation."""

    def test_comparison_initialization(self):
        """Should initialize with all required fields."""
        balance_tests = [
            BalanceTest("language", "chi-square", 0.5, True),
            BalanceTest("domain", "chi-square", 0.3, True),
        ]

        comparison = BetweenGroupComparison(
            timestamp="2024-05-18T10:00:00Z",
            methodology={"approach": "between-group"},
            balance_tests=balance_tests,
            human_corpus_stats={},
            agent_corpus_stats={},
            control_variable_summary={},
        )

        assert comparison.timestamp == "2024-05-18T10:00:00Z"
        assert len(comparison.balance_tests) == 2

    def test_comparison_to_dict(self):
        """Should convert to dictionary for JSON serialization."""
        balance_tests = [
            BalanceTest("language", "chi-square", 0.5, True),
        ]

        comparison = BetweenGroupComparison(
            timestamp="2024-05-18T10:00:00Z",
            methodology={"approach": "between-group"},
            balance_tests=balance_tests,
            human_corpus_stats={"fixtures": 100},
            agent_corpus_stats={"fixtures": 80},
            control_variable_summary={},
        )

        comparison_dict = comparison.to_dict()

        assert comparison_dict["timestamp"] == "2024-05-18T10:00:00Z"
        assert len(comparison_dict["balance_tests"]) == 1
        assert comparison_dict["human_corpus_stats"]["fixtures"] == 100

    def test_comparison_all_tests_balanced(self):
        """Should report when all control variables are balanced."""
        balance_tests = [
            BalanceTest("language", "chi-square", 0.5, True),
            BalanceTest("domain", "chi-square", 0.3, True),
            BalanceTest("star_tier", "chi-square", 0.6, True),
            BalanceTest("repo_age_years", "mann-whitney-u", 0.4, True),
        ]

        comparison = BetweenGroupComparison(
            timestamp="2024-05-18T10:00:00Z",
            methodology={},
            balance_tests=balance_tests,
            human_corpus_stats={},
            agent_corpus_stats={},
            control_variable_summary={},
        )

        all_balanced = all(t.is_balanced for t in comparison.balance_tests)
        assert all_balanced is True

    def test_comparison_some_tests_imbalanced(self):
        """Should report when some control variables are imbalanced."""
        balance_tests = [
            BalanceTest("language", "chi-square", 0.5, True),
            BalanceTest("domain", "chi-square", 0.02, False),  # Imbalanced
            BalanceTest("star_tier", "chi-square", 0.6, True),
        ]

        comparison = BetweenGroupComparison(
            timestamp="2024-05-18T10:00:00Z",
            methodology={},
            balance_tests=balance_tests,
            human_corpus_stats={},
            agent_corpus_stats={},
            control_variable_summary={},
        )

        all_balanced = all(t.is_balanced for t in comparison.balance_tests)
        assert all_balanced is False


class TestComparisonLimitations:
    """Test documentation of between-group study limitations."""

    def test_comparison_with_limitations(self):
        """Should document known limitations of between-group design."""
        limitations = [
            "Temporal separation confounding: human corpus (pre-2021) vs agent corpus (2025+)",
            "Tier 1 agent detection is conservative (70-80% recall, 99%+ precision)",
            "Repository availability may differ between temporal periods",
        ]

        comparison = BetweenGroupComparison(
            timestamp="2024-05-18T10:00:00Z",
            methodology={},
            balance_tests=[],
            human_corpus_stats={},
            agent_corpus_stats={},
            control_variable_summary={},
            limitations=limitations,
        )

        assert len(comparison.limitations) == 3
        assert "Temporal separation confounding" in comparison.limitations[0]
