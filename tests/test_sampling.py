from collection.sampling import stratified_sample_by_language


def make_candidate(repo_id, language, name="f"):
    return {
        "repo_id": repo_id,
        "language": language,
        "name": name,
        "start_line": 1,
    }


def test_stratified_sample_exact_target():
    # Build candidates: repo A has 5 py fixtures, repo B has 5 py fixtures
    candidates = []
    for i in range(5):
        candidates.append({**make_candidate("A", "py", f"fA{i}"), "repo_id": "A"})
    for i in range(5):
        candidates.append({**make_candidate("B", "py", f"fB{i}"), "repo_id": "B"})

    targets = {"py": 6}
    selected = stratified_sample_by_language(candidates, targets, seed=123)
    # Should select exactly 6 fixtures for py
    assert len(selected) == 6
    assert all(s["language"] == "py" for s in selected)


def test_stratified_sample_insufficient_pool():
    # Only 3 candidates but target is 5 -> should return all 3
    candidates = [make_candidate("A", "js", f"f{i}") for i in range(3)]
    targets = {"js": 5}
    selected = stratified_sample_by_language(candidates, targets, seed=1)
    assert len(selected) == 3


def test_stratified_sample_deterministic():
    # Determinism: same seed => same selection order
    candidates = []
    for rid in ("A", "B", "C"):
        for i in range(4):
            candidates.append(
                {**make_candidate(rid, "py", f"{rid}{i}"), "repo_id": rid}
            )

    targets = {"py": 5}
    s1 = stratified_sample_by_language(candidates, targets, seed=999)
    s2 = stratified_sample_by_language(candidates, targets, seed=999)
    assert [f["name"] for f in s1] == [f["name"] for f in s2]
