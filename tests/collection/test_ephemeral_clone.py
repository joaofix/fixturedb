"""Tests for ephemeral_clone.py::temp_clone_commit_history's shallow_since
support: presence/absence of `--shallow-since=<date>` in the clone args, and
the fallback-to-full-clone behavior when the shallow clone is flagged as
truncated (see clone_primitives.py's `_shallow_clone_is_truncated`)."""

from __future__ import annotations

from pathlib import Path

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
