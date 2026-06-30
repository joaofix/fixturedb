import sqlite3

from collection.human_corpus import HumanCorpusCollector


class FakeCommit:
    def __init__(self, sha, role, is_test, date):
        self.commit_sha = sha
        self.commit_role = role
        self.is_test_commit = is_test
        self.commit_date = date
        self.agent_type = None


def test_collect_inter_human_basic(monkeypatch, tmp_path):
    output_db = tmp_path / "between-group.db"

    # Prepare a minimal agent repo list
    agent_repos = [
        {
            "github_id": 111,
            "full_name": "owner/repo",
            "language": "py",
            "clone_url": "https://example.com/owner_repo.git",
        }
    ]

    # Monkeypatch cloning to create a fake repo directory
    def fake_clone(clone_url, target_dir):
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / ".git").mkdir(parents=True, exist_ok=True)
        return True

    monkeypatch.setattr(
        "collection.human_corpus.clone_repo_for_commit_scan", fake_clone
    )

    # Monkeypatch scanner to return one human test commit dated pre-2021
    class FakeScanner:
        def __init__(self, *args, **kwargs):
            pass

        def scan_repo_commit_roles(
            self, repo_path, start_date=None, language=None, detect_test_files=False
        ):
            return [FakeCommit("deadbeef", "human", True, "2020-01-01")]

    monkeypatch.setattr("collection.human_corpus.Tier1RepositoryScanner", FakeScanner)

    # Monkeypatch extractor to return one complete fixture
    def fake_extract(self, repo_name=None, commits=None):
        return [
            {
                "name": "fix1",
                "start_line": 1,
                "end_line": 3,
                "is_complete_addition": True,
                "file_path": "tests/test_x.py",
                "mocks": [],
                "fixture_type": "pytest_decorator",
                "scope": "module",
                "loc": 3,
                "cyclomatic_complexity": 1,
                "max_nesting_depth": 0,
                "num_objects_instantiated": 0,
                "num_external_calls": 0,
                "num_parameters": 0,
                "reuse_count": 0,
                "has_teardown_pair": 0,
                "raw_source": "def f(): pass",
                "framework": "pytest",
                "commit_sha": "deadbeef",
                "commit_author_name": "alice",
                "commit_author_email": "a@b.com",
                "commit_date": "2020-01-01",
            }
        ]

    monkeypatch.setattr(
        "collection.human_corpus.AgentFixtureExtractor._extract_from_agent_commits",
        fake_extract,
    )

    # Run collector
    collector = HumanCorpusCollector(
        corpus_db_path=tmp_path / "corpus.db", output_db=output_db, repo_qc_dir=tmp_path, fixtures_output_dir=tmp_path
    )
    stats, db_path = collector.collect_inter_human(
        agent_repos=agent_repos, targets={"py": 1}, seed=7
    )

    # Verify DB contains at least one human_inter_fixtures row
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("SELECT COUNT(1) FROM human_inter_fixtures")
    count = cur.fetchone()[0]
    conn.close()

    assert count >= 1
