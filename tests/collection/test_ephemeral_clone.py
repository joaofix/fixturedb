"""Tests for ephemeral_clone.py::temp_clone_commit_history's shallow_since
support: presence/absence of `--shallow-since=<date>` in the clone args, and
the fallback-to-full-clone behavior when the shallow clone is flagged as
truncated (see clone_primitives.py's `_shallow_clone_is_truncated`).

Also covers the clone-concurrency throttle (2026-08-12): the actual `git
clone` subprocess is gated by the module's `_CLONE_SEMAPHORE`, independently
of however many workers the caller uses for local (non-network) scanning."""

from __future__ import annotations

import threading
import time
from pathlib import Path

from collection import ephemeral_clone as cm
from collection.ephemeral_clone import temp_clone_commit_history


def _fake_clone_to_tempdir_factory(tmp_path: Path, calls: list):
    def fake_clone_to_tempdir(repo_full_name, clone_url, clone_args, *, timeout, prefix, **kw):
        calls.append(list(clone_args))
        n = len(calls)
        repo_path = tmp_path / f"clone-{n}"
        repo_path.mkdir(parents=True, exist_ok=True)
        return repo_path, repo_path.parent

    return fake_clone_to_tempdir


class TestTempCloneCommitHistoryShallowSince:
    def test_omits_shallow_since_by_default(self, tmp_path, monkeypatch):
        calls: list = []
        monkeypatch.setattr(
            "collection.ephemeral_clone.clone_to_tempdir",
            _fake_clone_to_tempdir_factory(tmp_path, calls),
        )
        monkeypatch.setattr("collection.ephemeral_clone.cleanup_tempdir", lambda *_: None)

        with temp_clone_commit_history("https://example.com/o/r.git", "o/r") as repo_path:
            assert repo_path is not None

        assert len(calls) == 1
        assert not any(a.startswith("--shallow-since=") for a in calls[0])

    def test_includes_shallow_since_when_given_and_not_truncated(self, tmp_path, monkeypatch):
        calls: list = []
        monkeypatch.setattr(
            "collection.ephemeral_clone.clone_to_tempdir",
            _fake_clone_to_tempdir_factory(tmp_path, calls),
        )
        monkeypatch.setattr("collection.ephemeral_clone.cleanup_tempdir", lambda *_: None)
        monkeypatch.setattr(
            "collection.ephemeral_clone._shallow_clone_is_truncated", lambda *a, **k: False
        )

        with temp_clone_commit_history(
            "https://example.com/o/r.git", "o/r", shallow_since="2025-01-01"
        ) as repo_path:
            assert repo_path is not None

        assert len(calls) == 1  # no fallback needed
        assert "--shallow-since=2025-01-01" in calls[0]

    def test_falls_back_to_full_clone_when_truncated(self, tmp_path, monkeypatch):
        calls: list = []
        monkeypatch.setattr(
            "collection.ephemeral_clone.clone_to_tempdir",
            _fake_clone_to_tempdir_factory(tmp_path, calls),
        )
        monkeypatch.setattr("collection.ephemeral_clone.cleanup_tempdir", lambda *_: None)
        monkeypatch.setattr(
            "collection.ephemeral_clone._shallow_clone_is_truncated", lambda *a, **k: True
        )

        with temp_clone_commit_history(
            "https://example.com/o/r.git", "o/r", shallow_since="2025-01-01"
        ) as repo_path:
            assert repo_path is not None

        assert len(calls) == 2
        assert "--shallow-since=2025-01-01" in calls[0]
        assert not any(a.startswith("--shallow-since=") for a in calls[1])

    def test_clone_failure_yields_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "collection.ephemeral_clone.clone_to_tempdir",
            lambda *a, **k: (None, None),
        )
        monkeypatch.setattr("collection.ephemeral_clone.cleanup_tempdir", lambda *_: None)

        with temp_clone_commit_history("https://example.com/o/r.git", "o/r") as repo_path:
            assert repo_path is None


class TestTempCloneCommitHistoryConcurrencyThrottle:
    def test_clone_step_never_exceeds_semaphore_limit(self, tmp_path, monkeypatch):
        """Cap concurrency at 2 (patched down from the real default of 4) and
        launch 6 concurrent calls whose fake clone_to_tempdir blocks briefly
        -- the observed peak concurrent count inside clone_to_tempdir must
        never exceed 2, proving the semaphore actually gates the clone step."""
        monkeypatch.setattr(cm, "_CLONE_SEMAPHORE", threading.Semaphore(2))
        monkeypatch.setattr(cm, "cleanup_tempdir", lambda *_: None)

        lock = threading.Lock()
        state = {"current": 0, "peak": 0}

        def fake_clone_to_tempdir(repo_full_name, clone_url, clone_args, *, timeout, prefix, **kw):
            with lock:
                state["current"] += 1
                state["peak"] = max(state["peak"], state["current"])
            time.sleep(0.05)
            with lock:
                state["current"] -= 1
            repo_path = tmp_path / repo_full_name.replace("/", "__")
            repo_path.mkdir(parents=True, exist_ok=True)
            return repo_path, repo_path.parent

        monkeypatch.setattr(cm, "clone_to_tempdir", fake_clone_to_tempdir)

        def run(n):
            with temp_clone_commit_history(f"https://example.com/o/r{n}.git", f"o/r{n}"):
                pass

        threads = [threading.Thread(target=run, args=(n,)) for n in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert state["peak"] <= 2

    def test_semaphore_released_when_clone_raises(self, tmp_path, monkeypatch):
        """CloneUnavailable (or any exception) out of clone_to_tempdir must
        still release the semaphore slot -- otherwise a run of failures
        permanently starves out all future clone attempts."""
        from collection.clone_primitives import CloneUnavailable

        semaphore = threading.Semaphore(1)
        monkeypatch.setattr(cm, "_CLONE_SEMAPHORE", semaphore)

        def failing_clone_to_tempdir(*a, **k):
            raise CloneUnavailable("simulated failure")

        monkeypatch.setattr(cm, "clone_to_tempdir", failing_clone_to_tempdir)

        for _ in range(3):
            try:
                with temp_clone_commit_history("https://example.com/o/r.git", "o/r"):
                    pass
            except CloneUnavailable:
                pass

        # If the slot weren't released, this would block forever -- bound it.
        acquired = semaphore.acquire(timeout=1)
        assert acquired is True
        semaphore.release()
