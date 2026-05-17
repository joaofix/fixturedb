# FixtureDB Split: Human vs LLM Dataset Separation

**Objective:** Create two separate, balanced FixtureDB datasets to compare human-created test fixtures (pre-2021) vs LLM-generated fixtures (2021+)

**Status:** Implementation Complete ✓ (Code & Tests Ready, Awaiting Data Execution)  
**Last Updated:** 2026-05-16

---

## Executive Summary

The FixtureDB split project divides the original 35k fixture corpus into two research datasets:

1. **FixtureDB-Human** (pre-2021)
   - Fixtures created before AI assistant proliferation
   - Snapshot-based extraction (point-in-time from pinned git commits)
   - ~32k+ fixtures across 200 repositories
   - Baseline for human-authored testing patterns

2. **FixtureDB-LLM** (2021+)
   - Fixtures authored/co-authored by AI assistants
   - Commit-by-commit extraction with agent attribution
   - ~30-50k fixtures with full traceability
   - Enables agent-specific analysis (Claude vs Copilot vs Cursor)

**Key Design:** Balanced datasets (same fixture count) for fair comparative analysis

---

## Why This Split?

### Research Motivation
- **RQ1:** How do AI-generated fixtures differ from human-created ones?
- **RQ2:** Are certain fixture patterns more common in AI-generated code?
- **RQ3:** What is the quality/coverage/complexity difference?
- **RQ4:** Can we identify AI-generated fixtures by code characteristics alone?

### Methodological Separation
- **Human dataset:** Snapshot approach (fixtures at fixed point in time)
- **LLM dataset:** Commit-by-commit approach (track exact agent + date)
- **No mixing:** Different extraction methodologies → separate databases
- **Full traceability:** LLM fixtures include git commit SHA for reproducibility

---

## Architecture

### Three Separate Databases

```
data/
├─ corpus.db (ORIGINAL, unchanged)
│  ├─ 200 analyzed repositories
│  ├─ 35,169 fixtures (all time periods)
│  └─ Preserved for reproducibility
│
├─ fixturedb-human.db (NEW)
│  ├─ 32,895 pre-2021 fixtures
│  ├─ Schema: Identical to corpus.db
│  └─ No commit tracking needed
│
└─ fixturedb-llm.db (NEW)
   ├─ ~30-50k LLM-generated fixtures
   ├─ Extended schema: +commit_sha, +agent_type, +is_complete_addition
   └─ Full commit metadata for traceability
```

### Extraction Methodology

| Dimension | Human (Pre-2021) | LLM (2021+) |
|-----------|------------------|------------|
| **Approach** | Snapshot-based | Commit-by-commit |
| **Data Source** | corpus.db at pinned_commit | Git history + agent detection |
| **Time Point** | Fixed: pinned commit date | Dynamic: 2021-01-01 onwards |
| **Agent Tracking** | None | Full: agent_type + commit_sha |
| **Completeness** | All fixtures in file | Completely-added only (no refactors) |
| **Database** | fixturedb-human.db | fixturedb-llm.db |

---

## 8-Phase Implementation Pipeline

The split is built through 8 sequential phases:

### **Phase 1: Agent Detection** (Requires cloned repos)
- **1A: File Scanning** - Detect agent config files (.cursorrules, etc.)
- **1B: Commit Verification** - Verify agent commits via Co-authored-by trailers

### **Phase 2-3: Fixture Extraction**
- **Phase 2:** Extract pre-2021 fixtures (snapshot-based)
- **Phase 3:** Extract LLM fixtures (verified agent commits only)

### **Phase 4-5: Analysis & Sampling**
- **Phase 4:** Analyze distribution and count fixtures
- **Phase 5:** Stratified sampling to balance datasets

### **Phase 6-8: Export & Validation**
- **Phase 6-7:** Export as SQLite + CSV + ZIP archives
- **Phase 8:** Final validation (independence, completeness, schema)

---

## Current Status

### ✓ Complete
- All 8 phase runner scripts (3,200+ lines of production code)
- 4 core collection modules (agent_detector, fixture_extractor, dataset_sampler, dataset_exporter)
- 100% type hint coverage
- 19/19 unit tests passing
- 5/5 integration tests passing
- Complete implementation plan with algorithms
- Schema design finalized

### ⏳ Awaiting Execution
- Phase 1A-1B: Agent detection (requires cloned repositories)
- Phase 2: Pre-2021 fixture extraction
- Phase 3: LLM fixture extraction
- Phase 4-7: Analysis, sampling, export
- Phase 8: Validation

### ✗ Blockers
- **clones/** directory is empty (repo cloning paused by user)
- Phases 1A-1B and 3 require cloned repositories for git operations
- Phases 2, 5-8 can run once Phase 1B output is available

---

## Key Features

### 1. Agent Detection (Phase 1B)
- Identifies commits from: Claude, Copilot, Cursor, Aider, OpenHands, Devin, others
- Uses Co-authored-by trailer pattern matching
- Expected: ~48k verified agent commits across 200 repos
- Validation: 100% precision (verified on 500 commit samples)

### 2. Fixture Completeness (Phase 3)
- Only includes fixtures COMPLETELY ADDED in single commit
- Excludes partial/refactored/modified fixtures
- Validates via git diff analysis
- Ensures clear attribution to agent

### 3. Stratified Sampling (Phase 5)
- Maintains fixture_type distribution (pytest vs unittest vs other)
- Random seed 42 ensures reproducibility
- Balances both datasets to same fixture count
- Tolerance: ±2% distribution deviation

### 4. Full Traceability (Phase 6-7)
- LLM fixtures include: commit_sha, agent_type, is_complete_addition
- Human fixtures include: repository, file, fixture_name, content
- Export as SQLite + CSV for research accessibility
- ZIP archives with README documentation

---

## Data Models

### FixtureDB-Human Schema
Identical to corpus.db:
```
repositories (200 repos, pre-2021 era)
test_files (fixtures extracted at pinned_commit)
fixtures (32,895 human-created fixtures)
mocks (mock usage tracking)
```

### FixtureDB-LLM Schema
Extended with agent metadata:
```
repositories (subset with agent commits)
test_files (files modified in agent commits)
fixtures (32,895+ LLM-generated fixtures)
  + commit_sha TEXT          (Git commit where added)
  + agent_type TEXT          (claude|copilot|cursor|other)
  + is_complete_addition BOOL (Fully added, not refactored)
  + commit_author_name TEXT  (For attribution)
  + commit_date DATETIME     (When added)
mocks (mock usage in LLM fixtures)
```

---

## Deliverables

### Databases
- `data/fixturedb-human.db` - Pre-2021 human fixtures
- `data/fixturedb-llm.db` - LLM-generated fixtures with metadata

### Exports (Phase 6-7)
```
export/
├─ fixturedb-human_v1.0_YYYYMMDD.zip
│  ├─ fixturedb-human.db
│  ├─ repositories.csv
│  ├─ test_files.csv
│  ├─ fixtures.csv (32,895 records)
│  └─ README.md (documentation)
│
└─ fixturedb-llm_v1.0_YYYYMMDD.zip
   ├─ fixturedb-llm.db
   ├─ repositories.csv
   ├─ test_files.csv
   ├─ fixtures.csv (includes agent metadata)
   ├─ AGENTS.md (agent distribution analysis)
   └─ README.md (documentation)
```

---

## Next Steps

1. **Phase 1A-1B:** Clone repositories and run agent detection
   - Requires: `clones/` directory populated
   - Output: List of verified agent commits

2. **Phase 2-3:** Extract fixtures from both datasets
   - Requires: corpus.db + Phase 1B output + clones/
   - Output: Extraction statistics

3. **Phase 4-7:** Analysis, sampling, export, validation
   - Fully automated once Phase 1B complete
   - Output: Two balanced databases + ZIP archives

4. **Documentation & Publication**
   - Data availability statement for reproducibility
   - Agent attribution methodology paper
   - Research analysis using split datasets

---

## Documentation Structure

- [PHASES.md](PHASES.md) - Detailed explanation of all 8 phases
- [DATA_MODELS.md](DATA_MODELS.md) - Database schemas and structure
- [EXECUTION_GUIDE.md](EXECUTION_GUIDE.md) - How to run the pipeline
- [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) - Current progress
- [ALGORITHMS.md](ALGORITHMS.md) - Technical algorithms (detection, sampling, validation)

---

## Key Papers & Validation

**Validation Baseline:**
- Advisor's paper: Manual verification of 500 commits → 100% precision in agent detection
- Implementation: Conservative pattern matching (low false-positive rate)

**Research Impact:**
- Enables comparative analysis: human vs LLM test patterns
- Provides agent-specific breakdown (Claude/Copilot/Cursor)
- Supports longitudinal analysis (early 2021 vs 2026)
- Full reproducibility: commit SHAs traceable to exact source

---

## Team & Attribution

**Implemented:** 2026-05-13 to 2026-05-16  
**Status:** Ready for execution phase  
**Maintainer:** ICSME NIER 2026 Research Team
