# CSV Export Guide

`python -m collection export --dataset {a,b,c}` writes `export/{dataset}.zip`, a
self-contained bundle for one dataset at a time (Dataset A: agent fixtures, Dataset B:
human within-repo control, Dataset C: human cross-repo baseline — see
[Repository Structure](../getting-started/repository-structure.md)). There is no
combined cross-dataset export; each ZIP stands alone and is usable without the
source database or the other two datasets.

## Export contents

```
export/a.zip
├── repositories.csv    (repositories table, raw dump)
├── test_files.csv      (test_files table, raw dump)
├── fixtures.csv        (fixtures table, sampled subset)
├── mock_usages.csv     (mock_usages table, filtered to fixtures in the sample)
├── README.md           (dataset description, generated at export time)
├── SCHEMA.md           (column reference for this export)
└── AGENTS.md           (Dataset A only: agent-detection methodology summary)
```

Each CSV is a direct dump of its table's columns via `SELECT *` — the same columns
documented in [Database Schema](../architecture/database-schema.md), not a separate
curated/renamed column set. `fixtures.csv` and `mock_usages.csv` are filtered to the
sampled fixture IDs produced by `python -m collection sample --dataset {a,b,c}`
(see [Manual-Validation Sampling](../usage/validation-sampling.md) for how that sample is
drawn); `repositories.csv` and `test_files.csv` include every row associated with
those fixtures.

## Column reference

See [Database Schema](../architecture/database-schema.md) for the full, authoritative
column list per table (`repositories`, `test_files`, `fixtures`, `mock_usages`) —
duplicating it here would just be another place for it to drift out of sync.

## Design rationale

- Exports are per-dataset (A/B/C), not merged, so a downstream analysis that needs to
  compare across datasets must open more than one export — see
  [Database Schema § Query examples](../architecture/database-schema.md#query-examples)
  for the recommended pattern (load each dataset separately, tag with a `dataset`
  column, concatenate).
- The full raw `mock_usages.csv` (including each mock's `category` — the classic
  test-double taxonomy dummy/stub/spy/mock/fake) is included directly in the export;
  there is currently no separate aggregated-statistics CSV layer on top of it.

## See also

- [Database Schema](../architecture/database-schema.md)
- [Repository Structure](../getting-started/repository-structure.md)
- [Manual-Validation Sampling](../usage/validation-sampling.md)
