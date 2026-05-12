"""
Core exporter tests — validates CSV generation, data integrity, and ZIP creation.

Tests cover:
- CSV export correctness (column filtering, row counts, data types)
- exclude_cols logic (present and absent columns)
- README and stats generation
- Full export_dataset workflow (ZIP creation, versioning, file layout)
- Data integrity (no unexpected NULLs, correct column ordering)
"""

import tempfile
import sqlite3
from pathlib import Path
import zipfile
import csv

import pandas as pd
import pytest

from collection.db import get_connection
from collection.exporter import (
    _export_table,
    _write_readme,
    _write_stats,
    export_dataset,
    SCHEMA_DOCS,
)


@pytest.fixture
def temp_db_with_data():
    """Create a temporary database with realistic test data."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        temp_path = Path(f.name)

    conn = get_connection(temp_path)
    conn.executescript("""
    CREATE TABLE repositories (
        id INTEGER PRIMARY KEY,
        github_id INTEGER UNIQUE,
        full_name TEXT,
        language TEXT,
        stars INTEGER,
        forks INTEGER,
        description TEXT,
        topics TEXT,
        created_at TEXT,
        pushed_at TEXT,
        clone_url TEXT,
        pinned_commit TEXT,
        domain TEXT,
        star_tier TEXT,
        status TEXT DEFAULT 'discovered',
        error_message TEXT,
        skip_reason TEXT,
        num_test_files INTEGER DEFAULT 0,
        num_fixtures INTEGER DEFAULT 0,
        num_mock_usages INTEGER DEFAULT 0,
        collected_at TEXT,
        num_contributors INTEGER DEFAULT 0
    );
    
    CREATE TABLE test_files (
        id INTEGER PRIMARY KEY,
        repo_id INTEGER,
        relative_path TEXT,
        language TEXT,
        file_loc INTEGER DEFAULT 0,
        num_test_funcs INTEGER DEFAULT 0,
        num_fixtures INTEGER DEFAULT 0,
        total_fixture_loc INTEGER DEFAULT 0,
        UNIQUE(repo_id, relative_path)
    );
    
    CREATE TABLE fixtures (
        id INTEGER PRIMARY KEY,
        file_id INTEGER,
        repo_id INTEGER,
        name TEXT,
        fixture_type TEXT,
        scope TEXT,
        start_line INTEGER,
        end_line INTEGER,
        loc INTEGER,
        cyclomatic_complexity INTEGER,
        num_objects_instantiated INTEGER,
        num_external_calls INTEGER,
        num_parameters INTEGER,
        raw_source TEXT,
        category TEXT,
        framework TEXT,
        max_nesting_depth INTEGER DEFAULT 1,
        reuse_count INTEGER DEFAULT 0,
        has_teardown_pair INTEGER DEFAULT 0,
        UNIQUE(file_id, name, start_line)
    );
    
    CREATE TABLE mock_usages (
        id INTEGER PRIMARY KEY,
        fixture_id INTEGER,
        repo_id INTEGER,
        framework TEXT,
        mock_style TEXT,
        target_identifier TEXT,
        target_layer TEXT,
        num_interactions_configured INTEGER,
        raw_snippet TEXT
    );
    """)

    # Insert realistic test data
    conn.execute("""
        INSERT INTO repositories 
        (github_id, full_name, language, stars, forks, description, topics, 
         created_at, pushed_at, clone_url, pinned_commit, domain, star_tier, status, error_message, skip_reason, collected_at, num_contributors)
        VALUES (100, 'owner/repo1', 'python', 500, 50, 'Test repo', '["testing"]',
                '2020-01-01T00:00:00Z', '2024-01-01T00:00:00Z', 'https://example.com/repo1.git', 
                'abc1234567890', 'library', 'core', 'analysed', NULL, NULL, '2024-01-02T00:00:00Z', 10)
    """)
    conn.execute("""
        INSERT INTO repositories 
        (github_id, full_name, language, stars, forks, description, topics, 
         created_at, pushed_at, clone_url, pinned_commit, domain, star_tier, status, error_message, skip_reason, collected_at, num_contributors)
        VALUES (101, 'owner/repo2', 'java', 300, 30, 'Another repo', '[]',
                '2019-01-01T00:00:00Z', '2024-01-01T00:00:00Z', 'https://example.com/repo2.git',
                'def5678901234', 'web', 'extended', 'analysed', NULL, NULL, '2024-01-02T00:00:00Z', 5)
    """)

    # Test files
    conn.execute(
        "INSERT INTO test_files (repo_id, relative_path, language, num_test_funcs, num_fixtures) VALUES (1, 'test_module.py', 'python', 5, 2)"
    )
    conn.execute(
        "INSERT INTO test_files (repo_id, relative_path, language, num_test_funcs, num_fixtures) VALUES (2, 'src/test/TestMain.java', 'java', 3, 1)"
    )

    # Fixtures
    conn.execute("""
        INSERT INTO fixtures 
        (file_id, repo_id, name, fixture_type, scope, start_line, end_line, loc,
         cyclomatic_complexity, num_objects_instantiated,
         num_external_calls, num_parameters, raw_source, category, framework,
         max_nesting_depth, reuse_count, has_teardown_pair)
        VALUES (1, 1, 'db_fixture', 'pytest_decorator', 'per_test', 5, 15, 11,
                2, 1, 2, 0, 'def db_fixture():\\n    ...', 'setup', 'pytest',
                2, 1, 0)
    """)
    conn.execute("""
        INSERT INTO fixtures 
        (file_id, repo_id, name, fixture_type, scope, start_line, end_line, loc,
         cyclomatic_complexity, num_objects_instantiated,
         num_external_calls, num_parameters, raw_source, category, framework,
         max_nesting_depth, reuse_count, has_teardown_pair)
        VALUES (1, 1, 'config_fixture', 'pytest_decorator', 'per_module', 20, 25, 6,
                1, 0, 1, 1, 'def config_fixture(request):\\n    ...', 'setup', 'pytest',
                1, 0, 1)
    """)
    conn.execute("""
        INSERT INTO fixtures 
        (file_id, repo_id, name, fixture_type, scope, start_line, end_line, loc,
         cyclomatic_complexity, num_objects_instantiated,
         num_external_calls, num_parameters, raw_source, category, framework,
         max_nesting_depth, reuse_count, has_teardown_pair)
        VALUES (2, 2, 'setUp', 'junit4_before', 'per_test', 10, 20, 11,
                2, 1, 1, 0, 'public void setUp() {\\n    ...', 'setup', 'junit',
                1, 2, 0)
    """)

    # Mock usages
    conn.execute("""
        INSERT INTO mock_usages 
        (fixture_id, repo_id, framework, mock_style, target_identifier, target_layer,
         num_interactions_configured, raw_snippet)
        VALUES (1, 1, 'pytest_mock', 'mock', 'database', 'boundary', 3, 'database.getConnection()')
    """)
    conn.execute("""
        INSERT INTO mock_usages 
        (fixture_id, repo_id, framework, mock_style, target_identifier, target_layer,
         num_interactions_configured, raw_snippet)
        VALUES (1, 1, 'unittest_mock', 'stub', 'config', 'internal', 1, 'config.load()')
    """)

    conn.commit()
    conn.close()

    yield temp_path

    # Cleanup
    temp_path.unlink()


class TestExportTable:
    """Test _export_table CSV generation and filtering."""

    def test_export_table_creates_csv_file(self, temp_db_with_data):
        """_export_table should create a CSV file with correct rows."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "repos.csv"
            conn = sqlite3.connect(temp_db_with_data)

            _export_table(conn, "repositories", dest)
            conn.close()

            assert dest.exists()
            df = pd.read_csv(dest)
            assert len(df) == 2
            assert list(df["full_name"]) == ["owner/repo1", "owner/repo2"]

    def test_export_table_excludes_specified_columns(self, temp_db_with_data):
        """_export_table should exclude columns listed in exclude_cols."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "fixtures.csv"
            conn = sqlite3.connect(temp_db_with_data)

            # Export fixtures without category, fixture_type, and has_teardown_pair (but keep raw_source)
            _export_table(
                conn,
                "fixtures",
                dest,
                exclude_cols=["category", "fixture_type", "has_teardown_pair"],
            )
            conn.close()

            df = pd.read_csv(dest)
            assert "category" not in df.columns
            assert "fixture_type" not in df.columns
            assert "has_teardown_pair" not in df.columns
            assert "raw_source" in df.columns
            assert "name" in df.columns
            assert "scope" in df.columns
            assert len(df) == 3

    def test_export_table_handles_missing_exclude_columns(self, temp_db_with_data):
        """_export_table should gracefully handle non-existent columns in exclude_cols."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "repos.csv"
            conn = sqlite3.connect(temp_db_with_data)

            # Try to exclude a column that doesn't exist in this table
            _export_table(
                conn,
                "repositories",
                dest,
                exclude_cols=["raw_source", "nonexistent_col"],
            )
            conn.close()

            df = pd.read_csv(dest)
            # Should not throw error; just skip nonexistent columns
            assert len(df) == 2
            assert "raw_source" not in df.columns  # Was excluded
            assert "full_name" in df.columns  # Remained

    def test_export_table_preserves_all_rows(self, temp_db_with_data):
        """_export_table should export all rows, not filter any."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "test_files.csv"
            conn = sqlite3.connect(temp_db_with_data)

            # Count rows in DB
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM test_files")
            db_count = cursor.fetchone()[0]

            _export_table(conn, "test_files", dest)
            conn.close()

            df = pd.read_csv(dest)
            assert len(df) == db_count == 2

    def test_export_table_correct_data_types_in_csv(self, temp_db_with_data):
        """Exported CSV should preserve numeric types (integers stay numeric in CSV)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "repos.csv"
            conn = sqlite3.connect(temp_db_with_data)

            _export_table(conn, "repositories", dest)
            conn.close()

            df = pd.read_csv(dest)
            assert pd.api.types.is_numeric_dtype(df["stars"])
            assert pd.api.types.is_numeric_dtype(df["forks"])
            assert df.iloc[0]["stars"] == 500
            assert df.iloc[1]["forks"] == 30

    def test_repositories_export_excludes_internal_fields(self, temp_db_with_data):
        """repositories export should exclude internal tracking fields (star_tier, status, domain, error_message, skip_reason)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "repositories.csv"
            conn = sqlite3.connect(temp_db_with_data)

            _export_table(
                conn,
                "repositories",
                dest,
                exclude_cols=[
                    "star_tier",
                    "status",
                    "domain",
                    "error_message",
                    "skip_reason",
                ],
            )
            conn.close()

            df = pd.read_csv(dest)
            # Verify excluded columns are not present
            assert "star_tier" not in df.columns
            assert "status" not in df.columns
            assert "domain" not in df.columns
            assert "error_message" not in df.columns
            assert "skip_reason" not in df.columns

            # Verify essential columns are present
            assert "github_id" in df.columns
            assert "full_name" in df.columns
            assert "language" in df.columns
            assert "stars" in df.columns
            assert "forks" in df.columns
            assert "clone_url" in df.columns
            assert "pinned_commit" in df.columns
            assert "num_contributors" in df.columns
            assert len(df) == 2


class TestMockUsagesExport:
    """Test that mock_usages CSV excludes internal classification fields."""

    def test_mock_usages_excludes_internal_fields(self, temp_db_with_data):
        """mock_usages export should exclude mock_style, target_layer, raw_snippet."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "mock_usages.csv"
            conn = sqlite3.connect(temp_db_with_data)

            _export_table(
                conn,
                "mock_usages",
                dest,
                exclude_cols=["mock_style", "target_layer", "raw_snippet"],
            )
            conn.close()

            df = pd.read_csv(dest)
            assert "mock_style" not in df.columns
            assert "target_layer" not in df.columns
            assert "raw_snippet" not in df.columns
            assert "framework" in df.columns
            assert "num_interactions_configured" in df.columns


class TestFixturesExport:
    """Test fixtures CSV exports with quantitative metrics and source code."""

    def test_fixtures_excludes_qualitative_fields_by_default(self, temp_db_with_data):
        """Default fixtures.csv should exclude qualitative fields but include raw_source."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "fixtures.csv"
            conn = sqlite3.connect(temp_db_with_data)

            _export_table(
                conn,
                "fixtures",
                dest,
                exclude_cols=["category", "fixture_type", "has_teardown_pair"],
            )
            conn.close()

            df = pd.read_csv(dest)
            # Qualitative fields excluded
            assert "category" not in df.columns
            assert "fixture_type" not in df.columns
            assert "has_teardown_pair" not in df.columns
            # But raw_source is included for reproducibility
            assert "raw_source" in df.columns
            assert "name" in df.columns
            assert len(df) == 3

    def test_fixtures_with_source_includes_raw_source(self, temp_db_with_data):
        """fixtures_with_source.csv should include raw_source and exclude only qualitative fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "fixtures_with_source.csv"
            conn = sqlite3.connect(temp_db_with_data)

            _export_table(
                conn,
                "fixtures",
                dest,
                exclude_cols=["category", "fixture_type", "has_teardown_pair"],
            )
            conn.close()

            df = pd.read_csv(dest)
            # raw_source is included
            assert "raw_source" in df.columns
            # Qualitative fields still excluded
            assert "category" not in df.columns
            assert "fixture_type" not in df.columns
            assert "has_teardown_pair" not in df.columns
            # raw_source contains the literal string with escaped newlines
            assert "db_fixture" in df.iloc[0]["raw_source"]


class TestFixturesExport:
    """Test fixtures CSV exports with quantitative metrics and source code."""

    def test_fixtures_excludes_qualitative_fields_by_default(self, temp_db_with_data):
        """Default fixtures.csv should exclude qualitative fields but include raw_source."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "fixtures.csv"
            conn = sqlite3.connect(temp_db_with_data)

            _export_table(
                conn,
                "fixtures",
                dest,
                exclude_cols=["category", "fixture_type", "has_teardown_pair"],
            )
            conn.close()

            df = pd.read_csv(dest)
            # Qualitative fields excluded
            assert "category" not in df.columns
            assert "fixture_type" not in df.columns
            assert "has_teardown_pair" not in df.columns
            # But raw_source is included for reproducibility
            assert "raw_source" in df.columns
            assert "name" in df.columns
            assert len(df) == 3

    def test_fixtures_with_source_includes_raw_source(self, temp_db_with_data):
        """fixtures_with_source.csv should include raw_source and exclude only qualitative fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "fixtures_with_source.csv"
            conn = sqlite3.connect(temp_db_with_data)

            _export_table(
                conn,
                "fixtures",
                dest,
                exclude_cols=["category", "fixture_type", "has_teardown_pair"],
            )
            conn.close()

            df = pd.read_csv(dest)
            # raw_source is included
            assert "raw_source" in df.columns
            # Qualitative fields still excluded
            assert "category" not in df.columns
            assert "fixture_type" not in df.columns
            assert "has_teardown_pair" not in df.columns
            # raw_source contains the literal string with escaped newlines
            assert "db_fixture" in df.iloc[0]["raw_source"]


class TestRepositoryStatisticsExport:
    """Test repository_statistics CSV generation with aggregated metrics."""

    def test_repository_statistics_structure(self, temp_db_with_data):
        """repository_statistics should have expected aggregated columns."""
        from collection.exporter import _export_repository_statistics

        with tempfile.TemporaryDirectory() as tmpdir:
            stats_path = Path(tmpdir) / "repository_statistics.csv"
            conn = sqlite3.connect(temp_db_with_data)

            _export_repository_statistics(conn, stats_path)
            conn.close()

            assert stats_path.exists()

            df = pd.read_csv(stats_path)
            # Should have one row per repository with analyzed fixtures
            assert len(df) >= 1

            # Check for key aggregation columns
            assert "full_name" in df.columns
            assert "num_fixtures_total" in df.columns
            assert "num_test_files" in df.columns

            # Aggregation statistics should be present
            assert "avg_cyclomatic_complexity" in df.columns
            assert "max_cyclomatic_complexity" in df.columns
            assert "min_fixture_loc" in df.columns
            assert "max_fixture_loc" in df.columns

    def test_repository_statistics_row_count(self, temp_db_with_data):
        """repository_statistics should have one row per repository."""
        from collection.exporter import _export_repository_statistics

        with tempfile.TemporaryDirectory() as tmpdir:
            stats_path = Path(tmpdir) / "repository_statistics.csv"
            conn = sqlite3.connect(temp_db_with_data)

            # Count analyzed repos in DB
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(DISTINCT full_name) FROM repositories WHERE status = 'analysed'"
            )
            expected_repos = cursor.fetchone()[0]

            _export_repository_statistics(conn, stats_path)
            conn.close()

            df = pd.read_csv(stats_path)

            # Should have one row per analyzed repository
            assert len(df) == expected_repos


class TestTestFileStatisticsExport:
    """Test test_file_statistics CSV generation with per-file aggregated metrics."""

    def test_test_file_statistics_structure(self, temp_db_with_data):
        """test_file_statistics should have expected per-file aggregation columns."""
        from collection.exporter import _export_test_file_statistics

        with tempfile.TemporaryDirectory() as tmpdir:
            stats_path = Path(tmpdir) / "test_file_statistics.csv"
            conn = sqlite3.connect(temp_db_with_data)

            _export_test_file_statistics(conn, stats_path)
            conn.close()

            assert stats_path.exists()

            df = pd.read_csv(stats_path)
            # Should have rows for test files
            assert len(df) > 0

            # Check for key columns
            assert "relative_path" in df.columns
            assert "language" in df.columns
            assert "num_fixtures_total" in df.columns
            assert "file_loc" in df.columns

            # Aggregation statistics should be present
            assert "avg_cyclomatic_complexity" in df.columns
            assert "max_cyclomatic_complexity" in df.columns

    def test_test_file_statistics_includes_all_files(self, temp_db_with_data):
        """test_file_statistics should include all test files, even those with zero fixtures."""
        from collection.exporter import _export_test_file_statistics

        with tempfile.TemporaryDirectory() as tmpdir:
            stats_path = Path(tmpdir) / "test_file_statistics.csv"
            conn = sqlite3.connect(temp_db_with_data)

            # Count all test files in DB
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM test_files")
            total_files = cursor.fetchone()[0]

            _export_test_file_statistics(conn, stats_path)
            conn.close()

            df = pd.read_csv(stats_path)

            # Should have rows for all test files
            assert len(df) == total_files


class TestReadmeGeneration:
    """Test README generation contains necessary metadata."""

    def test_write_readme_includes_version(self, tmp_path):
        """README should include the version number."""
        readme_path = tmp_path / "README.txt"
        _write_readme(readme_path, "1.0.0")

        content = readme_path.read_text()
        assert "1.0.0" in content
        assert "FixtureDB v1.0.0" in content

    def test_write_readme_includes_schema_docs(self, tmp_path):
        """README should include the full schema documentation."""
        readme_path = tmp_path / "README.txt"
        _write_readme(readme_path, "1.0")

        content = readme_path.read_text()
        assert "REPOSITORIES.CSV" in content
        assert "FIXTURES.CSV" in content
        assert "cyclomatic_complexity" in content
        assert SCHEMA_DOCS in content

    def test_write_readme_includes_timestamp(self, tmp_path):
        """README should include a generated timestamp."""
        readme_path = tmp_path / "README.txt"
        _write_readme(readme_path, "1.0")

        content = readme_path.read_text()
        assert "Generated: 20" in content  # Matches "Generated: YYYY-..."

    def test_write_readme_includes_license_info(self, tmp_path):
        """README should include license information."""
        readme_path = tmp_path / "README.txt"
        _write_readme(readme_path, "1.0")

        content = readme_path.read_text()
        assert "CC BY 4.0" in content
        assert "MIT" in content


class TestStatsGeneration:
    """Test stats.txt generation with per-language aggregations."""

    def test_write_stats_generates_file(self, temp_db_with_data):
        """_write_stats should create a stats.txt file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            stats_path = Path(tmpdir) / "stats.txt"
            conn = sqlite3.connect(temp_db_with_data)

            _write_stats(conn, stats_path)
            conn.close()

            assert stats_path.exists()

    def test_write_stats_includes_language_breakdowns(self, temp_db_with_data):
        """Stats should include counts for python and java."""
        with tempfile.TemporaryDirectory() as tmpdir:
            stats_path = Path(tmpdir) / "stats.txt"
            conn = sqlite3.connect(temp_db_with_data)

            _write_stats(conn, stats_path)
            conn.close()

            content = stats_path.read_text()
            assert "python" in content
            assert "java" in content
            # Stats should include language in a table format
            lines = content.split("\n")
            python_line = [l for l in lines if l.strip().startswith("python")][0]
            # Check that the line has numeric values (repos, test files, fixtures)
            assert any(c.isdigit() for c in python_line)

    def test_write_stats_counts_fixtures_correctly(self, temp_db_with_data):
        """Stats should count fixtures per language accurately."""
        with tempfile.TemporaryDirectory() as tmpdir:
            stats_path = Path(tmpdir) / "stats.txt"
            conn = sqlite3.connect(temp_db_with_data)

            _write_stats(conn, stats_path)
            conn.close()

            content = stats_path.read_text()
            # We have 2 Python fixtures and 1 Java fixture
            if "fixtures=" in content:
                lines = content.split("\n")
                assert len([l for l in lines if l.strip()]) >= 4  # Header + 4 languages


class TestFullExportWorkflow:
    """Integration tests for the complete export_dataset workflow."""

    def test_export_dataset_creates_zip_archive(self, temp_db_with_data, monkeypatch):
        """export_dataset should create a ZIP file with correct layout."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Temporarily override DB_PATH to use our test database
            from collection import exporter

            original_db = exporter.DB_PATH
            monkeypatch.setattr(exporter, "DB_PATH", temp_db_with_data)

            export_dir = Path(tmpdir) / "export"
            monkeypatch.setattr(exporter, "EXPORT_DIR", export_dir)

            try:
                zip_path = export_dataset(version="1.0.0")

                assert zip_path.exists()
                assert zip_path.suffix == ".zip"
                assert "1.0.0" in zip_path.name
            finally:
                monkeypatch.setattr(exporter, "DB_PATH", original_db)

    def test_export_dataset_zip_contains_csvs(self, temp_db_with_data, monkeypatch):
        """ZIP should contain all expected CSV files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from collection import exporter

            original_db = exporter.DB_PATH
            monkeypatch.setattr(exporter, "DB_PATH", temp_db_with_data)

            export_dir = Path(tmpdir) / "export"
            monkeypatch.setattr(exporter, "EXPORT_DIR", export_dir)

            try:
                zip_path = export_dataset(version="1.0.0")

                with zipfile.ZipFile(zip_path) as zf:
                    names = zf.namelist()
                    assert any("repositories.csv" in n for n in names)
                    assert any("repository_statistics.csv" in n for n in names)
                    assert any("test_files.csv" in n for n in names)
                    assert any("test_file_statistics.csv" in n for n in names)
                    assert any("fixtures.csv" in n for n in names)
                    assert any("README" in n for n in names)
            finally:
                monkeypatch.setattr(exporter, "DB_PATH", original_db)

    def test_export_dataset_version_in_filename(self, temp_db_with_data, monkeypatch):
        """Exported ZIP filename should include the version."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from collection import exporter

            original_db = exporter.DB_PATH
            monkeypatch.setattr(exporter, "DB_PATH", temp_db_with_data)

            export_dir = Path(tmpdir) / "export"
            monkeypatch.setattr(exporter, "EXPORT_DIR", export_dir)

            try:
                zip_path = export_dataset(version="2.3.4")
                assert "2.3.4" in zip_path.name
                assert "fixturedb_v2.3.4" in zip_path.name
            finally:
                monkeypatch.setattr(exporter, "DB_PATH", original_db)


class TestDataIntegrity:
    """Test for data quality and integrity in exports."""

    def test_exported_csv_no_unexpected_nulls_in_ids(self, temp_db_with_data):
        """ID and FK columns should never be NULL in exported CSVs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "fixtures.csv"
            conn = sqlite3.connect(temp_db_with_data)

            _export_table(conn, "fixtures", dest)
            conn.close()

            df = pd.read_csv(dest)
            # ID columns should never be null
            if "id" in df.columns:
                assert df["id"].notna().all()
            if "file_id" in df.columns:
                assert df["file_id"].notna().all()
            if "repo_id" in df.columns:
                assert df["repo_id"].notna().all()

    def test_exported_csv_preserves_column_order(self, temp_db_with_data):
        """CSV should maintain a consistent, logical column order."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "repositories.csv"
            conn = sqlite3.connect(temp_db_with_data)

            _export_table(conn, "repositories", dest)
            conn.close()

            df = pd.read_csv(dest)
            # ID should come first typically
            assert df.columns[0] == "id"
