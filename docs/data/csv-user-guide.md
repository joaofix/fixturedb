# CSV User Guide - FixtureDB Between-Group Study

This guide explains the CSV exports from the between-group study collection pipeline. The exports are designed for spreadsheet tools and lightweight analysis workflows; for joins, control variable analysis, and provenance checks, use the SQLite database documented in [Database Schema](../architecture/database-schema.md).

## Export layout

Typical export bundle:

```
export/
├── repositories.csv
├── repository_statistics.csv
├── test_files.csv
├── test_file_statistics.csv
├── fixtures.csv
├── stats.txt
└── README.txt
```

## Quick import

| Tool | Command |
|------|---------|
| Excel | Open `fixtures.csv` |
| Python | `pd.read_csv("fixtures.csv")` |
| R | `read.csv("fixtures.csv")` |
| DuckDB | `SELECT * FROM read_csv_auto('fixtures.csv')` |
| Google Sheets | File > Import > Upload `fixtures.csv` |

## Core CSV files

### repositories.csv

One row per analyzed repository.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INT | Internal repository ID |
| `github_id` | INT | GitHub numeric ID |
| `full_name` | TEXT | Repository slug such as `owner/repo` |
| `language` | TEXT | Repository language |
| `stars` | INT | Star count at collection time |
| `forks` | INT | Fork count at collection time |
| `description` | TEXT | Repository description |
| `topics` | TEXT | JSON-encoded topics list |
| `created_at` | TEXT | Repository creation timestamp |
| `pushed_at` | TEXT | Last push timestamp |
| `clone_url` | TEXT | Repository clone URL |
| `pinned_commit` | TEXT | Commit analyzed for the repository |
| `status` | TEXT | Collection status |
| `error_message` | TEXT | Error text if the repository failed collection |
| `skip_reason` | TEXT | Reason for skipping a repository |
| `num_test_files` | INT | Number of test files found |
| `num_fixtures` | INT | Number of fixture definitions found |
| `num_mock_usages` | INT | Number of mock usages detected |
| `num_contributors` | INT | Contributor count from GitHub |
| `collected_at` | TEXT | Collection timestamp |

### test_files.csv

One row per test file.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INT | Internal test file ID |
| `repo` | TEXT | Repository slug |
| `language` | TEXT | File language |
| `relative_path` | TEXT | Path relative to repository root |
| `file_loc` | INT | Non-blank lines of code in the file |
| `num_test_funcs` | INT | Number of test functions detected |
| `num_fixtures` | INT | Number of fixtures in the file |
| `total_fixture_loc` | INT | Sum of fixture LOC in the file |

### fixtures.csv

One row per extracted fixture definition.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INT | Internal fixture ID |
| `language` | TEXT | Fixture language |
| `repo` | TEXT | Repository slug |
| `file_path` | TEXT | Relative path to the test file |
| `name` | TEXT | Fixture name or method name |
| `fixture_type` | TEXT | Detected fixture pattern |
| `framework` | TEXT | Detected testing framework |
| `scope` | TEXT | Execution scope |
| `start_line` | INT | Start line in the source file |
| `end_line` | INT | End line in the source file |
| `loc` | INT | Non-blank lines of code |
| `cyclomatic_complexity` | INT | McCabe cyclomatic complexity |
| `max_nesting_depth` | INT | Maximum block nesting depth |
| `num_parameters` | INT | Number of parameters |
| `num_objects_instantiated` | INT | Estimated object instantiations |
| `num_external_calls` | INT | Estimated external or I/O calls |
| `has_teardown_pair` | INT | 1 when teardown or cleanup logic is present |
| `pinned_commit` | TEXT | Commit SHA analyzed for the fixture |
| `github_url` | TEXT | Direct link to the fixture source on GitHub |

## Aggregated CSVs

### repository_statistics.csv

Repository-level aggregates for cross-project comparisons.

### test_file_statistics.csv

Test-file-level aggregates for file organization and complexity analysis.

These aggregated exports usually contain the same metric families as the underlying tables: fixture counts by scope, fixture type and framework distribution, LOC statistics, cyclomatic complexity statistics, nesting, parameters, external calls, teardown adoption, mock usage counts, and test-function counts.

## When to use CSV vs SQLite

| Task | Best format |
|------|-------------|
| Load into Excel, R, or pandas | CSV |
| Simple descriptive statistics | CSV |
| Joins across repositories, files, and fixtures | SQLite |
| Inspect raw source text | SQLite |
| Reproduce a paper table | CSV |

## Data quality notes

- CSV exports contain objective, quantitative metrics only.
- Repository, file, and fixture identifiers are stable within an export bundle.
- Legacy columns from the old collection are not part of the current CSV design.
- SQLite should be used when you need provenance, raw source text, or joins across tables.

