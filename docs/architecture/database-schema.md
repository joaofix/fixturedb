# Database Schema

FixtureDB collects three separate datasets — see
[Repository Structure](../getting-started/repository-structure.md) — each written to
its own SQLite database rather than one shared file:

## Database overview

| Database | Purpose | `fixtures.commit_kind` |
|----------|---------|-------------------------|
| `db/corpus.db` | Pre-A/B/C paired-study repository corpus with pinned commits (only needed for `--tier2` agent discovery, see [Agent Detection](agent-detection.md)) | n/a |
| `db/a.db` | Dataset A: agent-authored fixtures (2025+, Tier 1 detection) | always `'agent'` |
| `db/b.db` | Dataset B: human-authored fixtures, within-repo control (same repos as A, non-agent commits) | always `'human'` |
| `db/c.db` | Dataset C: human-authored fixtures, cross-repo baseline (independent pre-2021 repo pool, snapshot extraction) | not set (Dataset C has no commit-level agent/human distinction to make — every fixture in it is human-authored by construction) |

All four use the identical schema below (defined once in `collection/db_schema.py`)
and run in SQLite WAL mode for safe concurrent reads. Because each dataset is a
separate file, there is no single query that spans all three — see
[Query examples](#query-examples) for the recommended cross-dataset pattern.

## Schema

### repositories

Repository metadata and control variables computed at fixture writing time.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Internal primary key |
| `github_id` | INTEGER | GitHub repository numeric ID |
| `full_name` | TEXT | Repository slug such as `pytest-dev/pytest` |
| `language` | TEXT | Normalized primary language (`python`, `java`, `javascript`, `typescript`) |
| `stars` | INTEGER | Star count (current; historical unavailable from GitHub API) |
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
| **Control Variables** |
| `domain` | TEXT | Classified domain (`web`, `systems`, `ml`, `security`, `database`, `devops`, `other`) |
| `repo_age_years` | REAL | Repository age in years at fixture writing time (2025-01-01 for Datasets A/B, 2020-12-31 for Dataset C) |
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
| `has_teardown_pair` | INTEGER | Binary indicator for teardown or cleanup logic |
| `raw_source` | TEXT | Original source text for the fixture |
| `framework` | TEXT | Detected framework such as `pytest`, `unittest`, `junit`, `jest`, or `mocha` |
| `num_mocks` | INTEGER | Number of distinct mock usages associated with the fixture |
| **Dataset Labeling** |
| `commit_sha` | TEXT | Commit SHA that introduced this fixture (empty string in `db/c.db`, whose fixtures come from a repo-snapshot extraction, not a commit scan) |
| `commit_kind` | TEXT | `'agent'` in `db/a.db`, `'human'` in `db/b.db`; not set in `db/c.db` (see [Database overview](#database-overview)) |
| `agent_type` | TEXT | Agent family (`claude`, `copilot`, `cursor`, `aider`) if agent-authored, NULL otherwise |
| `is_complete_addition` | INTEGER | 1 when the fixture was added as a complete addition in its commit |

### mock_usages

Per-fixture mock framework usage data — one row per detected mock call
(a fixture with `num_mocks=3` has 3 rows here). See
[Fixture Detection Logic § Mock Detection](detection.md#mock-detection)
for how these are detected and classified, and
[collection/heuristics/feature_extraction_patterns.yaml](../../collection/heuristics/feature_extraction_patterns.yaml)
for the exact pattern/framework/category catalog.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Internal primary key |
| `fixture_id` | INTEGER | Foreign key to `fixtures.id` |
| `repo_id` | INTEGER | Foreign key to `repositories.id` |
| `framework` | TEXT | Mocking framework or helper family (e.g. `unittest_mock`, `sinon`, `mockito`) |
| `category` | TEXT | Classic test-double taxonomy (Meszaros): `dummy` \| `stub` \| `spy` \| `mock` \| `fake` — `dummy` is never populated by design (see detection.md) |
| `target_identifier` | TEXT | Identifier passed to the mock call, if extractable (empty string otherwise) |
| `num_interactions_configured` | INTEGER | Number of interactions configured on the mock |
| `raw_snippet` | TEXT | Original source snippet for the mock usage |


## Query examples

Each database is a single dataset (see [Database overview](#database-overview)), so
within-database queries never need a `commit_kind` filter to isolate a corpus — every
row in `db/a.db` already is Dataset A. Cross-dataset comparisons instead load each
database separately and combine in pandas.

### Within one dataset: fixture characteristics

```python
import sqlite3
import pandas as pd

conn = sqlite3.connect("db/a.db")

summary = pd.read_sql("""
    SELECT
        COUNT(f.id) as fixture_count,
        ROUND(AVG(f.loc), 2) as avg_loc,
        ROUND(AVG(f.cyclomatic_complexity), 2) as avg_complexity,
        ROUND(AVG(f.num_parameters), 2) as avg_parameters
    FROM fixtures f
""", conn)

print(summary)
```

### Within one dataset: agent type distribution (Dataset A only)

```python
import sqlite3
import pandas as pd

conn = sqlite3.connect("db/a.db")

agent_breakdown = pd.read_sql("""
    SELECT
        f.agent_type,
        COUNT(DISTINCT f.commit_sha) as commits,
        COUNT(f.id) as fixtures,
        ROUND(AVG(f.loc), 2) as avg_loc
    FROM fixtures f
    WHERE f.agent_type IS NOT NULL
    GROUP BY f.agent_type
    ORDER BY commits DESC
""", conn)

print(agent_breakdown)
```

### Cross-dataset: compare A vs B (same repos, agent vs human)

Load each database into its own DataFrame, tag with the dataset it came from, then
concatenate — this is the general pattern for any A-vs-B or A-vs-C comparison:

```python
import sqlite3
import pandas as pd

def load_fixtures(dataset: str) -> pd.DataFrame:
    conn = sqlite3.connect(f"db/{dataset}.db")
    df = pd.read_sql("""
        SELECT f.*, r.language, r.domain, r.repo_age_years
        FROM fixtures f
        JOIN repositories r ON f.repo_id = r.id
    """, conn)
    df["dataset"] = dataset
    return df

combined = pd.concat([load_fixtures("a"), load_fixtures("b")], ignore_index=True)

comparison = combined.groupby("dataset").agg(
    fixture_count=("id", "count"),
    avg_loc=("loc", "mean"),
    avg_complexity=("cyclomatic_complexity", "mean"),
)
print(comparison)
```

Dataset B's `dataset` column here plays the role Dataset A's `commit_kind='agent'` /
`commit_kind='human'` distinction used to play in the old single-database design —
prefer `dataset` (which one you loaded from) over `commit_kind` for A-vs-B/A-vs-C
comparisons, since `commit_kind` is not populated at all in `db/c.db`.

### Test-double category breakdown, one dataset

```python
import sqlite3
import pandas as pd

conn = sqlite3.connect("db/a.db")

mock_categories = pd.read_sql("""
    SELECT
        m.category,
        m.framework,
        COUNT(*) as mock_count
    FROM mock_usages m
    JOIN fixtures f ON m.fixture_id = f.id
    GROUP BY m.category, m.framework
    ORDER BY mock_count DESC
""", conn)

print(mock_categories)
```

## Data quality guarantees

- The schema is append-safe and re-runnable; existing records are not duplicated during collection.
- Control variables (`language`, `domain`, `repo_age_years`) are computed deterministically at each dataset's temporal boundary (2025-01-01 for A/B, 2020-12-31 for C).
- Quantitative fields such as LOC, complexity, counts, and scope are derived deterministically from analyzed source code.

## Accessing the database

### CLI

```bash
# Fixture count for one dataset
sqlite3 db/a.db "SELECT COUNT(*) FROM fixtures;"

# Agent type breakdown (Dataset A only)
sqlite3 db/a.db "SELECT agent_type, COUNT(*) FROM fixtures WHERE agent_type IS NOT NULL GROUP BY agent_type;"
```

### Python

```python
import sqlite3

conn = sqlite3.connect("db/a.db")

count = conn.execute("SELECT COUNT(*) FROM fixtures").fetchone()[0]
print(f"Dataset A: {count} fixtures")
```

### R

```r
library(DBI)
con <- dbConnect(RSQLite::SQLite(), "db/a.db")

dbGetQuery(con, "
  SELECT agent_type, COUNT(*) AS fixture_count
  FROM fixtures
  WHERE agent_type IS NOT NULL
  GROUP BY agent_type
  ORDER BY fixture_count DESC
")
```

## Notes

- Control variables (language, domain, repo_age_years) are computed at each dataset's temporal boundary for reproducibility and validity assessment.
- The schema supports unpaired statistical tests appropriate for independent samples (Mann-Whitney U for continuous variables, chi-square for categorical) — see [Between-Group Study Design](../reference/limitations.md#between-group-study-design).
- `python -m collection summarize --dataset {a,b,c}` writes `datasets/{dataset}/summary.yaml` with repo/fixture counts and purity-gate rates read directly from the CSV outputs, not the database — see `collection/dataset_summary.py`.

