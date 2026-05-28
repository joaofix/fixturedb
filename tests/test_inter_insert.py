import tempfile
from pathlib import Path
import os

from collection.db import initialise_db, db_session, upsert_repository, upsert_test_file, insert_fixture, insert_human_inter_fixtures_bulk
from collection.corpus_utils import construct_repo_dict


def test_bulk_insert_and_conflict_handling(tmp_path):
    db_path = tmp_path / "test.db"
    initialise_db(db_path)

    repo = construct_repo_dict(full_name="owner/repo", language="python", github_id=123)
    fixtures = []

    with db_session(db_path) as conn:
        repo_id, _ = upsert_repository(conn, repo)
        file_id = upsert_test_file(conn, repo_id, "tests/test_sample.py", "python")

        fixture_data = {
            "file_id": file_id,
            "repo_id": repo_id,
            "name": "sample_fixture",
            "fixture_type": "pytest_decorator",
            "scope": "per_test",
            "start_line": 10,
            "end_line": 20,
            "loc": 8,
            "cyclomatic_complexity": 1,
            "max_nesting_depth": 1,
            "num_objects_instantiated": 0,
            "num_external_calls": 0,
            "num_parameters": 0,
            "reuse_count": 0,
            "has_teardown_pair": 0,
            "raw_source": "def sample_fixture(): pass",
            "framework": "pytest",
            "num_mocks": 0,
            "commit_sha": "deadbeef",
            "commit_kind": "human",
            "is_complete_addition": 1,
        }
        fixture_id = insert_fixture(conn, fixture_data)

    inter_row = {
        "file_id": file_id,
        "repo_id": repo_id,
        "name": "sample_fixture",
        "fixture_type": "pytest_decorator",
        "scope": "per_test",
        "start_line": 10,
        "end_line": 20,
        "loc": 8,
        "cyclomatic_complexity": 1,
        "max_nesting_depth": 1,
        "num_objects_instantiated": 0,
        "num_external_calls": 0,
        "num_parameters": 0,
        "reuse_count": 0,
        "has_teardown_pair": 0,
        "raw_source": "def sample_fixture(): pass",
        "framework": "pytest",
        "num_mocks": 0,
        "commit_sha": "deadbeef",
        "commit_author_name": "Alice",
        "commit_author_email": "alice@example.com",
        "commit_date": "2020-01-01",
        "matched_control_id": None,
        "match_score": None,
        "provenance": '{"sample_seed": 42}',
    }

    # First bulk insert
    with db_session(db_path) as conn:
        inserted = insert_human_inter_fixtures_bulk(conn, [inter_row])
        assert inserted == 1

    # Confirm row exists
    with db_session(db_path) as conn:
        cur = conn.execute("SELECT COUNT(*) AS n FROM human_inter_fixtures WHERE file_id=?", (file_id,))
        assert cur.fetchone()["n"] == 1

    # Second bulk insert (duplicate) should not raise and should attempt 1 insert
    with db_session(db_path) as conn:
        inserted2 = insert_human_inter_fixtures_bulk(conn, [inter_row])
        assert inserted2 == 1

    with db_session(db_path) as conn:
        cur = conn.execute("SELECT COUNT(*) AS n FROM human_inter_fixtures WHERE file_id=?", (file_id,))
        assert cur.fetchone()["n"] == 1
