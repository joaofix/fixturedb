import csv
import subprocess
from types import SimpleNamespace

import collection.human_corpus as human_corpus
from collection.db import db_session, initialise_db, is_checkpoint_completed
from collection.human_corpus import HumanCorpusCollector


def test_human_collection_run_mocked(tmp_path, monkeypatch, make_csv):
    # Setup directories and DB
    clones_dir = tmp_path / "clones"
    clones_dir.mkdir()
    repo_qc_dir = tmp_path / "repo_qc"
    repo_qc_dir.mkdir()
    fixtures_dir = repo_qc_dir / "fixtures-from-agents"
    fixtures_dir.mkdir()
    out_db = tmp_path / "between.db"
    test_commits_dir = tmp_path / "test_commits"

    initialise_db(out_db)

    # Create a minimal agent fixture repo list so strict within-mode selection is satisfied
    repos_dir = fixtures_dir / "repos"
    repos_dir.mkdir()
    make_csv(repos_dir, "python_agent_fixture_repos.csv")

    # Monkeypatch cloning to create repo directory
    def fake_clone(url, path):
        path.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "init", "-b", "main", str(path)], check=True, capture_output=True
        )
        subprocess.run(
            ["git", "-C", str(path), "config", "user.email", "test@example.com"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(path), "config", "user.name", "Test"],
            check=True,
            capture_output=True,
        )
        (path / "file.txt").write_text("hello\n")
        subprocess.run(
            ["git", "-C", str(path), "add", "file.txt"], check=True, capture_output=True
        )
        subprocess.run(
            ["git", "-C", str(path), "commit", "-m", "initial"],
            check=True,
            capture_output=True,
        )
        return True

    monkeypatch.setattr(human_corpus, "clone_repo_for_commit_scan", fake_clone)

    # Fake scanner returns one human test commit
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
                    test_files=["tests/test_foo.py"],
                )
            ]

    monkeypatch.setattr(human_corpus, "Tier1RepositoryScanner", FakeScanner)

    # Fake extractor returns one complete fixture
    class FakeExtractor:
        def __init__(self, clones_dir=None, source_db=None, start_date=None):
            pass

        def _extract_from_agent_commits(self, repo_name, commits):
            return [
                {
                    "name": "my_fixture",
                    "file_path": "tests/test_foo.py",
                    "start_line": 10,
                    "end_line": 20,
                    "loc": 5,
                    "fixture_type": "pytest_decorator",
                    "scope": "per_test",
                    "cyclomatic_complexity": 1,
                    "max_nesting_depth": 1,
                    "num_objects_instantiated": 0,
                    "num_external_calls": 0,
                    "num_parameters": 0,
                    "has_teardown_pair": 0,
                    "raw_source": "def my_fixture(): pass",
                    "framework": "pytest",
                    "mocks": [],
                    "commit_sha": "deadbeef",
                    "commit_author_name": "Alice",
                    "commit_author_email": "alice@example.com",
                    "commit_date": "2020-01-01",
                    "is_complete_addition": 1,
                }
            ]

    monkeypatch.setattr(human_corpus, "AgentFixtureExtractor", FakeExtractor)

    collector = HumanCorpusCollector(
        corpus_db_path=out_db,
        clones_dir=clones_dir,
        output_db=out_db,
        repo_qc_dir=repo_qc_dir,
        test_commits_csv=test_commits_dir,
        fixtures_output_dir=tmp_path,
    )

    # Run the collector in fast (single-worker) mode; this should persist fixtures
    stats, db_path = collector.run(repos_per_language=1, workers=1)

    # Basic assertions (do not require running tests now)
    assert db_path == out_db
    # expect at least one fixture collected according to stats
    assert stats.fixtures_collected >= 1

    out_csv = test_commits_dir / "python_human_test_commit.csv"
    assert out_csv.exists()

    with out_csv.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))

    assert len(rows) == 1
    assert rows[0]["repo_name"] == "owner/fixture_repo"

    with db_session(out_db) as conn:
        assert is_checkpoint_completed(conn, 0, "human_within_complete:all")

    # A second run should short-circuit immediately once the completion checkpoint exists.
    stats2, db_path2 = collector.run(repos_per_language=1, workers=1)
    assert db_path2 == out_db
    assert stats2.fixtures_collected == 0
    assert stats2.repos_scanned == 0
