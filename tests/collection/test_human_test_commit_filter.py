import csv
import json
import subprocess
from pathlib import Path

from collection.test_commit_filter import collect_human_test_commits


def init_minimal_repo(path: Path) -> str:
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
    (tests_dir / "test_sample.py").write_text("def test_x():\n    assert True\n")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(path), "commit", "-m", "Add test file"], check=True
    )
    sha = (
        subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"])
        .decode()
        .strip()
    )
    return sha


def test_collect_human_test_commits(tmp_path: Path):
    repo_dir = tmp_path / "repo"
    commit_sha = init_minimal_repo(repo_dir)

    repo_qc_dir = tmp_path / "repo_qc"
    repo_qc_dir.mkdir()
    csv_path = repo_qc_dir / "python_agent_repo_qc.csv"
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
    result = collect_human_test_commits(repo_qc_dir, out_dir, workers=1)
    assert result["test_commits_found"] >= 1

    out_csv = out_dir / "python_human_test_commit_qc.csv"
    assert out_csv.exists()

    with out_csv.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
    assert any(r["commit_sha"] == commit_sha for r in rows)
