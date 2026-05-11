# CSV Export Guide

**Note:** For full database queries and raw source code access, see [Database Schema](../architecture/database-schema.md) or [Using the Dataset](../usage/usage.md).

This document describes all CSV files exported during `python pipeline.py export`.

## Export Structure

CSV files generated during export:

```
export/fixturedb_v<version>_<date>/
├── fixtures.db                (full database with all fields)
├── repositories.csv
├── test_files.csv
├── fixtures.csv               (raw_source excluded by default; use --include-source for full source)
├── stats.txt                  (summary statistics)
└── README.txt                 (schema documentation)
```

## 1. repositories.csv

One row per repository with at least one analyzed fixture (status='analysed').

| Column | Type | Description |
|--------|------|-------------|
| `id` | INT | Internal primary key |
| `github_id` | INT | GitHub repository numeric ID |
| `full_name` | TEXT | Repository slug (e.g., "pytest-dev/pytest") |
| `language` | TEXT | Primary language (python, java, javascript, typescript) |
| `stars` | INT | Star count at collection time (GitHub maturity metric) |
| `forks` | INT | Fork count at collection time (adoption metric) |
| `num_contributors` | INT | GitHub contributor count (project maturity) |
| `created_at` | TEXT | ISO 8601 repository creation date |
| `pushed_at` | TEXT | ISO 8601 last push date |
| `pinned_commit` | TEXT | SHA of HEAD commit at analysis time (for reproducibility) |
| `num_test_files` | INT | Total test files found in repository |
| `num_fixtures` | INT | Total fixture definitions in repository |
| `num_analyzed_fixtures` | INT | Fixture definitions extracted and analyzed (matches fixtures.csv count for this repo) |
| `collected_at` | TEXT | ISO 8601 timestamp of DB insertion |

## 2. test_files.csv

One row per test file found during repository analysis.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INT | Internal primary key |
| `repo` | TEXT | Repository full_name (e.g., "owner/repo") — human-readable context |
| `language` | TEXT | Source language (python, java, javascript, typescript) |
| `relative_path` | TEXT | Path relative to repository root |
| `file_loc` | INT | Non-blank lines of code in test file |
| `num_test_funcs` | INT | Count of test function definitions detected |
| `num_fixtures` | INT | Count of fixture definitions in this file |
| `total_fixture_loc` | INT | Sum of lines of code across all fixtures in this file |

## 3. fixtures.csv

One row per fixture definition found during extraction.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INT | Internal primary key |
| `language` | TEXT | Programming language (python, java, javascript, typescript) |
| `repo` | TEXT | Repository full_name (e.g., "owner/repo") — human-readable context |
| `file_path` | TEXT | Relative path to test file |
| `name` | TEXT | Function/method name of the fixture |
| `fixture_type` | TEXT | Detection pattern (pytest_decorator, unittest_setup, before_each, etc.) — quantitative classification |
| `framework` | TEXT | Detected testing framework (pytest, unittest, jest, mocha, junit4, etc.) |
| `scope` | TEXT | Execution scope (per_test, per_class, per_module, global) |
| `start_line` | INT | 1-indexed start line in source file |
| `end_line` | INT | 1-indexed end line in source file |
| `loc` | INT | Non-blank lines of code in fixture |
| `cyclomatic_complexity` | INT | McCabe complexity: 1 + number of branching statements |
| `max_nesting_depth` | INT | Maximum block nesting level |
| `num_parameters` | INT | Number of function parameters |
| `num_objects_instantiated` | INT | Estimated constructor calls inside fixture (detected via regex; see limitations) |
| `num_external_calls` | INT | Estimated I/O / external API calls (DB, HTTP, filesystem, env); see limitations |
| `reuse_count` | INT | Number of test functions using this fixture |
| `has_teardown_pair` | INT | Binary indicator (0/1): whether fixture includes cleanup/teardown logic |
| `pinned_commit` | TEXT | SHA of analyzed commit (for reproducibility) |
| `github_url` | TEXT | Direct GitHub link to fixture source code (click to view in browser) |

## Design Rationale

### CSV Export Strategy

The public CSV exports contain **quantitative metrics only** for this dataset. The full SQLite database includes additional infrastructure columns for reproducibility and detailed mock framework analysis, but these are intentionally excluded from CSV exports:

**Internal-only fields (excluded from CSV):**
- `category` (fixture) — Internal fixture classification infrastructure; enables future taxonomy work
- `mock_usages` table (fixture framework analysis) — Detailed mock framework counts and interactions; available in SQLite database for researchers who need it

### Design principles

1. **Quantitative focus:** CSV exports contain only measurable, objective facts (LOC, counts, metrics, detection patterns)
2. **Context-rich:** Human-readable columns (repo, file_path, github_url) enable standalone analysis without database joins
3. **Reproducible:** Full SQLite database available for verification of extraction decisions
4. **Traceable:** github_url enables verification of any finding directly in source code on GitHub
5. **Archivable:** Zenodo deposit includes both SQLite (for transparency and future research) and CSV (for paper analysis and public sharing)

## See Also

- [Database Schema](../architecture/database-schema.md) — Complete schema including excluded fields
- [Collection & Extraction](../data/data-collection.md) — How metrics and detections are computed
