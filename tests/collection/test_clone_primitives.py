"""Tests for clone_primitives.py's retry/failure-classification behavior.

Real Dataset B run (2026-07-29): the network dropped mid-run, git clone
started failing for every remaining repo, and every one of those failures
got silently checkpointed as "processed, zero results" -- indistinguishable
from a repo that genuinely has nothing to clone. These tests cover the fix:
a confirmed-permanent failure (credential prompt) still returns (None, None)
immediately, but anything else is retried and, if still failing, raises
CloneUnavailable instead of returning (None, None) -- so a caller can tell
"unknown, retry me" apart from "confirmed, nothing here."
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from collection.clone_primitives import (
    CloneUnavailable,
    _shallow_clone_is_truncated,
    clone_repo_for_commit_scan,
    clone_to_tempdir,
)


def _fake_result(returncode: int, stderr: str = "") -> Mock:
    result = Mock()
    result.returncode = returncode
    result.stderr = stderr
    return result


class TestCloneToTempdir:
    def test_success_on_first_attempt(self, tmp_path, monkeypatch):
        calls = {"n": 0}

        def fake_run(*args, **kwargs):
            calls["n"] += 1
            target_dir = Path(args[0][-1])
            target_dir.mkdir(parents=True, exist_ok=True)
            return _fake_result(0)

        monkeypatch.setattr("subprocess.run", fake_run)
        repo_path, temp_root = clone_to_tempdir(
            "owner/repo", "https://example.com/owner/repo.git", [], timeout=10, prefix="t-"
        )
        assert repo_path is not None
        assert calls["n"] == 1

    def test_credential_prompt_returns_none_immediately_no_retry(self, tmp_path, monkeypatch):
        calls = {"n": 0}

        def fake_run(*args, **kwargs):
            calls["n"] += 1
            return _fake_result(128, stderr="fatal: could not read Username: terminal prompts disabled")

        monkeypatch.setattr("subprocess.run", fake_run)
        monkeypatch.setattr("time.sleep", lambda _: None)

        repo_path, temp_root = clone_to_tempdir(
            "owner/private-repo",
            "https://example.com/owner/private-repo.git",
            [],
            timeout=10,
            prefix="t-",
            retries=2,
        )
        assert (repo_path, temp_root) == (None, None)
        assert calls["n"] == 1  # confirmed-permanent -- no retry attempted

    def test_generic_failure_retries_then_raises_clone_unavailable(self, tmp_path, monkeypatch):
        calls = {"n": 0}

        def fake_run(*args, **kwargs):
            calls["n"] += 1
            return _fake_result(128, stderr="fatal: unable to access: Could not resolve host")

        monkeypatch.setattr("subprocess.run", fake_run)
        monkeypatch.setattr("time.sleep", lambda _: None)

        with pytest.raises(CloneUnavailable):
            clone_to_tempdir(
                "owner/repo",
                "https://example.com/owner/repo.git",
                [],
                timeout=10,
                prefix="t-",
                retries=2,
            )
        assert calls["n"] == 3  # 1 initial + 2 retries

    def test_succeeds_on_a_later_retry(self, tmp_path, monkeypatch):
        calls = {"n": 0}

        def fake_run(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] < 2:
                return _fake_result(128, stderr="fatal: unable to access: Could not resolve host")
            target_dir = Path(args[0][-1])
            target_dir.mkdir(parents=True, exist_ok=True)
            return _fake_result(0)

        monkeypatch.setattr("subprocess.run", fake_run)
        monkeypatch.setattr("time.sleep", lambda _: None)

        repo_path, temp_root = clone_to_tempdir(
            "owner/repo", "https://example.com/owner/repo.git", [], timeout=10, prefix="t-", retries=2
        )
        assert repo_path is not None
        assert calls["n"] == 2

    def test_exception_during_subprocess_run_also_retries_then_raises(self, tmp_path, monkeypatch):
        calls = {"n": 0}

        def fake_run(*args, **kwargs):
            calls["n"] += 1
            raise OSError("network unreachable")

        monkeypatch.setattr("subprocess.run", fake_run)
        monkeypatch.setattr("time.sleep", lambda _: None)

        with pytest.raises(CloneUnavailable):
            clone_to_tempdir(
                "owner/repo", "https://example.com/owner/repo.git", [], timeout=10, prefix="t-", retries=1
            )
        assert calls["n"] == 2  # 1 initial + 1 retry


def _git(args: list[str], cwd: Path, env: dict | None = None) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True, env=env
    )
    return result.stdout.strip()


def _make_origin_repo(tmp_path: Path, commit_dates: list[str]) -> Path:
    """A local git repo with one commit per date in `commit_dates` (ISO,
    oldest first) -- committer/author date pinned via GIT_COMMITTER_DATE/
    GIT_AUTHOR_DATE, HEAD ends up at the last date."""
    import os

    origin = tmp_path / "origin"
    origin.mkdir()
    _git(["init", "-q"], cwd=origin)
    _git(["config", "user.email", "test@example.com"], cwd=origin)
    _git(["config", "user.name", "Test"], cwd=origin)
    for i, date in enumerate(commit_dates):
        env = {**os.environ, "GIT_COMMITTER_DATE": date, "GIT_AUTHOR_DATE": date}
        _git(["commit", "-q", "--allow-empty", "-m", f"c{i}"], cwd=origin, env=env)
    return origin


def _shallow_clone_with_full_objects(origin: Path, dest: Path) -> Path:
    """Depth-1 clone `origin` into `dest`, then copy all of `origin`'s
    objects into `dest`. Mirrors what a real `--shallow-since` clone leaves
    behind in production: a `.git/shallow` boundary that `git log`/`rev-list`
    respect, but with the boundary commit's true parent object still
    physically present (just unreachable through normal traversal) --
    confirmed empirically against 24 real GitHub repos (see
    clone_primitives.py's `_shallow_clone_is_truncated` docstring). A plain
    `--depth=1` clone against a local repo does *not* keep the parent object
    around on its own (git's local-transport negotiation is stricter than
    the smart-HTTP negotiation real hosts use), so the copy step is what
    makes this fixture representative."""
    subprocess.run(
        ["git", "clone", "--depth=1", f"file://{origin}", str(dest)],
        check=True,
        capture_output=True,
    )
    shutil.copytree(origin / ".git" / "objects", dest / ".git" / "objects", dirs_exist_ok=True)
    return dest


def _shallow_boundary_and_parent(dest: Path) -> tuple[str, str]:
    boundary = (dest / ".git" / "shallow").read_text().strip()
    raw = _git(["cat-file", "-p", boundary], cwd=dest)
    parent = next(line.split()[1] for line in raw.splitlines() if line.startswith("parent "))
    return boundary, parent


class TestShallowCloneIsTruncated:
    def test_no_shallow_file_is_not_truncated(self, tmp_path):
        origin = _make_origin_repo(tmp_path, ["2025-02-01T00:00:00+00:00"])
        dest = tmp_path / "dest"
        subprocess.run(
            ["git", "clone", f"file://{origin}", str(dest)], check=True, capture_output=True
        )
        assert not (dest / ".git" / "shallow").exists()
        assert _shallow_clone_is_truncated(dest, "2025-01-01") is False

    def test_safe_when_true_parent_predates_cutoff(self, tmp_path):
        # `git clone --depth=1` fetches only HEAD, so the shallow boundary is
        # always the *last* commit and its true parent is always the
        # second-to-last -- a 2-commit chain keeps that unambiguous.
        origin = _make_origin_repo(
            tmp_path,
            [
                "2024-06-01T00:00:00+00:00",  # c0 -- becomes the shallow boundary's true parent
                "2025-02-05T00:00:00+00:00",  # c1 -- HEAD, becomes the shallow boundary
            ],
        )
        dest = _shallow_clone_with_full_objects(origin, tmp_path / "dest")
        _, parent = _shallow_boundary_and_parent(dest)
        assert _git(["show", "--no-patch", "--format=%cI", parent], cwd=dest).startswith(
            "2024-06-01"
        )
        assert _shallow_clone_is_truncated(dest, "2025-01-01") is False

    def test_truncated_when_true_parent_is_on_or_after_cutoff(self, tmp_path):
        origin = _make_origin_repo(
            tmp_path,
            [
                "2025-01-10T00:00:00+00:00",  # c0 -- becomes the boundary's true parent, ON/AFTER cutoff
                "2025-02-05T00:00:00+00:00",  # c1 -- HEAD, becomes the shallow boundary
            ],
        )
        dest = _shallow_clone_with_full_objects(origin, tmp_path / "dest")
        _, parent = _shallow_boundary_and_parent(dest)
        assert _git(["show", "--no-patch", "--format=%cI", parent], cwd=dest).startswith(
            "2025-01-10"
        )
        assert _shallow_clone_is_truncated(dest, "2025-01-01") is True

    def test_unresolvable_parent_object_is_treated_as_truncated(self, tmp_path):
        origin = _make_origin_repo(
            tmp_path,
            [
                "2024-06-01T00:00:00+00:00",
                "2025-02-05T00:00:00+00:00",
            ],
        )
        dest = _shallow_clone_with_full_objects(origin, tmp_path / "dest")
        _, parent = _shallow_boundary_and_parent(dest)
        # Delete the parent's loose object -- simulates "can't verify locally".
        obj_path = dest / ".git" / "objects" / parent[:2] / parent[2:]
        assert obj_path.exists()
        obj_path.unlink()
        assert _shallow_clone_is_truncated(dest, "2025-01-01") is True


class TestCloneRepoForCommitScanShallowSince:
    def test_omits_shallow_since_flag_by_default(self, tmp_path, monkeypatch):
        captured_args = []

        def fake_run(args, **kwargs):
            captured_args.append(args)
            target_dir = Path(args[-1])
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / "marker").write_text("x")
            return Mock(returncode=0, stderr="")

        monkeypatch.setattr("subprocess.run", fake_run)
        target = tmp_path / "repo"
        assert clone_repo_for_commit_scan("https://example.com/o/r.git", target) is True
        assert len(captured_args) == 1
        assert not any(a.startswith("--shallow-since=") for a in captured_args[0])

    def test_includes_shallow_since_flag_when_given_and_not_truncated(self, tmp_path, monkeypatch):
        captured_args = []

        def fake_run(args, **kwargs):
            captured_args.append(args)
            target_dir = Path(args[-1])
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / "marker").write_text("x")
            return Mock(returncode=0, stderr="")

        monkeypatch.setattr("subprocess.run", fake_run)
        monkeypatch.setattr(
            "collection.clone_primitives._shallow_clone_is_truncated", lambda *a, **k: False
        )
        target = tmp_path / "repo"
        ok = clone_repo_for_commit_scan(
            "https://example.com/o/r.git", target, shallow_since="2025-01-01"
        )
        assert ok is True
        assert len(captured_args) == 1  # no fallback needed
        assert "--shallow-since=2025-01-01" in captured_args[0]

    def test_falls_back_to_full_clone_when_shallow_clone_is_truncated(self, tmp_path, monkeypatch):
        captured_args = []

        def fake_run(args, **kwargs):
            captured_args.append(args)
            target_dir = Path(args[-1])
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / "marker").write_text("x")
            return Mock(returncode=0, stderr="")

        # Truncated only on the first (shallow) attempt.
        truncation_calls = {"n": 0}

        def fake_is_truncated(*a, **k):
            truncation_calls["n"] += 1
            return truncation_calls["n"] == 1

        monkeypatch.setattr("subprocess.run", fake_run)
        monkeypatch.setattr(
            "collection.clone_primitives._shallow_clone_is_truncated", fake_is_truncated
        )
        target = tmp_path / "repo"
        ok = clone_repo_for_commit_scan(
            "https://example.com/o/r.git", target, shallow_since="2025-01-01"
        )
        assert ok is True
        assert len(captured_args) == 2
        assert "--shallow-since=2025-01-01" in captured_args[0]
        assert not any(a.startswith("--shallow-since=") for a in captured_args[1])
        # _shallow_clone_is_truncated is only consulted when shallow_since is set,
        # so the fallback (full) clone must not re-trigger it.
        assert truncation_calls["n"] == 1
