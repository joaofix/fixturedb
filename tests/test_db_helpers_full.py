from collection.db import (
    classify_domain,
    compute_repo_age_at_date,
    compute_star_tier,
    db_session,
    get_analyzed_count_by_language,
    get_corpus_stats,
    initialise_db,
    insert_commit_observation,
    insert_fixture,
    insert_mock_usage,
    insert_test_commit,
    set_repo_analysed,
    update_agent_commit_stats,
    upsert_repository,
    upsert_test_file,
)


def test_db_helpers_end_to_end(tmp_path):
    db_path = tmp_path / "test.db"
    initialise_db(db_path)

    # Insert repository and test file
    repo = {
        "github_id": 999,
        "full_name": "owner/testrepo",
        "language": "python",
        "stars": 42,
        "forks": 1,
        "description": "A test repo",
        "topics": '["web"]',
        "created_at": "2019-01-01T00:00:00Z",
        "pushed_at": "2020-01-01T00:00:00Z",
        "clone_url": "https://github.com/owner/testrepo.git",
        "num_contributors": 2,
        "domain": None,
        "star_tier": None,
        "repo_age_years": None,
    }

    with db_session(db_path) as conn:
        repo_id, is_new = upsert_repository(conn, repo)
        assert is_new is True
        # Upsert again should not be new
        repo_id2, is_new2 = upsert_repository(conn, repo)
        assert repo_id == repo_id2
        assert is_new2 is False

        file_id = upsert_test_file(conn, repo_id, "tests/test_foo.py", "python")
        assert isinstance(file_id, int) and file_id > 0

        # Insert fixture
        fixture = {
            "file_id": file_id,
            "repo_id": repo_id,
            "name": "my_fixture",
            "fixture_type": "pytest_decorator",
            "scope": "per_test",
            "start_line": 10,
            "end_line": 20,
            "loc": 5,
            "cyclomatic_complexity": 1,
            "max_nesting_depth": 1,
            "num_objects_instantiated": 0,
            "num_external_calls": 0,
            "num_parameters": 0,
            "reuse_count": 0,
            "has_teardown_pair": 0,
            "raw_source": "def my_fixture(): pass",
            "framework": "pytest",
            "num_mocks": 0,
            "commit_sha": "deadbeef",
            "commit_kind": "human",
            "is_complete_addition": 1,
        }
        fixture_id = insert_fixture(conn, fixture)
        assert isinstance(fixture_id, int) and fixture_id > 0

        # Insert commit observation and test commit
        obs = {
            "repo_id": repo_id,
            "commit_sha": "deadbeef",
            "commit_role": "human",
            "agent_type": None,
            "commit_date": "2020-01-01",
            "fixture_count": 1,
            "mock_usage_count": 0,
            "test_file_count": 1,
        }
        obs_id = insert_commit_observation(conn, obs)
        assert isinstance(obs_id, int) and obs_id > 0

        test_commit = {
            "repo_id": repo_id,
            "commit_sha": "deadbeef",
            "commit_role": "human",
            "agent_type": None,
            "commit_date": "2020-01-01",
            "language": "python",
            "test_file_count": 1,
            "test_file_paths": "[]",
        }
        tc_id = insert_test_commit(conn, test_commit)
        assert isinstance(tc_id, int) and tc_id > 0

        # Insert a mock usage referencing the fixture
        mock = {
            "fixture_id": fixture_id,
            "repo_id": repo_id,
            "framework": "unittest_mock",
            "category": "mock",
            "target_identifier": "module.Client",
            "num_interactions_configured": 1,
            "raw_snippet": "mock.call()",
        }
        insert_mock_usage(conn, mock)

        stats = get_corpus_stats(conn)
        assert "fixtures" in stats and stats["fixtures"] >= 1

        # mark repo as analysed so language appears in analysed counts
        set_repo_analysed(
            conn, repo_id, num_test_files=1, num_fixtures=1, num_mock_usages=0
        )
        lang_counts = get_analyzed_count_by_language(conn)
        assert "python" in lang_counts and lang_counts["python"] >= 1


def test_update_agent_commit_stats(tmp_path):
    """Dataset A's repo-level agent-commit counters persist and default to 0."""
    db_path = tmp_path / "agent_stats.db"
    initialise_db(db_path)

    repo = {
        "github_id": 1234,
        "full_name": "owner/agentrepo",
        "language": "python",
        "stars": 10,
        "forks": 0,
        "description": "",
        "topics": "[]",
        "created_at": "2020-01-01T00:00:00Z",
        "pushed_at": "2020-01-01T00:00:00Z",
        "clone_url": "https://github.com/owner/agentrepo.git",
        "num_contributors": 1,
        "domain": None,
        "star_tier": None,
        "repo_age_years": None,
    }

    with db_session(db_path) as conn:
        repo_id, _ = upsert_repository(conn, repo)

        # Defaults to 0 before any stats are recorded.
        row = conn.execute(
            "SELECT agent_commits_touching_tests, agent_commits_rejected_mixed_test_diff, "
            "agent_commits_accepted FROM repositories WHERE id = ?",
            (repo_id,),
        ).fetchone()
        assert tuple(row) == (0, 0, 0)

        update_agent_commit_stats(
            conn,
            repo_id,
            {
                "agent_commits_touching_tests": 5,
                "rejected_mixed_test_diff": 2,
                "accepted": 3,
            },
        )

        row = conn.execute(
            "SELECT agent_commits_touching_tests, agent_commits_rejected_mixed_test_diff, "
            "agent_commits_accepted FROM repositories WHERE id = ?",
            (repo_id,),
        ).fetchone()
        assert tuple(row) == (5, 2, 3)


def test_classify_and_age():
    # classify_domain
    topic = '["django", "rest"]'
    desc = "A web framework project"
    assert classify_domain(topic, desc) == "web"

    # compute_star_tier
    assert compute_star_tier(600) == "core"
    assert compute_star_tier(10) == "extended"

    # compute_repo_age_at_date
    created = "2019-01-01T00:00:00Z"
    age = compute_repo_age_at_date(created, "2020-01-01T00:00:00Z")
    assert age is not None and age > 0
