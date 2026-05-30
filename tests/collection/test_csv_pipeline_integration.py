"""
CSV Pipeline Integration Tests - Use Case 1.

Tests manual pipeline execution with real CSV input/output files.
Verifies that the collection module correctly:
1. Reads input CSV files (repo-QC, test-commit CSVs)
2. Processes repositories based on CSV data
3. Exports output fixtures to properly formatted CSV files
"""

import csv
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, ANY

import pytest

from collection.human_corpus import (
    HumanCorpusCollector,
    select_human_corpus_repositories,
)
from collection.config import HUMAN_CORPUS_CUTOFF_DATE


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


@pytest.fixture
def sample_human_test_commit_qc_csv(tmp_csv_dir, make_csv):
    make_csv(tmp_csv_dir, "python_human_test_commit_qc.csv")
    return tmp_csv_dir / "python_human_test_commit_qc.csv"


class TestCSVRepositorySelection:
    """Test CSV file reading and repository selection."""

    def test_select_human_corpus_repositories_reads_csv_file(
        self, sample_agent_repo_csv
    ):
        """Verify CSV file is read and repositories are selected."""
        csv_dir = sample_agent_repo_csv.parent

        repos = select_human_corpus_repositories(
            csv_dir,
            repos_per_language=None,  # All rows
            language="python",
        )

        assert len(repos) >= 1
        assert any(repo["full_name"] == "owner1/repo_python" for repo in repos)

    def test_select_human_corpus_repositories_respects_language_filter(
        self, tmp_csv_dir, make_csv
    ):
        """Verify language filter is applied."""
        # Use generated mixed CSV sample
        make_csv(tmp_csv_dir, "mixed_agent_repo.csv")

        repos = select_human_corpus_repositories(
            tmp_csv_dir,
            repos_per_language=None,
            language="python",
        )

        # Should only have Python repos
        assert all(repo["language"] == "python" for repo in repos)
        assert any(repo["full_name"] == "owner/repo_python" for repo in repos)

    def test_select_human_corpus_repositories_respects_per_language_cap(
        self, tmp_csv_dir, make_csv
    ):
        """Verify per-language cap is applied."""
        # Use generated sample with multiple Python repos
        make_csv(tmp_csv_dir, "python_agent_repo.csv")

        repos = select_human_corpus_repositories(
            tmp_csv_dir,
            repos_per_language=2,  # Cap at 2
            language="python",
        )

        # Should have exactly 2 repos
        assert len(repos) == 2

    def test_select_human_corpus_repositories_all_rows_when_none(self, tmp_csv_dir):
        """Verify None for repos_per_language means all rows."""
        csv_path = tmp_csv_dir / "python_agent_repo.csv"

        rows = [
            {
                "repo_name": f"owner{i}/repo",
                "full_name": f"owner{i}/repo",
                "language": "python",
                "stars": 100,
                "forks": 10,
                "num_contributors": 5,
                "clone_url": "https://github.com/owner/repo.git",
                "has_agent_config": "1",
            }
            for i in range(5)
        ]

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

        repos = select_human_corpus_repositories(
            tmp_csv_dir,
            repos_per_language=None,  # All rows
            language="python",
        )

        # Should have all 5 repos
        assert len(repos) == 5

    def test_select_human_corpus_restricts_to_agent_test_commits(self, tmp_path, make_csv):
        """When agent test-commit CSVs exist, selection is restricted to those repos."""
        input_dir = tmp_path / "input"
        input_dir.mkdir()

        # Create tests_commits subdir with a single agent test-commit repo
        tests_dir = input_dir / "tests_commits"
        tests_dir.mkdir()

        tpath = tests_dir / "python_agent_test_commit.csv"
        with open(tpath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "repo_name",
                    "language",
                    "commit_sha",
                    "commit_role",
                    "agent_type",
                    "commit_date",
                    "test_file_count",
                    "test_file_paths",
                ],
            )
            writer.writeheader()
            writer.writerow(
                {
                    "repo_name": "owner/only_test_repo",
                    "language": "python",
                    "commit_sha": "abc123",
                    "commit_role": "agent",
                    "agent_type": "claude",
                    "commit_date": "2026-01-01T00:00:00Z",
                    "test_file_count": "1",
                    "test_file_paths": '["tests/test_foo.py"]',
                }
            )

        # Create agent_repo csv containing two repos, only one of which appears
        # Create sample repo CSV and test-commit CSV for selection test
        make_csv(input_dir, "python_agent_test_commit.csv", dest_name="tests_commits/python_agent_test_commit.csv")

        # Write agent_repo CSV that lists the two repos referenced in this test
        csv_path = input_dir / "python_agent_repo.csv"
        rows = [
            {
                "repo_name": "owner/only_test_repo",
                "full_name": "owner/only_test_repo",
                "language": "python",
                "stars": 100,
                "forks": 10,
                "num_contributors": 1,
                "clone_url": "",
                "has_agent_config": "1",
            },
            {
                "repo_name": "owner/other_repo",
                "full_name": "owner/other_repo",
                "language": "python",
                "stars": 50,
                "forks": 5,
                "num_contributors": 1,
                "clone_url": "",
                "has_agent_config": "1",
            },
        ]

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

        repos = select_human_corpus_repositories(
            input_dir, repos_per_language=None, language="python"
        )

        assert len(repos) == 1
        assert repos[0]["full_name"] == "owner/only_test_repo"

    def test_select_human_corpus_fallback_when_no_tests_commits(self, tmp_path, make_csv):
        """When no tests_commits directory exists, selection falls back to agent_repo CSVs."""
        input_dir = tmp_path / "input"
        input_dir.mkdir()

        # Use committed small sample CSV with exactly two repos (copy into expected name)
        make_csv(input_dir, "python_agent_repo_small.csv", dest_name="python_agent_repo.csv")

        repos = select_human_corpus_repositories(
            input_dir, repos_per_language=None, language="python"
        )

        assert len(repos) == 2

    def test_select_human_corpus_prefers_agent_fixture_repo_list(self, tmp_path, make_csv):
        """When an agent fixture repo list exists, it should be preferred."""
        input_dir = tmp_path / "input"
        input_dir.mkdir()

        # Create fixtures-from-agents directory with a per-language repo list
        fixtures_dir = input_dir / "fixtures-from-agents"
        fixtures_dir.mkdir()
        make_csv(fixtures_dir, "python_agent_fixture_repos.csv", dest_name="python_agent_fixture_repos.csv")

        # Also create agent_repo with another repo that should be ignored
        csv_path = input_dir / "python_agent_repo.csv"
        rows = [
            {
                "repo_name": "owner/fixture_repo",
                "full_name": "owner/fixture_repo",
                "language": "python",
                "stars": 100,
                "forks": 10,
                "num_contributors": 1,
                "clone_url": "",
                "has_agent_config": "1",
            },
            {
                "repo_name": "owner/other_repo",
                "full_name": "owner/other_repo",
                "language": "python",
                "stars": 50,
                "forks": 5,
                "num_contributors": 1,
                "clone_url": "",
                "has_agent_config": "1",
            },
        ]

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

        repos = select_human_corpus_repositories(
            input_dir, repos_per_language=None, language="python"
        )

        assert len(repos) == 1
        assert repos[0]["full_name"] == "owner/fixture_repo"


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
            "framework": "pytest",
            "mocks": [],
        }

        write_fixture_csv_row(out_path, "owner/repo", "python", fixture)

        # Read and verify columns
        with open(out_path, "r", encoding="utf-8") as f:
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
                "framework",
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
            "framework": "pytest",
            "mocks": [],
        }

        write_fixture_csv_row(out_path, "owner/repo", "python", fixture)

        # Verify no truncation
        with open(out_path, "r", encoding="utf-8") as f:
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
            "framework": "pytest",
            "mocks": [],
        }

        write_fixture_csv_row(out_path, "owner/特殊_repo", "python", fixture)

        # Verify content is preserved
        with open(out_path, "r", encoding="utf-8") as f:
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
            "framework": "pytest",
            "mocks": [],
        }

        write_fixture_csv_row(out_path, "owner/repo", "python", fixture)

        # Read and verify comma handling
        with open(out_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            row = next(reader)

            # Should preserve the commas
            assert row["fixture_name"] == "fixture, with, commas"


class TestCSVPipelineEndToEnd:
    """Test end-to-end CSV pipeline (read input, process, write output)."""

    def test_csv_pipeline_reads_input_and_writes_output(self, tmp_path):
        """Verify full pipeline: read input CSV → process → write output CSV."""
        # Create input CSV
        input_dir = tmp_path / "input"
        input_dir.mkdir()

        csv_path = input_dir / "python_agent_repo.csv"
        rows = [
            {
                "repo_name": "owner/repo",
                "full_name": "owner/repo",
                "language": "python",
                "stars": 100,
                "forks": 10,
                "num_contributors": 5,
                "clone_url": "https://github.com/owner/repo.git",
                "has_agent_config": "1",
            }
        ]

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

        # Select repositories from input CSV
        repos = select_human_corpus_repositories(
            input_dir,
            repos_per_language=None,
            language="python",
        )

        # Verify input was read correctly
        assert len(repos) == 1
        assert repos[0]["full_name"] == "owner/repo"

        # Create output CSV directory
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # Write output fixture CSV
        from collection.corpus_utils import write_fixture_csv_row

        out_path = output_dir / "python_human_fixtures.csv"
        fixture = {
            "commit_sha": "abc123",
            "file_path": "test_foo.py",
            "name": "test_fixture",
            "fixture_type": "function",
            "start_line": 10,
            "end_line": 20,
            "loc": 11,
            "framework": "pytest",
            "mocks": [],
        }

        write_fixture_csv_row(out_path, repos[0]["full_name"], "python", fixture)

        # Verify output CSV was created and contains expected data
        assert out_path.exists()

        with open(out_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows_out = list(reader)

            assert len(rows_out) == 1
            assert rows_out[0]["repo_name"] == "owner/repo"
            assert rows_out[0]["fixture_name"] == "test_fixture"
