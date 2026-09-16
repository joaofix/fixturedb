"""Tests for collection/detection_validation_report.py.

compute_precision() is tested directly against small in-memory row lists
(no CSV/filesystem needed for the math itself); generate_report()/
write_report() are tested against tiny synthetic CSVs under tmp_path, in
the exact two-file layout collection.detection_validation_sampling
produces (mock-detection/mock_detection_sample.csv,
pytest-lifecycle/pytest_lifecycle_sample.csv).
"""

from __future__ import annotations

import csv
import dataclasses

import pytest

from collection.detection_validation_report import (
    COMPONENTS,
    PrecisionResult,
    compute_precision,
    generate_report,
    render_paper_text,
    render_table,
    write_report,
)


def _rows(*labels: str) -> list[dict]:
    return [{"id": f"row-{i}", "rater_label": label} for i, label in enumerate(labels)]


class TestComputePrecision:
    def test_basic_counts_and_precision(self):
        result = compute_precision("Mock detection", "mock detection", _rows("TP", "TP", "TP", "FP"))
        assert result.total_sampled == 4
        assert result.count_404 == 0
        assert result.count_unrated == 0
        assert result.effective_n == 4
        assert result.count_tp == 3
        assert result.count_fp == 1
        assert result.count_unsure == 0
        assert result.precision == pytest.approx(75.0)

    def test_unsure_excluded_from_precision_denominator_entirely(self):
        """3 TP, 1 FP, 2 Unsure -- precision must be 3/4 = 75%, not
        3/6 (folded as non-TP) or (3+2)/6 (folded as TP), matching the
        "excluded, not folded in either direction" requirement."""
        result = compute_precision(
            "Mock detection", "mock detection", _rows("TP", "TP", "TP", "FP", "Unsure", "Unsure")
        )
        assert result.effective_n == 6
        assert result.precision == pytest.approx(75.0)
        assert result.unsure_rate == pytest.approx(100 * 2 / 6)

    def test_404_excluded_from_effective_n_and_never_counted_as_fp(self):
        result = compute_precision("Mock detection", "mock detection", _rows("TP", "FP", "404", "404"))
        assert result.total_sampled == 4
        assert result.count_404 == 2
        assert result.effective_n == 2
        assert result.count_tp == 1
        assert result.count_fp == 1
        assert result.precision == pytest.approx(50.0)

    def test_unrated_rows_excluded_from_every_count(self):
        result = compute_precision("Mock detection", "mock detection", _rows("TP", "TP", "", "  "))
        assert result.total_sampled == 4  # original size, unaffected
        assert result.count_unrated == 2
        assert result.effective_n == 2
        assert result.count_tp == 2
        assert result.precision == pytest.approx(100.0)

    def test_sanity_check_tp_fp_unsure_sum_to_effective_n(self):
        result = compute_precision(
            "Mock detection", "mock detection", _rows("TP", "FP", "Unsure", "404", "")
        )
        assert result.count_tp + result.count_fp + result.count_unsure == result.effective_n

    def test_invalid_label_raises_not_silently_ignored(self):
        with pytest.raises(ValueError, match="invalid rater_label"):
            compute_precision("Mock detection", "mock detection", _rows("TP", "Maybe"))

    def test_precision_is_none_when_no_tp_or_fp_at_all(self):
        result = compute_precision("Mock detection", "mock detection", _rows("Unsure", "Unsure"))
        assert result.precision is None

    def test_unsure_rate_is_none_when_effective_n_is_zero(self):
        result = compute_precision("Mock detection", "mock detection", _rows("404"))
        assert result.effective_n == 0
        assert result.unsure_rate is None


class TestRenderTable:
    def test_renders_expected_columns_and_values(self):
        result = compute_precision("Mock detection", "mock detection", _rows("TP", "TP", "TP", "FP"))
        table = render_table([result])
        assert (
            "| Component | n sampled | 404 excluded | Effective n | TP | FP | Unsure | "
            "Precision | Unsure rate |" in table
        )
        assert "| Mock detection | 4 | 0 | 4 | 3 | 1 | 0 | 75.0% | 0.0% |" in table

    def test_dashes_when_precision_not_computable(self):
        result = compute_precision("Mock detection", "mock detection", _rows("Unsure"))
        table = render_table([result])
        assert "| Mock detection | 1 | 0 | 1 | 0 | 0 | 1 | -- | 100.0% |" in table


class TestRenderPaperText:
    def test_matches_exact_requested_phrasing(self):
        mock_result = compute_precision(
            "Mock detection", "mock detection", _rows("TP", "TP", "TP", "FP")
        )
        lifecycle_result = compute_precision(
            "Pytest lifecycle heuristic",
            "the pytest lifecycle heuristic",
            _rows("TP", "TP", "Unsure"),
        )
        text = render_paper_text([mock_result, lifecycle_result])
        assert "mock detection (75.0%, 0 items unsure)" in text
        assert "the pytest lifecycle heuristic (100.0%, 1 items unsure)" in text


class TestGenerateReportAndWriteReport:
    def _write_csv(self, tmp_path, subdir, filename, prefix, labels):
        directory = tmp_path / subdir
        directory.mkdir(parents=True)
        with (directory / filename).open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=["id", "rater_label"])
            writer.writeheader()
            for i, label in enumerate(labels):
                writer.writerow({"id": f"{prefix}{i}", "rater_label": label})

    def _make_sample_csvs(self, tmp_path, mock_labels, lifecycle_labels, unittest_labels=("TP",)):
        self._write_csv(tmp_path, "mock-detection", "mock_detection_sample.csv", "m", mock_labels)
        self._write_csv(
            tmp_path, "pytest-lifecycle", "pytest_lifecycle_sample.csv", "p", lifecycle_labels
        )
        self._write_csv(
            tmp_path, "unittest-heuristic", "unittest_heuristic_sample.csv", "u", unittest_labels
        )

    def test_components_is_exactly_three_no_mock_type(self):
        """mock-type was dropped entirely -- exactly 3 components, and
        neither the sampling module's mock-type step name nor its
        filename appear anywhere in this module's config."""
        assert len(COMPONENTS) == 3
        labels = {c[0] for c in COMPONENTS}
        assert labels == {
            "Mock detection",
            "Pytest lifecycle heuristic",
            "Unittest name-based lifecycle heuristic",
        }
        for _, _, relative_path in COMPONENTS:
            assert "mock-type" not in relative_path
            assert "mock_type" not in relative_path

    def test_generate_report_never_mentions_mock_type_or_conservative(self, tmp_path):
        self._make_sample_csvs(tmp_path, ["TP", "TP", "TP", "FP"], ["TP", "TP", "Unsure"])
        report = generate_report(tmp_path)
        assert "mock-type" not in report.lower()
        assert "conservative" not in report.lower()
        assert "mock detection (75.0%, 0 items unsure)" in report
        assert "the pytest lifecycle heuristic (100.0%, 1 items unsure)" in report

    def test_write_report_persists_file(self, tmp_path):
        self._make_sample_csvs(tmp_path, ["TP", "FP"], ["TP"])
        output_path = write_report(samples_root=tmp_path)
        assert output_path == tmp_path / "precision_report.md"
        assert output_path.read_text(encoding="utf-8") == generate_report(tmp_path)

    def test_unrated_rows_reported_in_a_note(self, tmp_path):
        self._make_sample_csvs(tmp_path, ["TP", "TP", ""], ["TP"])
        report = generate_report(tmp_path)
        assert "not yet rated" in report
        assert "Mock detection: 1 row(s) not yet rated" in report

    def test_no_unrated_note_when_everything_is_rated(self, tmp_path):
        self._make_sample_csvs(tmp_path, ["TP", "FP"], ["TP"])
        report = generate_report(tmp_path)
        assert "not yet rated" not in report


def test_precision_result_is_frozen_dataclass_instance():
    result = compute_precision("X", "x", _rows("TP"))
    assert isinstance(result, PrecisionResult)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.count_tp = 99  # frozen -- must not be mutable after computation
