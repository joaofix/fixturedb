# Database Schema

FixtureDB provides data in two formats optimized for different use cases:

## Data Formats Comparison

| Aspect | **SQLite** (`fixtures.db`) | **CSV Exports** |
|--------|--------|---------|
| **Purpose** | Complete reproducible dataset with all fields | Quantitative metrics with context for analysis |
| **Tables** | 4 normalized (repositories, test_files, fixtures, mock_usages) | 3 CSV files (fixtures, repositories, test_files) |
| **Includes** | Raw source, internal classifications, error logs, mock framework details | Quantitative metrics only (no raw_source, categories, classifications) |
| **Best for** | Verification, reproducibility, source inspection, detailed mock analysis | Paper analysis, spreadsheet workflows, pandas/R |

---

## SQLite Database (fixtures.db)

**Setup:** Standard SQLite 3 with WAL mode (safe read-only access during writes)

### Table Overview

| Table | Rows (toy) | Relationship | Key Columns |
|-------|------|--------------|---------|
| `repositories` | 200 | Root | full_name, language, stars, forks, pinned_commit, status, num_test_files, num_fixtures, num_contributors |
| `test_files` | 257,764 | FK → repositories.id | repo_id, relative_path, language, file_loc, num_fixtures, total_fixture_loc |
| `fixtures` | 35,169 | FK → test_files.id, repo_id | name, fixture_type, scope, loc, cyclomatic_complexity, num_parameters, reuse_count, has_teardown_pair |
| `mock_usages` | ~18K | FK → fixtures.id | fixture_id, framework, mock_style, target_identifier |

**Entity Relationship:**
```
repositories (1) ──< test_files (1) ──< fixtures (1) ──< mock_usages
      │                                      │
      └──────────────── repo_id ─────────────┘  (denormalized FK)
```

### Key Columns for CSV Export

**fixtures table (primary analysis table):**
- **structure:** `loc`, `cyclomatic_complexity` (via Lizard)
- **design:** `scope`, `num_parameters`, `reuse_count`, `has_teardown_pair`
- **detection:** `fixture_type`, `framework`, `name`
- **context:** Via SQL join: `language`, `repo` (full_name), `file_path`
- **reproducibility:** Via SQL join: `pinned_commit`, `github_url`

**repositories table (exported for context):**
- **identification:** `github_id`, `full_name`, `language`
- **metrics:** `stars`, `forks`, `num_contributors`
- **dates:** `created_at`, `pushed_at`, `pinned_commit`, `collected_at`
- **counts:** `num_test_files`, `num_fixtures`, `num_analyzed_fixtures`

**mock_usages table (database only - not exported to CSV):**
- `framework` (detection pattern: unittest_mock, pytest_mock, mockito, jest, sinon, etc.)
- `target_identifier` (string passed to mock call)
- `num_interactions_configured` (behavior configuration count)
- Available in SQLite for researchers who need detailed mock analysis

---

## CSV Exports

### Files Generated

```
export/fixturedb_v<version>_<date>/
├── fixtures.db                      ← SQLite database
├── fixtures.csv                     ← All fixtures, all languages (~35K rows)
├── repositories.csv                 ← Repository metadata (200 rows)
├── test_files.csv                   ← Test files analyzed (~257K rows)
└── README.txt
```

### What's Excluded from CSV

**Never exported:** `raw_source`, `category`, `mock_style`, `target_layer`, `raw_snippet`, `mock_usages table`  
(Use SQLite database if you need to inspect original code, internal classifications, or detailed mock framework analysis)

### CSV Export Columns

**fixtures.csv** — Main analysis table; one row per fixture (all languages)
- **Identification:** id, language
- **Context:** repo (full_name), file_path, name  
- **Classification:** fixture_type, framework, scope
- **Location:** start_line, end_line
- **Structure:** loc
- **Complexity:** cyclomatic_complexity, max_nesting_depth
- **Design:** num_parameters, num_objects_instantiated, num_external_calls, reuse_count, has_teardown_pair
- **Reproducibility:** pinned_commit, github_url

**repositories.csv** — Repository metadata; one row per analyzed repository
- **Identification:** id, github_id, full_name, language
- **Metrics:** stars, forks, num_contributors
- **Dates:** created_at, pushed_at, pinned_commit
- **Counts:** num_test_files, num_fixtures, num_analyzed_fixtures, collected_at

**test_files.csv** — Test file metadata; one row per test file analyzed
- **Path:** repo (full_name), language, relative_path
- **Metrics:** file_loc, num_test_funcs, num_fixtures, total_fixture_loc

---

## Usage Guidelines

**Use CSVs if:**
- Analyzing with Excel, Tableau, pandas, or R
- Writing a paper (clean, quantitative-only format)
- You don't need raw source code or internal details

**Use SQLite if:**
- Verifying extraction decisions (inspect raw_source)
- Performing complex joins across tables
- Tracing fixture → mock → repository relationships
- Reproducing results (includes error_message, pinned_commit)
