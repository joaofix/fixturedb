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


def test_upsert_repository_round_trips_repo_age_at_collection_years(tmp_path):
    """repo_age_at_collection_years should be persisted when supplied, and
    updated on a later upsert with a different value."""
    db_path = tmp_path / "test.db"
    initialise_db(db_path)

    repo = {
        "github_id": 111,
        "full_name": "owner/agerepo",
        "language": "python",
        "stars": 1,
        "forks": 0,
        "description": "",
        "topics": "[]",
        "created_at": "2019-01-01",
        "pushed_at": "",
        "clone_url": "https://github.com/owner/agerepo.git",
        "num_contributors": 0,
        "domain": None,
        "repo_age_years": None,
        "repo_age_at_collection_years": 5.5,
    }

    with db_session(db_path) as conn:
        repo_id, _ = upsert_repository(conn, repo)
        row = conn.execute(
            "SELECT repo_age_at_collection_years FROM repositories WHERE id = ?",
            (repo_id,),
        ).fetchone()
        assert row["repo_age_at_collection_years"] == 5.5

        # Re-upsert with an updated value (e.g. a later collection run)
        upsert_repository(conn, {**repo, "repo_age_at_collection_years": 6.1})
        row = conn.execute(
            "SELECT repo_age_at_collection_years FROM repositories WHERE id = ?",
            (repo_id,),
        ).fetchone()
        assert row["repo_age_at_collection_years"] == 6.1


def test_upsert_repository_backward_compatible_without_repo_age_at_collection_years(
    tmp_path,
):
    """Regression test: upsert_repository() is a fixed-column INSERT bound
    by named params from the caller's dict -- callers that predate
    repo_age_at_collection_years (e.g. paired_collection.py's own
    hand-built repo dict, which doesn't set it) must not crash just because
    the schema grew a new column."""
    db_path = tmp_path / "test.db"
    initialise_db(db_path)

    repo = {
        "github_id": 222,
        "full_name": "owner/legacycaller",
        "language": "python",
        "stars": 1,
        "forks": 0,
        "description": "",
        "topics": "[]",
        "created_at": "2019-01-01",
        "pushed_at": "",
        "clone_url": "https://github.com/owner/legacycaller.git",
        "num_contributors": 0,
        "domain": None,
        "repo_age_years": None,
        # repo_age_at_collection_years intentionally omitted
    }

    with db_session(db_path) as conn:
        repo_id, is_new = upsert_repository(conn, repo)
        assert is_new is True
        row = conn.execute(
            "SELECT repo_age_at_collection_years FROM repositories WHERE id = ?",
            (repo_id,),
        ).fetchone()
        assert row["repo_age_at_collection_years"] is None


def test_upsert_repository_round_trips_total_commits_since_agent_start(tmp_path):
    """total_commits_since_agent_start should be persisted when supplied,
    and updated on a later upsert -- same treatment as
    repo_age_at_collection_years above. Backs dataset_findings.py's "All
    commits" row (`_fetch_total_commits_since_agent_start()`)."""
    db_path = tmp_path / "test.db"
    initialise_db(db_path)

    repo = {
        "github_id": 333,
        "full_name": "owner/commitcountrepo",
        "language": "python",
        "stars": 1,
        "forks": 0,
        "description": "",
        "topics": "[]",
        "created_at": "2019-01-01",
        "pushed_at": "",
        "clone_url": "https://github.com/owner/commitcountrepo.git",
        "num_contributors": 0,
        "domain": None,
        "repo_age_years": None,
        "total_commits_since_agent_start": 42,
    }

    with db_session(db_path) as conn:
        repo_id, _ = upsert_repository(conn, repo)
        row = conn.execute(
            "SELECT total_commits_since_agent_start FROM repositories WHERE id = ?",
            (repo_id,),
        ).fetchone()
        assert row["total_commits_since_agent_start"] == 42

        # Re-upsert with an updated value (e.g. a backfill run)
        upsert_repository(conn, {**repo, "total_commits_since_agent_start": 51})
        row = conn.execute(
            "SELECT total_commits_since_agent_start FROM repositories WHERE id = ?",
            (repo_id,),
        ).fetchone()
        assert row["total_commits_since_agent_start"] == 51


def test_upsert_repository_backward_compatible_without_total_commits_since_agent_start(
    tmp_path,
):
    """Callers that don't set total_commits_since_agent_start (Dataset B/C's
    repo dicts, which never compute it) must not crash -- the column stays
    NULL, matching repo_age_at_collection_years's backward-compat
    treatment above."""
    db_path = tmp_path / "test.db"
    initialise_db(db_path)

    repo = {
        "github_id": 444,
        "full_name": "owner/nocommitcount",
        "language": "python",
        "stars": 1,
        "forks": 0,
        "description": "",
        "topics": "[]",
        "created_at": "2019-01-01",
        "pushed_at": "",
        "clone_url": "https://github.com/owner/nocommitcount.git",
        "num_contributors": 0,
        "domain": None,
        "repo_age_years": None,
        # total_commits_since_agent_start intentionally omitted
    }

    with db_session(db_path) as conn:
        repo_id, is_new = upsert_repository(conn, repo)
        assert is_new is True
        row = conn.execute(
            "SELECT total_commits_since_agent_start FROM repositories WHERE id = ?",
            (repo_id,),
        ).fetchone()
        assert row["total_commits_since_agent_start"] is None


def test_initialise_db_self_heals_a_schema_predating_column_migrations(tmp_path):
    """Regression test for a real incident: db/a.db's last collection run
    predated schema additions (repo_age_at_collection_years,
    total_commits_since_agent_start, commit_date, repo_age_at_commit_years)
    and CREATE TABLE IF NOT EXISTS is a no-op on an already-existing table,
    so those columns were silently missing -- the next
    upsert_repository()/insert_fixture() call (or, for
    total_commits_since_agent_start specifically,
    backfill_total_commits.py's own query) against that file would have
    crashed with "no such column". Simulates that exact stale state (a DB
    built from an old schema without these columns, with a real row already
    in it) and confirms a later initialise_db() call -- exactly what every
    collector, and now backfill_total_commits.py's run(), already does at
    the start -- adds the missing columns without touching existing data."""
    import sqlite3

    db_path = tmp_path / "stale.db"
    old_schema_conn = sqlite3.connect(db_path)
    old_schema_conn.executescript(
        """
        CREATE TABLE repositories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            github_id INTEGER UNIQUE NOT NULL,
            full_name TEXT NOT NULL,
            language TEXT NOT NULL,
            repo_age_years REAL DEFAULT NULL
        );
        CREATE TABLE fixtures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER NOT NULL,
            repo_id INTEGER NOT NULL,
            name TEXT,
            fixture_type TEXT,
            scope TEXT,
            start_line INTEGER,
            end_line INTEGER,
            loc INTEGER,
            cyclomatic_complexity INTEGER,
            max_nesting_depth INTEGER DEFAULT 0,
            num_objects_instantiated INTEGER DEFAULT 0,
            num_external_calls INTEGER DEFAULT 0,
            num_parameters INTEGER DEFAULT 0,
            has_teardown_pair INTEGER DEFAULT 0,
            raw_source TEXT,
            framework TEXT,
            num_mocks INTEGER DEFAULT 0,
            commit_sha TEXT DEFAULT NULL,
            agent_type TEXT DEFAULT NULL,
            commit_kind TEXT DEFAULT NULL,
            match_scope TEXT DEFAULT NULL,
            is_complete_addition INTEGER DEFAULT NULL,
            commit_type TEXT DEFAULT NULL,
            UNIQUE(file_id, name, start_line, commit_sha)
        );
        """
    )
    old_schema_conn.execute(
        "INSERT INTO repositories (github_id, full_name, language) "
        "VALUES (1, 'owner/prehistoric', 'python')"
    )
    old_schema_conn.commit()
    old_schema_conn.close()

    initialise_db(db_path)

    with db_session(db_path) as conn:
        repo_cols = {row[1] for row in conn.execute("PRAGMA table_info(repositories)")}
        fixture_cols = {row[1] for row in conn.execute("PRAGMA table_info(fixtures)")}
        assert "repo_age_at_collection_years" in repo_cols
        assert "agent_adoption_intensity" in repo_cols
        assert "total_commits_since_agent_start" in repo_cols
        assert {"commit_date", "repo_age_at_commit_years"} <= fixture_cols

        # Pre-existing row survives the migration untouched.
        row = conn.execute(
            "SELECT full_name, repo_age_at_collection_years FROM repositories "
            "WHERE github_id = 1"
        ).fetchone()
        assert row["full_name"] == "owner/prehistoric"
        assert row["repo_age_at_collection_years"] is None

    # Calling it again (e.g. a second collection run) must not error just
    # because the columns are already there.
    initialise_db(db_path)


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
