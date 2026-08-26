"""Integration coverage for persistent_clone.py's clone_repo() MIN_TEST_FILES
gate -- previously zero: clone_repo() itself was never exercised by any
test, which is exactly how _count_test_files()'s directory-pattern
undercount bug (see its docstring) went unnoticed. These clone from a real
local git repo (file:// origin, no network) so the gate runs against real
on-disk files rather than a mocked count.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from collection import persistent_clone
from collection.persistent_clone import clone_repo


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _make_origin_repo(tmp_path: Path, test_file_names: list[str]) -> Path:
    """A local git repo, one commit, with `test_file_names` under tests/ --
    plain names (e.g. "helper_0.py"), deliberately not matching any of
    Python's suffix conventions, so they're only recognized as test files
    via the tests/ directory convention."""
    origin = tmp_path / "origin"
    origin.mkdir()
    _git(["init", "-q", "-b", "main"], cwd=origin)
    _git(["config", "user.email", "test@example.com"], cwd=origin)
    _git(["config", "user.name", "Test"], cwd=origin)
    tests_dir = origin / "tests"
    tests_dir.mkdir()
    for name in test_file_names:
        (tests_dir / name).write_text("x = 1\n")
    _git(["add", "-A"], cwd=origin)
    _git(["commit", "-q", "-m", "add test files"], cwd=origin)
    return origin


@pytest.fixture(autouse=True)
def _hermetic(tmp_path, monkeypatch):
    """Bypass the pre-clone GitHub API screen (network) and lower
    MIN_COMMITS to match the single local commit these fixtures create --
    isolates the post-clone on-disk MIN_TEST_FILES recount, which is what's
    under test here."""
    monkeypatch.setattr(persistent_clone, "_has_sufficient_test_files", lambda *a, **k: True)
    monkeypatch.setattr(persistent_clone, "MIN_COMMITS", 1)
    monkeypatch.setattr(persistent_clone, "CLONES_DIR", tmp_path / "clones")


def test_clone_repo_keeps_a_repo_whose_test_files_only_match_by_directory_convention(tmp_path):
    """Regression test for the _count_test_files() undercount bug: 6 files
    live under tests/ with no suffix convention. The old code credited at
    most 1 file for the whole "tests/" pattern match (1 < 5 -> would have
    wrongly skipped this repo); the fixed count is exact (6 >= 5 -> cloned)."""
    names = [f"helper_{i}.py" for i in range(6)]
    origin = _make_origin_repo(tmp_path, names)

    repo_id, status, commit, skip_reason = clone_repo(1, "o/r", f"file://{origin}", "python")

    assert status == "cloned"
    assert skip_reason is None
    assert commit is not None
    assert (persistent_clone.CLONES_DIR / "o__r").exists()


def test_clone_repo_skips_and_cleans_up_when_genuinely_below_threshold(tmp_path):
    origin = _make_origin_repo(tmp_path, ["helper_0.py", "helper_1.py"])

    repo_id, status, commit, skip_reason = clone_repo(1, "o/r", f"file://{origin}", "python")

    assert status == "skipped"
    assert skip_reason == "insufficient test files (2 < 5)"
    assert commit is None
    assert not (persistent_clone.CLONES_DIR / "o__r").exists()
