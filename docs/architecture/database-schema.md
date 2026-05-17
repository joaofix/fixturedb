# Database Schema - FixtureDB Collection

The collection stores fixture data in SQLite with a shared schema and a small set of AGENT-only columns. The public documentation focuses on the fields that are actually used for analysis and export.

## Database overview

| Database | Purpose | Scope |
|----------|---------|-------|
| `fixturedb-human.db` | Pre-2021 human-written fixtures | Human baseline |
| `fixturedb-agent.db` | 2021+ agent-generated fixtures | Agent-era dataset with commit metadata |

Both databases use SQLite with WAL mode enabled for safe concurrent reads.

## Shared schema

### repositories

Repository metadata and collection statistics.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Internal primary key |
| `github_id` | INTEGER | GitHub repository numeric ID |
| `full_name` | TEXT | Repository slug such as `pytest-dev/pytest` |
| `language` | TEXT | Normalized primary language (`python`, `java`, `javascript`, `typescript`, `go`) |
| `stars` | INTEGER | Star count at collection time |
| `forks` | INTEGER | Fork count at collection time |
| `description` | TEXT | Repository description from GitHub |
| `topics` | TEXT | JSON-encoded list of GitHub topics |
| `created_at` | TEXT | ISO 8601 repository creation date |
| `pushed_at` | TEXT | ISO 8601 last push date |
| `clone_url` | TEXT | Repository clone URL |
| `pinned_commit` | TEXT | Commit SHA analyzed for the repository |
| `status` | TEXT | Collection status such as `discovered`, `cloned`, `analysed`, `skipped`, or `error` |
| `error_message` | TEXT | Error details if collection failed |
| `skip_reason` | TEXT | Skip reason when a repository is filtered out |
| `num_test_files` | INTEGER | Number of test files found |
| `num_fixtures` | INTEGER | Number of fixture definitions found |
| `num_mock_usages` | INTEGER | Number of mock usages detected |
| `num_contributors` | INTEGER | Contributor count from GitHub |
| `collected_at` | TEXT | Timestamp of insertion |

### test_files

Test file inventory and file-level summary counts.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Internal primary key |
| `repo_id` | INTEGER | Foreign key to `repositories.id` |
| `relative_path` | TEXT | Path relative to repository root |
| `language` | TEXT | File language |
| `file_loc` | INTEGER | Non-blank lines of code in the file |
| `num_test_funcs` | INTEGER | Number of detected test functions |
| `num_fixtures` | INTEGER | Number of fixtures in the file |
| `total_fixture_loc` | INTEGER | Sum of fixture LOC within the file |

### fixtures

Individual fixture definitions and their quantitative metrics.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Internal primary key |
| `file_id` | INTEGER | Foreign key to `test_files.id` |
| `repo_id` | INTEGER | Foreign key to `repositories.id` |
| `name` | TEXT | Fixture name or method name |
| `fixture_type` | TEXT | Detected fixture pattern such as `pytest_decorator`, `unittest_setup`, or `before_each` |
| `scope` | TEXT | Execution scope such as `per_test`, `per_class`, `per_module`, or `global` |
| `start_line` | INTEGER | 1-based start line |
| `end_line` | INTEGER | 1-based end line |
| `loc` | INTEGER | Non-blank lines of code in the fixture |
| `cyclomatic_complexity` | INTEGER | McCabe cyclomatic complexity |
| `max_nesting_depth` | INTEGER | Maximum block nesting depth |
| `num_objects_instantiated` | INTEGER | Estimated object creations inside the fixture |
| `num_external_calls` | INTEGER | Estimated I/O or external calls inside the fixture |
| `num_parameters` | INTEGER | Number of fixture parameters |
| `reuse_count` | INTEGER | Number of test functions using this fixture |
| `has_teardown_pair` | INTEGER | Binary indicator for teardown or cleanup logic |
| `raw_source` | TEXT | Original source text for the fixture |
| `framework` | TEXT | Detected framework such as `pytest`, `unittest`, `junit`, `jest`, or `mocha` |
| `num_mocks` | INTEGER | Number of distinct mock usages associated with the fixture |
| `commit_sha` | TEXT | AGENT-only: commit that introduced the fixture |
| `agent_type` | TEXT | AGENT-only: agent family such as `claude`, `copilot`, `cursor`, or `github-actions` |
| `tier` | INTEGER | AGENT-only: corpus tier flag used by the split pipeline |
| `is_complete_addition` | INTEGER | AGENT-only: 1 when the fixture was added as a complete addition |

### mock_usages

Per-fixture mock framework usage data.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Internal primary key |
| `fixture_id` | INTEGER | Foreign key to `fixtures.id` |
| `repo_id` | INTEGER | Foreign key to `repositories.id` |
| `framework` | TEXT | Mocking framework or helper family |
| `target_identifier` | TEXT | Identifier passed to the mock call |
| `num_interactions_configured` | INTEGER | Number of interactions configured on the mock |
| `raw_snippet` | TEXT | Original source snippet for the mock usage |

## Query examples

### Compare human and AGENT fixture size

```python
import pandas as pd
import sqlite3

human = sqlite3.connect("fixturedb-human.db")
agent = sqlite3.connect("fixturedb-agent.db")

human_by_framework = pd.read_sql(
    "SELECT framework, COUNT(*) AS n, AVG(loc) AS avg_loc FROM fixtures GROUP BY framework ORDER BY n DESC",
    human,
)
llm_by_framework = pd.read_sql(
    "SELECT framework, COUNT(*) AS n, AVG(loc) AS avg_loc FROM fixtures GROUP BY framework ORDER BY n DESC",
    agent,
)

print(human_by_framework)
print(llm_by_framework)
```

### Compare scope distributions

```sql
SELECT scope, COUNT(*) AS fixtures
FROM fixtures
GROUP BY scope
ORDER BY fixtures DESC;
```

### Inspect mock usage per framework

```python
import sqlite3
import pandas as pd

conn = sqlite3.connect("fixturedb-agent.db")
df = pd.read_sql(
    "SELECT framework, COUNT(*) AS mock_count, AVG(num_interactions_configured) AS avg_interactions FROM mock_usages GROUP BY framework ORDER BY mock_count DESC",
    conn,
)
print(df)
```

## Data quality guarantees

- The schema is append-safe and re-runnable; existing records are not truncated during collection.
- Human and AGENT databases share the same core table structure so analyses can be compared directly.
- AGENT-only columns are only populated where commit-level provenance exists.
- Quantitative fields such as LOC, complexity, counts, and scope are derived deterministically from the analyzed source code.

## Accessing the databases

### CLI

```bash
sqlite3 fixturedb-human.db "SELECT COUNT(*) FROM fixtures;"
sqlite3 fixturedb-agent.db "SELECT framework, COUNT(*) FROM fixtures GROUP BY framework ORDER BY COUNT(*) DESC;"
```

### Python

```python
import sqlite3

conn = sqlite3.connect("fixturedb-human.db")
rows = conn.execute("SELECT scope, COUNT(*) FROM fixtures GROUP BY scope ORDER BY COUNT(*) DESC").fetchall()
print(rows)
```

### R

```r
library(DBI)
con <- dbConnect(RSQLite::SQLite(), "fixturedb-agent.db")
dbGetQuery(con, "SELECT agent_type, COUNT(*) AS fixtures FROM fixtures GROUP BY agent_type ORDER BY fixtures DESC")
```

## Notes

- The public docs only document the current collection fields and metrics.
- The SQLite database keeps the raw source text for reproducibility and deeper analysis.
