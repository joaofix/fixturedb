from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import collection.human_corpus as human_corpus
from collection.db import initialise_db
from collection.human_corpus import HumanCorpusCollector


def test_integration_smoke_within_and_inter(tmp_path, monkeypatch):
    clones_dir = tmp_path / "clones"
    clones_dir.mkdir()
    out_db = tmp_path / "between.db"

    repo = {
        "full_name": "owner/testrepo",
        "language": "python",
        "clone_url": "https://example.com/owner/testrepo.git",
        "github_id": 1,
    }

    @contextmanager
    def fake_clone_with_function(func, url, path):
        path.mkdir(parents=True, exist_ok=True)
        (path / ".git").mkdir(exist_ok=True)
        yield path

    monkeypatch.setattr(human_corpus, "clone_with_function", fake_clone_with_function)

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

    monkeypatch.setattr(
        human_corpus,
        "stratified_sample_by_language",
        lambda candidates, targets, seed=42: list(candidates),
    )

    monkeypatch.setattr(
        human_corpus,
        "_human_fixture_csv_path",
        lambda language, kind, override=None: tmp_path
        / f"{language}_human_fixtures.csv",
    )

    def fake_persist_repository_and_fixtures(
        output_db, repo_data, fixtures_list, out_path=None, handle_mocks=False
    ):
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("a", encoding="utf-8", newline="") as fh:
            fh.write(
                f"{repo_data['full_name']},{repo_data['language']},{len(fixtures_list)}\n"
            )
        return len(fixtures_list)

    monkeypatch.setattr(
        human_corpus,
        "persist_repository_and_fixtures",
        fake_persist_repository_and_fixtures,
    )

    import collection.db as db_module

    monkeypatch.setattr(
        db_module,
        "insert_human_inter_fixtures_coordinated",
        lambda db_path, selected_fixtures, seed=42, batch_size=1000: len(
            selected_fixtures
        ),
    )

    initialise_db(out_db)

    collector = HumanCorpusCollector(
        corpus_db_path=out_db,
        clones_dir=clones_dir,
        output_db=out_db,
        repo_qc_dir=tmp_path,
    )
    # Ensure run() selects our single repo
    monkeypatch.setattr(
        human_corpus,
        "select_human_corpus_repositories",
        lambda repo_qc_dir, repos_per_language, language, require_fixture_repo_list: [
            repo
        ],
    )

    stats_run, db_path = collector.run(
        repos_per_language=None, language=None, only_write_test_commits=False, workers=1
    )
    assert db_path == out_db

    stats_inter, db_path = collector.collect_inter_human(
        [repo], targets={"python": 1}, workers=1
    )
    assert stats_inter.fixtures_collected == 1
