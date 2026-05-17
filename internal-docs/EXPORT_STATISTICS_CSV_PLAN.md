# Implementation Plan: Per-Repository and Per-File Statistics CSV Files

**Date:** May 12, 2026  
**Purpose:** Design schema and implementation approach for two new CSV exports to provide aggregated statistics

---

## 1. Current Export Structure

### Current Files (4 CSV + 1 SQLite)

```
export/fixturedb_v1.0_20260511/
├── fixtures.db                 (SQLite: complete raw data)
├── repositories.csv            (200 rows: repo metadata)
├── test_files.csv              (257,764 rows: file-level data)
├── fixtures.csv                (35,169 rows: fixture-level data)
├── README.txt                  (schema documentation)
└── stats.txt                   (summary statistics by language)
```

**Current Scope:**
- repositories.csv: Basic repo metadata (name, language, stars, forks, contributors, pinned_commit)
- test_files.csv: File-level metadata (path, language, LOC, test count, fixture count)
- fixtures.csv: Individual fixture data (type, scope, framework, metrics)

**Problem:** No aggregated statistics at repository or file level
- Researchers must aggregate fixture data themselves
- No readily available summary statistics
- Harder to answer "per-repo" and "per-file" questions

---

## 2. Proposed New Files

### File 1: `repository_statistics.csv`

**Purpose:** Aggregated fixture metrics per repository (200 rows)

**Motivation:**
- Answer questions like: "What's the average fixture complexity per language?"
- Enable repository-level analysis
- Support repository maturity assessments
- Reduce query complexity for common analyses

**Key Metrics Included:**
- Fixture counts (total, by type, by scope, by framework)
- Complexity statistics (avg/min/max cyclomatic complexity)
- Code quality metrics (avg LOC, avg nesting depth, etc.)
- Mock and test function counts
- Repository maturity indicators (total LOC, contributor count, star tier)

### File 2: `test_file_statistics.csv`

**Purpose:** Aggregated fixture metrics per test file (257,764 rows)

**Motivation:**
- Bridge between repository and fixture level analysis
- Enable file-level pattern analysis
- Support test suite quality metrics
- Identify high-complexity test files

**Key Metrics Included:**
- Fixture statistics per file (count, totals, averages)
- Complexity distributions per file
- Framework and scope distributions
- File complexity burden (total complexity, avg per fixture)

---

## 3. Detailed Schema: repository_statistics.csv

### Column Definitions (36 columns)

```csv
repository_id,
full_name,
language,
github_id,
stars,
forks,
num_contributors,
pinned_commit,
domain,

num_test_files,
total_test_file_loc,
avg_test_file_loc,

num_fixtures_total,
num_fixtures_per_test,
num_fixtures_per_class,
num_fixtures_per_module,
num_fixtures_global,

num_fixture_types_unique,
top_fixture_type,
top_fixture_type_count,

num_frameworks_unique,
top_framework,
top_framework_count,

avg_fixture_loc,
min_fixture_loc,
max_fixture_loc,
median_fixture_loc,
stddev_fixture_loc,

avg_cyclomatic_complexity,
min_cyclomatic_complexity,
max_cyclomatic_complexity,
median_cyclomatic_complexity,

avg_max_nesting_depth,
max_nesting_depth_overall,

avg_num_parameters,
avg_num_external_calls,
avg_num_objects_instantiated,

fixtures_with_teardown_count,
teardown_adoption_rate,

total_mock_usages,
avg_mocks_per_fixture,

total_test_functions,
avg_fixtures_per_test_file
```

### SQL Query Template

```sql
SELECT
    r.id AS repository_id,
    r.full_name,
    r.language,
    r.github_id,
    r.stars,
    r.forks,
    r.num_contributors,
    r.pinned_commit,
    r.domain,
    
    -- Test file metrics
    COUNT(DISTINCT tf.id) AS num_test_files,
    SUM(tf.file_loc) AS total_test_file_loc,
    ROUND(AVG(tf.file_loc), 2) AS avg_test_file_loc,
    
    -- Fixture counts
    COUNT(DISTINCT f.id) AS num_fixtures_total,
    SUM(CASE WHEN f.scope = 'per_test' THEN 1 ELSE 0 END) AS num_fixtures_per_test,
    SUM(CASE WHEN f.scope = 'per_class' THEN 1 ELSE 0 END) AS num_fixtures_per_class,
    SUM(CASE WHEN f.scope = 'per_module' THEN 1 ELSE 0 END) AS num_fixtures_per_module,
    SUM(CASE WHEN f.scope = 'global' THEN 1 ELSE 0 END) AS num_fixtures_global,
    
    -- Fixture type diversity
    COUNT(DISTINCT f.fixture_type) AS num_fixture_types_unique,
    (SELECT f2.fixture_type FROM fixtures f2 WHERE f2.repo_id = r.id 
     GROUP BY f2.fixture_type ORDER BY COUNT(*) DESC LIMIT 1) AS top_fixture_type,
    (SELECT COUNT(*) FROM fixtures f2 WHERE f2.repo_id = r.id 
     AND f2.fixture_type = (SELECT f3.fixture_type FROM fixtures f3 WHERE f3.repo_id = r.id 
                            GROUP BY f3.fixture_type ORDER BY COUNT(*) DESC LIMIT 1)) AS top_fixture_type_count,
    
    -- Framework diversity
    COUNT(DISTINCT f.framework) AS num_frameworks_unique,
    (SELECT f2.framework FROM fixtures f2 WHERE f2.repo_id = r.id 
     GROUP BY f2.framework ORDER BY COUNT(*) DESC LIMIT 1) AS top_framework,
    (SELECT COUNT(*) FROM fixtures f2 WHERE f2.repo_id = r.id 
     AND f2.framework = (SELECT f3.framework FROM fixtures f3 WHERE f3.repo_id = r.id 
                         GROUP BY f3.framework ORDER BY COUNT(*) DESC LIMIT 1)) AS top_framework_count,
    
    -- LOC statistics
    ROUND(AVG(f.loc), 2) AS avg_fixture_loc,
    MIN(f.loc) AS min_fixture_loc,
    MAX(f.loc) AS max_fixture_loc,
    (SELECT PERCENTILE_CONT(0.5) WITHIN GROUP(ORDER BY f2.loc)
     FROM fixtures f2 WHERE f2.repo_id = r.id) AS median_fixture_loc,
    ROUND(SQRT(AVG((f.loc - (SELECT AVG(f3.loc) FROM fixtures f3 WHERE f3.repo_id = r.id)) * 
                   (f.loc - (SELECT AVG(f4.loc) FROM fixtures f4 WHERE f4.repo_id = r.id)))), 2) AS stddev_fixture_loc,
    
    -- Complexity statistics
    ROUND(AVG(f.cyclomatic_complexity), 2) AS avg_cyclomatic_complexity,
    MIN(f.cyclomatic_complexity) AS min_cyclomatic_complexity,
    MAX(f.cyclomatic_complexity) AS max_cyclomatic_complexity,
    (SELECT PERCENTILE_CONT(0.5) WITHIN GROUP(ORDER BY f2.cyclomatic_complexity)
     FROM fixtures f2 WHERE f2.repo_id = r.id) AS median_cyclomatic_complexity,
    
    -- Nesting depth statistics
    ROUND(AVG(f.max_nesting_depth), 2) AS avg_max_nesting_depth,
    MAX(f.max_nesting_depth) AS max_nesting_depth_overall,
    
    -- Parameter and call statistics
    ROUND(AVG(f.num_parameters), 2) AS avg_num_parameters,
    ROUND(AVG(f.num_external_calls), 2) AS avg_num_external_calls,
    ROUND(AVG(f.num_objects_instantiated), 2) AS avg_num_objects_instantiated,
    
    -- Teardown adoption
    SUM(CASE WHEN f.has_teardown_pair = 1 THEN 1 ELSE 0 END) AS fixtures_with_teardown_count,
    ROUND(100.0 * SUM(CASE WHEN f.has_teardown_pair = 1 THEN 1 ELSE 0 END) / 
          COUNT(DISTINCT f.id), 2) AS teardown_adoption_rate,
    
    -- Mock usage
    SUM(f.num_mocks) AS total_mock_usages,
    ROUND(AVG(f.num_mocks), 2) AS avg_mocks_per_fixture,
    
    -- Test function metrics
    SUM(tf.num_test_funcs) AS total_test_functions,
    ROUND(AVG(tf.num_fixtures), 2) AS avg_fixtures_per_test_file

FROM repositories r
LEFT JOIN test_files tf ON r.id = tf.repo_id
LEFT JOIN fixtures f ON r.id = f.repo_id
WHERE r.status = 'analysed'
GROUP BY r.id, r.full_name, r.language, r.github_id, r.stars, r.forks, 
         r.num_contributors, r.pinned_commit, r.domain
ORDER BY r.full_name
```

### Schema Notes

- **IDs:** repository_id kept for joining with other CSVs
- **Counts:** Distinct counts to avoid double-counting from joins
- **Statistics:** Min, max, median, stddev, and avg for key metrics
- **Aggregations:** Scope and framework distributions as separate columns
- **Adoption Rates:** Percentage columns (teardown_adoption_rate, etc.)
- **Top Values:** Most common fixture type and framework in repo

---

## 4. Detailed Schema: test_file_statistics.csv

### Column Definitions (30 columns)

```csv
test_file_id,
repository_id,
full_name,
language,
relative_path,
file_loc,

num_fixtures_total,
num_fixtures_per_test,
num_fixtures_per_class,
num_fixtures_per_module,
num_fixtures_global,

num_fixture_types_unique,
top_fixture_type,

num_frameworks_unique,
top_framework,

total_fixture_loc,
avg_fixture_loc,
min_fixture_loc,
max_fixture_loc,

avg_cyclomatic_complexity,
min_cyclomatic_complexity,
max_cyclomatic_complexity,

avg_max_nesting_depth,

avg_num_parameters,
avg_num_external_calls,

fixtures_with_teardown_count,
teardown_adoption_rate,

total_mock_usages,

num_test_functions
```

### SQL Query Template

```sql
SELECT
    tf.id AS test_file_id,
    r.id AS repository_id,
    r.full_name,
    tf.language,
    tf.relative_path,
    tf.file_loc,
    
    -- Fixture counts
    COUNT(DISTINCT f.id) AS num_fixtures_total,
    SUM(CASE WHEN f.scope = 'per_test' THEN 1 ELSE 0 END) AS num_fixtures_per_test,
    SUM(CASE WHEN f.scope = 'per_class' THEN 1 ELSE 0 END) AS num_fixtures_per_class,
    SUM(CASE WHEN f.scope = 'per_module' THEN 1 ELSE 0 END) AS num_fixtures_per_module,
    SUM(CASE WHEN f.scope = 'global' THEN 1 ELSE 0 END) AS num_fixtures_global,
    
    -- Diversity metrics
    COUNT(DISTINCT f.fixture_type) AS num_fixture_types_unique,
    (SELECT f2.fixture_type FROM fixtures f2 WHERE f2.file_id = tf.id 
     GROUP BY f2.fixture_type ORDER BY COUNT(*) DESC LIMIT 1) AS top_fixture_type,
    
    COUNT(DISTINCT f.framework) AS num_frameworks_unique,
    (SELECT f2.framework FROM fixtures f2 WHERE f2.file_id = tf.id 
     GROUP BY f2.framework ORDER BY COUNT(*) DESC LIMIT 1) AS top_framework,
    
    -- LOC statistics
    SUM(f.loc) AS total_fixture_loc,
    ROUND(AVG(f.loc), 2) AS avg_fixture_loc,
    MIN(f.loc) AS min_fixture_loc,
    MAX(f.loc) AS max_fixture_loc,
    
    -- Complexity statistics
    ROUND(AVG(f.cyclomatic_complexity), 2) AS avg_cyclomatic_complexity,
    MIN(f.cyclomatic_complexity) AS min_cyclomatic_complexity,
    MAX(f.cyclomatic_complexity) AS max_cyclomatic_complexity,
    
    -- Nesting depth
    ROUND(AVG(f.max_nesting_depth), 2) AS avg_max_nesting_depth,
    
    -- Parameter and call statistics
    ROUND(AVG(f.num_parameters), 2) AS avg_num_parameters,
    ROUND(AVG(f.num_external_calls), 2) AS avg_num_external_calls,
    
    -- Teardown adoption
    SUM(CASE WHEN f.has_teardown_pair = 1 THEN 1 ELSE 0 END) AS fixtures_with_teardown_count,
    ROUND(100.0 * SUM(CASE WHEN f.has_teardown_pair = 1 THEN 1 ELSE 0 END) / 
          NULLIF(COUNT(DISTINCT f.id), 0), 2) AS teardown_adoption_rate,
    
    -- Mock usage
    SUM(f.num_mocks) AS total_mock_usages,
    
    -- Test functions
    tf.num_test_funcs

FROM test_files tf
LEFT JOIN repositories r ON tf.repo_id = r.id
LEFT JOIN fixtures f ON tf.id = f.file_id
WHERE r.status = 'analysed'
GROUP BY tf.id, r.id, r.full_name, tf.language, tf.relative_path, tf.file_loc, tf.num_test_funcs
ORDER BY r.full_name, tf.relative_path
```

### Schema Notes

- **IDs:** test_file_id and repository_id for joining
- **Context:** full_name, language, relative_path for human readability
- **File Size:** file_loc as baseline
- **Aggregations:** Scope distribution, type/framework diversity
- **Metrics:** Same aggregations as repository level but per file
- **Completeness:** Handle empty files (no fixtures) gracefully with NULLIF

---

## 5. Example Data: repository_statistics.csv

### Sample Row (pytest repo)

```
repository_id: 42
full_name: pytest-dev/pytest
language: python
github_id: 636362
stars: 12500
forks: 1200
num_contributors: 450
pinned_commit: 8a3f2b1c9e7d5f4a
domain: library

num_test_files: 125
total_test_file_loc: 45820
avg_test_file_loc: 366.56

num_fixtures_total: 1850
num_fixtures_per_test: 1520
num_fixtures_per_class: 280
num_fixtures_per_module: 45
num_fixtures_global: 5

num_fixture_types_unique: 4
top_fixture_type: pytest_decorator
top_fixture_type_count: 1680

num_frameworks_unique: 1
top_framework: pytest
top_framework_count: 1850

avg_fixture_loc: 12.5
min_fixture_loc: 1
max_fixture_loc: 87
median_fixture_loc: 9.0
stddev_fixture_loc: 18.3

avg_cyclomatic_complexity: 2.3
min_cyclomatic_complexity: 1
max_cyclomatic_complexity: 28
median_cyclomatic_complexity: 2.0

avg_max_nesting_depth: 1.8
max_nesting_depth_overall: 6

avg_num_parameters: 1.2
avg_num_external_calls: 0.45
avg_num_objects_instantiated: 0.12

fixtures_with_teardown_count: 420
teardown_adoption_rate: 22.7

total_mock_usages: 185
avg_mocks_per_fixture: 0.1

total_test_functions: 2340
avg_fixtures_per_test_file: 14.8
```

---

## 6. Example Data: test_file_statistics.csv

### Sample Row (pytest test file)

```
test_file_id: 8934
repository_id: 42
full_name: pytest-dev/pytest
language: python
relative_path: testing/test_fixtures.py
file_loc: 1245

num_fixtures_total: 15
num_fixtures_per_test: 12
num_fixtures_per_class: 3
num_fixtures_per_module: 0
num_fixtures_global: 0

num_fixture_types_unique: 1
top_fixture_type: pytest_decorator

num_frameworks_unique: 1
top_framework: pytest

total_fixture_loc: 185
avg_fixture_loc: 12.3
min_fixture_loc: 2
max_fixture_loc: 45

avg_cyclomatic_complexity: 1.9
min_cyclomatic_complexity: 1
max_cyclomatic_complexity: 4

avg_max_nesting_depth: 1.5

avg_num_parameters: 1.1
avg_num_external_calls: 0.2

fixtures_with_teardown_count: 2
teardown_adoption_rate: 13.3

total_mock_usages: 3

num_test_functions: 18
```

---

## 7. Implementation Approach

### Phase 1: Code Changes (collection/exporter.py)

**New Functions:**

1. `_export_repository_statistics(conn, export_dir)`
   - Executes SQL query for repository stats
   - Creates repository_statistics.csv
   - Handles NULL values, rounds floats

2. `_export_test_file_statistics(conn, export_dir)`
   - Executes SQL query for test file stats
   - Creates test_file_statistics.csv
   - Handles empty test files gracefully

3. Update `export_dataset()` main function
   - Call both new export functions
   - Update README with new columns
   - Include in zip archive

### Phase 2: Documentation Updates

**Files to Update:**

1. `docs/data/csv-export-guide.md`
   - Add sections for two new files
   - Column descriptions and use cases
   - Example queries

2. `docs/reference/limitations.md`
   - Note on aggregation rounding
   - PERCENTILE_CONT SQL function requirements

3. `collection/exporter.py` docstring
   - Update file list

### Phase 3: Testing

**New Tests:**

1. `tests/test_export/test_export_statistics.py`
   - Verify repository_statistics.csv structure
   - Verify test_file_statistics.csv structure
   - Test aggregation calculations (manual spot-checks)
   - Test edge cases (empty repos, single-file repos)

2. Update `tests/test_export/test_export_core.py`
   - Include new CSV files in full export test
   - Verify row counts in README

### Phase 4: Integration

**Files Updated:**

1. `collection/exporter.py` (120+ lines added)
2. `docs/data/csv-export-guide.md` (50+ lines added)
3. Tests (100+ lines added)
4. README.txt (30+ lines updated)

---

## 8. File Organization in Export

### Updated Export Structure

```
export/fixturedb_v1.0_20260512/
├── fixtures.db                         (SQLite: complete raw data)
├── repositories.csv                    (200 rows: repo metadata)
├── repository_statistics.csv           (200 rows: NEW - aggregated repo stats)
├── test_files.csv                      (257,764 rows: file metadata)
├── test_file_statistics.csv            (257,764 rows: NEW - aggregated file stats)
├── fixtures.csv                        (35,169 rows: fixture-level data)
├── README.txt                          (updated schema documentation)
└── stats.txt                           (summary statistics by language)
```

**Zip File Name:** `fixturedb_v1.0_20260512.zip` (now 2-3 MB larger due to new CSVs)

---

## 9. Research Use Cases

### repository_statistics.csv Enables:

1. **Repository Maturity Analysis**
   - Correlation between stars/forks and fixture complexity
   - Average complexity by language
   - Teardown adoption trends

2. **Language Comparisons**
   - Fixture patterns per language (e.g., "Python uses 12% more teardowns than Java")
   - Scope distribution by language
   - Framework adoption rates

3. **Quality Assessments**
   - Identify high-complexity repositories
   - Track fixture reuse patterns
   - Measure mock adoption per repository

### test_file_statistics.csv Enables:

1. **Test Suite Quality**
   - Identify high-complexity test files
   - Measure test file organization (fixtures per file)
   - Compare file-level patterns

2. **Test Maintenance Insights**
   - Fixture complexity distribution within files
   - Correlation between file LOC and fixture complexity
   - Test function-to-fixture ratios

3. **Granular Analysis**
   - Per-file trend analysis
   - Exception detection (unusually complex files)
   - Complexity patterns within repositories

---

## 10. SQL Considerations

### Aggregation Functions Used

- **COUNT(DISTINCT ...)** — Avoid double-counting from joins
- **SUM(CASE WHEN ...)** — Conditional aggregation for scope counts
- **AVG(), MIN(), MAX()** — Standard aggregations
- **PERCENTILE_CONT()** — Median calculation (standard SQL)

### SQLite Compatibility Notes

**Issue:** SQLite doesn't support `PERCENTILE_CONT()` natively

**Solutions:**
1. Use Python pandas to calculate percentiles post-query
2. Approximate median with `MEDIAN()` aggregate function
3. Skip median for SQLite version

**Recommended:** Solution 2 - use pandas post-processing

```python
# In _export_repository_statistics()
conn = sqlite3.connect(db_path)
df = pd.read_sql_query(query, conn)
# Calculate percentiles in pandas
df['median_fixture_loc'] = df.groupby('repository_id')['fixture_loc'].transform('median')
```

---

## 11. Validation & Testing Strategy

### Validation Checks

1. **Row Counts**
   - repository_statistics.csv: exactly 200 rows (one per analyzed repo)
   - test_file_statistics.csv: exactly 257,764 rows (one per test file)

2. **Data Integrity**
   - No negative values (except for calculations)
   - Sums add up: `sum(per_scope_counts) == num_fixtures_total`
   - Top values are actually most common

3. **Edge Cases**
   - Repos with no fixtures → all counts 0
   - Test files with no fixtures → avoid division by zero
   - Single-fixture repos → no stddev issues

### Manual Spot-Checks

```python
# Verify aggregations by random sampling
sample_repo = 'pytest-dev/pytest'
manual_avg_cc = (SELECT AVG(cyclomatic_complexity) FROM fixtures WHERE repo_id = ...)
csv_avg_cc = (read from repository_statistics.csv)
assert abs(manual_avg_cc - csv_avg_cc) < 0.01  # Allow for rounding
```

---

## 12. Implementation Checklist

### Pre-Implementation
- [ ] Review and approve schema designs
- [ ] Confirm SQL function compatibility with SQLite/Pandas
- [ ] Identify any missing metrics or columns

### Implementation
- [ ] Add SQL queries to exporter.py
- [ ] Add _export_repository_statistics() function
- [ ] Add _export_test_file_statistics() function
- [ ] Update export_dataset() to call new functions
- [ ] Update README.txt template with new file sections
- [ ] Add error handling for NULL values

### Testing
- [ ] Write unit tests for both export functions
- [ ] Test with actual database (not mocked)
- [ ] Verify row counts match expectations
- [ ] Spot-check aggregation calculations
- [ ] Test edge cases (empty repos, single files)

### Documentation
- [ ] Update csv-export-guide.md with new files
- [ ] Add column descriptions and use cases
- [ ] Update README.txt in export template
- [ ] Add example queries to guide
- [ ] Document SQL function requirements

### Integration
- [ ] Update pipeline.py export command
- [ ] Test full export workflow (extract → export)
- [ ] Verify ZIP file contents
- [ ] Update version/date in export name

---

## 13. Migration Path

### If Adding to Existing Export

For v1.0 already released:

1. **v1.1 (Next Release)**
   - Include new CSV files in export
   - Update README schema
   - Maintain backward compatibility (old files still present)

2. **Version Numbering**
   - `fixturedb_v1.0_...` (original, no stats CSVs)
   - `fixturedb_v1.1_...` (with new stats CSVs)

### If Starting Fresh Export

For new release:
- Simply include both new files from start
- No migration needed

---

## 14. Performance Considerations

### Query Performance

**Expected Execution Time:**
- repository_statistics: ~5-10 seconds (200 rows, complex aggregations)
- test_file_statistics: ~30-60 seconds (257,764 rows with joins)

**Optimization:**
- Create temporary indexes on (repo_id, file_id) if slow
- Run aggregations in separate transactions
- Cache intermediate results if needed

### File Size

**Expected Size:**
- repository_statistics.csv: ~50 KB (200 rows × 36 columns)
- test_file_statistics.csv: ~150-200 MB (257,764 rows × 30 columns)

**Total Archive Size Increase:** ~150-200 MB (from ~25 MB to ~175-225 MB)

---

## Next Steps

1. **Design Review:** Confirm schema columns and calculations
2. **SQL Validation:** Test queries against actual database
3. **Prototype:** Implement sample export with first 10 repos
4. **Testing:** Develop unit tests
5. **Documentation:** Update all guides
6. **Integration:** Add to main export pipeline
7. **Release:** Include in v1.1 (or next release)

---

**Document Status:** Implementation Plan Complete

**Ready for:** Feedback, Schema Review, SQL Validation

**Estimated Implementation Time:** 6-8 hours (including tests + docs)
