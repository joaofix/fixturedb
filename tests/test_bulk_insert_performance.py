import time

from collection.db import (
    db_session,
    initialise_db,
    insert_human_inter_fixture,
    insert_human_inter_fixtures_bulk,
)


def make_fixture(i, repo_id, file_id=1):
    return {
        "file_id": file_id,
        "repo_id": repo_id,
        "name": f"fixture_{repo_id}_{i}",
        "fixture_type": "pytest_decorator",
        "scope": "per_test",
        "start_line": i * 10,
        "end_line": i * 10 + 5,
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
        "commit_sha": "deadbeef",
        "commit_author_name": "Alice",
        "commit_author_email": "alice@example.com",
        "commit_date": "2020-01-01",
        "matched_control_id": None,
        "match_score": None,
        "provenance": "{}",
    }


def test_bulk_insert_vs_single(tmp_path):
    db_path = tmp_path / "perf.db"
    initialise_db(db_path)

    N = 500  # moderate sample size
    fixtures = [make_fixture(i, repo_id=(i % 10) + 1) for i in range(N)]

    # Measure bulk insert
    with db_session(db_path) as conn:
        t0 = time.perf_counter()
        inserted = insert_human_inter_fixtures_bulk(conn, fixtures)
        t1 = time.perf_counter()
        bulk_time = t1 - t0

    # Now measure per-row insertion on a fresh DB
    db_path2 = tmp_path / "perf2.db"
    initialise_db(db_path2)

    with db_session(db_path2) as conn:
        t0 = time.perf_counter()
        for f in fixtures:
            insert_human_inter_fixture(conn, f)
        t1 = time.perf_counter()
        single_time = t1 - t0

    # Bulk should be faster or at least not dramatically slower
    assert bulk_time <= single_time * 1.5
    # Confirm counts inserted
    with db_session(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) as n FROM human_inter_fixtures").fetchone()
        assert row["n"] == inserted
