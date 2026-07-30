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

from pathlib import Path
from unittest.mock import Mock

import pytest

from collection.clone_primitives import CloneUnavailable, clone_to_tempdir


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
