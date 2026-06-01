from collections import Counter
from pathlib import Path

from collection.sampling import stratified_sample_by_language


def make_candidates(lang: str, repo_counts: dict) -> list:
    """Create candidate fixtures list. repo_counts maps repo_id->num_fixtures."""
    candidates = []
    for repo_id, count in repo_counts.items():
        for i in range(count):
            candidates.append(
                {
                    "repo_id": repo_id,
                    "language": lang,
                    "name": f"f_{repo_id}_{i}",
                }
            )
    return candidates


def test_stratified_sample_basic_distribution():
    # Simulate two languages with varying repo distributions
    python_repos = {1: 50, 2: 30, 3: 20}  # total 100
    java_repos = {10: 10, 11: 5}  # total 15

    py_candidates = make_candidates("python", python_repos)
    java_candidates = make_candidates("java", java_repos)

    all_candidates = py_candidates + java_candidates

    targets = {"python": 40, "java": 10}

    selected = stratified_sample_by_language(all_candidates, targets, seed=123)

    # Validate totals match targets when sufficient candidates exist
    counts = Counter([c["language"] for c in selected])
    assert counts["python"] == 40
    # java target is 10 but only 15 available -> should select min(available, target) == 10
    assert counts["java"] == 10

    # Ensure per-repo selections do not exceed available counts
    py_repo_counts = Counter(
        [c["repo_id"] for c in selected if c["language"] == "python"]
    )
    for rid, ct in py_repo_counts.items():
        assert ct <= python_repos[rid]


def test_stratified_when_insufficient_candidates():
    # if target > available, all candidates should be returned for that language
    repo_map = {1: 2, 2: 1}
    candidates = make_candidates("python", repo_map)
    targets = {"python": 10}
    selected = stratified_sample_by_language(candidates, targets)
    assert len(selected) == sum(repo_map.values())
