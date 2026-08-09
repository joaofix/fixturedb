"""Tests for repository_quality_control/backfill_total_commits.py -- the
one-time backfill of repositories.total_commits_since_agent_start for
Dataset A repos collected before that column existed.

No real network clones here: `temp_clone_commit_history()` is monkeypatched
to either yield a real *local* git repo (so `count_total_commits_since()`
still runs for real, same as `tests/between_group/test_agent_corpus.py`'s
style) or `None` (simulating a clone failure), never a real GitHub clone.
"""

from __future__ import annotations

import os
import subprocess
from contextlib import contextmanager
from pathlib import Path

from collection.db import db_session, initialise_db, upsert_repository
from collection.repository_quality_control import backfill_total_commits as backfill


def _git(args: list[str], cwd: Path, env: dict | None = None) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True, env=env
    )
    return result.stdout.strip()


def _make_repo_with_commits(tmp_path: Path, name: str, commit_dates: list[str]) -> Path:
    """A local git repo with one (empty, non-merge) commit per date in
    `commit_dates` (ISO, oldest first)."""
    repo = tmp_path / name
    repo.mkdir()
    _git(["init", "-q", "-b", "main"], cwd=repo)
    _git(["config", "user.email", "test@example.com"], cwd=repo)
    _git(["config", "user.name", "Test"], cwd=repo)
    for i, date in enumerate(commit_dates):
        env = {**os.environ, "GIT_COMMITTER_DATE": date, "GIT_AUTHOR_DATE": date}
        _git(["commit", "-q", "--allow-empty", "-m", f"c{i}"], cwd=repo, env=env)
    return repo


def _make_db_with_repos(db_path: Path, repos: list[dict]) -> None:
    initialise_db(db_path)
    with db_session(db_path) as conn:
        for i, r in enumerate(repos):
            upsert_repository(
                conn,
                {
                    "github_id": 1000 + i,
                    "full_name": r["full_name"],
                    "language": r.get("language", "python"),
                    "stars": 0,
                    "forks": 0,
                    "description": "",
                    "topics": "[]",
                    "created_at": "2019-01-01",
                    "pushed_at": "",
                    "clone_url": r.get("clone_url", f"https://github.com/{r['full_name']}.git"),
                    "num_contributors": 0,
                    "domain": None,
                    "repo_age_years": None,
                    "agent_adoption_intensity": "pervasive",
                    "total_commits_since_agent_start": r.get("total_commits_since_agent_start"),
                },
            )


@contextmanager
def _yield_ctx(value):
    yield value


class TestFetchReposMissingTotalCommits:
    def test_returns_only_null_rows(self, tmp_path):
        db_path = tmp_path / "a.db"
        _make_db_with_repos(
            db_path,
            [
                {"full_name": "owner/has-count", "total_commits_since_agent_start": 10},
                {"full_name": "owner/missing-count", "total_commits_since_agent_start": None},
            ],
        )
        with db_session(db_path) as conn:
            missing = backfill.fetch_repos_missing_total_commits(conn)
        assert [r["full_name"] for r in missing] == ["owner/missing-count"]


class TestBackfillOne:
    def test_returns_total_commit_count_on_successful_clone(self, tmp_path, monkeypatch):
        repo_path = _make_repo_with_commits(
            tmp_path,
            "origin",
            [
                "2024-06-01T00:00:00+00:00",  # before the window -- excluded
                "2025-02-01T00:00:00+00:00",
                "2025-03-01T00:00:00+00:00",
                "2025-04-01T00:00:00+00:00",
            ],
        )
        monkeypatch.setattr(
            backfill,
            "temp_clone_commit_history",
            lambda clone_url, full_name, **kw: _yield_ctx(repo_path),
        )
        repo_id, total = backfill.backfill_one(
            {"id": 7, "full_name": "owner/repo", "clone_url": str(repo_path)},
            since="2025-01-01",
        )
        assert repo_id == 7
        assert total == 3

    def test_returns_none_on_clone_failure(self, monkeypatch):
        monkeypatch.setattr(
            backfill,
            "temp_clone_commit_history",
            lambda clone_url, full_name, **kw: _yield_ctx(None),
        )
        repo_id, total = backfill.backfill_one(
            {"id": 9, "full_name": "owner/gone", "clone_url": "https://github.com/owner/gone.git"},
            since="2025-01-01",
        )
        assert repo_id == 9
        assert total is None


class TestRun:
    def test_updates_db_rows_for_repos_missing_column(self, tmp_path, monkeypatch):
        db_path = tmp_path / "a.db"
        _make_db_with_repos(
            db_path,
            [
                {"full_name": "owner/repo-a", "total_commits_since_agent_start": None},
                {"full_name": "owner/repo-b", "total_commits_since_agent_start": None},
            ],
        )
        counts = {"owner/repo-a": 5, "owner/repo-b": 12}

        def fake_backfill_one(repo, since):
            return repo["id"], counts[repo["full_name"]]

        monkeypatch.setattr(backfill, "backfill_one", fake_backfill_one)

        result = backfill.run(db_path, since="2025-01-01", workers=2)
        assert result == {"updated": 2, "failed": 0}

        with db_session(db_path) as conn:
            rows = {
                row["full_name"]: row["total_commits_since_agent_start"]
                for row in conn.execute(
                    "SELECT full_name, total_commits_since_agent_start FROM repositories"
                ).fetchall()
            }
        assert rows == counts

    def test_skips_repos_already_populated(self, tmp_path, monkeypatch):
        db_path = tmp_path / "a.db"
        _make_db_with_repos(
            db_path,
            [
                {"full_name": "owner/already-done", "total_commits_since_agent_start": 99},
                {"full_name": "owner/still-missing", "total_commits_since_agent_start": None},
            ],
        )
        seen_repo_names: list[str] = []

        def fake_backfill_one(repo, since):
            seen_repo_names.append(repo["full_name"])
            return repo["id"], 3

        monkeypatch.setattr(backfill, "backfill_one", fake_backfill_one)

        result = backfill.run(db_path, since="2025-01-01", workers=2)
        assert result == {"updated": 1, "failed": 0}
        assert seen_repo_names == ["owner/still-missing"]

        with db_session(db_path) as conn:
            row = conn.execute(
                "SELECT total_commits_since_agent_start FROM repositories WHERE full_name = ?",
                ("owner/already-done",),
            ).fetchone()
        # Untouched -- the pre-existing value survives, not overwritten by
        # the fake's return value.
        assert row["total_commits_since_agent_start"] == 99

    def test_leaves_column_null_and_counts_failed_on_clone_failure(self, tmp_path, monkeypatch):
        db_path = tmp_path / "a.db"
        _make_db_with_repos(
            db_path,
            [{"full_name": "owner/unreachable", "total_commits_since_agent_start": None}],
        )

        def fake_backfill_one(repo, since):
            return repo["id"], None

        monkeypatch.setattr(backfill, "backfill_one", fake_backfill_one)

        result = backfill.run(db_path, since="2025-01-01", workers=1)
        assert result == {"updated": 0, "failed": 1}

        with db_session(db_path) as conn:
            row = conn.execute(
                "SELECT total_commits_since_agent_start FROM repositories WHERE full_name = ?",
                ("owner/unreachable",),
            ).fetchone()
        assert row["total_commits_since_agent_start"] is None

    def test_resumable_second_run_only_processes_remaining_null_rows(self, tmp_path, monkeypatch):
        db_path = tmp_path / "a.db"
        _make_db_with_repos(
            db_path,
            [{"full_name": "owner/repo-a", "total_commits_since_agent_start": None}],
        )

        def fake_backfill_one(repo, since):
            return repo["id"], 4

        monkeypatch.setattr(backfill, "backfill_one", fake_backfill_one)

        first = backfill.run(db_path, since="2025-01-01", workers=1)
        assert first == {"updated": 1, "failed": 0}

        # Second run: nothing left to do -- the repo already backfilled must
        # not be re-submitted (would show up as a spurious extra "updated").
        second = backfill.run(db_path, since="2025-01-01", workers=1)
        assert second == {"updated": 0, "failed": 0}

    def test_self_heals_a_db_collected_before_the_column_existed(self, tmp_path, monkeypatch):
        """Regression test: db/a.db predating this column entirely (CREATE
        TABLE IF NOT EXISTS is a no-op on an already-existing table, so the
        column would never appear on its own) must not crash with "no such
        column" -- run() calls initialise_db() first, same as every other
        collection entry point, to self-heal exactly this case."""
        import sqlite3

        db_path = tmp_path / "stale.db"
        conn = sqlite3.connect(db_path)
        conn.execute(
            "CREATE TABLE repositories (id INTEGER PRIMARY KEY, github_id INTEGER, "
            "full_name TEXT NOT NULL, language TEXT, clone_url TEXT)"
        )
        conn.execute(
            "INSERT INTO repositories (github_id, full_name, language, clone_url) "
            "VALUES (1, 'owner/prehistoric', 'python', 'https://github.com/owner/prehistoric.git')"
        )
        conn.commit()
        conn.close()

        def fake_backfill_one(repo, since):
            return repo["id"], 8

        monkeypatch.setattr(backfill, "backfill_one", fake_backfill_one)

        result = backfill.run(db_path, since="2025-01-01", workers=1)
        assert result == {"updated": 1, "failed": 0}

        with db_session(db_path) as conn:
            row = conn.execute(
                "SELECT total_commits_since_agent_start FROM repositories WHERE full_name = ?",
                ("owner/prehistoric",),
            ).fetchone()
        assert row["total_commits_since_agent_start"] == 8
