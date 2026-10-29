"""Tests for collection/detector_precision_report.py.

compute_precision() is tested directly against small in-memory row lists
(no CSV/filesystem needed for the math itself); generate_report()/
write_report() are tested against tiny synthetic CSVs under tmp_path, in
the exact four-file layout collection.detector_precision_sampling produces
(mock-detection/, pytest-lifecycle/, unittest-heuristic/, before-after/).
"""

from __future__ import annotations

import csv
import dataclasses

import pytest

from collection.detector_precision_report import (
    COMPONENTS,
    PrecisionResult,
    compute_precision,
    generate_report,
    render_paper_text,
    render_table,
    write_report,
)
from collection.detector_precision_sampling import CASE_OUTPUT_PATHS


def _rows(*labels: str) -> list[dict]:
    return [{"github_url": f"https://example/{i}", "label": label} for i, label in enumerate(labels)]


class TestComputePrecision:
    def test_basic_counts_and_precision(self):
        result = compute_precision("mock_detection", "mock detection", _rows("true_positive", "true_positive", "true_positive", "false_positive"))
        assert result.total_sampled == 4
        assert result.count_true_positive == 3
        assert result.count_false_positive == 1
        assert result.count_unsure == 0
        assert result.clearly_labeled == 4
        assert result.precision == pytest.approx(75.0)

    def test_unsure_excluded_from_precision_denominator_entirely(self):
        """3 TP, 1 FP, 2 unsure -- precision must be 3/4 = 75%, not 3/6."""
        result = compute_precision(
            "mock_detection",
            "mock detection",
            _rows("true_positive", "true_positive", "true_positive", "false_positive", "unsure", "unsure"),
        )
        assert result.total_labeled == 6
        assert result.precision == pytest.approx(75.0)
        assert result.unsure_rate == pytest.approx(100 * 2 / 6)

    def test_no_404_category_exists(self):
        with pytest.raises(ValueError, match="invalid label"):
            compute_precision("mock_detection", "mock detection", _rows("true_positive", "404"))

    def test_empty_label_raises_immediately_no_soft_skip(self):
        with pytest.raises(ValueError, match="no label yet"):
            compute_precision("mock_detection", "mock detection", _rows("true_positive", ""))

    def test_whitespace_only_label_also_raises(self):
        with pytest.raises(ValueError, match="no label yet"):
            compute_precision("mock_detection", "mock detection", _rows("true_positive", "   "))

    def test_invalid_label_raises_not_silently_ignored(self):
        with pytest.raises(ValueError, match="invalid label"):
            compute_precision("mock_detection", "mock detection", _rows("true_positive", "maybe"))

    def test_precision_is_none_when_no_tp_or_fp_at_all(self):
        result = compute_precision("mock_detection", "mock detection", _rows("unsure", "unsure"))
        assert result.precision is None
        assert result.clearly_labeled == 0

    def test_unsure_rate_is_none_when_total_labeled_is_zero(self):
        result = compute_precision("mock_detection", "mock detection", [])
        assert result.total_labeled == 0
        assert result.unsure_rate is None

    def test_rule_of_three_upper_bound_when_zero_false_positives(self):
        result = compute_precision(
            "pytest_scope", "pytest scope classification", _rows(*(["true_positive"] * 97 + ["unsure"] * 3))
        )
        assert result.count_false_positive == 0
        assert result.clearly_labeled == 97
        assert result.rule_of_three_upper_bound == pytest.approx(100 * 3 / 97)

    def test_rule_of_three_is_none_when_any_false_positive_exists(self):
        result = compute_precision(
            "mock_detection", "mock detection", _rows("true_positive", "false_positive")
        )
        assert result.rule_of_three_upper_bound is None

    def test_rule_of_three_is_none_when_clearly_labeled_is_zero(self):
        result = compute_precision("mock_detection", "mock detection", _rows("unsure"))
        assert result.count_false_positive == 0
        assert result.rule_of_three_upper_bound is None


class TestRenderTable:
    def test_renders_expected_columns_and_values(self):
        result = compute_precision(
            "mock_detection", "mock detection", _rows("true_positive", "true_positive", "true_positive", "false_positive")
        )
        table = render_table([result])
        assert (
            "| Case | n sampled | TP | FP | Unsure | Precision | Unsure rate | "
            "Rule-of-three upper bound (95%) |" in table
        )
        assert "| mock detection | 4 | 3 | 1 | 0 | 75.0% | 0.0% | -- |" in table

    def test_shows_upper_bound_when_zero_fp(self):
        result = compute_precision(
            "pytest_scope", "pytest scope classification", _rows(*(["true_positive"] * 100))
        )
        table = render_table([result])
        assert "3.0%" in table  # 3/100


class TestRenderPaperText:
    def test_matches_exact_requested_phrasing(self):
        mock_result = compute_precision(
            "mock_detection", "mock detection", _rows("true_positive", "true_positive", "true_positive", "false_positive")
        )
        text = render_paper_text([mock_result])
        assert "mock detection (75.0%, 0 items unsure)" in text

    def test_includes_rule_of_three_text_when_zero_fp(self):
        result = compute_precision(
            "unittest_detection", "unittest detection", _rows(*(["true_positive"] * 100))
        )
        text = render_paper_text([result])
        assert "rule of three" in text
        assert "<= 3.0%" in text


class TestGenerateReportAndWriteReport:
    def _write_csv(self, tmp_path, case, labels):
        folder, filename = CASE_OUTPUT_PATHS[case]
        directory = tmp_path / folder
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / filename).open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=["github_url", "label"])
            writer.writeheader()
            for i, label in enumerate(labels):
                writer.writerow({"github_url": f"https://example/{case}/{i}", "label": label})

    def _make_all_four(
        self,
        tmp_path,
        mock=("true_positive", "true_positive", "true_positive", "false_positive"),
        pytest_scope=("true_positive", "true_positive", "unsure"),
        unittest=("true_positive",),
        before_after=("true_positive",),
    ):
        self._write_csv(tmp_path, "mock_detection", mock)
        self._write_csv(tmp_path, "pytest_scope", pytest_scope)
        self._write_csv(tmp_path, "unittest_detection", unittest)
        self._write_csv(tmp_path, "before_after", before_after)

    def test_components_is_exactly_four(self):
        assert len(COMPONENTS) == 4
        cases = {c[0] for c in COMPONENTS}
        assert cases == {"mock_detection", "pytest_scope", "unittest_detection", "before_after"}

    def test_generate_report_covers_all_four_cases(self, tmp_path):
        self._make_all_four(tmp_path)
        report = generate_report(tmp_path)
        assert "mock detection (75.0%, 0 items unsure)" in report
        assert "pytest scope classification" in report
        assert "unittest detection" in report
        assert "bare before/after" in report

    def test_write_report_persists_file(self, tmp_path):
        self._make_all_four(tmp_path)
        output_path = write_report(samples_root=tmp_path)
        assert output_path == tmp_path / "precision_report.md"
        assert output_path.read_text(encoding="utf-8") == generate_report(tmp_path)

    def test_fails_loudly_on_any_unlabeled_row(self, tmp_path):
        self._make_all_four(tmp_path, mock=("true_positive", ""))
        with pytest.raises(ValueError, match="no label yet"):
            generate_report(tmp_path)

    def test_no_soft_skip_note_exists_anywhere(self, tmp_path):
        """v1's 'not yet rated' soft-skip behavior must not exist here --
        confirmed by the fact that an unlabeled row raises instead of
        producing a report at all (see test_fails_loudly_on_any_unlabeled_row)."""
        self._make_all_four(tmp_path)
        report = generate_report(tmp_path)
        assert "not yet rated" not in report


def test_precision_result_is_frozen_dataclass_instance():
    result = compute_precision("mock_detection", "mock detection", _rows("true_positive"))
    assert isinstance(result, PrecisionResult)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.count_true_positive = 99  # frozen -- must not be mutable after computation
