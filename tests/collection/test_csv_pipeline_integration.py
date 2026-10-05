"""
CSV Pipeline Integration Tests - Use Case 1.

Tests manual pipeline execution with real CSV input/output files.
Verifies that the collection module correctly:
1. Reads input CSV files (repo-QC, test-commit CSVs)
2. Processes repositories based on CSV data
3. Exports output fixtures to properly formatted CSV files
"""

import csv

import pytest



@pytest.fixture
def tmp_csv_dir(tmp_path):
    """Create a temporary directory with sample CSV files."""
    csv_dir = tmp_path / "repo_qc_csvs"
    csv_dir.mkdir()
    return csv_dir


@pytest.fixture
def sample_agent_repo_csv(tmp_csv_dir, make_csv):
    """Provide a sample agent repo CSV for tests without relying on committed files."""
    make_csv(tmp_csv_dir, "python_agent_repo.csv")
    return tmp_csv_dir / "python_agent_repo.csv"


class TestCSVFixtureExportFormat:
    """Test fixture CSV export format validation."""

    def test_fixture_csv_has_required_columns(self, tmp_path):
        """Verify exported fixture CSV has all required columns."""
        from collection.corpus_utils import write_fixture_csv_row

        out_path = tmp_path / "fixtures.csv"
        fixture = {
            "commit_sha": "abc123",
            "file_path": "test_foo.py",
            "name": "test_fixture",
            "fixture_type": "function",
            "start_line": 10,
            "end_line": 20,
            "loc": 11,
            "mocks": [],
        }

        write_fixture_csv_row(out_path, "owner/repo", "python", fixture)

        # Read and verify columns
        with open(out_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames

            required_columns = [
                "repo_name",
                "language",
                "commit_sha",
                "file_path",
                "fixture_name",
                "fixture_type",
                "start_line",
                "end_line",
                "loc",
                "num_mocks",
            ]

            for col in required_columns:
                assert col in headers, f"Missing required column: {col}"

    def test_fixture_csv_no_truncation(self, tmp_path):
        """Verify fixture CSV data is not truncated."""
        from collection.corpus_utils import write_fixture_csv_row

        out_path = tmp_path / "fixtures.csv"

        # Create a fixture with long field values
        fixture = {
            "commit_sha": "abc123def456abc123def456abc123def456",
            "file_path": "very/long/path/to/test_file_with_long_name.py",
            "name": "test_fixture_with_a_very_long_name_indeed",
            "fixture_type": "function",
            "start_line": 10,
            "end_line": 20,
            "loc": 11,
            "mocks": [],
        }

        write_fixture_csv_row(out_path, "owner/repo", "python", fixture)

        # Verify no truncation
        with open(out_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            row = next(reader)

            assert row["fixture_name"] == fixture["name"]
            assert row["file_path"] == fixture["file_path"]
            assert len(row["commit_sha"]) == len(fixture["commit_sha"])

    def test_fixture_csv_encoding_utf8(self, tmp_path):
        """Verify fixture CSV uses UTF-8 encoding."""
        from collection.corpus_utils import write_fixture_csv_row

        out_path = tmp_path / "fixtures.csv"

        # Create a fixture with special characters
        fixture = {
            "commit_sha": "abc123",
            "file_path": "test_café.py",
            "name": "test_特殊_fixture",
            "fixture_type": "function",
            "start_line": 10,
            "end_line": 20,
            "loc": 11,
            "mocks": [],
        }

        write_fixture_csv_row(out_path, "owner/特殊_repo", "python", fixture)

        # Verify content is preserved
        with open(out_path, encoding="utf-8") as f:
            content = f.read()
            assert "café" in content
            assert "特殊" in content

    def test_fixture_csv_proper_quoting_for_fields_with_commas(self, tmp_path):
        """Verify CSV fields with commas are properly quoted."""
        from collection.corpus_utils import write_fixture_csv_row

        out_path = tmp_path / "fixtures.csv"

        # Create a fixture with commas in field values
        fixture = {
            "commit_sha": "abc123",
            "file_path": "test_foo.py",
            "name": "fixture, with, commas",
            "fixture_type": "function",
            "start_line": 10,
            "end_line": 20,
            "loc": 11,
            "mocks": [],
        }

        write_fixture_csv_row(out_path, "owner/repo", "python", fixture)

        # Read and verify comma handling
        with open(out_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            row = next(reader)

            # Should preserve the commas
            assert row["fixture_name"] == "fixture, with, commas"


