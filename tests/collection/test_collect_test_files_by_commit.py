"""collect_test_files_by_commit (one git log per repository) must give exactly what
collect_test_files_for_commit (PyDriller, one call per commit) gives."""

import os
import subprocess
from pathlib import Path

import pytest

from collection.test_commit_utils import collect_test_files_by_commit, collect_test_files_for_commit

ENV = dict(
    os.environ,
    GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
    GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid",
)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, env=ENV, check=True, capture_output=True, text=True).stdout.strip()


def _write(repo: Path, rel: str, text: str = "x") -> None:
    target = repo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--allow-empty", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def varied_repo(tmp_path):
    """A repository covering: a root commit, adds in nested test directories, a modify,
    a delete, a test->test rename, a non-test->test rename, a test->non-test rename,
    a file name with a space and non-ASCII letters, and a commit with no test files."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    shas = {}
    _write(repo, "tests/test_a.py", "a1")
    _write(repo, "src/app.py", "app")
    _write(repo, "README.md", "readme")
    shas["root"] = _commit(repo, "root")
    _write(repo, "tests/sub/test_b.py", "b")
    _write(repo, "tests/x y.py", "xy")
    _write(repo, "tests/ação_test.py", "u")
    shas["adds"] = _commit(repo, "adds")
    _write(repo, "tests/test_a.py", "a2")
    shas["modify"] = _commit(repo, "modify")
    (repo / "tests/test_a.py").unlink()
    shas["delete"] = _commit(repo, "delete")
    _git(repo, "mv", "tests/sub/test_b.py", "tests/sub/test_renamed.py")
    shas["rename_test_to_test"] = _commit(repo, "rename test to test")
    _git(repo, "mv", "src/app.py", "tests/moved_app.py")
    shas["rename_nontest_to_test"] = _commit(repo, "rename non-test to test")
    (repo / "lib").mkdir()
    _git(repo, "mv", "tests/x y.py", "lib/y.py")
    shas["rename_test_to_nontest"] = _commit(repo, "rename test to non-test")
    _write(repo, "docs/guide.md", "g")
    shas["no_tests"] = _commit(repo, "no test files")
    return repo, shas


def test_matches_the_per_commit_pydriller_result_for_every_commit(varied_repo):
    repo, shas = varied_repo
    batched = collect_test_files_by_commit(repo, shas.values(), "python")

    for name, sha in shas.items():
        expected = collect_test_files_for_commit(repo, sha, "python")
        assert batched[sha] == expected, name

    # the comparison has to exercise real test files, not only empty results
    assert any(batched[shas["adds"]])
    assert batched[shas["rename_nontest_to_test"]] == ["tests/moved_app.py"]
    assert batched[shas["rename_test_to_nontest"]] == []
    assert batched[shas["delete"]] == []


def test_a_missing_commit_maps_to_an_empty_list_and_does_not_disturb_the_others(varied_repo):
    repo, shas = varied_repo
    missing = "0" * 40
    batched = collect_test_files_by_commit(repo, [missing, shas["adds"]], "python")

    assert batched[missing] == []
    assert batched[shas["adds"]] == collect_test_files_for_commit(repo, shas["adds"], "python")


def test_no_commits_gives_an_empty_mapping(varied_repo):
    repo, _ = varied_repo
    assert collect_test_files_by_commit(repo, [], "python") == {}
    assert collect_test_files_by_commit(repo, ["", "   "], "python") == {}


def test_a_root_commit_lists_every_file_it_adds_as_pydriller_does(varied_repo):
    repo, shas = varied_repo
    batched = collect_test_files_by_commit(repo, [shas["root"]], "python")
    assert batched[shas["root"]] == collect_test_files_for_commit(repo, shas["root"], "python")


def test_the_clone_uses_no_blobs_for_test_commits(monkeypatch, tmp_path):
    """The filter's clone must request the blobless filter, and only that step's clone."""
    from contextlib import contextmanager

    from collection import test_commit_filter as tcf

    captured = {}

    @contextmanager
    def fake_clone(clone_url, repo_full_name, **kwargs):
        captured.update(kwargs)
        yield None

    monkeypatch.setattr(tcf, "temp_clone_commit_history", fake_clone)
    language, rows, repos, scanned = tcf._process_repo_test_commits(
        "owner/repo",
        [{"repo_name": "owner/repo", "clone_url": "https://example.invalid/o/r.git", "language": "python", "commit_sha": "a" * 40}],
    )
    assert captured["clone_filter"] == "--filter=blob:none"
    assert rows == []


def test_a_real_blobless_partial_clone_gives_the_same_answer_as_a_full_clone(varied_repo, tmp_path):
    """End to end: a partial clone of the repository through file:// (so that the filter is
    honoured) lists the same test files for every commit as the full repository."""
    from collection import ephemeral_clone

    repo, shas = varied_repo
    _git(repo, "config", "uploadpack.allowFilter", "true")
    _git(repo, "config", "uploadpack.allowAnySHA1InWant", "true")

    with ephemeral_clone.temp_clone_commit_history(
        repo.as_uri(), "o/repo", clone_filter="--filter=blob:none"
    ) as clone_path:
        assert clone_path is not None
        partial = collect_test_files_by_commit(clone_path, shas.values(), "python")

    full = collect_test_files_by_commit(repo, shas.values(), "python")
    assert partial == full


def test_a_shallow_boundary_commit_gets_no_files_as_pydriller_does(varied_repo, tmp_path):
    """Regression: in a shallow clone the boundary commit's parent is missing. Git then
    lists every file as added, which would invent test files. PyDriller gives no files
    for such a commit, and so must the batched listing (found on lewish/asciiflow
    1084fd4 in the manual test, where the real diff touches no test file)."""
    repo, shas = varied_repo
    shallow = tmp_path / "shallow"
    subprocess.run(
        ["git", "clone", "-q", "--depth=1", repo.as_uri(), str(shallow)],
        check=True, capture_output=True,
    )
    boundary = _git(shallow, "rev-parse", "HEAD")
    batched = collect_test_files_by_commit(shallow, [boundary], "python")
    assert batched[boundary] == collect_test_files_for_commit(shallow, boundary, "python") == []


def test_a_shallow_clone_matches_pydriller_for_every_commit_it_contains(varied_repo, tmp_path):
    repo, shas = varied_repo
    shallow = tmp_path / "shallow2"
    subprocess.run(
        ["git", "clone", "-q", "--depth=3", repo.as_uri(), str(shallow)],
        check=True, capture_output=True,
    )
    present = _git(shallow, "rev-list", "HEAD").split()
    batched = collect_test_files_by_commit(shallow, present, "python")
    for sha in present:
        assert batched[sha] == collect_test_files_for_commit(shallow, sha, "python"), sha


def test_a_blobless_shallow_boundary_commit_gets_no_files_and_is_not_fetched(varied_repo, tmp_path):
    """The real case (lewish/asciiflow 1084fd4): a blobless shallow clone. Git's
    promisor would fetch a missing parent on demand, which must not change the answer
    or the clone."""
    repo, shas = varied_repo
    _git(repo, "config", "uploadpack.allowFilter", "true")
    _git(repo, "config", "uploadpack.allowAnySHA1InWant", "true")
    shallow = tmp_path / "blobless-shallow"
    subprocess.run(
        ["git", "clone", "-q", "--filter=blob:none", "--depth=1", "--no-checkout", repo.as_uri(), str(shallow)],
        check=True, capture_output=True,
    )
    boundary = _git(shallow, "rev-parse", "HEAD")
    batched = collect_test_files_by_commit(shallow, [boundary], "python")
    assert batched[boundary] == []
    parent_fetched = subprocess.run(
        ["git", "--no-lazy-fetch", "-C", str(shallow), "cat-file", "-e", "HEAD~1"], capture_output=True
    ).returncode == 0
    assert not parent_fetched

