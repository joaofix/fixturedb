"""Tests for collection/research_questions/language_contamination.py.

Writes small synthetic datasets/{dataset}/fixtures/*.csv files under
tmp_path (never touching the real datasets/ directory) and checks the
per-CSV mismatch counting, missing-directory handling, and report
rendering.
"""

from __future__ import annotations

import csv
from pathlib import Path

from collection import paths
from collection.research_questions.language_contamination import (
    check_dataset,
    generate_report,
    write_report,
)


def _write_fixtures_csv(root: Path, dataset: str, filename: str, languages: list[str]) -> None:
    path = paths.stage_dir(dataset, "fixtures", root=root) / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["repo_name", "language", "fixture_name"])
        writer.writeheader()
        for i, lang in enumerate(languages):
            writer.writerow({"repo_name": "o/r", "language": lang, "fixture_name": f"f{i}"})


class TestCheckDataset:
    def test_missing_fixtures_dir_returns_none(self, tmp_path):
        assert check_dataset("a", datasets_root=tmp_path) is None

    def test_empty_fixtures_dir_returns_none(self, tmp_path):
        paths.stage_dir("a", "fixtures", root=tmp_path).mkdir(parents=True)
        assert check_dataset("a", datasets_root=tmp_path) is None

    def test_clean_csv_has_zero_mismatches(self, tmp_path):
        _write_fixtures_csv(tmp_path, "a", "python_fixtures.csv", ["python", "python", "python"])
        results = check_dataset("a", datasets_root=tmp_path)
        assert len(results) == 1
        r = results[0]
        assert r.nominal_language == "python"
        assert r.total == 3
        assert r.mismatched == 0
        assert r.pct == 0.0

    def test_contaminated_csv_counts_and_breaks_down_by_language(self, tmp_path):
        _write_fixtures_csv(
            tmp_path, "a", "python_fixtures.csv", ["python", "java", "python", "javascript", "java"]
        )
        results = check_dataset("a", datasets_root=tmp_path)
        r = results[0]
        assert r.total == 5
        assert r.mismatched == 3
        assert r.pct == 60.0
        assert r.mismatched_by_language == {"java": 2, "javascript": 1}

    def test_case_and_whitespace_insensitive_comparison(self, tmp_path):
        _write_fixtures_csv(tmp_path, "a", "python_fixtures.csv", [" Python ", "PYTHON", "python"])
        r = check_dataset("a", datasets_root=tmp_path)[0]
        assert r.mismatched == 0

    def test_multiple_csvs_checked_independently(self, tmp_path):
        _write_fixtures_csv(tmp_path, "a", "python_fixtures.csv", ["python", "java"])
        _write_fixtures_csv(tmp_path, "a", "java_fixtures.csv", ["java", "java"])
        results = check_dataset("a", datasets_root=tmp_path)
        by_name = {r.csv_name: r for r in results}
        assert by_name["python_fixtures.csv"].mismatched == 1
        assert by_name["java_fixtures.csv"].mismatched == 0


class TestGenerateReport:
    def test_missing_all_datasets_notes_unavailable(self, tmp_path):
        report = generate_report(datasets_root=tmp_path)
        assert report.count("Not available -- no fixtures/*.csv files collected yet.") == 3

    def test_reports_totals_and_breakdown(self, tmp_path):
        _write_fixtures_csv(tmp_path, "a", "python_fixtures.csv", ["python", "java"])
        report = generate_report(datasets_root=tmp_path)
        assert "1/2 fixtures mismatched (50.00%)" in report
        assert "java=1" in report


class TestWriteReport:
    def test_writes_file_matching_generate_report(self, tmp_path):
        _write_fixtures_csv(tmp_path, "a", "python_fixtures.csv", ["python"])
        out_dir = tmp_path / "out"
        path = write_report(out_dir, datasets_root=tmp_path)
        assert path == out_dir / "language_contamination.md"
        assert path.read_text() == generate_report(datasets_root=tmp_path)
