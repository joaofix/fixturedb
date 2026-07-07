"""Tests for persistent_clone.py's small git read-only helpers.

Previously had zero test coverage; added while migrating them from
subprocess ("git rev-parse HEAD") to GitPython (git.Repo(...).head.commit.hexsha)
as part of a broader DIY-vs-library pass.
"""

import subprocess
from pathlib import Path

from collection.persistent_clone import _count_commits, _get_head_sha


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "a@b.com"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "A"],
        check=True,
        capture_output=True,
    )
    return repo


def _commit(repo: Path, filename: str, message: str) -> str:
    (repo / filename).write_text("x\n")
    subprocess.run(["git", "-C", str(repo), "add", filename], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", message], check=True, capture_output=True
    )
    return (
        subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"])
        .decode()
        .strip()
    )


def test_get_head_sha_matches_real_head(tmp_path):
    repo = _init_repo(tmp_path)
    sha = _commit(repo, "a.txt", "first")

    assert _get_head_sha(repo) == sha


def test_get_head_sha_updates_after_new_commit(tmp_path):
    repo = _init_repo(tmp_path)
    _commit(repo, "a.txt", "first")
    second_sha = _commit(repo, "b.txt", "second")

    assert _get_head_sha(repo) == second_sha


def test_count_commits_counts_all_commits_on_head(tmp_path, monkeypatch):
    """_count_commits() also runs `git fetch --depth 500 origin` first; a
    local-only repo with no remote configured just has that fetch fail
    silently (caught by the surrounding try/except), so the count still
    reflects the real local commit count."""
    repo = _init_repo(tmp_path)
    _commit(repo, "a.txt", "first")
    _commit(repo, "b.txt", "second")
    _commit(repo, "c.txt", "third")

    assert _count_commits(repo) == 3


def test_count_commits_returns_zero_for_non_git_dir(tmp_path):
    not_a_repo = tmp_path / "not_a_repo"
    not_a_repo.mkdir()

    assert _count_commits(not_a_repo) == 0
