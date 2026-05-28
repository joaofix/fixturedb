# Reproducing the Between-Group Study

The FixtureDB between-group dataset is reproducible via the collection pipeline from agent-enabled repositories discovered through GitHub search.

## Overview

The collection pipeline processes agent-enabled repositories to extract fixtures from both agent-authored and human-authored commits in the same temporal window. This provides paired observations within repositories for direct comparison.

**Key design principles:**
- Agent-enabled repos sourced from `github-search/` directory
- Single temporal window (post-2025) for both agent and human fixtures  
- Tier 1 detection only (co-authored-by trailers, author signatures)
- All repositories processed without per-language caps

## Collection Pipeline

### Stage 1: Prepare Agent-Enabled Repository List

The repository list comes from `github-search/` output (pre-computed GitHub API search results). These are repositories identified as containing agent config files.

```bash
# github-search/ contains:
# - repositories-source-*.csv: Agent-enabled repo metadata
# - agent-activity-*.csv: Agent commit indicators
```

### Stage 2: Collect Agent and Human Fixtures

```bash
python -m collection human_corpus --repo-qc-dir github-search --workers 8
python -m collection agent_corpus --repo-qc-dir github-search --workers 8
```

Both commands:
1. Read agent-enabled repositories from CSVs in `github-search/`
2. Filter by language (if specified) or include all
3. Clone and scan each repository
4. Extract fixtures from all commits (2025-01-01 onwards)
5. Classify commits as agent or human based on authorship signals
6. Persist fixtures to `data/between-group.db` with `commit_kind`
7. Generate summary JSON with statistics

### Output

**Database:**
- `data/between-group.db` — SQLite with fixtures from all repositories
- Schema: repositories, test_files, fixtures, test_commits, mock_usages

**Summaries:**
- `output/human_corpus_summary_*.json` — Human fixtures statistics
- `output/agent_corpus_summary_*.json` — Agent fixtures statistics
- Each includes: languages, domains, star tiers, fixture type distributions

## Commands

```bash
# Collect all agent-enabled repositories (no capping)
python -m collection human_corpus --repo-qc-dir github-search

# Specific language only
python -m collection agent_corpus --repo-qc-dir github-search --language python

# Parallel processing (default: 8 workers)
python -m collection human_corpus --repo-qc-dir github-search --workers 12

# Using custom output database
python -m collection agent_corpus --output-db data/custom.db
```

## Parameters

| Parameter | Human | Agent | Default | Meaning |
|-----------|-------|-------|---------|---------|
| `--repo-qc-dir` | Required | Required | — | Path to CSV repo list (github-search/) |
| `--language` | Optional | Optional | None | Limit to single language |
| `--workers` | Optional | Optional | 8 | Parallel clone/extract threads |
| `--output-db` | Optional | Optional | data/between-group.db | Output database path |

## Pipeline Stages

### Stage 1: Repository Selection
- Read `*_agent_repo.csv` files from `--repo-qc-dir`
- Filter by language if specified
- No per-language caps (all repos processed)
echo "Stage 3: Between-group comparison..."
python -m collection between-group-stats

# Check outputs
echo ""
echo "=== Collection Complete ==="
ls -lh output/*_summary_*.json output/between_group_comparison_*.json | tail -5
```

---

## Reproducing from a Frozen Corpus

To ensure reproducibility across runs, work from a frozen corpus.db:

```bash
# Verify corpus.db integrity
sqlite3 data/corpus.db "PRAGMA integrity_check;"

# Verify clones are available
ls clones/ | wc -l

# Run human collection (will use cached repos when available)
python -m collection human --repos-per-language 100
```

The between-group study is deterministic given:
1. **Fixed corpus.db** with pinned repository commits
2. **Fixed clone directory** with repository snapshots
3. **Deterministic fixture extraction** from tree-sitter AST analysis
4. **Conservative agent detection** (Tier 1 only: co-authored-by trailers)
5. **Fixed temporal boundaries** (2021-01-01 for human, 2025-01-01 for agent)

---

## Verification & Validation

### Verify the Summary Statistics

```python
import json

# Load human summary
with open("output/human_corpus_summary_*.json") as f:
    human = json.load(f)

print(f"Human corpus: {human['summary_statistics']['fixtures_collected']} fixtures")
print(f"  Repositories: {human['summary_statistics']['repos_passed_qc']}")
print(f"  Domain distribution: {human['control_variables']['domain_distribution']}")

# Load agent summary
with open("output/agent_corpus_summary_*.json") as f:
    agent = json.load(f)

print(f"\nAgent corpus: {agent['summary_statistics']['fixtures_collected']} fixtures")
print(f"  Agent types: {agent['agent_types']['distribution']}")
print(f"  Repositories: {agent['summary_statistics']['repos_passed_qc']}")

# Load comparison
with open("output/between_group_comparison_*.json") as f:
    comparison = json.load(f)

print(f"\nBalance tests:")
for test in comparison['balance_tests']:
    print(f"  {test['variable']}: p={test['p_value']:.4f} (balanced={test['is_balanced']})")
```

### Check Database Schema

```bash
# Inspect between-group.db schema
sqlite3 data/between-group.db ".tables"
sqlite3 data/between-group.db ".schema fixtures"

# Count fixtures by corpus
sqlite3 data/between-group.db "SELECT commit_kind, COUNT(*) FROM fixtures GROUP BY commit_kind;"

# Check control variables
sqlite3 data/between-group.db "SELECT COUNT(DISTINCT repo_id), COUNT(DISTINCT domain) FROM repositories;"
```

### Validate Temporal Separation

```python
import sqlite3
import pandas as pd

conn = sqlite3.connect("data/between-group.db")

# Human corpus: all commits before 2021-01-01
human_dates = pd.read_sql("""
    SELECT MIN(commit_sha), MAX(commit_sha) FROM fixtures WHERE commit_kind = 'human'
""", conn)

# Agent corpus: all commits after 2025-01-01
agent_dates = pd.read_sql("""
    SELECT MIN(commit_sha), MAX(commit_sha) FROM fixtures WHERE commit_kind = 'agent'
""", conn)

print("Human corpus temporal range:", human_dates)
print("Agent corpus temporal range:", agent_dates)
print("✓ Corpora are temporally separated" if agent_dates > human_dates else "✗ Warning: temporal overlap")
```

---

## Troubleshooting

### GitHub API Rate Limiting

If you hit rate limits during agent corpus collection:

```bash
# Use authenticated API with token
python -m collection agent --github-token YOUR_GITHUB_TOKEN

# Or set environment variable
export GITHUB_TOKEN=your_token_here
python -m collection agent
```

### Large Database Performance

If between-group.db becomes slow:

```bash
# Analyze and optimize indexes
sqlite3 data/between-group.db "VACUUM;"
sqlite3 data/between-group.db "ANALYZE;"

# Check index effectiveness
sqlite3 data/between-group.db "PRAGMA index_list(fixtures);"
```

### Verify Database Integrity

```bash
# Verify between-group.db is valid
sqlite3 data/between-group.db "PRAGMA integrity_check;"

# Count fixtures by commit_kind
sqlite3 data/between-group.db "SELECT commit_kind, COUNT(*) FROM fixtures GROUP BY commit_kind;"

# Verify both corpora are present
sqlite3 data/between-group.db "
  SELECT commit_kind, 
         COUNT(f.id) as fixture_count,
         COUNT(DISTINCT tf.repo_id) as repo_count,
         ROUND(100.0 * COUNT(f.id) / (SELECT COUNT(*) FROM fixtures), 1) as pct
  FROM fixtures f
  JOIN test_files tf ON f.test_file_id = tf.id
  GROUP BY f.commit_kind;
"
```

---

## Determinism & Reproducibility Guarantees

### Fully Deterministic Components

- **Agent detection**: Co-authored-by trailer parsing (Tier 1, 99%+ precision)
- **Fixture extraction**: Tree-sitter-based extraction (deterministic code analysis)
- **Control variable computation**: Snapshot-based calculation (deterministic)
- **Statistical tests**: Chi-square and Mann-Whitney U (deterministic aggregation)

### Conditional Determinism

- **Repository selection**: Depends on corpus.db and GitHub API results
- **Temporal boundaries**: Fixed at 2021-01-01 (human) and 2025-01-01 (agent)
- **Clone freshness**: Depends on git history at time of collection

**Guarantee**: If `data/corpus.db` and temporal boundaries are fixed, all between-group collections are reproducible.

---

## Comparing Results Across Runs

To compare two between-group runs:

```python
import json

# Load two human corpus summaries
with open("output/human_corpus_summary_20260517_143022.json") as f:
    human_summary1 = json.load(f)

with open("output/human_corpus_summary_20260517_150000.json") as f:
    human_summary2 = json.load(f)

# Compare key metrics
print("Human Corpus Comparison:")
print(f"Run 1 - Total fixtures: {human_summary1['summary']['total_fixtures']}")
print(f"Run 2 - Total fixtures: {human_summary2['summary']['total_fixtures']}")

# Load balance test results
with open("output/between_group_comparison_20260517_160000.json") as f:
    comparison = json.load(f)

# Check balance test results
print(f"\nBalance Tests (p-values):")
for test in comparison['balance_tests']:
    print(f"  {test['control']}: p={test['p_value']:.6f} ({'balanced' if test['p_value'] >= 0.05 else 'imbalanced'})")
```

---

## See Also

- [Database Schema](../architecture/database-schema.md) — Between-group database schema
- [Analyzing the Dataset](./usage.md) — Query examples and statistical analysis
- [Collection README](../../collection/README.md) — CLI documentation


## Limitations on Reproducibility

### GitHub-Dependent Issues
1. **Repository deletions:** If repos are deleted, Phase 1-3 cannot run
   - **Mitigation:** Use Zenodo deposit (archives the data state)
2. **Repository changes:** If repos are modified, Phase 1-3 gives different results
   - **Mitigation:** Clone at fixed commit (Phase 2 already does this)

### Determinism Issues
1. **SQLite write ordering:** May vary on different systems
   - **Mitigation:** Indexes ensure consistent query results
2. **Floating point precision:** Statistics may differ slightly
   - **Mitigation:** Minimal rounding - no significant impact

---

## See Also

- [Execution Guide](../split/EXECUTION_GUIDE.md) — How to run each phase
- [Database Schema](../architecture/database-schema.md) — Data structure reference
- [Agent Detection](../architecture/agent-detection.md) — Determinism of agent matching
- [Data Models](../split/DATA_MODELS.md) — Schema details
