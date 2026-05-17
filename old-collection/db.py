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

from collection.config import DB_PATH

logger = logging.getLogger(__name__)

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
    domain          TEXT,                   -- web/cli/data/infra/library/other (filled later)
    status          TEXT DEFAULT 'discovered',
    -- status values: discovered | cloned | analysed | skipped | error
    error_message   TEXT,
    skip_reason     TEXT,                   -- reason for skipping (few commits, few test files, few fixtures)
    num_test_files  INTEGER DEFAULT 0,      -- count of test files found
    num_fixtures    INTEGER DEFAULT 0,      -- count of fixture definitions
    num_mock_usages INTEGER DEFAULT 0,      -- count of mock usages detected
    num_contributors INTEGER DEFAULT 0,     -- GitHub API: repository contributor count
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
    category                TEXT,              -- RQ1 taxonomy label (filled by classifier)
    framework               TEXT,              -- testing framework (pytest, unittest, junit, nunit, testify, etc.)
    num_mocks               INTEGER DEFAULT 0, -- count of distinct mock usages in this fixture
    UNIQUE(file_id, name, start_line)
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
CREATE INDEX IF NOT EXISTS idx_fixtures_category ON fixtures(category);
CREATE INDEX IF NOT EXISTS idx_mocks_fixture    ON mock_usages(fixture_id);
CREATE INDEX IF NOT EXISTS idx_mocks_framework  ON mock_usages(framework);
CREATE INDEX IF NOT EXISTS idx_test_files_repo  ON test_files(repo_id);
"""


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
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
    last_exception = None

    for attempt in range(max_retries):
        conn = None
        caught_exception = None
        try:
            conn = get_connection(db_path)
            try:
                yield conn
                conn.commit()
                return  # Success - exit the retry loop
            except Exception as e:
                caught_exception = e
                if conn:
                    conn.rollback()
                # Don't re-raise here - handle in outer scope
        finally:
            if conn:
                conn.close()

        # Handle exception outside the finally block to avoid generator issues
        if caught_exception is not None:
            if (
                isinstance(caught_exception, sqlite3.OperationalError)
                and "locked" in str(caught_exception).lower()
            ):
                if attempt < max_retries - 1:
                    # Database locked - retry with exponential backoff
                    last_exception = caught_exception
                    wait_time = (2**attempt) * 0.5
                    logger.warning(
                        f"Database locked, retrying in {wait_time:.1f}s (attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(wait_time)
                    continue  # Retry
                else:
                    # Max retries reached
                    logger.error(
                        f"Database lock not resolved after {max_retries} attempts: {caught_exception}"
                    )
                    raise caught_exception
            else:
                # Non-lock exceptions should be raised immediately (not retried)
                raise caught_exception

    # Should not reach here, but just in case
    if last_exception:
        raise last_exception


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
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='repositories'"
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
            description, topics, created_at, pushed_at, clone_url
        ) VALUES (
            :github_id, :full_name, :language, :stars, :forks,
            :description, :topics, :created_at, :pushed_at, :clone_url
        )
        ON CONFLICT(github_id) DO UPDATE SET
            stars       = excluded.stars,
            pushed_at   = excluded.pushed_at
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
    """Insert a fixture record. Returns the new row id, or existing id on conflict."""
    cursor = conn.execute(
        """
        INSERT INTO fixtures (
            file_id, repo_id, name, fixture_type, scope,
            start_line, end_line, loc, cyclomatic_complexity,
            max_nesting_depth, num_objects_instantiated, 
            num_external_calls, num_parameters, reuse_count, has_teardown_pair,
            raw_source, framework
        ) VALUES (
            :file_id, :repo_id, :name, :fixture_type, :scope,
            :start_line, :end_line, :loc, :cyclomatic_complexity,
            :max_nesting_depth, :num_objects_instantiated, 
            :num_external_calls, :num_parameters, :reuse_count, :has_teardown_pair,
            :raw_source, :framework
        )
        ON CONFLICT(file_id, name, start_line) DO NOTHING
    """,
        fixture,
    )
    if cursor.lastrowid:
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


def cleanup_to_toy_dataset(
    db_path: Path = DB_PATH, toy_count_per_language: int = 50
) -> dict:
    """
    Clean up database to keep only the toy dataset: 50 repos per language.

    Removes extracted fixtures and data for all repos beyond the first toy_count_per_language
    analyzed repos per language (ordered by creation date, then by ID for consistency).

    Returns a dict with:
      - 'repos_removed': count of repos cleaned
      - 'fixtures_removed': count of fixtures deleted
      - 'mocks_removed': count of mock_usages deleted
      - 'per_language': dict of cleanup counts per language
    """
    with db_session(db_path) as conn:
        summary = {
            "repos_removed": 0,
            "fixtures_removed": 0,
            "mocks_removed": 0,
            "per_language": {},
        }

        # Get all analyzed repos per language, ordered by creation date
        cursor = conn.execute("""
            SELECT r.id, r.language, r.full_name, r.created_at
            FROM repositories r
            WHERE r.status = 'analysed' AND EXISTS (
                SELECT 1 FROM fixtures WHERE repo_id = r.id
            )
            ORDER BY r.language, r.created_at ASC, r.id ASC
        """)
        all_analyzed = cursor.fetchall()

        # Group by language and keep track of which IDs to remove
        by_language = {}
        for row in all_analyzed:
            lang = row["language"]
            if lang not in by_language:
                by_language[lang] = []
            by_language[lang].append(row["id"])

        # Identify repos to delete (those beyond toy_count_per_language per language)
        repos_to_remove = []
        for lang, repo_ids in by_language.items():
            keep_count = min(toy_count_per_language, len(repo_ids))
            remove_ids = repo_ids[keep_count:]
            repos_to_remove.extend(remove_ids)

            if remove_ids:
                summary["per_language"][lang] = {
                    "kept": keep_count,
                    "removed": len(remove_ids),
                }
                logger.info(
                    f"{lang}: Keeping {keep_count}/{len(repo_ids)}, "
                    f"removing {len(remove_ids)}"
                )

        # Delete fixtures and mocks for repos to remove
        if repos_to_remove:
            # Delete mock_usages first (foreign key to fixtures)
            placeholders = ",".join("?" * len(repos_to_remove))
            cursor = conn.execute(
                f"SELECT COUNT(*) as n FROM mock_usages WHERE fixture_id IN "
                f"(SELECT id FROM fixtures WHERE repo_id IN ({placeholders}))",
                repos_to_remove,
            )
            mock_count = cursor.fetchone()["n"]
            summary["mocks_removed"] = mock_count

            conn.execute(
                f"DELETE FROM mock_usages WHERE fixture_id IN "
                f"(SELECT id FROM fixtures WHERE repo_id IN ({placeholders}))",
                repos_to_remove,
            )

            # Delete fixtures
            cursor = conn.execute(
                f"SELECT COUNT(*) as n FROM fixtures WHERE repo_id IN ({placeholders})",
                repos_to_remove,
            )
            fixture_count = cursor.fetchone()["n"]
            summary["fixtures_removed"] = fixture_count

            conn.execute(
                f"DELETE FROM fixtures WHERE repo_id IN ({placeholders})",
                repos_to_remove,
            )

            # Update repository status to 'skipped' instead of deleting the repo record
            # (keeps provenance that we discovered them, but didn't keep them)
            conn.execute(
                f"UPDATE repositories SET status = 'skipped', skip_reason = 'Removed to maintain toy dataset balance' "
                f"WHERE id IN ({placeholders})",
                repos_to_remove,
            )

            summary["repos_removed"] = len(repos_to_remove)

        conn.commit()

    return summary
