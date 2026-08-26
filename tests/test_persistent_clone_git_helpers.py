"""Tests for persistent_clone.py's small git read-only helpers.

Previously had zero test coverage; added while migrating them from
subprocess ("git rev-parse HEAD") to GitPython (git.Repo(...).head.commit.hexsha)
as part of a broader DIY-vs-library pass.
"""

import subprocess
from pathlib import Path

from collection.persistent_clone import (
    _count_commits,
    _count_test_files,
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


def test_count_commits_returns_none_not_zero_when_verification_fails(tmp_path):
    """Regression guard: a failed fetch/rev-list (here, not even a git repo)
    must come back as None, distinguishable from a confirmed low count --
    collapsing it to 0 would make clone_repo() report a confident
    "insufficient commits (0 < N)" skip for a repo that was never actually
    verified. See _count_commits()'s docstring."""
    not_a_repo = tmp_path / "not_a_repo"
    not_a_repo.mkdir()

    assert _count_commits(not_a_repo) is None


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


def test_count_test_files_counts_every_directory_pattern_match_not_just_one(tmp_path):
    """Regression test: `_count_test_files()` used to credit at most 1 file
    per matched `test_path_patterns` directory, no matter how many test
    files actually lived there (a stray `break` after the first match).
    Delegating to `is_test_file_path()` fixed that -- these 3 files live
    under Python's `tests/` directory convention without a `_test.py`-style
    suffix, so the old code would have reported 1, not 3."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    for name in ("fixtures.py", "conftest.py", "helpers.py"):
        (tests_dir / name).write_text("# not test-suffix-named\n")

    # conftest.py matches via suffix convention; fixtures.py/helpers.py only
    # match via the "tests/" directory convention.
    assert _count_test_files(tmp_path, "python") == 3


def test_count_test_files_counts_suffix_matches_across_nested_dirs(tmp_path):
    src = tmp_path / "pkg"
    src.mkdir()
    (src / "widget_test.py").write_text("x\n")
    (src / "widget.py").write_text("x\n")

    assert _count_test_files(tmp_path, "python") == 1


def test_count_test_files_does_not_double_count_a_file_matching_both_conventions(tmp_path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "widget_test.py").write_text("x\n")  # suffix AND directory match

    assert _count_test_files(tmp_path, "python") == 1


def test_count_test_files_ignores_non_test_files(tmp_path):
    (tmp_path / "widget.py").write_text("x\n")
    (tmp_path / "README.md").write_text("x\n")

    assert _count_test_files(tmp_path, "python") == 0


def test_count_test_files_unknown_language_returns_zero(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "widget_test.rb").write_text("x\n")

    assert _count_test_files(tmp_path, "ruby") == 0


def test_count_test_files_excludes_git_internals(tmp_path):
    """.git/ is walked by rglob("*") like any other directory but must be
    skipped -- it's git bookkeeping, not the checked-out tree, and this
    file would otherwise match Python's conftest.py suffix convention."""
    git_hooks = tmp_path / ".git" / "hooks"
    git_hooks.mkdir(parents=True)
    (git_hooks / "conftest.py").write_text("# not a real fixture file\n")

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "widget_test.py").write_text("x\n")

    assert _count_test_files(tmp_path, "python") == 1
