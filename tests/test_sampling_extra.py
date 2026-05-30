from collection.sampling import stratified_sample_by_language


def make_candidate(repo_id, language, name="f"):
    return {"repo_id": repo_id, "language": language, "name": name, "start_line": 1}


def test_sampling_no_targets_returns_empty():
    candidates = [make_candidate("A", "py"), make_candidate("B", "py")]
    selected = stratified_sample_by_language(candidates, {}, seed=1)
    assert selected == []


def test_sampling_multiple_languages_independent():
    candidates = [
        make_candidate("A", "py", "p1"),
        make_candidate("B", "py", "p2"),
        make_candidate("C", "js", "j1"),
    ]
    targets = {"py": 2, "js": 1}
    sel = stratified_sample_by_language(candidates, targets, seed=2)
    assert len(sel) == 3
    assert sum(1 for s in sel if s["language"] == "py") == 2
    assert sum(1 for s in sel if s["language"] == "js") == 1


def test_sampling_quota_with_small_repo_pools():
    # Repo A has 3 items, repo B has 1 item, target 2 -> should pick 2 distinct items
    candidates = [make_candidate("A", "py", f"a{i}") for i in range(3)]
    candidates += [make_candidate("B", "py", "b0")]
    targets = {"py": 2}
    sel = stratified_sample_by_language(candidates, targets, seed=10)
    assert len(sel) == 2
    names = {s["name"] for s in sel}
    assert len(names) == 2
