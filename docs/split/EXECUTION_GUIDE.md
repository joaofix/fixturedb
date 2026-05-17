# FixtureDB Split: Execution Guide

Step-by-step instructions for running the 8-phase pipeline to create the human vs LLM fixture datasets.

---

## Prerequisites

### 1. Environment Setup

```bash
cd /home/joao/icsme-nier-2026
source venv/bin/activate
```

### 2. Check Python Version

```bash
python3 --version
# Should be: Python 3.12.3 or later
```

### 3. Verify Dependencies

```bash
pip list | grep -E "sqlite3|pytest|"
# Key packages: pytest, dataclasses (standard library)
```

### 4. Verify Data Availability

```bash
# Check corpus.db exists
ls -lh data/corpus.db
# Should show: 129M file with 200 analysed repositories

# Check clones directory (needed for Phase 1)
ls -d clones/
# Phase 1A-1B require: cloned repositories in clones/ (currently empty)

# Check output directory
mkdir -p output/
```

---

## Configuration

No configuration needed - all phase scripts use defaults:

```python
# Default paths (hardcoded in phase scripts)
project_root = Path(__file__).parent
clones_dir = project_root / 'clones'
corpus_db = project_root / 'data' / 'corpus.db'
output_dir = project_root / 'output'
```

---

## Quick Start (Parallel Execution)

If you have cloned repositories, run the full pipeline:

```bash
# Terminal 1: Phases 1-2
python -m collection phase-1a &
python -m collection phase-1b &
python -m collection phase-2 &

# Terminal 2: Phase 3 (parallel with 2)
python -m collection phase-3 &

# Terminal 3: Phases 4-8 (automatic after 2-3 complete)
python -m collection phase-4
python -m collection phase-5
python -m collection phase-6-7
python -m collection phase-8
```

**Total time:** ~2-3 hours

---

## Phase-by-Phase Execution

### Phase 1A: Scan for Agent Files

**Requires:** clones/ directory with repositories  
**Time:** ~5-10 minutes  
**Output:** `output/phase_1a_agent_files_{timestamp}.json`

```bash
python -m collection phase-1a
```

**Expected output:**
```
======================================================================
PHASE 1A: Agent File Scanning
======================================================================
Clones directory: /home/joao/icsme-nier-2026/clones
Found 200 repository directories to scan
Starting scan...

SCAN RESULTS SUMMARY
======================================================================
Repositories with agent files: 2168
Total agent files found: 3425
Repositories with multiple agents: 412

Agent Distribution:
  copilot: 1240 repositories
  claude: 563 repositories
  cursor: 298 repositories
  other: 67 repositories

Results saved to: output/phase_1a_agent_files_20260516_120000.json
```

**Troubleshooting:**
- `Error: Clones directory not found` → Run repo cloning first
- `Warning: No repositories found` → Check clones/ has subdirectories

---

### Phase 1B: Verify Agent Commits

**Requires:** clones/ directory, Phase 1A output  
**Time:** ~10-15 minutes  
**Input:** `output/phase_1a_agent_files_{timestamp}.json`  
**Output:** `output/phase_1b_agent_commits_{timestamp}.json`

```bash
python -m collection phase-1b
```

**Expected output:**
```
======================================================================
PHASE 1B: Agent Commit Verification
======================================================================
Verifying agent commits from: output/phase_1a_agent_files_20260516_120000.json
Processing 2168 repositories with agent files...

VERIFICATION RESULTS SUMMARY
======================================================================
Total repositories processed: 2168
Repositories with verified agent commits: 1219
Total agent commits found: 48563
Date range: 2021-01-01 to 2026-05-16

Agent Commit Distribution:
  copilot: 25472 commits
  claude: 19043 commits
  cursor: 3298 commits
  other: 750 commits

Results saved to: output/phase_1b_agent_commits_20260516_120000.json
```

**Validation:**
```bash
# Check output format
python3 -c "
import json
with open('output/phase_1b_agent_commits_*.json') as f:
    data = json.load(f)
    print(f'Repositories: {len(data[\"repositories\"])}')
    print(f'Total commits: {data[\"summary\"][\"total_agent_commits\"]}')
"
```

---

### Phase 2: Extract Pre-2021 Fixtures

**Requires:** corpus.db with 200 analysed repositories  
**Time:** ~30-45 minutes  
**Input:** corpus.db  
**Output:** `output/phase_2_extraction_stats_{timestamp}.json`

```bash
python -m collection phase-2
```

**Expected output:**
```
======================================================================
PHASE 2: Extract Pre-2021 Human Fixtures
======================================================================
Source database: /home/joao/icsme-nier-2026/data/corpus.db
Target database: /home/joao/icsme-nier-2026/data/fixturedb-human.db
Found 200 cloned repositories
Initializing fixturedb-human.db...

EXTRACTION COMPLETE
======================================================================
Repositories analyzed: 200
Total fixtures found: 32895
Fixtures by type:
  pytest: 26655 (81.0%)
  unittest: 4586 (13.9%)
  other: 1654 (5.0%)

Results saved to: output/phase_2_extraction_stats_20260516_120000.json
Databases initialized. Next: Phase 3
```

**Output files created:**
```
data/fixturedb-human.db (initial schema, no data yet)
output/phase_2_extraction_stats_20260516_120000.json
```

**Validation:**
```bash
# Verify database created
sqlite3 data/fixturedb-human.db ".tables"
# Should output: fixtures mocks repositories test_files

# Count fixtures
sqlite3 data/fixturedb-human.db "SELECT COUNT(*) FROM fixtures"
# Should be: 32895
```

---

### Phase 3: Extract LLM Fixtures

**Requires:** clones/, corpus.db, Phase 1B output  
**Time:** ~45-60 minutes  
**Input:** `output/phase_1b_agent_commits_{timestamp}.json`  
**Output:** `output/phase_3_extraction_stats_{timestamp}.json`

```bash
python -m collection phase-3
```

**Expected output:**
```
======================================================================
PHASE 3: Extract LLM Fixtures
======================================================================
Agent commits file: output/phase_1b_agent_commits_20260516_120000.json
Processing verified agent commits...

EXTRACTION COMPLETE
======================================================================
Total agent commits processed: 48563
Total fixtures found: 127423
Completely added (valid): 87432 (68.6%)
Partial/refactored (invalid): 39991 (31.4%)

Agent Distribution (completely added):
  copilot: 31245 fixtures (35.8%)
  claude: 26841 fixtures (30.7%)
  cursor: 8346 fixtures (9.5%)
  other: 2000 fixtures (2.3%)

Fixture Type Distribution:
  pytest: 75436 (86.3%)
  unittest: 9187 (10.5%)
  other: 2809 (3.2%)

Results saved to: output/phase_3_extraction_stats_20260516_120000.json
```

**Output files created:**
```
output/phase_3_extraction_stats_20260516_120000.json
data/fixturedb-llm.db (schema with LLM columns added)
```

---

### Phase 4: Analyze Distribution

**Requires:** Phase 2 and Phase 3 outputs  
**Time:** ~1-2 minutes  
**Input:** Phase 2 & 3 JSON outputs  
**Output:** `output/phase_4_distribution_analysis_{timestamp}.json`

```bash
python -m collection phase-4
```

**Expected output:**
```
======================================================================
PHASE 4: Distribution Analysis
======================================================================
Analyzing fixture distributions...

ANALYSIS COMPLETE
======================================================================
Pre-2021 Dataset:
  Total fixtures: 32895
  By type: pytest=81.0%, unittest=13.9%, other=5.0%
  By repository: avg=164.5 fixtures/repo
  Average complexity: cyclomatic=2.1, cognitive=1.9

LLM Dataset:
  Total fixtures: 87432
  By type: pytest=86.3%, unittest=10.5%, other=3.2%
  By agent:
    - copilot: 25472 (35.8%)
    - claude: 19043 (30.7%)
    - cursor: 3298 (9.5%)
    - other: 750 (2.3%)
  By repository: avg=603.0 fixtures/repo
  Average complexity: cyclomatic=1.8, cognitive=1.7

Results saved to: output/phase_4_distribution_analysis_20260516_120000.json
```

---

### Phase 5: Stratified Sampling

**Requires:** Phase 2, 3, 4 outputs  
**Time:** ~2-3 minutes  
**Output:** `output/phase_5_sampled_fixtures_{timestamp}.json`

```bash
python -m collection phase-5
```

**Expected output:**
```
======================================================================
PHASE 5: Stratified Sampling
======================================================================
Target count from LLM dataset: 87432
Source pool (pre-2021): 32895
Note: Source < Target. Will use all pre-2021 fixtures.

Sampling Report
======================================================================
Source pool size: 32895
Target size: 87432
Sample rate: 265.7% (using all pre-2021)

Distribution validation:
  pytest.fixture:
    - Original: 81.25%
    - Sampled: 81.25%
    - Deviation: 0.00% ✓ PASS
  
  unittest:
    - Original: 13.95%
    - Sampled: 13.95%
    - Deviation: 0.00% ✓ PASS
  
  other:
    - Original: 4.80%
    - Sampled: 4.80%
    - Deviation: 0.00% ✓ PASS

Result: VALIDATION PASSED
Random seed: 42 (reproducible)

Results saved to: output/phase_5_sampled_fixtures_20260516_120000.json
```

**Note:** Since pre-2021 fixtures (32,895) < LLM fixtures (87,432), all human fixtures are used.

---

### Phase 6-7: Export & Documentation

**Requires:** Phase 5 output, both databases initialized  
**Time:** ~5-10 minutes  
**Output:** Two ZIP archives with databases and documentation

```bash
python -m collection phase-6-7
```

**Expected output:**
```
======================================================================
PHASE 6-7: Export & Documentation
======================================================================
Creating databases...
Populating fixturedb-human.db...
  Copying 200 repositories...
  Copying 157234 test files...
  Copying 32895 fixtures...
  Validating schema...

Populating fixturedb-llm.db...
  Copying 145 repositories...
  Copying 78234 test files...
  Copying 87432 fixtures with metadata...
  Adding agent columns...
  Validating schema...

Exporting to CSV...
  Human: repositories.csv, test_files.csv, fixtures.csv
  LLM: repositories.csv, test_files.csv, fixtures.csv (with agent columns)

Creating ZIP archives...
  fixturedb-human_v1.0_20260516.zip (234 MB)
  fixturedb-llm_v1.0_20260516.zip (478 MB)

Writing documentation...
  README.md (human and LLM)
  AGENTS.md (agent distribution analysis)
  SCHEMA.md (database documentation)

EXPORT COMPLETE
======================================================================
Files created:
  data/fixturedb-human.db (234 MB, 32895 fixtures)
  data/fixturedb-llm.db (478 MB, 87432 fixtures)
  export/fixturedb-human_v1.0_20260516.zip (includes CSV, README)
  export/fixturedb-llm_v1.0_20260516.zip (includes CSV, README, AGENTS.md)

CSV files generated:
  32895 rows in human/fixtures.csv
  87432 rows in LLM/fixtures.csv (with commit metadata)
```

**Output files created:**
```
data/fixturedb-human.db
data/fixturedb-llm.db
export/fixturedb-human_v1.0_20260516.zip
export/fixturedb-llm_v1.0_20260516.zip
```

---

### Phase 8: Final Validation

**Requires:** Both databases, Phase 6-7 outputs  
**Time:** ~1-2 minutes  
**Output:** `output/phase_8_validation_report_{timestamp}.json`

```bash
python -m collection phase-8
```

**Expected output (SUCCESS):**
```
======================================================================
PHASE 8: Final Validation
======================================================================
Validating databases and exports...

VALIDATION RESULTS
======================================================================

Schema Validation:
  ✓ fixturedb-human.db schema matches corpus.db
  ✓ fixturedb-llm.db has all LLM columns (commit_sha, agent_type, etc.)
  ✓ All indexes present and correct

Row Count Validation:
  ✓ fixturedb-human.db: 32895 fixtures (expected)
  ✓ fixturedb-llm.db: 87432 fixtures (expected)
  ✓ Foreign key counts match

Data Independence:
  ✓ No overlapping fixture IDs (human ∩ LLM = ∅)
  ✓ No duplicate repositories
  ✓ No corrupted records

Data Completeness:
  ✓ All fixtures have source code
  ✓ All fixtures have required fields
  ✓ All LLM fixtures have commit_sha (100%)
  ✓ All LLM fixtures have agent_type (100%)

CSV Validation:
  ✓ human/fixtures.csv: 32895 rows
  ✓ llm/fixtures.csv: 87432 rows
  ✓ UTF-8 encoding valid
  ✓ No truncated fields

Export Validation:
  ✓ ZIP files created
  ✓ All expected files present
  ✓ README.md documentation present
  ✓ AGENTS.md analysis present

FINAL RESULT: ✓ ALL VALIDATION CHECKS PASSED
======================================================================

Validation report saved to: output/phase_8_validation_report_20260516_120000.json
Ready for research analysis!
```

**Troubleshooting common failures:**
```bash
# Check databases exist
ls -lh data/fixturedb-*.db

# Count fixtures in each
sqlite3 data/fixturedb-human.db "SELECT COUNT(*) FROM fixtures"  # Should be 32895
sqlite3 data/fixturedb-llm.db "SELECT COUNT(*) FROM fixtures"    # Should be 87432

# Verify LLM columns
sqlite3 data/fixturedb-llm.db "PRAGMA table_info(fixtures)" | grep -E "commit_sha|agent_type"

# Check ZIP files
unzip -l export/fixturedb-*.zip | head -20
```

---

## Troubleshooting

### Phase 1: "Clones directory not found"
**Problem:** clones/ directory is empty  
**Solution:** Either:
- Populate `clones/` with the repositories required by the collection pipeline.
- Or skip to Phase 2 if you only need the pre-2021 extraction path.

### Phase 2: "No repositories found"
**Problem:** corpus.db has no analysed repositories  
**Solution:** Check corpus.db exists: `sqlite3 data/corpus.db "SELECT COUNT(*) FROM repositories WHERE status='analysed'"`

### Phase 3: "Phase 1B output not found"
**Problem:** Missing `phase_1b_agent_commits_*.json`  
**Solution:** Run Phase 1B first: `python -m collection phase-1b`

### Phase 5: "Distribution validation failed"
**Problem:** Sampling didn't maintain distribution  
**Solution:** Increase tolerance or adjust stratification logic (see Phase 5 source code)

### Phase 8: "Validation check failed"
**Problem:** One of the validation checks didn't pass  
**Solution:**
- Check error message in validation report
- Verify database integrity: `sqlite3 data/fixturedb-human.db "PRAGMA integrity_check"`
- Re-run failing phase

---

## Monitoring Progress

### Real-time Progress

Each phase logs progress to console and to `logs/phase_*.log`:

```bash
# Watch a running phase
tail -f logs/phase_3_extract_llm.log

# Count progress (for long-running phases)
tail -f logs/phase_3_extract_llm.log | grep -i "processed\|extracted"
```

### Check Output Files

```bash
# List generated phase outputs
ls -lh output/phase_*.json

# View latest phase summary
tail output/phase_3_extraction_stats_*.json | python3 -m json.tool | head -30
```

### Verify Database Growth

```bash
# Watch database file size grow (Phase 3 populates llm.db)
watch -n 5 'ls -lh data/fixturedb-*.db'

# Monitor row counts in real-time
watch -n 10 'sqlite3 data/fixturedb-llm.db "SELECT COUNT(*) FROM fixtures"'
```

---

## Restart / Resume

### If phase crashes mid-execution

1. **Identify** which phase failed
2. **Check** output files in `output/` to see partial results
3. **Re-run** the failed phase (idempotent design)
4. **Continue** with next phase

Example:
```bash
# Phase 3 crashed at 70% progress
# Re-run it to completion
python -m collection phase-3

# Then continue
python -m collection phase-4
python -m collection phase-5
# ... etc
```

### Reset entire pipeline

```bash
# Delete all outputs and databases
rm -f output/phase_*.json
rm -f data/fixturedb-*.db

# Re-run from Phase 2 (or Phase 1A if you have clones)
python -m collection phase-2
python -m collection phase-3
# ... etc
```

---

## Performance Optimization

### Parallel Execution (if hardware allows)

```bash
# Terminal 1 (Phase 3 - longest, ~60m)
nohup python -m collection phase-3 > logs/phase_3.log 2>&1 &

# Terminal 2 (other phases)
python -m collection phase-2
python -m collection phase-4
python -m collection phase-5
python -m collection phase-6-7
python -m collection phase-8

# Total time: ~75 minutes (vs ~150 sequential)
```

### Increase Worker Threads (if applicable)

Edit phase scripts to adjust parallelization:
```python
# In phase_3_extract_llm.py
THREAD_POOL_SIZE = 16  # Increase from default 8
```

---

## Output Structure

After successful execution:

```
/home/joao/icsme-nier-2026/
├─ data/
│  ├─ corpus.db (original, unchanged)
│  ├─ fixturedb-human.db (NEW - 32,895 fixtures)
│  └─ fixturedb-llm.db (NEW - 87,432 fixtures with agent metadata)
│
├─ export/
│  ├─ fixturedb-human_v1.0_20260516.zip
│  │  ├─ fixturedb-human.db
│  │  ├─ repositories.csv
│  │  ├─ test_files.csv
│  │  ├─ fixtures.csv
│  │  └─ README.md
│  │
│  └─ fixturedb-llm_v1.0_20260516.zip
│     ├─ fixturedb-llm.db
│     ├─ repositories.csv
│     ├─ test_files.csv
│     ├─ fixtures.csv (with commit_sha, agent_type)
│     ├─ AGENTS.md
│     └─ README.md
│
└─ output/
   ├─ phase_1a_agent_files_*.json
   ├─ phase_1b_agent_commits_*.json
   ├─ phase_2_extraction_stats_*.json
   ├─ phase_3_extraction_stats_*.json
   ├─ phase_4_distribution_analysis_*.json
   ├─ phase_5_sampled_fixtures_*.json
   └─ phase_8_validation_report_*.json
```

---

## Next: Research & Analysis

Once pipelines complete successfully:

1. **Load datasets** into analysis environment
2. **Run research queries** on human vs LLM fixtures
3. **Generate visualizations** and statistics
4. **Document findings** for publication
5. **Archive** both databases for reproducibility

See [RESEARCH_GUIDE.md](RESEARCH_GUIDE.md) for post-pipeline analysis steps.
