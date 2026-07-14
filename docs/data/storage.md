# Storage and Scale

Storage layout and disk-usage drivers for the three-dataset collection pipeline
(Dataset A: agent fixtures, Dataset B: human within-repo control, Dataset C: human
cross-repo baseline — see
[Repository Structure](../getting-started/repository-structure.md)).

## Database layout

Each dataset writes to its own SQLite file under `db/`, not a single shared
database — see [Database Schema § Database overview](../architecture/database-schema.md#database-overview)
for what each file contains and why they're kept separate (Dataset C in particular
has no commit-level agent/human distinction to make, so folding it into a shared
`commit_kind` column the way A/B once were would misrepresent it).

```
db/
├── corpus.db   # pre-A/B/C paired-study corpus (only needed for --tier2 discovery)
├── a.db        # Dataset A
├── b.db        # Dataset B
└── c.db        # Dataset C
```

Relative size across the three is driven by fixture count, which in turn depends on
`--repos-per-language` and how many of those repos actually yield fixtures (see
[Limitations § Fixture Detection Recall](../reference/limitations.md#fixture-detection-recall)
and the survivorship-bias note in `collection/dataset_summary.py`'s module docstring
for why "repos scanned" and "repos yielding fixtures" are not the same denominator).
There are no fixed size figures published here — actual database size depends on
how many repos/languages a given run targets; run
`python -m collection summarize --dataset {a,b,c}` after collection and check
`datasets/{dataset}/summary.yaml`'s `fixtures.total` for the real count, then
`du -h db/{dataset}.db` for the corresponding file size.

## Storage during collection

| Component | Persists after collection? | Notes |
|-----------|----------------------------|-------|
| `db/{a,b,c}.db` | Yes | The actual deliverable — required for `sample`/`export`/`validate`/`summarize` |
| `db/corpus.db` | Only if `--tier2` was used | Not touched by the default Tier 1 collection path |
| `clones/` | No — safe to delete once collection finishes | Full or shallow git clones of every candidate repo; by far the largest transient consumer of disk space, since it holds full commit history for repos under active scan |
| `datasets/{a,b,c}/**/*.csv` | Yes | Stage-by-stage CSV outputs (repos/commits/test-commits/fixtures); the real source of truth for downstream steps — see [Repository Structure](../getting-started/repository-structure.md) |
| `export/{a,b,c}.zip` | Yes | Self-contained per-dataset export (see [CSV Export Guide](csv-export-guide.md)); much smaller than the source DB since it's the sampled subset only |
| `toy-dataset/` | Local only — gitignored | Structurally identical output tree for `toy --dataset {a,b,c}` dry runs, isolated from `datasets/`/`db/` by construction (see `collection/paths.py`) |

`clones/` is the component worth actively managing: `rm -rf clones/` after a
collection run reclaims the majority of disk used during that run, since the CSV/DB
outputs it fed are already durable by that point.

## WAL mode

Every database in `db/` runs in SQLite WAL (Write-Ahead Logging) mode, enabled by
`collection/db.py`'s `get_connection()` — this allows concurrent readers during
multi-worker extraction and reduces `database is locked` errors under load.

```bash
# Check current mode (should return 'wal')
sqlite3 db/a.db "PRAGMA journal_mode;"

# Verify integrity
sqlite3 db/a.db "PRAGMA integrity_check;"  # should return 'ok'
```

## Backups and archival

```bash
# Back up before any destructive operation
cp db/a.db db/a.db.backup

# Compress a single dataset's database for archival
tar -czf a-db.tar.gz db/a.db

# Archive a full export (already small — see export/{dataset}.zip above)
# export/a.zip is already the archival-ready artifact; no further bundling needed
```

## See also

- [Database Schema](../architecture/database-schema.md) — table structure, per-dataset differences
- [CSV Export Guide](csv-export-guide.md) — what ships in `export/{dataset}.zip`
- [Repository Structure](../getting-started/repository-structure.md) — full directory layout
