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

Datasets A and B come from the same agent-enabled repos, scanned in the same temporal window (post-2025), giving paired within-repo observations. Dataset C comes from an independent set of repos created within a fixed window (`DATASET_C_MIN_CREATED_DATE` to `HUMAN_CORPUS_CUTOFF_DATE`, 2016–2020), each checked out at its own pinned pre-2021 commit — no domain sampling, no per-language cap. This bounds repo age at snapshot time instead of relying on a live popularity filter; see [internal-docs/methodology-improvements/dataset-c-repo-selection.md](../../internal-docs/methodology-improvements/dataset-c-repo-selection.md). Agent detection is Tier 1 only (co-authored-by trailers, author signatures).

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

## Reproducing from Frozen Inputs

`db/corpus.db` is **not** part of the default reproduction path — it's only
read by `discover-commits --tier2` (see [Database Schema § Database overview](../architecture/database-schema.md#database-overview)).
The default Tier 1 path for all three datasets reproduces from `github-search-raw/`
and each stage's own CSV output under `datasets/{a,b,c}/`, not from `corpus.db`.

```bash
# Verify clones are available
ls clones/ | wc -l

# Only relevant if a run used --tier2:
sqlite3 db/corpus.db "PRAGMA integrity_check;"
```

See Determinism & Reproducibility Guarantees below for exactly what has to stay fixed for a reproduction to match.

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

Dataset C has no per-fixture commit date (`fixtures.commit_sha` is an empty
string in `db/c.db` — it's a single-snapshot extraction, not a commit-by-commit
scan; see [Database Schema](../architecture/database-schema.md#fixtures)).
The temporal claim to validate instead is on `repositories.created_at`:

```python
import sqlite3

conn = sqlite3.connect("db/c.db")
cur = conn.execute("SELECT MIN(created_at), MAX(created_at) FROM repositories")
print("Dataset C repo creation-date range:", cur.fetchone())
# Expect DATASET_C_MIN_CREATED_DATE .. HUMAN_CORPUS_CUTOFF_DATE (collection/config.py)
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

### Fully deterministic components

Agent detection (co-authored-by trailer parsing, Tier 1), fixture extraction (tree-sitter-based, deterministic code analysis), control variable computation (snapshot-based calculation), and statistical tests (chi-square and Mann-Whitney U, deterministic aggregation).

### Conditional determinism

Repository selection depends on the `github-search-raw/` snapshot and each stage's own QC CSV outputs (plus `corpus.db`, only for a `--tier2` run). Temporal boundaries are fixed via `AGENT_CORPUS_START_DATE`/`HUMAN_CORPUS_CUTOFF_DATE` in `collection/config.py`. Clone freshness depends on git history at time of collection — Dataset C pins an explicit cutoff commit SHA to avoid this issue. Live GitHub state can change between runs (repos going private or being deleted) — see [Limitations § Repository Availability](../reference/limitations.md#repository-availability).

Guarantee: if the `github-search-raw/` snapshot, the QC CSV inputs, and the temporal boundaries are fixed, all three datasets are reproducible.

## See Also

- [Database Schema](../architecture/database-schema.md) — Database schema
- [Collection Architecture](../architecture/collection.md) — Dataset A/B/C build map and module layout
- [Analyzing the Dataset](./usage.md) — Query examples and statistical analysis
