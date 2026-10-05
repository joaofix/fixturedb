"""discover-commits checkpoints: each repository is recorded in the progress
database after its CSV rows are written, and a restarted run skips the
repositories already recorded."""

import csv
import sqlite3
from pathlib import Path

import pytest

from collection.repository_quality_control import agent_commit_counter
from collection.repository_quality_control.agent_commit_counter import (
    load_completed_repos,
    record_repo_progress,
    run,
)


def _write_repo_csv(input_dir: Path, rows: list[dict]) -> None:
    input_dir.mkdir(parents=True, exist_ok=True)
    with (input_dir / "python_repo.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["repo_name", "language", "clone_url", "has_agent_config"])
        writer.writeheader()
        writer.writerows(rows)


def _repo(name: str, language: str = "python") -> dict:
    return {
        "repo_name": name,
        "language": language,
        "clone_url": f"https://example.invalid/{name}.git",
        "has_agent_config": "1",
    }


def _commit(repo: str, sha: str, language: str = "python") -> dict:
    return {
        "repo_name": repo,
        "commit_sha": sha,
        "commit_url": f"https://github.com/{repo}/commit/{sha}",
        "agent_type": "claude",
        "commit_date": "2025-02-01",
        "author_name": "agent",
        "author_email": "agent@example.invalid",
        "language": language,
        "clone_url": f"https://example.invalid/{repo}.git",
        "processed_at": "2026-01-01T00:00:00+00:00",
    }


class FakeScanner:
    """Stands in for process_repo_for_commits. `plan` maps a repo name to
    (rows, commits_examined), or to an exception to raise."""

    def __init__(self, plan: dict):
        self.plan = plan
        self.calls: list[str] = []

    def __call__(self, row: dict, since: str):
        name = row["repo_name"].strip()
        self.calls.append(name)
        outcome = self.plan[name]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture
def paths_for_run(tmp_path):
    return {
        "input_dir": tmp_path / "repos",
        "output_dir": tmp_path / "commits",
        "progress_db_path": tmp_path / "progress.db",
    }


def _run(paths_for_run, workers=1):
    return run(
        since="2025-01-01",
        workers=workers,
        input_dir=paths_for_run["input_dir"],
        output_dir=paths_for_run["output_dir"],
        progress_db_path=paths_for_run["progress_db_path"],
    )


def _csv_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def test_first_run_checkpoints_every_finished_repository_including_empty_ones(monkeypatch, paths_for_run):
    _write_repo_csv(paths_for_run["input_dir"], [_repo("owner/has-commits"), _repo("owner/no-commits")])
    monkeypatch.setattr(
        agent_commit_counter,
        "process_repo_for_commits",
        FakeScanner(
            {
                "owner/has-commits": ([_commit("owner/has-commits", "sha1"), _commit("owner/has-commits", "sha2")], 10),
                "owner/no-commits": ([], 5),
            }
        ),
    )

    _run(paths_for_run)

    completed = load_completed_repos(paths_for_run["progress_db_path"])
    assert completed == {"owner/has-commits": ("python", 10), "owner/no-commits": ("python", 5)}
    assert len(_csv_rows(paths_for_run["output_dir"] / "python_commit.csv")) == 2


def test_progress_file_holds_the_agent_commit_rows_as_a_backup(monkeypatch, paths_for_run):
    _write_repo_csv(paths_for_run["input_dir"], [_repo("owner/a")])
    monkeypatch.setattr(
        agent_commit_counter,
        "process_repo_for_commits",
        FakeScanner({"owner/a": ([_commit("owner/a", "sha1")], 3)}),
    )

    _run(paths_for_run)

    with sqlite3.connect(paths_for_run["progress_db_path"]) as conn:
        rows = conn.execute("SELECT repo_name, commit_sha, agent_type FROM agent_commits").fetchall()
    assert rows == [("owner/a", "sha1", "claude")]


def test_restarted_run_skips_checkpointed_repositories_and_keeps_totals(monkeypatch, paths_for_run):
    _write_repo_csv(paths_for_run["input_dir"], [_repo("owner/a"), _repo("owner/b")])
    first = FakeScanner({"owner/a": ([_commit("owner/a", "sha1")], 10), "owner/b": ([], 5)})
    monkeypatch.setattr(agent_commit_counter, "process_repo_for_commits", first)
    _run(paths_for_run)

    _write_repo_csv(paths_for_run["input_dir"], [_repo("owner/a"), _repo("owner/b"), _repo("owner/c")])
    second = FakeScanner({"owner/c": ([_commit("owner/c", "sha9")], 7)})
    monkeypatch.setattr(agent_commit_counter, "process_repo_for_commits", second)
    _run(paths_for_run)

    assert second.calls == ["owner/c"]
    summary = (paths_for_run["output_dir"] / "summary.md").read_text(encoding="utf-8")
    assert "| python | 22 |" in summary  # 10 + 5 from the first run, 7 from the second
    assert len(_csv_rows(paths_for_run["output_dir"] / "python_commit.csv")) == 2


def test_failed_repository_is_not_checkpointed_and_is_retried(monkeypatch, paths_for_run):
    _write_repo_csv(paths_for_run["input_dir"], [_repo("owner/flaky")])
    monkeypatch.setattr(
        agent_commit_counter,
        "process_repo_for_commits",
        FakeScanner({"owner/flaky": RuntimeError("clone timed out")}),
    )
    _run(paths_for_run)
    assert load_completed_repos(paths_for_run["progress_db_path"]) == {}

    retry = FakeScanner({"owner/flaky": ([_commit("owner/flaky", "sha1")], 4)})
    monkeypatch.setattr(agent_commit_counter, "process_repo_for_commits", retry)
    _run(paths_for_run)

    assert retry.calls == ["owner/flaky"]
    assert "owner/flaky" in load_completed_repos(paths_for_run["progress_db_path"])


def test_recording_the_same_repository_twice_leaves_one_checkpoint_and_one_row_per_commit(tmp_path):
    db = tmp_path / "progress.db"
    agent_commit_counter.initialise_progress_db(db)
    rows = [_commit("owner/a", "sha1")]

    record_repo_progress(db, "owner/a", "python", 10, rows)
    record_repo_progress(db, "owner/a", "python", 10, rows)

    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM repo_progress").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM agent_commits").fetchone()[0] == 1


def test_threaded_run_checkpoints_every_repository_and_resumes(monkeypatch, paths_for_run):
    repos = [_repo(f"owner/r{i}") for i in range(6)]
    _write_repo_csv(paths_for_run["input_dir"], repos)
    plan = {r["repo_name"]: ([_commit(r["repo_name"], f"sha{i}")], 2) for i, r in enumerate(repos)}
    monkeypatch.setattr(agent_commit_counter, "process_repo_for_commits", FakeScanner(plan))
    _run(paths_for_run, workers=3)

    assert set(load_completed_repos(paths_for_run["progress_db_path"])) == set(plan)

    resumed = FakeScanner({})
    monkeypatch.setattr(agent_commit_counter, "process_repo_for_commits", resumed)
    _run(paths_for_run, workers=3)

    assert resumed.calls == []
    assert len(_csv_rows(paths_for_run["output_dir"] / "python_commit.csv")) == 6


def _status_of(progress_db_path: Path, repo_name: str) -> str:
    with sqlite3.connect(progress_db_path) as conn:
        row = conn.execute("SELECT status FROM repo_progress WHERE repo_name = ?", (repo_name,)).fetchone()
    return row[0] if row else ""


def test_permanently_refused_clone_is_recorded_as_unavailable_and_not_retried(monkeypatch, paths_for_run):
    _write_repo_csv(paths_for_run["input_dir"], [_repo("owner/gone"), _repo("owner/ok")])
    monkeypatch.setattr(
        agent_commit_counter,
        "process_repo_for_commits",
        FakeScanner({"owner/gone": agent_commit_counter.RepoUnavailable("owner/gone"), "owner/ok": ([], 2)}),
    )
    _run(paths_for_run)

    assert _status_of(paths_for_run["progress_db_path"], "owner/gone") == "clone_unavailable"
    assert _status_of(paths_for_run["progress_db_path"], "owner/ok") == "ok"

    again = FakeScanner({})
    monkeypatch.setattr(agent_commit_counter, "process_repo_for_commits", again)
    _run(paths_for_run)
    assert again.calls == []


def test_transient_clone_failure_is_not_recorded_so_it_is_retried(monkeypatch, paths_for_run):
    from collection.clone_primitives import CloneUnavailable

    _write_repo_csv(paths_for_run["input_dir"], [_repo("owner/flaky")])
    monkeypatch.setattr(
        agent_commit_counter,
        "process_repo_for_commits",
        FakeScanner({"owner/flaky": CloneUnavailable("timed out after 300s")}),
    )
    _run(paths_for_run)
    assert load_completed_repos(paths_for_run["progress_db_path"]) == {}

    retry = FakeScanner({"owner/flaky": ([], 1)})
    monkeypatch.setattr(agent_commit_counter, "process_repo_for_commits", retry)
    _run(paths_for_run)
    assert retry.calls == ["owner/flaky"]


def test_threaded_run_records_permanently_refused_clone(monkeypatch, paths_for_run):
    _write_repo_csv(paths_for_run["input_dir"], [_repo("owner/gone"), _repo("owner/ok")])
    monkeypatch.setattr(
        agent_commit_counter,
        "process_repo_for_commits",
        FakeScanner({"owner/gone": agent_commit_counter.RepoUnavailable("owner/gone"), "owner/ok": ([], 2)}),
    )
    _run(paths_for_run, workers=2)

    assert _status_of(paths_for_run["progress_db_path"], "owner/gone") == "clone_unavailable"


def test_real_clone_of_a_missing_repository_is_a_permanent_refusal(tmp_path):
    missing = {"repo_name": "owner/missing", "language": "python", "clone_url": str(tmp_path / "no-such.git")}

    with pytest.raises(agent_commit_counter.RepoUnavailable):
        agent_commit_counter.process_repo_for_commits(missing, "2025-01-01")
