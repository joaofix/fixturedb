from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

import collection.validation_sampling as vs
from collection.validation_sampling import (
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


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


class TestRunValidationSamplingCombinedMode:
    def test_combines_multiple_files_into_one_sample(self, tmp_path):
        python_csv = tmp_path / "python_agent_repo.csv"
        java_csv = tmp_path / "java_agent_repo.csv"
        _write_csv(
            python_csv,
            [{"repo_name": f"py/repo{i}", "language": "python"} for i in range(300)],
        )
        _write_csv(
            java_csv,
            [{"repo_name": f"java/repo{i}", "language": "java"} for i in range(300)],
        )
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
            rows = list(csv.DictReader(fh))
        assert len(rows) == expected_n

        metadata_files = list((output_root / "agent-repos").glob("sample_metadata_*.json"))
        assert len(metadata_files) == 1
        with metadata_files[0].open(encoding="utf-8") as fh:
            assert json.load(fh) == metadata

    def test_deterministic_across_two_runs_same_seed(self, tmp_path):
        csv_path = tmp_path / "agent_commits.csv"
        _write_csv(csv_path, [{"commit_sha": f"sha{i}"} for i in range(200)])
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


class TestRunValidationSamplingPerFileMode:
    def test_one_output_per_input_file(self, tmp_path):
        python_csv = tmp_path / "python_agent_fixtures.csv"
        java_csv = tmp_path / "java_agent_fixtures.csv"
        _write_csv(python_csv, [{"name": f"fixture{i}"} for i in range(500)])
        _write_csv(java_csv, [{"name": f"fixture{i}"} for i in range(50)])
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

        out_dir = output_root / "agent-fixtures-dataset-a"
        csv_files = list(out_dir.glob("*.csv"))
        assert len(csv_files) == 2


def test_unknown_step_raises():
    with pytest.raises(ValueError):
        run_validation_sampling("not-a-real-step", [Path("x.csv")])


def test_no_input_paths_raises(tmp_path):
    with pytest.raises(ValueError):
        run_validation_sampling(
            "agent-repos", [], output_root=tmp_path / "validation-samples"
        )


class TestCLI:
    def test_main_invokes_run_validation_sampling(self, monkeypatch, tmp_path):
        csv_path = tmp_path / "python_agent_fixtures.csv"
        _write_csv(csv_path, [{"name": f"fixture{i}"} for i in range(20)])
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
