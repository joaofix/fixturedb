"""Real (non-mocked) unit tests for agent_commit_counter.py's per-commit and
per-run "total commits examined" counting -- the number that feeds
paper-draft/3-results.md's "all commits" column, distinct from the
agent-attributed subset already captured in datasets/a/commits/*.csv."""

import csv
import os
import subprocess
from pathlib import Path

from collection.repository_quality_control.agent_commit_counter import (
    process_repo_for_commits,
    run,
)


def _make_repo(path: Path, commits: list[str]) -> None:
    """Create a real git repo with one empty commit per message in *commits*."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Alice Example",
        "GIT_AUTHOR_EMAIL": "alice@example.com",
        "GIT_COMMITTER_NAME": "Alice Example",
        "GIT_COMMITTER_EMAIL": "alice@example.com",
    }
    for message in commits:
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", message],
            cwd=path,
            check=True,
            capture_output=True,
            env=env,
        )


def _write_repo_qc_csv(repo_qc_dir: Path, filename: str, rows: list[dict]) -> None:
    repo_qc_dir.mkdir(parents=True, exist_ok=True)
    header = ["repo_name", "language", "clone_url", "has_agent_config"]
    with (repo_qc_dir / filename).open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=header)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def test_process_repo_for_commits_total_examined_counts_every_commit(tmp_path: Path):
    """total_examined must count human + agent commits alike, not just the
    agent-matched ones returned in out_rows."""
    repo_dir = tmp_path / "repo"
    _make_repo(
        repo_dir,
        [
            "Plain human commit one",
            "Plain human commit two",
            "Add feature\n\nCo-authored-by: GitHub Copilot <copilot@github.com>",
        ],
    )

    out_rows, total_examined = process_repo_for_commits(
        {"repo_name": "owner/repo", "clone_url": str(repo_dir), "language": "python"},
        "2025-01-01",
    )

    assert len(out_rows) == 1
    assert out_rows[0]["agent_type"] == "copilot"
    assert total_examined == 3


def test_process_repo_for_commits_no_repo_name_returns_empty(tmp_path: Path):
    out_rows, total_examined = process_repo_for_commits({}, "2025-01-01")
    assert out_rows == []
    assert total_examined == 0


def test_process_repo_for_commits_clone_failure_returns_zero_total(tmp_path: Path):
    out_rows, total_examined = process_repo_for_commits(
        {
            "repo_name": "owner/nonexistent",
            "clone_url": str(tmp_path / "does-not-exist"),
            "language": "python",
        },
        "2025-01-01",
    )
    assert out_rows == []
    assert total_examined == 0


def test_run_writes_commit_scan_summary_md(tmp_path: Path):
    repo_dir = tmp_path / "repo"
    _make_repo(
        repo_dir,
        [
            "Plain human commit",
            "Add feature\n\nCo-authored-by: GitHub Copilot <copilot@github.com>",
        ],
    )

    repo_qc_dir = tmp_path / "repo_qc"
    _write_repo_qc_csv(
        repo_qc_dir,
        "python_agent_repo.csv",
        [
            {
                "repo_name": "owner/repo",
                "language": "python",
                "clone_url": str(repo_dir),
                "has_agent_config": "1",
            }
        ],
    )

    output_dir = tmp_path / "out"
    result = run(
        since="2025-01-01",
        workers=1,
        input_dir=repo_qc_dir,
        output_dir=output_dir,
    )
    assert result == 0

    summary_path = output_dir / "summary.md"
    assert summary_path.exists()
    summary_text = summary_path.read_text()
    assert "Dataset A -- commit scan summary" in summary_text
    assert "| python | 2 |" in summary_text

    commits_csv = output_dir / "python_commit.csv"
    assert commits_csv.exists()
    with commits_csv.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 1
    assert rows[0]["agent_type"] == "copilot"


def test_run_accumulates_per_language_totals_across_repos(tmp_path: Path):
    python_repo = tmp_path / "python_repo"
    _make_repo(python_repo, ["Human commit A", "Human commit B", "Human commit C"])

    java_repo = tmp_path / "java_repo"
    _make_repo(java_repo, ["Human commit D"])

    repo_qc_dir = tmp_path / "repo_qc"
    _write_repo_qc_csv(
        repo_qc_dir,
        "python_agent_repo.csv",
        [
            {
                "repo_name": "owner/python-repo",
                "language": "python",
                "clone_url": str(python_repo),
                "has_agent_config": "1",
            }
        ],
    )
    _write_repo_qc_csv(
        repo_qc_dir,
        "java_agent_repo.csv",
        [
            {
                "repo_name": "owner/java-repo",
                "language": "java",
                "clone_url": str(java_repo),
                "has_agent_config": "1",
            }
        ],
    )

    output_dir = tmp_path / "out"
    run(since="2025-01-01", workers=1, input_dir=repo_qc_dir, output_dir=output_dir)

    summary_text = (output_dir / "summary.md").read_text()
    assert "| python | 3 |" in summary_text
    assert "| java | 1 |" in summary_text


def test_run_skips_repos_missing_agent_config(tmp_path: Path):
    """read_config_positive_rows already filters to has_agent_config=1 --
    confirm a non-qualifying repo contributes nothing to the totals."""
    repo_dir = tmp_path / "repo"
    _make_repo(repo_dir, ["Some commit"])

    repo_qc_dir = tmp_path / "repo_qc"
    _write_repo_qc_csv(
        repo_qc_dir,
        "python_agent_repo.csv",
        [
            {
                "repo_name": "owner/repo",
                "language": "python",
                "clone_url": str(repo_dir),
                "has_agent_config": "0",
            }
        ],
    )

    output_dir = tmp_path / "out"
    result = run(since="2025-01-01", workers=1, input_dir=repo_qc_dir, output_dir=output_dir)
    assert result == 0
    assert not (output_dir / "summary.md").exists()
