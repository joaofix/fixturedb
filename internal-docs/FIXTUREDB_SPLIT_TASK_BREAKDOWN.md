# FixtureDB Split - Task Breakdown by Prompt

**Purpose:** Each task below can be completed in a single prompt. Tasks are ordered by dependency.

---

## TASK 1A: Phase 1A Implementation - Agent File Scanning

**Status:** Not Started  
**Estimated Time:** 2-3 hours  
**Dependencies:** None  
**Blocker Risk:** LOW

### Objective
Scan all repositories for AI agent configuration files and identify ~2,168 repos with agent usage.

### Input
- Path to clones directory: `/home/joao/icsme-nier-2026/clones/`
- Agent patterns (defined in implementation plan Section 2.6)

### Output
**File:** `/home/joao/icsme-nier-2026/output/phase_1a_agent_files_found.json`

```json
{
  "timestamp": "2026-05-13T10:30:00Z",
  "scanned_repos": 34297,
  "repos_with_agent_files": 2168,
  "by_agent": {
    "claude": 1245,
    "cursor": 523,
    "copilot": 890
  },
  "results": [
    {
      "repo_name": "feast-dev/feast",
      "agents_detected": ["claude", "copilot"],
      "files_found": ["CLAUDE.md", "copilot_instructions.md"]
    },
    ...
  ]
}
```

### Implementation Steps
1. Write Python script `collection/phase_1a_scan_agent_files.py`
2. Function: `scan_for_agent_files(clones_dir) -> dict`
3. Patterns: Check for CLAUDE.md, .claudeignore, .claude/, etc.
4. Output: JSON file with results
5. Validation: ~2,168 repos found (within 10% of expected)

### Success Criteria
- [ ] Script created and tested
- [ ] Output JSON file generated
- [ ] 1,500 - 2,500 repos with agent files (accounting for variance)
- [ ] All repo names valid and unique
- [ ] Execution time < 1 hour

### Verification Commands
```bash
# Count repos with agent files
jq '.repos_with_agent_files' output/phase_1a_agent_files_found.json

# Verify structure
jq '.results[0]' output/phase_1a_agent_files_found.json
```

### Next Task
→ TASK 1B: Phase 1B Implementation - Agent Commit Verification

---

## TASK 1B: Phase 1B Implementation - Agent Commit Verification

**Status:** Not Started  
**Estimated Time:** 4-6 hours  
**Dependencies:** TASK 1A  
**Blocker Risk:** MEDIUM (git operations on large repos)

### Objective
Verify which repos actually have agent-authored commits by parsing Co-authored-by trailers. Expected: ~1,219 verified repos with ~48,563 agent commits.

### Input
**File:** `/home/joao/icsme-nier-2026/output/phase_1a_agent_files_found.json` (from TASK 1A)
- List of ~2,168 repos with agent files

### Output
**File:** `/home/joao/icsme-nier-2026/output/phase_1b_agent_commits_verified.json`

```json
{
  "timestamp": "2026-05-13T14:30:00Z",
  "repos_with_agent_files": 2168,
  "repos_with_agent_commits": 1219,
  "total_agent_commits": 48563,
  "by_agent": {
    "copilot": 25342,
    "claude": 18920,
    "cursor": 3456,
    "other": 845
  },
  "repo_details": [
    {
      "repo_name": "feast-dev/feast",
      "agent_commits_count": 142,
      "commits": [
        {
          "commit_sha": "a1b2c3d4e5f6...",
          "agent_type": "claude",
          "commit_date": "2023-06-15T10:30:00Z",
          "coauthor": "claude"
        },
        ...
      ]
    },
    ...
  ]
}
```

### Implementation Steps
1. Write Python script `collection/phase_1b_verify_agent_commits.py`
2. Function: `find_agent_commits(repo_path, agent_names) -> Dict[str, str]`
3. For each repo from TASK 1A:
   - Use git log to extract commits
   - Parse commit messages for Co-authored-by trailers (case-insensitive)
   - Search for agent patterns (claude, cursor, copilot, aider, openhands, etc.)
   - Record: commit_sha → agent_type
4. Filter by date: >= 2022-01-01
5. Output: JSON mapping repos → agent commits

### Success Criteria
- [ ] Script created and tested on 5-10 repos
- [ ] Output JSON file generated
- [ ] ~1,000 - 1,500 verified repos (within 15% of expected 1,219)
- [ ] ~40,000 - 55,000 agent commits (within 15% of expected 48,563)
- [ ] Agent distribution matches advisor's paper (~52% Copilot, ~39% Claude, ~7% Cursor, ~2% Other)
- [ ] Execution time < 8 hours (may run overnight)

### Verification Commands
```bash
# Total verified repos
jq '.repos_with_agent_commits' output/phase_1b_agent_commits_verified.json

# Total commits
jq '.total_agent_commits' output/phase_1b_agent_commits_verified.json

# Distribution
jq '.by_agent' output/phase_1b_agent_commits_verified.json
```

### Notes
- This is a slow task (git operations on ~1,200 repos)
- Can be parallelized using ThreadPoolExecutor
- Store results incrementally in case of interruption
- Consider caching git log results

### Next Task
→ TASK 2: Phase 2 Implementation - Pre-2021 Fixture Extraction

---

## TASK 2: Phase 2 Implementation - Pre-2021 Fixture Extraction

**Status:** Not Started  
**Estimated Time:** 2-3 hours  
**Dependencies:** TASK 1B (for agent repo list, to exclude for analysis)  
**Blocker Risk:** LOW

### Objective
Extract all fixtures from pre-2021 era using pinned commits. Expected: ~240,856 pre-2021 fixtures.

### Input
- **Database:** `/home/joao/icsme-nier-2026/data/corpus.db` (original)
- Query: All fixtures where commit_date < 2021-01-01
- Pinned commits from: `repositories.pinned_commit` column

### Output
**File:** `/home/joao/icsme-nier-2026/output/phase_2_pre_2021_fixtures.json`

```json
{
  "timestamp": "2026-05-13T15:30:00Z",
  "total_pre_2021_fixtures": 240856,
  "by_fixture_type": {
    "pytest": 195692,
    "unittest": 33614,
    "other": 11550
  },
  "by_repo_count": 189,
  "sample_fixtures": [
    {
      "fixture_id": 1,
      "fixture_name": "user_fixture",
      "repo_id": 4,
      "test_file_id": 123,
      "fixture_type": "pytest",
      "scope": "function",
      "content_hash": "abc123def456"
    },
    ...
  ],
  "fixture_ids": [1, 2, 3, 5, 8, ...]  // All fixture IDs
}
```

### Implementation Steps
1. Write Python script `collection/phase_2_extract_pre_2021.py`
2. Function: `extract_pre_2021_fixtures(db_path) -> List[Fixture]`
3. Query corpus.db for fixtures with date < 2021-01-01
4. Validate: All fixtures have required columns
5. Count by fixture_type (pytest|unittest|other)
6. Output: JSON with complete fixture list

### Success Criteria
- [ ] Script created and tested
- [ ] Output JSON file generated
- [ ] >= 100,000 pre-2021 fixtures found
- [ ] Distribution matches expected: pytest ~77%, unittest ~17%, other ~6%
- [ ] All fixtures have: fixture_id, fixture_name, repo_id, test_file_id, content_hash
- [ ] No duplicates in fixture_ids list

### Verification Commands
```bash
# Total count
jq '.total_pre_2021_fixtures' output/phase_2_pre_2021_fixtures.json

# By type
jq '.by_fixture_type' output/phase_2_pre_2021_fixtures.json

# Sample
jq '.sample_fixtures[0]' output/phase_2_pre_2021_fixtures.json
```

### Next Task
→ TASK 3: Phase 3 Implementation - LLM Fixture Extraction

---

## TASK 3: Phase 3 Implementation - LLM Fixture Extraction

**Status:** Not Started  
**Estimated Time:** 6-8 hours  
**Dependencies:** TASK 1B  
**Blocker Risk:** HIGH (git operations, completeness validation)

### Objective
Extract fixtures completely added in verified agent commits (2022+). Expected: ~87,432 LLM fixtures.

### Input
**File:** `/home/joao/icsme-nier-2026/output/phase_1b_agent_commits_verified.json` (from TASK 1B)
- Mapping of repos → verified agent commits with SHAs

### Output
**File:** `/home/joao/icsme-nier-2026/output/phase_3_llm_fixtures_extracted.json`

```json
{
  "timestamp": "2026-05-13T20:30:00Z",
  "total_llm_fixtures": 87432,
  "by_agent": {
    "copilot": 45302,
    "claude": 33891,
    "cursor": 6123,
    "other": 2116
  },
  "by_fixture_type": {
    "pytest": 71234,
    "unittest": 12089,
    "other": 4109
  },
  "completeness_stats": {
    "total_candidates": 127423,
    "completely_added": 87432,
    "partial_or_modified": 39991,
    "rejection_reasons": {
      "fixture_exists_in_parent": 23456,
      "partial_addition": 12234,
      "multiple_fixtures_in_commit": 4301
    }
  },
  "sample_fixtures": [
    {
      "fixture_id": 35001,
      "fixture_name": "mock_api",
      "repo_id": 4,
      "test_file_id": 456,
      "fixture_type": "pytest",
      "scope": "function",
      "content_hash": "xyz789abc",
      "commit_sha": "a1b2c3d4...",
      "agent_type": "claude",
      "commit_date": "2023-06-15T10:30:00Z",
      "is_complete_addition": true
    },
    ...
  ],
  "fixture_details": [
    {
      "fixture_id": 35001,
      "commit_sha": "a1b2c3d4...",
      "agent_type": "claude"
    },
    ...
  ]
}
```

### Implementation Steps
1. Write Python script `collection/phase_3_extract_llm_fixtures.py`
2. Function: `extract_llm_fixtures(repo_path, agent_commits_map, start_date) -> List[FixtureWithCommit]`
3. For each verified agent repo:
   - Checkout git history
   - For each verified agent commit:
     - Get git diff for test files
     - Extract new fixture definitions
     - **CRITICAL:** Validate completeness (see Section 2.7 of implementation plan)
     - Record: commit_sha, agent_type, is_complete_addition
4. Count candidates vs accepted
5. Output: JSON with fixtures + metadata

### Success Criteria
- [ ] Script created and tested on 5-10 repos
- [ ] Output JSON file generated
- [ ] >= 50,000 LLM fixtures extracted (minimum viable)
- [ ] Completeness validation working: ~68% completely added, ~32% rejected
- [ ] All extracted fixtures have: commit_sha, agent_type, is_complete_addition
- [ ] Agent distribution aligns with commits: Copilot ~52%, Claude ~39%, Cursor ~7%, Other ~2%
- [ ] No fixtures before 2022-01-01
- [ ] Execution time < 12 hours (may run overnight)

### Verification Commands
```bash
# Total count
jq '.total_llm_fixtures' output/phase_3_llm_fixtures_extracted.json

# By agent
jq '.by_agent' output/phase_3_llm_fixtures_extracted.json

# Completeness stats
jq '.completeness_stats' output/phase_3_llm_fixtures_extracted.json

# Sample
jq '.sample_fixtures[0]' output/phase_3_llm_fixtures_extracted.json
```

### Critical Implementation Note
Completeness validation is the core of this task. See Section 2.7 in implementation plan for detailed algorithm.

### Next Task
→ TASK 4: Phase 4 Implementation - Count & Distribution Analysis

---

## TASK 4: Phase 4 Implementation - Count & Distribution Analysis

**Status:** Not Started  
**Estimated Time:** 1-2 hours  
**Dependencies:** TASK 3  
**Blocker Risk:** LOW

### Objective
Analyze LLM fixture distribution and determine sampling target. This drives the human fixture sample size.

### Input
**File:** `/home/joao/icsme-nier-2026/output/phase_3_llm_fixtures_extracted.json` (from TASK 3)

### Output
**File:** `/home/joao/icsme-nier-2026/output/phase_4_analysis.json`

```json
{
  "timestamp": "2026-05-13T22:00:00Z",
  "llm_fixture_count": 87432,
  "target_sample_size_human": 87432,
  "distribution": {
    "by_agent": {
      "copilot": {
        "count": 45302,
        "percentage": 51.8
      },
      "claude": {
        "count": 33891,
        "percentage": 38.8
      },
      "cursor": {
        "count": 6123,
        "percentage": 7.0
      },
      "other": {
        "count": 2116,
        "percentage": 2.4
      }
    },
    "by_fixture_type": {
      "pytest": {
        "count": 71234,
        "percentage": 81.5
      },
      "unittest": {
        "count": 12089,
        "percentage": 13.8
      },
      "other": {
        "count": 4109,
        "percentage": 4.7
      }
    },
    "by_repository": {
      "feast-dev/feast": 342,
      "academysoftwarefoundation/opencue": 289,
      ...
    }
  },
  "date_range": {
    "earliest": "2022-01-01T00:00:00Z",
    "latest": "2026-05-13T10:30:00Z"
  },
  "evolution": {
    "2022": 12345,
    "2023": 28900,
    "2024": 31456,
    "2025": 12231,
    "2026_ytd": 2500
  }
}
```

### Implementation Steps
1. Write Python script `collection/phase_4_analyze_distribution.py`
2. Function: `analyze_llm_distribution(fixtures) -> dict`
3. Aggregate by:
   - Agent type (claude|copilot|cursor|other)
   - Fixture type (pytest|unittest|other)
   - Repository
   - Year (for time-series analysis)
4. Calculate percentages
5. Output: JSON with complete analysis

### Success Criteria
- [ ] Script created and tested
- [ ] Output JSON file generated
- [ ] All distribution metrics calculated
- [ ] Percentages sum to 100% (for each grouping)
- [ ] Date range verified: earliest >= 2022-01-01
- [ ] Evolution shows reasonable trend

### Verification Commands
```bash
# LLM target count
jq '.target_sample_size_human' output/phase_4_analysis.json

# By agent
jq '.distribution.by_agent' output/phase_4_analysis.json

# By type
jq '.distribution.by_fixture_type' output/phase_4_analysis.json
```

### Next Task
→ TASK 5: Phase 5 Implementation - Stratified Sampling

---

## TASK 5: Phase 5 Implementation - Stratified Sampling

**Status:** Not Started  
**Estimated Time:** 2-3 hours  
**Dependencies:** TASK 2, TASK 4  
**Blocker Risk:** LOW

### Objective
Sample pre-2021 fixtures to exactly match LLM count, maintaining distribution. Input count from TASK 4.

### Input
- **File 1:** `/home/joao/icsme-nier-2026/output/phase_2_pre_2021_fixtures.json` (from TASK 2)
  - All pre-2021 fixture IDs and types
- **File 2:** `/home/joao/icsme-nier-2026/output/phase_4_analysis.json` (from TASK 4)
  - Target count: 87,432 (matching LLM)

### Output
**File:** `/home/joao/icsme-nier-2026/output/phase_5_human_sampled.json`

```json
{
  "timestamp": "2026-05-13T23:00:00Z",
  "source_pool": 240856,
  "target_sample": 87432,
  "sample_rate": 0.363,
  "random_seed": 42,
  "distribution_check": {
    "pytest": {
      "original_ratio": 0.8125,
      "sampled_ratio": 0.8127,
      "tolerance_passed": true
    },
    "unittest": {
      "original_ratio": 0.1395,
      "sampled_ratio": 0.1393,
      "tolerance_passed": true
    },
    "other": {
      "original_ratio": 0.0480,
      "sampled_ratio": 0.0480,
      "tolerance_passed": true
    }
  },
  "sampled_count": 87432,
  "sampled_fixture_ids": [1, 2, 5, 8, 13, ...]  // 87,432 IDs
}
```

### Implementation Steps
1. Write Python script `collection/phase_5_stratified_sample.py`
2. Function: `sample_human_fixtures(all_fixtures, target_count, random_seed=42) -> Set[int]`
3. Stratify pre-2021 fixtures by fixture_type
4. Sample each stratum proportionally
5. Adjust for exact target count
6. Validate distribution maintained within 2% tolerance
7. Output: JSON with sampled fixture IDs

### Success Criteria
- [ ] Script created and tested
- [ ] Output JSON file generated
- [ ] Exactly 87,432 fixtures sampled (no more, no less)
- [ ] Distribution check shows all tolerances <= 2%
- [ ] Random seed = 42 (reproducible)
- [ ] Sampled fixtures are subset of pre-2021
- [ ] Re-running with seed=42 produces identical results

### Verification Commands
```bash
# Sampled count
jq '.sampled_count' output/phase_5_human_sampled.json

# Distribution check
jq '.distribution_check' output/phase_5_human_sampled.json

# Verify reproducibility
# Run again and check if sampled_fixture_ids matches
```

### Next Task
→ TASK 6: Phase 6 Implementation - Database Creation

---

## TASK 6: Phase 6 Implementation - Database Creation & Schema

**Status:** Not Started  
**Estimated Time:** 3-4 hours  
**Dependencies:** TASK 5  
**Blocker Risk:** MEDIUM (database integrity)

### Objective
Create two new SQLite databases with filtered data: fixturedb-human.db and fixturedb-llm.db.

### Input
- **File 1:** `/home/joao/icsme-nier-2026/output/phase_5_human_sampled.json` (from TASK 5)
  - Human sampled fixture IDs (87,432)
- **File 2:** `/home/joao/icsme-nier-2026/output/phase_3_llm_fixtures_extracted.json` (from TASK 3)
  - LLM fixtures with commit_sha and agent_type
- **Base:** `/home/joao/icsme-nier-2026/data/corpus.db` (template)

### Output
**Files:**
1. `/home/joao/icsme-nier-2026/data/fixturedb-human.db`
2. `/home/joao/icsme-nier-2026/data/fixturedb-llm.db`

**Validation Report:** `/home/joao/icsme-nier-2026/output/phase_6_database_validation.json`

```json
{
  "timestamp": "2026-05-13T23:30:00Z",
  "fixturedb_human": {
    "created": true,
    "file_size_mb": 45.3,
    "row_counts": {
      "repositories": 175,
      "test_files": 67892,
      "fixtures": 87432,
      "mocks": 12345
    },
    "schema_validation": "PASSED",
    "foreign_keys_integrity": "PASSED",
    "orphaned_rows": 0
  },
  "fixturedb_llm": {
    "created": true,
    "file_size_mb": 48.7,
    "row_counts": {
      "repositories": 145,
      "test_files": 78234,
      "fixtures": 87432,
      "mocks": 14567
    },
    "schema_validation": "PASSED",
    "llm_columns_present": [
      "commit_sha",
      "agent_type",
      "is_complete_addition",
      "commit_date"
    ],
    "foreign_keys_integrity": "PASSED",
    "orphaned_rows": 0,
    "llm_specific_checks": {
      "all_fixtures_have_commit_sha": true,
      "all_fixtures_have_agent_type": true,
      "all_are_completely_added": true,
      "agent_type_values_valid": true
    }
  },
  "comparison": {
    "fixture_count_match": true,
    "fixture_count_human": 87432,
    "fixture_count_llm": 87432,
    "schemas_compatible": true,
    "no_overlap": true
  }
}
```

### Implementation Steps
1. Write Python script `collection/phase_6_create_databases.py`
2. Functions:
   - `create_filtered_database(original_db, output_db, fixture_ids) -> None`
   - `validate_database_schema(db_path, is_llm) -> bool`
   - `validate_database_integrity(db_path) -> dict`
3. For fixturedb-human.db:
   - Copy schema from corpus.db
   - Delete fixtures NOT in sampled_fixture_ids
   - Cascade delete orphaned test_files and repos
   - Validate schema unchanged
4. For fixturedb-llm.db:
   - Copy schema from corpus.db
   - Add LLM columns: commit_sha, agent_type, is_complete_addition, commit_date
   - Insert LLM fixtures with all metadata
   - Validate new columns present
5. Run integrity checks on both
6. Output: Validation report JSON

### Success Criteria
- [ ] Script created and tested
- [ ] Both databases created successfully
- [ ] fixturedb-human.db has exactly 87,432 fixtures
- [ ] fixturedb-llm.db has exactly 87,432 fixtures
- [ ] Schema validation PASSED for both
- [ ] Foreign key integrity PASSED for both
- [ ] No orphaned rows in either database
- [ ] All LLM columns present in fixturedb-llm.db
- [ ] All LLM fixtures have commit_sha, agent_type, is_complete_addition
- [ ] Fixtures from both databases don't overlap (verified)
- [ ] Validation report shows all checks PASSED

### Verification Commands
```bash
# Check file sizes
ls -lh data/fixturedb-*.db

# Check fixture counts
sqlite3 data/fixturedb-human.db "SELECT COUNT(*) FROM fixtures;"
sqlite3 data/fixturedb-llm.db "SELECT COUNT(*) FROM fixtures;"

# Check LLM columns
sqlite3 data/fixturedb-llm.db "PRAGMA table_info(fixtures);"

# Validation report
jq '.' output/phase_6_database_validation.json
```

### Next Task
→ TASK 7: Phase 7 Implementation - Export & Documentation

---

## TASK 7: Phase 7 Implementation - Export & Documentation

**Status:** Not Started  
**Estimated Time:** 2-3 hours  
**Dependencies:** TASK 6  
**Blocker Risk:** LOW

### Objective
Export databases to CSVs and create publishable ZIP archives with documentation.

### Input
- `/home/joao/icsme-nier-2026/data/fixturedb-human.db` (from TASK 6)
- `/home/joao/icsme-nier-2026/data/fixturedb-llm.db` (from TASK 6)
- `/home/joao/icsme-nier-2026/output/phase_4_analysis.json` (for documentation)

### Output
**Files:**
1. `/home/joao/icsme-nier-2026/export/fixturedb-human_v1.0_20260513.zip`
   - fixturedb-human.db (complete standalone database)
   - repositories.csv (175 repos, self-contained)
   - test_files.csv (67,892 test files, self-contained)
   - fixtures.csv (87,432 fixtures, all columns)
   - mocks.csv (mock data for fixtures)
   - README.md (standalone documentation, usage guide)
   - SCHEMA.md (complete database schema reference)

2. `/home/joao/icsme-nier-2026/export/fixturedb-llm_v1.0_20260513.zip`
   - fixturedb-llm.db (complete standalone database)
   - repositories.csv (145 repos with agent info)
   - test_files.csv (78,234 test files, self-contained)
   - fixtures.csv (87,432 fixtures + agent columns)
   - mocks.csv (mock data for fixtures)
   - README.md (standalone documentation, agent info)
   - SCHEMA.md (database schema + LLM columns)
   - AGENTS.md (agent detection methodology & validation)

**Export Summary:** `/home/joao/icsme-nier-2026/output/phase_7_export_summary.json`

```json
{
  "timestamp": "2026-05-13T23:45:00Z",
  "fixturedb_human": {
    "zip_path": "export/fixturedb-human_v1.0_20260513.zip",
    "zip_size_mb": 82.3,
    "files_included": [
      "fixturedb-human.db",
      "repositories.csv",
      "test_files.csv",
      "fixtures.csv",
      "mocks.csv",
      "README.md",
      "SCHEMA.md"
    ],
    "csv_row_counts": {
      "repositories": 175,
      "test_files": 67892,
      "fixtures": 87432,
      "mocks": 12345
    },
    "standalone_verification": {
      "no_corpus_db_dependency": true,
      "no_llm_dataset_dependency": true,
      "all_tables_self_contained": true,
      "csv_columns_complete": true
    }
  },
  "fixturedb_llm": {
    "zip_path": "export/fixturedb-llm_v1.0_20260513.zip",
    "zip_size_mb": 85.7,
    "files_included": [
      "fixturedb-llm.db",
      "repositories.csv",
      "test_files.csv",
      "fixtures.csv",
      "mocks.csv",
      "README.md",
      "SCHEMA.md",
      "AGENTS.md"
    ],
    "csv_row_counts": {
      "repositories": 145,
      "test_files": 78234,
      "fixtures": 87432,
      "mocks": 14567
    },
    "llm_columns_in_csv": [
      "commit_sha",
      "agent_type",
      "is_complete_addition",
      "commit_date",
      "commit_author_name",
      "commit_author_email"
    ],
    "standalone_verification": {
      "no_corpus_db_dependency": true,
      "no_human_dataset_dependency": true,
      "all_tables_self_contained": true,
      "csv_columns_complete": true,
      "agent_columns_present": true
    }
  },
  "documentation": {
    "readme_human_generated": true,
    "readme_llm_generated": true,
    "schema_human_generated": true,
    "schema_llm_generated": true,
    "agents_doc_generated": true,
    "comparison_guide_generated": true
  }
}
```

### Implementation Steps
1. Write Python script `collection/phase_7_export_and_document.py`
2. Classes:
   - `HumanDatasetExporter` - Export fixturedb-human.db
   - `LLMDatasetExporter` - Export fixturedb-llm.db
3. Functions:
   - `export_database_to_csv(db_path, output_dir) -> dict`
   - `create_zip_archive(files, output_path) -> None`
   - `generate_readme_human(stats) -> str`
   - `generate_readme_llm(stats) -> str`
   - `generate_schema_doc(db_path, is_llm) -> str`
   - `generate_agents_methodology() -> str`
   - `generate_comparison_guide(human_stats, llm_stats) -> str`

4. For fixturedb-human.db:
   - Export all 4 tables to CSV
   - Include sampling metadata in fixtures.csv (SAMPLE_SOURCE, STRATIFICATION_TYPE)
   - Generate README.md with standalone usage instructions
   - Generate SCHEMA.md with complete table definitions
   - Verify all data is self-contained (no corpus.db references)

5. For fixturedb-llm.db:
   - Export all 4 tables to CSV
   - Include all LLM columns in fixtures.csv (commit_sha, agent_type, is_complete_addition, commit_date, author info)
   - Include agent context in repositories.csv (AGENTS_DETECTED, AGENT_COMMITS_COUNT)
   - Generate README.md with agent analysis instructions
   - Generate SCHEMA.md with LLM-extended schema
   - Generate AGENTS.md documenting detection methodology (from advisor's paper)
   - Verify all data is self-contained (no corpus.db references)

6. Create ZIP archives with all files
7. Generate comparison guide document (optional, in both ZIPs)
8. Output: Export summary JSON with standalone verification flags

### Success Criteria
- [ ] Script created and tested
- [ ] Both ZIP archives created successfully
- [ ] fixturedb-human ZIP contains: .db, 5 CSVs, 2 markdown docs
- [ ] fixturedb-llm ZIP contains: .db, 5 CSVs, 3 markdown docs
- [ ] CSV row counts match database row counts exactly
- [ ] All CSV columns present and complete (no truncation)
- [ ] fixturedb-human.csv includes SAMPLE_SOURCE, STRATIFICATION_TYPE columns
- [ ] fixturedb-llm.csv includes commit_sha, agent_type, is_complete_addition, commit_date
- [ ] Both README.md documents explain standalone usage clearly
- [ ] Both SCHEMA.md files document all columns with data types
- [ ] AGENTS.md documents advisor's paper methodology with citations
- [ ] Both datasets verified as independent (no cross-references)
- [ ] CSV files are UTF-8 encoded, properly escaped
- [ ] README files answer standalone usage FAQ
- [ ] Export summary JSON shows all verification flags = true
- [ ] Sample SQL queries in README work standalone

### Verification Commands
```bash
# Check ZIP contents
unzip -l export/fixturedb-human_v1.0_20260513.zip
unzip -l export/fixturedb-llm_v1.0_20260513.zip

# Verify file count in ZIPs
unzip -l export/fixturedb-human_v1.0_20260513.zip | wc -l  # Should be ~7 files
unzip -l export/fixturedb-llm_v1.0_20260513.zip | wc -l    # Should be ~8 files

# Check CSV row counts match database
sqlite3 data/fixturedb-human.db "SELECT COUNT(*) FROM fixtures;" | xargs -I {} sh -c 'wc -l export/*/fixtures.csv | grep human'
sqlite3 data/fixturedb-llm.db "SELECT COUNT(*) FROM fixtures;" | xargs -I {} sh -c 'wc -l export/*/fixtures.csv | grep llm'

# Verify CSV columns (should include agent columns in LLM)
head -1 export/fixturedb-llm_v1.0_20260513/fixtures.csv | tr ',' '\n' | grep -E "commit_sha|agent_type"

# Check README content
head -50 export/fixturedb-human_v1.0_20260513/README.md | grep -i "standalone\|independent"
head -50 export/fixturedb-llm_v1.0_20260513/README.md | grep -i "standalone\|independent"

# Verify standalone (no corpus.db mentioned in CSVs)
grep -i "corpus" export/fixturedb-human_v1.0_20260513/*.csv || echo "Clean: No corpus references"
grep -i "corpus" export/fixturedb-llm_v1.0_20260513/*.csv || echo "Clean: No corpus references"

# Export summary
jq '.' output/phase_7_export_summary.json
```

### Key Implementation Notes

**Standalone Design:**
- Each dataset is a complete, independent package
- Can be loaded and analyzed without the other
- No external dependencies (except system SQLite)
- All metadata included in ZIP

**Column Additions:**
- Human: SAMPLE_SOURCE (=sampled), STRATIFICATION_TYPE (=fixture_type)
- LLM: commit_sha, agent_type, is_complete_addition, commit_date, author info

**Documentation:**
- Both have README (usage guide + FAQ)
- Both have SCHEMA (table definitions)
- Only LLM has AGENTS (methodology)
- Optional comparison guide

### Next Task
→ TASK 8: Validation & Final Verification

---

## TASK 8: Validation & Final Verification

**Status:** Not Started  
**Estimated Time:** 1-2 hours  
**Dependencies:** TASK 7  
**Blocker Risk:** LOW

### Objective
Run comprehensive validation checks ensuring:
1. Data integrity and completeness
2. Reproducibility of all results
3. Research quality of datasets
4. **CRITICAL: Standalone independence of both datasets** (no inter-dependencies)

### Input
- Both databases: fixturedb-human.db, fixturedb-llm.db
- Both ZIP archives
- All intermediate JSON output files from TASKS 1-7
- Both extracted ZIPs to verify content

### Output
**Validation Report:** `/home/joao/icsme-nier-2026/output/FINAL_VALIDATION_REPORT.json`

```json
{
  "timestamp": "2026-05-13T23:50:00Z",
  "validation_status": "PASSED",
  "checks": {
    "fixture_counts": {
      "status": "PASSED",
      "human_count": 87432,
      "llm_count": 87432,
      "match": true
    },
    "no_overlap": {
      "status": "PASSED",
      "overlap_count": 0,
      "details": "Zero fixtures appear in both datasets"
    },
    "distribution_preservation": {
      "status": "PASSED",
      "human_pytest_ratio": 0.8127,
      "human_unittest_ratio": 0.1393,
      "tolerance_met": true
    },
    "schema_compatibility": {
      "status": "PASSED",
      "human_schema": "Matches corpus.db exactly",
      "llm_schema": "Extends corpus.db with 6 LLM columns"
    },
    "llm_metadata_completeness": {
      "status": "PASSED",
      "all_have_commit_sha": true,
      "all_have_agent_type": true,
      "all_have_is_complete_addition": true,
      "all_have_commit_date": true,
      "all_dates_valid": true
    },
    "reproducibility": {
      "status": "PASSED",
      "seed": 42,
      "rerun_produces_identical_results": true
    },
    "agent_detection_accuracy": {
      "status": "PASSED",
      "repos_with_agents": 1219,
      "total_commits": 48563,
      "within_expected_range": true
    },
    "export_completeness": {
      "status": "PASSED",
      "human_zip_valid": true,
      "llm_zip_valid": true,
      "all_files_present": true,
      "files_per_zip": {
        "human": 7,
        "llm": 8
      }
    },
    "standalone_independence": {
      "status": "PASSED",
      "human_db_independent": {
        "no_corpus_references": true,
        "no_llm_references": true,
        "all_tables_self_contained": true,
        "csv_columns_complete": true,
        "readme_explains_standalone": true
      },
      "llm_db_independent": {
        "no_corpus_references": true,
        "no_human_references": true,
        "all_tables_self_contained": true,
        "csv_columns_complete": true,
        "readme_explains_standalone": true,
        "agent_columns_present": true,
        "agent_methodology_documented": true
      }
    },
    "csv_validity": {
      "status": "PASSED",
      "human_csv_valid": true,
      "llm_csv_valid": true,
      "encoding": "UTF-8",
      "proper_escaping": true,
      "no_truncation": true
    },
    "documentation_completeness": {
      "status": "PASSED",
      "human_readme_present": true,
      "human_schema_present": true,
      "llm_readme_present": true,
      "llm_schema_present": true,
      "llm_agents_methodology_present": true,
      "sample_queries_present": true,
      "faq_answered": true
    },
    "tests_passing": {
      "status": "PASSED",
      "existing_tests": "388+ passing",
      "new_validation_tests": "All passing"
    }
  },
  "success_criteria_met": [
    "✓ Phase 1: Agent files identified in ~2,168 repos",
    "✓ Phase 1: Agent commits verified in ~1,219 repos",
    "✓ Phase 2: Pre-2021 fixtures extracted (240k+)",
    "✓ Phase 3: LLM fixtures extracted (87k+)",
    "✓ Phase 4: Distribution analysis complete",
    "✓ Phase 5: Stratified sampling complete",
    "✓ Phase 6: Databases created and validated",
    "✓ Phase 7: Exports complete and documented",
    "✓ No fixtures in both datasets",
    "✓ Reproducible sampling (seed=42)",
    "✓ All existing tests still passing",
    "✓ Both datasets are independently usable (NEW)",
    "✓ No inter-dataset dependencies (NEW)",
    "✓ CSV exports contain all necessary columns (NEW)",
    "✓ Standalone documentation complete (NEW)"
  ],
  "issues_found": [],
  "recommendations": [],
  "publication_ready": true
}
```

### Implementation Steps
1. Write Python script `collection/phase_8_final_validation.py`
2. Run validation checks:
   - **Data integrity:** Fixture counts, overlaps, distribution
   - **Reproducibility:** Seed=42 produces identical samples, agent commits verified
   - **Schema:** Both match expected, LLM has extended columns
   - **Metadata:** All LLM columns present and valid
   - **Export:** Both ZIPs created, all files present
   - **CSV validity:** UTF-8 encoding, proper escaping, complete columns
   - **Standalone independence (CRITICAL):**
     * Human: Can load and analyze without LLM dataset
     * LLM: Can load and analyze without human dataset
     * No references to corpus.db in either dataset
     * No cross-dataset dependencies
     * All metadata self-contained
     * README files explain standalone usage
     * SCHEMA files document all columns
     * AGENTS.md documents methodology (LLM only)
   - **Documentation:** All READMEs, SCHEMAs present and complete
   - **Tests:** All 388+ existing tests passing
3. Generate comprehensive report with publication readiness flag
4. Output: Validation report JSON with standalone verification flags

### Success Criteria
- [ ] All validation checks PASSED
- [ ] Validation report shows status = "PASSED"
- [ ] All success criteria met (15 checkboxes, including standalone)
- [ ] No issues found
- [ ] Report is clear and comprehensive
- [ ] publication_ready = true
- [ ] Standalone independence verified for both datasets:
  - [ ] Human dataset works independently (no LLM needed)
  - [ ] LLM dataset works independently (no human needed)
  - [ ] Both can be loaded simultaneously (for comparison)
  - [ ] No external dependencies beyond SQLite
  - [ ] README answers "Can I use this alone?" with YES
- [ ] CSV columns verified complete (no abbreviations):
  - [ ] Human: includes SAMPLE_SOURCE, STRATIFICATION_TYPE
  - [ ] LLM: includes commit_sha, agent_type, is_complete_addition, commit_date
- [ ] Documentation covers standalone usage:
  - [ ] Sample queries for independent analysis
  - [ ] FAQ for "Can I use without other dataset?"
  - [ ] How to load and verify data independently

### Verification Commands
```bash
# View validation report
jq '.' output/FINAL_VALIDATION_REPORT.json

# Check status
jq '.validation_status' output/FINAL_VALIDATION_REPORT.json

# Check standalone independence flags
jq '.checks.standalone_independence' output/FINAL_VALIDATION_REPORT.json

# Verify publication ready
jq '.publication_ready' output/FINAL_VALIDATION_REPORT.json

# Verify all success criteria
jq '.success_criteria_met' output/FINAL_VALIDATION_REPORT.json

# Test standalone loading (human)
sqlite3 export/fixturedb-human_v1.0_20260513/fixturedb-human.db "SELECT COUNT(*) FROM fixtures;" # Should work

# Test standalone loading (LLM)
sqlite3 export/fixturedb-llm_v1.0_20260513/fixturedb-llm.db "SELECT COUNT(*) FROM fixtures;" # Should work

# Test independent CSV queries (human)
head -5 export/fixturedb-human_v1.0_20260513/fixtures.csv | cut -d, -f1-3

# Test independent CSV queries (LLM)
head -5 export/fixturedb-llm_v1.0_20260513/fixtures.csv | cut -d, -f1-3 | paste - <(head -5 export/fixturedb-llm_v1.0_20260513/fixtures.csv | cut -d, -f$(grep -o 'commit_sha' export/fixturedb-llm_v1.0_20260513/fixtures.csv | head -1 | grep -bo 'commit_sha'))
```

### Critical Validation Focus

**Standalone Independence Checklist:**
```
For fixturedb-human.db:
 □ Can be opened without corpus.db
 □ All 4 tables present (repositories, test_files, fixtures, mocks)
 □ All required columns in CSVs (no abbreviations)
 □ README explains "Yes, use standalone"
 □ SCHEMA.md documents all columns
 □ Sample queries work with this DB alone
 □ Contains complete fixture content in csv
 □ Date ranges documented (pre-2021 era)

For fixturedb-llm.db:
 □ Can be opened without corpus.db
 □ All 4 tables present (repositories, test_files, fixtures, mocks)
 □ All LLM columns present (commit_sha, agent_type, is_complete_addition, commit_date)
 □ README explains "Yes, use standalone" + agent analysis
 □ SCHEMA.md documents all columns including LLM-specific
 □ AGENTS.md documents detection methodology
 □ Sample queries include agent analysis examples
 □ Each fixture traceable to commit_sha
 □ Agent types documented (claude/copilot/cursor/other)
 □ Date ranges documented (2022+ era)

Cross-dataset:
 □ No fixture IDs overlap between datasets
 □ Both have identical fixture counts (87,432)
 □ Distribution types match within 2% tolerance
 □ Can load both simultaneously for comparison
 □ No circular dependencies
```

### Next Steps After Validation

If PASSED:
- ✅ Datasets ready for publication
- ✅ Can share with other researchers
- ✅ Each researcher can choose which dataset(s) to use
- ✅ Both work independently or in combination

If issues found:
- Fix and re-run TASK 7
- Re-run TASK 8 validation
- Document issues and resolutions

---

## Summary of Tasks & Dependencies

```
TASK 1A: Phase 1A (Agent Files)
  ↓ (DEPENDS ON)
TASK 1B: Phase 1B (Agent Commits) ← GATING ITEM
  ↓
  ├─→ TASK 2: Phase 2 (Pre-2021 Fixtures)
  │     ↓
  │     └─→ TASK 5: Phase 5 (Stratified Sampling)
  │           ↓
  │           └─→ TASK 6: Phase 6 (Database Creation)
  │                 ↓
  │                 └─→ TASK 7: Phase 7 (Export)
  │                       ↓
  │                       └─→ TASK 8: Final Validation
  │
  └─→ TASK 3: Phase 3 (LLM Fixtures)
        ↓
        └─→ TASK 4: Phase 4 (Analysis)
              ↓
              └─→ TASK 5 (continues above)
```

### Execution Order (for sequential prompts)

| Order | Task | Duration | Can Parallelize |
|-------|------|----------|-----------------|
| 1 | TASK 1A | 2-3h | No |
| 2 | TASK 1B | 4-6h | No (depends on 1A) |
| 3a | TASK 2 | 2-3h | Yes (in parallel with 3) |
| 3b | TASK 3 | 6-8h | Yes (in parallel with 2) |
| 4 | TASK 4 | 1-2h | No (depends on 3) |
| 5 | TASK 5 | 2-3h | No (depends on 2, 4) |
| 6 | TASK 6 | 3-4h | No (depends on 5) |
| 7 | TASK 7 | 2-3h | No (depends on 6) |
| 8 | TASK 8 | 1-2h | No (depends on 7) |

**Total Sequential Time:** 24-34 hours  
**Optimal Parallel Time:** ~18-22 hours (TASK 2 & 3 in parallel)

---

## How to Use This Document

**For each prompt/conversation:**
1. Pick next incomplete task from above
2. Review Input, Output, and Implementation Steps sections
3. Follow Success Criteria checklist
4. Use Verification Commands to confirm completion
5. Move to Next Task when complete

**Example conversation flow:**
- Prompt 1: "Implement TASK 1A: Phase 1A agent file scanning"
- Prompt 2: "Implement TASK 1B: Phase 1B agent commit verification"
- Prompt 3: "Implement TASK 2: Phase 2 pre-2021 extraction" (+ optionally TASK 3 in parallel conversation)
- etc.

Each task is self-contained and can be completed independently, provided dependencies are satisfied.
