"""
Comprehensive tests for corpus_utils shared utilities.

Tests the new shared utilities module that provides common functions
for both agent and human corpus collection.
"""

import csv
from pathlib import Path
from unittest.mock import patch

from collection.corpus_utils import (
    BaseCorpusStats,
    compute_repo_metadata,
    construct_repo_dict,
    generate_corpus_summary,
    persist_repository_and_fixtures,
    truncate_fixture_csvs,
    write_fixture_csv_row,
)


class TestBaseCorpusStats:
    """Test BaseCorpusStats dataclass and methods."""

    def test_base_corpus_stats_initialization(self):
        """Verify BaseCorpusStats initializes with default values."""
        stats = BaseCorpusStats()
        assert stats.repos_scanned == 0
        assert stats.repos_passed_qc == 0
        assert stats.repos_failed_qc == 0
        assert stats.fixtures_collected == 0
        assert stats.qc_skip_reasons == {}
        assert stats.domain_distribution == {}

    def test_base_corpus_stats_record_skip(self):
        """Verify record_skip method updates counts correctly."""
        stats = BaseCorpusStats()

        stats.record_skip("clone_failed")
        assert stats.repos_failed_qc == 1
        assert stats.qc_skip_reasons["clone_failed"] == 1

        stats.record_skip("clone_failed")
        assert stats.repos_failed_qc == 2
        assert stats.qc_skip_reasons["clone_failed"] == 2

        stats.record_skip("no_commits")
        assert stats.repos_failed_qc == 3
        assert stats.qc_skip_reasons["no_commits"] == 1

    def test_base_corpus_stats_to_dict(self):
        """Verify to_dict serializes all fields."""
        stats = BaseCorpusStats(
            repos_scanned=10,
            repos_passed_qc=8,
            fixtures_collected=42,
        )

        result = stats.to_dict()
        assert isinstance(result, dict)
        assert result["repos_scanned"] == 10
        assert result["repos_passed_qc"] == 8
        assert result["fixtures_collected"] == 42
        assert "qc_skip_reasons" in result
        assert "domain_distribution" in result


class TestComputeRepoMetadata:
    """Test repository metadata computation."""

    def test_compute_repo_metadata_returns_all_fields(self):
        """Verify function returns domain, star_tier, and repo_age."""
        repo = {
            "topics": '["django", "web"]',
            "description": "Web framework",
            "stars": 1000,
            "created_at": "2015-01-01",
        }

        result = compute_repo_metadata(repo, "2020-12-31")

        assert "domain" in result
        assert "star_tier" in result
        assert "repo_age_years" in result
        assert isinstance(result["domain"], str)
        assert isinstance(result["star_tier"], str)

    def test_compute_repo_metadata_with_web_domain(self):
        """Verify web domain is detected from topics."""
        repo = {
            "topics": '["django", "flask", "rest"]',
            "description": "",
            "stars": 100,
            "created_at": "2015-01-01",
        }

        result = compute_repo_metadata(repo, "2020-12-31")
        assert result["domain"] == "web"

    def test_compute_repo_metadata_with_ml_domain(self):
        """Verify ML domain is detected from topics."""
        repo = {
            "topics": '["machine learning", "tensorflow"]',
            "description": "",
            "stars": 5000,
            "created_at": "2015-01-01",
        }

        result = compute_repo_metadata(repo, "2020-12-31")
        assert result["domain"] == "ml"

    def test_compute_repo_metadata_star_tier_low(self):
        """Verify star_tier classification for low stars."""
        repo = {
            "topics": "[]",
            "description": "",
            "stars": 100,
            "created_at": "2015-01-01",
        }

        result = compute_repo_metadata(repo, "2020-12-31")
        assert result["star_tier"] in ["extended", "core"]

    def test_compute_repo_metadata_repo_age(self):
        """Verify repo age is computed correctly."""
        repo = {
            "topics": "[]",
            "description": "",
            "stars": 0,
            "created_at": "2015-01-01",
        }

        result = compute_repo_metadata(repo, "2020-12-31")
        # 2015 to 2021 = 6 years
        assert isinstance(result["repo_age_years"], (float, type(None)))
        if result["repo_age_years"] is not None:
            assert result["repo_age_years"] > 5  # Approximate


class TestConstructRepoDict:
    """Test repository dictionary construction."""

    def test_construct_repo_dict_has_all_required_fields(self):
        """Verify constructed dict has all required DB fields."""
        result = construct_repo_dict(
            full_name="owner/repo",
            language="python",
        )

        required_fields = [
            "github_id",
            "full_name",
            "language",
            "stars",
            "forks",
            "description",
            "topics",
            "created_at",
            "pushed_at",
            "clone_url",
            "num_contributors",
        ]

        for field in required_fields:
            assert field in result

    def test_construct_repo_dict_default_clone_url(self):
        """Verify clone_url defaults to GitHub URL if not provided."""
        result = construct_repo_dict(
            full_name="owner/repo",
            language="python",
            clone_url="",
        )

        assert result["clone_url"] == "https://github.com/owner/repo.git"

    def test_construct_repo_dict_explicit_clone_url(self):
        """Verify clone_url is used if provided."""
        custom_url = "https://git.example.com/owner/repo.git"
        result = construct_repo_dict(
            full_name="owner/repo",
            language="python",
            clone_url=custom_url,
        )

        assert result["clone_url"] == custom_url

    def test_construct_repo_dict_with_all_fields(self):
        """Verify all fields are correctly assigned."""
        result = construct_repo_dict(
            full_name="owner/repo",
            language="python",
            stars=100,
            forks=10,
            description="Test repo",
            topics='["testing"]',
            created_at="2020-01-01T00:00:00Z",
            pushed_at="2020-12-31T00:00:00Z",
            clone_url="https://github.com/owner/repo.git",
            github_id=12345,
            num_contributors=5,
            domain="web",
            star_tier="tier_mid",
            repo_age_years=1.5,
        )

        assert result["full_name"] == "owner/repo"
        assert result["language"] == "python"
        assert result["stars"] == 100
        assert result["forks"] == 10
        assert result["description"] == "Test repo"
        assert result["domain"] == "web"
        assert result["star_tier"] == "tier_mid"
        assert result["repo_age_years"] == 1.5


class TestWriteFixtureCsvRow:
    """Test fixture CSV row writing."""

    def test_write_fixture_csv_row_creates_file_with_header(self, tmp_path):
        """Verify CSV file is created with header on first write."""
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
        }

        write_fixture_csv_row(out_path, "owner/repo", "python", fixture)

        assert out_path.exists()
        content = out_path.read_text()
        assert "repo_name" in content  # Header
        assert "owner/repo" in content  # Data

    def test_write_fixture_csv_row_appends_without_header(self, tmp_path):
        """Verify subsequent writes append without header."""
        out_path = tmp_path / "fixtures.csv"

        fixture1 = {
            "commit_sha": "abc123",
            "file_path": "test_foo.py",
            "name": "fixture1",
            "fixture_type": "function",
            "start_line": 10,
            "end_line": 20,
            "loc": 11,
            "framework": "pytest",
        }
        fixture2 = {
            "commit_sha": "def456",
            "file_path": "test_bar.py",
            "name": "fixture2",
            "fixture_type": "function",
            "start_line": 30,
            "end_line": 40,
            "loc": 11,
            "framework": "pytest",
        }

        write_fixture_csv_row(out_path, "owner/repo", "python", fixture1)
        write_fixture_csv_row(out_path, "owner/repo", "python", fixture2)

        content = out_path.read_text()
        lines = content.strip().split("\n")
        # 1 header + 2 data rows
        assert len(lines) == 3
        assert "fixture1" in content
        assert "fixture2" in content

    def test_write_fixture_csv_row_with_extra_fields(self, tmp_path):
        """Verify extra fields are included in CSV."""
        out_path = tmp_path / "fixtures.csv"

        fixture = {
            "commit_sha": "abc123",
            "file_path": "test_foo.py",
            "name": "fixture",
            "fixture_type": "function",
            "start_line": 10,
            "end_line": 20,
            "loc": 11,
            "framework": "pytest",
        }

        write_fixture_csv_row(
            out_path,
            "owner/repo",
            "python",
            fixture,
            extra_fields={"is_complete_addition": 1},
        )

        content = out_path.read_text()
        assert "is_complete_addition" in content

    def test_write_fixture_csv_row_preserves_fixture_agent_type(self, tmp_path):
        """Fixture's own agent_type should be passed via extra_fields value.

        Regression test for agent_corpus.py: when writing per-fixture CSV
        rows, the caller must pass fixture.get('agent_type', fallback) as
        the extra_fields value, not the outer-loop's stale agent_type.
        """
        out_path = tmp_path / "fixtures.csv"

        fixture = {
            "commit_sha": "cursor_sha",
            "file_path": "test_foo.py",
            "name": "test_bar",
            "fixture_type": "pytest_decorator",
            "start_line": 10,
            "end_line": 20,
            "loc": 10,
            "framework": "pytest",
            "agent_type": "cursor",
        }

        # Correct call pattern (as fixed in agent_corpus.py):
        # pass fixture.get('agent_type', fallback) as the value
        write_fixture_csv_row(
            out_path,
            "owner/repo",
            "python",
            fixture,
            extra_fields={
                "agent_type": fixture.get("agent_type", "claude"),
                "commit_kind": "agent",
            },
        )

        with out_path.open(newline="") as fh:
            row = next(csv.DictReader(fh))

        assert row["agent_type"] == "cursor"
        assert row["commit_kind"] == "agent"

    def test_write_fixture_csv_row_falls_back_to_extra_agent_type(self, tmp_path):
        """When fixture has no agent_type, extra_fields fallback is used."""
        out_path = tmp_path / "fixtures.csv"

        fixture = {
            "commit_sha": "abc123",
            "file_path": "test_foo.py",
            "name": "test_bar",
            "fixture_type": "pytest_decorator",
            "start_line": 10,
            "end_line": 20,
            "loc": 10,
            "framework": "pytest",
        }

        write_fixture_csv_row(
            out_path,
            "owner/repo",
            "python",
            fixture,
            extra_fields={
                "agent_type": "copilot",
                "commit_kind": "agent",
            },
        )

        with out_path.open(newline="") as fh:
            row = next(csv.DictReader(fh))

        assert row["agent_type"] == "copilot"

    def test_write_fixture_csv_row_includes_commit_type(self, tmp_path):
        """commit_type (Dataset A conventional-commit classification) is
        written straight from the fixture dict."""
        out_path = tmp_path / "fixtures.csv"

        fixture = {
            "commit_sha": "abc123",
            "file_path": "test_foo.py",
            "name": "test_bar",
            "fixture_type": "pytest_decorator",
            "start_line": 10,
            "end_line": 20,
            "loc": 10,
            "framework": "pytest",
            "agent_type": "claude",
            "commit_type": "test",
        }

        write_fixture_csv_row(out_path, "owner/repo", "python", fixture)

        with out_path.open(newline="") as fh:
            row = next(csv.DictReader(fh))

        assert row["commit_type"] == "test"

    def test_write_fixture_csv_row_defaults_commit_type_to_empty(self, tmp_path):
        """Fixtures with no commit_type (e.g. Dataset B/C) get an empty value."""
        out_path = tmp_path / "fixtures.csv"

        fixture = {
            "commit_sha": "abc123",
            "file_path": "test_foo.py",
            "name": "test_bar",
            "fixture_type": "pytest_decorator",
            "start_line": 10,
            "end_line": 20,
            "loc": 10,
            "framework": "pytest",
        }

        write_fixture_csv_row(out_path, "owner/repo", "python", fixture)

        with out_path.open(newline="") as fh:
            row = next(csv.DictReader(fh))

        assert row["commit_type"] == ""


class TestBuildGithubUrl:
    """Test _build_github_url helper."""

    def test_basic_url(self):
        from collection.corpus_utils import _build_github_url

        url = _build_github_url("owner/repo", "abc123def", "tests/test_foo.py", 10, 20)
        assert (
            url
            == "https://github.com/owner/repo/blob/abc123def/tests/test_foo.py#L10-L20"
        )

    def test_leading_slash_stripped(self):
        from collection.corpus_utils import _build_github_url

        url = _build_github_url("owner/repo", "abc123", "/tests/test_foo.py", 1, 5)
        assert url.startswith("https://github.com/owner/repo/blob/abc123/tests/")

    def test_no_lines_returns_no_anchor(self):
        from collection.corpus_utils import _build_github_url

        url = _build_github_url("owner/repo", "abc123", "tests/test_foo.py", 0, 0)
        assert url == "https://github.com/owner/repo/blob/abc123/tests/test_foo.py"

    def test_missing_fields_returns_empty(self):
        from collection.corpus_utils import _build_github_url

        assert _build_github_url("", "abc123", "tests/test_foo.py", 1, 5) == ""
        assert _build_github_url("owner/repo", "", "tests/test_foo.py", 1, 5) == ""
        assert _build_github_url("owner/repo", "abc123", "", 1, 5) == ""


class TestPersistRepositoryAndFixtures:
    """Test repository and fixture persistence (CSV + DB)."""

    def test_persist_returns_fixture_count(self):
        """Verify function returns number of fixtures persisted."""
        repo_data = {
            "github_id": 123,
            "full_name": "owner/repo",
            "language": "python",
            "stars": 100,
            "forks": 10,
            "description": "Test",
            "topics": "[]",
            "created_at": "",
            "pushed_at": "",
            "clone_url": "https://github.com/owner/repo.git",
            "num_contributors": 5,
        }
        fixtures = [
            {
                "commit_sha": "abc123",
                "file_path": "test_foo.py",
                "name": "fixture",
                "fixture_type": "function",
                "start_line": 10,
                "end_line": 20,
                "loc": 11,
                "framework": "pytest",
                "mocks": [],
            }
        ]

        with patch("collection.corpus_utils.db_session"):
            with patch("collection.corpus_utils.upsert_repository") as mock_upsert:
                with patch("collection.corpus_utils.insert_fixture"):
                    mock_upsert.return_value = (1, False)
                    count = persist_repository_and_fixtures(
                        Path("/tmp/test.db"),
                        repo_data,
                        fixtures,
                    )
                    assert count == 1

    def test_persist_with_csv_export(self, tmp_path):
        """Verify CSV export when out_path provided."""
        repo_data = {
            "github_id": 123,
            "full_name": "owner/repo",
            "language": "python",
            "stars": 100,
            "forks": 10,
            "description": "Test",
            "topics": "[]",
            "created_at": "",
            "pushed_at": "",
            "clone_url": "https://github.com/owner/repo.git",
            "num_contributors": 5,
        }
        fixtures = [
            {
                "commit_sha": "abc123",
                "file_path": "test_foo.py",
                "name": "fixture",
                "fixture_type": "function",
                "start_line": 10,
                "end_line": 20,
                "loc": 11,
                "framework": "pytest",
                "mocks": [],
            }
        ]
        out_path = tmp_path / "fixtures.csv"

        with patch("collection.corpus_utils.db_session"):
            with patch("collection.corpus_utils.upsert_repository") as mock_upsert:
                with patch("collection.corpus_utils.insert_fixture"):
                    mock_upsert.return_value = (1, False)
                    persist_repository_and_fixtures(
                        Path("/tmp/test.db"),
                        repo_data,
                        fixtures,
                        out_path=out_path,
                    )

                    assert out_path.exists()
                    content = out_path.read_text()
                    assert "owner/repo" in content
                    assert "fixture" in content

    def test_persist_writes_commit_type_to_db_and_csv(self, tmp_path):
        """commit_type (Dataset A conventional-commit classification) reaches
        both the fixtures table and the CSV export, end-to-end against a
        real (non-mocked) database."""
        from collection.db import initialise_db

        db_path = tmp_path / "test.db"
        initialise_db(db_path)

        repo_data = {
            "github_id": 456,
            "full_name": "owner/agentrepo",
            "language": "python",
            "stars": 10,
            "forks": 0,
            "description": "",
            "topics": "[]",
            "created_at": "",
            "pushed_at": "",
            "clone_url": "https://github.com/owner/agentrepo.git",
            "num_contributors": 1,
            "domain": None,
            "star_tier": None,
            "repo_age_years": None,
        }
        fixtures = [
            {
                "commit_sha": "abc123",
                "file_path": "tests/test_foo.py",
                "name": "my_fixture",
                "fixture_type": "pytest_decorator",
                "start_line": 1,
                "end_line": 3,
                "loc": 3,
                "framework": "pytest",
                "agent_type": "claude",
                "commit_kind": "agent",
                "commit_type": "test",
                "mocks": [],
            }
        ]
        out_path = tmp_path / "fixtures.csv"

        persist_repository_and_fixtures(
            db_path, repo_data, fixtures, out_path=out_path
        )

        with out_path.open(newline="") as fh:
            row = next(csv.DictReader(fh))
        assert row["commit_type"] == "test"

        import sqlite3

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        db_row = conn.execute(
            "SELECT commit_type FROM fixtures WHERE name = 'my_fixture'"
        ).fetchone()
        conn.close()
        assert db_row["commit_type"] == "test"

    def test_persist_with_empty_fixtures(self):
        """Verify handling of empty fixture list."""
        repo_data = {
            "github_id": 123,
            "full_name": "owner/repo",
            "language": "python",
            "stars": 100,
            "forks": 10,
            "description": "Test",
            "topics": "[]",
            "created_at": "",
            "pushed_at": "",
            "clone_url": "https://github.com/owner/repo.git",
            "num_contributors": 5,
        }

        with patch("collection.corpus_utils.db_session"):
            with patch("collection.corpus_utils.upsert_repository") as mock_upsert:
                mock_upsert.return_value = (1, False)
                count = persist_repository_and_fixtures(
                    Path("/tmp/test.db"),
                    repo_data,
                    [],
                )
                assert count == 0


class TestGenerateCorpusSummary:
    """Test corpus summary generation."""

    def test_generate_corpus_summary_creates_json_file(self, tmp_path):
        """Verify summary file is created."""
        stats = BaseCorpusStats(
            repos_scanned=100,
            repos_passed_qc=80,
            fixtures_collected=1500,
        )

        with patch("collection.corpus_utils.Path") as mock_path_class:
            mock_output_dir = tmp_path / "output"
            mock_output_dir.mkdir()
            mock_path_class.return_value = mock_output_dir

            # Mock the datetime for predictable filename
            with patch("collection.corpus_utils.datetime") as mock_datetime:
                mock_datetime.now.return_value.isoformat.return_value = (
                    "2026-05-24T12:00:00"
                )
                mock_datetime.now.return_value.strftime.return_value = "20260524_120000"

                summary_path = generate_corpus_summary(
                    stats,
                    "test_corpus",
                    Path("/tmp/test.db"),
                    "since 2020-12-31",
                    extra_metadata={"test": "value"},
                )

                assert summary_path is not None

    def test_generate_corpus_summary_json_structure(self, tmp_path):
        """Verify summary JSON has expected structure."""
        stats = BaseCorpusStats(
            repos_scanned=100,
            repos_passed_qc=80,
            repos_failed_qc=20,
            fixtures_collected=1500,
            test_commits_found=500,
            domain_distribution={"web": 50, "ml": 30},
            star_tier_distribution={"tier_low": 60, "tier_high": 40},
            mean_repo_age_years=3.5,
            mean_contributors=8.2,
        )

        # Patch Path to use tmp_path
        with patch("collection.corpus_utils.Path") as mock_path_class:
            output_dir = tmp_path / "output"
            output_dir.mkdir()

            # Make Path() return tmp_path/output for the parent call
            def path_side_effect(arg=None):
                if arg == ".":
                    return tmp_path
                return output_dir

            mock_path_class.side_effect = lambda *args: (
                output_dir if not args else output_dir / args[0]
            )

            # Just test the structure by checking what gets passed to json.dump
            with patch("builtins.open", create=True):
                with patch("json.dump") as mock_json_dump:
                    generate_corpus_summary(
                        stats,
                        "test_corpus",
                        Path("/tmp/test.db"),
                        "since 2020-12-31",
                    )

                    # Verify json.dump was called
                    assert mock_json_dump.called
                    # Get the data that was passed to json.dump
                    call_args = mock_json_dump.call_args
                    summary_data = call_args[0][0]

                    # Verify structure
                    assert "timestamp" in summary_data
                    assert "methodology" in summary_data
                    assert "summary_statistics" in summary_data
                    assert "control_variables" in summary_data
                    assert (
                        summary_data["summary_statistics"]["fixtures_collected"] == 1500
                    )
                    assert (
                        summary_data["control_variables"]["mean_repo_age_years"] == 3.5
                    )


class TestTruncateFixtureCsvs:
    """Test truncation of output CSV files before collection runs."""

    def test_truncate_removes_existing_files(self, tmp_path):
        """Verify truncate_fixture_csvs removes existing CSV files."""
        csv_a = tmp_path / "python_agent_fixtures.csv"
        csv_b = tmp_path / "repos" / "python_agent_fixture_repos.csv"
        csv_b.parent.mkdir(parents=True, exist_ok=True)

        csv_a.write_text("old,data\nrow1\n")
        csv_b.write_text("old,data\nrow1\n")

        truncate_fixture_csvs([csv_a, csv_b])

        assert not csv_a.exists()
        assert not csv_b.exists()

    def test_truncate_ignores_missing_files(self, tmp_path):
        """Verify truncate_fixture_csvs does not fail on missing files."""
        missing = tmp_path / "nonexistent.csv"
        truncate_fixture_csvs([missing])
        # Should not raise

    def test_truncate_then_write_produces_fresh_file(self, tmp_path):
        """Verify that after truncation, a new write produces a clean file."""
        csv_path = tmp_path / "fixtures.csv"

        # Simulate a previous run
        csv_path.write_text("repo_name,language\nold/repo,python\n")

        # Truncate
        truncate_fixture_csvs([csv_path])

        # New run writes fresh data
        write_fixture_csv_row(
            csv_path,
            "new/repo",
            "python",
            {
                "commit_sha": "abc",
                "file_path": "test.py",
                "name": "fixture",
                "fixture_type": "function",
                "start_line": 1,
                "end_line": 3,
                "loc": 3,
                "framework": "pytest",
            },
        )

        content = csv_path.read_text()
        lines = content.strip().split("\n")
        assert len(lines) == 2  # header + 1 data row
        assert "new/repo" in content
        assert "old/repo" not in content
