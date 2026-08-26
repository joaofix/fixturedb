"""Tests for clone_repo()'s crash-proofing: both real production call sites
(tiered_agent_corpus_scanner.py, paired_collection.py) call clone_repo()
directly inside a plain per-repo loop with no try/except of their own, so
clone_repo() itself must never let an unexpected exception escape -- one
bad repo must degrade to that repo's own 'error' row, not abort every repo
still queued behind it in the batch.

Also covers _count_commits()'s None (verification failed) vs int
(confirmed count) distinction actually being honored by clone_repo() --
see _count_commits()'s own docstring for why collapsing "couldn't verify"
into "confirmed 0" is the wrong default.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from collection import persistent_clone
from collection.persistent_clone import clone_repo


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _make_origin_repo(tmp_path: Path) -> Path:
    origin = tmp_path / "origin"
    origin.mkdir()
    _git(["init", "-q", "-b", "main"], cwd=origin)
    _git(["config", "user.email", "test@example.com"], cwd=origin)
    _git(["config", "user.name", "Test"], cwd=origin)
    (origin / "README.md").write_text("hi\n")
    _git(["add", "-A"], cwd=origin)
    _git(["commit", "-q", "-m", "init"], cwd=origin)
    return origin


@pytest.fixture(autouse=True)
def _hermetic(tmp_path, monkeypatch):
    """Bypass the pre-clone GitHub API screen (network) and MIN_COMMITS --
    isolates the post-clone steps under test."""
    monkeypatch.setattr(persistent_clone, "_has_sufficient_test_files", lambda *a, **k: True)
    monkeypatch.setattr(persistent_clone, "MIN_COMMITS", 1)
    monkeypatch.setattr(persistent_clone, "CLONES_DIR", tmp_path / "clones")


def test_unexpected_exception_after_clone_becomes_an_error_row_not_a_crash(tmp_path, monkeypatch):
    """Regression guard for the crash-proofing fix: an unanticipated
    exception from a post-clone step (here _count_test_files, standing in
    for any surprise -- a pathological filename, a permissions error, disk
    pressure) must come back as a clean ('error', ...) tuple, not propagate
    out of clone_repo() and abort whatever loop is calling it."""
    origin = _make_origin_repo(tmp_path)

    def boom(*args, **kwargs):
        raise OSError("simulated unexpected failure")

    monkeypatch.setattr(persistent_clone, "_count_test_files", boom)

    repo_id, status, commit, skip_reason = clone_repo(1, "o/r", f"file://{origin}", "python")

    assert status == "error"
    assert commit is None
    assert "unexpected error" in skip_reason
    assert "simulated unexpected failure" in skip_reason
    assert not (persistent_clone.CLONES_DIR / "o__r").exists()


def test_commit_count_verification_failure_is_an_error_not_a_confident_skip(tmp_path, monkeypatch):
    """_count_commits() returning None (fetch/rev-list failed) must not be
    silently treated as "confirmed 0 commits" -- that would produce a
    confident-looking "insufficient commits (0 < N)" skip_reason for a repo
    that was never actually checked."""
    origin = _make_origin_repo(tmp_path)
    monkeypatch.setattr(persistent_clone, "_count_commits", lambda *a, **k: None)

    repo_id, status, commit, skip_reason = clone_repo(1, "o/r", f"file://{origin}", "python")

    assert status == "error"
    assert skip_reason == "commit count verification failed"
    assert "insufficient commits" not in (skip_reason or "")
    assert not (persistent_clone.CLONES_DIR / "o__r").exists()


def test_confirmed_low_commit_count_still_skips_normally(tmp_path, monkeypatch):
    """Sanity check alongside the above: a real, confirmed low count (not
    None) must still produce the ordinary 'skipped' path, unaffected by the
    None-handling change."""
    origin = _make_origin_repo(tmp_path)
    monkeypatch.setattr(persistent_clone, "MIN_COMMITS", 5)

    repo_id, status, commit, skip_reason = clone_repo(1, "o/r", f"file://{origin}", "python")

    assert status == "skipped"
    assert skip_reason == "insufficient commits (1 < 5)"
