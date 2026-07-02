"""Sampling utilities for stratified human fixture selection.

This module provides a deterministic, reproducible stratified sampler that
attempts to preserve within-repo representation while meeting per-language
targets. Fallback strategies (expand pool or reduce targets) are intentionally
not implemented here — they'll be added later after initial collection tests.
"""

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
