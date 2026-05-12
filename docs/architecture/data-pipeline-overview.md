# Data Pipeline: Collection → Counting → Export

## Overview Diagram

```
GitHub Repositories
        ↓
    Search & Clone
        ↓
    Extract Fixtures
        ↓
  Calculate Metrics
        ↓
  Store in Database
    (SQLite)
        ↓
    Export Dataset
        ├── fixtures.db (full database)
        ├── repositories.csv (metadata)
        ├── repository_statistics.csv (aggregated per repo) [NEW]
        ├── test_files.csv (with repo context)
        ├── test_file_statistics.csv (aggregated per file) [NEW]
        ├── fixtures.csv (individual fixtures)
        └── stats.txt
                ↓
           Zenodo Archive
```

## 1. Database Schema

The `repositories` table includes three count fields populated during extraction:

```sql
CREATE TABLE repositories (
    id              INTEGER PRIMARY KEY,
    github_id       INTEGER UNIQUE,
    full_name       TEXT,
    language        TEXT,
    stars           INTEGER,
    status          TEXT,  -- discovered|cloned|analysed|skipped|error
    num_test_files  INTEGER DEFAULT 0,
    num_fixtures    INTEGER DEFAULT 0,
    num_mock_usages INTEGER DEFAULT 0,
    collected_at    TEXT
);
```

## 2. Extraction Process

Extraction counts test files and fixtures per repository, stores in `repositories` table. See [collection/extractor.py](../../collection/detector.py) for implementation.

**Key counts set during extraction:**
- `num_test_files` — total test files found
- `num_fixtures` — aggregated fixture count across all test files  
- `num_mock_usages` — aggregated mock usage count

## 3. Querying the Data

**Example: Per-language statistics**

```sql
SELECT 
    language,
    COUNT(*) as num_repos,
    SUM(num_fixtures) as total_fixtures,
    AVG(num_fixtures) as avg_per_repo
FROM repositories
WHERE status = 'analysed'
GROUP BY language
ORDER BY total_fixtures DESC;
```

## 4. CSV Export

Export phase generates queryable database (`fixtures.db`) and user-friendly CSVs with human-readable context columns. See [collection/exporter.py](../../collection/exporter.py) for implementation.

**Generated files:**
- `fixtures.db` — Full SQLite database (all internal columns available, including mock_usages table)
- `repositories.csv` — Repository metadata with maturity metrics (stars, forks, contributors) and num_analyzed_fixtures count
- `repository_statistics.csv` — Aggregated fixture metrics per repository (complexity distribution, scope breakdown, framework diversity, teardown adoption)
- `test_files.csv` — Test file listing with repo name, language, and fixture counts
- `test_file_statistics.csv` — Aggregated fixture metrics per test file (for test suite quality analysis)
- `fixtures.csv` — Individual fixture definitions with quantitative metrics, fixture_type detection pattern, github_url for direct source access, and has_teardown_pair indicator
- `stats.txt` — Summary statistics by language

**Note:** Detailed mock framework analysis (`mock_usages` table) is available in SQLite database for researchers who need it; not exported to CSV for Zenodo distribution.

## 5. Data Flow

```
_find_test_files(repo) → num_test_files
    ↓
extract_fixtures() per file → metrics computed (LOC, complexity, etc.)
    ↓
detect_framework() & extract_mocks() → framework, mock patterns
    ↓
set_repo_analysed() → UPDATE repositories table
    ↓
During export: Query database with joins → CSV files with context columns
```

Metrics are computed once at extraction time. CSV exports add human-readable context (repo names, file paths, github_urls) via SQL joins during export.

## 6. Why This Design?

**Counts in Database** — Computed once at extraction, stored atomically. Fast queries, no repeated aggregation.

**Language-Specific CSVs** — Pre-aggregated views; accessible without database software.

**Both Database + CSVs** — Database is authoritative source; CSVs are published views. Enables both reproducibility (SQL) and accessibility (CSV).

## 7. See Also

- [language-specific-csv-export.md](../data/language-specific-csv-export.md) — CSV format and example analysis
