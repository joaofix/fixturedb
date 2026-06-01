from pathlib import Path

from collection.db import (
    initialise_db,
    db_session,
    upsert_test_file,
    insert_fixture,
    insert_human_inter_fixtures_coordinated,
)
from collection.corpus_utils import construct_repo_dict


def test_coordinator_inserts(tmp_path: Path):
    db_path = tmp_path / "coord.db"
    initialise_db(db_path)

    with db_session(db_path) as conn:
        # Create repo using standard constructor to provide all expected keys
        repo = construct_repo_dict(
            "owner/repo", "python", stars=0, clone_url=str(db_path)
        )
        cur = conn.execute(
            "INSERT INTO repositories (github_id, full_name, language, stars, clone_url) VALUES (?,?,?,?,?)",
            (
                123,
                repo["full_name"],
                repo["language"],
                repo["stars"],
                repo["clone_url"],
            ),
        )
        repo_id = cur.lastrowid

        # Add test file and fixture
        file_id = upsert_test_file(conn, repo_id, "tests/test_sample.py", "python")
        fixture = {
            "file_id": file_id,
            "repo_id": repo_id,
            "name": "fixture_one",
            "fixture_type": "pytest_decorator",
            "scope": "per_test",
            "start_line": 1,
            "end_line": 5,
            "loc": 5,
            "cyclomatic_complexity": 1,
            "max_nesting_depth": 1,
            "num_objects_instantiated": 0,
            "num_external_calls": 0,
            "num_parameters": 0,
            "reuse_count": 0,
            "has_teardown_pair": 0,
            "raw_source": "def f(): pass",
            "framework": "pytest",
            "num_mocks": 0,
        }
        insert_fixture(conn, fixture)

    # Now call coordinator to insert human_inter row
    selected = [
        {
            "repo_full_name": "owner/repo",
            "name": "fixture_one",
            "start_line": 1,
            "fixture_type": "pytest_decorator",
            "scope": "per_test",
            "start_line": 1,
            "end_line": 5,
            "loc": 5,
            "cyclomatic_complexity": 1,
            "mocks": [],
        }
    ]
    inserted = insert_human_inter_fixtures_coordinated(
        db_path, selected, seed=42, batch_size=10
    )
    assert inserted == 1
