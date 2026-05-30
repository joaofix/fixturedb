import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from collection.human_corpus import HumanCorpusCollector
import collection.human_corpus as human_corpus
from collection.db import initialise_db


def test_collect_inter_human_monkeypatched(tmp_path, monkeypatch):
    # Setup temp dirs and DB
    clones_dir = tmp_path / "clones"
    clones_dir.mkdir()
    out_db = tmp_path / "between.db"

    # Minimal agent repo list with one repo
    repo = {
        "full_name": "owner/testrepo",
        "language": "python",
        "clone_url": "https://example.com/owner/testrepo.git",
        "github_id": 1,
    }

    # Monkeypatch clone to create dir and succeed
    def fake_clone(url, path):
        path.mkdir(parents=True, exist_ok=True)
        # create a fake .git/shallow to mimic shallow state not present
        (path / ".git").mkdir(exist_ok=True)
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
                    "reuse_count": 0,
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

    # Ensure the output DB is initialised
    initialise_db(out_db)

    collector = HumanCorpusCollector(
        corpus_db_path=out_db,
        clones_dir=clones_dir,
        output_db=out_db,
        repo_qc_dir=tmp_path,
    )

    # Provide explicit targets so sampler selects our single fixture
    stats, db_path = collector.collect_inter_human(
        [repo], targets={"python": 1}, workers=1
    )

    # Verify output DB path and that at least one human_inter_fixtures row exists
    assert db_path == out_db
    conn = sqlite3.connect(str(db_path))
    cur = conn.execute("SELECT COUNT(*) as n FROM human_inter_fixtures")
    n = cur.fetchone()[0]
    conn.close()
    assert n >= 1
