from collection.db import (
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
from collection.repo_metadata import (
    classify_domain,
    compute_repo_age_at_date,
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


def test_insert_fixture_dedupes_per_commit_not_across_commits(tmp_path):
    """Regression: fixtures' UNIQUE constraint was (file_id, name,
    start_line) with no commit_sha, so two different commits adding a
    same-named fixture at the same line (plausible after a fixture is
    removed and later re-added) silently collided -- the second insert was
    dropped via ON CONFLICT DO NOTHING, even though it belongs to a
    genuinely different commit and should be its own row."""
    db_path = tmp_path / "dedup.db"
    initialise_db(db_path)

    repo = {
        "github_id": 555,
        "full_name": "owner/deduprepo",
        "language": "python",
        "stars": 10,
        "forks": 0,
        "description": "",
        "topics": "[]",
        "created_at": "2020-01-01T00:00:00Z",
        "pushed_at": "2020-01-01T00:00:00Z",
        "clone_url": "https://github.com/owner/deduprepo.git",
        "num_contributors": 1,
        "domain": None,
        "repo_age_years": None,
    }

    with db_session(db_path) as conn:
        repo_id, _ = upsert_repository(conn, repo)
        file_id = upsert_test_file(conn, repo_id, "tests/conftest.py", "python")

        base_fixture = {
            "file_id": file_id,
            "repo_id": repo_id,
            "name": "mock_client",
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
            "has_teardown_pair": 0,
            "framework": "pytest",
            "num_mocks": 0,
        }

        id1 = insert_fixture(
            conn, {**base_fixture, "commit_sha": "sha1", "raw_source": "SHA1 VERSION"}
        )
        id2 = insert_fixture(
            conn, {**base_fixture, "commit_sha": "sha2", "raw_source": "SHA2 VERSION"}
        )

        assert id1 != id2

        rows = conn.execute(
            "SELECT commit_sha, raw_source FROM fixtures WHERE file_id = ? ORDER BY commit_sha",
            (file_id,),
        ).fetchall()
        assert [(r["commit_sha"], r["raw_source"]) for r in rows] == [
            ("sha1", "SHA1 VERSION"),
            ("sha2", "SHA2 VERSION"),
        ]

        # Re-inserting the exact same (file, name, line, commit) still dedupes.
        id1_again = insert_fixture(
            conn, {**base_fixture, "commit_sha": "sha1", "raw_source": "SHA1 VERSION"}
        )
        assert id1_again == id1


def test_insert_fixture_dedupes_when_commit_sha_omitted(tmp_path):
    """Dataset C's pre2021 extractor never sets commit_sha at all. NULL is
    always-distinct in a SQLite UNIQUE index, so commit_sha must fall back
    to "" (not NULL) for such callers, or dedup would be silently disabled
    for the entire pre-agent baseline dataset."""
    db_path = tmp_path / "no_commit_sha.db"
    initialise_db(db_path)

    repo = {
        "github_id": 556,
        "full_name": "owner/pre2021repo",
        "language": "python",
        "stars": 10,
        "forks": 0,
        "description": "",
        "topics": "[]",
        "created_at": "2020-01-01T00:00:00Z",
        "pushed_at": "2020-01-01T00:00:00Z",
        "clone_url": "https://github.com/owner/pre2021repo.git",
        "num_contributors": 1,
        "domain": None,
        "repo_age_years": None,
    }

    with db_session(db_path) as conn:
        repo_id, _ = upsert_repository(conn, repo)
        file_id = upsert_test_file(conn, repo_id, "tests/test_foo.py", "python")

        fixture = {
            "file_id": file_id,
            "repo_id": repo_id,
            "name": "sample_data",
            "fixture_type": "pytest_decorator",
            "scope": "per_test",
            "start_line": 5,
            "end_line": 8,
            "loc": 3,
            "cyclomatic_complexity": 1,
            "max_nesting_depth": 1,
            "num_objects_instantiated": 0,
            "num_external_calls": 0,
            "num_parameters": 0,
            "has_teardown_pair": 0,
            "raw_source": "def sample_data(): return 1",
            "framework": "pytest",
            "num_mocks": 0,
        }

        first_id = insert_fixture(conn, fixture)
        second_id = insert_fixture(conn, dict(fixture))

        assert first_id == second_id

        rows = conn.execute(
            "SELECT COUNT(*) as n FROM fixtures WHERE file_id = ?", (file_id,)
        ).fetchone()
        assert rows["n"] == 1


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

    # compute_repo_age_at_date
    created = "2019-01-01T00:00:00Z"
    age = compute_repo_age_at_date(created, "2020-01-01T00:00:00Z")
    assert age is not None and age > 0


def test_classify_domain_uses_word_boundaries_not_substrings():
    """Regression: classify_domain used a plain `kw in text` substring
    check, so short/common keywords collided with unrelated English words
    inside longer words -- "ai" inside "email", "os" inside "postgresql",
    "auth" inside "author" -- mis-tagging the domain control variable used
    in the between-group balance comparison."""
    assert classify_domain("[]", "A lightweight email notification library") != "ml"
    assert classify_domain("[]", "A fast PostgreSQL client and query builder") == "database"
    assert (
        classify_domain("[]", "A static site generator, by the author of Foo")
        != "security"
    )
    # Real keyword usages must still match.
    assert classify_domain("[]", "Machine learning library using AI") == "ml"
    assert classify_domain("[]", "An authentication and oauth library") == "security"
