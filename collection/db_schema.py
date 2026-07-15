"""SQLite DDL for the FixtureDB schema. Applied by db.py's initialise_db()."""

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
    repo_age_years  REAL DEFAULT NULL,      -- repository age in years at collection time
    agent_adoption_intensity TEXT DEFAULT NULL,  -- agent commit ratio since adoption: no_commits/experimental/limited/consistent/pervasive
    agent_commits_touching_tests INTEGER DEFAULT 0,  -- Dataset A: agent commits that touched >=1 test file
    agent_commits_rejected_mixed_test_diff INTEGER DEFAULT 0,  -- Dataset A: rejected, a test file had deletions/edits
    agent_commits_accepted  INTEGER DEFAULT 0,      -- Dataset A: accepted, all test file diffs were pure additions
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
    commit_type             TEXT DEFAULT NULL,      -- Conventional Commits type of the originating commit
                                    -- (agent or human: feat/fix/docs/refactor/test/chore/style/other/none)
    UNIQUE(file_id, name, start_line, commit_sha)
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
    category                    TEXT,   -- test-double taxonomy: dummy/stub/spy/mock/fake
                                        -- (see feature_extraction_patterns.yaml)
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
CREATE INDEX IF NOT EXISTS idx_mocks_category   ON mock_usages(category);
CREATE INDEX IF NOT EXISTS idx_test_files_repo  ON test_files(repo_id);
CREATE INDEX IF NOT EXISTS idx_test_commits_repo ON test_commits(repo_id);
CREATE INDEX IF NOT EXISTS idx_test_commits_role ON test_commits(commit_role);

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
