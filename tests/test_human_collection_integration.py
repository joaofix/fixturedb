import csv
import subprocess
import threading
from collections import defaultdict
from types import SimpleNamespace

import pytest

import collection.human_corpus as human_corpus
from collection.corpus_utils import construct_repo_dict
from collection.db import db_session, initialise_db, is_checkpoint_completed
from collection.human_corpus import HumanCorpusCollector, HumanCorpusStats


def test_crash_mid_language_leaves_already_processed_repos_persisted(tmp_path, monkeypatch):
    """Regression test for the crash-safety fix in _process_human_within_language():
    it used to buffer every repo's result in memory and only persist (DB rows
    + fixture CSVs) after the WHOLE language's repo list finished scanning --
    a crash partway through (dead battery, killed process, ...) lost every
    repo already scanned, even though the expensive clone+full-history-scan
    work for them was already done. Persistence now happens per-repo,
    immediately after each repo's result is available, so repos processed
    before a crash must already be durable in the output DB."""
    out_db = tmp_path / "b.db"
    initialise_db(out_db)
    collector = HumanCorpusCollector(
        clones_dir=tmp_path / "clones",
        output_db=out_db,
        repo_qc_dir=tmp_path / "repo_qc",
    )

    def fake_result(repo_name: str) -> dict:
        return {
            "repo_name": repo_name,
            "language_name": "python",
            "status": "ok",
            "skip_reason": None,
            "domain": "web",
            "repo_age": 1.0,
            "num_contributors": 1,
            "repo_data": construct_repo_dict(
                full_name=repo_name,
                language="python",
                stars=0,
                forks=0,
                description="",
                topics="[]",
                created_at="2019-01-01T00:00:00Z",
                pushed_at="2020-01-01T00:00:00Z",
                clone_url=f"https://github.com/{repo_name}.git",
                github_id=abs(hash(repo_name)) % 1_000_000,
                num_contributors=1,
                domain="web",
                repo_age_years=1.0,
            ),
            "test_commit_rows": [],
            "fixtures": [],
            "commits_accepted": 0,
            "commits_rejected": 0,
        }

    call_count = {"n": 0}

    def fake_process(repo):
        call_count["n"] += 1
        if call_count["n"] == 3:
            raise RuntimeError("simulated crash (e.g. process killed mid-scan)")
        return fake_result(repo["full_name"])

    monkeypatch.setattr(collector, "_process_human_repository", fake_process)

    lang_repos = [{"full_name": f"owner/repo{i}", "language": "python"} for i in range(5)]
    stats = HumanCorpusStats()
    language_progress = {
        "python": {"total_repos": 5, "completed": 0, "avg_fixtures_per_repo": 0}
    }

    with pytest.raises(RuntimeError, match="simulated crash"):
        collector._process_human_within_language(
            current_lang="python",
            lang_repos=lang_repos,
            workers=1,
            only_write_test_commits=False,
            stats=stats,
            progress_lock=threading.Lock(),
            language_progress=language_progress,
            repo_ages=[],
            repo_contributors=[],
            all_test_commit_rows=[],
            test_commit_rows_by_language=defaultdict(list),
            progress_file=tmp_path / "progress.json",
        )

    # repo0 and repo1 were fully processed and persisted before the
    # simulated crash on repo2's call -- their DB rows must survive it.
    with db_session(out_db) as conn:
        names = {
            row[0] for row in conn.execute("SELECT full_name FROM repositories").fetchall()
        }
    assert names == {"owner/repo0", "owner/repo1"}


def test_human_collection_run_mocked(tmp_path, monkeypatch, make_csv):
    # Setup directories and DB
    clones_dir = tmp_path / "clones"
    clones_dir.mkdir()
    repo_qc_dir = tmp_path / "repo_qc"
    repo_qc_dir.mkdir()
    out_db = tmp_path / "between.db"
    test_commits_dir = tmp_path / "test_commits"

    initialise_db(out_db)

    # Create a minimal, already-resolved repo list (as discover-repos --dataset b
    # would write) so strict within-mode selection is satisfied.
    make_csv(
        repo_qc_dir,
        "python_agent_repo.csv",
        rows=[
            {
                "repo_name": "owner/fixture_repo",
                "full_name": "owner/fixture_repo",
                "language": "python",
                "stars": "100",
                "forks": "10",
                "num_contributors": "1",
                "clone_url": "https://github.com/owner/fixture_repo.git",
                "has_agent_config": "1",
            }
        ],
        dest_name="python_repo.csv",
    )

    # Monkeypatch cloning to create repo directory
    def fake_clone(url, path, shallow_since=None):
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

        def _extract_from_agent_commits(self, repo_name, commits, stats=None):
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
