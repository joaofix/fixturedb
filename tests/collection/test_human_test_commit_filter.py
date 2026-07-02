import csv
import gzip
import subprocess
from pathlib import Path
from types import SimpleNamespace

from collection.test_commit_filter import (
    collect_human_test_commits,
    collect_human_test_commits_from_raw_search,
)


class FakeScanner:
    def __init__(self, corpus_db_path):
        pass

    def scan_repo_commit_roles(
        self, repo_path, start_date, language, detect_test_files=True
    ):
        return [
            SimpleNamespace(
                commit_sha="deadbeef",
                commit_role="human",
                is_test_commit=True,
                commit_date="2020-01-01",
                agent_type=None,
                test_files=["tests/test_sample.py"],
            )
        ]


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


def test_collect_human_test_commits(tmp_path: Path, monkeypatch):
    repo_dir = tmp_path / "repo"
    init_minimal_repo(repo_dir)

    monkeypatch.setattr(
        "collection.test_commit_filter.Tier1RepositoryScanner", FakeScanner
    )

    repo_qc_dir = tmp_path / "repo_qc"
    repo_qc_dir.mkdir()
    csv_path = repo_qc_dir / "python_agent_repo.csv"
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

    out_csv = out_dir / "python_human_test_commit.csv"
    assert out_csv.exists()

    with out_csv.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
    assert any(r["commit_sha"] == "deadbeef" for r in rows)


def test_collect_human_test_commits_from_raw_search(tmp_path: Path, monkeypatch):
    repo_dir = tmp_path / "repo"
    commit_sha = init_minimal_repo(repo_dir)

    monkeypatch.setattr(
        "collection.test_commit_filter.Tier1RepositoryScanner", FakeScanner
    )

    raw_dir = tmp_path / "github-search-raw"
    raw_dir.mkdir()
    raw_csv = raw_dir / "python.csv.gz"
    with gzip.open(raw_csv, "wt", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "id",
                "name",
                "isFork",
                "commits",
                "branches",
                "releases",
                "forks",
                "mainLanguage",
                "defaultBranch",
                "license",
                "homepage",
                "watchers",
                "stargazers",
                "contributors",
                "size",
                "createdAt",
                "pushedAt",
                "updatedAt",
                "totalIssues",
                "openIssues",
                "totalPullRequests",
                "openPullRequests",
                "blankLines",
                "codeLines",
                "commentLines",
                "metrics",
                "lastCommit",
                "lastCommitSHA",
                "hasWiki",
                "isArchived",
                "isDisabled",
                "isLocked",
                "languages",
                "labels",
                "topics",
                "clone_url",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "id": "1",
                "name": "owner/raw_repo",
                "isFork": "false",
                "commits": "1",
                "branches": "1",
                "releases": "0",
                "forks": "0",
                "mainLanguage": "python",
                "defaultBranch": "main",
                "license": "",
                "homepage": "",
                "watchers": "0",
                "stargazers": "0",
                "contributors": "1",
                "size": "1",
                "createdAt": "2020-01-01T00:00:00Z",
                "pushedAt": "2020-01-02T00:00:00Z",
                "updatedAt": "2020-01-02T00:00:00Z",
                "totalIssues": "0",
                "openIssues": "0",
                "totalPullRequests": "0",
                "openPullRequests": "0",
                "blankLines": "0",
                "codeLines": "1",
                "commentLines": "0",
                "metrics": "{}",
                "lastCommit": "",
                "lastCommitSHA": commit_sha,
                "hasWiki": "false",
                "isArchived": "false",
                "isDisabled": "false",
                "isLocked": "false",
                "languages": "python",
                "labels": "[]",
                "topics": "[]",
                "clone_url": str(repo_dir),
            }
        )

    out_dir = tmp_path / "out"
    result = collect_human_test_commits_from_raw_search(raw_dir, out_dir, workers=1)

    assert result["test_commits_found"] >= 1
    out_csv = out_dir / "python_human_test_commit.csv"
    assert out_csv.exists()

    with out_csv.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert any(r["commit_sha"] == "deadbeef" for r in rows)
