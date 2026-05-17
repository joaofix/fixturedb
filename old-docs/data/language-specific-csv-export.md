# Fixture CSV Export Guide

## Overview

The exporter generates a cross-language CSV file with context columns (repository, file path, github_url) and quantitative metrics for all fixtures.

## Usage

Export the dataset:

```bash
python pipeline.py export --version 1.0
```

This generates:
- `export/fixturedb_v<version>_<date>/` directory containing:
  - `fixtures.db` — Full SQLite database with raw source code
  - `repositories.csv` — Repository metadata (200 repositories)
  - `repository_statistics.csv` — Aggregated fixture metrics per repository (NEW)
  - `test_files.csv` — Test file listing (257,764 test files)
  - `test_file_statistics.csv` — Aggregated fixture metrics per test file (NEW)
  - `fixtures.csv` — All fixture definitions (35,169 individual fixtures)
  - `stats.txt` — Summary statistics by language
  - `README.txt` — Complete schema documentation

The directory is zipped into `fixturedb_v<version>_<date>.zip` for upload to Zenodo.

## Analyzing by Language

The `fixtures.csv` file includes the `language` column. Filter by language in your analysis tool:

**Python:**
```python
import pandas as pd
df = pd.read_csv('fixtures.csv')
df_python = df[df['language'] == 'python']
print(f"Python fixtures: {len(df_python)}")
```

**SQL (SQLite):**
```sql
SELECT language, COUNT(*) FROM fixtures WHERE language='java' GROUP BY language;
```

See [CSV User Guide](csv-user-guide.md) for full column descriptions and analysis examples.

**Analyze mock usage patterns:**
```python
# Repos using mocks extensively
mock_heavy = df_python[df_python['num_mocks'] > 0].groupby('full_name').agg({
    'fixture_id': 'count',
    'num_mocks': 'sum',
    'stars': 'first'
}).sort_values('num_mocks', ascending=False)
```

**Distribution analysis:**
```python
# LOC distribution
print(df_python['loc'].describe())

# Complexity distribution
print(df_python['cyclomatic_complexity'].value_counts().sort_index())
```

## Design Decisions

### Why counts instead of joining tables?

The CSV format uses **aggregated mock counts** rather than requiring joins back to the database:
- More accessible to non-programmers
- Self-contained for easy distribution to Zenodo
- Faster exploratory analysis with pandas
- Database remains the source of truth for detailed queries

### Why one row per fixture?

- Aligns with typical data analysis workflows (one observation per row)
- Easier to compute statistics and distributions
- Straightforward to filter and aggregate
- Reduces redundancy compared to denormalized alternatives

### Why separate CSVs per language?

- Clearer organization for domain-specific analysis
- Smaller file sizes for targeted studies
- Simpler queries when focusing on one language
- Standard practice in multi-language repositories

## Integration with Zenodo

The exported archive is ready for Zenodo:
1. SQLite database provides full queryability
2. CSV files provide accessible analysis-ready datasets
3. README.txt documents the schema
4. stats.txt shows the corpus scope

Include citation in `README.txt`:
```
TODO: Citation information
```
