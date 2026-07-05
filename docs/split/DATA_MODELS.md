# FixtureDB Split: Data Models

Complete documentation of the database schemas for fixturedb-human.db and fixturedb-agent.db

---

## Overview

**fixturedb-human.db:** Identical schema to corpus.db (no agent tracking needed)  
**fixturedb-llm.db:** Extended with agent metadata columns

Both databases inherit the core schema from corpus.db with additions specific to the agent dataset.

---

## Core Schema (Both Databases)

### REPOSITORIES Table

Metadata about repositories in the dataset.

```sql
CREATE TABLE repositories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    github_id INTEGER UNIQUE,
    full_name TEXT NOT NULL,                    -- e.g., "torvalds/linux"
    language TEXT,                              -- Primary language (Python, Java, etc.)
    stars INTEGER DEFAULT 0,                    -- GitHub stars
    forks INTEGER DEFAULT 0,                    -- Fork count
    description TEXT,                           -- Repository description
    topics TEXT,                                -- JSON array of topics
    created_at TEXT,                            -- Repo creation date
    pushed_at TEXT,                             -- Last push date
    clone_url TEXT NOT NULL UNIQUE,             -- Clone URL
    pinned_commit TEXT,                         -- Fixed commit SHA (for snapshots)
    domain TEXT,                                -- Domain classification
    star_tier TEXT,                             -- Star count tier
    status TEXT DEFAULT 'discovered',           -- Status (analysed|cloned|discovered|skipped|error)
    error_message TEXT,                         -- Error details if status=error
    skip_reason TEXT,                           -- Reason if status=skipped
    num_test_files INTEGER DEFAULT 0,           -- Count of test files
    num_fixtures INTEGER DEFAULT 0,             -- Count of fixtures
    num_mock_usages INTEGER DEFAULT 0,          -- Mock usage count
    num_contributors INTEGER DEFAULT 0,         -- GitHub contributor count
    agent_commits_touching_tests INTEGER DEFAULT 0,          -- Dataset A: agent commits touching >=1 test file
    agent_commits_rejected_mixed_test_diff INTEGER DEFAULT 0, -- Dataset A: rejected, a test file had deletions/edits
    agent_commits_accepted INTEGER DEFAULT 0,                 -- Dataset A: accepted, all test file diffs were pure additions
    collected_at TEXT DEFAULT CURRENT_TIMESTAMP -- When data was collected
);

CREATE INDEX idx_repo_full_name ON repositories(full_name);
CREATE INDEX idx_repo_language ON repositories(language);
CREATE INDEX idx_repo_status ON repositories(status);
CREATE INDEX idx_repo_domain ON repositories(domain);
```

| Column | Type | Purpose |
|--------|------|---------|
| id | INTEGER | Primary key |
| github_id | INTEGER | GitHub API ID |
| full_name | TEXT | owner/repo format |
| language | TEXT | Primary language (Python/Java/JavaScript/TypeScript) |
| stars | INTEGER | GitHub stars at collection time |
| pinned_commit | TEXT | Snapshot point for pre-2021 data |
| status | TEXT | analysed = fixtures extracted successfully |
| num_test_files | INTEGER | Test file count in dataset |
| num_fixtures | INTEGER | Fixture count in dataset |
| agent_commits_touching_tests | INTEGER | Dataset A: agent commits that touched >=1 test file (set during agent test-commit detection) |
| agent_commits_rejected_mixed_test_diff | INTEGER | Dataset A: of those, commits rejected because a test file had deletions/edits |
| agent_commits_accepted | INTEGER | Dataset A: of those, commits accepted because all test file diffs were pure additions |

---

### TEST_FILES Table

Metadata about test files containing fixtures.

```sql
CREATE TABLE test_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id INTEGER NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    file_path TEXT NOT NULL,                    -- e.g., "tests/test_model.py"
    relative_path TEXT,                         -- Relative path (same as file_path)
    file_size_bytes INTEGER,                    -- Physical file size
    line_count INTEGER,                         -- Total lines in file
    fixture_count INTEGER DEFAULT 0,            -- Number of fixtures in file
    language TEXT DEFAULT 'python',             -- Programming language
    content_hash TEXT,                          -- SHA256 hash for deduplication
    is_fixture_file BOOLEAN DEFAULT TRUE,       -- Contains fixtures?
    last_modified TEXT,                         -- Last modification date
    created_at_analyzed TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(repo_id) REFERENCES repositories(id) ON DELETE CASCADE,
    UNIQUE(repo_id, file_path)
);

CREATE INDEX idx_testfile_repo ON test_files(repo_id);
CREATE INDEX idx_testfile_fixture_count ON test_files(fixture_count);
CREATE INDEX idx_testfile_language ON test_files(language);
```

| Column | Type | Purpose |
|--------|------|---------|
| id | INTEGER | Primary key |
| repo_id | INTEGER | Foreign key to repositories |
| file_path | TEXT | Path relative to repo root |
| fixture_count | INTEGER | Number of fixtures in this file |
| language | TEXT | File language (Python/Java/JavaScript/TypeScript) |
| content_hash | TEXT | SHA256 hash for deduplication |

---

### FIXTURES Table

Individual fixture definitions. Core schema same in both databases.

```sql
CREATE TABLE fixtures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL REFERENCES test_files(id) ON DELETE CASCADE,
    repo_id INTEGER NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    name TEXT NOT NULL,                         -- Fixture name
    fixture_type TEXT,                          -- pytest_decorator|unittest_setup|etc.
    scope TEXT DEFAULT 'function',              -- function|class|module|session
    start_line INTEGER,                         -- Line number in file
    end_line INTEGER,                           -- Line number in file
    loc INTEGER,                                -- Lines of code (non-blank)
    cyclomatic_complexity INTEGER,              -- McCabe complexity
    cognitive_complexity INTEGER,               -- SonarQube cognitive complexity
    max_nesting_depth INTEGER DEFAULT 0,        -- Maximum nesting level
    num_objects_instantiated INTEGER DEFAULT 0, -- Objects created
    num_external_calls INTEGER DEFAULT 0,       -- External function calls
    num_parameters INTEGER DEFAULT 0,           -- Parameter count
    reuse_count INTEGER DEFAULT 0,              -- Used by N test functions
    has_teardown_pair INTEGER DEFAULT 0,        -- Has cleanup logic?
    raw_source TEXT NOT NULL,                   -- Complete source code
    category TEXT,                              -- RQ1 taxonomy label
    framework TEXT,                             -- Testing framework
    UNIQUE(file_id, name, start_line),
    FOREIGN KEY(file_id) REFERENCES test_files(id) ON DELETE CASCADE,
    FOREIGN KEY(repo_id) REFERENCES repositories(id) ON DELETE CASCADE
);

CREATE INDEX idx_fixture_repo ON fixtures(repo_id);
CREATE INDEX idx_fixture_file ON fixtures(file_id);
CREATE INDEX idx_fixture_name ON fixtures(name);
CREATE INDEX idx_fixture_type ON fixtures(fixture_type);
CREATE INDEX idx_fixture_framework ON fixtures(framework);
```

| Column | Type | Purpose | Human | LLM |
|--------|------|---------|--------|-----|
| id | INTEGER | Primary key | ✓ | ✓ |
| file_id | INTEGER | FK to test_files | ✓ | ✓ |
| repo_id | INTEGER | FK to repositories | ✓ | ✓ |
| name | TEXT | Fixture name | ✓ | ✓ |
| fixture_type | TEXT | Type (pytest/unittest) | ✓ | ✓ |
| scope | TEXT | Scope (function/class/module) | ✓ | ✓ |
| loc | INTEGER | Lines of code | ✓ | ✓ |
| cyclomatic_complexity | INTEGER | McCabe complexity | ✓ | ✓ |
| cognitive_complexity | INTEGER | Cognitive complexity | ✓ | ✓ |
| max_nesting_depth | INTEGER | Max nesting | ✓ | ✓ |
| reuse_count | INTEGER | Used by N tests | ✓ | ✓ |
| raw_source | TEXT | Source code | ✓ | ✓ |
| framework | TEXT | Testing framework | ✓ | ✓ |
| **commit_sha** | TEXT | Git commit SHA | ✗ | ✓ |
| **agent_type** | TEXT | Agent (claude/copilot) | ✗ | ✓ |
| **is_complete_addition** | BOOLEAN | Fully added (not refactored) | ✗ | ✓ |
| **commit_author_name** | TEXT | Commit author | ✗ | ✓ |
| **commit_author_email** | TEXT | Author email | ✗ | ✓ |
| **commit_date** | TEXT | When committed | ✗ | ✓ |

---

### MOCKS Table

Tracks mock usage within fixtures.

```sql
CREATE TABLE mocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id INTEGER NOT NULL REFERENCES fixtures(id) ON DELETE CASCADE,
    mock_name TEXT NOT NULL,                    -- e.g., "mock_database"
    mock_type TEXT,                             -- Mock|MagicMock|patch|etc.
    line_position INTEGER,                      -- Position within fixture
    created_at_analyzed TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(fixture_id) REFERENCES fixtures(id) ON DELETE CASCADE
);

CREATE INDEX idx_mock_fixture ON mocks(fixture_id);
```

---

## Extended Schema for LLM (fixturedb-llm.db Only)

### Additional FIXTURES Columns

```sql
-- These columns are ONLY in fixturedb-llm.db

ALTER TABLE fixtures ADD COLUMN commit_sha TEXT;
    -- Git commit SHA where fixture was added
    -- Example: "a1b2c3d4e5f6..."
    -- Enables: git show {commit_sha}:{file_path}
    -- Required: 100% of fixtures (no NULL values)
    -- Index: Fast lookup by commit

ALTER TABLE fixtures ADD COLUMN agent_type TEXT;
    -- AI agent that created this fixture
    -- Values: 'claude' | 'copilot' | 'cursor' | 'other'
    -- From: Phase 1B verification
    -- Confidence: 100% (verified)
    -- Required: 100% of fixtures (no NULL values)

ALTER TABLE fixtures ADD COLUMN is_complete_addition BOOLEAN;
    -- Validation: Fixture completely added in one commit
    -- TRUE: All lines are additions (+ prefix in diff)
    -- FALSE: Modified/refactored (filtered out during extraction)
    -- Required: 100% of LLM fixtures = TRUE (by design)
    -- Used: For completeness validation

ALTER TABLE fixtures ADD COLUMN commit_author_name TEXT;
    -- Original commit author name
    -- Example: "John Doe"
    -- Purpose: Attribution tracking
    -- Optional: May be NULL for automated commits

ALTER TABLE fixtures ADD COLUMN commit_author_email TEXT;
    -- Original commit author email
    -- Example: "john@example.com"
    -- Purpose: Agent verification
    -- Optional: May be NULL

ALTER TABLE fixtures ADD COLUMN commit_date TEXT;
    -- When commit was authored
    -- Format: ISO 8601 (YYYY-MM-DDTHH:MM:SS)
    -- Filter: >= 2020-12-31 (by design)
    -- Use: Time-series analysis (early 2021 vs 2026)

-- Indexes for fast queries on agent-specific columns
CREATE INDEX idx_agent_commit ON fixtures(commit_sha);
CREATE INDEX idx_agent_agent ON fixtures(agent_type);
CREATE INDEX idx_agent_complete ON fixtures(is_complete_addition);
CREATE INDEX idx_agent_date ON fixtures(commit_date);
```

---

## Data Model Comparison

### Human Dataset (Pre-2021)

```
Characteristics:
- Snapshot-based (all fixtures at pinned_commit)
- No agent tracking (pre-AI era)
- All fixtures from 2020 and earlier
- Represents "baseline" human testing practices
- Full repository context available

Schema: Identical to corpus.db
Data:
  - Repositories: 200
  - Test files: ~157k
  - Fixtures: human dataset
  - No commit metadata
```

### Agent Dataset (2021+)

```
Characteristics:
- Commit-by-commit tracking (agents identified per commit)
- Full agent attribution (Claude/Copilot/Cursor)
- All fixtures from 2021 onwards
- Represents "agent-generated" testing practices
- Exact reproducibility via commit SHA

Schema: corpus.db + agent columns
Data:
  - Repositories: ~145 (with agent commits)
  - Test files: ~78k (modified by agents)
  - Fixtures: ~87k (completely added by agents)
  - Full commit metadata per fixture
  - Agent attribution (100% accuracy)
```

---

## Fixture Type Taxonomy

Fixtures are classified by type and framework:

### Pytest (81% of dataset)
```
Type: pytest_decorator
Scope: function | class | module | session
Example:
  @pytest.fixture
  def user_db():
      return Database(":memory:")
```

### Unittest (14% of dataset)
```
Type: unittest_setup | unittest_teardown
Scope: class | module
Example:
  class TestModel(unittest.TestCase):
      def setUp(self):
          self.db = Database()
```

### Other (5% of dataset)
```
Types: before_each | after_each | before_all | after_all | helper
Frameworks: Jasmine, Mocha, Jest, JUnit, NUnit, TestNG
```

---

## Complexity Metrics

### Cyclomatic Complexity
- Measures: Number of linearly independent paths
- Range: 1 (simple) to 10+ (very complex)
- Tool: Lizard (language-independent)

### Cognitive Complexity
- Measures: Mental effort required to understand code
- Range: 0 (trivial) to 20+ (complex)
- Tool: SonarQube methodology

### Max Nesting Depth
- Measures: Maximum block nesting level
- Range: 1 (no nesting) to 10+ (deep nesting)
- Extracted: Via tree-sitter AST

### Example
```python
@pytest.fixture
def complex_fixture(db):           # Nesting: 1
    result = []
    for repo in db.repos:          # Nesting: 2
        if repo.active:            # Nesting: 3
            for file in repo.files: # Nesting: 4
                if file.is_test:    # Nesting: 5
                    result.append(file)
    return result

# Metrics:
# - Lines of code: 7
# - Cyclomatic complexity: 3 (2 conditions × paths)
# - Cognitive complexity: 3
# - Max nesting depth: 5
```

---

## CSV Export Format

### fixtures.csv (Human Dataset)

```csv
repository_id,repository_name,test_file_id,test_file_path,fixture_id,fixture_name,fixture_type,scope,loc,cyclomatic_complexity,cognitive_complexity,max_nesting_depth,num_parameters,reuse_count,framework
4,torvalds/linux,123,tests/test_model.py,456,user_fixture,pytest_decorator,function,15,2,2,2,1,8,pytest
5,torvalds/linux,124,tests/test_utils.py,457,db_fixture,pytest_decorator,module,22,3,3,3,0,12,pytest
```

### fixtures.csv (LLM Dataset) - Extended

```csv
repository_id,repository_name,test_file_id,test_file_path,fixture_id,fixture_name,fixture_type,scope,loc,cyclomatic_complexity,cognitive_complexity,max_nesting_depth,num_parameters,reuse_count,framework,commit_sha,agent_type,is_complete_addition,commit_date
4,torvalds/linux,123,tests/test_model.py,789,ai_fixture,pytest_decorator,function,12,1,1,1,2,5,pytest,a1b2c3d4e5f6,copilot,true,2024-03-15T10:30:00
5,torvalds/linux,124,tests/test_utils.py,790,ml_fixture,pytest_decorator,function,18,2,2,2,1,10,pytest,b2c3d4e5f6a7,claude,true,2024-03-16T14:45:00
```

---

## Relationships & Integrity

### Foreign Key Constraints

```
repositories
  ├─ 1:N → test_files (repo_id)
  │         ├─ 1:N → fixtures (file_id, repo_id)
  │         └─ N:1 → fixtures (repo_id)
  └─ N:1 ← fixtures (repo_id)

test_files
  ├─ N:1 → repositories (repo_id)
  └─ 1:N → fixtures (file_id)
           └─ 1:N → mocks (fixture_id)

fixtures
  ├─ N:1 → repositories (repo_id)
  ├─ N:1 → test_files (file_id)
  └─ 1:N → mocks (fixture_id)

mocks
  └─ N:1 → fixtures (fixture_id)
```

### Cascade Delete Policy
- Delete repository → Delete all test_files, fixtures, mocks
- Delete test_file → Delete all fixtures in that file, their mocks
- Delete fixture → Delete all mocks using that fixture

### Unique Constraints

```
fixtures UNIQUE(file_id, name, start_line)
  → No duplicate fixture names per file at same line

test_files UNIQUE(repo_id, file_path)
  → No duplicate test file paths per repository

repositories UNIQUE(github_id, clone_url)
  → No duplicate repositories by GitHub ID or URL
```

---

## Row Count Estimates

| Table | Human | LLM |
|-------|-------|-----|
| repositories | ~200 | ~145 |
| test_files | ~157k | ~78k |
| fixtures | human dataset | agent dataset |
| mocks | ~2k | ~3k |

---

## Query Examples

### Find all pytest fixtures with high complexity

**SQL:**
```sql
SELECT f.name, f.loc, f.cyclomatic_complexity
FROM fixtures f
WHERE f.fixture_type = 'pytest_decorator'
  AND f.cyclomatic_complexity >= 5
ORDER BY f.cyclomatic_complexity DESC
```

### Compare fixture reuse between human and LLM

**SQL (human.db):**
```sql
SELECT fixture_type, AVG(reuse_count) as avg_reuse
FROM fixtures
GROUP BY fixture_type
```

**SQL (llm.db):**
```sql
SELECT agent_type, fixture_type, AVG(reuse_count) as avg_reuse
FROM fixtures
GROUP BY agent_type, fixture_type
```

### Find all Copilot-generated fixtures from 2024

**SQL:**
```sql
SELECT r.full_name, f.name, f.commit_sha, f.commit_date
FROM fixtures f
JOIN repositories r ON f.repo_id = r.id
WHERE f.agent_type = 'copilot'
  AND f.commit_date >= '2024-01-01'
ORDER BY f.commit_date DESC
```

### Verify fixture completeness (LLM database)

**SQL:**
```sql
SELECT 
  COUNT(*) as total,
  SUM(CASE WHEN is_complete_addition = 1 THEN 1 ELSE 0 END) as complete,
  SUM(CASE WHEN is_complete_addition = 0 THEN 1 ELSE 0 END) as incomplete
FROM fixtures
```

---

## Schema Evolution

### From corpus.db to fixturedb-human.db
- No schema changes
- Simple copy + filter operation
- All columns retained
- Agent columns remain NULL/unused

### From corpus.db to fixturedb-llm.db
- Schema extension (+ 6 columns)
- All core columns retained
- New columns: commit_sha, agent_type, is_complete_addition, commit_author_name, commit_author_email, commit_date
- Backward compatible (old code can still query core columns)

---

## Data Quality Standards

### Completeness
- Human: all pre-2021 fixtures included
- LLM: Only completely-added fixtures (is_complete_addition = TRUE)

### Uniqueness
- No duplicate fixtures (UNIQUE constraint on file_id, name, start_line)
- No duplicate repositories (UNIQUE on github_id, clone_url)

### Integrity
- All foreign keys enforced
- No orphaned records (cascade delete on parent deletion)
- All required fields populated

### Accuracy
- Fixture metrics validated against source code
- Agent detection: 100% precision (validated on 500 samples)
- Completeness: Validated via git diff analysis
