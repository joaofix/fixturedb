"""Sampling utilities for stratified human fixture selection.

This module provides a deterministic, reproducible stratified sampler that
attempts to preserve within-repo representation while meeting per-language
targets. Fallback strategies (expand pool or reduce targets) are intentionally
not implemented here — they'll be added later after initial collection tests.
"""

import math
import random
from collections import defaultdict
from typing import Dict, List


def stratified_sample_by_language(
    candidates: List[dict],
    targets: Dict[str, int],
    seed: int = 42,
) -> List[dict]:
    """
    Stratified sampling by language and repository.

    Args:
        candidates: list of fixture dicts. Each dict must include at least
            `repo_id` and `language` keys.
        targets: mapping language->desired_count
        seed: RNG seed for deterministic selection

    Returns:
        List of selected candidate dicts (length <= sum(targets.values())).
    """
    rnd = random.Random(seed)

    # Group candidates by language then by repo
    by_lang: Dict[str, Dict[str, List[dict]]] = defaultdict(lambda: defaultdict(list))
    for c in candidates:
        lang = c.get("language") or c.get("framework") or "unknown"
        repo_id = c.get("repo_id") or "unknown"
        by_lang[lang][repo_id].append(c)

    selected: List[dict] = []

    for lang, target in targets.items():
        repo_groups: Dict[str, List[dict]] = by_lang.get(lang, {})
        if not repo_groups:
            continue

        # Compute proportional quotas per repo based on available counts
        total_available = sum(len(v) for v in repo_groups.values())
        if total_available <= target:
            # Not enough candidates: take all
            for v in repo_groups.values():
                selected.extend(v)
            continue

        # Assign initial quotas
        quotas = {}
        for repo_id, items in repo_groups.items():
            proportion = len(items) / total_available
            quotas[repo_id] = int(proportion * target)

        # Ensure at least 1 for repos with items until we reach target
        # Fill remaining slots randomly across repos weighted by leftover capacity
        assigned = sum(quotas.values())
        remaining = target - assigned

        # Build a flat pool of (repo_id, item) for random draws when filling
        repo_pools = {rid: list(items)[:] for rid, items in repo_groups.items()}
        for rid in repo_pools:
            rnd.shuffle(repo_pools[rid])

        # Collect initial selections per repo
        for rid, q in quotas.items():
            take = min(q, len(repo_pools[rid]))
            for _ in range(take):
                selected.append(repo_pools[rid].pop())

        # Fill remaining deterministically by random choices across repos with remaining items
        available_repos = [rid for rid, pool in repo_pools.items() if pool]
        while remaining > 0 and available_repos:
            rid = rnd.choice(available_repos)
            selected.append(repo_pools[rid].pop())
            remaining -= 1
            if not repo_pools[rid]:
                available_repos.remove(rid)

    return selected


def cochran_sample_size(
    population: int,
    margin: float = 0.05,
    confidence_z: float = 1.96,
    p: float = 0.5,
) -> int:
    """Minimum sample size to estimate a proportion within `margin` at the
    confidence level implied by `confidence_z`, corrected for finite
    `population`. Capped at `population`.

    Used by `toy --stratified` to size each language's validation sample
    against its own real population rather than applying one flat count
    uniformly (or globally) across languages.
    """
    if population <= 0:
        return 0
    n0 = (confidence_z**2) * p * (1 - p) / (margin**2)
    n = n0 / (1 + (n0 - 1) / population)
    return min(population, math.ceil(n))


def sample_stratified_by_population(
    rows: List[dict],
    language_key: str = "language",
    language: str | None = None,
) -> List[dict]:
    """Per-language sample of `rows`, each language's size set by
    `cochran_sample_size` against that language's own real row count.

    Unlike `stratified_sample_by_language`, this has no caller-supplied
    `targets` -- the sample size itself is derived statistically per
    language, which is what a representative validation run needs.
    """
    grouped: Dict[str, List[dict]] = defaultdict(list)
    for row in rows:
        lang = (row.get(language_key) or "").strip().lower()
        if lang:
            grouped[lang].append(row)

    if language:
        grouped = {language: grouped.get(language, [])}

    sampled: List[dict] = []
    for lang in sorted(grouped):
        pool = grouped[lang]
        n = cochran_sample_size(len(pool))
        sampled.extend(pool[:n])
    return sampled
