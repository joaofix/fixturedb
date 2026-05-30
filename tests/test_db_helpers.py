import sqlite3
from pathlib import Path

from collection.db import (
    initialise_db,
    db_session,
    insert_human_inter_fixture,
    upsert_repository,
    upsert_test_file,
)


def test_insert_human_inter_fixture(tmp_path):
    db_path = tmp_path / "test.db"
    initialise_db(db_path)

    with db_session(db_path) as conn:
        # Insert a repository and a test file
        repo_row = {
            "github_id": 12345,
            "full_name": "owner/repo",
            "language": "py",
            "stars": 0,
            "forks": 0,
            "description": "",
            "topics": "[]",
            "created_at": "",
            "pushed_at": "",
            "clone_url": "",
            "domain": None,
            "star_tier": None,
            "repo_age_years": None,
            "num_contributors": 0,
        }
        repo_id, _ = upsert_repository(conn, repo_row)
        file_id = upsert_test_file(conn, repo_id, "tests/test_x.py", "py")

        inter_row = {
            "file_id": file_id,
            "repo_id": repo_id,
            "name": "fix1",
            "fixture_type": "pytest_decorator",
            "scope": "module",
            "start_line": 1,
            "end_line": 3,
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
            "num_mocks": 0,
            "commit_sha": "deadbeef",
            "commit_author_name": "alice",
            "commit_author_email": "a@b.com",
            "commit_date": "2020-01-01",
            "matched_control_id": None,
            "match_score": None,
            "provenance": "{}",
        }

        row_id = insert_human_inter_fixture(conn, inter_row)

        cur = conn.execute(
            "SELECT COUNT(1) FROM human_inter_fixtures WHERE id = ?", (row_id,)
        )
        count = cur.fetchone()[0]
        assert count == 1
