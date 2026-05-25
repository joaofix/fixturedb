# CSV Export Guide - FixtureDB Between-Group Study

This document describes CSV files you can export from the between-group.db database using SQL tools or custom scripts. The public CSVs contain objective, quantitative metrics only; the full SQLite database contains additional internal fields and control variable data for reproducibility.

## Export structure

Typical export layout:

```
export/fixturedb_v<version>_<date>/
├── fixtures.db                     (full SQLite database with all fields)
├── repositories.csv                (repository metadata)
├── repository_statistics.csv       (aggregated fixture metrics per repository)
├── test_files.csv                  (test file metadata)
├── test_file_statistics.csv        (aggregated fixture metrics per test file)
├── fixtures.csv                    (individual fixture definitions)
├── stats.txt                       (summary statistics)
└── README.txt                      (schema documentation)
```

## 1. repositories.csv

One row per repository with at least one analyzed fixture (status='analysed').

| Column | Type | Description |
|--------|------|-------------|
| `id` | INT | Internal primary key |
| `github_id` | INT | GitHub repository numeric ID |
| `full_name` | TEXT | Repository slug (e.g., "pytest-dev/pytest") |
| `language` | TEXT | Primary language (python, java, javascript, typescript, go) |
| `stars` | INT | Star count at collection time |
| `forks` | INT | Fork count at collection time |
| `num_contributors` | INT | GitHub contributor count |
| `created_at` | TEXT | ISO 8601 repository creation date |
| `pushed_at` | TEXT | ISO 8601 last push date |
| `pinned_commit` | TEXT | SHA of HEAD commit at analysis time |
| `num_test_files` | INT | Total test files found in repository |
| `num_fixtures` | INT | Total fixture definitions in repository |
| `num_analyzed_fixtures` | INT | Fixture definitions extracted and analyzed |
| `collected_at` | TEXT | ISO 8601 timestamp of DB insertion |

## 2. test_files.csv

One row per test file found during repository analysis.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INT | Internal primary key |
| `repo` | TEXT | Repository full_name (e.g., "owner/repo") |
| `language` | TEXT | Source language |
| `relative_path` | TEXT | Path relative to repository root |
| `file_loc` | INT | Non-blank lines of code in test file |
| `num_test_funcs` | INT | Count of test function definitions detected |
| `num_fixtures` | INT | Count of fixture definitions in this file |
| `total_fixture_loc` | INT | Sum of lines of code across all fixtures in this file |

## 3. repository_statistics.csv

Aggregated fixture metrics per repository. One row per analyzed repository. Designed for cross-repository comparisons and correlational studies.

| Column | Type | Description |
|--------|------|-------------|
| `repository_id` | INT | Internal primary key (matches repositories.csv id) |
| `full_name` | TEXT | Repository slug |
| `language` | TEXT | Programming language |
| `github_id` | INT | GitHub repository numeric ID |
| `stars` | INT | Star count at collection time |
| `forks` | INT | Fork count at collection time |
| `num_contributors` | INT | GitHub contributor count |
| `pinned_commit` | TEXT | SHA of analyzed commit |
| | | **Test File Metrics** |
| `num_test_files` | INT | Count of test files in repository |
| `total_test_file_loc` | INT | Total LOC across all test files |
| `avg_test_file_loc` | FLOAT | Average test file size |
| | | **Fixture Counts by Scope** |
| `num_fixtures_total` | INT | Total fixture definitions |
| `num_fixtures_per_test` | INT | Fixtures with per_test scope |
| `num_fixtures_per_class` | INT | Fixtures with per_class scope |
| `num_fixtures_per_module` | INT | Fixtures with per_module scope |
| `num_fixtures_global` | INT | Fixtures with global scope |
| | | **Fixture Type & Framework Diversity** |
| `num_fixture_types_unique` | INT | Count of distinct fixture type values |
| `top_fixture_type` | TEXT | Most common fixture type in repository |
| `top_fixture_type_count` | INT | Count of most common fixture type |
| `num_frameworks_unique` | INT | Count of distinct frameworks |
| `top_framework` | TEXT | Most common testing framework |
| `top_framework_count` | INT | Count of most common framework |
| | | **Fixture LOC Statistics** |
| `avg_fixture_loc` | FLOAT | Average fixture LOC |
| `min_fixture_loc` | INT | Minimum fixture LOC |
| `max_fixture_loc` | INT | Maximum fixture LOC |
| `median_fixture_loc` | FLOAT | Median fixture LOC |
| `stddev_fixture_loc` | FLOAT | Standard deviation of fixture LOC |
| | | **Cyclomatic Complexity Statistics** |
| `avg_cyclomatic_complexity` | FLOAT | Average McCabe complexity |
| `min_cyclomatic_complexity` | INT | Minimum McCabe complexity |
| `max_cyclomatic_complexity` | INT | Maximum McCabe complexity |
| `median_cyclomatic_complexity` | FLOAT | Median McCabe complexity |
| | | **Structural Metrics** |
| `avg_max_nesting_depth` | FLOAT | Average maximum nesting depth |
| `max_nesting_depth_overall` | INT | Deepest nesting level in any fixture |
| `avg_num_parameters` | FLOAT | Average fixture parameters |
| `avg_num_external_calls` | FLOAT | Average external/IO calls per fixture |
| `avg_num_objects_instantiated` | FLOAT | Average object instantiations per fixture |
| | | **Teardown & Cleanup Metrics** |
| `fixtures_with_teardown_count` | INT | Count of fixtures with cleanup logic |
| `teardown_adoption_rate` | FLOAT | Percentage of fixtures with teardown |
| | | **Mock Usage Metrics** |
| `total_mock_usages` | INT | Total distinct mock usages |
| `avg_mocks_per_fixture` | FLOAT | Average mocks per fixture |
| | | **Test Function Metrics** |
| `total_test_functions` | INT | Total test functions in repository |
| `avg_fixtures_per_test_file` | FLOAT | Average fixtures per test file |

## 4. test_file_statistics.csv

Aggregated fixture metrics per test file. One row per test file (including files with no fixtures).

| Column | Type | Description |
|--------|------|-------------|
| `test_file_id` | INT | Internal primary key (matches test_files.csv id) |
| `repository_id` | INT | Reference to repository (matches repositories.csv id) |
| `full_name` | TEXT | Repository slug — human-readable context |
| `language` | TEXT | Programming language |
| `relative_path` | TEXT | Path relative to repository root |
| `file_loc` | INT | Non-blank lines of code in test file |
| | | **Fixture Counts by Scope** |
| `num_fixtures_total` | INT | Total fixtures in this file |
| `num_fixtures_per_test` | INT | Fixtures with per_test scope |
| `num_fixtures_per_class` | INT | Fixtures with per_class scope |
| `num_fixtures_per_module` | INT | Fixtures with per_module scope |
| `num_fixtures_global` | INT | Fixtures with global scope |
| | | **Fixture Type & Framework Diversity** |
| `num_fixture_types_unique` | INT | Count of distinct fixture types in file |
| `top_fixture_type` | TEXT | Most common fixture type in file |
| `num_frameworks_unique` | INT | Count of distinct frameworks in file |
| `top_framework` | TEXT | Most common testing framework in file |
| | | **Fixture LOC Statistics** |
| `total_fixture_loc` | INT | Total LOC of all fixtures in file |
| `avg_fixture_loc` | FLOAT | Average fixture LOC |
| `min_fixture_loc` | INT | Minimum fixture LOC in file |
| `max_fixture_loc` | INT | Maximum fixture LOC in file |
| | | **Cyclomatic Complexity Statistics** |
| `avg_cyclomatic_complexity` | FLOAT | Average McCabe complexity of fixtures |
| `min_cyclomatic_complexity` | INT | Minimum complexity in file |
| `max_cyclomatic_complexity` | INT | Maximum complexity in file |
| | | **Structural Metrics** |
| `avg_max_nesting_depth` | FLOAT | Average nesting depth |
| `avg_num_parameters` | FLOAT | Average parameters per fixture |
| `avg_num_external_calls` | FLOAT | Average external calls per fixture |
| | | **Teardown & Cleanup Metrics** |
| `fixtures_with_teardown_count` | INT | Count of fixtures with cleanup logic |
| `teardown_adoption_rate` | FLOAT | Percentage of fixtures with teardown |
| | | **Mock Usage Metrics** |
| `total_mock_usages` | INT | Total distinct mock usages in file |
| | | **Test Function Metrics** |
| `num_test_funcs` | INT | Count of test functions in file |

## 5. fixtures.csv

One row per fixture definition extracted from test code.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INT | Internal primary key |
| `language` | TEXT | Programming language |
| `repo` | TEXT | Repository full_name (e.g., "owner/repo") |
| `file_path` | TEXT | Relative path to test file |
| `name` | TEXT | Function/method name of the fixture |
| `fixture_type` | TEXT | Detection pattern (pytest_decorator, unittest_setup, before_each, etc.) |
| `framework` | TEXT | Detected testing framework (pytest, unittest, jest, mocha, junit4, etc.) |
| `scope` | TEXT | Execution scope (per_test, per_class, per_module, global) |
| `start_line` | INT | 1-indexed start line in source file |
| `end_line` | INT | 1-indexed end line in source file |
| `loc` | INT | Non-blank lines of code in fixture |
| `cyclomatic_complexity` | INT | McCabe complexity |
| `max_nesting_depth` | INT | Maximum block nesting level |
| `num_parameters` | INT | Number of function parameters |
| `num_objects_instantiated` | INT | Estimated constructor calls inside fixture |
| `num_external_calls` | INT | Estimated I/O / external API calls |
| `reuse_count` | INT | Number of test functions using this fixture |
| `has_teardown_pair` | INT | Binary indicator (0/1): whether fixture includes cleanup/teardown logic |
| `pinned_commit` | TEXT | SHA of analyzed commit |
| `github_url` | TEXT | Direct GitHub link to fixture source code |

## Design rationale

- CSV exports contain only quantitative, objective metrics to facilitate reproducible analyses.
- The full SQLite database (`fixtures.db`) includes internal-only tables/columns used for advanced analysis and reproducibility.

**Internal-only fields (excluded from CSV exports):**
- `category` (fixture): internal fixture classification infrastructure removed from public CSVs
- Detailed `mock_usages` table: available in the SQLite database for researchers who need the raw mock/framework interaction data

## See also

- [Database Schema](../architecture/database-schema.md)
- [Collection & Extraction](../data/data-collection.md)
