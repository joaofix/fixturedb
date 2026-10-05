"""Statistical-test primitives for control-variable balance checks.

Chi-square tests for categorical variables and Mann-Whitney U tests for
continuous variables, with effect sizes (Cramér's V, Cliff's delta) and their
magnitude labels. The research-question scripts in
collection/research_questions/ use these to check whether two repository
samples are comparable on control variables.
"""

import math
import statistics
from dataclasses import asdict, dataclass, field
from typing import Dict, Optional

ALLOWED_CATEGORICAL_VARIABLES = {"language", "domain"}
ALLOWED_CONTINUOUS_VARIABLES = {"repo_age_years"}
ALLOWED_VARIABLES = ALLOWED_CATEGORICAL_VARIABLES | ALLOWED_CONTINUOUS_VARIABLES

from scipy.stats import chi2_contingency, mannwhitneyu

from collection.logging_utils import get_logger


logger = get_logger(__name__)


@dataclass
class BalanceTest:
    """Result of a single control variable balance test."""

    variable: str  # e.g., "domain", "repo_age_years"
    test_type: str  # "chi-square" or "mann-whitney-u"
    p_value: float
    is_balanced: bool  # p >= 0.05
    statistic: Optional[float] = None
    details: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Return the test result as a plain dict, for JSON serialization."""
        return asdict(self)


def _cramers_v(chi2: float, n: int) -> Optional[float]:
    """Cramér's V effect size from a chi2 statistic, for the 2xK contingency
    tables every caller here builds (two groups being compared, K
    categories). V's normalization divides by min(rows-1, cols-1) =
    min(1, K-1), which is always 1 whenever K>=2 (the only case this gets
    called -- K<2 has no variation to test at all), so V simplifies to
    sqrt(chi2/n). Standard categorical effect size in SE empirical
    research; unlike the p-value, it doesn't grow with sample size, so it's
    what actually answers "how big is this difference," not just "is it
    non-zero." See _cramers_v_magnitude() for the conventional thresholds.
    """
    if n == 0:
        return None
    return math.sqrt(chi2 / n)


def _cramers_v_magnitude(v: Optional[float]) -> Optional[str]:
    if v is None:
        return None
    if v < 0.1:
        return "negligible"
    if v < 0.3:
        return "small"
    if v < 0.5:
        return "medium"
    return "large"


def _cliffs_delta(u_statistic: float, n1: int, n2: int) -> Optional[float]:
    """Cliff's delta effect size, derived directly from the U statistic
    mannwhitneyu() already computes (delta = 2*U/(n1*n2) - 1) -- no second,
    more expensive pairwise computation needed. Standard non-parametric
    effect size for Mann-Whitney U in SE empirical research (Vargha &
    Delaney, 2000), used instead of Cohen's d since it doesn't assume
    normality, matching why Mann-Whitney was chosen over a t-test in the
    first place. Positive means the *first* array passed to
    mannwhitneyu() -- human_vals in compute_continuous_balance() below --
    tends to have larger values than the second (agent_vals). See
    _cliffs_delta_magnitude() for the conventional thresholds.
    """
    if n1 == 0 or n2 == 0:
        return None
    return (2 * u_statistic) / (n1 * n2) - 1


def _cliffs_delta_magnitude(delta: Optional[float]) -> Optional[str]:
    if delta is None:
        return None
    d = abs(delta)
    if d < 0.147:
        return "negligible"
    if d < 0.33:
        return "small"
    if d < 0.474:
        return "medium"
    return "large"


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

    # A category can be a real key in both dicts (e.g. a fixed-shape
    # {"setup": 0, "teardown": 0, "other": 0} distribution some callers
    # always initialize) yet have zero count on *both* sides -- an
    # all-zero column chi2_contingency can't compute an expected frequency
    # for (division by zero internally), regardless of how large the
    # other columns' samples are. That's not a small-sample problem to
    # work around, it's a genuinely empty category with no variation to
    # test -- drop it, the same way an all-zero *row* is already handled
    # above via the insufficient_data check.
    kept = [
        i for i in range(len(all_categories))
        if human_counts[i] > 0 or agent_counts[i] > 0
    ]
    if len(kept) < 2:
        return BalanceTest(
            variable=variable,
            test_type="chi-square",
            p_value=1.0,
            is_balanced=True,
            details={"reason": "insufficient_data"},
        )
    if len(kept) < len(all_categories):
        all_categories = [all_categories[i] for i in kept]
        human_counts = [human_counts[i] for i in kept]
        agent_counts = [agent_counts[i] for i in kept]

    try:
        chi2, p_value, dof, expected = chi2_contingency([human_counts, agent_counts])
        n_total = sum(human_counts) + sum(agent_counts)
        cramers_v = _cramers_v(chi2, n_total)

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
                "cramers_v": cramers_v,
                "cramers_v_magnitude": _cramers_v_magnitude(cramers_v),
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
        # If all values are identical, distributions are trivially balanced
        if len(set(human_vals)) == 1 and len(set(agent_vals)) == 1 and human_vals[0] == agent_vals[0]:
            return BalanceTest(
                variable=variable,
                test_type="mann-whitney-u",
                p_value=1.0,
                is_balanced=True,
                statistic=0.0,
                details={
                    "human_count": len(human_vals),
                    "agent_count": len(agent_vals),
                    "human_mean": float(human_vals[0]),
                    "agent_mean": float(agent_vals[0]),
                    "human_median": float(human_vals[0]),
                    "agent_median": float(agent_vals[0]),
                    "u_statistic": 0.0,
                    "cliffs_delta": 0.0,
                    "cliffs_delta_magnitude": "negligible",
                    "reason": "identical_distributions",
                },
            )

        statistic, p_value = mannwhitneyu(
            human_vals, agent_vals, alternative="two-sided"
        )
        cliffs_delta = _cliffs_delta(statistic, len(human_vals), len(agent_vals))

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
                    float(statistics.median(human_vals)) if human_vals else None
                ),
                "agent_median": (
                    float(statistics.median(agent_vals)) if agent_vals else None
                ),
                "u_statistic": float(statistic),
                "cliffs_delta": cliffs_delta,
                "cliffs_delta_magnitude": _cliffs_delta_magnitude(cliffs_delta),
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


