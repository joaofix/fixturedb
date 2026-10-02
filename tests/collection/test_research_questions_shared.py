"""Tests for collection/research_questions/_shared.py -- the helpers rq2.py,
rq3.py, rq4.py, and language_contamination.py all import instead of each
redefining their own copy.
"""

from __future__ import annotations

from collection.between_group_comparison import BalanceTest
from collection.db import (
    db_session,
    initialise_db,
    insert_fixture,
    upsert_repository,
    upsert_test_file,
)
from collection.research_questions._shared import (
    LanguageLeakage,
    NCounts,
    apply_fdr_correction,
    compute_language_leakage,
    compute_stratified_continuous_balance,
    fdr_cell,
    fetch_categorical_column,
    fetch_continuous_column,
    fetch_continuous_column_by_repo,
    fmt,
    format_p_value,
    pct,
    percentile,
    render_comparison_table,
    render_language_leakage_table,
    repo_level_means,
    repo_level_medians,
    require_db_or_none,
    summarize_continuous,
    write_markdown_report,
)


class TestRequireDbOrNone:
    def test_missing_db_returns_none(self, tmp_path):
        assert require_db_or_none("a", tmp_path) is None

    def test_existing_db_returns_its_path(self, tmp_path):
        db_file = tmp_path / "a.db"
        initialise_db(db_file)
        assert require_db_or_none("a", tmp_path) == db_file

    def test_dataset_c_resolves_to_sampled_db_not_full_db(self, tmp_path):
        """Dataset "c" resolves to db/c_sampled.db, the fixture-level
        sample-down -- not the full db/c.db."""
        initialise_db(tmp_path / "c_sampled.db")
        assert require_db_or_none("c", tmp_path) == tmp_path / "c_sampled.db"

    def test_dataset_c_ignores_full_db_when_only_that_exists(self, tmp_path):
        """db/c.db existing (the full, unsampled corpus) must never be
        enough to satisfy dataset "c" on its own -- run `sample-c-repos`
        first to produce db/c_sampled.db."""
        initialise_db(tmp_path / "c.db")
        initialise_db(tmp_path / "a.db")  # unrelated dataset present -- must not matter
        assert require_db_or_none("c", tmp_path) is None


class TestSummarizeContinuous:
    def test_known_values(self):
        s = summarize_continuous([1.0, 2.0, 3.0, 4.0])
        assert s == {"n": 4, "mean": 2.5, "median": 2.5, "min": 1.0, "max": 4.0, "stdev": s["stdev"]}
        assert round(s["stdev"], 4) == round(1.2909944487358056, 4)

    def test_empty_list(self):
        s = summarize_continuous([])
        assert s == {"n": 0, "mean": None, "median": None, "min": None, "max": None, "stdev": None}

    def test_single_value_stdev_is_zero_not_an_error(self):
        s = summarize_continuous([7.0])
        assert s["n"] == 1
        assert s["stdev"] == 0.0


class TestPercentile:
    def test_empty_list_returns_none(self):
        assert percentile([], 75) is None

    def test_single_value_returns_that_value_for_any_percentile(self):
        assert percentile([7.0], 25) == 7.0
        assert percentile([7.0], 90) == 7.0

    def test_known_values(self):
        values = [10.0, 20.0, 30.0, 40.0]
        assert percentile(values, 50) == 25.0
        assert percentile(values, 75) == 32.5
        assert percentile(values, 90) == 37.0

    def test_50th_percentile_matches_median(self):
        values = [3.0, 1.0, 4.0, 1.0, 5.0, 9.0, 2.0, 6.0]
        assert percentile(values, 50) == summarize_continuous(values)["median"]


class TestFmt:
    def test_none_renders_as_dashes(self):
        assert fmt(None) == "--"

    def test_rounds_to_requested_digits(self):
        assert fmt(3.14159, 2) == "3.14"
        assert fmt(3.14159, 0) == "3"


class TestPct:
    def test_none_renders_as_dashes_no_percent_sign(self):
        assert pct(None) == "--"

    def test_proportion_renders_as_percentage(self):
        assert pct(0.723, 1) == "72.3%"

    def test_zero_and_one_are_not_treated_as_missing(self):
        assert pct(0.0) == "0.0%"
        assert pct(1.0) == "100.0%"


class TestFormatPValue:
    def test_rounds_to_three_decimals(self):
        assert format_p_value(0.03142) == "0.031"
        assert format_p_value(0.5) == "0.500"

    def test_below_threshold_renders_as_less_than(self):
        assert format_p_value(0.0009) == "<.001"
        assert format_p_value(0.0001) == "<.001"

    def test_exactly_at_threshold_renders_as_number_not_less_than(self):
        assert format_p_value(0.001) == "0.001"

    def test_zero_renders_as_less_than(self):
        assert format_p_value(0.0) == "<.001"


def _make_fixtures_db(tmp_path, values: list[dict]) -> None:
    db_file = tmp_path / "a.db"
    initialise_db(db_file)
    with db_session(db_file) as conn:
        repo_id, _ = upsert_repository(
            conn,
            {
                "github_id": 1,
                "full_name": "owner/repo",
                "language": "python",
                "stars": 1,
                "forks": 0,
                "description": "",
                "topics": "[]",
                "created_at": "2019-01-01T00:00:00Z",
                "pushed_at": "2020-01-01T00:00:00Z",
                "clone_url": "https://github.com/owner/repo.git",
                "num_contributors": 1,
                "domain": None,
                "repo_age_years": None,
            },
        )
        file_id = upsert_test_file(conn, repo_id, "tests/test_foo.py", "python")
        for i, overrides in enumerate(values):
            base = {
                "file_id": file_id,
                "repo_id": repo_id,
                "name": f"fixture_{i}",
                "fixture_type": "pytest_decorator",
                "start_line": i,
                "end_line": i + 1,
                "loc": 5,
                "cyclomatic_complexity": 1,
                "num_comment_lines": 0,
                "comment_density": 0.0,
                "num_parameters": 0,
                "raw_source": "",
                "num_mocks": 0,
            }
            base.update(overrides)
            insert_fixture(conn, base)


class TestFetchContinuousColumn:
    def test_returns_non_null_values(self, tmp_path):
        _make_fixtures_db(tmp_path, [{"loc": 3}, {"loc": 7}, {"loc": None}])
        db_file = tmp_path / "a.db"
        with db_session(db_file) as conn:
            values = fetch_continuous_column(conn, "fixtures", "loc")
        assert sorted(values) == [3, 7]


class TestFetchCategoricalColumn:
    def test_returns_value_counts(self, tmp_path):
        _make_fixtures_db(
            tmp_path,
            [
                {"fixture_type": "before_each"},
                {"fixture_type": "before_each"},
                {"fixture_type": "after_each"},
            ],
        )
        db_file = tmp_path / "a.db"
        with db_session(db_file) as conn:
            dist = fetch_categorical_column(conn, "fixtures", "fixture_type")
        assert dist == {"before_each": 2, "after_each": 1}


class TestFetchContinuousColumnByRepo:
    def test_groups_values_by_repo_id(self, tmp_path):
        _make_fixtures_db(tmp_path, [{"loc": 3}, {"loc": 7}, {"loc": None}])
        db_file = tmp_path / "a.db"
        with db_session(db_file) as conn:
            by_repo = fetch_continuous_column_by_repo(conn, "fixtures", "loc")
        # _make_fixtures_db puts every fixture under the same one repo.
        assert len(by_repo) == 1
        assert sorted(next(iter(by_repo.values()))) == [3, 7]


class TestRepoLevelMeans:
    def test_one_mean_per_repo(self):
        by_repo = {1: [10.0, 20.0], 2: [5.0], 3: [1.0, 2.0, 3.0]}
        assert sorted(repo_level_means(by_repo)) == [2.0, 5.0, 15.0]

    def test_empty_input_returns_empty_list(self):
        assert repo_level_means({}) == []

    def test_a_repo_with_many_fixtures_still_contributes_one_value(self):
        """The whole point: a repo with 1000 fixtures must count once in
        the output, not 1000 times -- that's what distinguishes this from
        the raw fixture-level list fetch_continuous_column() returns."""
        by_repo = {1: [5.0] * 1000, 2: [10.0]}
        result = repo_level_means(by_repo)
        assert len(result) == 2


class TestRepoLevelMedians:
    def test_one_median_per_repo(self):
        by_repo = {1: [10.0, 20.0], 2: [5.0], 3: [1.0, 2.0, 100.0]}
        assert sorted(repo_level_medians(by_repo)) == [2.0, 5.0, 15.0]

    def test_empty_input_returns_empty_list(self):
        assert repo_level_medians({}) == []

    def test_median_is_not_mean_for_a_skewed_repo(self):
        """The whole point of using the median instead of the mean: a
        repo's own outlier fixture must not pull that repo's contributed
        value away from what a typical fixture in it looks like. Mean of
        [1, 2, 100] is 34.33; median is 2 -- if this returned the mean,
        this test would fail."""
        by_repo = {1: [1.0, 2.0, 100.0]}
        assert repo_level_medians(by_repo) == [2.0]

    def test_a_repo_with_many_fixtures_still_contributes_one_value(self):
        """The whole point: a repo with 1000 fixtures must count once in
        the output, not 1000 times -- that's what distinguishes this from
        the raw fixture-level list fetch_continuous_column() returns."""
        by_repo = {1: [5.0] * 1000, 2: [10.0]}
        result = repo_level_medians(by_repo)
        assert len(result) == 2


def _make_leakage_db(tmp_path, *, repo_language: str, file_fixtures: list[tuple[str, str]]) -> None:
    """db/a.db with one repo tagged `repo_language`, and one test_file per
    (relative_path, file_language) pair in `file_fixtures`, each carrying a
    single fixture."""
    db_file = tmp_path / "a.db"
    initialise_db(db_file)
    with db_session(db_file) as conn:
        repo_id, _ = upsert_repository(
            conn,
            {
                "github_id": 1,
                "full_name": "owner/repo",
                "language": repo_language,
                "stars": 1,
                "forks": 0,
                "description": "",
                "topics": "[]",
                "created_at": "2019-01-01T00:00:00Z",
                "pushed_at": "2020-01-01T00:00:00Z",
                "clone_url": "https://github.com/owner/repo.git",
                "num_contributors": 1,
                "domain": None,
                "repo_age_years": None,
            },
        )
        for i, (rel_path, file_language) in enumerate(file_fixtures):
            file_id = upsert_test_file(conn, repo_id, rel_path, file_language)
            insert_fixture(
                conn,
                {
                    "file_id": file_id,
                    "repo_id": repo_id,
                    "name": f"fixture_{i}",
                    "fixture_type": "pytest_decorator",
                    "scope": "per_test",
                    "start_line": 1,
                    "end_line": 2,
                    "loc": 5,
                    "cyclomatic_complexity": 1,
                    "max_nesting_depth": 1,
                    "num_objects_instantiated": 0,
                    "num_external_calls": 0,
                    "num_comment_lines": 0,
                    "comment_density": 0.0,
                    "num_parameters": 0,
                    "has_teardown_pair": 0,
                    "raw_source": "",
                    "framework": "pytest",
                    "num_mocks": 0,
                },
            )


class TestComputeLanguageLeakage:
    def test_no_leakage_when_all_fixtures_match_repo_language(self, tmp_path):
        _make_leakage_db(
            tmp_path,
            repo_language="python",
            file_fixtures=[("test_a.py", "python"), ("test_b.py", "python")],
        )
        with db_session(tmp_path / "a.db") as conn:
            leakage = compute_language_leakage(conn)
        assert len(leakage) == 1
        assert leakage[0].repo_language == "python"
        assert leakage[0].total == 2
        assert leakage[0].leaked == 0
        assert leakage[0].leaked_by_language == {}
        assert leakage[0].pct == 0.0

    def test_detects_leaked_fixtures_by_language(self, tmp_path):
        _make_leakage_db(
            tmp_path,
            repo_language="python",
            file_fixtures=[("test_a.py", "python"), ("foo.test.js", "javascript")],
        )
        with db_session(tmp_path / "a.db") as conn:
            leakage = compute_language_leakage(conn)
        assert len(leakage) == 1
        row = leakage[0]
        assert row.repo_language == "python"
        assert row.total == 2
        assert row.leaked == 1
        assert row.leaked_by_language == {"javascript": 1}
        assert row.pct == 50.0

    def test_no_fixtures_returns_empty_list(self, tmp_path):
        db_file = tmp_path / "a.db"
        initialise_db(db_file)
        with db_session(db_file) as conn:
            assert compute_language_leakage(conn) == []


class TestRenderLanguageLeakageTable:
    def test_renders_table_with_breakdown(self):
        leakage = [
            LanguageLeakage(
                repo_language="python",
                total=10,
                leaked=3,
                leaked_by_language={"javascript": 2, "java": 1},
            ),
        ]
        rendered = render_language_leakage_table(leakage)
        assert "3/10" in rendered
        assert "javascript=2" in rendered
        assert "java=1" in rendered

    def test_no_leakage_data_renders_no_data_row(self):
        rendered = render_language_leakage_table([])
        assert "_(no data)_" in rendered


class TestApplyFdrCorrection:
    def test_borderline_significant_results_can_fail_to_survive_correction(self):
        """Five tests: one clearly significant (p=0.001), two borderline
        (p=0.04, 0.045 -- both "significant" at uncorrected alpha=0.05),
        two clearly not (p=0.5, 0.6). Uncorrected, 3/5 look significant.
        BH-FDR ranks the borderline pair among all 5 p-values, where they
        pick up a stricter critical threshold and no longer clear it --
        this is the actual point of the correction, not just relabeling
        everything the same way uncorrected testing already would."""
        tests = {
            f"metric_{i}": BalanceTest(
                variable=f"metric_{i}", test_type="chi-square",
                p_value=p, is_balanced=p >= 0.05,
            )
            for i, p in enumerate([0.001, 0.04, 0.045, 0.5, 0.6])
        }
        result = apply_fdr_correction(tests)
        assert all("adjusted_p_value" in t.details for t in result.values())
        assert result["metric_0"].details["significant_after_correction"] is True
        assert result["metric_1"].details["significant_after_correction"] is False
        assert result["metric_2"].details["significant_after_correction"] is False

    def test_insufficient_data_tests_pass_through_unchanged(self):
        tests = {
            "real": BalanceTest(variable="real", test_type="chi-square", p_value=0.01, is_balanced=False),
            "skip": BalanceTest(
                variable="skip", test_type="chi-square", p_value=1.0, is_balanced=True,
                details={"reason": "insufficient_data"},
            ),
        }
        result = apply_fdr_correction(tests)
        assert "adjusted_p_value" not in result["skip"].details
        assert "adjusted_p_value" in result["real"].details

    def test_identical_distributions_tests_are_still_corrected(self):
        """reason='identical_distributions' (both sides are one single,
        equal value -- compute_continuous_balance()'s "trivially balanced"
        shortcut) is a real, complete result (p_value=1.0, real medians),
        not a non-result the way insufficient_data is -- it must still
        get adjusted_p_value, or every _row()-style renderer's `corrected`
        branch across rq2-4/balance.py (which only guards against
        insufficient_data/error, not this reason) hits a KeyError reading
        it. Real regression: reproduced via rq3.py's
        TestRenderTeardownDipTest before this fix."""
        tests = {
            "real": BalanceTest(variable="real", test_type="mann-whitney-u", p_value=0.01, is_balanced=False),
            "identical": BalanceTest(
                variable="identical", test_type="mann-whitney-u", p_value=1.0, is_balanced=True,
                details={"human_median": 1.0, "agent_median": 1.0, "reason": "identical_distributions"},
            ),
        }
        result = apply_fdr_correction(tests)
        assert "adjusted_p_value" in result["identical"].details
        assert "adjusted_p_value" in result["real"].details

    def test_error_tests_still_pass_through_unchanged(self):
        tests = {
            "real": BalanceTest(variable="real", test_type="chi-square", p_value=0.01, is_balanced=False),
            "broken": BalanceTest(
                variable="broken", test_type="chi-square", p_value=1.0, is_balanced=True,
                details={"error": "division by zero"},
            ),
        }
        result = apply_fdr_correction(tests)
        assert "adjusted_p_value" not in result["broken"].details
        assert "adjusted_p_value" in result["real"].details

    def test_empty_input_returns_empty_dict(self):
        assert apply_fdr_correction({}) == {}

    def test_no_testable_entries_returns_originals_unchanged(self):
        tests = {
            "skip": BalanceTest(
                variable="skip", test_type="chi-square", p_value=1.0, is_balanced=True,
                details={"reason": "insufficient_data"},
            ),
        }
        result = apply_fdr_correction(tests)
        assert result == tests

    def test_original_p_value_and_is_balanced_untouched(self):
        tests = {
            "m": BalanceTest(variable="m", test_type="chi-square", p_value=0.03, is_balanced=False),
        }
        result = apply_fdr_correction(tests)
        assert result["m"].p_value == 0.03
        assert result["m"].is_balanced is False


class TestFdrCell:
    def test_no_correction_applied_renders_dashes(self):
        t = BalanceTest(variable="m", test_type="chi-square", p_value=0.03, is_balanced=False)
        assert fdr_cell(t) == "--"

    def test_renders_adjusted_p_and_verdict(self):
        t = BalanceTest(
            variable="m", test_type="chi-square", p_value=0.03, is_balanced=False,
            details={"adjusted_p_value": 0.045, "significant_after_correction": True},
        )
        assert fdr_cell(t) == "0.045 (yes)"


class TestComputeStratifiedContinuousBalance:
    def test_only_shared_languages_are_compared(self):
        a_values = {"python": [1.0, 2.0], "java": [5.0, 6.0]}
        other_values = {"python": [10.0, 20.0], "javascript": [1.0, 2.0]}
        results = compute_stratified_continuous_balance(a_values, other_values, "loc")
        assert set(results.keys()) == {"python"}

    def test_no_shared_languages_returns_empty_dict(self):
        a_values = {"python": [1.0, 2.0]}
        other_values = {"java": [1.0, 2.0]}
        assert compute_stratified_continuous_balance(a_values, other_values, "loc") == {}

    def test_computes_real_mann_whitney_per_language(self):
        a_values = {"python": [1, 1, 2, 1, 2, 1, 2, 1, 2, 1]}
        other_values = {"python": [50, 60, 55, 58, 62, 57, 59, 61, 56, 54]}
        results = compute_stratified_continuous_balance(a_values, other_values, "loc")
        assert results["python"].p_value < 0.05


class TestRenderComparisonTable:
    def test_overall_row_always_first_and_never_bh_corrected(self):
        overall = BalanceTest(variable="loc", test_type="mann-whitney-u", p_value=0.02, is_balanced=False)
        rendered = render_comparison_table(overall, NCounts(5, 5), None, None, other_dataset="c")
        data_rows = [
            line
            for line in rendered.splitlines()
            if line.startswith("| ") and not line.startswith("| Language")
        ]
        assert data_rows[0].startswith("| Overall | 5 | 5 |")
        assert data_rows[0].rstrip("|").rsplit("|", 1)[-1].strip() == "--"

    def test_overall_only_when_no_family_given(self):
        overall = BalanceTest(variable="some_metric", test_type="chi-square", p_value=0.5, is_balanced=True)
        rendered = render_comparison_table(overall, NCounts(3, 3), None, None, other_dataset="c")
        data_rows = [
            line
            for line in rendered.splitlines()
            if line.startswith("| ") and not line.startswith("| Language")
        ]
        assert len(data_rows) == 1

    def test_per_language_rows_added_and_bh_corrected_independently_of_overall(self):
        overall = BalanceTest(variable="loc", test_type="mann-whitney-u", p_value=0.02, is_balanced=False)
        per_language = {
            "python": BalanceTest(
                variable="loc_python", test_type="mann-whitney-u", p_value=0.04, is_balanced=False
            ),
            "java": BalanceTest(
                variable="loc_java", test_type="mann-whitney-u", p_value=0.6, is_balanced=True
            ),
        }
        per_language_n = {"python": NCounts(2, 2), "java": NCounts(3, 3)}
        rendered = render_comparison_table(
            overall, NCounts(5, 5), per_language, per_language_n, other_dataset="c"
        )
        python_line = next(line for line in rendered.splitlines() if line.startswith("| python |"))
        java_line = next(line for line in rendered.splitlines() if line.startswith("| java |"))
        # Both languages' raw p-values still shown exactly.
        assert "0.040" in python_line
        assert "0.600" in java_line
        # BH-adjusted p present (not "--") for both -- corrected as a
        # 2-test family, independent of the Overall row's own p=0.02.
        assert not python_line.rstrip("|").rsplit("|", 1)[-1].strip() == "--"
        assert not java_line.rstrip("|").rsplit("|", 1)[-1].strip() == "--"

    def test_chi_square_statistic_shows_degrees_of_freedom(self):
        overall = BalanceTest(
            variable="scope", test_type="chi-square", p_value=0.5, is_balanced=True,
            statistic=3.2, details={"degrees_of_freedom": 2, "cramers_v": 0.1, "cramers_v_magnitude": "small"},
        )
        rendered = render_comparison_table(overall, NCounts(5, 5), None, None, other_dataset="c")
        assert "chi2=3.2 (df=2)" in rendered

    def test_mann_whitney_statistic_labeled_u(self):
        overall = BalanceTest(
            variable="loc", test_type="mann-whitney-u", p_value=0.5, is_balanced=True,
            statistic=12.0, details={"cliffs_delta": 0.1, "cliffs_delta_magnitude": "negligible"},
        )
        rendered = render_comparison_table(overall, NCounts(5, 5), None, None, other_dataset="c")
        assert "U=12.0" in rendered

    def test_insufficient_data_row_still_shows_n(self):
        overall = BalanceTest(
            variable="loc", test_type="mann-whitney-u", p_value=1.0, is_balanced=True,
            details={"reason": "insufficient_data"},
        )
        rendered = render_comparison_table(overall, NCounts(0, 5), None, None, other_dataset="c")
        overall_line = next(line for line in rendered.splitlines() if line.startswith("| Overall |"))
        assert "| Overall | 0 | 5 |" in overall_line
        assert "_insufficient data_" in overall_line

    def test_error_row_shows_test_failed_marker(self):
        overall = BalanceTest(
            variable="loc", test_type="chi-square", p_value=1.0, is_balanced=True,
            details={"error": "some scipy failure"},
        )
        rendered = render_comparison_table(overall, NCounts(1, 1), None, None, other_dataset="c")
        assert "_test failed (some scipy failure)_" in rendered

    def test_no_significant_yes_no_column(self):
        overall = BalanceTest(variable="loc", test_type="mann-whitney-u", p_value=0.02, is_balanced=False)
        rendered = render_comparison_table(overall, NCounts(5, 5), None, None, other_dataset="c")
        assert "significant (p<0.05)" not in rendered

    def test_header_names_other_dataset_column(self):
        overall = BalanceTest(variable="loc", test_type="mann-whitney-u", p_value=0.5, is_balanced=True)
        rendered = render_comparison_table(overall, NCounts(5, 5), None, None, other_dataset="c")
        assert "n_C" in rendered.splitlines()[0]

    def test_no_per_language_medians_means_no_median_columns(self):
        """The default (per_language_medians=None) renders the original
        8-column table, byte-for-byte -- every existing caller (rq3.py/
        rq4.py, RQ2's own categorical tables) doesn't pass this arg."""
        overall = BalanceTest(variable="loc", test_type="mann-whitney-u", p_value=0.5, is_balanced=True)
        rendered = render_comparison_table(overall, NCounts(5, 5), None, None, other_dataset="c")
        header = rendered.splitlines()[0]
        assert "median" not in header.lower()
        assert header.count("|") == 9  # 8 columns -> 9 pipes

    def test_per_language_medians_add_columns_named_for_each_dataset(self):
        overall = BalanceTest(variable="loc", test_type="mann-whitney-u", p_value=0.02, is_balanced=False)
        per_language = {
            "python": BalanceTest(
                variable="loc_python", test_type="mann-whitney-u", p_value=0.04, is_balanced=False
            ),
        }
        per_language_n = {"python": NCounts(2, 2)}
        rendered = render_comparison_table(
            overall,
            NCounts(5, 5),
            per_language,
            per_language_n,
            other_dataset="c",
            per_language_medians={"python": (7.5, 3.25)},
        )
        header = rendered.splitlines()[0]
        assert "A median" in header
        assert "C median" in header
        assert header.count("|") == 11  # 10 columns -> 11 pipes

    def test_per_language_medians_values_land_on_the_right_row(self):
        overall = BalanceTest(variable="loc", test_type="mann-whitney-u", p_value=0.02, is_balanced=False)
        per_language = {
            "python": BalanceTest(
                variable="loc_python", test_type="mann-whitney-u", p_value=0.04, is_balanced=False
            ),
            "java": BalanceTest(
                variable="loc_java", test_type="mann-whitney-u", p_value=0.6, is_balanced=True
            ),
        }
        per_language_n = {"python": NCounts(2, 2), "java": NCounts(3, 3)}
        rendered = render_comparison_table(
            overall,
            NCounts(5, 5),
            per_language,
            per_language_n,
            other_dataset="c",
            per_language_medians={"python": (7.5, 3.25), "java": (1.0, 2.0)},
        )
        python_line = next(line for line in rendered.splitlines() if line.startswith("| python |"))
        java_line = next(line for line in rendered.splitlines() if line.startswith("| java |"))
        assert "| python | 2 | 2 | 7.50 | 3.25 |" in python_line
        assert "| java | 3 | 3 | 1.00 | 2.00 |" in java_line

    def test_overall_row_medians_are_always_dashes(self):
        """Overall gets no aggregate median -- just placeholder cells so
        the row's column count matches the rest of the table."""
        overall = BalanceTest(variable="loc", test_type="mann-whitney-u", p_value=0.02, is_balanced=False)
        per_language = {
            "python": BalanceTest(
                variable="loc_python", test_type="mann-whitney-u", p_value=0.04, is_balanced=False
            ),
        }
        per_language_n = {"python": NCounts(2, 2)}
        rendered = render_comparison_table(
            overall,
            NCounts(5, 5),
            per_language,
            per_language_n,
            other_dataset="c",
            per_language_medians={"python": (7.5, 3.25)},
        )
        overall_line = next(line for line in rendered.splitlines() if line.startswith("| Overall |"))
        assert "| Overall | 5 | 5 | -- | -- |" in overall_line

    def test_language_missing_from_medians_dict_renders_dashes_not_ragged(self):
        """A language present in per_language but absent from
        per_language_medians (e.g. a real gap upstream) still gets its two
        median cells -- "--"/"--" -- rather than a short row."""
        overall = BalanceTest(variable="loc", test_type="mann-whitney-u", p_value=0.02, is_balanced=False)
        per_language = {
            "python": BalanceTest(
                variable="loc_python", test_type="mann-whitney-u", p_value=0.04, is_balanced=False
            ),
        }
        per_language_n = {"python": NCounts(2, 2)}
        rendered = render_comparison_table(
            overall,
            NCounts(5, 5),
            per_language,
            per_language_n,
            other_dataset="c",
            per_language_medians={},  # python missing entirely
        )
        python_line = next(line for line in rendered.splitlines() if line.startswith("| python |"))
        assert "| python | 2 | 2 | -- | -- |" in python_line

    def test_insufficient_data_row_still_has_median_columns_when_requested(self):
        overall = BalanceTest(
            variable="loc", test_type="mann-whitney-u", p_value=1.0, is_balanced=True,
            details={"reason": "insufficient_data"},
        )
        rendered = render_comparison_table(
            overall, NCounts(0, 5), None, None, other_dataset="c", per_language_medians={}
        )
        overall_line = next(line for line in rendered.splitlines() if line.startswith("| Overall |"))
        assert "| Overall | 0 | 5 | -- | -- | -- | -- | _insufficient data_ | -- | -- |" == overall_line

    def test_q3_and_p90_add_their_own_columns_independently_of_medians(self):
        """Q3/P90 don't require per_language_medians -- each of the three
        extra-column kinds is independently optional."""
        overall = BalanceTest(variable="loc", test_type="mann-whitney-u", p_value=0.02, is_balanced=False)
        per_language = {
            "python": BalanceTest(
                variable="loc_python", test_type="mann-whitney-u", p_value=0.04, is_balanced=False
            ),
        }
        per_language_n = {"python": NCounts(2, 2)}
        rendered = render_comparison_table(
            overall,
            NCounts(5, 5),
            per_language,
            per_language_n,
            other_dataset="c",
            per_language_q3={"python": (11.0, 9.0)},
        )
        header = rendered.splitlines()[0]
        assert "A Q3" in header
        assert "C Q3" in header
        assert "median" not in header.lower()
        assert header.count("|") == 11  # 10 columns -> 11 pipes
        python_line = next(line for line in rendered.splitlines() if line.startswith("| python |"))
        assert "| python | 2 | 2 | 11.00 | 9.00 |" in python_line

    def test_median_q3_p90_columns_appear_in_that_fixed_order(self):
        overall = BalanceTest(variable="loc", test_type="mann-whitney-u", p_value=0.02, is_balanced=False)
        per_language = {
            "python": BalanceTest(
                variable="loc_python", test_type="mann-whitney-u", p_value=0.04, is_balanced=False
            ),
        }
        per_language_n = {"python": NCounts(2, 2)}
        rendered = render_comparison_table(
            overall,
            NCounts(5, 5),
            per_language,
            per_language_n,
            other_dataset="c",
            per_language_medians={"python": (5.0, 4.0)},
            per_language_q3={"python": (11.0, 9.0)},
            per_language_p90={"python": (20.0, 15.0)},
        )
        header = rendered.splitlines()[0]
        assert header.index("A median") < header.index("A Q3") < header.index("A P90") < header.index("Statistic")
        assert header.count("|") == 15  # 14 columns -> 15 pipes
        python_line = next(line for line in rendered.splitlines() if line.startswith("| python |"))
        assert (
            "| python | 2 | 2 | 5.00 | 4.00 | 11.00 | 9.00 | 20.00 | 15.00 |" in python_line
        )
        overall_line = next(line for line in rendered.splitlines() if line.startswith("| Overall |"))
        assert "| Overall | 5 | 5 | -- | -- | -- | -- | -- | -- |" in overall_line


class TestWriteMarkdownReport:
    def test_second_write_fully_replaces_the_first(self, tmp_path):
        """A dataset shrinking between runs (e.g. a retroactive dedup fix)
        must never leave stale content from a larger, older report behind."""
        path = write_markdown_report(tmp_path, "rq2.md", "# old report\n" * 50)
        assert len(path.read_text()) > len("# new report\n")

        path = write_markdown_report(tmp_path, "rq2.md", "# new report\n")
        assert path.read_text() == "# new report\n"

    def test_creates_output_dir_if_missing(self, tmp_path):
        out_dir = tmp_path / "does" / "not" / "exist"
        path = write_markdown_report(out_dir, "rq2.md", "content")
        assert path == out_dir / "rq2.md"
        assert path.read_text() == "content"
