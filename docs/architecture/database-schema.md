# Database Schema - FixtureDB Between-Group Study

The between-group study stores fixture data from two separate populations: human-authored (pre-2021) and agent-authored (2025+). The database enables comparison of fixture characteristics across populations while tracking control variables.

## Database overview

| Database | Purpose | Scope |
|----------|---------|-------|
| `corpus.db` | Original repository corpus with pinned commits | Source data for both corpora |
| `between-group.db` | Human and agent fixture populations | Between-group comparison and statistical analysis |

Both databases use SQLite with WAL mode enabled for safe concurrent reads.

## Between-Group Schema

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
| `star_tier` | TEXT | Star classification (`core` ≥500 stars, `extended` <500 stars) |
| `repo_age_years` | REAL | Repository age in years at fixture writing time (2020-12-31 for human, 2025-01-01 for agent) |
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
| **Between-Group Labeling** |
| `commit_sha` | TEXT | Commit SHA that introduced this fixture |
| `commit_kind` | TEXT | Corpus label: `human` (pre-2021) or `agent` (2025+) |
| `agent_type` | TEXT | Agent family (`claude`, `copilot`, `cursor`, `aider`) if agent-authored, NULL otherwise |
| `is_complete_addition` | INTEGER | 1 when the fixture was added as a complete addition in its commit |

### mock_usages

Per-fixture mock framework usage data — one row per detected mock call
(a fixture with `num_mocks=3` has 3 rows here). See
[Fixture Detection Logic § Mock Framework Detection](detection.md#mock-framework-detection)
for how these are detected and classified, and
[collection/config_data/feature_extraction_patterns.yaml](../../collection/config_data/feature_extraction_patterns.yaml)
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

### Compare human vs agent fixture characteristics

```python
import pandas as pd
import sqlite3

conn = sqlite3.connect("between-group.db")

# Aggregate fixtures by corpus
fixtures_by_corpus = pd.read_sql("""
    SELECT 
        f.commit_kind as corpus,
        COUNT(f.id) as fixture_count,
        ROUND(AVG(f.loc), 2) as avg_loc,
        ROUND(AVG(f.cyclomatic_complexity), 2) as avg_complexity,
        ROUND(AVG(f.num_parameters), 2) as avg_parameters
    FROM fixtures f
    GROUP BY f.commit_kind
""", conn)

print(fixtures_by_corpus)
```

### Analyze agent type distribution (agent corpus only)

```python
import sqlite3
import pandas as pd

conn = sqlite3.connect("between-group.db")

agent_breakdown = pd.read_sql("""
    SELECT 
        f.agent_type,
        COUNT(DISTINCT f.commit_sha) as commits,
        COUNT(f.id) as fixtures,
        ROUND(AVG(f.loc), 2) as avg_loc
    FROM fixtures f
    WHERE f.commit_kind = 'agent' AND f.agent_type IS NOT NULL
    GROUP BY f.agent_type
    ORDER BY commits DESC
""", conn)

print(agent_breakdown)
```

### Check control variable distributions

```python
import sqlite3
import pandas as pd

conn = sqlite3.connect("between-group.db")

# Domain distribution by corpus
domain_balance = pd.read_sql("""
    SELECT 
        r.domain,
        f.commit_kind as corpus,
        COUNT(DISTINCT r.id) as repos,
        COUNT(f.id) as fixtures
    FROM fixtures f
    JOIN repositories r ON f.repo_id = r.id
    WHERE r.domain IS NOT NULL
    GROUP BY r.domain, f.commit_kind
    ORDER BY r.domain, f.commit_kind
""", conn)

print(domain_balance)
```

### Test-double category breakdown by corpus

```python
import sqlite3
import pandas as pd

conn = sqlite3.connect("between-group.db")

mock_categories = pd.read_sql("""
    SELECT
        f.commit_kind as corpus,
        m.category,
        m.framework,
        COUNT(*) as mock_count
    FROM mock_usages m
    JOIN fixtures f ON m.fixture_id = f.id
    GROUP BY f.commit_kind, m.category, m.framework
    ORDER BY f.commit_kind, mock_count DESC
""", conn)

print(mock_categories)
```

### Repository age and star tier balance

```python
import sqlite3
import pandas as pd

conn = sqlite3.connect("between-group.db")

# Age and star tier by corpus
control_balance = pd.read_sql("""
    SELECT 
        r.star_tier,
        f.commit_kind as corpus,
        COUNT(DISTINCT r.id) as repos,
        ROUND(AVG(r.repo_age_years), 2) as avg_age_years
    FROM fixtures f
    JOIN repositories r ON f.repo_id = r.id
    WHERE r.star_tier IS NOT NULL
    GROUP BY r.star_tier, f.commit_kind
    ORDER BY r.star_tier, f.commit_kind
""", conn)

print(control_balance)
```

### Inspect frameworks used in agent vs human fixtures

```python
import sqlite3
import pandas as pd

conn = sqlite3.connect("data/between-group.db")

framework_comparison = pd.read_sql("""
    SELECT 
        f.framework,
        f.commit_kind,
        COUNT(*) as fixture_count,
        ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM fixtures), 1) as pct
    FROM fixtures f
    WHERE f.framework IS NOT NULL
    GROUP BY f.framework, f.commit_kind
    ORDER BY fixture_count DESC
""", conn)

print(framework_comparison)
```

## Data quality guarantees

- The schema is append-safe and re-runnable; existing records are not duplicated during collection.
- Fixtures are labeled by corpus (`commit_kind`) and agent type, enabling unpaired statistical analysis.
- Control variables (`language`, `domain`, `star_tier`, `repo_age_years`) are computed deterministically at temporal boundaries (2020-12-31 for human, 2025-01-01 for agent).
- Quantitative fields such as LOC, complexity, counts, and scope are derived deterministically from analyzed source code.

## Accessing the database

### CLI

```bash
# Count fixtures by commit_kind (corpus)
sqlite3 data/between-group.db "SELECT commit_kind, COUNT(*) FROM fixtures GROUP BY commit_kind;"

# Agent type breakdown
sqlite3 data/between-group.db "SELECT agent_type, COUNT(*) FROM fixtures WHERE agent_type IS NOT NULL GROUP BY agent_type;"

# Compare fixture counts
sqlite3 data/between-group.db "
  SELECT commit_kind, 
         COUNT(f.id) as fixture_count,
         ROUND(AVG(f.cyclomatic_complexity), 2) as avg_complexity
  FROM fixtures f
  GROUP BY f.commit_kind;
"
```

### Python

```python
import sqlite3

conn = sqlite3.connect("data/between-group.db")

# Human vs agent fixture count
corpus_counts = conn.execute(
    "SELECT commit_kind, COUNT(*) as count FROM fixtures GROUP BY commit_kind"
).fetchall()

for corpus, count in corpus_counts:
    print(f"{corpus}: {count} fixtures")
```

### R

```r
library(DBI)
con <- dbConnect(RSQLite::SQLite(), "data/between-group.db")

# Fixture counts by agent type
dbGetQuery(con, "
  SELECT agent_type, COUNT(*) AS fixture_count
  FROM fixtures
  WHERE commit_kind = 'agent' AND agent_type IS NOT NULL
  GROUP BY agent_type
  ORDER BY fixture_count DESC
")
```

## Notes

- The between-group database preserves control variables (language, domain, star_tier, repo_age_years) computed at temporal boundaries for reproducibility and validity assessment.
- The schema is designed for between-group unpaired comparisons using statistical tests appropriate for independent samples.
- Balance test results enable assessment of control variable distributions across human and agent corpora.

