# Reproducing the Study

The FixtureDB datasets are reproducible via the unified `python -m collection`
CLI, run from agent-enabled repositories discovered through GitHub search.
Every verb takes `--dataset {a,b,c}` and resolves its default input/output
directories through `collection/paths.py` — CSVs under `datasets/{a,b,c}/`
are the real, reviewable output; the per-dataset SQLite DBs under `db/` are
secondary/derived.

## Overview

The pipeline builds three datasets from agent-enabled repositories:

| Dataset | What it is | `extract-fixtures` collector |
|---|---|---|
| A | Agent-authored fixtures | `agent_corpus.AgentCorpusCollector` |
| B | Human-authored fixtures, within-repo matched control (same repos and 2025+ window as Dataset A) | `human_corpus.HumanCorpusCollector.run()` |
| C | Human-authored fixtures, cross-repo pre-2021 baseline (independent repo set) | `dataset_c.collect_dataset_c_fixtures()` |

**Key design principles:**
- Datasets A and B come from the same agent-enabled repos, scanned in the same temporal window (post-2025), giving paired within-repo observations.
- Dataset C comes from an independent set of repos created within a fixed window (`DATASET_C_MIN_CREATED_DATE` to `HUMAN_CORPUS_CUTOFF_DATE`, 2016–2020), each checked out at its own pinned pre-2021 commit — no domain sampling, no per-language cap. Bounds repo age at snapshot time instead of relying on a live popularity filter; see [internal-docs/methodology-improvements/dataset-c-repo-selection.md](../../internal-docs/methodology-improvements/dataset-c-repo-selection.md).
- Tier 1 agent detection only (co-authored-by trailers, author signatures).

## Collection Pipeline

Run each verb from the project root, one dataset at a time:

```bash
# Dataset A: discover repos, scan for agent commits, filter to test-touching commits, extract
python -m collection discover-repos      --dataset a
python -m collection discover-commits    --dataset a [--tier2]   # --tier2 only if Tier 1 yield is insufficient
python -m collection filter-test-commits --dataset a
python -m collection extract-fixtures    --dataset a

# Dataset B: resolve repo list from Dataset A, filter test commits, extract
python -m collection discover-repos      --dataset b
python -m collection filter-test-commits --dataset b
python -m collection extract-fixtures    --dataset b

# Dataset C: select repos in the fixed creation-date window, extract at the pinned cutoff commit
python -m collection discover-repos   --dataset c
python -m collection extract-fixtures --dataset c

# Cross-cutting: balance, sample, export, validate -- one dataset at a time
python -m collection analyze-distribution --dataset a --against b
python -m collection sample    --dataset a --target-count N
python -m collection sample    --dataset b --target-count N
python -m collection sample    --dataset c
python -m collection export    --dataset a
python -m collection export    --dataset b
python -m collection export    --dataset c
python -m collection validate  --dataset a
python -m collection validate  --dataset b
python -m collection validate  --dataset c
```

`--help` on any verb lists its full argument set (`--language`,
`--repos-per-language`, `--workers`, `--output-db`, etc.). Before a full
collection run, use `python -m collection toy --dataset {a,b,c} --repos N`
to smoke-test the same code path end-to-end at small scale, entirely under
`toy-dataset/` (never touches `datasets/`/`db/`).

### Output

**Databases:**
- `db/a.db` — Dataset A fixtures
- `db/b.db` — Dataset B fixtures
- `db/c.db` — Dataset C fixtures
- Schema: `repositories`, `test_files`, `fixtures`, `mock_usages` (see [Database Schema](../architecture/database-schema.md))

**CSV exports (the primary, reviewable output):**
- `datasets/a/{repos,commits,test-commits,fixtures}/`
- `datasets/b/{repos,test-commits,fixtures}/`
- `datasets/c/{repos,fixtures}/`

**Final export ZIPs:**
- `export/a.zip`, `export/b.zip`, `export/c.zip` — one standalone, independently-usable archive per dataset

**Statistics:**
- `output/sample_{a,b,c}.json` — per-dataset stratified-sampling results
- `output/*_corpus_summary_*.json` — extraction run summaries

## Reproducing from a Frozen Corpus

To ensure reproducibility across runs, work from a frozen `corpus.db`:

```bash
# Verify corpus.db integrity
sqlite3 db/corpus.db "PRAGMA integrity_check;"

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
sqlite3 db/a.db ".tables"
sqlite3 db/a.db ".schema fixtures"

# Count Dataset A fixtures
sqlite3 db/a.db "SELECT COUNT(*) FROM fixtures;"

# Count Dataset B fixtures and Dataset C fixtures separately (each has its own DB)
sqlite3 db/b.db "SELECT COUNT(*) FROM fixtures;"
sqlite3 db/c.db "SELECT COUNT(*) FROM fixtures;"
```

### Validate Temporal Separation

```python
import sqlite3

conn = sqlite3.connect("db/c.db")
cur = conn.execute("SELECT commit_date FROM fixtures ORDER BY commit_date DESC LIMIT 1")
print("Most recent Dataset C fixture commit date:", cur.fetchone())
```

## Troubleshooting

### GitHub API Rate Limiting

Most verbs read from pre-computed QC CSVs and generally don't need a
GitHub token. If a step you're running does hit rate limits, set
`GITHUB_TOKEN` in the environment before running it.

### Large Database Performance

```bash
sqlite3 db/b.db "VACUUM;"
sqlite3 db/b.db "ANALYZE;"
```

### Verify Database Integrity

```bash
sqlite3 db/b.db "PRAGMA integrity_check;"
sqlite3 db/a.db "PRAGMA integrity_check;"
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

**Guarantee**: If `db/corpus.db`, the QC CSV inputs, and the temporal boundaries are fixed, all three datasets are reproducible.

## See Also

- [Database Schema](../architecture/database-schema.md) — Database schema
- [Collection Architecture](../architecture/collection.md) — Dataset A/B/C build map and module layout
- [Analyzing the Dataset](./usage.md) — Query examples and statistical analysis
