# Storage and Scale - FixtureDB Between-Group Database

Database size estimates and storage requirements for the between-group study.

## Database Size Estimates

The between-group study uses a **single unified database** (`between-group.db`) containing both human and agent corpora:

### Single Database: between-group.db

| Stage | Fixtures | Database Size | Notes |
|-------|----------|---------------|-------|
| After Stage 1 (human corpus) | ~3,500 | 50-80 MB | Pre-2021 repositories |
| After Stage 2 (agent corpus) | ~7,500-8,500 | 120-180 MB | 2025+ agent-authored commits |
| **Total** | **7,000-8,500** | **120-180 MB** | Single database, both corpora |

The between-group design collects **fewer fixtures per corpus** than the original paired study (to maintain statistical power for comparison), resulting in a smaller overall database than the original FixtureDB.

## Storage Requirements

### During Collection

| Phase | Peak Disk Space | Components | Notes |
|-------|-----------------|-----------|-------|
| Stage 1 (Human) | 100-150 MB | corpus.db (input) + between-group.db (output) | No repository cloning |
| Stage 2 (Agent) | 5-10 GB | clones/ (2,000+ repos) + between-group.db | Temporary during git operations |
| Final | 120-180 MB | between-group.db only | Compressed is ~60 MB |

### Permanent Storage

After collection completes:
- **between-group.db** — 120-180 MB (required for all analysis)
- **clones/** — Can be deleted if no further agent detection needed
- **output/*.json** — 2-5 MB total (statistics and comparison results)

### Archive Storage

For long-term storage / paper submission:
```bash
# Compressed database
tar -czf between-group.db.tar.gz data/between-group.db  # ~60 MB

# With metadata and outputs
tar -czf fixtutedb-between-group.tar.gz \
  data/between-group.db \
  output/*.json \
  docs/ \
  README.md
# Total: ~80-100 MB
```

## Database Structure

### Single Unified Schema

```
between-group.db
│
├── repositories (control variables)
│   ├── id INTEGER PRIMARY KEY
│   ├── full_name TEXT
│   ├── language TEXT  
│   ├── domain TEXT
│   ├── star_tier INTEGER
│   ├── created_at DATE
│   └── ... (metadata)
│
├── test_files (file-level metadata)
│   ├── id INTEGER PRIMARY KEY
│   ├── repo_id FOREIGN KEY
│   ├── path TEXT
│   ├── framework TEXT
│   └── ... (file details)
│
├── fixtures (CORE TABLE: human + agent)
│   ├── id INTEGER PRIMARY KEY
│   ├── test_file_id FOREIGN KEY
│   ├── commit_kind TEXT  ← NEW: 'human' or 'agent'
│   ├── agent_type TEXT   ← NEW: 'claude'|'copilot'|'cursor'|'aider'|NULL
│   ├── commit_sha TEXT   ← NEW: for traceability
│   ├── is_complete_addition INTEGER ← NEW: full fixture added
│   ├── fixture_type TEXT  (setUp, test_XXX, mock, etc.)
│   ├── lines_added INTEGER
│   ├── lines_deleted INTEGER
│   ├── framework TEXT
│   ├── mock_usage TEXT
│   └── ... (fixture details)
│
└── mock_usages (framework usage)
    ├── id INTEGER PRIMARY KEY
    ├── fixture_id FOREIGN KEY
    ├── framework TEXT
    └── count INTEGER
```

**Key Difference from Original:**
- Original FixtureDB: Single table with all fixtures
- Between-group design: Adds `commit_kind` and `agent_type` columns to distinguish corpora and agent types

## Control Variables at Collection Time

Both human and agent fixtures include **control variables computed at their temporal boundaries**:

### Human Corpus (snapshot: 2020-12-31)
```sql
SELECT 
  f.id,
  r.language,           -- Programming language
  r.domain,            -- Project domain
  r.star_tier,         -- GitHub stars tier
  (JULIANDAY('2020-12-31') - JULIANDAY(r.created_at)) / 365.25 as repo_age_years
FROM fixtures f
JOIN test_files tf ON f.test_file_id = tf.id
JOIN repositories r ON tf.repo_id = r.id
WHERE f.commit_kind = 'human'
```

### Agent Corpus (snapshot: 2025-01-01)
```sql
SELECT 
  f.id,
  r.language,
  r.domain,
  r.star_tier,
  (JULIANDAY('2025-01-01') - JULIANDAY(r.created_at)) / 365.25 as repo_age_years
FROM fixtures f
JOIN test_files tf ON f.test_file_id = tf.id
JOIN repositories r ON tf.repo_id = r.id
WHERE f.commit_kind = 'agent'
```

These control variables are **balanced across corpora** using statistical tests:
- **Chi-square test** for categorical variables (language, domain, star_tier)
- **Mann-Whitney U test** for continuous variable (repo_age_years)

Balance report generated after Stage 3 shows p-values for all controls.

## Indexes

Critical indexes for fast queries:

```sql
CREATE INDEX idx_fixtures_test_file ON fixtures(test_file_id);
CREATE INDEX idx_fixtures_commit_kind ON fixtures(commit_kind);  -- NEW
CREATE INDEX idx_fixtures_framework ON fixtures(framework);
CREATE INDEX idx_test_files_repo ON test_files(repo_id);
CREATE INDEX idx_repositories_language ON repositories(language);
CREATE INDEX idx_repositories_domain ON repositories(domain);
```

The `idx_fixtures_commit_kind` index is essential for fast corpus filtering (human vs agent).

## Query Performance

### Typical Analysis Queries

Time on between-group.db (120-180 MB):

| Query | Time | Result Size |
|-------|------|-------------|
| Count fixtures per commit_kind | <1 ms | 2 rows |
| Fixtures by language | <10 ms | 10-20 rows |
| Fixture type distribution (all corpora) | <50 ms | 50 rows |
| Filter by agent_type | <10 ms | 1,000-3,000 rows |
| Export 5,000 fixtures | <500 ms | 5,000 rows + mocks |
| Statistical comparison (chi-square) | <100 ms | P-value per test |

### Sample Query: Language Distribution

```sql
-- Human corpus
SELECT language, COUNT(*) as human_count
FROM fixtures f
JOIN test_files tf ON f.test_file_id = tf.id
JOIN repositories r ON tf.repo_id = r.id
WHERE f.commit_kind = 'human'
GROUP BY r.language
ORDER BY human_count DESC;

-- Agent corpus
SELECT language, COUNT(*) as agent_count
FROM fixtures f
JOIN test_files tf ON f.test_file_id = tf.id
JOIN repositories r ON tf.repo_id = r.id
WHERE f.commit_kind = 'agent'
GROUP BY r.language
ORDER BY agent_count DESC;
```

## CSV Export Sizes

If you export the dataset to CSV:

| File | Rows | Size | Notes |
|------|------|------|-------|
| fixtures.csv | 8,000 | 15-20 MB | All fixtures, both corpora |
| repositories.csv | 2,000 | 0.5-1 MB | Repository metadata |
| test_files.csv | 4,000 | 0.5-1 MB | File-level data |
| mock_usages.csv | 50,000+ | 5-8 MB | Mock framework usage counts |
| **Total** | - | **~25 MB** | Uncompressed |
| **Compressed** | - | **~8-10 MB** | gzip with -9 |

## Memory Requirements

### Running the Pipeline

| Stage | Memory Peak | Notes |
|-------|------------|-------|
| Stage 1 (Human) | 500 MB | In-memory processing, 3,500 fixtures |
| Stage 2 (Agent) | 1.5 GB | In-memory GitHub API results, git operations |
| Stage 3 (Comparison) | 300 MB | Statistical tests on summaries (not full data) |

Typical machine:
- **Minimum:** 2 GB RAM
- **Recommended:** 4+ GB RAM
- **Database operations:** SQLite uses OS page cache (automatically managed)

## File Locations

After running the full pipeline:

```
data/
├── corpus.db                      # Original (input, ~25 MB)
└── between-group.db               # Between-group results (output, ~120-180 MB)

output/
├── human_corpus_summary_*.json    # Stage 1 output (~0.5 MB)
├── agent_corpus_summary_*.json    # Stage 2 output (~0.5 MB)
└── between_group_comparison_*.json # Stage 3 output (~0.2 MB)

clones/                            # Git repositories (can delete after Stage 2)
├── pytest__pytest/
├── django__django/
└── ... (~5-10 GB during collection, temporary)
```

## Cleanup After Collection

To save disk space after collecting the dataset:

```bash
# Delete temporary clones (if no longer needed)
rm -rf clones/

# Keep only these essential files:
# - data/between-group.db (120-180 MB)
# - output/*.json (summary statistics)
# - docs/ (documentation)
# - README.md, LICENSE, etc.

# For archival, compress:
tar -czf fixtutedb-between-group-final.tar.gz \
  data/between-group.db \
  output/*.json \
  docs/ \
  README.md \
  LICENSE

# Size: ~60-80 MB
```

## Database Integrity

### Backups

```bash
# Create backup before processing
cp data/between-group.db data/between-group.db.backup

# Verify integrity
sqlite3 data/between-group.db "PRAGMA integrity_check;"  # Should return 'ok'
```

### WAL Mode

The database runs in WAL (Write-Ahead Logging) mode for better concurrency:

```bash
# Check current mode
sqlite3 data/between-group.db "PRAGMA journal_mode;"  # Should return 'wal'
```

## Scale Limitations

The current between-group study collects approximately 7,000-8,500 total fixtures (~120-180 MB database). This is designed for **robust statistical comparison** of human vs agent, not for maximum fixture volume.

If you want to scale to 20,000+ fixtures per corpus (original FixtureDB scale):
- Use original FixtureDB approach (not between-group design)
- Contact the maintainers for guidance

## Storage Optimization

### Compression Ratios

| Format | Size | Compression |
|--------|------|-------------|
| Raw .db | 150 MB | 1.0x |
| gzip -6 | 60 MB | 2.5x |
| gzip -9 | 55 MB | 2.7x |
| bzip2 | 50 MB | 3.0x |

For archival, recommend **gzip -9** (standard, widely compatible).
