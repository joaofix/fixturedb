"""Tests for collection/research_questions/rq1.py.

Builds synthetic db/rq1_prevalence.db files under tmp_path by reusing
rq1_prevalence_scan.py's own initialise_rq1_db()/persist_result()/
_result_row() -- the real production code that writes this db, not a
reimplementation -- so these tests exercise the exact schema/shape the
real scan produces.
"""

from __future__ import annotations

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
    def test_reads_the_exact_file_the_scan_module_writes(self, tmp_path):
        """Regression guard: this module's db filename is derived from
        rq1_prevalence_scan.DB_PATH, not a second hardcoded literal, so a
        rename there can't silently desync into "always reports not
        available" here."""
        from collection.rq1_prevalence_scan import DB_PATH

        _make_db(tmp_path, [{"language": "python", "clone_ok": True, "num_test_files": 1}])
        assert (tmp_path / DB_PATH.name).exists()
        assert load_rows(tmp_path) is not None

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

    def test_pooled_all_percentage_is_weighted_not_averaged(self, tmp_path):
        """Statistical correctness guard: with asymmetric group sizes,
        averaging the two languages' own percentages gives a DIFFERENT
        (wrong) answer than pooling the raw counts first. Python: 50/100
        = 50%. Java: 9/10 = 90%. Naive average of percentages: 70%.
        True pooled: (50+9)/(100+10) = 53.6% -- what the paper's "All"
        row must report, since it's one population, not two percentages
        averaged."""
        rows = []
        for i in range(100):
            rows.append({"language": "python", "clone_ok": True, "num_test_files": 1, "num_fixtures": 1 if i < 50 else 0})
        for i in range(10):
            rows.append({"language": "java", "clone_ok": True, "num_test_files": 1, "num_fixtures": 1 if i < 9 else 0})
        db_rows = self._rows(tmp_path, rows)
        result = compute_prevalence(db_rows)

        assert result["all"].n_with_tests == 110
        assert result["all"].n_with_fixtures == 59
        table = render_table1(result)
        all_line = next(l for l in table.splitlines() if l.startswith("| All"))
        assert "53.6%" in all_line
        assert "70.0%" not in all_line  # the wrong, naively-averaged answer

    def test_pooled_all_median_is_over_the_combined_list_not_averaged(self, tmp_path):
        """Same statistical guard, for Table 2's median: Python's 5 repos
        median to 10, Java's 1 repo medians to 1. Naive average of the
        two medians: 5.5. True pooled median of the combined 6 values
        ([1,10,10,10,10,100] sorted): 10.0 -- what "All" must report."""
        rows = [
            {"language": "python", "clone_ok": True, "num_test_files": 1, "num_fixtures": 10},
            {"language": "python", "clone_ok": True, "num_test_files": 1, "num_fixtures": 10},
            {"language": "python", "clone_ok": True, "num_test_files": 1, "num_fixtures": 10},
            {"language": "python", "clone_ok": True, "num_test_files": 1, "num_fixtures": 10},
            {"language": "python", "clone_ok": True, "num_test_files": 1, "num_fixtures": 100},
            {"language": "java", "clone_ok": True, "num_test_files": 1, "num_fixtures": 1},
        ]
        db_rows = self._rows(tmp_path, rows)
        result = compute_prevalence(db_rows)

        table = render_table2(result)
        all_line = next(l for l in table.splitlines() if l.startswith("| All"))
        assert "| All | 10.0 |" in all_line
        assert "5.5" not in all_line  # the wrong, naively-averaged answer

    def test_other_only_fixture_counts_toward_fixtures_but_not_setup_or_teardown(self, tmp_path):
        """A repo whose fixtures are all fixture_role='other' (no setup,
        no teardown) must still count toward n_with_fixtures/
        fixtures_per_repo, but NOT toward n_with_setup/n_with_teardown."""
        rows = self._rows(
            tmp_path,
            [{"language": "python", "clone_ok": True, "num_test_files": 1, "num_fixtures": 3, "num_setup": 0, "num_teardown": 0}],
        )
        result = compute_prevalence(rows)
        py = result["python"]
        assert py.n_with_fixtures == 1
        assert py.fixtures_per_repo == [3]
        assert py.n_with_setup == 0
        assert py.n_with_teardown == 0

    def test_fixtures_per_repo_length_always_matches_n_with_fixtures(self, tmp_path):
        """Invariant Table 1's "#" column and Table 2's whole population
        both silently depend on: these must never drift apart."""
        rows = self._rows(
            tmp_path,
            [
                {"language": "python", "clone_ok": True, "num_test_files": 1, "num_fixtures": 5},
                {"language": "python", "clone_ok": True, "num_test_files": 1, "num_fixtures": 0},
                {"language": "java", "clone_ok": True, "num_test_files": 1, "num_fixtures": 2},
            ],
        )
        result = compute_prevalence(rows)
        for entry in result.values():
            assert len(entry.fixtures_per_repo) == entry.n_with_fixtures
            assert len(entry.setup_per_repo) == entry.n_with_fixtures
            assert len(entry.teardown_per_repo) == entry.n_with_fixtures

    def test_no_quality_floor_is_applied(self, tmp_path):
        """RQ1 deliberately never filters on min_test_files (or anything
        else) -- see this module's own docstring for why. A repo with a
        single test file counts exactly like one with a thousand."""
        rows = self._rows(
            tmp_path,
            [{"language": "python", "clone_ok": True, "num_test_files": 1, "num_fixtures": 1}],
        )
        result = compute_prevalence(rows)
        assert result["python"].n_with_tests == 1


class TestRenderTable1:
    def test_renders_counts_and_percentages(self):
        """Fixture (%)/Setup (%)/Teardown (%) all share one denominator,
        `n_with_tests` (2026-10-04 restructure -- see render_table1()'s
        own docstring): 5/10 = 50%, 4/10 = 40%, 1/10 = 10%. No `#` column
        -- that raw count lives in the Raw Numbers table instead, so
        nothing here can be misread as dividing by it."""
        entry = LanguagePrevalence(n_with_tests=10, n_with_fixtures=5, n_with_setup=4, n_with_teardown=1)
        table = render_table1({"all": entry})
        lines = table.splitlines()
        assert lines[0] == "| Language | Repositories with Tests | Fixture (%) | Setup (%) | Teardown (%) |"
        all_line = next(l for l in lines if l.startswith("| All"))
        assert "| All | 10 | 50.0% | 40.0% | 10.0% |" == all_line

    def test_zero_denominator_renders_dashes_not_a_crash(self):
        entry = LanguagePrevalence(n_with_tests=0, n_with_fixtures=0)
        table = render_table1({"all": entry})
        assert "| All | 0 | -- | -- | -- |" in table

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

    def test_no_quality_floor_section_appears_anywhere(self, tmp_path):
        """Regression guard: the "Quality floor applied" variant (and its
        min_test_files filtering) was deliberately removed -- see this
        module's own docstring. Must never silently reappear."""
        _make_db(
            tmp_path,
            [{"language": "python", "clone_ok": True, "num_test_files": 1, "num_fixtures": 1, "num_setup": 1}],
        )
        report = generate_report(db_root=tmp_path)
        assert "## Quality floor applied" not in report
        assert "## No additional quality floor" not in report
        assert "| All | 1 |" in report

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
