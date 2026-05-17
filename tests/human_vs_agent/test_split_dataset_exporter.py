"""
Unit tests for FixtureDB split dataset export.
"""

import sqlite3
import tempfile
from pathlib import Path
from zipfile import ZipFile

from collection.dataset_exporter import HumanDatasetExporter, LLMDatasetExporter


def _create_export_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE repositories (id INTEGER PRIMARY KEY, full_name TEXT, language TEXT, status TEXT, pinned_commit TEXT, num_fixtures INTEGER)"
    )
    conn.execute(
        "CREATE TABLE test_files (id INTEGER PRIMARY KEY, repo_id INTEGER, relative_path TEXT, language TEXT, file_loc INTEGER, num_test_funcs INTEGER, num_fixtures INTEGER, total_fixture_loc INTEGER)"
    )
    conn.execute(
        "CREATE TABLE fixtures (id INTEGER PRIMARY KEY, file_id INTEGER, repo_id INTEGER, name TEXT, fixture_type TEXT, scope TEXT, start_line INTEGER, end_line INTEGER, loc INTEGER, cyclomatic_complexity INTEGER, max_nesting_depth INTEGER, num_objects_instantiated INTEGER, num_external_calls INTEGER, num_parameters INTEGER, reuse_count INTEGER, has_teardown_pair INTEGER, raw_source TEXT, category TEXT, framework TEXT, num_mocks INTEGER)"
    )
    conn.execute(
        "CREATE TABLE mock_usages (id INTEGER PRIMARY KEY, fixture_id INTEGER, repo_id INTEGER, framework TEXT, target_identifier TEXT, num_interactions_configured INTEGER, raw_snippet TEXT)"
    )
    conn.execute(
        "INSERT INTO repositories VALUES (1, 'owner/repo', 'python', 'analysed', 'abc123', 1)"
    )
    conn.execute(
        "INSERT INTO test_files VALUES (1, 1, 'tests/conftest.py', 'python', 10, 1, 1, 4)"
    )
    conn.execute(
        "INSERT INTO fixtures VALUES (1, 1, 1, 'sample_fixture', 'pytest.fixture', 'function', 1, 4, 4, 1, 0, 0, 0, 0, 0, 0, 'source', 'category', 'framework', 0)"
    )
    conn.execute(
        "INSERT INTO mock_usages VALUES (1, 1, 1, 'pytest-mock', 'client', 1, 'mock')"
    )
    conn.commit()
    conn.close()


class TestHumanDatasetExporter:
    def test_export_table_to_csv_writes_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "source.db"
            _create_export_db(db_path)

            exporter = HumanDatasetExporter(db_path, Path(tmpdir) / "out")
            csv_path = exporter.export_table_to_csv("fixtures")

            assert csv_path.exists()
            assert csv_path.name == "fixtures.csv"

    def test_export_creates_zip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "source.db"
            _create_export_db(db_path)

            exporter = HumanDatasetExporter(db_path, Path(tmpdir) / "out")
            result = exporter.export([1], version="1.0")

            assert result.zip_path.exists()
            assert result.fixture_count == 1
            assert result.documentation_files
            assert result.csv_files

            with ZipFile(result.zip_path) as archive:
                names = set(archive.namelist())
                assert "fixtures.csv" in names
                assert "README.md" in names
                assert "SCHEMA.md" in names


class TestLLMDatasetExporter:
    def test_export_includes_agents_documentation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "source.db"
            _create_export_db(db_path)

            exporter = LLMDatasetExporter(db_path, Path(tmpdir) / "out")
            result = exporter.export([1], version="1.0")

            assert result.zip_path.exists()
            assert any(path.name == "AGENTS.md" for path in result.documentation_files)

            with ZipFile(result.zip_path) as archive:
                assert "AGENTS.md" in set(archive.namelist())


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
