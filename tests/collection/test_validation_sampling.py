from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

import collection.validation_sampling as vs
from collection.validation_sampling import (
    CANONICAL_FIELDNAMES,
    cochran_sample_size,
    run_validation_sampling,
    sample_rows,
)


class TestCochranSampleSize:
    def test_infinite_population_95_5_defaults(self):
        assert cochran_sample_size(None) == 385

    def test_large_population_close_to_infinite_value(self):
        n = cochran_sample_size(100_000)
        assert 380 <= n <= 385

    def test_small_population_finite_correction_reduces_sample(self):
        n = cochran_sample_size(100)
        assert n < 100
        assert n == 80

    def test_never_exceeds_population_size(self):
        assert cochran_sample_size(10) == 10

    def test_zero_population_returns_zero(self):
        assert cochran_sample_size(0) == 0

    def test_stricter_margin_of_error_increases_sample_size(self):
        loose = cochran_sample_size(10_000, margin_of_error=0.1)
        strict = cochran_sample_size(10_000, margin_of_error=0.01)
        assert strict > loose


class TestSampleRows:
    def test_deterministic_given_same_seed(self):
        rows = [{"id": i, "value": f"row-{i}"} for i in range(50)]
        a = sample_rows(rows, 10, seed=1)
        b = sample_rows(rows, 10, seed=1)
        assert a == b

    def test_stable_regardless_of_input_order(self):
        rows = [{"id": i, "value": f"row-{i}"} for i in range(50)]
        shuffled = list(reversed(rows))
        a = sample_rows(rows, 10, seed=1)
        b = sample_rows(shuffled, 10, seed=1)
        assert a == b

    def test_n_greater_than_population_returns_all(self):
        rows = [{"id": i} for i in range(5)]
        assert sample_rows(rows, 10, seed=1) == rows


class TestAllocateStratified:
    def test_sums_to_total_n(self):
        alloc = vs._allocate_stratified({"a": 100, "b": 200, "c": 300}, 60)
        assert sum(alloc.values()) == 60

    def test_never_exceeds_stratum_size(self):
        alloc = vs._allocate_stratified({"a": 5, "b": 500}, 60)
        assert alloc["a"] <= 5
        assert sum(alloc.values()) == 60

    def test_exact_proportional_case(self):
        alloc = vs._allocate_stratified({"a": 100, "b": 200, "c": 300}, 60)
        assert alloc == {"a": 10, "b": 20, "c": 30}

    def test_handles_zero_size_stratum(self):
        alloc = vs._allocate_stratified({"a": 0, "b": 100}, 10)
        assert alloc["a"] == 0
        assert alloc["b"] == 10

    def test_total_n_exceeds_population_caps_at_population(self):
        alloc = vs._allocate_stratified({"a": 3, "b": 4}, 100)
        assert alloc == {"a": 3, "b": 4}

    def test_empty_strata_returns_empty(self):
        assert vs._allocate_stratified({}, 10) == {}


class TestNormalizers:
    def test_normalize_repo_row_uses_matched_config_file(self):
        row = {
            "repo_name": "owner/repo",
            "language": "python",
            "has_agent_config": "1",
            "matched_config_file": "CLAUDE.md",
        }
        out = vs._normalize_repo_row(row)
        assert out["validation_type"] == "repo"
        assert out["repo_full_name"] == "owner/repo"
        assert out["item_id"] == "owner/repo"
        assert out["item_url"] == "https://github.com/owner/repo"
        assert out["detection_signal"] == "CLAUDE.md"
        assert out["evidence"] == "CLAUDE.md"

    def test_normalize_repo_row_falls_back_without_matched_config_file(self):
        row = {"repo_name": "owner/repo", "language": "python", "has_agent_config": "1"}
        out = vs._normalize_repo_row(row)
        assert out["detection_signal"] == "agent_config_present"
        assert out["evidence"] == "agent_config_present"

    def test_normalize_commit_row(self):
        row = {
            "repo_name": "owner/repo",
            "language": "python",
            "commit_sha": "abc123",
            "commit_url": "https://github.com/owner/repo/commit/abc123",
            "agent_type": "claude",
            "commit_date": "2026-01-01T00:00:00Z",
            "author_name": "Bot",
            "author_email": "bot@example.com",
        }
        out = vs._normalize_commit_row(row)
        assert out["item_id"] == "abc123"
        assert out["item_url"] == "https://github.com/owner/repo/commit/abc123"
        assert out["detection_signal"] == "claude"
        assert "agent_type=claude" in out["evidence"]
        assert "commit_date=2026-01-01T00:00:00Z" in out["evidence"]
        assert "Bot <bot@example.com>" in out["evidence"]

    def test_normalize_commit_row_constructs_url_when_missing(self):
        row = {"repo_name": "owner/repo", "commit_sha": "abc123"}
        out = vs._normalize_commit_row(row)
        assert out["item_url"] == "https://github.com/owner/repo/commit/abc123"

    def test_normalize_fixture_row_uses_raw_source(self):
        row = {
            "repo_name": "owner/repo",
            "language": "python",
            "commit_sha": "abc",
            "file_path": "tests/conftest.py",
            "start_line": "10",
            "github_url": "https://github.com/owner/repo/blob/abc/tests/conftest.py#L10-L15",
            "fixture_type": "pytest_decorator",
            "raw_source": "@pytest.fixture\ndef foo(): ...",
        }
        out = vs._normalize_fixture_row(row)
        assert out["item_id"] == "owner/repo:abc:tests/conftest.py:10"
        assert out["item_url"] == row["github_url"]
        assert out["detection_signal"] == "pytest_decorator"
        assert out["evidence"] == row["raw_source"]

    def test_normalize_fixture_row_falls_back_without_raw_source(self):
        row = {
            "repo_name": "owner/repo",
            "commit_sha": "abc",
            "file_path": "x.py",
            "start_line": "1",
            "fixture_type": "pytest_decorator",
        }
        out = vs._normalize_fixture_row(row)
        assert out["evidence"] == ""

    def test_normalize_human_commit_row(self):
        row = {
            "repo_name": "owner/repo",
            "language": "python",
            "commit_sha": "abc123",
            "commit_role": "human",
            "agent_type": "",
            "commit_date": "2026-01-01T00:00:00Z",
            "test_file_count": "2",
        }
        out = vs._normalize_human_commit_row(row)
        assert out["validation_type"] == "human_commit"
        assert out["item_id"] == "abc123"
        assert out["item_url"] == "https://github.com/owner/repo/commit/abc123"
        assert out["detection_signal"] == "classified_as_human"
        assert "commit_role=human" in out["evidence"]
        assert "commit_date=2026-01-01T00:00:00Z" in out["evidence"]
        assert "test_file_count=2" in out["evidence"]

    def test_normalize_human_test_commit_row(self):
        row = {
            "repo_name": "owner/repo",
            "language": "python",
            "commit_sha": "abc123",
            "commit_role": "human",
            "test_file_count": "1",
            "test_file_paths": '["tests/test_foo.py"]',
        }
        out = vs._normalize_human_test_commit_row(row)
        assert out["validation_type"] == "human_test_commit"
        assert out["item_id"] == "abc123"
        assert out["item_url"] == "https://github.com/owner/repo/commit/abc123"
        assert out["detection_signal"] == "test_file_count=1"
        assert out["evidence"] == '["tests/test_foo.py"]'


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _repo_row(i: int, language: str, has_agent_config: str = "1") -> dict:
    return {
        "repo_name": f"{language}/repo{i}",
        "language": language,
        "has_agent_config": has_agent_config,
    }


def _commit_row(i: int, language: str, agent_type: str) -> dict:
    return {
        "repo_name": "owner/repo",
        "language": language,
        "commit_sha": f"sha{i}",
        "agent_type": agent_type,
    }


class TestRunValidationSamplingCombinedMode:
    def test_combines_multiple_files_and_normalizes_schema(self, tmp_path):
        python_csv = tmp_path / "python_agent_repo.csv"
        java_csv = tmp_path / "java_agent_repo.csv"
        _write_csv(python_csv, [_repo_row(i, "python") for i in range(300)])
        _write_csv(java_csv, [_repo_row(i, "java") for i in range(300)])
        output_root = tmp_path / "validation-samples"

        metadata = run_validation_sampling(
            step="agent-repos",
            input_paths=[python_csv, java_csv],
            seed=7,
            output_root=output_root,
        )

        assert metadata["population_mode"] == "combined"
        assert len(metadata["outputs"]) == 1
        entry = metadata["outputs"][0]
        assert entry["population_size"] == 600
        expected_n = cochran_sample_size(600)
        assert entry["sample_size"] == expected_n

        out_path = Path(entry["output_file"])
        assert out_path.exists()
        with out_path.open(encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            assert reader.fieldnames == CANONICAL_FIELDNAMES
            rows = list(reader)
        assert len(rows) == expected_n
        assert all(r["validation_type"] == "repo" for r in rows)
        assert all(r["label"] == "" and r["reviewer_notes"] == "" for r in rows)
        assert {r["validation_id"] for r in rows} == {
            f"agent-repos-{i + 1:04d}" for i in range(expected_n)
        }

        metadata_files = list((output_root / "agent-repos").glob("sample_metadata_*.json"))
        assert len(metadata_files) == 1
        with metadata_files[0].open(encoding="utf-8") as fh:
            assert json.load(fh) == metadata

    def test_filters_out_repos_not_flagged_agent_positive(self, tmp_path):
        rows = [_repo_row(i, "python", "1") for i in range(10)] + [
            _repo_row(i, "python", "0") for i in range(20)
        ]
        csv_path = tmp_path / "python_agent_repo.csv"
        _write_csv(csv_path, rows)

        metadata = run_validation_sampling(
            "agent-repos", [csv_path], output_root=tmp_path / "validation-samples"
        )

        assert metadata["outputs"][0]["population_size"] == 10

    def test_repo_step_stratifies_by_language_proportionally(self, tmp_path):
        python_csv = tmp_path / "python_agent_repo.csv"
        java_csv = tmp_path / "java_agent_repo.csv"
        _write_csv(python_csv, [_repo_row(i, "python") for i in range(300)])
        _write_csv(java_csv, [_repo_row(i, "java") for i in range(300)])

        metadata = run_validation_sampling(
            "agent-repos",
            [python_csv, java_csv],
            output_root=tmp_path / "validation-samples",
        )

        entry = metadata["outputs"][0]
        strata = {s["key"]["language"]: s for s in entry["strata"]}
        assert set(strata) == {"python", "java"}
        assert strata["python"]["population_size"] == 300
        assert strata["java"]["population_size"] == 300
        assert abs(strata["python"]["sample_size"] - strata["java"]["sample_size"]) <= 1
        assert (
            strata["python"]["sample_size"] + strata["java"]["sample_size"]
            == entry["sample_size"]
        )

        with Path(entry["output_file"]).open(encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        assert len([r for r in rows if r["language"] == "python"]) == strata["python"][
            "sample_size"
        ]
        assert len([r for r in rows if r["language"] == "java"]) == strata["java"][
            "sample_size"
        ]

    def test_commit_step_stratifies_by_language_and_agent_type(self, tmp_path):
        csv_path = tmp_path / "python_agent_commit.csv"
        rows = [_commit_row(i, "python", "claude") for i in range(150)] + [
            _commit_row(i, "python", "copilot") for i in range(50)
        ]
        _write_csv(csv_path, rows)

        metadata = run_validation_sampling(
            "agent-commits-dataset-a",
            [csv_path],
            output_root=tmp_path / "validation-samples",
        )

        entry = metadata["outputs"][0]
        assert entry["population_size"] == 200
        strata_sizes = {
            (s["key"]["language"], s["key"]["agent_type"]): s["population_size"]
            for s in entry["strata"]
        }
        assert strata_sizes == {("python", "claude"): 150, ("python", "copilot"): 50}

    def test_deterministic_across_two_runs_same_seed(self, tmp_path):
        csv_path = tmp_path / "python_agent_commit.csv"
        _write_csv(csv_path, [_commit_row(i, "python", "claude") for i in range(200)])
        root_a = tmp_path / "run_a"
        root_b = tmp_path / "run_b"

        meta_a = run_validation_sampling(
            "agent-commits-dataset-a", [csv_path], seed=99, output_root=root_a
        )
        meta_b = run_validation_sampling(
            "agent-commits-dataset-a", [csv_path], seed=99, output_root=root_b
        )

        def read_rows(meta):
            path = Path(meta["outputs"][0]["output_file"])
            with path.open(encoding="utf-8") as fh:
                return list(csv.DictReader(fh))

        assert read_rows(meta_a) == read_rows(meta_b)

    def test_normalizes_despite_differing_source_columns(self, tmp_path):
        """Real per-language QC CSVs can have slightly different columns
        (e.g. matched_config_file only present on newer collector output)."""
        base_csv = tmp_path / "python_agent_repo.csv"
        extra_csv = tmp_path / "java_agent_repo.csv"
        _write_csv(base_csv, [_repo_row(i, "python") for i in range(5)])
        _write_csv(
            extra_csv,
            [
                {**_repo_row(i, "java"), "matched_config_file": "CLAUDE.md"}
                for i in range(5)
            ],
        )

        metadata = run_validation_sampling(
            "agent-repos",
            [base_csv, extra_csv],
            output_root=tmp_path / "validation-samples",
        )

        out_path = Path(metadata["outputs"][0]["output_file"])
        with out_path.open(encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            assert reader.fieldnames == CANONICAL_FIELDNAMES
            rows = list(reader)
        assert len(rows) == 10  # N=10 is below the Cochran floor, all included
        assert any(r["detection_signal"] == "CLAUDE.md" for r in rows)
        assert any(r["detection_signal"] == "agent_config_present" for r in rows)

    def test_empty_input_file_produces_empty_sample(self, tmp_path):
        empty_csv = tmp_path / "python_agent_repo.csv"
        empty_csv.write_text("repo_name,language,has_agent_config\n", encoding="utf-8")

        metadata = run_validation_sampling(
            "agent-repos", [empty_csv], output_root=tmp_path / "validation-samples"
        )

        entry = metadata["outputs"][0]
        assert entry["population_size"] == 0
        assert entry["sample_size"] == 0
        with Path(entry["output_file"]).open(encoding="utf-8") as fh:
            assert list(csv.DictReader(fh)) == []


class TestRunValidationSamplingPerFileMode:
    def _fixture_row(self, i: int, language: str) -> dict:
        return {
            "repo_name": "owner/repo",
            "language": language,
            "commit_sha": f"sha{i}",
            "file_path": f"tests/test_{i}.py",
            "fixture_name": f"fixture{i}",
            "fixture_type": "pytest_decorator",
            "start_line": str(i),
            "github_url": f"https://github.com/owner/repo/blob/sha{i}/tests/test_{i}.py#L{i}",
            "raw_source": f"@pytest.fixture\ndef fixture{i}(): ...",
        }

    def test_one_output_per_input_file(self, tmp_path):
        python_csv = tmp_path / "python_agent_fixtures.csv"
        java_csv = tmp_path / "java_agent_fixtures.csv"
        _write_csv(python_csv, [self._fixture_row(i, "python") for i in range(500)])
        _write_csv(java_csv, [self._fixture_row(i, "java") for i in range(50)])
        output_root = tmp_path / "validation-samples"

        metadata = run_validation_sampling(
            step="agent-fixtures-dataset-a",
            input_paths=[python_csv, java_csv],
            output_root=output_root,
        )

        assert metadata["population_mode"] == "per_file"
        assert len(metadata["outputs"]) == 2

        by_source = {e["source_files"][0]: e for e in metadata["outputs"]}
        assert by_source[str(python_csv)]["population_size"] == 500
        assert by_source[str(python_csv)]["sample_size"] == cochran_sample_size(500)
        assert by_source[str(java_csv)]["population_size"] == 50
        assert by_source[str(java_csv)]["sample_size"] == cochran_sample_size(50)
        assert "strata" not in by_source[str(python_csv)]

        out_dir = output_root / "agent-fixtures-dataset-a"
        csv_files = list(out_dir.glob("*.csv"))
        assert len(csv_files) == 2

        with csv_files[0].open(encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            assert reader.fieldnames == CANONICAL_FIELDNAMES
            row = next(reader)
            assert row["validation_type"] == "fixture"
            assert row["evidence"]  # raw_source round-tripped, non-empty


def _human_test_commit_row(i: int, language: str, test_file_count: int = 1) -> dict:
    return {
        "repo_name": "owner/repo",
        "language": language,
        "commit_sha": f"sha{i}",
        "commit_role": "human",
        "agent_type": "",
        "commit_date": "2026-05-21T00:00:00Z",
        "test_file_count": str(test_file_count),
        "test_file_paths": json.dumps([f"tests/test_{i}.py"]),
    }


class TestRunValidationSamplingDatasetBSteps:
    """`human-commits-dataset-b` (classification/contamination check),
    `human-test-commits-dataset-b` (file-path match check), and
    `human-fixtures-dataset-b` (fixture extraction check) close the
    Dataset-B-side gap in the reduced validation set: Dataset A's own
    samples only validate the claimed-agent side of the same detectors."""

    def test_human_commits_step_stratifies_by_language(self, tmp_path):
        python_csv = tmp_path / "python_human_test_commit.csv"
        java_csv = tmp_path / "java_human_test_commit.csv"
        _write_csv(python_csv, [_human_test_commit_row(i, "python") for i in range(300)])
        _write_csv(java_csv, [_human_test_commit_row(i, "java") for i in range(300)])

        metadata = run_validation_sampling(
            "human-commits-dataset-b",
            [python_csv, java_csv],
            output_root=tmp_path / "validation-samples",
        )

        entry = metadata["outputs"][0]
        assert entry["population_size"] == 600
        strata = {s["key"]["language"]: s for s in entry["strata"]}
        assert set(strata) == {"python", "java"}

        with Path(entry["output_file"]).open(encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            assert reader.fieldnames == CANONICAL_FIELDNAMES
            rows = list(reader)
        assert all(r["validation_type"] == "human_commit" for r in rows)
        assert all(r["detection_signal"] == "classified_as_human" for r in rows)

    def test_human_test_commits_step_evidence_is_test_file_paths(self, tmp_path):
        csv_path = tmp_path / "python_human_test_commit.csv"
        _write_csv(csv_path, [_human_test_commit_row(i, "python") for i in range(20)])

        metadata = run_validation_sampling(
            "human-test-commits-dataset-b",
            [csv_path],
            output_root=tmp_path / "validation-samples",
        )

        entry = metadata["outputs"][0]
        with Path(entry["output_file"]).open(encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        assert all(r["validation_type"] == "human_test_commit" for r in rows)
        assert all(r["evidence"].startswith("[") for r in rows)

    def test_human_fixtures_step_one_output_per_language_file(self, tmp_path):
        fixture_row = TestRunValidationSamplingPerFileMode()._fixture_row
        python_csv = tmp_path / "python_fixtures.csv"
        java_csv = tmp_path / "java_fixtures.csv"
        _write_csv(python_csv, [fixture_row(i, "python") for i in range(500)])
        _write_csv(java_csv, [fixture_row(i, "java") for i in range(50)])
        output_root = tmp_path / "validation-samples"

        metadata = run_validation_sampling(
            step="human-fixtures-dataset-b",
            input_paths=[python_csv, java_csv],
            output_root=output_root,
        )

        assert metadata["population_mode"] == "per_file"
        assert len(metadata["outputs"]) == 2
        out_dir = output_root / "human-fixtures-dataset-b"
        assert len(list(out_dir.glob("*.csv"))) == 2

    def test_human_commits_real_schema_normalizes(self, tmp_path, make_csv):
        rows = [
            {
                "repo_name": "owner/repo",
                "language": "python",
                "commit_sha": f"sha{i}",
                "commit_role": "human",
                "agent_type": "",
                "commit_date": "2026-05-21T00:00:00Z",
                "test_file_count": "1",
                "test_file_paths": json.dumps([f"tests/test_{i}.py"]),
            }
            for i in range(30)
        ]
        csv_path = make_csv(tmp_path, "python_human_test_commit.csv", rows=rows)

        metadata = run_validation_sampling(
            "human-commits-dataset-b",
            [csv_path],
            output_root=tmp_path / "validation-samples",
        )

        entry = metadata["outputs"][0]
        with Path(entry["output_file"]).open(encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            assert reader.fieldnames == CANONICAL_FIELDNAMES
            sampled = list(reader)
        assert len(sampled) == entry["sample_size"]
        assert all(r["item_url"].startswith("https://github.com/owner/repo/commit/") for r in sampled)


class TestRealPipelineCSVSchemas:
    """Round-trip checks against the real column layouts the pipeline
    actually produces (via tests/conftest.py's make_csv fixture) -- proves
    the normalizer maps real headers/values into the fixed schema, not just
    the small synthetic dicts used above.
    """

    def test_agent_repos_real_schema_normalizes(self, tmp_path, make_csv):
        rows = [
            {
                "repo_name": f"owner{i}/repo_python",
                "full_name": f"owner{i}/repo_python",
                "language": "python",
                "stars": str(500 + i),
                "forks": str(10 + i),
                "num_contributors": str(1 + i % 5),
                "clone_url": f"https://github.com/owner{i}/repo_python.git",
                "has_agent_config": "1",
                "matched_config_file": "CLAUDE.md",
            }
            for i in range(30)
        ]
        csv_path = make_csv(tmp_path, "python_agent_repo.csv", rows=rows)

        metadata = run_validation_sampling(
            "agent-repos", [csv_path], output_root=tmp_path / "validation-samples"
        )

        entry = metadata["outputs"][0]
        assert entry["population_size"] == 30
        with Path(entry["output_file"]).open(encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            assert reader.fieldnames == CANONICAL_FIELDNAMES
            sampled = list(reader)
        assert len(sampled) == entry["sample_size"]
        assert all(r["detection_signal"] == "CLAUDE.md" for r in sampled)
        assert all(r["item_url"].startswith("https://github.com/owner") for r in sampled)

    def test_agent_commits_dataset_a_real_schema_normalizes(self, tmp_path, make_csv):
        rows = [
            {
                "repo_name": "good/repo",
                "commit_sha": f"sha{i}",
                "commit_url": f"https://github.com/good/repo/commit/sha{i}",
                "agent_type": "claude" if i % 2 == 0 else "copilot",
                "commit_date": "2026-05-21T00:00:00Z",
                "author_name": "Some Bot",
                "author_email": "bot@example.com",
                "language": "python",
                "clone_url": "https://github.com/good/repo.git",
                "processed_at": "2026-05-21T00:00:00Z",
            }
            for i in range(30)
        ]
        csv_path = make_csv(tmp_path, "python_agent_commit.csv", rows=rows)

        metadata = run_validation_sampling(
            "agent-commits-dataset-a",
            [csv_path],
            output_root=tmp_path / "validation-samples",
        )

        entry = metadata["outputs"][0]
        with Path(entry["output_file"]).open(encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            assert reader.fieldnames == CANONICAL_FIELDNAMES
            sampled = list(reader)
        assert len(sampled) == entry["sample_size"]
        assert all(r["detection_signal"] in {"claude", "copilot"} for r in sampled)
        assert all("agent_type=" in r["evidence"] for r in sampled)


def test_unknown_step_raises():
    with pytest.raises(ValueError):
        run_validation_sampling("not-a-real-step", [Path("x.csv")])


@pytest.mark.parametrize(
    "excluded_step",
    [
        "human-fixtures-dataset-c",
        "agent-test-commits-dataset-a",
    ],
)
def test_deliberately_excluded_steps_are_not_selectable(tmp_path, excluded_step):
    """Reduced validation set: these are redundant with an already-validated
    step (same file-matching or AST-detection logic, different corpus) and
    must not be reintroduced as selectable --step values.
    """
    with pytest.raises(ValueError):
        run_validation_sampling(
            excluded_step, [Path("x.csv")], output_root=tmp_path / "validation-samples"
        )


def test_no_input_paths_raises(tmp_path):
    with pytest.raises(ValueError):
        run_validation_sampling(
            "agent-repos", [], output_root=tmp_path / "validation-samples"
        )


def test_readme_written_with_label_vocabulary(tmp_path):
    csv_path = tmp_path / "python_agent_repo.csv"
    _write_csv(csv_path, [_repo_row(i, "python") for i in range(5)])
    output_root = tmp_path / "validation-samples"

    run_validation_sampling("agent-repos", [csv_path], output_root=output_root)

    readme = (output_root / "README.md").read_text(encoding="utf-8")
    assert "TP" in readme
    assert "FP" in readme
    assert "Unsure" in readme
    assert "404" in readme


class TestCLI:
    def test_main_invokes_run_validation_sampling(self, monkeypatch, tmp_path):
        csv_path = tmp_path / "python_agent_fixtures.csv"
        _write_csv(
            csv_path,
            [
                {
                    "repo_name": "owner/repo",
                    "language": "python",
                    "commit_sha": f"sha{i}",
                    "file_path": f"tests/test_{i}.py",
                    "fixture_name": f"fixture{i}",
                    "fixture_type": "pytest_decorator",
                    "start_line": str(i),
                    "github_url": f"https://github.com/owner/repo/blob/sha{i}#L{i}",
                    "raw_source": "@pytest.fixture\ndef f(): ...",
                }
                for i in range(20)
            ],
        )
        output_root = tmp_path / "validation-samples"

        captured = {}
        original = vs.run_validation_sampling

        def spy(*args, **kwargs):
            result = original(*args, **kwargs)
            captured["kwargs"] = kwargs
            return result

        monkeypatch.setattr(vs, "run_validation_sampling", spy)

        argv = [
            "--step",
            "agent-fixtures-dataset-a",
            "--input",
            str(csv_path),
            "--output-root",
            str(output_root),
            "--seed",
            "5",
        ]
        rc = vs.main(argv)

        assert rc == 0
        assert captured["kwargs"]["step"] == "agent-fixtures-dataset-a"
        assert captured["kwargs"]["seed"] == 5
        assert (output_root / "agent-fixtures-dataset-a").exists()
