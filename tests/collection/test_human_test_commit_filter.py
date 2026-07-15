import csv
import gzip
import subprocess
from pathlib import Path
from types import SimpleNamespace

from collection.human_test_commit_filter import (
    collect_human_test_commits,
    collect_human_test_commits_from_raw_search,
)


def make_fake_scanner(commit_role, agent_type, commit_sha="deadbeef"):
    """FakeScanner factory: build a scanner whose single scanned commit has the
    given (commit_role, agent_type, commit_sha), for exercising the Dataset A
    disagreement cross-check with different classifications per test."""

    class _FakeScanner:
        def __init__(self, corpus_db_path):
            pass

        def scan_repo_commit_roles(
            self, repo_path, start_date, language, detect_test_files=True
        ):
            return [
                SimpleNamespace(
                    commit_sha=commit_sha,
                    commit_role=commit_role,
                    is_test_commit=True,
                    commit_date="2026-01-01",
                    agent_type=agent_type,
                    test_files=["tests/test_sample.py"],
                )
            ]

    return _FakeScanner


def write_dataset_a_commits_csv(commits_dir: Path, repo_name: str, rows: list[dict]) -> None:
    """Write a minimal datasets/a/commits/{lang}_commit.csv-shaped fixture for the
    Dataset A cross-check lookup (_load_dataset_a_commit_lookup only reads
    repo_name/commit_sha/agent_type, but the real file has more columns)."""
    commits_dir.mkdir(parents=True, exist_ok=True)
    csv_path = commits_dir / "python_commit.csv"
    header = ["repo_name", "commit_sha", "commit_url", "agent_type", "commit_date", "language"]
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=header)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "repo_name": repo_name,
                    "commit_sha": row["commit_sha"],
                    "commit_url": "",
                    "agent_type": row["agent_type"],
                    "commit_date": "2026-01-01",
                    "language": "python",
                }
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
        "collection.human_test_commit_filter.Tier1RepositoryScanner", FakeScanner
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
        "collection.human_test_commit_filter.Tier1RepositoryScanner", FakeScanner
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


def write_repo_qc_csv(repo_qc_dir: Path, repo_name: str, repo_dir: Path) -> None:
    repo_qc_dir.mkdir(parents=True, exist_ok=True)
    csv_path = repo_qc_dir / "python_agent_repo.csv"
    header = [
        "repo_name",
        "language",
        "clone_url",
        "has_agent_config",
        "stars",
        "num_contributors",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=header)
        writer.writeheader()
        writer.writerow(
            {
                "repo_name": repo_name,
                "language": "python",
                "clone_url": str(repo_dir),
                "has_agent_config": "1",
                "stars": "0",
                "num_contributors": "1",
            }
        )


def test_dataset_a_cross_check_no_dataset_a_dir_does_not_crash(tmp_path: Path, monkeypatch):
    """A missing/empty datasets/a/commits/ dir must not block Dataset B's own
    collection -- the cross-check is a safety net, not a hard dependency."""
    repo_dir = tmp_path / "repo"
    init_minimal_repo(repo_dir)
    monkeypatch.setattr(
        "collection.human_test_commit_filter.Tier1RepositoryScanner",
        make_fake_scanner(commit_role="human", agent_type=None),
    )
    repo_qc_dir = tmp_path / "repo_qc"
    write_repo_qc_csv(repo_qc_dir, "owner/repo", repo_dir)

    result = collect_human_test_commits(
        repo_qc_dir,
        tmp_path / "out",
        workers=1,
        dataset_a_commits_dir=tmp_path / "does-not-exist",
    )
    assert result["disagreements_found"] == 0
    assert result["disagreements_file"] is None


def test_dataset_a_cross_check_matching_classification_no_disagreement(
    tmp_path: Path, monkeypatch
):
    """Dataset B independently re-derives the same agent_type Dataset A already
    recorded for this SHA -- no disagreement."""
    repo_dir = tmp_path / "repo"
    init_minimal_repo(repo_dir)
    monkeypatch.setattr(
        "collection.human_test_commit_filter.Tier1RepositoryScanner",
        make_fake_scanner(commit_role="agent", agent_type="claude"),
    )
    repo_qc_dir = tmp_path / "repo_qc"
    write_repo_qc_csv(repo_qc_dir, "owner/repo", repo_dir)
    dataset_a_dir = tmp_path / "dataset_a_commits"
    write_dataset_a_commits_csv(
        dataset_a_dir, "owner/repo", [{"commit_sha": "deadbeef", "agent_type": "claude"}]
    )

    result = collect_human_test_commits(
        repo_qc_dir, tmp_path / "out", workers=1, dataset_a_commits_dir=dataset_a_dir
    )
    assert result["disagreements_found"] == 0


def test_dataset_a_cross_check_flags_mismatch_agent_vs_human(tmp_path: Path, monkeypatch):
    """Dataset A recorded this SHA as agent-authored, but Dataset B's fresh scan
    classifies it human -- this is the case that matters most (an A-confirmed
    agent commit could otherwise leak into Dataset B's human pool)."""
    repo_dir = tmp_path / "repo"
    init_minimal_repo(repo_dir)
    monkeypatch.setattr(
        "collection.human_test_commit_filter.Tier1RepositoryScanner",
        make_fake_scanner(commit_role="human", agent_type=None),
    )
    repo_qc_dir = tmp_path / "repo_qc"
    write_repo_qc_csv(repo_qc_dir, "owner/repo", repo_dir)
    dataset_a_dir = tmp_path / "dataset_a_commits"
    write_dataset_a_commits_csv(
        dataset_a_dir, "owner/repo", [{"commit_sha": "deadbeef", "agent_type": "claude"}]
    )

    result = collect_human_test_commits(
        repo_qc_dir, tmp_path / "out", workers=1, dataset_a_commits_dir=dataset_a_dir
    )
    assert result["disagreements_found"] == 1
    disagreements_path = Path(result["disagreements_file"])
    assert disagreements_path.exists()
    with disagreements_path.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 1
    assert rows[0]["reason"] == "mismatch"
    assert rows[0]["dataset_a_agent_type"] == "claude"
    assert rows[0]["dataset_b_role"] == "human"


def test_dataset_a_cross_check_flags_mismatch_different_agent_types(
    tmp_path: Path, monkeypatch
):
    """Dataset A said claude, Dataset B's fresh scan says copilot for the same SHA."""
    repo_dir = tmp_path / "repo"
    init_minimal_repo(repo_dir)
    monkeypatch.setattr(
        "collection.human_test_commit_filter.Tier1RepositoryScanner",
        make_fake_scanner(commit_role="agent", agent_type="copilot"),
    )
    repo_qc_dir = tmp_path / "repo_qc"
    write_repo_qc_csv(repo_qc_dir, "owner/repo", repo_dir)
    dataset_a_dir = tmp_path / "dataset_a_commits"
    write_dataset_a_commits_csv(
        dataset_a_dir, "owner/repo", [{"commit_sha": "deadbeef", "agent_type": "claude"}]
    )

    result = collect_human_test_commits(
        repo_qc_dir, tmp_path / "out", workers=1, dataset_a_commits_dir=dataset_a_dir
    )
    assert result["disagreements_found"] == 1
    with Path(result["disagreements_file"]).open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert rows[0]["reason"] == "mismatch"
    assert rows[0]["dataset_a_agent_type"] == "claude"
    assert rows[0]["dataset_b_agent_type"] == "copilot"


def test_dataset_a_cross_check_flags_agent_missing_from_dataset_a(tmp_path: Path, monkeypatch):
    """Dataset B's fresh scan finds a new agent commit Dataset A never saw --
    logged for human review (likely just repo activity since A's snapshot),
    not raised as an error."""
    repo_dir = tmp_path / "repo"
    init_minimal_repo(repo_dir)
    monkeypatch.setattr(
        "collection.human_test_commit_filter.Tier1RepositoryScanner",
        make_fake_scanner(commit_role="agent", agent_type="claude", commit_sha="deadbeef"),
    )
    repo_qc_dir = tmp_path / "repo_qc"
    write_repo_qc_csv(repo_qc_dir, "owner/repo", repo_dir)
    dataset_a_dir = tmp_path / "dataset_a_commits"
    # Dataset A knows about a *different* SHA in this repo, not this one.
    write_dataset_a_commits_csv(
        dataset_a_dir, "owner/repo", [{"commit_sha": "otherSha", "agent_type": "claude"}]
    )

    result = collect_human_test_commits(
        repo_qc_dir, tmp_path / "out", workers=1, dataset_a_commits_dir=dataset_a_dir
    )
    assert result["disagreements_found"] == 1
    with Path(result["disagreements_file"]).open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert rows[0]["reason"] == "dataset_a_missing"


def test_dataset_a_cross_check_no_flag_for_new_human_commit(tmp_path: Path, monkeypatch):
    """The common case: Dataset B classifies a commit as human, and Dataset A
    never examined that SHA at all (new repo activity, not a disagreement)."""
    repo_dir = tmp_path / "repo"
    init_minimal_repo(repo_dir)
    monkeypatch.setattr(
        "collection.human_test_commit_filter.Tier1RepositoryScanner",
        make_fake_scanner(commit_role="human", agent_type=None),
    )
    repo_qc_dir = tmp_path / "repo_qc"
    write_repo_qc_csv(repo_qc_dir, "owner/repo", repo_dir)
    dataset_a_dir = tmp_path / "dataset_a_commits"
    write_dataset_a_commits_csv(dataset_a_dir, "owner/repo", [])

    result = collect_human_test_commits(
        repo_qc_dir, tmp_path / "out", workers=1, dataset_a_commits_dir=dataset_a_dir
    )
    assert result["disagreements_found"] == 0
    assert result["disagreements_file"] is None
