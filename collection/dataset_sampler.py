"""
Dataset Sampler Module

Implements stratified random sampling to create balanced datasets.
Ensures both fixturedb-human and fixturedb-agent have identical fixture counts
while maintaining statistical distribution within tolerance.
"""

import random
from dataclasses import dataclass, field
from typing import Dict, List

from collection.logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class StratificationResult:
    """Result of stratified sampling operation."""

    sampled_ids: List[int] = field(default_factory=list)
    sampled_count: int = 0
    target_count: int = 0
    distribution_check: Dict[str, Dict] = field(default_factory=dict)
    random_seed: int = 42
    reproducible: bool = True
    stratify_by: str = "fixture_type"


class StratifiedSampler:
    """Stratified random sampling with distribution validation."""

    def __init__(self, random_seed: int = 42):
        """
        Initialize sampler with random seed for reproducibility.

        Args:
            random_seed: Random seed for reproducible sampling (default: 42)
        """
        self.random_seed = random_seed
        random.seed(random_seed)

    def sample(
        self,
        fixtures: List[Dict],
        target_count: int,
        stratify_by: str = "fixture_type",
        tolerance: float = 0.02,
    ) -> StratificationResult:
        """
        Sample fixtures maintaining distribution.

        CRITICAL: Ensures stratification within tolerance (default 2%).
        For example, if original has 60% pytest and 40% unittest,
        sampled should also be 60/40 (within 2%).

        Args:
            fixtures: List of fixture dicts with stratification column
            target_count: Exact number of fixtures to sample
            stratify_by: Column name for stratification (fixture_type, scope, etc.)
            tolerance: Distribution tolerance as decimal (0.02 = 2%)

        Returns:
            StratificationResult with sampled IDs and validation results

        Raises:
            ValueError: If target_count exceeds population or invalid config
        """
        if not fixtures:
            raise ValueError("Cannot sample from empty fixture list")

        if target_count > len(fixtures):
            raise ValueError(
                f"Target count {target_count} exceeds population {len(fixtures)}"
            )

        # Group fixtures by stratification dimension
        by_strata = self._group_by_strata(fixtures, stratify_by)

        logger.info(
            f"Sampling {target_count} from {len(fixtures)} fixtures "
            f"(stratified by {stratify_by})"
        )
        logger.info(f"Strata: {', '.join(by_strata.keys())}")

        # Sample proportionally from each stratum
        sampled = []
        for stratum_value, group in by_strata.items():
            proportion = len(group) / len(fixtures)
            count_for_stratum = round(target_count * proportion)

            # Sample from this stratum
            if count_for_stratum > len(group):
                count_for_stratum = len(group)

            sampled_from_stratum = random.sample(group, count_for_stratum)
            sampled.extend(sampled_from_stratum)

            logger.debug(
                f"  {stratum_value}: {len(sampled_from_stratum)}/{len(group)} "
                f"({proportion * 100:.1f}%)"
            )

        # Adjust to exact target if needed (rounding may cause differences).
        # Note: this must run even when `sampled` is still empty (every
        # stratum's proportional count rounded down to 0), or a small
        # target_count relative to the number of strata silently produces an
        # empty/under-filled sample instead of backfilling to target_count.
        while len(sampled) < target_count:
            # Add more fixtures to reach exact target
            additional_needed = target_count - len(sampled)

            # Sample from all fixtures excluding already sampled ones
            current_ids = {f["id"] for f in sampled}
            remaining = [f for f in fixtures if f["id"] not in current_ids]

            if not remaining:
                break

            additional = random.sample(
                remaining, min(additional_needed, len(remaining))
            )
            sampled.extend(additional)

        # Trim to exact target if overshoot occurred
        sampled = sampled[:target_count]

        # Extract IDs
        sampled_ids: List[int] = [f["id"] for f in sampled]

        # Validate distribution
        distribution_check = self._validate_distribution(
            fixtures,
            sampled,
            stratify_by,
            tolerance,
        )

        result = StratificationResult(
            sampled_ids=sampled_ids,
            sampled_count=len(sampled_ids),
            target_count=target_count,
            distribution_check=distribution_check,
            random_seed=self.random_seed,
            reproducible=True,
            stratify_by=stratify_by,
        )

        return result

    def _group_by_strata(
        self,
        fixtures: List[Dict],
        stratify_by: str,
    ) -> Dict[str, List[Dict]]:
        """
        Group fixtures by stratification dimension.

        Args:
            fixtures: List of fixture dicts
            stratify_by: Column name for grouping

        Returns:
            Dict mapping stratum value to list of fixtures
        """
        groups: Dict[str, List[Dict]] = {}

        for fixture in fixtures:
            stratum_value = fixture.get(stratify_by, "unknown")
            if stratum_value not in groups:
                groups[stratum_value] = []
            groups[stratum_value].append(fixture)

        return groups

    def _validate_distribution(
        self,
        original: List[Dict],
        sampled: List[Dict],
        stratify_by: str,
        tolerance: float,
    ) -> Dict[str, Dict]:
        """
        Validate that sampling maintained distribution within tolerance.

        Args:
            original: Original fixture list
            sampled: Sampled fixture list
            stratify_by: Stratification column
            tolerance: Acceptable deviation (0.02 = 2%)

        Returns:
            Dict with validation results per stratum:
            {
                stratum: {
                    'original_ratio': float,
                    'sampled_ratio': float,
                    'deviation': float,
                    'tolerance_met': bool,
                }
            }
        """
        results = {}

        # Get all strata from original
        strata = {f.get(stratify_by, "unknown") for f in original}

        for stratum_value in strata:
            original_count = len(
                [f for f in original if f.get(stratify_by) == stratum_value]
            )
            sampled_count = len(
                [f for f in sampled if f.get(stratify_by) == stratum_value]
            )

            orig_ratio = original_count / len(original) if original else 0
            samp_ratio = sampled_count / len(sampled) if sampled else 0
            deviation = abs(orig_ratio - samp_ratio)
            tolerance_met = deviation <= tolerance

            results[str(stratum_value)] = {
                "original_ratio": round(orig_ratio, 4),
                "sampled_ratio": round(samp_ratio, 4),
                "deviation": round(deviation, 4),
                "tolerance_met": tolerance_met,
            }

            status = "✓" if tolerance_met else "✗"
            logger.debug(
                f"  {stratum_value}: {orig_ratio * 100:.1f}% → {samp_ratio * 100:.1f}% "
                f"({status})"
            )

        return results

    def get_sample_statistics(self, result: StratificationResult) -> Dict:
        """
        Generate summary statistics from sampling result.

        Args:
            result: StratificationResult from sample()

        Returns:
            Dict with statistics
        """
        all_tolerances_met = all(
            v["tolerance_met"] for v in result.distribution_check.values()
        )

        return {
            "target_count": result.target_count,
            "sampled_count": result.sampled_count,
            "sampling_ratio": round(result.sampled_count / result.target_count, 4),
            "stratify_by": result.stratify_by,
            "random_seed": result.random_seed,
            "all_strata_within_tolerance": all_tolerances_met,
            "strata_count": len(result.distribution_check),
        }
