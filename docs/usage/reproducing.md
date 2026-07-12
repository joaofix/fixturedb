# Reproducing the Study

The FixtureDB datasets are reproducible via the numbered phase-script pipeline
in `collection/`, run from agent-enabled repositories discovered through
GitHub search.

## Overview

The pipeline builds three datasets from agent-enabled repositories:

| Dataset | What it is | Entry script | Collector / function |
|---|---|---|---|
| A | Agent-authored fixtures | `collection/phase_3_extract_agent.py` | `agent_corpus.AgentCorpusCollector` |
| B | Human-authored fixtures, within-repo matched control (same repos and 2025+ window as Dataset A) | `collection/phase_2_extract_human.py` | `human_corpus.HumanCorpusCollector.run()` |
| C | Human-authored fixtures, cross-repo pre-2021 baseline (independent repo set) | `collection/phase_2b_extract_dataset_c.py` | `dataset_c.collect_dataset_c_fixtures()` |

**Key design principles:**
- Datasets A and B come from the same agent-enabled repos, scanned in the same temporal window (post-2025), giving paired within-repo observations.
- Dataset C comes from an independent set of repos created within a fixed window (`DATASET_C_MIN_CREATED_DATE` to `HUMAN_CORPUS_CUTOFF_DATE`, 2016–2020), each checked out at its own pinned pre-2021 commit — no domain sampling, no per-language cap. Bounds repo age at snapshot time instead of relying on a live popularity filter; see [internal-docs/methodology-improvements/dataset-c-repo-selection.md](../../internal-docs/methodology-improvements/dataset-c-repo-selection.md).
- Tier 1 agent detection only (co-authored-by trailers, author signatures).

## Collection Pipeline

Run each phase as a module from the project root:

```bash
# Phase 1A-1D: discover agent-enabled repos, scan/verify agent commits, assess yield
python -m collection.phase_1a_scan_agent_commits
python -m collection.phase_1b_verify_agent_commits
python -m collection.phase_1c_assess_tier1_yield
python -m collection.phase_1d_discover_matched_repos   # only if Tier 1 yield is insufficient

# Phase 2 / 2B: Dataset B (within-repo) and Dataset C (cross-repo baseline)
python -m collection.phase_2_extract_human --repo-dir github-search-agent/agent_repositories
python -m collection.select_dataset_c_repos   # writes dataset_c_{lang}.csv, no sampling
python -m collection.phase_2b_extract_dataset_c

# Phase 3: Dataset A (agent-authored), same repos as Dataset B
python -m collection.phase_3_extract_agent --repo-dir github-search-agent/agent_repositories

# Phase 4-8: analysis, sampling, export, validation
python -m collection.phase_4_analyze_distribution
python -m collection.phase_5_stratified_sample
python -m collection.phase_6_7_export_and_document
python -m collection.phase_8_final_validation
```

Each phase script logs its own "Next steps" pointing at what to run next.
`--help` on any phase script lists its full argument set (`--language`,
`--repos-per-language`, `--workers`, `--output-db`, etc.).

### Output

**Databases:**
- `data/fixturedb-human.db` — Dataset B (`same-repo`) and Dataset C (`cross-repo`) fixtures
- `data/fixturedb-agent.db` — Dataset A fixtures
- Schema: `repositories`, `test_files`, `fixtures`, `mock_usages` (see [Database Schema](../architecture/database-schema.md))

**CSV exports:**
- `fixtures-from-agents/` — Dataset A, plus the `dataset_c_*.csv` repo lists (from `select_dataset_c_repos.py`) used by Phase 2B
- `fixtures-from-humans/same-repo/` — Dataset B
- `fixtures-from-humans/cross-repo/` — Dataset C

**Statistics:**
- `output/phase_2_extraction_stats_*.json`, `output/phase_2b_extraction_stats_*.json`, `output/phase_4_distribution_analysis_*.json`, etc. — one JSON summary per phase run

## Reproducing from a Frozen Corpus

To ensure reproducibility across runs, work from a frozen `corpus.db`:

```bash
# Verify corpus.db integrity
sqlite3 data/corpus.db "PRAGMA integrity_check;"

# Verify clones are available
ls clones/ | wc -l
```

The pipeline is deterministic given:
1. **Fixed `corpus.db`** with pinned repository metadata
2. **Fixed clone directory** with repository snapshots (Dataset C additionally pins a cutoff commit SHA per repo)
3. **Deterministic fixture extraction** from tree-sitter AST analysis
4. **Conservative agent detection** (Tier 1 only: co-authored-by trailers)
5. **Fixed temporal boundaries** (`AGENT_CORPUS_START_DATE` for Datasets A/B, `HUMAN_CORPUS_CUTOFF_DATE` for Dataset C — see `collection/config.py`)

## Verification & Validation

### Check Database Schema

```bash
sqlite3 data/fixturedb-agent.db ".tables"
sqlite3 data/fixturedb-agent.db ".schema fixtures"

# Count Dataset A fixtures
sqlite3 data/fixturedb-agent.db "SELECT COUNT(*) FROM fixtures;"

# Count Dataset B vs Dataset C fixtures (commit_kind distinguishes them)
sqlite3 data/fixturedb-human.db "SELECT commit_kind, COUNT(*) FROM fixtures GROUP BY commit_kind;"
```

### Validate Temporal Separation

```python
import sqlite3

conn = sqlite3.connect("data/fixturedb-human.db")
cur = conn.execute("SELECT commit_date FROM fixtures WHERE commit_kind = 'human' ORDER BY commit_date DESC LIMIT 1")
print("Most recent Dataset C fixture commit date:", cur.fetchone())
```

## Troubleshooting

### GitHub API Rate Limiting

The phase scripts read from pre-computed QC CSVs and generally don't need a
GitHub token. If a step you're running does hit rate limits, set
`GITHUB_TOKEN` in the environment before running it.

### Large Database Performance

```bash
sqlite3 data/fixturedb-human.db "VACUUM;"
sqlite3 data/fixturedb-human.db "ANALYZE;"
```

### Verify Database Integrity

```bash
sqlite3 data/fixturedb-human.db "PRAGMA integrity_check;"
sqlite3 data/fixturedb-agent.db "PRAGMA integrity_check;"
```

## Determinism & Reproducibility Guarantees

### Fully Deterministic Components

- **Agent detection**: Co-authored-by trailer parsing (Tier 1)
- **Fixture extraction**: Tree-sitter-based extraction (deterministic code analysis)
- **Control variable computation**: Snapshot-based calculation (deterministic)
- **Statistical tests**: Chi-square and Mann-Whitney U (deterministic aggregation)

### Conditional Determinism

- **Repository selection**: Depends on `corpus.db` and the QC CSV inputs
- **Temporal boundaries**: Fixed via `AGENT_CORPUS_START_DATE` / `HUMAN_CORPUS_CUTOFF_DATE` in `collection/config.py`
- **Clone freshness**: Depends on git history at time of collection; Dataset C pins an explicit cutoff commit SHA to avoid this issue

**Guarantee**: If `data/corpus.db`, the QC CSV inputs, and the temporal boundaries are fixed, all three datasets are reproducible.

## See Also

- [Database Schema](../architecture/database-schema.md) — Database schema
- [Collection Architecture](../architecture/collection.md) — Dataset A/B/C build map and module layout
- [Analyzing the Dataset](./usage.md) — Query examples and statistical analysis
