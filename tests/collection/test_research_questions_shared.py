"""Tests for collection/research_questions/_shared.py -- the helpers rq1.py,
rq2.py, rq3.py, and language_contamination.py all import instead of each
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
    apply_fdr_correction,
    compute_language_leakage,
    compute_stratified_categorical_balance,
    fdr_cell,
    fetch_categorical_column,
    fetch_continuous_column,
    fetch_continuous_column_by_repo,
    fmt,
    render_language_leakage_table,
    render_stratified_categorical_table,
    repo_level_means,
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
        initialise_db(tmp_path / "c_sampled.db")
        assert require_db_or_none("c", tmp_path) == tmp_path / "c_sampled.db"

    def test_dataset_c_ignores_full_db_when_only_that_exists(self, tmp_path):
        """The real, full db/c.db existing must never be enough to satisfy
        dataset "c" for any research_questions/ script -- it's ~3.3x Dataset
        A's size, and running RQ comparisons against that imbalance is
        exactly what this redirection exists to prevent."""
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


class TestFmt:
    def test_none_renders_as_dashes(self):
        assert fmt(None) == "--"

    def test_rounds_to_requested_digits(self):
        assert fmt(3.14159, 2) == "3.14"
        assert fmt(3.14159, 0) == "3"


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
                "scope": "per_test",
                "start_line": i,
                "end_line": i + 1,
                "loc": 5,
                "cyclomatic_complexity": 1,
                "max_nesting_depth": 1,
                "num_objects_instantiated": 0,
                "num_external_calls": 0,
                "num_parameters": 0,
                "has_teardown_pair": 0,
                "raw_source": "",
                "framework": "pytest",
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
            tmp_path, [{"scope": "per_test"}, {"scope": "per_test"}, {"scope": "per_class"}]
        )
        db_file = tmp_path / "a.db"
        with db_session(db_file) as conn:
            dist = fetch_categorical_column(conn, "fixtures", "scope")
        assert dist == {"per_test": 2, "per_class": 1}


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


class TestComputeStratifiedCategoricalBalance:
    def test_only_shared_languages_are_compared(self):
        a_dist = {"python": {"has_mock": 5, "no_mock": 5}, "java": {"has_mock": 1, "no_mock": 1}}
        other_dist = {"python": {"has_mock": 2, "no_mock": 8}, "javascript": {"has_mock": 1, "no_mock": 1}}
        results = compute_stratified_categorical_balance(a_dist, other_dist, "has_mock")
        assert set(results.keys()) == {"python"}

    def test_no_shared_languages_returns_empty_dict(self):
        a_dist = {"python": {"has_mock": 5, "no_mock": 5}}
        other_dist = {"java": {"has_mock": 5, "no_mock": 5}}
        assert compute_stratified_categorical_balance(a_dist, other_dist, "has_mock") == {}

    def test_computes_real_chi_square_per_language(self):
        # Sharply different has_mock rates for python -> should be significant.
        a_dist = {"python": {"has_mock": 90, "no_mock": 10}}
        other_dist = {"python": {"has_mock": 10, "no_mock": 90}}
        results = compute_stratified_categorical_balance(a_dist, other_dist, "has_mock")
        assert results["python"].p_value < 0.05


class TestRenderStratifiedCategoricalTable:
    def test_renders_one_row_per_language(self):
        a_dist = {"python": {"has_mock": 90, "no_mock": 10}}
        other_dist = {"python": {"has_mock": 10, "no_mock": 90}}
        results = compute_stratified_categorical_balance(a_dist, other_dist, "has_mock")
        rendered = render_stratified_categorical_table(results)
        assert "| python |" in rendered

    def test_no_results_renders_placeholder_row(self):
        rendered = render_stratified_categorical_table({})
        assert "_(no language shared by both datasets)_" in rendered

    def test_insufficient_data_marked_per_language(self):
        a_dist = {"python": {"has_mock": 0, "no_mock": 0}}
        other_dist = {"python": {"has_mock": 5, "no_mock": 5}}
        results = compute_stratified_categorical_balance(a_dist, other_dist, "has_mock")
        rendered = render_stratified_categorical_table(results)
        assert "_insufficient data_" in rendered

    def test_all_zero_category_no_longer_fails_the_test(self):
        """This exact shape (a whole category, e.g. "teardown", at 0 on
        both sides for one language) used to crash chi2_contingency inside
        compute_categorical_balance() -- fixed there by dropping empty
        columns before testing (see test_between_group_comparison.py's
        test_all_zero_column_is_dropped_not_a_failure). Confirms the fix
        holds through compute_stratified_categorical_balance() and renders
        as a real result, not a "test failed" placeholder."""
        a_dist = {"javascript": {"setup": 3, "teardown": 0, "other": 2}}
        other_dist = {"javascript": {"setup": 1, "teardown": 0, "other": 4}}
        results = compute_stratified_categorical_balance(a_dist, other_dist, "fixture_type_kind")
        assert "error" not in results["javascript"].details
        rendered = render_stratified_categorical_table(results)
        assert "_test failed" not in rendered
        assert "| javascript |" in rendered

    def test_genuine_test_failure_still_renders_as_test_failed(self):
        """The "test failed" rendering path itself must still work for a
        real, otherwise-unhandled compute_categorical_balance() exception
        -- constructed directly via BalanceTest rather than relying on
        finding a live scipy failure mode (the main one is now fixed)."""
        results = {
            "javascript": BalanceTest(
                variable="fixture_type_kind_javascript",
                test_type="chi-square",
                p_value=1.0,
                is_balanced=True,
                details={"error": "some other unrecoverable scipy failure"},
            )
        }
        rendered = render_stratified_categorical_table(results)
        assert "_test failed (some other unrecoverable scipy failure)_" in rendered


class TestWriteMarkdownReport:
    def test_second_write_fully_replaces_the_first(self, tmp_path):
        """A dataset shrinking between runs (e.g. a retroactive dedup fix)
        must never leave stale content from a larger, older report behind."""
        path = write_markdown_report(tmp_path, "rq1.md", "# old report\n" * 50)
        assert len(path.read_text()) > len("# new report\n")

        path = write_markdown_report(tmp_path, "rq1.md", "# new report\n")
        assert path.read_text() == "# new report\n"

    def test_creates_output_dir_if_missing(self, tmp_path):
        out_dir = tmp_path / "does" / "not" / "exist"
        path = write_markdown_report(out_dir, "rq1.md", "content")
        assert path == out_dir / "rq1.md"
        assert path.read_text() == "content"
