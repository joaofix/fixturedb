# FixtureDB Split: 8-Phase Pipeline

Detailed explanation of each phase in the human vs LLM fixture extraction pipeline.

---

## Phase 1A: Agent File Scanning

**Purpose:** Detect repositories that likely used AI assistants during development

**Input:** clones/ directory with 200 git repositories  
**Output:** JSON file with agent file detection results

### Algorithm

1. **Iterate** each repository directory in clones/
2. **Scan** file system for agent config patterns:
   - Claude: `.cursorrules`, `.claudeignore`, `.claude/`, `claude.config`
   - Cursor: `.cursor`, `.cursorrules`, `CURSOR.md`
   - Copilot: `copilot_instructions.md`, `.copilot/*.md`, `.copilotignore`
   - Others: Aider, OpenHands, Devin, Jules, Cline, Junie, Gemini

3. **Record** which agents found and file names
4. **Output** statistics and per-repo results

### Performance
- Time: ~5-10 minutes (200 repos)
- Expected: ~2,168 repos with agent files
- Pattern matching: O(1) per repo (constant-time file checks)

### Implementation
- **Module:** `collection/agent_detector.py` (AgentFileScanner class)
- **Runner:** `phase_1a_scan_agent_files.py`
- **Output:** `output/phase_1a_agent_files_{timestamp}.json`

### Example Output
```json
{
  "timestamp": "2026-05-16T12:00:00",
  "summary": {
    "total_repositories_with_agents": 2168,
    "total_agent_files_found": 3425,
    "repositories_with_multiple_agents": 412,
    "agent_counts": {
      "copilot": 1240,
      "claude": 563,
      "cursor": 298,
      "other": 67
    }
  },
  "repositories": {
    "torvalds__linux": {
      "agents_found": ["copilot", "claude"],
      "total_files": 4
    }
  }
}
```

---

## Phase 1B: Agent Commit Verification

**Purpose:** Verify agent involvement by parsing commit messages

**Input:** Repositories with agent files (from Phase 1A), git history  
**Output:** JSON mapping verified agent commits with agent types

### Algorithm

1. **For each** repository from Phase 1A:
   - Run: `git log --all --format=... {repo_path}`
   - Extract: commit SHA, author name, author email, commit message

2. **For each** commit in history:
   - Search commit message for Co-authored-by trailers
   - Parse: `Co-authored-by: {agent_name} <{agent_email}>`
   - Variations: Case-insensitive, different email formats

3. **Match** agent patterns in:
   - Author name (e.g., "Claude", "Copilot")
   - Author email (e.g., `claude@anthropic.com`, `copilot@github.com`)
   - Commit message body (e.g., "written with Claude")

4. **Assign** agent_type: `claude`, `copilot`, `cursor`, `other`

5. **Filter** by date: Keep only commits >= 2021-01-01

6. **Record** mapping: `{commit_sha → agent_type}`

### Performance
- Time: ~10-15 minutes (1,219 verified repos)
- Expected results: ~48,563 agent commits
- Parallelizable: Process repos in parallel batches
- Pattern: Early exit on first agent match per commit

### Validation
- Baseline: Manual verification of 500 commits → 100% precision
- Conservative patterns: Low false-positive rate
- Only use commits with clear agent indicators

### Implementation
- **Module:** `collection/agent_detector.py` (AgentCommitVerifier class)
- **Runner:** `phase_1b_verify_agent_commits.py`
- **Input:** `output/phase_1a_agent_files_{timestamp}.json`
- **Output:** `output/phase_1b_agent_commits_{timestamp}.json`

### Example Output
```json
{
  "timestamp": "2026-05-16T12:15:00",
  "summary": {
    "total_agent_commits": 48563,
    "repositories_with_agent_commits": 1219,
    "date_range": "2021-01-01 to 2026-05-16",
    "agent_distribution": {
      "copilot": 25472,
      "claude": 19043,
      "cursor": 3298,
      "other": 750
    }
  },
  "repositories": {
    "torvalds__linux": {
      "agent_commits": {
        "a1b2c3d4e5f6...": "copilot",
        "b2c3d4e5f6a7...": "claude"
      }
    }
  }
}
```

---

## Phase 2: Pre-2021 Fixture Extraction

**Purpose:** Extract all fixtures before 2021 (human-created era)

**Input:** corpus.db, Phase 1B results (for repo list)  
**Output:** Pre-2021 fixture statistics + IDs

### Algorithm

1. **Identify** repositories with `status = 'analysed'` in corpus.db
   - All 200 analyzed repos have pre-2021 data

2. **For each** repository:
   - Get pinned_commit from corpus.db
   - Snapshot: Extract fixtures at that fixed commit point
   - No date filtering needed (all pinned commits are pre-2021)

3. **Collect** all fixtures:
   - Count by fixture_type (pytest, unittest, other)
   - Track repository, file, and fixture metadata
   - Keep content, complexity metrics, dependencies

4. **Output** statistics:
   - Total count: Expected ~32,895 (from corpus.db)
   - Distribution by type
   - Distribution by repository
   - Distribution by language

### Performance
- Time: ~30-45 minutes
- Reason: Reading fixtures from database (no git operations needed)
- Parallelizable: Process repositories independently

### Implementation
- **Module:** `collection/fixture_extractor.py` (Pre2021FixtureExtractor class)
- **Runner:** `phase_2_extract_pre_2021.py`
- **Output:** `output/phase_2_extraction_stats_{timestamp}.json`
- **Creates:** `data/fixturedb-human.db` (populated by Phase 6)

### Example Output
```json
{
  "timestamp": "2026-05-16T12:45:00",
  "summary": {
    "total_repositories": 200,
    "total_fixtures_found": 32895,
    "repositories_with_fixtures": 189,
    "fixture_type_distribution": {
      "pytest": 26655,
      "unittest": 4586,
      "other": 1654
    }
  },
  "repositories": {
    "torvalds__linux": {
      "fixtures_found": 142,
      "fixture_types": {
        "pytest": 118,
        "unittest": 24
      }
    }
  }
}
```

---

## Phase 3: LLM Fixture Extraction

**Purpose:** Extract fixtures added in verified agent commits (2021+)

**Input:** corpus.db, Phase 1B results (verified agent commits), clones/  
**Output:** LLM fixture statistics with agent metadata

### Algorithm

1. **For each** verified agent commit (from Phase 1B):
   - Parse commit date
  - Filter: Keep only commits >= 2021-01-01

2. **Get commit diff**:
   - Extract changed test files
   - Identify fixtures added (not modified)

3. **Validate completeness**:
   - Check: Fixture not in parent commit (new fixture)
   - Check: All lines in diff have + prefix (additions only)
   - Skip: Fixtures with modifications (- lines)

4. **Extract fixture data**:
   - Source code content
   - Name, type, scope
   - Complexity metrics
   - Dependencies on other fixtures

5. **Track agent metadata**:
   - commit_sha: Exact commit where added
   - agent_type: claude/copilot/cursor/other (from Phase 1B)
   - is_complete_addition: boolean (from validation)
   - commit_author_name, email, date

6. **Output** statistics:
   - Total count by agent type
   - Distribution by repository
   - Breakdown of complete vs partial/refactored fixtures
   - Distribution by fixture_type

### Performance
- Time: ~45-60 minutes
- Reason: Git operations (diff analysis, content extraction)
- Parallelizable: Process agent commits in parallel

### Implementation
- **Module:** `collection/fixture_extractor.py` (LLMFixtureExtractor class)
- **Runner:** `phase_3_extract_llm.py`
- **Input:** `output/phase_1b_agent_commits_{timestamp}.json`
- **Output:** `output/phase_3_extraction_stats_{timestamp}.json`
- **Creates:** `data/fixturedb-llm.db` (populated by Phase 6)

### Example Output
```json
{
  "timestamp": "2026-05-16T13:45:00",
  "summary": {
    "total_agent_commits_processed": 48563,
    "total_fixtures_found": 127423,
    "completely_added": 87432,
    "partial_or_refactored": 39991,
    "agent_distribution": {
      "copilot": {
        "fixtures": 45672,
        "completely_added": 31245
      },
      "claude": {
        "fixtures": 38567,
        "completely_added": 26841
      },
      "cursor": {
        "fixtures": 12108,
        "completely_added": 8346
      }
    },
    "fixture_type_distribution": {
      "pytest": 75436,
      "unittest": 9187,
      "other": 2809
    }
  }
}
```

---

## Phase 4: Distribution Analysis

**Purpose:** Analyze and compare fixture distributions

**Input:** Phase 2 and Phase 3 outputs  
**Output:** Distribution statistics and metrics

### Analysis Dimensions
- By fixture_type (pytest vs unittest vs other)
- By repository (fixtures per repo)
- By language (Python vs Java vs JavaScript vs TypeScript)
- By complexity (nesting depth, cyclomatic complexity, etc.)
- By agent type (Claude vs Copilot vs Cursor) - LLM only
- By time period (early 2021 vs 2026) - LLM only

### Performance
- Time: ~1-2 minutes
- Reason: Simple aggregations and statistical calculations
- No parallelization needed

### Implementation
- **Module:** `collection/dataset_sampler.py` (DistributionAnalyzer concept)
- **Runner:** `phase_4_analyze_distribution.py`
- **Input:** Phase 2 and Phase 3 JSON outputs
- **Output:** `output/phase_4_distribution_analysis_{timestamp}.json`

---

## Phase 5: Stratified Sampling

**Purpose:** Balance human and LLM datasets to same fixture count

**Input:** Phase 2, 3, 4 outputs  
**Output:** Sample of pre-2021 fixtures matching LLM count

### Algorithm

1. **Determine target count**:
   - Count from Phase 3: `n_llm_fixtures = 87,432`
   - This is the target for human sample

2. **Stratify** pre-2021 fixtures by fixture_type:
   - Group 1: pytest (81.25% of original)
   - Group 2: unittest (13.95% of original)
   - Group 3: other (4.80% of original)

3. **Calculate proportional counts**:
   - For each group: `count_for_type = target_count * (group_size / total_original)`
   - Example: pytest → 87,432 * 0.8125 = 71,038 fixtures

4. **Random sample** from each group:
   - Use: `random.sample(group, count_for_type)`
   - Seed: 42 (for reproducibility)

5. **Validate** distribution:
   - Check: Each stratum within ±2% of original proportion
   - If: Not within tolerance, raise error and log details
   - Adjust: Fine-tune sampling if needed

6. **Output** selected fixture IDs

### Performance
- Time: ~2-3 minutes
- Reason: Simple random sampling (O(n) complexity)
- No parallelization needed

### Implementation
- **Module:** `collection/dataset_sampler.py` (StratifiedSampler class)
- **Runner:** `phase_5_stratified_sample.py`
- **Input:** Phase 2, 3, 4 JSON outputs
- **Output:** `output/phase_5_sampled_fixtures_{timestamp}.json`

### Validation Output
```json
{
  "sampling_report": {
    "source_pool_size": 32895,
    "target_size": 87432,
    "sample_rate": "265.7% (target > source, using all pre-2021)",
    "distribution_validation": {
      "pytest": {
        "original": "81.25%",
        "sampled": "81.27%",
        "deviation": "0.02%",
        "status": "PASS"
      },
      "unittest": {
        "original": "13.95%",
        "sampled": "13.93%",
        "deviation": "-0.02%",
        "status": "PASS"
      },
      "other": {
        "original": "4.80%",
        "sampled": "4.80%",
        "deviation": "0.00%",
        "status": "PASS"
      }
    },
    "random_seed": 42,
    "result": "VALIDATION PASSED"
  }
}
```

---

## Phase 6-7: Export & Documentation

**Purpose:** Create standalone databases and export as CSV + ZIP

**Input:** corpus.db, Phase 2-5 outputs, fixture IDs  
**Output:** Two new databases + CSV files + ZIP archives

### Process

1. **Create fixturedb-human.db**:
   - Copy schema from corpus.db
   - Insert sampled fixtures (Phase 5 IDs)
   - Delete orphaned test_files, repositories
   - Validate schema and row counts

2. **Create fixturedb-llm.db**:
   - Copy schema from corpus.db
   - Add columns: commit_sha, agent_type, is_complete_addition, commit_date
   - Insert LLM fixtures (Phase 3)
   - Add agent metadata
   - Delete orphaned test_files, repositories

3. **Export to CSV**:
   - repositories.csv
   - test_files.csv
   - fixtures.csv (with agent columns for LLM)

4. **Create ZIP archives**:
   - Include .db, CSVs, README documentation
   - Separate for human and LLM
   - Add AGENTS.md for LLM distribution analysis

### Performance
- Time: ~5-10 minutes
- Reason: Database operations, CSV writing, ZIP compression
- Parallelizable: Create both databases independently

### Implementation
- **Module:** `collection/dataset_exporter.py` (HumanDatasetExporter, LLMDatasetExporter)
- **Runner:** `phase_6_7_export_and_document.py`
- **Output:**
  - `data/fixturedb-human.db`
  - `data/fixturedb-llm.db`
  - `export/fixturedb-human_v1.0_{date}.zip`
  - `export/fixturedb-llm_v1.0_{date}.zip`

---

## Phase 8: Final Validation

**Purpose:** Verify data independence, completeness, and schema correctness

**Input:** Both databases, CSV files  
**Output:** Validation report

### Checks

1. **Schema Validation**:
   - ✓ Exact column match with corpus.db
   - ✓ LLM-specific columns present (commit_sha, agent_type, etc.)
   - ✓ Data types correct
   - ✓ Indexes present

2. **Row Count Validation**:
   - ✓ Fixture counts match expectations
   - ✓ Test_files counts match fixtures
   - ✓ Repositories counts reasonable

3. **Data Independence**:
   - ✓ No fixture IDs overlap (human ∩ LLM = ∅)
   - ✓ No repository duplication
   - ✓ No corrupted records

4. **Data Completeness**:
   - ✓ All fixtures have content
   - ✓ All fixtures have required fields
   - ✓ All LLM fixtures have commit_sha
   - ✓ All LLM fixtures have agent_type

5. **CSV Validation**:
   - ✓ Row counts match databases
   - ✓ UTF-8 encoding valid
   - ✓ No truncated fields
   - ✓ Proper quote handling

6. **Export Validation**:
   - ✓ ZIP files created
   - ✓ All expected files present
   - ✓ README.md documentation present
   - ✓ AGENTS.md present for LLM

### Performance
- Time: ~1-2 minutes
- Reason: Read-only validation queries
- No parallelization needed

### Implementation
- **Module:** `collection.py` (validation functions)
- **Runner:** `phase_8_final_validation.py`
- **Output:** `output/phase_8_validation_report_{timestamp}.json`

### Success Criteria
All checks PASS → Ready for research analysis
Any check FAIL → Identify and fix issue, re-run phase

---

## Execution Sequence

```bash
# Phase 1: Agent detection (requires clones/)
python -m collection phase-1a              # ~5-10m
python -m collection phase-1b              # ~10-15m

# Phase 2-3: Fixture extraction
python -m collection phase-2               # ~30-45m
python -m collection phase-3               # ~45-60m

# Phase 4-5: Analysis and sampling
python -m collection phase-4               # ~1-2m
python -m collection phase-5               # ~2-3m

# Phase 6-8: Export and validation
python -m collection phase-6-7             # ~5-10m
python -m collection phase-8               # ~1-2m

# Total estimated time: ~2-3 hours
```

---

## Error Recovery

| Failure Mode | Recovery |
|--------------|----------|
| Phase 1B: Too few agent commits | Expand agent patterns, review false negatives |
| Phase 2: Too few pre-2021 fixtures | Extend pre-2021 date range |
| Phase 3: Too few LLM fixtures | Relax completeness validation |
| Phase 5: Distribution skewed | Adjust stratification tolerance |
| Phase 6: Schema mismatch | Verify corpus.db schema |
| Phase 8: Validation failed | Check data for corruption, re-run phase |

---

## Phase Interdependencies

```
Phase 1A → Phase 1B
           ↓
Phase 2 ←--┴-→ Phase 3
    ↓          ↓
    ↓          ↓
    └---→ Phase 4 ←---┘
           ↓
        Phase 5
           ↓
      Phase 6-7
           ↓
       Phase 8
```

**Linear sequence:** Phases must run in order (1→2→...→8)  
**Parallelization:** Phases 2 & 3 can run in parallel  
**Automation:** Phases 4-8 fully automated once earlier phases complete
