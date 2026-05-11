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

This archive contains 3 CSV files plus a SQLite database:

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

2. TEST_FILES.CSV
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

3. FIXTURES.CSV
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
    # test_files: with repo context for researchers
    _export_test_files(
        conn,
        staging / "test_files.csv",
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
  repositories.csv    200 repositories with maturity metrics
  test_files.csv      257,764 test files with fixture counts
  fixtures.csv        35,169 fixtures with metrics and GitHub links
  fixtures.db         Full SQLite database (includes raw source code)
  stats.txt           Summary statistics by language

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
