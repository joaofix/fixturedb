"""Tests for collection/research_questions/rq1.py.

Builds synthetic db/rq1_prevalence.db files under tmp_path by reusing
rq1_prevalence_scan.py's own initialise_rq1_db()/persist_result()/
_result_row() -- the real production code that writes this db, not a
reimplementation -- so these tests exercise the exact schema/shape the
real scan produces.
"""

from __future__ import annotations

from collection.config import MIN_TEST_FILES
from collection.research_questions.rq1 import (
    DISPLAY_LANGUAGES,
    LanguagePrevalence,
    compute_prevalence,
    generate_report,
    load_rows,
    render_median_prose,
    render_raw_numbers,
    render_table1,
    render_table2,
    write_report,
)
from collection.rq1_prevalence_scan import _result_row, initialise_rq1_db, persist_result


def _make_db(db_root, rows):
    """rows: list of dicts with repo_name, language, clone_ok, and
    optionally num_test_files/num_fixtures/num_setup/num_teardown/
    error_reason -- defaults match _result_row()'s own zero-filled shape."""
    db_root.mkdir(parents=True, exist_ok=True)
    db_path = db_root / "rq1_prevalence.db"
    initialise_rq1_db(db_path)
    for i, row in enumerate(rows):
        counts = {
            "num_test_files": row.get("num_test_files", 0),
            "num_fixtures": row.get("num_fixtures", 0),
            "num_setup": row.get("num_setup", 0),
            "num_teardown": row.get("num_teardown", 0),
        }
        persist_result(
            _result_row(
                row.get("repo_name", f"org/repo{i}"),
                row["language"],
                f"2026-10-02T00:00:{i:02d}+00:00",
                clone_ok=row["clone_ok"],
                error_reason=row.get("error_reason"),
                counts=counts,
            ),
            db_path,
        )
    return db_path


class TestLoadRows:
    def test_missing_db_returns_none(self, tmp_path):
        assert load_rows(tmp_path) is None

    def test_excludes_clone_ok_zero_rows(self, tmp_path):
        _make_db(
            tmp_path,
            [
                {"language": "python", "clone_ok": True, "num_test_files": 1},
                {"language": "python", "clone_ok": False, "error_reason": "clone_failed"},
            ],
        )
        rows = load_rows(tmp_path)
        assert len(rows) == 1
        assert rows[0]["num_test_files"] == 1


class TestComputePrevalence:
    def _rows(self, db_root, specs):
        _make_db(db_root, specs)
        return load_rows(db_root)

    def test_counts_with_tests_fixtures_setup_teardown(self, tmp_path):
        rows = self._rows(
            tmp_path,
            [
                {"language": "python", "clone_ok": True, "num_test_files": 3, "num_fixtures": 2, "num_setup": 1, "num_teardown": 1},
                {"language": "python", "clone_ok": True, "num_test_files": 1, "num_fixtures": 0},
                {"language": "python", "clone_ok": True, "num_test_files": 0},
            ],
        )
        result = compute_prevalence(rows)
        py = result["python"]
        assert py.n_with_tests == 2  # the two rows with num_test_files > 0
        assert py.n_with_fixtures == 1
        assert py.n_with_setup == 1
        assert py.n_with_teardown == 1
        assert py.fixtures_per_repo == [2]

    def test_repo_with_zero_fixtures_excluded_from_per_repo_lists(self, tmp_path):
        rows = self._rows(
            tmp_path,
            [{"language": "java", "clone_ok": True, "num_test_files": 5, "num_fixtures": 0}],
        )
        result = compute_prevalence(rows)
        assert result["java"].fixtures_per_repo == []

    def test_pooled_all_sums_across_languages(self, tmp_path):
        rows = self._rows(
            tmp_path,
            [
                {"language": "python", "clone_ok": True, "num_test_files": 1, "num_fixtures": 2, "num_setup": 2, "num_teardown": 0},
                {"language": "java", "clone_ok": True, "num_test_files": 1, "num_fixtures": 4, "num_setup": 0, "num_teardown": 4},
            ],
        )
        result = compute_prevalence(rows)
        assert result["all"].n_with_tests == 2
        assert result["all"].n_with_fixtures == 2
        assert sorted(result["all"].fixtures_per_repo) == [2, 4]

    def test_no_floor_variant_includes_everything(self, tmp_path):
        rows = self._rows(
            tmp_path,
            [{"language": "python", "clone_ok": True, "num_test_files": 1, "num_fixtures": 1}],
        )
        result = compute_prevalence(rows, min_test_files=None)
        assert result["python"].n_with_tests == 1

    def test_floor_variant_excludes_repos_below_min_test_files(self, tmp_path):
        rows = self._rows(
            tmp_path,
            [
                {"language": "python", "clone_ok": True, "num_test_files": MIN_TEST_FILES - 1, "num_fixtures": 1},
                {"language": "python", "clone_ok": True, "num_test_files": MIN_TEST_FILES, "num_fixtures": 1},
            ],
        )
        result = compute_prevalence(rows, min_test_files=MIN_TEST_FILES)
        assert result["python"].n_with_tests == 1
        assert result["python"].n_with_fixtures == 1


class TestRenderTable1:
    def test_renders_counts_and_percentages(self):
        entry = LanguagePrevalence(n_with_tests=10, n_with_fixtures=5, n_with_setup=4, n_with_teardown=1)
        table = render_table1({"all": entry})
        lines = table.splitlines()
        assert lines[0] == "| Language | Repositories with Tests | # | % | Setup (%) | Teardown (%) |"
        all_line = next(l for l in lines if l.startswith("| All"))
        assert "| All | 10 | 5 | 50.0% | 80.0% | 20.0% |" == all_line

    def test_zero_denominator_renders_dashes_not_a_crash(self):
        entry = LanguagePrevalence(n_with_tests=0, n_with_fixtures=0)
        table = render_table1({"all": entry})
        assert "| All | 0 | 0 | -- | -- | -- |" in table

    def test_includes_a_row_per_display_language_in_order(self):
        table = render_table1({})
        lines = [l for l in table.splitlines() if l.startswith("|") and "Language" not in l and "---" not in l]
        labels = [l.split("|")[1].strip() for l in lines]
        assert labels == ["All", "Python", "Java", "JavaScript", "TypeScript"]
        assert len(DISPLAY_LANGUAGES) == 4


class TestRenderTable2:
    def test_renders_medians(self):
        entry = LanguagePrevalence(
            fixtures_per_repo=[2, 4, 6], setup_per_repo=[1, 1, 1], teardown_per_repo=[0, 0, 2]
        )
        table = render_table2({"all": entry})
        assert "| All | 4.0 | 1.0 | 0.0 |" in table

    def test_empty_population_renders_dashes(self):
        table = render_table2({"all": LanguagePrevalence()})
        assert "| All | -- | -- | -- |" in table


class TestRenderRawNumbers:
    def test_renders_counts_and_sums(self):
        entry = LanguagePrevalence(
            n_with_tests=3,
            n_with_fixtures=2,
            n_with_setup=1,
            n_with_teardown=1,
            fixtures_per_repo=[2, 3],
            setup_per_repo=[1, 0],
            teardown_per_repo=[0, 1],
        )
        table = render_raw_numbers({"all": entry})
        assert "| All | 3 | 2 | 1 | 1 | 5 | 1 | 1 |" in table


class TestRenderMedianProse:
    def test_fills_in_the_pooled_medians(self):
        entry = LanguagePrevalence(fixtures_per_repo=[2, 4], setup_per_repo=[1, 1], teardown_per_repo=[0, 2])
        prose = render_median_prose({"all": entry})
        assert "3.0 test fixtures" in prose
        assert "1.0 setups" in prose
        assert "1.0 teardowns" in prose

    def test_no_data_renders_not_available(self):
        prose = render_median_prose({"all": LanguagePrevalence()})
        assert "Not available" in prose


class TestGenerateReport:
    def test_missing_db_renders_not_available(self, tmp_path):
        report = generate_report(db_root=tmp_path)
        assert "Not available -- db/rq1_prevalence.db not collected yet" in report

    def test_clone_ok_zero_repos_never_affect_any_count(self, tmp_path):
        """The core correctness guarantee: a clone failure must be
        "unknown", never silently counted as "confirmed no tests"."""
        _make_db(
            tmp_path,
            [
                {"language": "python", "clone_ok": True, "num_test_files": 5, "num_fixtures": 1, "num_setup": 1},
                {"language": "python", "clone_ok": False, "error_reason": "clone_failed"},
                {"language": "python", "clone_ok": False, "error_reason": "no_commit_at_or_before_cutoff"},
            ],
        )
        report = generate_report(db_root=tmp_path)
        # Only 1 successfully-scanned repo total, regardless of the 2 failures.
        assert "Population: 1 successfully-scanned repos" in report

    def test_both_variants_present_and_floor_changes_the_numbers(self, tmp_path):
        _make_db(
            tmp_path,
            [
                # Below the floor: counts in "no floor", excluded from "floor applied".
                {"language": "python", "clone_ok": True, "num_test_files": MIN_TEST_FILES - 1, "num_fixtures": 1, "num_setup": 1},
                # Above the floor: counts in both.
                {"language": "python", "clone_ok": True, "num_test_files": MIN_TEST_FILES, "num_fixtures": 1, "num_setup": 1},
            ],
        )
        report = generate_report(db_root=tmp_path)
        assert "## No additional quality floor" in report
        assert f"## Quality floor applied (>= {MIN_TEST_FILES} test files)" in report
        no_floor_section = report.split("## No additional quality floor")[1].split("## Quality floor applied")[0]
        with_floor_section = report.split(f"## Quality floor applied (>= {MIN_TEST_FILES} test files)")[1]
        assert "| All | 2 |" in no_floor_section
        assert "| All | 1 |" in with_floor_section

    def test_renders_display_languages_in_paper_order(self, tmp_path):
        _make_db(tmp_path, [{"language": "python", "clone_ok": True, "num_test_files": 1}])
        report = generate_report(db_root=tmp_path)
        table = report.split("### Table 1")[1]
        order = [line.split("|")[1].strip() for line in table.splitlines() if line.startswith("| ") and "Language" not in line][:5]
        assert order == ["All", "Python", "Java", "JavaScript", "TypeScript"]


class TestWriteReport:
    def test_writes_to_rq1_md(self, tmp_path):
        db_root = tmp_path / "db"
        out_dir = tmp_path / "out"
        path = write_report(out_dir, db_root=db_root)
        assert path == out_dir / "rq1.md"
        assert path.read_text() == generate_report(db_root=db_root)
