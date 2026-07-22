"""
Database layer — connection/query helpers over the schema in db_schema.py.

All analysis reads from this DB; all collection writes to it.
Schema is designed to be append-safe: re-running the pipeline on new repos
will not duplicate existing records. Repo-metadata computation (domain,
age) has no DB dependency and lives in repo_metadata.py instead.
"""

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from collection.logging_utils import get_logger

from .config import DB_PATH
from .db_schema import SCHEMA

logger = get_logger(__name__)

GLOBAL_CHECKPOINT_REPO_ID = 0


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Open a WAL-mode SQLite connection at *db_path* with a 60s busy timeout.

    Prefer `db_session()` for normal use — it wraps this with retries and
    connection pooling. Use this directly only for one-off scripts/tests.
    """
    # Use a file-backed SQLite DB with WAL and a generous busy timeout to
    # tolerate concurrent readers while writers operate. These PRAGMA settings
    # are chosen to reduce transient `database is locked` errors during
    # multi-worker extraction and insertion:
    #  - `journal_mode=WAL` allows concurrent reads and a single writer
    #  - `busy_timeout` / `timeout` give SQLite time to resolve brief locks
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
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
        rowid = cursor.lastrowid
        return rowid if rowid is not None else 0

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
        rowid = cursor.lastrowid
        return rowid if rowid is not None else 0

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


def migrate_add_adoption_intensity(db_path: Path = DB_PATH) -> None:
    """Add agent_adoption_intensity column to existing databases (idempotent)."""
    try:
        conn = get_connection(db_path)
        conn.execute(
            "ALTER TABLE repositories ADD COLUMN agent_adoption_intensity TEXT DEFAULT NULL"
        )
        conn.commit()
        conn.close()
        logger.info("Migrated repositories table: added agent_adoption_intensity column")
    except sqlite3.OperationalError:
        # Column already exists — safe to ignore
        pass
    except Exception:
        logger.debug("Migration skipped (database may not exist yet)")


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

    adoption = repo.get("agent_adoption_intensity")

    conn.execute(
        """
        INSERT INTO repositories (
            github_id, full_name, language, stars, forks,
            description, topics, created_at, pushed_at, clone_url,
            domain, repo_age_years, num_contributors,
            agent_adoption_intensity
        ) VALUES (
            :github_id, :full_name, :language, :stars, :forks,
            :description, :topics, :created_at, :pushed_at, :clone_url,
            :domain, :repo_age_years, :num_contributors,
            :agent_adoption_intensity
        )
        ON CONFLICT(github_id) DO UPDATE SET
            stars       = excluded.stars,
            pushed_at   = excluded.pushed_at,
            domain      = excluded.domain,
            repo_age_years = excluded.repo_age_years,
            num_contributors = excluded.num_contributors,
            agent_adoption_intensity = excluded.agent_adoption_intensity
    """,
        {**repo, "agent_adoption_intensity": adoption},
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
    error: Optional[str] = None,
    skip_reason: Optional[str] = None,
    pinned_commit: Optional[str] = None,
) -> None:
    """Update a repo's pipeline status, optionally recording an error/skip reason."""
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
    num_contributors: int | None = None,
) -> None:
    """Mark a repo as analysed and store the extraction counts.

    num_contributors defaults to None (left unchanged via COALESCE) rather
    than 0 -- it's set separately from GitHub metadata by upsert_repository(),
    and callers here (persist_repository_and_fixtures(), re-syncing counts
    after every fixture-persist call) have no reason to know or touch it.
    """
    conn.execute(
        """
        UPDATE repositories
        SET status = 'analysed',
            num_contributors = COALESCE(?, num_contributors),
            num_test_files = ?,
            num_fixtures = ?,
            num_mock_usages = ?
        WHERE id = ?
    """,
        (num_contributors, num_test_files, num_fixtures, num_mock_usages, repo_id),
    )


def update_agent_commit_stats(
    conn: sqlite3.Connection,
    repo_id: int,
    stats: dict,
) -> None:
    """Persist Dataset A's per-repo agent test-commit counters.

    `stats` is expected to have `agent_commits_touching_tests`,
    `rejected_mixed_test_diff`, and `accepted` keys (see
    AgentCorpusCollector.run()).
    """
    conn.execute(
        """
        UPDATE repositories
        SET agent_commits_touching_tests = ?,
            agent_commits_rejected_mixed_test_diff = ?,
            agent_commits_accepted = ?
        WHERE id = ?
    """,
        (
            int(stats.get("agent_commits_touching_tests", 0) or 0),
            int(stats.get("rejected_mixed_test_diff", 0) or 0),
            int(stats.get("accepted", 0) or 0),
            repo_id,
        ),
    )


def get_repos_by_status(conn: sqlite3.Connection, status: str) -> list[sqlite3.Row]:
    """Return all repository rows with the given pipeline *status*."""
    return conn.execute(
        "SELECT * FROM repositories WHERE status = ?", (status,)
    ).fetchall()


# ---------------------------------------------------------------------------
# Test file helpers
# ---------------------------------------------------------------------------


def upsert_test_file(
    conn: sqlite3.Connection, repo_id: int, relative_path: str, language: str
) -> int:
    """Insert the test file row if missing, and return its id either way."""
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
    """Update a test file's aggregate test/fixture counts and LOC."""
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
        "commit_type",
    ]
    for col in agent_columns:
        if col in fixture:
            columns.append(col)

    # commit_sha must always be part of the row (defaulting to "" when the
    # caller didn't provide one, e.g. Dataset C's pre2021 extractor) so it
    # can safely be part of the UNIQUE constraint below. Dataset A/B walk
    # full repo history and persist one row per qualifying commit, so
    # dedup must be per-commit, not just per (file, name, line) -- but
    # SQLite treats NULL as always-distinct in UNIQUE indexes, which would
    # silently disable dedup entirely for any caller that left it NULL.
    if "commit_sha" not in columns:
        columns.append("commit_sha")
        fixture = {**fixture, "commit_sha": fixture.get("commit_sha") or ""}

    # Build the INSERT statement
    cols_str = ", ".join(columns)
    placeholders = ", ".join([f":{col}" for col in columns])

    cursor = conn.execute(
        f"""
        INSERT INTO fixtures ({cols_str})
        VALUES ({placeholders})
        ON CONFLICT(file_id, name, start_line, commit_sha) DO NOTHING
        """,
        fixture,
    )
    if cursor.rowcount == 1:
        rowid = cursor.lastrowid
        return rowid if rowid is not None else 0
    row = conn.execute(
        "SELECT id FROM fixtures WHERE file_id=? AND name=? AND start_line=? AND commit_sha=?",
        (fixture["file_id"], fixture["name"], fixture["start_line"], fixture["commit_sha"]),
    ).fetchone()
    if row is None:
        raise ValueError(
            f"Fixture insert conflict but SELECT returned no rows: "
            f"file_id={fixture['file_id']}, name={fixture['name']}, "
            f"start_line={fixture['start_line']}, commit_sha={fixture['commit_sha']}"
        )
    return row["id"]




# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


def insert_mock_usage(conn: sqlite3.Connection, mock: dict) -> None:
    """Insert a mock/stub usage row keyed by `mock`'s dict fields."""
    try:
        conn.execute(
            """
            INSERT INTO mock_usages (
                fixture_id, repo_id, framework, category, target_identifier,
                num_interactions_configured, raw_snippet
            ) VALUES (
                :fixture_id, :repo_id, :framework, :category, :target_identifier,
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
    """Return repo counts by status plus total test file/fixture/mock rows."""
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


