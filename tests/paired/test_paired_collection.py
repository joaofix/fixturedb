"""
Unit tests for paired study collection and control variable computation.

Tests the paired within-repository methodology including:
- Control variable collection (domain classification, repo age)
- Quality filter validation
- Chi-square balance testing
- Repository selection logic
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from collection.paired_collection import (
    PairedStudyCollector,
    PairedStudyStats,
)
from collection.repo_metadata import (
    classify_domain,
    compute_repo_age_years,
)


class TestControlVariableComputation:
    """Test collection of control variables for confound assessment."""

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
        # Note: "web" keywords are checked before "security", so django matches first
        topics = '["django", "security"]'
        domain = classify_domain(topics, "")
        assert domain == "web"

    def test_classify_domain_default_other(self):
        """Unknown topics should classify as 'other'."""
        topics = '["random", "tags"]'
        domain = classify_domain(topics, "Some random description")
        assert domain == "other"

    def test_compute_repo_age_years_recent(self):
        """Repository created recently should have small age."""
        date_str = "2023-01-01T00:00:00Z"
        age = compute_repo_age_years(date_str)

        # Should be roughly 1-3 years old (depending on current date)
        assert age is not None
        assert isinstance(age, float)
        assert age > 0

    def test_compute_repo_age_years_old(self):
        """Old repository should have large age."""
        date_str = "2000-01-01T00:00:00Z"
        age = compute_repo_age_years(date_str)

        # Should be roughly 20+ years old
        assert age is not None
        assert age > 20

    def test_compute_repo_age_years_invalid_date(self):
        """Invalid date string should return None gracefully."""
        age = compute_repo_age_years("invalid-date")
        assert age is None

    def test_compute_repo_age_years_empty_string(self):
        """Empty date string should return None."""
        age = compute_repo_age_years("")
        assert age is None


class TestPairedStudyCollectorControlVariables:
    """Test PairedStudyCollector control variable collection."""

    def test_collect_control_variables_returns_dict(self):
        """Should return dict with domain, repo_age_years."""
        with tempfile.TemporaryDirectory() as tmpdir:
            collector = PairedStudyCollector(
                corpus_db_path=Path(tmpdir) / "corpus.db",
            )

            repo = {
                "topics": '["django", "python"]',
                "description": "A web framework",
                "stars": 750,
                "created_at": "2020-01-01T00:00:00Z",
            }

            control_vars = collector._collect_control_variables(repo)

            assert "domain" in control_vars
            assert "repo_age_years" in control_vars

    def test_collect_control_variables_domain_classification(self):
        """Domain should be correctly classified."""
        with tempfile.TemporaryDirectory() as tmpdir:
            collector = PairedStudyCollector(
                corpus_db_path=Path(tmpdir) / "corpus.db",
            )

            repo = {
                "topics": '["machine learning", "tensorflow"]',
                "description": "",
                "stars": 100,
                "created_at": "2020-01-01T00:00:00Z",
            }

            control_vars = collector._collect_control_variables(repo)
            assert control_vars["domain"] == "ml"

    def test_collect_control_variables_repo_age(self):
        """Repo age should be computed in years."""
        with tempfile.TemporaryDirectory() as tmpdir:
            collector = PairedStudyCollector(
                corpus_db_path=Path(tmpdir) / "corpus.db",
            )

            repo = {
                "topics": "[]",
                "description": "",
                "stars": 100,
                "created_at": "2000-01-01T00:00:00Z",
            }

            control_vars = collector._collect_control_variables(repo)
            assert control_vars["repo_age_years"] is not None
            assert control_vars["repo_age_years"] > 20


class TestQualityFilterValidation:
    """Test quality filter validation for paired study."""

    def test_validate_quality_filters_seart_repos_pass(self):
        """SEART-filtered repositories should pass QC."""
        with tempfile.TemporaryDirectory() as tmpdir:
            collector = PairedStudyCollector(
                corpus_db_path=Path(tmpdir) / "corpus.db",
            )

            repo_path = Path(tmpdir) / "repo"
            repo_path.mkdir()

            passes_qc, reason = collector._validate_quality_filters(
                repo_path, "python", "owner/repo"
            )

            assert passes_qc is True
            assert reason is None

    def test_validate_quality_filters_returns_tuple(self):
        """Should return (bool, optional reason) tuple."""
        with tempfile.TemporaryDirectory() as tmpdir:
            collector = PairedStudyCollector(
                corpus_db_path=Path(tmpdir) / "corpus.db",
            )

            repo_path = Path(tmpdir) / "repo"

            result = collector._validate_quality_filters(
                repo_path, "python", "owner/repo"
            )

            assert isinstance(result, tuple)
            assert len(result) == 2
            assert isinstance(result[0], bool)
            assert result[1] is None or isinstance(result[1], str)


class TestChiSquareBalance:
    """Test statistical balance testing via chi-square."""

    def test_chi_square_balanced_distribution(self):
        """Balanced distributions should have p >= 0.05."""
        with tempfile.TemporaryDirectory() as tmpdir:
            collector = PairedStudyCollector(
                corpus_db_path=Path(tmpdir) / "corpus.db",
            )

            # Perfectly balanced
            agent_counts = {"python": 10, "javascript": 10}
            human_counts = {"python": 10, "javascript": 10}

            result = collector._compute_chi_square_balance(agent_counts, human_counts)

            assert "chi_square" in result
            assert "p_value" in result
            assert "status" in result
            # Perfectly balanced should have p = 1.0
            assert result["status"] == "balanced"

    def test_chi_square_imbalanced_distribution(self):
        """Imbalanced distributions should have p < 0.05."""
        with tempfile.TemporaryDirectory() as tmpdir:
            collector = PairedStudyCollector(
                corpus_db_path=Path(tmpdir) / "corpus.db",
            )

            # Highly imbalanced
            agent_counts = {"python": 100, "javascript": 1}
            human_counts = {"python": 10, "javascript": 10}

            result = collector._compute_chi_square_balance(agent_counts, human_counts)

            assert "chi_square" in result
            assert "p_value" in result
            assert "status" in result
            assert result["status"] == "imbalanced"

    def test_chi_square_insufficient_data(self):
        """Small sample sizes should return insufficient_data status."""
        with tempfile.TemporaryDirectory() as tmpdir:
            collector = PairedStudyCollector(
                corpus_db_path=Path(tmpdir) / "corpus.db",
            )

            # Only 1 count in each
            agent_counts = {"python": 1}
            human_counts = {"python": 1}

            result = collector._compute_chi_square_balance(agent_counts, human_counts)

            assert result["status"] == "insufficient_data"

    def test_chi_square_scipy_unavailable(self):
        """Should gracefully handle missing scipy."""
        with tempfile.TemporaryDirectory() as tmpdir:
            collector = PairedStudyCollector(
                corpus_db_path=Path(tmpdir) / "corpus.db",
            )

            # Mock ImportError for scipy
            with patch.dict("sys.modules", {"scipy.stats": None}):
                agent_counts = {"python": 10, "javascript": 10}
                human_counts = {"python": 10, "javascript": 10}

                # Should not raise even without scipy
                result = collector._compute_chi_square_balance(
                    agent_counts, human_counts
                )
                # Result will be either "balanced" (if scipy is installed) or "unavailable"
                assert "status" in result

    def test_chi_square_empty_distributions(self):
        """Empty distributions should return insufficient_data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            collector = PairedStudyCollector(
                corpus_db_path=Path(tmpdir) / "corpus.db",
            )

            result = collector._compute_chi_square_balance({}, {})

            assert result["status"] == "insufficient_data"


class TestComputeFixtureRates:
    """Regression tests: fixtures_per_agent_commit / fixtures_per_human_commit
    must use per-role fixture counts, not the combined total."""

    def test_uses_per_role_fixture_counts_not_combined_total(self):
        stats = PairedStudyStats(
            agent_commits=10,
            human_commits=10,
            fixtures_observed=80,
            agent_fixtures_observed=50,
            human_fixtures_observed=30,
        )

        rates = PairedStudyCollector._compute_fixture_rates(stats)

        assert rates["fixtures_per_agent_commit"] == 5.0
        assert rates["fixtures_per_human_commit"] == 3.0

    def test_zero_commits_does_not_divide_by_zero(self):
        stats = PairedStudyStats(agent_commits=0, human_commits=0)

        rates = PairedStudyCollector._compute_fixture_rates(stats)

        assert rates["fixtures_per_agent_commit"] == 0
        assert rates["fixtures_per_human_commit"] == 0


class TestPairedStudyStats:
    """Test PairedStudyStats dataclass."""

    def test_paired_study_stats_initialization(self):
        """Should initialize with default values."""
        stats = PairedStudyStats()

        assert stats.repos_scanned == 0
        assert stats.repos_with_pairs == 0
        assert stats.agent_commits == 0
        assert stats.human_commits == 0
        assert stats.observations_inserted == 0

    def test_paired_study_stats_to_dict(self):
        """Should convert to dict representation."""
        stats = PairedStudyStats(
            repos_scanned=10,
            agent_commits=50,
            human_commits=50,
        )

        result = stats.to_dict()

        assert isinstance(result, dict)
        assert result["repos_scanned"] == 10
        assert result["agent_commits"] == 50
        assert result["human_commits"] == 50

    def test_paired_study_stats_dict_contains_control_variables(self):
        """Dict should contain control variable fields."""
        stats = PairedStudyStats(
            domain_distribution={"web": 5, "ml": 3},
            mean_repo_age_years=5.5,
        )

        result = stats.to_dict()

        assert "domain_distribution" in result
        assert "mean_repo_age_years" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
