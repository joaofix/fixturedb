"""
Dataset Sampler Module

Implements stratified random sampling to create balanced datasets.
Ensures both fixturedb-human and fixturedb-agent have identical fixture counts
while maintaining statistical distribution within tolerance.
"""

import random
from dataclasses import dataclass, field
from typing import Dict, List

from collection.config import DATASET_C_SAMPLING_SEED
from collection.logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class RepoSamplingResult:
    """Result of sample_repos_by_language()'s whole-repo stratified sample."""

    sampled_repo_ids: List[int] = field(default_factory=list)
    sampled_fixture_count: int = 0
    target_count: int = 0
    distribution_check: Dict[str, Dict] = field(default_factory=dict)
    random_seed: int = DATASET_C_SAMPLING_SEED


def _allocate_quotas_with_shortfall_reallocation(
    lang_caps: Dict[str, float],
    target_weights: Dict[str, float],
    target_count: float,
) -> Dict[str, float]:
    """Water-filling allocation: each language's quota is `target_count *
    (its share of target_weights)`, capped at `lang_caps[language]` (that
    language's real ceiling -- e.g. its whole fixture population in
    Dataset C). When a language's computed share would exceed its cap, it's
    fixed at its cap instead and the shortfall is redistributed across the
    *remaining* (not-yet-capped) languages, re-normalized among themselves
    -- repeated until stable, since redistributing to one language can
    itself push it over its own cap (bounded by len(lang_caps) iterations).

    Only languages present in both `lang_caps` and `target_weights` (with a
    positive weight) can receive a nonzero quota:
    - A language in `target_weights` absent from `lang_caps` (nothing to
      sample) contributes nothing and is excluded from consideration from
      the start -- its whole share cascades into the others via the same
      mechanism, no special-casing needed.
    - A language in `lang_caps` absent from `target_weights` (the target
      distribution has none of it) gets quota 0 -- correct for "match this
      other distribution's mix": a language it doesn't have shouldn't
      appear in the output either.

    `target_weights` need not sum to 1 -- every use is a ratio
    (`weight / sum of remaining weights`), so raw counts work the same as
    pre-normalized fractions.

    Returns one entry per key in `lang_caps` (0.0 for any that got no
    quota), never partial -- every language sample_repos_by_language()
    iterates over has a quota to look up.
    """
    remaining_langs: Dict[str, float] = {
        lang: weight
        for lang, weight in target_weights.items()
        if lang in lang_caps and weight > 0
    }
    finalized: Dict[str, float] = {}
    remaining_total = target_count

    while remaining_langs:
        weight_sum = sum(remaining_langs.values())
        if weight_sum <= 0:
            break

        shares = {
            lang: remaining_total * (weight / weight_sum)
            for lang, weight in remaining_langs.items()
        }
        overflowing = {
            lang: lang_caps[lang] for lang, share in shares.items() if share > lang_caps[lang]
        }

        if not overflowing:
            finalized.update(shares)
            break

        for lang, capped_quota in overflowing.items():
            finalized[lang] = capped_quota
            remaining_total -= capped_quota
            del remaining_langs[lang]

    for language in lang_caps:
        finalized.setdefault(language, 0.0)

    return finalized


def sample_repos_by_language(
    repos: List[Dict],
    target_count: int,
    tolerance: float = 0.02,
    seed: int = DATASET_C_SAMPLING_SEED,
    target_proportions: Dict[str, float] | None = None,
) -> RepoSamplingResult:
    """Randomly sample whole repos, stratified by language, until the total
    fixture count is as close as possible to `target_count`.

    Unlike `StratifiedSampler.sample()` below (which samples individual
    fixture *rows*), this never splits a repo -- a repo's fixtures are
    either entirely included or entirely excluded. This matters for Dataset
    C: RQ2's setup-to-teardown ratio and has_teardown_pair rate are computed
    per repo, so a fixture-level sample could split a repo's setup fixture
    from its teardown fixture, fabricating an artificial "zero-teardown"
    repo that's a sampling artifact, not a fact about the data.

    Args:
        repos: One dict per repo: {"repo_id": int, "language": str,
            "fixture_count": int}. `fixture_count` is the repo's total
            fixture count -- the whole point is this can't be subdivided.
        target_count: Desired total sampled fixture count.
        tolerance: Passed through to distribution_check's tolerance_met flag
            (diagnostic only -- doesn't affect sampling, see
            StratifiedSampler.sample()'s docstring for the same convention).
        seed: Random seed -- defaults to the project-wide
            DATASET_C_SAMPLING_SEED (config.py / study_parameters.yaml),
            not a fresh literal, so a plain call is reproducible with the
            same seed used everywhere else Dataset C sampling happens.
        target_proportions: Optional per-language weights (raw counts or
            fractions -- ratio-based, need not sum to 1) to stratify
            against instead of `repos`' own mix -- e.g. another dataset's
            language-by-repo-count distribution. When a language's target
            share exceeds what `repos` actually has available for it, that
            language is capped at everything it has and the shortfall is
            redistributed across the other languages
            (`_allocate_quotas_with_shortfall_reallocation()`) rather than
            discarded or failed on. `None` (default) preserves the
            original behavior: proportions computed from `repos`' own
            total fixture counts (Dataset C's own mix, unaffected by any
            other dataset).

    Returns:
        RepoSamplingResult. `sampled_fixture_count` will not exactly equal
        `target_count` -- repos are indivisible chunks, so this is the
        closest achievable total, not an exact hit.
    """
    if not repos:
        raise ValueError("Cannot sample from an empty repo list")

    total_fixtures = sum(r["fixture_count"] for r in repos)
    if total_fixtures == 0:
        raise ValueError("Cannot sample: every repo has fixture_count 0")

    by_language: Dict[str, List[Dict]] = {}
    for repo in repos:
        by_language.setdefault(repo["language"], []).append(repo)

    lang_caps = {
        language: sum(r["fixture_count"] for r in lang_repos)
        for language, lang_repos in by_language.items()
    }

    if target_proportions is None:
        quotas = {
            language: target_count * (lang_total / total_fixtures)
            for language, lang_total in lang_caps.items()
        }
        target_weight_sum = total_fixtures
        target_weights = lang_caps
    else:
        quotas = _allocate_quotas_with_shortfall_reallocation(
            lang_caps, target_proportions, target_count
        )
        target_weight_sum = sum(target_proportions.values()) or 1
        target_weights = target_proportions

    rng = random.Random(seed)
    sampled_repo_ids: List[int] = []
    sampled_fixture_count = 0
    language_totals: Dict[str, int] = {}
    language_repo_counts: Dict[str, int] = {}

    for language, lang_repos in by_language.items():
        quota = quotas[language]

        shuffled = lang_repos[:]
        rng.shuffle(shuffled)

        running_total = 0
        included: List[Dict] = []
        for repo in shuffled:
            if running_total >= quota:
                break
            # Stop at whichever boundary -- including this repo, or not --
            # lands closer to the quota, rather than always overshooting by
            # stopping at first-exceed.
            with_repo = running_total + repo["fixture_count"]
            if abs(with_repo - quota) < abs(running_total - quota):
                included.append(repo)
                running_total = with_repo
            else:
                break

        sampled_repo_ids.extend(r["repo_id"] for r in included)
        sampled_fixture_count += running_total
        language_totals[language] = running_total
        language_repo_counts[language] = len(included)

        logger.debug(
            f"  {language}: {len(included)}/{len(lang_repos)} repos, "
            f"{running_total}/{round(quota)} fixtures (quota)"
        )

    distribution_check: Dict[str, Dict] = {}
    for language in by_language:
        lang_total = lang_caps[language]
        original_ratio = lang_total / total_fixtures
        target_ratio = target_weights.get(language, 0) / target_weight_sum
        sampled_ratio = (
            language_totals[language] / sampled_fixture_count
            if sampled_fixture_count
            else 0.0
        )
        deviation = abs(target_ratio - sampled_ratio)
        distribution_check[language] = {
            "original_ratio": round(original_ratio, 4),
            "target_ratio": round(target_ratio, 4),
            "sampled_ratio": round(sampled_ratio, 4),
            "deviation": round(deviation, 4),
            "tolerance_met": deviation <= tolerance,
            "dataset_c_available_fixture_count": lang_total,
            "dataset_c_available_repo_count": len(by_language[language]),
            "sampled_fixture_count": language_totals[language],
            "sampled_repo_count": language_repo_counts[language],
        }

    return RepoSamplingResult(
        sampled_repo_ids=sampled_repo_ids,
        sampled_fixture_count=sampled_fixture_count,
        target_count=target_count,
        distribution_check=distribution_check,
        random_seed=seed,
    )


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
