# Using the Dataset for Research

FixtureDB offers two complementary analysis pathways, suited to different research needs and tool preferences:

## Two Main Use Cases

### **Use Case 1: SQLite Database** (`fixtures.db`)
**Best for:** Complex queries, joins across tables, reproducibility verification, custom analysis  
**Access methods:** `sqlite3` CLI, Python (`sqlite3` module), R (`RSQLite` package), SQL IDE (DBeaver, SQLiteStudio)  
**Data scope:** Full database with all fields, internal infrastructure, complete extraction history  
**Advantages:**
- Powerful joins across repositories, test files, fixtures, and mock usages
- Filter by multiple criteria simultaneously (language, star tier, complexity, domain)
- Verify extraction decisions and explore raw source code
- No data loss—nothing is filtered out

### **Use Case 2: CSV Exports** (`fixtures.csv`, `repositories.csv`, `test_files.csv`)
**Best for:** Quick analysis, non-SQL users, Excel/Python/R workflows, reproducible papers  
**Access methods:** Excel, Google Sheets, Python (pandas, polars), R (readr, data.table), SQL imports  
**Data scope:** Curated quantitative metrics only (no raw source code); mock analysis via SQLite database  
**Advantages:**
- No database knowledge required
- Works in any spreadsheet application
- Cross-language data with language column for filtering
- Column documentation in [docs/data/csv-export-guide.md](../data/csv-export-guide.md)

---

## Use Case 1: Querying the SQLite Database

Query directly with `sqlite3` CLI, Python, R, or SQL IDE (DBeaver, SQLiteStudio).

**Example: Python + Pandas**

```python
import sqlite3
import pandas as pd

conn = sqlite3.connect("fixtures.db")

# All Python fixtures with complexity metrics
df = pd.read_sql("""
    SELECT f.name, f.fixture_type, f.scope, f.loc,
           f.cyclomatic_complexity, f.num_external_calls,
           r.full_name, r.domain, r.stars
    FROM fixtures f
    JOIN repositories r ON f.repo_id = r.id
    WHERE r.language = 'python' AND r.status = 'analysed'
""", conn)

# Mock adoption rate
pd.read_sql("""
    SELECT r.language,
           COUNT(DISTINCT f.id) AS total_fixtures,
           ROUND(COUNT(DISTINCT m.fixture_id) * 100.0
                 / COUNT(DISTINCT f.id), 1) AS pct_with_mocks
    FROM fixtures f
    JOIN repositories r ON f.repo_id = r.id
    LEFT JOIN mock_usages m ON m.fixture_id = f.id
    WHERE r.status = 'analysed'
    GROUP BY r.language
""", conn)
```

**Raw source inspection:**

```python
# Retrieve full source code for a specific fixture
df = pd.read_sql("""
    SELECT f.name, f.fixture_type, f.raw_source, r.full_name
    FROM fixtures f
    JOIN repositories r ON f.repo_id = r.id
    WHERE f.name = 'setup_database' AND r.language = 'python'
""", conn)
print(df['raw_source'].iloc[0])

---

## Use Case 2: Analyzing CSV Exports

Pre-normalized CSVs with context columns (repo name, file path, github_url) for spreadsheet and statistical software. Quantitative metrics only; raw source and detailed mock analysis available in SQLite database.

**Available files:**
- `fixtures.csv` — All fixtures, all languages (~35K rows)
- `repositories.csv` — Repository metadata (200 rows)
- `test_files.csv` — Test file listing (~257K rows)

See [csv-export-guide.md](../data/csv-export-guide.md) for full column documentation.

**Example: Python + Pandas**

```python
import pandas as pd

# Load fixtures
fixtures = pd.read_csv("fixtures.csv")

# Filter by language
python_fixtures = fixtures[fixtures['language'] == 'python']
print(f"Python fixtures: {len(python_fixtures)}")

# Complex fixtures (cyclomatic complexity > 5)
complex_fixtures = fixtures[fixtures['cyclomatic_complexity'] > 5]
print(f"Complex fixtures: {len(complex_fixtures)}")

# Fixtures with teardown pairs (cleanup code)
with_teardown = fixtures[fixtures['has_teardown_pair'] == True]
print(f"With teardown: {len(with_teardown)}")

# Average complexity by scope
print(fixtures.groupby('scope')['cyclomatic_complexity'].mean())

# Most reused fixtures
print(fixtures.nlargest(10, 'reuse_count')[['name', 'repo', 'reuse_count']])
```

**Excel / Spreadsheet:**
- Open `fixtures.csv` directly
- Filter by `language` column to focus on specific languages
- Use Pivot Tables to summarize by language, fixture_type, scope
- Use VLOOKUP to join with `repositories.csv` for star counts

---

## Key Differences: SQLite vs. CSV

| Aspect | SQLite | CSV |
|--------|--------|-----|
| **Setup** | None; just open the `.db` file | None; just open `.csv` file |
| **Querying** | SQL joins across 4 tables (fixtures, repositories, test_files, mock_usages) | Spreadsheet operations or pandas/R imports |
| **Data completeness** | Full: all fields, raw source code, extraction metadata, detailed mock analysis | Curated: quantitative metrics only |
| **Filtering complexity** | Easy: complex WHERE clauses and aggregations | Moderate: requires spreadsheet functions or code |
| **Performance** | Fast even for large queries | Good for files <100k rows; slower for full dataset |
| **Best for** | Verification, custom analysis, reproducibility, mock framework analysis | Quick summaries, Excel workflows, sharing with colleagues |

---

## Common Analyses

### "How many Python fixtures have high cyclomatic complexity?"

**SQLite:**
```sql
SELECT 
    COUNT(*) as count,
    ROUND(AVG(cyclomatic_complexity), 2) as avg_complexity
FROM fixtures f
JOIN repositories r ON f.repo_id = r.id
WHERE r.language = 'python' AND r.status = 'analysed'
  AND f.cyclomatic_complexity > 5;
```

**CSV (Python):**
```python
fixtures = pd.read_csv("fixtures.csv")
python_complex = fixtures[
    (fixtures['language'] == 'python') & 
    (fixtures['cyclomatic_complexity'] > 5)
]
print(f"Count: {len(python_complex)}")
print(f"Avg complexity: {python_complex['cyclomatic_complexity'].mean():.2f}")
```

---

## Need help?

- **CSV column meanings:** See [docs/csv-export-guide.md](../data/csv-export-guide.md)
- **Full CSV guide with tool-specific walkthrough:** See [docs/csv-user-guide.md](../data/csv-user-guide.md)
- **Schema details:** See [docs/database-schema.md](../architecture/database-schema.md)
