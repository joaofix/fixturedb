# Exports and storage

## Export bundles

`python -m collection export --dataset a` writes `export/a.zip`. Dataset C is
`export/c.zip`. Each bundle is self-contained. Nothing else is needed to read it.

```
export/a.zip
├── repositories.csv   every repository linked to the sampled fixtures
├── test_files.csv     every test file linked to the sampled fixtures
├── fixtures.csv       the sampled fixtures
├── mock_usages.csv    mocks inside the sampled fixtures
├── README.md          dataset description, generated at export
├── SCHEMA.md          column list
└── AGENTS.md          Dataset A only: agent detection summary
```

Each CSV is a direct dump of its database table. The columns are listed in
[Database schema](../architecture/database-schema.md).

The sample comes from `python -m collection sample`. See
[Manual validation](../usage/validation-sampling.md). There is no combined export
for both datasets. Use two bundles and join them yourself.

## Opening the CSVs

| Tool | How |
|------|-----|
| pandas | `pd.read_csv("fixtures.csv")` |
| R | `read.csv("fixtures.csv")` |
| DuckDB | `SELECT * FROM read_csv_auto('fixtures.csv')` |
| Spreadsheet | Open `fixtures.csv` |

Use the SQLite database (`db/a.db`, `db/c.db`) for joins across tables and for
the full source text of fixtures. Use the CSVs for descriptive statistics.

## What to keep on disk

| Path | Keep after a run? |
|------|-------------------|
| `db/a.db`, `db/c.db` | Yes. Needed for `sample`, `export` and `validate`. |
| `datasets/` | Yes. These are the reviewable stage outputs. |
| `export/` | Yes. |
| `clones/` | No. This is the largest folder. Delete it after a run. |
| `toy-dataset/` | No. Toy output. |

The databases use SQLite in WAL mode. This lets several workers read while one
writes. Check it with `PRAGMA journal_mode;`. The answer should be `wal`.

## Backups

```bash
cp db/a.db db/a.db.backup
sqlite3 db/a.db "PRAGMA integrity_check;"   # should print ok
```

Make a backup before any operation that deletes rows.
