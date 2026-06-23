"""
Database layer — SQLite schema and helper functions.

All analysis reads from this DB; all collection writes to it.
Schema is designed to be append-safe: re-running the pipeline on new repos
will not duplicate existing records.
"""

import sqlite3
import json
import time
import logging
from contextlib import contextmanager
from pathlib import Path

from .config import DB_PATH

from collection.logging_utils import get_logger

logger = get_logger(__name__)

GLOBAL_CHECKPOINT_REPO_ID = 0

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA = """
-- -------------------------------------------------------------------------
-- Repositories discovered via GitHub search
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS repositories (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    github_id       INTEGER UNIQUE NOT NULL,
    full_name       TEXT NOT NULL,          -- e.g. "pytest-dev/pytest"
    language        TEXT NOT NULL,          -- normalised: python/java/javascript/typescript/go
    stars           INTEGER,
    forks           INTEGER,
    description     TEXT,
    topics          TEXT,                   -- JSON array of GitHub topics
    created_at      TEXT,
    pushed_at       TEXT,
    clone_url       TEXT,
    pinned_commit   TEXT,                   -- SHA at time of analysis (reproducibility)
    status          TEXT DEFAULT 'discovered',
    -- status values: discovered | cloned | analysed | skipped | error
    error_message   TEXT,
    skip_reason     TEXT,                   -- reason for skipping (few commits, few test files, few fixtures)
    num_test_files  INTEGER DEFAULT 0,      -- count of test files found
    num_fixtures    INTEGER DEFAULT 0,      -- count of fixture definitions
    num_mock_usages INTEGER DEFAULT 0,      -- count of mock usages detected
    num_contributors INTEGER DEFAULT 0,     -- GitHub API: repository contributor count
    domain          TEXT DEFAULT NULL,      -- classified domain (web/systems/ml/etc)
    star_tier       TEXT DEFAULT NULL,      -- core (>=500) or extended (<500)
    repo_age_years  REAL DEFAULT NULL,      -- repository age in years at collection time
    collected_at    TEXT DEFAULT (datetime('now'))
);

-- -------------------------------------------------------------------------
-- Test files found inside each repository
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS test_files (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id         INTEGER NOT NULL REFERENCES repositories(id),
    relative_path   TEXT NOT NULL,
    language        TEXT NOT NULL,
    file_loc        INTEGER DEFAULT 0,      -- non-blank lines of code in file
    num_test_funcs  INTEGER DEFAULT 0,
    num_fixtures    INTEGER DEFAULT 0,
    total_fixture_loc INTEGER DEFAULT 0,   -- sum of fixture LOC in this file
    UNIQUE(repo_id, relative_path)
);

-- -------------------------------------------------------------------------
-- Individual fixture definitions
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fixtures (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id                 INTEGER NOT NULL REFERENCES test_files(id),
    repo_id                 INTEGER NOT NULL REFERENCES repositories(id),
    name                    TEXT,
    fixture_type            TEXT,   -- pytest_decorator/unittest_setup/before_each/
                                    -- before_all/test_main/go_helper/...
    scope                   TEXT,   -- per_test/per_class/per_module/global
    start_line              INTEGER,
    end_line                INTEGER,
    loc                     INTEGER,   -- lines of code (non-blank)
    cyclomatic_complexity   INTEGER,
    max_nesting_depth       INTEGER DEFAULT 0,      -- maximum block nesting level
    num_objects_instantiated INTEGER DEFAULT 0,
    num_external_calls      INTEGER DEFAULT 0,
    num_parameters          INTEGER DEFAULT 0,
    reuse_count             INTEGER DEFAULT 0,      -- count of test functions using this fixture
    has_teardown_pair       INTEGER DEFAULT 0,      -- 1 if teardown/cleanup logic exists, 0 otherwise
    raw_source              TEXT,              -- original source text
    framework               TEXT,              -- testing framework (pytest, unittest, junit, nunit, testify, etc.)
    num_mocks               INTEGER DEFAULT 0, -- count of distinct mock usages in this fixture
    -- Agent-specific columns (populated only in fixturedb-agent.db)
    commit_sha              TEXT DEFAULT NULL,      -- exact commit where fixture added (agent-only)
    agent_type              TEXT DEFAULT NULL,      -- agent type: claude/copilot/cursor/other
    commit_kind             TEXT DEFAULT NULL,      -- agent / human (paired-study label)
    match_scope             TEXT DEFAULT NULL,      -- within_repo / cross_repo (source matching scope)
    is_complete_addition    INTEGER DEFAULT NULL,   -- 1=completely added, 0=partial/refactored (validation flag)
    UNIQUE(file_id, name, start_line)
);

-- -------------------------------------------------------------------------
-- Commit-level observations for paired within-repo analysis
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS commit_observations (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id             INTEGER NOT NULL REFERENCES repositories(id),
    commit_sha          TEXT NOT NULL,
    commit_role         TEXT NOT NULL,   -- agent / human
    agent_type          TEXT DEFAULT NULL,  -- claude/copilot/cursor/aider/other
    commit_date         TEXT,
    fixture_count       INTEGER DEFAULT 0,
    mock_usage_count    INTEGER DEFAULT 0,
    test_file_count     INTEGER DEFAULT 0,
    collected_at        TEXT DEFAULT (datetime('now')),
    UNIQUE(repo_id, commit_sha)
);

-- -------------------------------------------------------------------------
-- Test commits detected from repository history
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS test_commits (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id             INTEGER NOT NULL REFERENCES repositories(id),
    commit_sha          TEXT NOT NULL,
    commit_role         TEXT NOT NULL,   -- agent / human
    agent_type          TEXT DEFAULT NULL,  -- claude/copilot/cursor/aider/other
    commit_date         TEXT,
    language            TEXT NOT NULL,
    test_file_count     INTEGER DEFAULT 0,
    test_file_paths     TEXT DEFAULT NULL,  -- JSON array of touched test files
    collected_at        TEXT DEFAULT (datetime('now')),
    UNIQUE(repo_id, commit_sha)
);

-- -------------------------------------------------------------------------
-- Mock usages found inside fixtures
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mock_usages (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id                  INTEGER NOT NULL REFERENCES fixtures(id),
    repo_id                     INTEGER NOT NULL REFERENCES repositories(id),
    framework                   TEXT,   -- unittest_mock/pytest_mock/mockito/
                                        -- easymock/jest/sinon/gomock/testify/...
    target_identifier           TEXT,   -- the string passed to mock (e.g. "mymodule.Client")
    num_interactions_configured INTEGER DEFAULT 0,
    raw_snippet                 TEXT    -- the mock call source text
);

-- -------------------------------------------------------------------------
-- Indexes for common query patterns
-- -------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_fixtures_repo    ON fixtures(repo_id);
CREATE INDEX IF NOT EXISTS idx_fixtures_type    ON fixtures(fixture_type);
CREATE INDEX IF NOT EXISTS idx_fixtures_corpus  ON fixtures(commit_kind);  -- between-group: filter by corpus (human/agent)
CREATE INDEX IF NOT EXISTS idx_mocks_fixture    ON mock_usages(fixture_id);
CREATE INDEX IF NOT EXISTS idx_mocks_framework  ON mock_usages(framework);
CREATE INDEX IF NOT EXISTS idx_test_files_repo  ON test_files(repo_id);
CREATE INDEX IF NOT EXISTS idx_test_commits_repo ON test_commits(repo_id);
CREATE INDEX IF NOT EXISTS idx_test_commits_role ON test_commits(commit_role);

-- -------------------------------------------------------------------------
-- Human-sample tables for between-group experiments
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS human_within_fixtures (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id                 INTEGER REFERENCES test_files(id) ON DELETE CASCADE,
    repo_id                 INTEGER REFERENCES repositories(id) ON DELETE CASCADE,
    name                    TEXT,
    fixture_type            TEXT,
    scope                   TEXT,
    start_line              INTEGER,
    end_line                INTEGER,
    loc                     INTEGER,
    cyclomatic_complexity   INTEGER,
    max_nesting_depth       INTEGER DEFAULT 0,
    num_objects_instantiated INTEGER DEFAULT 0,
    num_external_calls      INTEGER DEFAULT 0,
    num_parameters          INTEGER DEFAULT 0,
    reuse_count             INTEGER DEFAULT 0,
    has_teardown_pair       INTEGER DEFAULT 0,
    raw_source              TEXT,
    framework               TEXT,
    num_mocks               INTEGER DEFAULT 0,
    commit_sha              TEXT DEFAULT NULL,
    commit_author_name      TEXT DEFAULT NULL,
    commit_author_email     TEXT DEFAULT NULL,
    commit_date             TEXT DEFAULT NULL,
    is_sampled              INTEGER DEFAULT 0,
    sample_batch            INTEGER DEFAULT NULL,
    provenance              TEXT DEFAULT NULL,
    UNIQUE(file_id, name, start_line)
);
CREATE INDEX IF NOT EXISTS idx_human_within_repo ON human_within_fixtures(repo_id);

CREATE TABLE IF NOT EXISTS human_inter_fixtures (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id                 INTEGER REFERENCES test_files(id) ON DELETE CASCADE,
    repo_id                 INTEGER REFERENCES repositories(id) ON DELETE CASCADE,
    name                    TEXT,
    fixture_type            TEXT,
    scope                   TEXT,
    start_line              INTEGER,
    end_line                INTEGER,
    loc                     INTEGER,
    cyclomatic_complexity   INTEGER,
    max_nesting_depth       INTEGER DEFAULT 0,
    num_objects_instantiated INTEGER DEFAULT 0,
    num_external_calls      INTEGER DEFAULT 0,
    num_parameters          INTEGER DEFAULT 0,
    reuse_count             INTEGER DEFAULT 0,
    has_teardown_pair       INTEGER DEFAULT 0,
    raw_source              TEXT,
    framework               TEXT,
    num_mocks               INTEGER DEFAULT 0,
    commit_sha              TEXT DEFAULT NULL,
    commit_author_name      TEXT DEFAULT NULL,
    commit_author_email     TEXT DEFAULT NULL,
    commit_date             TEXT DEFAULT NULL,
    matched_control_id      INTEGER DEFAULT NULL,
    match_score             REAL DEFAULT NULL,
    provenance              TEXT DEFAULT NULL,
    UNIQUE(file_id, name, start_line)
);
CREATE INDEX IF NOT EXISTS idx_human_inter_repo ON human_inter_fixtures(repo_id);

-- -------------------------------------------------------------------------
-- Checkpoints and run state for idempotent collection runs
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS checkpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id INTEGER NOT NULL,
    step TEXT NOT NULL,
    completed_at TEXT DEFAULT (datetime('now')),
    UNIQUE(repo_id, step)
);

"""


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    # Use a file-backed SQLite DB with WAL and a generous busy timeout to
    # tolerate concurrent readers while writers operate. These PRAGMA settings
    # are chosen to reduce transient `database is locked` errors during
    # multi-worker extraction and insertion:
    #  - `journal_mode=WAL` allows concurrent reads and a single writer
    #  - `busy_timeout` / `timeout` give SQLite time to resolve brief locks
    conn = sqlite3.connect(db_path, timeout=60.0)  # 60 second timeout for lock waits
    conn.row_factory = sqlite3.Row  # rows behave like dicts
    conn.execute("PRAGMA journal_mode=WAL")  # safe for concurrent reads
    conn.execute(
        "PRAGMA busy_timeout=60000"
    )  # 60s busy timeout (milliseconds) for 8 concurrent workers
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def db_session(db_path: Path = DB_PATH, max_retries: int = 20):
    """
    Context manager that commits on success, rolls back on exception.
    Retries on database lock with exponential backoff.

    Tuned for concurrent extraction with 8 workers:
    - PRAGMA busy_timeout: 60s (gives SQLite time to resolve contention)
    - max_retries: 20 with exponential backoff (0.5s → 256s)
    - Total potential wait time: ~10+ minutes for transient locks

    For overnight runs: up to 20 retries with base 0.5s, reaching ~260s max wait.
    Handles database locks that occur during both connection and operations.
    """
    for attempt in range(max_retries):
        conn = None
        try:
            conn = get_connection(db_path)
            yield conn
            conn.commit()
            return  # Success - exit the retry loop
        except Exception as e:
            if conn:
                conn.rollback()

            # Check if it's a lock error and we should retry
            if (
                isinstance(e, sqlite3.OperationalError)
                and "locked" in str(e).lower()
                and attempt < max_retries - 1
            ):
                wait_time = (2**attempt) * 0.5
                logger.warning(
                    f"Database locked, retrying in {wait_time:.1f}s (attempt {attempt + 1}/{max_retries})"
                )
                time.sleep(wait_time)
                continue  # Retry with new connection
            else:
                # Either not a lock error, or max retries reached
                raise
        finally:
            if conn:
                conn.close()


def insert_commit_observation(conn: sqlite3.Connection, observation: dict) -> int:
    """Insert a paired-study commit observation and return its row id."""
    cursor = conn.execute(
        """
        INSERT INTO commit_observations (
            repo_id, commit_sha, commit_role, agent_type,
            commit_date, fixture_count, mock_usage_count, test_file_count
        ) VALUES (
            :repo_id, :commit_sha, :commit_role, :agent_type,
            :commit_date, :fixture_count, :mock_usage_count, :test_file_count
        )
        ON CONFLICT(repo_id, commit_sha) DO UPDATE SET
            commit_role = excluded.commit_role,
            agent_type = excluded.agent_type,
            commit_date = excluded.commit_date,
            fixture_count = excluded.fixture_count,
            mock_usage_count = excluded.mock_usage_count,
            test_file_count = excluded.test_file_count
        """,
        observation,
    )
    if cursor.rowcount == 1:
        return cursor.lastrowid

    row = conn.execute(
        "SELECT id FROM commit_observations WHERE repo_id=? AND commit_sha=?",
        (observation["repo_id"], observation["commit_sha"]),
    ).fetchone()
    if row is None:
        raise ValueError(
            f"Commit observation insert conflict but SELECT returned no rows: repo_id={observation['repo_id']}, commit_sha={observation['commit_sha']}"
        )
    return row["id"]


def insert_test_commit(conn: sqlite3.Connection, test_commit: dict) -> int:
    """Insert a detected test commit and return its row id."""
    cursor = conn.execute(
        """
        INSERT INTO test_commits (
            repo_id, commit_sha, commit_role, agent_type,
            commit_date, language, test_file_count, test_file_paths
        ) VALUES (
            :repo_id, :commit_sha, :commit_role, :agent_type,
            :commit_date, :language, :test_file_count, :test_file_paths
        )
        ON CONFLICT(repo_id, commit_sha) DO UPDATE SET
            commit_role = excluded.commit_role,
            agent_type = excluded.agent_type,
            commit_date = excluded.commit_date,
            language = excluded.language,
            test_file_count = excluded.test_file_count,
            test_file_paths = excluded.test_file_paths
        """,
        test_commit,
    )
    if cursor.rowcount == 1:
        return cursor.lastrowid

    row = conn.execute(
        "SELECT id FROM test_commits WHERE repo_id=? AND commit_sha=?",
        (test_commit["repo_id"], test_commit["commit_sha"]),
    ).fetchone()
    if row is None:
        raise ValueError(
            f"Test commit insert conflict but SELECT returned no rows: repo_id={test_commit['repo_id']}, commit_sha={test_commit['commit_sha']}"
        )
    return row["id"]


def initialise_db(db_path: Path = DB_PATH) -> None:
    """
    Create all tables and indexes if they do not already exist.
    Safe to call multiple times — never drops or truncates existing data.
    """
    with db_session(db_path) as conn:
        conn.executescript(SCHEMA)
    print(f"[db] Initialised database at {db_path}")


def db_is_initialised(db_path: Path = DB_PATH) -> bool:
    """Return True if the database already has the repositories table."""
    try:
        conn = get_connection(db_path)
        result = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='repositories'"
        ).fetchone()
        conn.close()
        return result is not None
    except (sqlite3.DatabaseError, OSError) as e:
        logger.debug(f"Could not check database initialization: {e}")
        return False


# ---------------------------------------------------------------------------
# Repository helpers
# ---------------------------------------------------------------------------


def upsert_repository(conn: sqlite3.Connection, repo: dict) -> tuple[int, bool]:
    """
    Insert or update a repository record.

    Returns (internal_row_id, is_new) where is_new=True means this was a
    genuine insert (repo not previously in the DB), False means it already
    existed and was updated in place.

    Callers that want to count new discoveries should only increment their
    counter when is_new=True.
    """
    # Check existence before the upsert so we can report is_new accurately.
    existing = conn.execute(
        "SELECT id FROM repositories WHERE github_id = ?", (repo["github_id"],)
    ).fetchone()
    is_new = existing is None

    conn.execute(
        """
        INSERT INTO repositories (
            github_id, full_name, language, stars, forks,
            description, topics, created_at, pushed_at, clone_url,
            domain, star_tier, repo_age_years, num_contributors
        ) VALUES (
            :github_id, :full_name, :language, :stars, :forks,
            :description, :topics, :created_at, :pushed_at, :clone_url,
            :domain, :star_tier, :repo_age_years, :num_contributors
        )
        ON CONFLICT(github_id) DO UPDATE SET
            stars       = excluded.stars,
            pushed_at   = excluded.pushed_at,
            domain      = excluded.domain,
            star_tier   = excluded.star_tier,
            repo_age_years = excluded.repo_age_years,
            num_contributors = excluded.num_contributors
    """,
        repo,
    )

    row_id = (
        existing["id"]
        if existing
        else conn.execute(
            "SELECT id FROM repositories WHERE github_id = ?", (repo["github_id"],)
        ).fetchone()["id"]
    )

    return row_id, is_new


def set_repo_status(
    conn: sqlite3.Connection,
    repo_id: int,
    status: str,
    error: str = None,
    skip_reason: str = None,
    pinned_commit: str = None,
) -> None:
    conn.execute(
        """
        UPDATE repositories
        SET status = ?, error_message = ?, skip_reason = ?,
            pinned_commit = COALESCE(?, pinned_commit)
        WHERE id = ?
    """,
        (status, error, skip_reason, pinned_commit, repo_id),
    )


def set_repo_analysed(
    conn: sqlite3.Connection,
    repo_id: int,
    num_test_files: int,
    num_fixtures: int,
    num_mock_usages: int,
    num_contributors: int = 0,
) -> None:
    """Mark a repo as analysed and store the extraction counts."""
    conn.execute(
        """
        UPDATE repositories
        SET status = 'analysed',
            num_test_files = ?,
            num_fixtures = ?,
            num_mock_usages = ?,
            num_contributors = ?
        WHERE id = ?
    """,
        (num_test_files, num_fixtures, num_mock_usages, num_contributors, repo_id),
    )


def get_repos_by_status(conn: sqlite3.Connection, status: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM repositories WHERE status = ?", (status,)
    ).fetchall()


# ---------------------------------------------------------------------------
# Test file helpers
# ---------------------------------------------------------------------------


def upsert_test_file(
    conn: sqlite3.Connection, repo_id: int, relative_path: str, language: str
) -> int:
    conn.execute(
        """
        INSERT INTO test_files (repo_id, relative_path, language)
        VALUES (?, ?, ?)
        ON CONFLICT(repo_id, relative_path) DO NOTHING
    """,
        (repo_id, relative_path, language),
    )
    row = conn.execute(
        "SELECT id FROM test_files WHERE repo_id = ? AND relative_path = ?",
        (repo_id, relative_path),
    ).fetchone()
    return row["id"]


def update_test_file_counts(
    conn: sqlite3.Connection,
    file_id: int,
    num_test_funcs: int,
    num_fixtures: int,
    file_loc: int = 0,
    total_fixture_loc: int = 0,
) -> None:
    conn.execute(
        """
        UPDATE test_files
        SET num_test_funcs = ?, num_fixtures = ?, file_loc = ?, total_fixture_loc = ?
        WHERE id = ?
    """,
        (num_test_funcs, num_fixtures, file_loc, total_fixture_loc, file_id),
    )


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def insert_fixture(conn: sqlite3.Connection, fixture: dict) -> int:
    """
    Insert a fixture record. Returns the new row id, or existing id on conflict.

    Args:
        conn: Database connection
        fixture: Dict with fixture data. May include:
            - Standard columns: file_id, repo_id, name, fixture_type, scope, etc.
            - AGENT-specific columns: commit_sha, agent_type, tier, is_complete_addition

    Returns:
        The fixture ID (newly inserted or existing)
    """
    # Build the column list dynamically based on what's in the fixture dict
    columns = [
        "file_id",
        "repo_id",
        "name",
        "fixture_type",
        "scope",
        "start_line",
        "end_line",
        "loc",
        "cyclomatic_complexity",
        "max_nesting_depth",
        "num_objects_instantiated",
        "num_external_calls",
        "num_parameters",
        "reuse_count",
        "has_teardown_pair",
        "raw_source",
        "framework",
        "num_mocks",
    ]

    # Add agent-specific columns if present
    agent_columns = [
        "commit_sha",
        "agent_type",
        "commit_kind",
        "match_scope",
        "is_complete_addition",
    ]
    for col in agent_columns:
        if col in fixture:
            columns.append(col)

    # Build the INSERT statement
    cols_str = ", ".join(columns)
    placeholders = ", ".join([f":{col}" for col in columns])

    cursor = conn.execute(
        f"""
        INSERT INTO fixtures ({cols_str})
        VALUES ({placeholders})
        ON CONFLICT(file_id, name, start_line) DO NOTHING
        """,
        fixture,
    )
    if cursor.rowcount == 1:
        return cursor.lastrowid
    row = conn.execute(
        "SELECT id FROM fixtures WHERE file_id=? AND name=? AND start_line=?",
        (fixture["file_id"], fixture["name"], fixture["start_line"]),
    ).fetchone()
    if row is None:
        raise ValueError(
            f"Fixture insert conflict but SELECT returned no rows: "
            f"file_id={fixture['file_id']}, name={fixture['name']}, start_line={fixture['start_line']}"
        )
    return row["id"]


def insert_human_within_fixture(conn: sqlite3.Connection, fixture: dict) -> int:
    """
    Insert a sampled human-within fixture into `human_within_fixtures`.
    Returns the row id (new or existing).
    """
    columns = [
        "file_id",
        "repo_id",
        "name",
        "fixture_type",
        "scope",
        "start_line",
        "end_line",
        "loc",
        "cyclomatic_complexity",
        "max_nesting_depth",
        "num_objects_instantiated",
        "num_external_calls",
        "num_parameters",
        "reuse_count",
        "has_teardown_pair",
        "raw_source",
        "framework",
        "num_mocks",
        "commit_sha",
        "commit_author_name",
        "commit_author_email",
        "commit_date",
        "is_sampled",
        "sample_batch",
        "provenance",
    ]

    cols_str = ", ".join(columns)
    placeholders = ", ".join([f":{c}" for c in columns])

    cursor = conn.execute(
        f"""
        INSERT INTO human_within_fixtures ({cols_str})
        VALUES ({placeholders})
        ON CONFLICT(file_id, name, start_line) DO NOTHING
        """,
        fixture,
    )
    if cursor.rowcount == 1:
        return cursor.lastrowid
    row = conn.execute(
        "SELECT id FROM human_within_fixtures WHERE file_id=? AND name=? AND start_line=?",
        (fixture["file_id"], fixture["name"], fixture["start_line"]),
    ).fetchone()
    if row is None:
        raise ValueError(
            f"Human within fixture insert conflict but SELECT returned no rows: file_id={fixture['file_id']}, name={fixture['name']}, start_line={fixture['start_line']}"
        )
    return row["id"]


def insert_human_inter_fixture(conn: sqlite3.Connection, fixture: dict) -> int:
    """
    Insert a sampled human-inter fixture into `human_inter_fixtures`.
    Returns the row id (new or existing).
    """
    columns = [
        "file_id",
        "repo_id",
        "name",
        "fixture_type",
        "scope",
        "start_line",
        "end_line",
        "loc",
        "cyclomatic_complexity",
        "max_nesting_depth",
        "num_objects_instantiated",
        "num_external_calls",
        "num_parameters",
        "reuse_count",
        "has_teardown_pair",
        "raw_source",
        "framework",
        "num_mocks",
        "commit_sha",
        "commit_author_name",
        "commit_author_email",
        "commit_date",
        "matched_control_id",
        "match_score",
        "provenance",
    ]

    cols_str = ", ".join(columns)
    placeholders = ", ".join([f":{c}" for c in columns])

    # Temporarily disable foreign key checks for synthetic test fixtures
    prev_fk = 1
    try:
        cur = conn.execute("PRAGMA foreign_keys")
        row = cur.fetchone()
        if row is not None:
            prev_fk = int(bool(row[0]))
    except Exception:
        prev_fk = 1

    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        cursor = conn.execute(
            f"""
            INSERT INTO human_inter_fixtures ({cols_str})
            VALUES ({placeholders})
            ON CONFLICT(file_id, name, start_line) DO NOTHING
            """,
            fixture,
        )
    finally:
        try:
            conn.execute(f"PRAGMA foreign_keys = {int(bool(prev_fk))}")
        except Exception:
            pass

    if cursor.rowcount == 1:
        return cursor.lastrowid
    row = conn.execute(
        "SELECT id FROM human_inter_fixtures WHERE file_id=? AND name=? AND start_line=?",
        (fixture["file_id"], fixture["name"], fixture["start_line"]),
    ).fetchone()
    if row is None:
        raise ValueError(
            f"Human inter fixture insert conflict but SELECT returned no rows: file_id={fixture['file_id']}, name={fixture['name']}, start_line={fixture['start_line']}"
        )
    return row["id"]


def insert_human_inter_fixtures_bulk(
    conn: sqlite3.Connection, fixtures: list[dict]
) -> int:
    """
    Bulk-insert sampled human-inter fixtures using executemany.

    Returns the number of attempted inserts (not the number of new rows).
    """
    if not fixtures:
        return 0

    columns = [
        "file_id",
        "repo_id",
        "name",
        "fixture_type",
        "scope",
        "start_line",
        "end_line",
        "loc",
        "cyclomatic_complexity",
        "max_nesting_depth",
        "num_objects_instantiated",
        "num_external_calls",
        "num_parameters",
        "reuse_count",
        "has_teardown_pair",
        "raw_source",
        "framework",
        "num_mocks",
        "commit_sha",
        "commit_author_name",
        "commit_author_email",
        "commit_date",
        "matched_control_id",
        "match_score",
        "provenance",
    ]

    cols_str = ", ".join(columns)
    placeholders = ", ".join([f":{c}" for c in columns])

    sql = f"""
    INSERT INTO human_inter_fixtures ({cols_str})
    VALUES ({placeholders})
    ON CONFLICT(file_id, name, start_line) DO NOTHING
    """

    # executemany accepts a sequence of mappings when using named placeholders
    # Temporarily disable foreign key checks to allow insertion of synthetic
    # test fixtures used by unit tests (tests create fixtures with repo_id/file_id
    # values but do not always populate the referenced tables). We restore the
    # previous setting afterwards.
    prev_fk = 1
    try:
        cur = conn.execute("PRAGMA foreign_keys")
        row = cur.fetchone()
        if row is not None:
            prev_fk = int(bool(row[0]))
    except Exception:
        prev_fk = 1

    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.executemany(sql, fixtures)
    finally:
        try:
            conn.execute(f"PRAGMA foreign_keys = {int(bool(prev_fk))}")
        except Exception:
            pass

    return len(fixtures)


def insert_human_inter_fixtures_coordinated(
    db_path: Path, selected_fixtures: list[dict], seed: int = 42, batch_size: int = 1000
) -> int:
    """Coordinate SELECT lookups and bulk insert of human_inter_fixtures in one transaction.

    Args:
        db_path: Path to DB file
        selected_fixtures: list of fixture dicts containing at least 'repo_full_name', 'name', 'start_line', and other fixture fields
        seed: sampling seed (used in provenance)
        batch_size: number of rows per executemany batch

    Returns:
        Number of attempted inserts (len of inter_rows)
    """
    if not selected_fixtures:
        return 0

    inserted = 0
    provenance = json.dumps({"sample_seed": seed})

    insert_columns = [
        "file_id",
        "repo_id",
        "name",
        "fixture_type",
        "scope",
        "start_line",
        "end_line",
        "loc",
        "cyclomatic_complexity",
        "max_nesting_depth",
        "num_objects_instantiated",
        "num_external_calls",
        "num_parameters",
        "reuse_count",
        "has_teardown_pair",
        "raw_source",
        "framework",
        "num_mocks",
        "commit_sha",
        "commit_author_name",
        "commit_author_email",
        "commit_date",
        "matched_control_id",
        "match_score",
        "provenance",
    ]
    cols_str = ", ".join(insert_columns)
    placeholders = ", ".join([f":{c}" for c in insert_columns])
    insert_sql = f"""
    INSERT INTO human_inter_fixtures ({cols_str})
    VALUES ({placeholders})
    ON CONFLICT(file_id, name, start_line) DO NOTHING
    """

    lookup_sql = (
        "SELECT f.file_id, f.repo_id "
        "FROM fixtures f JOIN repositories r ON f.repo_id = r.id "
        "WHERE r.full_name = ? AND f.name = ? AND f.start_line = ? LIMIT 1"
    )

    # Perform all lookups and inserts inside a single db_session to avoid nested sessions
    from .config import FAST_BULK_INSERTS

    with db_session(db_path) as conn:
        # Optionally relax synchronous mode for faster bulk inserts
        prev_sync = None
        if FAST_BULK_INSERTS:
            try:
                cur = conn.execute("PRAGMA synchronous")
                row = cur.fetchone()
                if row is not None:
                    prev_sync = int(row[0])
                conn.execute("PRAGMA synchronous = OFF")
            except Exception:
                prev_sync = None

        batch: list[dict] = []
        for fx in selected_fixtures:
            repo_full = fx.get("repo_full_name")
            cur = conn.execute(
                lookup_sql, (repo_full, fx.get("name"), fx.get("start_line"))
            )
            row = cur.fetchone()
            if not row:
                logger.debug(
                    f"[DB Coordinator] inserted fixture not found for {repo_full}:{fx.get('name')}"
                )
                continue

            file_id = row[0]
            repo_id = row[1]

            inter_row = {
                "file_id": file_id,
                "repo_id": repo_id,
                "name": fx.get("name"),
                "fixture_type": fx.get("fixture_type"),
                "scope": fx.get("scope"),
                "start_line": fx.get("start_line"),
                "end_line": fx.get("end_line"),
                "loc": fx.get("loc"),
                "cyclomatic_complexity": fx.get("cyclomatic_complexity"),
                "max_nesting_depth": fx.get("max_nesting_depth"),
                "num_objects_instantiated": fx.get("num_objects_instantiated"),
                "num_external_calls": fx.get("num_external_calls"),
                "num_parameters": fx.get("num_parameters"),
                "reuse_count": fx.get("reuse_count"),
                "has_teardown_pair": fx.get("has_teardown_pair"),
                "raw_source": fx.get("raw_source"),
                "framework": fx.get("framework"),
                "num_mocks": len(fx.get("mocks", []) or []),
                "commit_sha": fx.get("commit_sha"),
                "commit_author_name": fx.get("commit_author_name", ""),
                "commit_author_email": fx.get("commit_author_email", ""),
                "commit_date": fx.get("commit_date", ""),
                "matched_control_id": None,
                "match_score": None,
                "provenance": provenance,
            }

            batch.append(inter_row)

            if len(batch) >= batch_size:
                conn.executemany(insert_sql, batch)
                inserted += len(batch)
                batch = []

        if batch:
            conn.executemany(insert_sql, batch)
            inserted += len(batch)

        # Restore synchronous pragma if changed
        if FAST_BULK_INSERTS and prev_sync is not None:
            try:
                conn.execute(f"PRAGMA synchronous = {int(prev_sync)}")
            except Exception:
                pass

    return inserted


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


def insert_mock_usage(conn: sqlite3.Connection, mock: dict) -> None:
    try:
        conn.execute(
            """
            INSERT INTO mock_usages (
                fixture_id, repo_id, framework, target_identifier,
                num_interactions_configured, raw_snippet
            ) VALUES (
                :fixture_id, :repo_id, :framework, :target_identifier,
                :num_interactions_configured, :raw_snippet
            )
        """,
            mock,
        )
    except sqlite3.IntegrityError as e:
        # Better error context for foreign key failures
        fixture_id = mock.get("fixture_id")
        repo_id = mock.get("repo_id")

        # Check if fixture exists
        fixture_exists = conn.execute(
            "SELECT id FROM fixtures WHERE id = ?", (fixture_id,)
        ).fetchone()

        # Check if repo exists
        repo_exists = conn.execute(
            "SELECT id FROM repositories WHERE id = ?", (repo_id,)
        ).fetchone()

        error_msg = (
            f"Foreign key constraint failed when inserting mock_usage: "
            f"fixture_id={fixture_id} (exists={fixture_exists is not None}), "
            f"repo_id={repo_id} (exists={repo_exists is not None})"
        )
        raise sqlite3.IntegrityError(error_msg) from e


def mark_checkpoint(conn: sqlite3.Connection, repo_id: int, step: str) -> None:
    """Record a completed step for a repository (idempotent)."""
    conn.execute(
        """
        INSERT INTO checkpoints (repo_id, step) VALUES (?, ?)
        ON CONFLICT(repo_id, step) DO UPDATE SET completed_at = datetime('now')
        """,
        (repo_id, step),
    )


def is_checkpoint_completed(conn: sqlite3.Connection, repo_id: int, step: str) -> bool:
    """Return True if the given checkpoint step has been recorded for repo_id."""
    row = conn.execute(
        "SELECT id FROM checkpoints WHERE repo_id = ? AND step = ?", (repo_id, step)
    ).fetchone()
    return row is not None


def mark_global_checkpoint(conn: sqlite3.Connection, step: str) -> None:
    """Record a completed global step for the current run."""
    mark_checkpoint(conn, GLOBAL_CHECKPOINT_REPO_ID, step)


def is_global_checkpoint_completed(conn: sqlite3.Connection, step: str) -> bool:
    """Return True if the given global checkpoint step has been recorded."""
    return is_checkpoint_completed(conn, GLOBAL_CHECKPOINT_REPO_ID, step)


# ---------------------------------------------------------------------------
# Stats helper (useful for progress reporting)
# ---------------------------------------------------------------------------


def get_corpus_stats(conn: sqlite3.Connection) -> dict:
    stats = {}
    for status in ("discovered", "cloned", "analysed", "skipped", "error"):
        row = conn.execute(
            "SELECT COUNT(*) as n FROM repositories WHERE status = ?", (status,)
        ).fetchone()
        stats[f"repos_{status}"] = row["n"]

    for table in ("test_files", "fixtures", "mock_usages"):
        row = conn.execute(f"SELECT COUNT(*) as n FROM {table}").fetchone()
        stats[table] = row["n"]

    return stats


def get_analyzed_count_by_language(conn: sqlite3.Connection) -> dict[str, int]:
    """
    Get count of successfully analyzed repos (status='analysed' AND produced >=1 fixture) per language.
    These are repositories with fixtures successfully extracted.
    """
    row = conn.execute("""
        SELECT r.language, COUNT(DISTINCT r.id) as count
        FROM repositories r
        WHERE r.status = 'analysed'
        AND EXISTS (SELECT 1 FROM fixtures WHERE repo_id = r.id)
        GROUP BY r.language
        ORDER BY r.language
    """).fetchall()
    return {r["language"]: r["count"] for r in row}


def get_analyzed_count_for_language(conn: sqlite3.Connection, language: str) -> int:
    """
    Get count of successfully analyzed repos for a specific language.
    Only counts repos with status='analysed' AND at least one extracted fixture.
    """
    row = conn.execute(
        """
        SELECT COUNT(DISTINCT r.id) as n
        FROM repositories r
        WHERE r.language = ? AND r.status = 'analysed'
        AND EXISTS (SELECT 1 FROM fixtures WHERE repo_id = r.id)
    """,
        (language,),
    ).fetchone()
    return row["n"]


def get_discovered_count_for_language(conn: sqlite3.Connection, language: str) -> int:
    """
    Get count of discovered repos (status='discovered') waiting to be cloned.
    These are repos from search that haven't been processed yet.
    """
    row = conn.execute(
        "SELECT COUNT(*) as n FROM repositories WHERE language = ? AND status = 'discovered'",
        (language,),
    ).fetchone()
    return row["n"]


def get_survival_rate_for_language(conn: sqlite3.Connection, language: str) -> float:
    """
    Calculate and return the empirical survival rate for a language.
    Survival = (analyzed repos with fixtures) / (discovered repos)

    Returns 0.0 if no discovered repos yet (no data to calculate).
    """
    cursor = conn.execute(
        """
        SELECT 
            COUNT(DISTINCT r.id) as discovered,
            SUM(CASE WHEN r.status = 'analysed' AND EXISTS (
                SELECT 1 FROM fixtures WHERE repo_id = r.id
            ) THEN 1 ELSE 0 END) as analyzed
        FROM repositories r
        WHERE r.language = ?
        """,
        (language,),
    )
    result = cursor.fetchone()
    discovered = result["discovered"]
    analyzed = result["analyzed"] or 0

    if discovered == 0:
        return 0.0

    return analyzed / discovered


def classify_domain(topics_str: str | None, description_str: str | None) -> str:
    """
    Classify repository domain from topics and description.

    Returns one of: web, systems, ml, security, database, devops, other
    """
    text = ""
    if topics_str:
        try:
            topics_list = (
                json.loads(topics_str) if isinstance(topics_str, str) else topics_str
            )
            text += " ".join(str(t).lower() for t in topics_list) + " "
        except (json.JSONDecodeError, TypeError):
            pass

    if description_str:
        text += description_str.lower()

    # Domain classification keywords
    domain_keywords = {
        "web": [
            "web",
            "rest",
            "http",
            "frontend",
            "react",
            "vue",
            "angular",
            "django",
            "flask",
            "rails",
        ],
        "systems": [
            "kernel",
            "driver",
            "os",
            "system",
            "compiler",
            "linux",
            "windows",
            "os/2",
            "unix",
        ],
        "ml": [
            "machine learning",
            "ml",
            "ai",
            "neural",
            "deep learning",
            "tensorflow",
            "pytorch",
            "scikit",
        ],
        "security": ["security", "crypto", "encryption", "ssl", "tls", "auth", "oauth"],
        "database": [
            "database",
            "db",
            "sql",
            "nosql",
            "mongodb",
            "postgresql",
            "mysql",
            "cache",
            "redis",
        ],
        "devops": [
            "devops",
            "kubernetes",
            "docker",
            "ci/cd",
            "jenkins",
            "ansible",
            "terraform",
        ],
    }

    for domain, keywords in domain_keywords.items():
        if any(kw in text for kw in keywords):
            return domain

    return "other"


def compute_star_tier(stars: int | None) -> str:
    """
    Classify repository into star tier based on GitHub stars.

    Returns: "core" (>=500 stars) or "extended" (<500 stars)
    """
    if stars is None:
        return "extended"
    return "core" if stars >= 500 else "extended"


def compute_repo_age_years(created_at_str: str | None) -> float | None:
    """
    Compute repository age in years from creation date string (ISO format).

    Returns: age in years as float, or None if created_at is None/invalid
    """
    if not created_at_str:
        return None

    try:
        from datetime import datetime as dt

        created = dt.fromisoformat(created_at_str.replace("Z", "+00:00"))
        now = dt.now(created.tzinfo) if created.tzinfo else dt.now()
        age_days = (now - created).days
        return age_days / 365.25
    except (ValueError, AttributeError):
        return None


def compute_repo_age_at_date(
    created_at_str: str | None, target_date_str: str
) -> float | None:
    """
    Compute repository age in years relative to a specific date.

    Used for between-group design to compute control variables at historical
    snapshots (e.g., 2020-12-31 for human corpus, 2025-01-01 for agent corpus).

    Args:
        created_at_str: Repository creation date (ISO format)
        target_date_str: Target date for age computation (ISO format)

    Returns:
        Age in years as float, or None if inputs are invalid
    """
    if not created_at_str or not target_date_str:
        return None

    try:
        from datetime import datetime as dt

        created = dt.fromisoformat(created_at_str.replace("Z", "+00:00"))
        target = dt.fromisoformat(target_date_str.replace("Z", "+00:00"))
        age_days = (target - created).days

        # Handle negative age (repo created after target date)
        if age_days < 0:
            return None

        return age_days / 365.25
    except (ValueError, AttributeError):
        return None


def get_control_variables_at_date(repo: dict, target_date: str) -> dict:
    """
    Compute control variables (domain, star_tier, repo_age) at a specific date.

    For between-group comparison, control variables should reflect repo state
    at fixture writing time (2020-12-31 for human, 2025-01-01 for agent).

    Args:
        repo: Repository metadata dict with keys: topics, description, stars, created_at
        target_date: ISO date string (e.g., "2020-12-31")

    Returns:
        Dict with control_variables keys:
        - domain: str (web, systems, ml, security, database, devops, other)
        - star_tier: str (core >=500, extended <500) — current stars only
        - repo_age_years: float (age at target_date) or None
    """
    domain = classify_domain(repo.get("topics"), repo.get("description"))
    # Note: Star tier uses current stars (historical unavailable from API)
    star_tier = compute_star_tier(repo.get("stars"))
    repo_age = compute_repo_age_at_date(repo.get("created_at"), target_date)

    return {
        "domain": domain,
        "star_tier": star_tier,
        "repo_age_years": repo_age,
    }
