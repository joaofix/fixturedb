"""Tests for persistent_clone.py's small git read-only helpers.

Previously had zero test coverage; added while migrating them from
subprocess ("git rev-parse HEAD") to GitPython (git.Repo(...).head.commit.hexsha)
as part of a broader DIY-vs-library pass.
"""

import subprocess
from pathlib import Path

from collection.persistent_clone import (
    _count_commits,
    _get_head_sha,
    _is_accessible_remote,
)


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


def test_count_commits_fetch_uses_no_prompt_env(tmp_path, monkeypatch):
    """Real incident (2026-08-11): discover-repos got stuck repeatedly on
    interactive Username/Password prompts. _count_commits()'s `git fetch`
    is one of the network calls that must never let git prompt. Patches
    the underlying subprocess.run (not run_git_no_prompt itself) so the
    real env-injection logic actually runs and gets verified."""
    repo = _init_repo(tmp_path)
    captured_kwargs = []

    def fake_run(args, **kwargs):
        captured_kwargs.append(kwargs)
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)
    _count_commits(repo)
    assert captured_kwargs[0]["env"]["GIT_TERMINAL_PROMPT"] == "0"
    assert captured_kwargs[0]["stdin"] == subprocess.DEVNULL


def test_is_accessible_remote_uses_no_prompt_env(monkeypatch):
    captured_kwargs = []

    def fake_run(args, **kwargs):
        captured_kwargs.append(kwargs)
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)
    accessible, requires_creds = _is_accessible_remote("https://example.com/o/r.git")
    assert accessible is True
    assert requires_creds is False
    assert captured_kwargs[0]["env"]["GIT_TERMINAL_PROMPT"] == "0"
    assert captured_kwargs[0]["stdin"] == subprocess.DEVNULL


def test_is_accessible_remote_detects_credential_prompt(monkeypatch):
    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(
            args, 128, stdout="", stderr="fatal: could not read Username: terminal prompts disabled"
        )

    monkeypatch.setattr("subprocess.run", fake_run)
    accessible, requires_creds = _is_accessible_remote("https://example.com/o/private.git")
    assert accessible is False
    assert requires_creds is True
