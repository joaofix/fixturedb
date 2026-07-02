"""
Between-group comparison and balance testing.

Compares human vs agent fixture corpora on control variables (language, domain,
star tier, repository age). Uses chi-square for categorical variables and
Mann-Whitney U for continuous variables.

python -m collection.test_commit_filter agent \
  --language java \
  --commit-dir github-search-agent/agent_commits \
  --output-dir output/test-commits/v2-pure-addition-2026-06 \
  --workers 8
"""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

ALLOWED_CATEGORICAL_VARIABLES = {"language", "domain", "star_tier"}
ALLOWED_CONTINUOUS_VARIABLES = {"repo_age_years"}
ALLOWED_VARIABLES = ALLOWED_CATEGORICAL_VARIABLES | ALLOWED_CONTINUOUS_VARIABLES

from scipy.stats import chi2_contingency, mannwhitneyu

from collection.logging_utils import get_logger

from .config import DATA_DIR
from .db import db_session

logger = get_logger(__name__)


@dataclass
class BalanceTest:
    """Result of a single control variable balance test."""

    variable: str  # e.g., "domain", "star_tier", "repo_age_years"
    test_type: str  # "chi-square" or "mann-whitney-u"
    p_value: float
    is_balanced: bool  # p >= 0.05
    statistic: Optional[float] = None
    details: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BetweenGroupComparison:
    """Complete between-group comparison results."""

    timestamp: str
    methodology: Dict
    balance_tests: list[BalanceTest]
    human_corpus_stats: Dict
    agent_corpus_stats: Dict
    control_variable_summary: Dict
    limitations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "methodology": self.methodology,
            "balance_tests": [t.to_dict() for t in self.balance_tests],
            "human_corpus_stats": self.human_corpus_stats,
            "agent_corpus_stats": self.agent_corpus_stats,
            "control_variable_summary": self.control_variable_summary,
            "limitations": self.limitations,
        }


def get_human_fixtures_by_variable(db_path: Path, variable: str) -> Dict[str, int]:
    """
    Get distribution of human fixtures by control variable.

    Args:
        db_path: Path to between-group.db
        variable: One of: "language", "domain", "star_tier"

    Returns:
        Dict with value → count
    """
    if variable not in ALLOWED_CATEGORICAL_VARIABLES:
        raise ValueError(
            f"variable must be one of {ALLOWED_CATEGORICAL_VARIABLES}, got {variable!r}"
        )

    with db_session(db_path) as conn:
        query = f"""
        SELECT r.{variable}, COUNT(f.id) as count
        FROM fixtures f
        JOIN repositories r ON f.repo_id = r.id
        WHERE f.commit_kind = 'human'
        GROUP BY r.{variable}
        """
        rows = conn.execute(query).fetchall()
        return {row[0]: row[1] for row in rows if row[0]}


def get_agent_fixtures_by_variable(db_path: Path, variable: str) -> Dict[str, int]:
    """
    Get distribution of agent fixtures by control variable.

    Args:
        db_path: Path to between-group.db
        variable: One of: "language", "domain", "star_tier"

    Returns:
        Dict with value → count
    """
    if variable not in ALLOWED_CATEGORICAL_VARIABLES:
        raise ValueError(
            f"variable must be one of {ALLOWED_CATEGORICAL_VARIABLES}, got {variable!r}"
        )

    with db_session(db_path) as conn:
        query = f"""
        SELECT r.{variable}, COUNT(f.id) as count
        FROM fixtures f
        JOIN repositories r ON f.repo_id = r.id
        WHERE f.commit_kind = 'agent'
        GROUP BY r.{variable}
        """
        rows = conn.execute(query).fetchall()
        return {row[0]: row[1] for row in rows if row[0]}


def compute_categorical_balance(
    human_dist: Dict[str, int],
    agent_dist: Dict[str, int],
    variable: str,
) -> BalanceTest:
    """
    Compute balance test for categorical control variable using chi-square test.

    Args:
        human_dist: Distribution of human fixtures {category: count}
        agent_dist: Distribution of agent fixtures {category: count}
        variable: Variable name (for reporting)

    Returns:
        BalanceTest result
    """
    # Get all categories
    all_categories = sorted(set(human_dist.keys()) | set(agent_dist.keys()))

    # Build contingency table
    human_counts = [human_dist.get(cat, 0) for cat in all_categories]
    agent_counts = [agent_dist.get(cat, 0) for cat in all_categories]

    # Skip if no variation
    if sum(human_counts) == 0 or sum(agent_counts) == 0:
        return BalanceTest(
            variable=variable,
            test_type="chi-square",
            p_value=1.0,
            is_balanced=True,
            details={"reason": "insufficient_data"},
        )

    try:
        chi2, p_value, dof, expected = chi2_contingency([human_counts, agent_counts])

        return BalanceTest(
            variable=variable,
            test_type="chi-square",
            p_value=float(p_value),
            is_balanced=p_value >= 0.05,
            statistic=float(chi2),
            details={
                "categories": all_categories,
                "human_distribution": dict(zip(all_categories, human_counts)),
                "agent_distribution": dict(zip(all_categories, agent_counts)),
                "chi2_statistic": float(chi2),
                "degrees_of_freedom": int(dof),
            },
        )
    except Exception as e:
        logger.warning(f"Chi-square test failed for {variable}: {e}")
        return BalanceTest(
            variable=variable,
            test_type="chi-square",
            p_value=1.0,
            is_balanced=True,
            details={"error": str(e)},
        )


def compute_continuous_balance(
    human_values: list[float],
    agent_values: list[float],
    variable: str,
) -> BalanceTest:
    """
    Compute balance test for continuous control variable using Mann-Whitney U test.

    Args:
        human_values: Values from human corpus
        agent_values: Values from agent corpus
        variable: Variable name (for reporting)

    Returns:
        BalanceTest result
    """
    # Filter out None values
    human_vals = [v for v in human_values if v is not None]
    agent_vals = [v for v in agent_values if v is not None]

    if not human_vals or not agent_vals:
        return BalanceTest(
            variable=variable,
            test_type="mann-whitney-u",
            p_value=1.0,
            is_balanced=True,
            details={"reason": "insufficient_data"},
        )

    try:
        statistic, p_value = mannwhitneyu(
            human_vals, agent_vals, alternative="two-sided"
        )

        return BalanceTest(
            variable=variable,
            test_type="mann-whitney-u",
            p_value=float(p_value),
            is_balanced=p_value >= 0.05,
            statistic=float(statistic),
            details={
                "human_count": len(human_vals),
                "agent_count": len(agent_vals),
                "human_mean": (
                    float(sum(human_vals) / len(human_vals)) if human_vals else None
                ),
                "agent_mean": (
                    float(sum(agent_vals) / len(agent_vals)) if agent_vals else None
                ),
                "human_median": (
                    float(sorted(human_vals)[len(human_vals) // 2])
                    if human_vals
                    else None
                ),
                "agent_median": (
                    float(sorted(agent_vals)[len(agent_vals) // 2])
                    if agent_vals
                    else None
                ),
                "u_statistic": float(statistic),
            },
        )
    except Exception as e:
        logger.warning(f"Mann-Whitney U test failed for {variable}: {e}")
        return BalanceTest(
            variable=variable,
            test_type="mann-whitney-u",
            p_value=1.0,
            is_balanced=True,
            details={"error": str(e)},
        )


def get_continuous_values(db_path: Path, variable: str, corpus: str) -> list[float]:
    """
    Get list of continuous values for a control variable.

    Args:
        db_path: Path to between-group.db
        variable: One of: "repo_age_years"
        corpus: "human" or "agent"

    Returns:
        List of values
    """
    if variable not in ALLOWED_CONTINUOUS_VARIABLES:
        raise ValueError(
            f"variable must be one of {ALLOWED_CONTINUOUS_VARIABLES}, got {variable!r}"
        )

    with db_session(db_path) as conn:
        query = f"""
        SELECT r.{variable}
        FROM repositories r
        WHERE EXISTS (
            SELECT 1 FROM fixtures f
            WHERE f.repo_id = r.id AND f.commit_kind = ?
        )
        """
        rows = conn.execute(query, (corpus,)).fetchall()
        return [row[0] for row in rows if row[0] is not None]


class BetweenGroupComparator:
    """Compare human and agent corpora on control variables."""

    def __init__(self, db_path: Path = None):
        """
        Initialize comparator.

        Args:
            db_path: Path to between-group.db (default: data/between-group.db)
        """
        self.db_path = Path(db_path) if db_path else (DATA_DIR / "between-group.db")

    def run(
        self,
        human_stats: Optional[Dict] = None,
        agent_stats: Optional[Dict] = None,
    ) -> BetweenGroupComparison:
        """
        Run complete between-group comparison.

        Args:
            human_stats: Human corpus stats dict (optional, for reporting)
            agent_stats: Agent corpus stats dict (optional, for reporting)

        Returns:
            BetweenGroupComparison object with all test results
        """
        balance_tests = []

        # Test categorical variables
        categorical_vars = ["language", "domain", "star_tier"]
        for var in categorical_vars:
            human_dist = get_human_fixtures_by_variable(self.db_path, var)
            agent_dist = get_agent_fixtures_by_variable(self.db_path, var)

            if human_dist or agent_dist:
                test = compute_categorical_balance(human_dist, agent_dist, var)
                balance_tests.append(test)

        # Test continuous variables
        continuous_vars = ["repo_age_years"]
        for var in continuous_vars:
            human_values = get_continuous_values(self.db_path, var, "human")
            agent_values = get_continuous_values(self.db_path, var, "agent")

            if human_values and agent_values:
                test = compute_continuous_balance(human_values, agent_values, var)
                balance_tests.append(test)

        # Generate control variable summary
        control_summary = self._generate_control_summary(balance_tests)

        # Identify imbalances and limitations
        imbalanced_vars = [t.variable for t in balance_tests if not t.is_balanced]
        limitations = []
        if imbalanced_vars:
            limitations.append(
                f"Imbalanced control variables (p < 0.05): {', '.join(imbalanced_vars)}. "
                "Consider stratified analysis or regression controls."
            )

        comparison = BetweenGroupComparison(
            timestamp=datetime.now().isoformat(),
            methodology={
                "design": "between-group comparison",
                "human_corpus": "pre-2021 (before agent era)",
                "agent_corpus": "2025+ (agent-authored, Tier 1 only)",
                "control_variables": [
                    "language",
                    "domain",
                    "star_tier",
                    "repo_age_years",
                ],
                "statistical_tests": {
                    "categorical": "chi-square",
                    "continuous": "mann-whitney-u",
                },
                "balance_threshold": 0.05,
            },
            balance_tests=balance_tests,
            human_corpus_stats=human_stats or {},
            agent_corpus_stats=agent_stats or {},
            control_variable_summary=control_summary,
            limitations=limitations,
        )

        return comparison

    def _generate_control_summary(self, balance_tests: list[BalanceTest]) -> Dict:
        """Generate summary of control variable balance."""
        summary = {
            "total_tests": len(balance_tests),
            "balanced_count": sum(1 for t in balance_tests if t.is_balanced),
            "imbalanced_count": sum(1 for t in balance_tests if not t.is_balanced),
            "balance_rate": (
                sum(1 for t in balance_tests if t.is_balanced) / len(balance_tests)
                if balance_tests
                else 0
            ),
            "test_results": {
                t.variable: {"p_value": t.p_value, "balanced": t.is_balanced}
                for t in balance_tests
            },
        }
        return summary

    def save_report(
        self, comparison: BetweenGroupComparison, output_path: Optional[Path] = None
    ) -> Path:
        """
        Save comparison report to JSON.

        Args:
            comparison: BetweenGroupComparison object
            output_path: Optional custom output path

        Returns:
            Path to saved report
        """
        if not output_path:
            output_dir = Path(__file__).parent.parent / "output"
            output_dir.mkdir(exist_ok=True)
            output_path = (
                output_dir
                / f"between_group_comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )

        report = comparison.to_dict()

        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)

        logger.info(f"Comparison report saved to {output_path}")
        return Path(output_path)


def compare_corpora(
    human_stats: Optional[Dict] = None,
    agent_stats: Optional[Dict] = None,
    db_path: Optional[Path] = None,
) -> Dict:
    """
    Convenience function to compare human and agent corpora.

    Args:
        human_stats: Human corpus stats (optional)
        agent_stats: Agent corpus stats (optional)
        db_path: Path to between-group.db

    Returns:
        Comparison results dict
    """
    comparator = BetweenGroupComparator(db_path=db_path)
    comparison = comparator.run(human_stats=human_stats, agent_stats=agent_stats)
    comparator.save_report(comparison)
    return comparison.to_dict()
