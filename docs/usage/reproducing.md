# Reproducing the study

Run every step from the project root with `python -m collection`. Each verb
takes `--dataset {a,c}`. Use `--help` on any verb for its options.

For the full chain of commands with progress notifications, see
[internal-docs/RUN_COMMANDS.md](../../internal-docs/RUN_COMMANDS.md).

## Datasets

| Dataset | What it holds | Extraction step |
|---------|---------------|-----------------|
| A | Fixtures written by coding agents | `extract-fixtures --dataset a` |
| C | Fixtures written by humans before 2021 | `extract-fixtures --dataset c` |

Dataset A comes from repositories with an agent configuration file and at
least one agent commit after 2025-01-01.

Dataset C comes from repositories created from 2016 to 2020. Each repository is
checked out at its own commit on or before 2020-12-31. The commit is pinned, so
a rerun reads the same code.

## Steps

```bash
# Dataset A
python -m collection discover-repos      --dataset a
python -m collection discover-commits    --dataset a
python -m collection filter-test-commits --dataset a
python -m collection extract-fixtures    --dataset a

# Dataset C
python -m collection discover-repos   --dataset c
python -m collection extract-fixtures --dataset c

# Comparison and outputs
python -m collection analyze-distribution --dataset a --against c
python -m collection sample   --dataset a --target-count N
python -m collection sample   --dataset c
python -m collection export   --dataset a
python -m collection export   --dataset c
python -m collection validate --dataset a
python -m collection validate --dataset c
```

Before a full run, check the code path on a small sample:

```bash
python -m collection toy --dataset a --repos 5
python -m collection toy --dataset c --repos 5
```

The toy run writes to `toy-dataset/`, not to `datasets/` or `db/`.

## Outputs

| Output | Location |
|--------|----------|
| Stage CSVs (reviewable) | `datasets/a/`, `datasets/c/` |
| Databases | `db/a.db`, `db/c.db` |
| Export bundles | `export/a.zip`, `export/c.zip` |
| Sampling results | `output/sample_a.json`, `output/sample_c.json` |
| Collection summaries | `datasets/{a,c}/summary.yaml` |

The CSVs are the source of truth. The databases are built from them.

## Check the output

Count the fixtures in each database:

```bash
sqlite3 db/a.db "SELECT COUNT(*) FROM fixtures;"
sqlite3 db/c.db "SELECT COUNT(*) FROM fixtures;"
```

Dataset C has no commit date per fixture, because each repository is read once
at its snapshot. Check the time window on the repository creation dates instead.
Run this on `db/c.db`:

```sql
SELECT MIN(created_at), MAX(created_at) FROM repositories;
```

The dates should fall between `DATASET_C_MIN_CREATED_DATE` and
`HUMAN_CORPUS_CUTOFF_DATE` in `collection/config.py`.

## What must stay fixed

A reproduction matches the original when these inputs are the same:

- The `github-search-raw/` snapshot.
- The date constants in `collection/config.py`.
- The per-stage CSV outputs, if you start from a later stage.

Repositories can change or disappear on GitHub between runs. Dataset C pins the
commit it reads, so new commits do not affect it. Dataset A reads the current
history.

The detection code is deterministic: the same commit and the same code give the
same result.

## Maintenance

```bash
sqlite3 db/a.db "VACUUM; ANALYZE;"
sqlite3 db/a.db "PRAGMA integrity_check;"
sqlite3 db/c.db "PRAGMA integrity_check;"
```

## See also

- [Repository structure](../getting-started/repository-structure.md)
- [Database schema](../architecture/database-schema.md)
- [Analysing the datasets](analysis.md)
