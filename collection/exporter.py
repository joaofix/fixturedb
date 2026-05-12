"""
Export utility — produces the Zenodo-ready dataset artifact.

Generates:
  export/fixturedb_v<version>_<date>/
  ├── fixtures.db               (full SQLite database with all tables)
  ├── repositories.csv          (200 repositories with maturity metrics)
  ├── test_files.csv            (257,764 test files with fixture counts)
  ├── fixtures.csv              (35,169 fixtures with metrics and GitHub links)
  ├── README.txt                (schema and column documentation)
  └── stats.txt                 (summary statistics by language)

Then zips everything into fixturedb_v<version>_<date>.zip.

CSV exports contain:
  - Quantitative metrics (LOC, complexity, counts, etc.)
  - Objective classifications (fixture_type, scope, framework)
  - Context for reproducibility (github_url, pinned_commit, file paths)
  - Excludes: raw source code (use SQLite for source), subjective categories

Full SQLite database includes all raw source code and internal tables
for transparency and future research.

Usage:
    python -m scripts.export --version 1.0
    # or
    python pipeline.py export
"""

import shutil
import sqlite3
import zipfile
import logging
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd

from collection.config import DB_PATH, ROOT_DIR

logger = logging.getLogger(__name__)

EXPORT_DIR = ROOT_DIR / "export"

# ---------------------------------------------------------------------------
# Column documentation for the README
# ---------------------------------------------------------------------------

SCHEMA_DOCS = """
FixtureDB — Dataset CSV Schema
==============================

This archive contains 5 CSV files plus a SQLite database:

1. REPOSITORIES.CSV
   One row per repository (200 total, status='analysed')
   
   Columns:
   - id                    Internal primary key
   - full_name             Repository slug: "owner/repo"
   - language              python | java | javascript | typescript
   - stars                 GitHub star count at collection time
   - forks                 GitHub fork count at collection time
   - num_contributors      GitHub contributor count (maturity metric)
   - num_analyzed_fixtures Total fixtures extracted from this repo
   - pinned_commit         SHA of analyzed commit (reproducibility)

2. REPOSITORY_STATISTICS.CSV
   Aggregated fixture metrics per repository (200 rows)
   
   Columns:
   - repository_id         Internal primary key
   - full_name             Repository slug: "owner/repo"
   - language              python | java | javascript | typescript
   - stars, forks, num_contributors  GitHub metrics
   - num_test_files        Count of test files analyzed
   - num_fixtures_total    Total fixtures in repository
   - num_fixtures_per_test / per_class / per_module / per_global
                          Fixture counts by scope
   - num_fixture_types_unique  Count of distinct fixture types
   - top_fixture_type, top_fixture_type_count  Most common type
   - num_frameworks_unique    Count of distinct frameworks
   - top_framework, top_framework_count  Most common framework
   - avg_fixture_loc, min/max/median_fixture_loc, stddev_fixture_loc
                          LOC statistics across fixtures
   - avg_cyclomatic_complexity, min/max/median_cyclomatic_complexity
                          Complexity statistics (McCabe)
   - avg_max_nesting_depth, max_nesting_depth_overall
                          Nesting depth statistics
   - avg_num_parameters, avg_num_external_calls, avg_num_objects_instantiated
                          Average counts for key metrics
   - fixtures_with_teardown_count, teardown_adoption_rate
                          Teardown/cleanup adoption metrics
   - total_mock_usages, avg_mocks_per_fixture
                          Mock usage patterns
   - total_test_functions, avg_fixtures_per_test_file
                          Test function and fixture distribution

3. TEST_FILES.CSV
   One row per test file (257,764 total)
   
   Columns:
   - id                    Internal primary key
   - repo                  Repository full_name for human readability
   - language              python | java | javascript | typescript
   - relative_path         Path relative to repository root
   - file_loc              Non-blank lines of code in test file
   - num_test_funcs        Count of test function definitions
   - num_fixtures          Count of fixture definitions in this file
   - total_fixture_loc     Sum of LOC across all fixtures in file

4. TEST_FILE_STATISTICS.CSV
   Aggregated fixture metrics per test file (257,764 rows, including files with 0 fixtures)
   
   Purpose: Enables test-file-level analysis without manual aggregation.
   Useful for: test suite complexity analysis, file quality metrics, fixture density patterns.
   
   Note: NULL values appear for aggregate columns when a file has 0 fixtures.
   This design preserves all test files for complete research datasets.
   
   Columns (grouped by category):
   
   Context & Metadata:
   - test_file_id          Internal primary key
   - repository_id         Reference to repository (matches repositories.csv id)
   - full_name             Repository slug: "owner/repo"
   - language              python | java | javascript | typescript
   - relative_path         Path relative to repository root
   - file_loc              Non-blank lines of code in file
   
   Fixture Counts by Scope:
   - num_fixtures_total    Total fixture definitions in file
   - num_fixtures_per_test Fixtures with per_test scope
   - num_fixtures_per_class Fixtures with per_class scope
   - num_fixtures_per_module Fixtures with per_module scope
   - num_fixtures_global   Fixtures with global scope
   
   Type & Framework Diversity:
   - num_fixture_types_unique  Count of distinct fixture type values
   - top_fixture_type      Most common fixture type in file
   - top_fixture_type_count Count of most common fixture type
   - num_frameworks_unique Count of distinct testing frameworks
   - top_framework         Most common testing framework in file
   - top_framework_count   Count of most common framework
   
   Fixture LOC Statistics:
   - total_fixture_loc     Sum of LOC across all fixtures in file
   - avg_fixture_loc       Average fixture LOC (NULL if 0 fixtures)
   - min_fixture_loc       Minimum fixture LOC (NULL if 0 fixtures)
   - max_fixture_loc       Maximum fixture LOC (NULL if 0 fixtures)
   - median_fixture_loc    Median fixture LOC (NULL if 0 fixtures)
   - stddev_fixture_loc    Standard deviation of fixture LOC (NULL if ≤1 fixture)
   
   Complexity Statistics:
   - avg_cyclomatic_complexity Average McCabe complexity (NULL if 0 fixtures)
   - min_cyclomatic_complexity Minimum complexity (NULL if 0 fixtures)
   - max_cyclomatic_complexity Maximum complexity (NULL if 0 fixtures)
   - median_cyclomatic_complexity Median complexity (NULL if 0 fixtures)
   
   Nesting & Structure:
   - avg_max_nesting_depth Average maximum nesting depth (NULL if 0 fixtures)
   - max_nesting_depth     Overall maximum nesting depth in file
   
   Metric Averages:
   - avg_num_parameters    Average parameters per fixture (NULL if 0 fixtures)
   - avg_num_external_calls Average external calls per fixture (NULL if 0 fixtures)
   - avg_num_objects_instantiated Average object instantiations (NULL if 0 fixtures)
   
   Teardown & Mock Usage:
   - fixtures_with_teardown_count Count of fixtures with teardown/cleanup logic
   - teardown_adoption_rate Percentage of fixtures with teardown (NULL if 0 fixtures)
   - total_mock_usages     Total mock framework usages across all fixtures
   
   Test Functions:
   - num_test_funcs        Count of test function definitions in file

5. FIXTURES.CSV
   One row per fixture definition (35,169 total)
   
   Columns (grouped by category):
   
   Context:
   - id                    Internal primary key
   - language              python | java | javascript | typescript
   - repo                  Repository full_name for human readability
   - file_path             Path relative to repository root
   - name                  Function/method name of the fixture
   
   Fixture Classification:
   - fixture_type          Detection pattern: pytest_decorator, unittest_setup,
                           junit4_before, junit5_before_each, before_each, etc.
   - framework             Testing framework: pytest, unittest, jest, mocha, junit, etc.
   - scope                 per_test | per_class | per_module | global
   
   Location & Size:
   - start_line            1-indexed start line in source file
   - end_line              1-indexed end line in source file
   - loc                   Non-blank lines of code
   
   Complexity:
   - cyclomatic_complexity 1 + number of branching statements (McCabe)
   - max_nesting_depth     Maximum block nesting level
   
   Dependencies & Structure:
   - num_parameters        Number of function parameters
   - num_objects_instantiated Estimated constructor calls inside fixture
   - num_external_calls    Estimated I/O / external API calls
   
   Reuse & Cleanup:
   - reuse_count           Number of test functions using this fixture
   - has_teardown_pair     Binary (0/1): fixture includes cleanup/teardown logic
   
   Reproducibility:
   - pinned_commit         SHA of analyzed commit (enables exact code reproduction)
   - github_url            Direct link to fixture on GitHub (click to view source)

FULL DATABASE
=============
For detailed analysis, use fixtures.db (SQLite 3):
  import sqlite3
  conn = sqlite3.connect("fixtures.db")
  df = pd.read_sql("SELECT * FROM fixtures", conn)

The database includes additional infrastructure columns (raw_source, category)
not exported to CSV. See database schema documentation for details.

LICENSES
========
Dataset: CC BY 4.0  (https://creativecommons.org/licenses/by/4.0/)
Source code: MIT
"""


# ---------------------------------------------------------------------------
# Export logic
# ---------------------------------------------------------------------------


def export_dataset(version: str = "1.0", include_raw_source: bool = False) -> Path:
    """
    Export the full dataset to EXPORT_DIR and produce a zip archive.
    Returns the path to the zip file.
    """
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    archive_name = f"fixturedb_v{version}_{timestamp}"
    staging = EXPORT_DIR / archive_name
    staging.mkdir(exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # --- SQLite copy ---
    dest_db = staging / "fixtures.db"
    shutil.copy2(DB_PATH, dest_db)
    logger.info(f"Copied database → {dest_db}")

    # --- CSV exports ---
    # repositories: with adoption metrics (stars, forks, num_contributors) and analysis counts
    _export_repositories(
        conn,
        staging / "repositories.csv",
    )
    # repository_statistics: aggregated metrics per repository
    _export_repository_statistics(
        conn,
        staging / "repository_statistics.csv",
    )
    # test_files: with repo context for researchers
    _export_test_files(
        conn,
        staging / "test_files.csv",
    )
    # test_file_statistics: aggregated metrics per test file
    _export_test_file_statistics(
        conn,
        staging / "test_file_statistics.csv",
    )
    # mock_usages: skip for now (not needed for Zenodo yet)
    # Will be added in future releases once validation is complete

    # fixtures: with github_url, fixture_type, and context (language, repo, file_path)
    # Excluded: category (subjective classification)
    # Included: fixture_type (quantitative detection method), has_teardown_pair (binary indicator)
    # Included: raw_source only if include_raw_source=True
    if include_raw_source:
        _export_fixtures_with_url(
            conn,
            staging / "fixtures_with_source.csv",
            include_raw_source=True,
        )
    else:
        _export_fixtures_with_url(
            conn,
            staging / "fixtures.csv",
            include_raw_source=False,
        )

    conn.close()

    # --- README ---
    readme = staging / "README.txt"
    _write_readme(readme, version)
    logger.info(f"Written README → {readme}")

    # --- Stats summary ---
    _write_stats(conn, staging / "stats.txt")

    # --- Zip ---
    zip_path = EXPORT_DIR / f"{archive_name}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in staging.rglob("*"):
            zf.write(f, f.relative_to(staging))

    logger.info(f"Archive ready → {zip_path}  ({zip_path.stat().st_size // 1024} KB)")
    return zip_path


def _export_table(
    conn: sqlite3.Connection, table: str, dest: Path, exclude_cols: list[str] = None
) -> None:
    exclude_cols = exclude_cols or []
    df = pd.read_sql(f"SELECT * FROM {table}", conn)
    if exclude_cols:
        df = df.drop(columns=[c for c in exclude_cols if c in df.columns])
    df.to_csv(dest, index=False)
    logger.info(f"  {table}: {len(df):,} rows → {dest.name}")


def _export_repositories(
    conn: sqlite3.Connection,
    dest: Path,
) -> None:
    """Export repositories with adoption and maturity metrics.
    
    Columns (in order):
      - Identifiers: id, github_id, full_name
      - Context: language
      - GitHub Metrics: stars, forks, num_contributors
      - Collection: created_at, pushed_at, pinned_commit
      - Dataset Info: num_test_files, num_fixtures, num_analyzed_fixtures, collected_at
    """
    query = """
    SELECT
        id,
        github_id,
        full_name,
        language,
        stars,
        forks,
        num_contributors,
        created_at,
        pushed_at,
        pinned_commit,
        num_test_files,
        num_fixtures,
        (SELECT COUNT(*) FROM fixtures WHERE repo_id = repositories.id) AS num_analyzed_fixtures,
        collected_at
    FROM repositories
    WHERE status = 'analysed'
    ORDER BY id
    """
    df = pd.read_sql(query, conn)
    df.to_csv(dest, index=False)
    logger.info(f"  repositories: {len(df):,} rows → {dest.name}")


def _export_test_files(
    conn: sqlite3.Connection,
    dest: Path,
) -> None:
    """Export test files with repository context.
    
    Columns (in order):
      - Identifiers: id
      - Context: repo (full_name), language, relative_path
      - Metrics: file_loc (file lines of code), num_test_funcs, num_fixtures, total_fixture_loc
    """
    query = """
    SELECT
        tf.id,
        r.full_name AS repo,
        tf.language,
        tf.relative_path,
        tf.file_loc,
        tf.num_test_funcs,
        tf.num_fixtures,
        tf.total_fixture_loc
    FROM test_files tf
    JOIN repositories r ON tf.repo_id = r.id
    ORDER BY tf.id
    """
    df = pd.read_sql(query, conn)
    df.to_csv(dest, index=False)
    logger.info(f"  test_files: {len(df):,} rows → {dest.name}")


def _export_fixtures_with_url(
    conn: sqlite3.Connection,
    dest: Path,
    include_raw_source: bool = False,
) -> None:
    """Export fixtures with computed github_url and context.
    
    Columns (in order):
      - Identifiers: id
      - Context: language, repo, file_path, name
      - Characteristics: fixture_type, framework, scope
      - Location: start_line, end_line
      - Structure: loc (lines of code)
      - Complexity: cyclomatic_complexity, max_nesting_depth
      - Behavior: num_parameters, num_objects_instantiated, num_external_calls
      - Reuse: reuse_count, has_teardown_pair
      - Reproducibility: pinned_commit, github_url
    """
    query = """
    SELECT
        f.id,
        r.language,
        r.full_name AS repo,
        tf.relative_path AS file_path,
        f.name,
        f.fixture_type,
        f.framework,
        f.scope,
        f.start_line,
        f.end_line,
        f.loc,
        f.cyclomatic_complexity,
        f.max_nesting_depth,
        f.num_parameters,
        f.num_objects_instantiated,
        f.num_external_calls,
        f.reuse_count,
        f.has_teardown_pair,
        r.pinned_commit,
        (CASE
            WHEN r.clone_url LIKE '%.git' 
            THEN SUBSTR(r.clone_url, 1, LENGTH(r.clone_url) - 4)
            ELSE r.clone_url
        END || '/blob/' || r.pinned_commit || '/' || tf.relative_path || '#L' || f.start_line) AS github_url
        """ + (", f.raw_source" if include_raw_source else "") + """
    FROM fixtures f
    JOIN repositories r ON f.repo_id = r.id
    JOIN test_files tf ON f.file_id = tf.id
    ORDER BY f.id
    """
    
    df = pd.read_sql(query, conn)
    df.to_csv(dest, index=False)
    logger.info(f"  fixtures: {len(df):,} rows → {dest.name}")


def _export_repository_statistics(
    conn: sqlite3.Connection,
    dest: Path,
) -> None:
    """Export aggregated fixture metrics per repository.
    
    Aggregates all fixtures in each repository to provide repository-level
    summary statistics. Includes complexity metrics, scope distribution, framework
    diversity, and teardown adoption rates.
    """
    query = """
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
        
        COUNT(DISTINCT tf.id) AS num_test_files,
        SUM(tf.file_loc) AS total_test_file_loc,
        ROUND(AVG(tf.file_loc), 2) AS avg_test_file_loc,
        
        COUNT(DISTINCT f.id) AS num_fixtures_total,
        SUM(CASE WHEN f.scope = 'per_test' THEN 1 ELSE 0 END) AS num_fixtures_per_test,
        SUM(CASE WHEN f.scope = 'per_class' THEN 1 ELSE 0 END) AS num_fixtures_per_class,
        SUM(CASE WHEN f.scope = 'per_module' THEN 1 ELSE 0 END) AS num_fixtures_per_module,
        SUM(CASE WHEN f.scope = 'global' THEN 1 ELSE 0 END) AS num_fixtures_global,
        
        COUNT(DISTINCT f.fixture_type) AS num_fixture_types_unique,
        COUNT(DISTINCT f.framework) AS num_frameworks_unique,
        
        ROUND(AVG(f.loc), 2) AS avg_fixture_loc,
        MIN(f.loc) AS min_fixture_loc,
        MAX(f.loc) AS max_fixture_loc,
        
        ROUND(AVG(f.cyclomatic_complexity), 2) AS avg_cyclomatic_complexity,
        MIN(f.cyclomatic_complexity) AS min_cyclomatic_complexity,
        MAX(f.cyclomatic_complexity) AS max_cyclomatic_complexity,
        
        ROUND(AVG(f.max_nesting_depth), 2) AS avg_max_nesting_depth,
        MAX(f.max_nesting_depth) AS max_nesting_depth_overall,
        
        ROUND(AVG(f.num_parameters), 2) AS avg_num_parameters,
        ROUND(AVG(f.num_external_calls), 2) AS avg_num_external_calls,
        ROUND(AVG(f.num_objects_instantiated), 2) AS avg_num_objects_instantiated,
        
        SUM(CASE WHEN f.has_teardown_pair = 1 THEN 1 ELSE 0 END) AS fixtures_with_teardown_count,
        ROUND(100.0 * SUM(CASE WHEN f.has_teardown_pair = 1 THEN 1 ELSE 0 END) / 
              NULLIF(COUNT(DISTINCT f.id), 0), 2) AS teardown_adoption_rate,
        
        COUNT(DISTINCT mu.id) AS total_mock_usages,
        ROUND(CAST(COUNT(DISTINCT mu.id) AS FLOAT) / NULLIF(COUNT(DISTINCT f.id), 0), 2) AS avg_mocks_per_fixture,
        
        SUM(tf.num_test_funcs) AS total_test_functions,
        ROUND(AVG(tf.num_fixtures), 2) AS avg_fixtures_per_test_file

    FROM repositories r
    LEFT JOIN test_files tf ON r.id = tf.repo_id
    LEFT JOIN fixtures f ON r.id = f.repo_id
    LEFT JOIN mock_usages mu ON f.id = mu.fixture_id
    WHERE r.status = 'analysed'
    GROUP BY r.id, r.full_name, r.language, r.github_id, r.stars, r.forks, 
             r.num_contributors, r.pinned_commit, r.domain
    ORDER BY r.full_name
    """
    
    try:
        df = pd.read_sql(query, conn)
    except Exception as e:
        logger.error(f"Failed to query repository_statistics from database: {e}")
        raise
    
    if df.empty:
        logger.warning("repository_statistics: No data returned from query")
        df.to_csv(dest, index=False)
        return
    
    # Calculate median and stddev using pandas (SQLite doesn't support PERCENTILE_CONT)
    # For each numeric column, we need to get raw fixture data for median/stddev calc
    fixture_query = """
    SELECT f.repo_id, f.loc, f.cyclomatic_complexity
    FROM fixtures f
    """
    fixture_df = pd.read_sql(fixture_query, conn)
    
    # Calculate per-repo statistics
    def calc_stats_by_repo(group_df, col):
        """Calculate median and stddev for a column by repo."""
        stats = {}
        for repo_id, group in group_df.groupby('repo_id'):
            values = group[col].dropna()
            if len(values) > 0:
                stats[repo_id] = {
                    'median': values.median(),
                    'stddev': values.std() if len(values) > 1 else 0.0
                }
            else:
                stats[repo_id] = {'median': None, 'stddev': None}
        return stats
    
    loc_stats = calc_stats_by_repo(fixture_df, 'loc')
    cc_stats = calc_stats_by_repo(fixture_df, 'cyclomatic_complexity')
    
    # Add calculated columns to dataframe
    df['median_fixture_loc'] = df['repository_id'].apply(
        lambda rid: round(loc_stats.get(rid, {}).get('median'), 2) 
                   if loc_stats.get(rid, {}).get('median') is not None else None
    )
    df['stddev_fixture_loc'] = df['repository_id'].apply(
        lambda rid: round(loc_stats.get(rid, {}).get('stddev'), 2)
                   if loc_stats.get(rid, {}).get('stddev') is not None else None
    )
    df['median_cyclomatic_complexity'] = df['repository_id'].apply(
        lambda rid: round(cc_stats.get(rid, {}).get('median'), 2)
                   if cc_stats.get(rid, {}).get('median') is not None else None
    )
    
    # Get top fixture type and framework for each repo
    type_query = """
    SELECT f.repo_id, f.fixture_type
    FROM fixtures f
    """
    type_df = pd.read_sql(type_query, conn)
    
    def get_top_value(group_df, col):
        """Get most common value in a column by repo."""
        tops = {}
        for repo_id, group in group_df.groupby('repo_id'):
            value_counts = group[col].value_counts()
            if len(value_counts) > 0:
                tops[repo_id] = value_counts.index[0]
            else:
                tops[repo_id] = None
        return tops
    
    top_type = get_top_value(type_df, 'fixture_type')
    
    framework_query = """
    SELECT f.repo_id, f.framework
    FROM fixtures f
    """
    framework_df = pd.read_sql(framework_query, conn)
    top_framework = get_top_value(framework_df, 'framework')
    
    df['top_fixture_type'] = df['repository_id'].apply(lambda rid: top_type.get(rid))
    df['top_framework'] = df['repository_id'].apply(lambda rid: top_framework.get(rid))
    
    # Pre-calculate counts for efficiency (avoid O(n²) lookups)
    type_counts_by_repo = type_df.groupby(['repo_id', 'fixture_type']).size().reset_index(name='count')
    type_counts_by_repo = type_counts_by_repo.loc[type_counts_by_repo.groupby('repo_id')['count'].idxmax()]
    type_count_map = dict(zip(type_counts_by_repo['repo_id'], type_counts_by_repo['count']))
    
    framework_counts_by_repo = framework_df.groupby(['repo_id', 'framework']).size().reset_index(name='count')
    framework_counts_by_repo = framework_counts_by_repo.loc[framework_counts_by_repo.groupby('repo_id')['count'].idxmax()]
    fw_count_map = dict(zip(framework_counts_by_repo['repo_id'], framework_counts_by_repo['count']))
    
    df['top_fixture_type_count'] = df['repository_id'].apply(lambda rid: type_count_map.get(rid, 0))
    df['top_framework_count'] = df['repository_id'].apply(lambda rid: fw_count_map.get(rid, 0))
    
    # Reorder columns for better readability
    col_order = [
        'repository_id', 'full_name', 'language', 'github_id', 'stars', 'forks',
        'num_contributors', 'pinned_commit', 'domain',
        'num_test_files', 'total_test_file_loc', 'avg_test_file_loc',
        'num_fixtures_total', 'num_fixtures_per_test', 'num_fixtures_per_class',
        'num_fixtures_per_module', 'num_fixtures_global',
        'num_fixture_types_unique', 'top_fixture_type', 'top_fixture_type_count',
        'num_frameworks_unique', 'top_framework', 'top_framework_count',
        'avg_fixture_loc', 'min_fixture_loc', 'max_fixture_loc', 'median_fixture_loc', 'stddev_fixture_loc',
        'avg_cyclomatic_complexity', 'min_cyclomatic_complexity', 'max_cyclomatic_complexity', 'median_cyclomatic_complexity',
        'avg_max_nesting_depth', 'max_nesting_depth_overall',
        'avg_num_parameters', 'avg_num_external_calls', 'avg_num_objects_instantiated',
        'fixtures_with_teardown_count', 'teardown_adoption_rate',
        'total_mock_usages', 'avg_mocks_per_fixture',
        'total_test_functions', 'avg_fixtures_per_test_file'
    ]
    df = df[[c for c in col_order if c in df.columns]]
    
    # Validate all expected columns are present
    missing = set(col_order) - set(df.columns)
    if missing:
        logger.warning(f"repository_statistics: Missing columns {missing}")
    
    df.to_csv(dest, index=False)
    logger.info(f"  repository_statistics: {len(df):,} rows × {len(df.columns)} cols → {dest.name}")


def _export_test_file_statistics(
    conn: sqlite3.Connection,
    dest: Path,
) -> None:
    """Export aggregated fixture metrics per test file.
    
    Aggregates all fixtures in each test file to provide file-level
    summary statistics. Includes complexity metrics, scope distribution,
    framework diversity, and teardown adoption rates.
    
    Args:
        conn: SQLite connection to corpus database
        dest: Path to write test_file_statistics.csv
    
    Returns:
        None. Writes CSV file to dest.
    
    Raises:
        Exception: If SQL query fails or data is invalid
    
    Note:
        For files with 0 fixtures, aggregate columns are NULL/empty.
        This design preserves all test files for complete research datasets.
    """
    query = """
    SELECT
        tf.id AS test_file_id,
        r.id AS repository_id,
        r.full_name,
        tf.language,
        tf.relative_path,
        tf.file_loc,
        
        COUNT(DISTINCT f.id) AS num_fixtures_total,
        SUM(CASE WHEN f.scope = 'per_test' THEN 1 ELSE 0 END) AS num_fixtures_per_test,
        SUM(CASE WHEN f.scope = 'per_class' THEN 1 ELSE 0 END) AS num_fixtures_per_class,
        SUM(CASE WHEN f.scope = 'per_module' THEN 1 ELSE 0 END) AS num_fixtures_per_module,
        SUM(CASE WHEN f.scope = 'global' THEN 1 ELSE 0 END) AS num_fixtures_global,
        
        COUNT(DISTINCT f.fixture_type) AS num_fixture_types_unique,
        COUNT(DISTINCT f.framework) AS num_frameworks_unique,
        
        SUM(f.loc) AS total_fixture_loc,
        ROUND(AVG(f.loc), 2) AS avg_fixture_loc,
        MIN(f.loc) AS min_fixture_loc,
        MAX(f.loc) AS max_fixture_loc,
        
        ROUND(AVG(f.cyclomatic_complexity), 2) AS avg_cyclomatic_complexity,
        MIN(f.cyclomatic_complexity) AS min_cyclomatic_complexity,
        MAX(f.cyclomatic_complexity) AS max_cyclomatic_complexity,
        
        ROUND(AVG(f.max_nesting_depth), 2) AS avg_max_nesting_depth,
        MAX(f.max_nesting_depth) AS max_nesting_depth,
        
        ROUND(AVG(f.num_parameters), 2) AS avg_num_parameters,
        ROUND(AVG(f.num_external_calls), 2) AS avg_num_external_calls,
        ROUND(AVG(f.num_objects_instantiated), 2) AS avg_num_objects_instantiated,
        
        SUM(CASE WHEN f.has_teardown_pair = 1 THEN 1 ELSE 0 END) AS fixtures_with_teardown_count,
        ROUND(100.0 * SUM(CASE WHEN f.has_teardown_pair = 1 THEN 1 ELSE 0 END) / 
              NULLIF(COUNT(DISTINCT f.id), 0), 2) AS teardown_adoption_rate,
        
        COUNT(DISTINCT mu.id) AS total_mock_usages,
        
        tf.num_test_funcs

    FROM test_files tf
    LEFT JOIN repositories r ON tf.repo_id = r.id
    LEFT JOIN fixtures f ON tf.id = f.file_id
    LEFT JOIN mock_usages mu ON f.id = mu.fixture_id
    WHERE r.status = 'analysed'
    GROUP BY tf.id, r.id, r.full_name, tf.language, tf.relative_path, tf.file_loc, tf.num_test_funcs
    ORDER BY r.full_name, tf.relative_path
    """
    
    try:
        df = pd.read_sql(query, conn)
    except Exception as e:
        logger.error(f"Failed to query test_file_statistics from database: {e}")
        raise
    
    if df.empty:
        logger.warning("test_file_statistics: No data returned from query")
        df.to_csv(dest, index=False)
        return
    
    # Get top fixture type and framework for each test file
    type_query = """
    SELECT f.file_id, f.fixture_type
    FROM fixtures f
    """
    type_df = pd.read_sql(type_query, conn)
    
    def get_top_value_by_file(group_df, col):
        """Get most common value in a column by file."""
        tops = {}
        for file_id, group in group_df.groupby('file_id'):
            value_counts = group[col].value_counts()
            if len(value_counts) > 0:
                tops[file_id] = value_counts.index[0]
            else:
                tops[file_id] = None
        return tops
    
    top_type = get_top_value_by_file(type_df, 'fixture_type')
    
    framework_query = """
    SELECT f.file_id, f.framework
    FROM fixtures f
    """
    framework_df = pd.read_sql(framework_query, conn)
    top_framework = get_top_value_by_file(framework_df, 'framework')
    
    # Calculate median and stddev using pandas for consistency with repository_statistics
    fixture_query = """
    SELECT f.file_id, f.loc, f.cyclomatic_complexity
    FROM fixtures f
    """
    fixture_df = pd.read_sql(fixture_query, conn)
    
    def calc_stats_by_file(group_df, col):
        """Calculate median and stddev for a column by file."""
        stats = {}
        for file_id, group in group_df.groupby('file_id'):
            values = group[col].dropna()
            if len(values) > 0:
                stats[file_id] = {
                    'median': values.median(),
                    'stddev': values.std() if len(values) > 1 else 0.0
                }
            else:
                stats[file_id] = {'median': None, 'stddev': None}
        return stats
    
    loc_stats = calc_stats_by_file(fixture_df, 'loc')
    cc_stats = calc_stats_by_file(fixture_df, 'cyclomatic_complexity')
    
    df['median_fixture_loc'] = df['test_file_id'].apply(
        lambda fid: round(loc_stats.get(fid, {}).get('median'), 2)
                   if loc_stats.get(fid, {}).get('median') is not None else None
    )
    df['stddev_fixture_loc'] = df['test_file_id'].apply(
        lambda fid: round(loc_stats.get(fid, {}).get('stddev'), 2)
                   if loc_stats.get(fid, {}).get('stddev') is not None else None
    )
    df['median_cyclomatic_complexity'] = df['test_file_id'].apply(
        lambda fid: round(cc_stats.get(fid, {}).get('median'), 2)
                   if cc_stats.get(fid, {}).get('median') is not None else None
    )
    
    # Pre-calculate top values for efficiency (avoid O(n²) lookups)
    type_counts_by_file = type_df.groupby(['file_id', 'fixture_type']).size().reset_index(name='count')
    type_counts_by_file = type_counts_by_file.loc[type_counts_by_file.groupby('file_id')['count'].idxmax()]
    type_map = dict(zip(type_counts_by_file['file_id'], type_counts_by_file['fixture_type']))
    type_count_map = dict(zip(type_counts_by_file['file_id'], type_counts_by_file['count']))
    
    framework_counts_by_file = framework_df.groupby(['file_id', 'framework']).size().reset_index(name='count')
    framework_counts_by_file = framework_counts_by_file.loc[framework_counts_by_file.groupby('file_id')['count'].idxmax()]
    fw_map = dict(zip(framework_counts_by_file['file_id'], framework_counts_by_file['framework']))
    fw_count_map = dict(zip(framework_counts_by_file['file_id'], framework_counts_by_file['count']))
    
    df['top_fixture_type'] = df['test_file_id'].apply(lambda fid: type_map.get(fid))
    df['top_fixture_type_count'] = df['test_file_id'].apply(lambda fid: type_count_map.get(fid, 0))
    df['top_framework'] = df['test_file_id'].apply(lambda fid: fw_map.get(fid))
    df['top_framework_count'] = df['test_file_id'].apply(lambda fid: fw_count_map.get(fid, 0))
    
    # Reorder columns for better readability and consistency with repository_statistics
    col_order = [
        'test_file_id', 'repository_id', 'full_name', 'language', 'relative_path', 'file_loc',
        'num_fixtures_total', 'num_fixtures_per_test', 'num_fixtures_per_class',
        'num_fixtures_per_module', 'num_fixtures_global',
        'num_fixture_types_unique', 'top_fixture_type', 'top_fixture_type_count',
        'num_frameworks_unique', 'top_framework', 'top_framework_count',
        'total_fixture_loc', 'avg_fixture_loc', 'min_fixture_loc', 'max_fixture_loc',
        'median_fixture_loc', 'stddev_fixture_loc',
        'avg_cyclomatic_complexity', 'min_cyclomatic_complexity', 'max_cyclomatic_complexity',
        'median_cyclomatic_complexity',
        'avg_max_nesting_depth', 'max_nesting_depth',
        'avg_num_parameters', 'avg_num_external_calls', 'avg_num_objects_instantiated',
        'fixtures_with_teardown_count', 'teardown_adoption_rate',
        'total_mock_usages',
        'num_test_funcs'
    ]
    df = df[[c for c in col_order if c in df.columns]]
    
    # Validate all expected columns are present
    missing = set(col_order) - set(df.columns)
    if missing:
        logger.warning(f"test_file_statistics: Missing columns {missing}")
    
    df.to_csv(dest, index=False)
    logger.info(f"  test_file_statistics: {len(df):,} rows × {len(df.columns)} cols → {dest.name}")





def _write_readme(path: Path, version: str) -> None:
    header = f"""FixtureDB v{version}
Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}

A multi-language dataset of test fixture definitions extracted from
open-source software repositories on GitHub.

Dataset includes 35,169 fixtures from 200 repositories across 4 languages
(Python, Java, JavaScript, TypeScript) with structural metrics and mock
framework usage patterns.

For paper, documentation, and usage examples:
  https://github.com/joao-almeida/icsme-nier-2026

CONTENTS
--------
  repositories.csv            200 repositories with maturity metrics
  repository_statistics.csv   200 repositories with aggregated fixture stats
  test_files.csv              257,764 test files with fixture counts
  test_file_statistics.csv    257,764 test files with aggregated fixture stats
  fixtures.csv                35,169 fixtures with metrics and GitHub links
  fixtures.db                 Full SQLite database (includes raw source code)
  stats.txt                   Summary statistics by language

QUICK START (Python)
--------------------
  import pandas as pd
  
  # Load CSV
  df_fixtures = pd.read_csv("fixtures.csv")
  df_repos = pd.read_csv("repositories.csv")
  
  # Or use SQLite database for full access
  import sqlite3
  conn = sqlite3.connect("fixtures.db")
  df = pd.read_sql("SELECT * FROM fixtures", conn)

COLUMN REFERENCE
----------------
See sections below for detailed CSV schema documentation.

CITATION
--------
If using this dataset, cite:
  FixtureDB: A Multi-Language Dataset of Test Fixture Definitions
  João Almeida, Andre Hora
  ICSME 2026, Tool Demonstration and Data Showcase Track
  
LICENSE
-------
  Dataset: CC BY 4.0  (https://creativecommons.org/licenses/by/4.0/)
  Pipeline source code: MIT

"""
    path.write_text(header + SCHEMA_DOCS, encoding="utf-8")


def _write_stats(conn, path: Path) -> None:
    """Write a human-readable stats summary (useful for the paper's Table 1)."""
    conn2 = sqlite3.connect(DB_PATH)
    conn2.row_factory = sqlite3.Row
    lines = [
        "FixtureDB — Corpus Statistics\n",
        "=" * 50 + "\n\n",
        "SUMMARY\n",
        "-" * 50 + "\n",
    ]

    # Overall stats
    total_repos = conn2.execute(
        "SELECT COUNT(*) n FROM repositories WHERE status='analysed'"
    ).fetchone()["n"]
    total_fixtures = conn2.execute("SELECT COUNT(*) n FROM fixtures").fetchone()["n"]
    total_test_files = conn2.execute("SELECT COUNT(*) n FROM test_files").fetchone()["n"]

    lines.append(f"Total repositories:     {total_repos:,}\n")
    lines.append(f"Total test files:       {total_test_files:,}\n")
    lines.append(f"Total fixtures:         {total_fixtures:,}\n")
    lines.append("\n")

    # Per-language breakdown
    lines.append("BY LANGUAGE\n")
    lines.append("-" * 50 + "\n")
    lines.append(f"{'Language':<15} {'Repos':<8} {'Test Files':<12} {'Fixtures':<10}\n")
    lines.append("-" * 50 + "\n")

    for lang in ("python", "java", "javascript", "typescript"):
        r = conn2.execute(
            "SELECT COUNT(*) n FROM repositories WHERE language=? AND status='analysed'",
            (lang,),
        ).fetchone()["n"]
        tf = conn2.execute(
            "SELECT COUNT(*) n FROM test_files tf "
            "JOIN repositories r ON tf.repo_id=r.id WHERE r.language=?",
            (lang,),
        ).fetchone()["n"]
        fx = conn2.execute(
            "SELECT COUNT(*) n FROM fixtures f "
            "JOIN repositories r ON f.repo_id=r.id WHERE r.language=?",
            (lang,),
        ).fetchone()["n"]
        lines.append(f"{lang:<15} {r:<8} {tf:<12} {fx:<10}\n")

    conn2.close()
    path.write_text("".join(lines), encoding="utf-8")
