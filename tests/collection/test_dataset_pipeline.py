"""Real (non-mocked) end-to-end tests for collection.dataset_pipeline.

Replaces the old phase_4/5/6_7/8 scripts, which relayed state through
timestamped JSON files and hardcoded exactly two datasets (human, agent).
These tests build tiny real SQLite DBs and run analyze_distribution ->
sample_dataset -> export_dataset -> validate_dataset against them for real
(no mocking of the sampler/exporter/validator), since that combination was
never previously exercised end-to-end -- doing so here caught a real bug in
dataset_exporter.py (see test_export_handles_empty_table_gracefully).
"""

from __future__ import annotations

import sqlite3

import pytest

from collection.dataset_pipeline import (
    analyze_distribution,
    export_dataset,
    sample_dataset,
    validate_dataset,
)
from collection.db import initialise_db


def _build_db(path, n, agent=False):
    initialise_db(path)
    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT INTO repositories (github_id, full_name, language, clone_url) "
        "VALUES (1, 'o/r', 'python', 'https://x.git')"
    )
    repo_id = conn.execute("SELECT id FROM repositories").fetchone()[0]
    conn.execute(
        "INSERT INTO test_files (repo_id, relative_path, language) "
        "VALUES (?, 'tests/test_x.py', 'python')",
        (repo_id,),
    )
    file_id = conn.execute("SELECT id FROM test_files").fetchone()[0]
    for i in range(n):
        scope = "per_test" if i % 2 == 0 else "per_module"
        conn.execute(
            "INSERT INTO fixtures "
            "(file_id, repo_id, name, fixture_type, scope, raw_source, commit_sha, agent_type) "
            "VALUES (?, ?, ?, 'pytest_decorator', ?, 'def f(): pass', ?, ?)",
            (
                file_id,
                repo_id,
                f"fixture_{i}",
                scope,
                "sha1" if agent else None,
                "claude" if agent else None,
            ),
        )
    conn.commit()
    conn.close()


@pytest.fixture
def db_root(tmp_path):
    root = tmp_path / "db"
    root.mkdir()
    return root


@pytest.fixture
def output_dir(tmp_path):
    return tmp_path / "output"


@pytest.fixture
def export_root(tmp_path):
    return tmp_path / "export"


class TestAnalyzeDistribution:
    def test_recommends_smaller_dataset_as_target(self, db_root):
        _build_db(db_root / "a.db", 10, agent=True)
        _build_db(db_root / "b.db", 6)

        result = analyze_distribution("a", "b", db_root=db_root)

        assert result["a"]["statistics"]["total_fixtures"] == 10
        assert result["b"]["statistics"]["total_fixtures"] == 6
        assert result["sampling_recommendation"]["target_count"] == 6

    def test_raises_when_db_missing(self, db_root):
        _build_db(db_root / "a.db", 5)
        with pytest.raises(FileNotFoundError, match="extract-fixtures --dataset b"):
            analyze_distribution("a", "b", db_root=db_root)


class TestSampleDataset:
    def test_samples_to_exact_target_count(self, db_root, output_dir):
        _build_db(db_root / "a.db", 10, agent=True)

        result = sample_dataset("a", target_count=4, db_root=db_root, output_dir=output_dir)

        assert result["sampled_count"] == 4
        assert (output_dir / "sample_a.json").exists()

    def test_none_target_count_samples_everything(self, db_root, output_dir):
        _build_db(db_root / "a.db", 7, agent=True)

        result = sample_dataset("a", db_root=db_root, output_dir=output_dir)

        assert result["sampled_count"] == 7

    def test_raises_when_no_fixtures(self, db_root, output_dir):
        initialise_db(db_root / "a.db")
        with pytest.raises(ValueError, match="No fixtures found"):
            sample_dataset("a", db_root=db_root, output_dir=output_dir)


class TestExportAndValidateDataset:
    def test_full_pipeline_agent_dataset(self, db_root, output_dir, export_root):
        _build_db(db_root / "a.db", 6, agent=True)
        sample_dataset("a", db_root=db_root, output_dir=output_dir)

        zip_path = export_dataset(
            "a", db_root=db_root, export_root=export_root, sample_output_dir=output_dir
        )

        assert zip_path == export_root / "a.zip"
        assert zip_path.exists()

        report = validate_dataset("a", export_root=export_root)
        assert report["valid"] is True
        assert report["zip_validation"]["agents_md_present"] is True

    def test_full_pipeline_human_dataset(self, db_root, output_dir, export_root):
        _build_db(db_root / "b.db", 6, agent=False)
        sample_dataset("b", db_root=db_root, output_dir=output_dir)

        export_dataset(
            "b", db_root=db_root, export_root=export_root, sample_output_dir=output_dir
        )

        report = validate_dataset("b", export_root=export_root)
        assert report["valid"] is True
        # Dataset B/C are not agent datasets -- no AGENTS.md required.
        assert report["zip_validation"]["agents_md_present"] is False

    def test_export_handles_empty_table_gracefully(self, db_root, output_dir, export_root):
        """Regression: export_table_to_csv() used to skip writing the CSV
        entirely when a table had zero matching rows (e.g. mock_usages for a
        sample with no mocks), so the later zip/size step crashed with
        FileNotFoundError trying to stat() a file that was never created.
        Every DB built by _build_db() here has zero mock_usages rows, so
        this is exercised by every test in this class -- this test just
        makes the regression explicit."""
        _build_db(db_root / "a.db", 3, agent=True)
        sample_dataset("a", db_root=db_root, output_dir=output_dir)

        zip_path = export_dataset(
            "a", db_root=db_root, export_root=export_root, sample_output_dir=output_dir
        )

        import zipfile

        with zipfile.ZipFile(zip_path) as zf:
            assert "mock_usages.csv" in zf.namelist()
            with zf.open("mock_usages.csv") as f:
                content = f.read().decode("utf-8")
        assert content.strip() != ""  # header row present, even with 0 data rows

    def test_export_raises_without_prior_sample(self, db_root, output_dir, export_root):
        _build_db(db_root / "a.db", 3, agent=True)
        with pytest.raises(FileNotFoundError, match="sample --dataset a"):
            export_dataset(
                "a", db_root=db_root, export_root=export_root, sample_output_dir=output_dir
            )
