# CSV User Guide

**Quick reference for analyzing FixtureDB without SQL.** For full schema details, see [Database Schema](../architecture/database-schema.md). For code examples, see [Using the Dataset](../usage/usage.md).

---

## CSV Files

```
fixturedb_export/
├── fixtures.csv                    ← Main table: 1 row per fixture (35.2K in toy dataset)
├── repositories.csv                ← Repository metadata (200 in toy dataset)
├── test_files.csv                  ← Test file listing (257.8K in toy dataset)
├── fixtures.db                     ← Full SQLite database (optional for advanced queries)
├── stats.txt                       ← Summary statistics
└── README.txt                      ← Schema documentation
```

**Note:** CSV files contain quantitative metrics only. For detailed mock framework analysis or raw source code inspection, use the included SQLite database (`fixtures.db`).

---

## Quick Import

| Tool | Command |
|------|---------|
| **Excel** | Open → fixtures.csv (auto-import) |
| **Python** | `pd.read_csv('fixtures.csv')` |
| **R** | `read.csv('fixtures.csv')` |
| **SQL (SQLite)** | See [usage.md](../usage/usage.md) |

---

## Fixtures Table (Main Analysis)

| Column | Type | Meaning |
|--------|------|---------|
| **Identifiers** | | |
| `id` | Integer | Fixture ID (primary key) |
| **Context** | | |
| `language` | Text | `python`, `java`, `javascript`, `typescript` |
| `repo` | Text | Repository (e.g., `owner/repo`) |
| `file_path` | Text | Test file path |
| `name` | Text | Fixture function name |
| **Characteristics** | | |
| `fixture_type` | Text | Detection pattern (`pytest_decorator`, `unittest_setup`, `before_each`, etc.) |
| `framework` | Text | Testing framework (pytest, unittest, jest, mocha, junit4, etc.) |
| `scope` | Text | Execution scope: `per_test`, `per_class`, `per_module`, `global` |
| **Location** | | |
| `start_line`, `end_line` | Integer | Line numbers in source file |
| `loc` | Integer | Lines of code |
| **Complexity** | | |
| `cyclomatic_complexity` | Integer | McCabe complexity (1 = simple, 10+ = very complex) |
| `max_nesting_depth` | Integer | Maximum nested block depth |
| **Behavior** | | |
| `num_parameters` | Integer | Function parameters |
| `num_objects_instantiated` | Integer | Object creations (heuristic) |
| `num_external_calls` | Integer | I/O and external API calls (heuristic) |
| `reuse_count` | Integer | Number of tests using this fixture |
| `has_teardown_pair` | Integer | Binary (0/1): has cleanup/teardown logic |
| **Reproducibility** | | |
| `pinned_commit` | Text | Git SHA of analyzed commit |
| `github_url` | Text | Direct link to fixture source on GitHub |

---

## Repositories Table

| Column | Meaning |
|--------|---------|
| `id` | Repository ID |
| `github_id` | GitHub numeric repository ID |
| `full_name` | GitHub slug (e.g., `"pytest-dev/pytest"`) |
| `language` | `python`, `java`, `javascript`, `typescript` |
| `stars` | Star count at collection time (maturity metric) |
| `forks` | Fork count at collection time (adoption metric) |
| `num_contributors` | GitHub contributor count (maturity metric) |
| `created_at`, `pushed_at` | Creation and last push dates (ISO 8601) |
| `pinned_commit` | Git SHA analyzed (for reproducibility) |
| `num_test_files` | Test files found in repository |
| `num_fixtures` | Fixtures found in repository |
| `num_analyzed_fixtures` | Fixtures extracted and analyzed (should match count for this repo in fixtures.csv) |
| `collected_at` | Timestamp of collection (ISO 8601) |

---

## Test Files Table

| Column | Meaning |
|--------|---------|
| `relative_path` | Path within repository (e.g., `tests/test_app.py`) |
| `file_loc` | Total lines of code |
| `num_fixtures` | Fixtures defined in file |
| `language` | Programming language |

---

## Common Analysis Patterns

**Distribution of complexity by language:**
```python
import pandas as pd
df = pd.read_csv('fixtures.csv')
df.groupby('language')['cyclomatic_complexity'].agg(['mean', 'count'])
```

**Fixtures with high reuse:**
```python
df_high_reuse = df[df['reuse_count'] > 10].sort_values('reuse_count', ascending=False)
df_high_reuse[['name', 'fixture_type', 'reuse_count', 'cyclomatic_complexity']]
```

**Teardown adoption by language:**
```python
df.groupby('language')['has_teardown_pair'].agg(['sum', 'count', lambda x: (x.sum()/len(x))*100])
```

**Test file statistics:**
```python
tf = pd.read_csv('test_files.csv')
tf.groupby('repo')['num_fixtures'].sum().sort_values(ascending=False).head(10)
```

---

## Data Notes

- **Complexity NULL:** Error during calculation (< 0.1%); safe to exclude
- **Count = 0:** Legitimate (no objects/calls in that fixture)
- **Scope options:** `per_test` (most common) → `per_class` → `per_module` → `global` (rare)
- **Pinned commits:** Use `repositories.pinned_commit` to check out exact code versions analyzed

See [Limitations](../reference/limitations.md) for known constraints and validation status.

