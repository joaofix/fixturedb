# CSV Quick-Reference

A quick-import reference for the CSVs inside `export/{dataset}.zip` (Dataset A, B,
or C — `python -m collection export --dataset {a,b,c}`). For the full column
reference and export mechanics, see [CSV Export Guide](csv-export-guide.md); this
page is just the "how do I open this in my tool of choice" cheat sheet.

## Export layout

```
export/a.zip
├── repositories.csv
├── test_files.csv
├── fixtures.csv
├── mock_usages.csv
├── README.md
└── SCHEMA.md
```

Each CSV is a raw dump of its database table (`repositories`, `test_files`,
`fixtures`, `mock_usages` — see [Database Schema](../architecture/database-schema.md)
for every column). There are no separate pre-aggregated "statistics" CSVs — if you
need per-repository or per-file aggregates, compute them yourself with a `GROUP BY`
over `fixtures.csv`/`mock_usages.csv`, or query the source SQLite database directly.

## Quick import

| Tool | Command |
|------|---------|
| Excel | Open `fixtures.csv` |
| Python | `pd.read_csv("fixtures.csv")` |
| R | `read.csv("fixtures.csv")` |
| DuckDB | `SELECT * FROM read_csv_auto('fixtures.csv')` |
| Google Sheets | File > Import > Upload `fixtures.csv` |

## When to use CSV vs SQLite

| Task | Best format |
|------|-------------|
| Load into Excel, R, or pandas | CSV |
| Simple descriptive statistics | CSV |
| Joins across repositories, test files, fixtures, and mocks | SQLite (`db/{dataset}.db`) |
| Inspect raw fixture/mock source text | SQLite |
| Cross-dataset comparison (A vs B, A vs C) | SQLite — see [Analyzing the Datasets](../usage/usage.md) |

## Data quality notes

- CSV exports contain objective, quantitative metrics only — see
  [CSV Export Guide § Design rationale](csv-export-guide.md#design-rationale) for
  what's deliberately excluded (e.g. `mock_usages.category` classification detail
  beyond the raw taxonomy value).
- `fixtures.csv`/`mock_usages.csv` are filtered to the sampled fixture set; they are
  not a dump of every fixture ever collected for that dataset.
- Column definitions live in one place — [Database Schema](../architecture/database-schema.md)
  — rather than duplicated here, so this page can't drift out of sync with the schema.
