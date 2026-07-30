import contextlib
import csv
import json
import subprocess
from pathlib import Path

from collection.clone_primitives import CloneUnavailable
from collection.config import COLLECTION_OUTPUT_TAG
from collection.test_commit_filter import (
    collect_agent_test_commits,
    collect_agent_test_commits_from_repos,
)


@contextlib.contextmanager
def _raise_clone_unavailable(*args, **kwargs):
    raise CloneUnavailable("simulated network drop")
    yield  # pragma: no cover -- unreachable, required to make this a generator


def init_minimal_repo_with_agent_commit(path: Path, marker: str = "") -> str:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", str(path)], check=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "test@example.com"], check=True
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "Test User"], check=True
    )
    tests_dir = path / "tests"
    tests_dir.mkdir(exist_ok=True)
    body = "def test_x():\n    assert True\n"
    if marker:
        body += f"# {marker}\n"
    (tests_dir / "test_agent.py").write_text(body)
    # Commit with co-authored-by footer referencing copilot to simulate agent commit
    subprocess.run(["git", "-C", str(path), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(path),
            "commit",
            "-m",
            f"Add test file {marker}\n\nCo-authored-by: GitHub Copilot <copilot@example.com>",
        ],
        check=True,
    )
    sha = (
        subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"])
        .decode()
        .strip()
    )
    return sha


def test_collect_agent_test_commits_from_repos(tmp_path: Path):
    repo_dir = tmp_path / "repo"
    commit_sha = init_minimal_repo_with_agent_commit(repo_dir)

    repo_qc_dir = tmp_path / "repo_qc"
    repo_qc_dir.mkdir()
    csv_path = repo_qc_dir / "python_repo.csv"
    header = [
        "repo_name",
        "language",
        "clone_url",
        "has_agent_config",
        "stars",
        "num_contributors",
    ]
    row = {
        "repo_name": "owner/repo",
        "language": "python",
        "clone_url": str(repo_dir),
        "has_agent_config": "1",
        "stars": "0",
        "num_contributors": "1",
    }
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=header)
        writer.writeheader()
        writer.writerow(row)

    out_dir = tmp_path / "out"
    result = collect_agent_test_commits_from_repos(repo_qc_dir, out_dir, workers=1)
    assert result["test_commits_found"] >= 1

    out_csv = out_dir / "python_test_commit.csv"
    assert out_csv.exists()

    with out_csv.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
    assert any(r["commit_sha"] == commit_sha for r in rows)


def test_collect_agent_test_commits_resumes_completed_repos(tmp_path: Path):
    repo_one = tmp_path / "repo_one"
    sha_one = init_minimal_repo_with_agent_commit(repo_one)
    repo_two = tmp_path / "repo_two"
    sha_two = init_minimal_repo_with_agent_commit(repo_two, marker="second")

    commit_dir = tmp_path / "agent_commits"
    commit_dir.mkdir()
    csv_path = commit_dir / "python_commit.csv"
    header = [
        "repo_name",
        "language",
        "clone_url",
        "commit_sha",
        "agent_type",
        "commit_date",
    ]
    rows = [
        {
            "repo_name": "owner/repo-one",
            "language": "python",
            "clone_url": str(repo_one),
            "commit_sha": sha_one,
            "agent_type": "copilot",
            "commit_date": "2025-01-01",
        },
        {
            "repo_name": "owner/repo-two",
            "language": "python",
            "clone_url": str(repo_two),
            "commit_sha": sha_two,
            "agent_type": "copilot",
            "commit_date": "2025-01-02",
        },
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    out_csv = out_dir / "python_test_commit.csv"
    with out_csv.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "repo_name",
                "language",
                "commit_sha",
                "commit_role",
                "agent_type",
                "commit_date",
                "test_file_count",
                "test_file_paths",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "repo_name": "owner/repo-one",
                "language": "python",
                "commit_sha": sha_one,
                "commit_role": "agent",
                "agent_type": "copilot",
                "commit_date": "2025-01-01",
                "test_file_count": "1",
                "test_file_paths": json.dumps(["tests/test_agent.py"]),
            }
        )

    checkpoint_path = out_dir / "agent_test_commits.checkpoint.json"
    checkpoint_path.write_text(
        json.dumps(
            {
                "repos_processed": 1,
                "commits_scanned": 1,
                "repos_with_test_commits": 1,
                "test_commits_found": 1,
                "completed_repos": ["owner/repo-one"],
                "last_updated_at": "2026-05-28T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    result = collect_agent_test_commits(commit_dir, out_dir, workers=1)

    assert result["repos_processed"] == 2
    assert result["commits_scanned"] == 2
    assert result["test_commits_found"] >= 2

    with out_csv.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
    assert {row["commit_sha"] for row in rows} == {sha_one, sha_two}


def test_clone_failure_is_not_checkpointed_as_complete(tmp_path: Path, monkeypatch):
    """Same guarantee as the human-side filter: a CloneUnavailable must not
    be checkpointed as done, or a transient failure (network drop mid-run)
    gets permanently miscached as 'scanned, zero results'."""
    monkeypatch.setattr(
        "collection.test_commit_filter.temp_clone_commit_history",
        _raise_clone_unavailable,
    )

    commit_dir = tmp_path / "agent_commits"
    commit_dir.mkdir()
    csv_path = commit_dir / "python_commit.csv"
    header = ["repo_name", "language", "clone_url", "commit_sha", "agent_type", "commit_date"]
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=header)
        writer.writeheader()
        writer.writerow(
            {
                "repo_name": "owner/repo",
                "language": "python",
                "clone_url": "unused",
                "commit_sha": "deadbeef",
                "agent_type": "copilot",
                "commit_date": "2025-01-01",
            }
        )

    out_dir = tmp_path / "out"
    result = collect_agent_test_commits(commit_dir, out_dir, workers=1)

    assert result["clone_failures"] == 1
    assert result["repos_processed"] == 0

    checkpoint = json.loads((out_dir / "agent_test_commits.checkpoint.json").read_text())
    assert "owner/repo" not in checkpoint["completed_repos"]


def test_clone_failure_multi_worker_does_not_block_other_repos(tmp_path: Path, monkeypatch):
    good_repo = tmp_path / "good_repo"
    sha = init_minimal_repo_with_agent_commit(good_repo)

    real_temp_clone = __import__(
        "collection.test_commit_filter", fromlist=["temp_clone_commit_history"]
    ).temp_clone_commit_history

    def flaky_temp_clone(clone_url, repo_full_name, **kwargs):
        if repo_full_name == "owner/bad-repo":
            return _raise_clone_unavailable()
        return real_temp_clone(clone_url, repo_full_name, **kwargs)

    monkeypatch.setattr(
        "collection.test_commit_filter.temp_clone_commit_history", flaky_temp_clone
    )

    commit_dir = tmp_path / "agent_commits"
    commit_dir.mkdir()
    csv_path = commit_dir / "python_commit.csv"
    header = ["repo_name", "language", "clone_url", "commit_sha", "agent_type", "commit_date"]
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=header)
        writer.writeheader()
        writer.writerow(
            {
                "repo_name": "owner/bad-repo",
                "language": "python",
                "clone_url": "unused",
                "commit_sha": "deadbeef",
                "agent_type": "copilot",
                "commit_date": "2025-01-01",
            }
        )
        writer.writerow(
            {
                "repo_name": "owner/good-repo",
                "language": "python",
                "clone_url": str(good_repo),
                "commit_sha": sha,
                "agent_type": "copilot",
                "commit_date": "2025-01-02",
            }
        )

    out_dir = tmp_path / "out"
    result = collect_agent_test_commits(commit_dir, out_dir, workers=2)

    assert result["clone_failures"] == 1
    assert result["repos_processed"] == 1

    checkpoint = json.loads((out_dir / "agent_test_commits.checkpoint.json").read_text())
    assert "owner/bad-repo" not in checkpoint["completed_repos"]
    assert "owner/good-repo" in checkpoint["completed_repos"]


def test_default_output_dir_no_versioned_subfolder_when_tag_empty():
    """With empty COLLECTION_OUTPUT_TAG, default output is root test-commits dir."""
    from pathlib import Path

    default_path = Path("output/test-commits") / COLLECTION_OUTPUT_TAG
    assert COLLECTION_OUTPUT_TAG == ""
    assert str(default_path).rstrip("/").endswith("output/test-commits")
