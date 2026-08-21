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
    NCounts,
    apply_fdr_correction,
    compare_categorical_repo_level,
    compute_language_leakage,
    compute_stratified_categorical_balance,
    compute_stratified_continuous_balance,
    fdr_cell,
    fetch_categorical_column,
    fetch_categorical_column_by_repo,
    fetch_continuous_column,
    fetch_continuous_column_by_repo,
    fmt,
    format_p_value,
    pct,
    render_ascii_histogram,
    render_categorical_repo_level_table,
    render_comparison_table,
    render_language_leakage_table,
    repo_level_category_n_counts,
    repo_level_category_proportions,
    repo_level_means,
    require_db_or_none,
    run_dip_test,
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


class TestRunDipTest:
    # Uniform 0.30..0.70 -- the dip test's own p-value is calibrated
    # against the uniform distribution as the unimodal reference case, so
    # this is the strongest, least-arbitrary "should not reject
    # unimodality" fixture available, and needs no RNG to be deterministic.
    UNIMODAL_VALUES = [i / 100 for i in range(30, 71)]
    # Two tight, far-separated clusters (0.000-0.020 and 0.980-1.000) --
    # an extreme, unambiguous bimodal shape, also RNG-free.
    BIMODAL_VALUES = [i / 1000 for i in range(0, 21)] + [1 - i / 1000 for i in range(0, 21)]

    def test_fewer_than_four_values_returns_none(self):
        assert run_dip_test([]) is None
        assert run_dip_test([0.5]) is None
        assert run_dip_test([0.1, 0.2, 0.3]) is None

    def test_exactly_four_values_does_not_crash(self):
        result = run_dip_test([0.1, 0.2, 0.3, 0.4])
        assert result is not None
        assert result["n"] == 4

    def test_uniform_distribution_not_significant(self):
        result = run_dip_test(self.UNIMODAL_VALUES)
        assert result["n"] == len(self.UNIMODAL_VALUES)
        assert result["p_value"] > 0.05

    def test_bimodal_distribution_significant(self):
        result = run_dip_test(self.BIMODAL_VALUES)
        assert result["n"] == len(self.BIMODAL_VALUES)
        assert result["p_value"] < 0.05
        # The bimodal split's dip statistic should exceed the uniform
        # case's -- confirms the two calls aren't returning the same
        # constant regardless of input.
        uniform_result = run_dip_test(self.UNIMODAL_VALUES)
        assert result["dip_statistic"] > uniform_result["dip_statistic"]

    def test_deterministic_no_seed_needed(self):
        """Two calls on the same data must agree exactly -- the default
        tabulated-critical-values p-value (not the optional bootstrap
        mode) is used specifically so this holds without a seed."""
        first = run_dip_test(self.BIMODAL_VALUES)
        second = run_dip_test(self.BIMODAL_VALUES)
        assert first == second


class TestRenderAsciiHistogram:
    def test_empty_values_renders_no_data(self):
        assert render_ascii_histogram([]) == "_(no data)_"

    def test_renders_fenced_code_block_with_all_bins(self):
        text = render_ascii_histogram([0.05, 0.05, 0.95], n_bins=10)
        lines = text.splitlines()
        assert lines[0] == "```"
        assert lines[-1] == "```"
        # 10 bins + 2 fence lines
        assert len(lines) == 12

    def test_bin_counts_match_input(self):
        text = render_ascii_histogram([0.05, 0.05, 0.95], n_bins=10)
        # bin 0 (0.00-0.10) gets the two 0.05s, bin 9 (0.90-1.00) gets the 0.95
        assert "0.00- 0.10 | " in text or "0.00-0.10" in text
        assert "(2)" in text
        assert "(1)" in text

    def test_value_at_exact_upper_edge_clamps_into_last_bin(self):
        """A value == value_range's upper bound (1.0 for the default 0..1
        range) must land in the last bin, not be dropped or overflow into
        a nonexistent 11th bin -- exercises the `v < hi` boundary check."""
        text = render_ascii_histogram([1.0], n_bins=4)
        assert "(1)" in text
        # Only 4 bins + 2 fence lines -- no extra bin created for the edge value.
        assert len(text.splitlines()) == 6

    def test_out_of_range_value_clamps_instead_of_dropped(self):
        text = render_ascii_histogram([-5.0, 5.0], n_bins=4)
        # Both values must still be counted somewhere (clamped to the
        # nearest edge bin), not silently discarded.
        total_counted = sum(int(line.rsplit("(", 1)[1].rstrip(")")) for line in text.splitlines()[1:-1])
        assert total_counted == 2


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
                "scope": "per_test",
                "start_line": i,
                "end_line": i + 1,
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
            }
            base.update(overrides)
            insert_fixture(conn, base)


def _make_multi_repo_fixtures_db(tmp_path, repos: list[list[str]]) -> None:
    """db/a.db with one repo per entry in `repos`, each a list of
    fixture_type values for that repo's fixtures -- for testing per-repo
    grouping (fetch_categorical_column_by_repo()), unlike _make_fixtures_db()
    above which puts everything under a single repo."""
    db_file = tmp_path / "a.db"
    initialise_db(db_file)
    with db_session(db_file) as conn:
        for repo_idx, fixture_types in enumerate(repos):
            repo_id, _ = upsert_repository(
                conn,
                {
                    "github_id": repo_idx + 1,
                    "full_name": f"owner/repo{repo_idx}",
                    "language": "python",
                    "stars": 1,
                    "forks": 0,
                    "description": "",
                    "topics": "[]",
                    "created_at": "2019-01-01T00:00:00Z",
                    "pushed_at": "2020-01-01T00:00:00Z",
                    "clone_url": f"https://github.com/owner/repo{repo_idx}.git",
                    "num_contributors": 1,
                    "domain": None,
                    "repo_age_years": None,
                },
            )
            file_id = upsert_test_file(conn, repo_id, "tests/test_foo.py", "python")
            for i, fixture_type in enumerate(fixture_types):
                insert_fixture(
                    conn,
                    {
                        "file_id": file_id,
                        "repo_id": repo_id,
                        "name": f"fixture_{repo_idx}_{i}",
                        "fixture_type": fixture_type,
                        "scope": "per_test",
                        "start_line": i,
                        "end_line": i + 1,
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


class TestFetchCategoricalColumnByRepo:
    def test_groups_counts_by_repo_id(self, tmp_path):
        _make_multi_repo_fixtures_db(
            tmp_path,
            [
                ["pytest_decorator", "pytest_decorator", "before_each"],
                ["before_each"],
            ],
        )
        db_file = tmp_path / "a.db"
        with db_session(db_file) as conn:
            by_repo = fetch_categorical_column_by_repo(conn, "fixtures", "fixture_type")
        assert len(by_repo) == 2
        assert {"pytest_decorator": 2, "before_each": 1} in by_repo.values()
        assert {"before_each": 1} in by_repo.values()

    def test_empty_table_returns_empty_dict(self, tmp_path):
        db_file = tmp_path / "a.db"
        initialise_db(db_file)
        with db_session(db_file) as conn:
            assert fetch_categorical_column_by_repo(conn, "fixtures", "fixture_type") == {}


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


class TestRepoLevelCategoryProportions:
    def test_one_proportion_per_repo(self):
        by_repo = {
            1: {"setup": 3, "teardown": 1},  # 3/4
            2: {"setup": 1, "teardown": 1},  # 1/2
        }
        assert sorted(repo_level_category_proportions(by_repo, "setup")) == [0.5, 0.75]

    def test_category_absent_in_a_repo_counts_as_zero_not_skipped(self):
        by_repo = {1: {"setup": 2, "teardown": 2}, 2: {"teardown": 5}}
        assert repo_level_category_proportions(by_repo, "setup") == [0.5, 0.0]

    def test_repo_with_no_classified_rows_is_skipped_not_zero(self):
        """An empty {repo: {}} (zero total) is a missing ratio, not a 0.0
        one -- must not silently pull the comparison toward 0."""
        by_repo = {1: {"setup": 1}, 2: {}}
        assert repo_level_category_proportions(by_repo, "setup") == [1.0]

    def test_empty_input_returns_empty_list(self):
        assert repo_level_category_proportions({}, "setup") == []

    def test_a_repo_with_many_fixtures_still_contributes_one_value(self):
        """The categorical analogue of repo_level_means()'s equivalent
        test: a repo with 1000 classified rows must count once."""
        by_repo = {1: {"setup": 900, "teardown": 100}, 2: {"setup": 1}}
        assert len(repo_level_category_proportions(by_repo, "setup")) == 2


class TestCompareCategoricalRepoLevel:
    def test_one_balance_test_per_category_seen_on_either_side(self):
        a_by_repo = {1: {"setup": 5, "teardown": 5}}
        other_by_repo = {2: {"setup": 3, "other": 7}}
        results = compare_categorical_repo_level(a_by_repo, other_by_repo, "fixture_type_kind")
        assert set(results.keys()) == {"setup", "teardown", "other"}

    def test_declusters_a_prolific_repo(self):
        """Core value proposition, mirrored from repo_level_means()'s repo-
        declustering: one repo with 1000 "setup"-heavy fixtures must not
        outweigh a second repo with a handful, once compared per-repo."""
        a_by_repo = {
            1: {"setup": 900, "teardown": 100},  # 0.9
            2: {"setup": 1, "teardown": 9},  # 0.1
        }
        other_by_repo = {3: {"setup": 5, "teardown": 5}, 4: {"setup": 4, "teardown": 6}}  # 0.5, 0.4
        result = compare_categorical_repo_level(a_by_repo, other_by_repo, "fixture_type_kind")
        t = result["setup"]
        # A's per-repo proportions [0.9, 0.1] (median 0.5) vs other's
        # [0.5, 0.4] (median 0.45) -- close, not a stark difference, unlike
        # what a fixture-level pooled count (901/1901 vs 9/20) would show.
        assert t.is_balanced

    def test_empty_input_returns_empty_dict(self):
        assert compare_categorical_repo_level({}, {}, "fixture_type_kind") == {}


class TestRepoLevelCategoryNCounts:
    def test_counts_repos_with_a_nonzero_total_only(self):
        a_by_repo = {1: {"setup": 5, "teardown": 0}, 2: {}}  # repo 2 has zero total -> excluded
        other_by_repo = {3: {"setup": 1}, 4: {"setup": 2}, 5: {"setup": 3}}
        n = repo_level_category_n_counts(a_by_repo, other_by_repo)
        assert n == NCounts(n_a=1, n_c=3)

    def test_empty_input_gives_zero_counts(self):
        assert repo_level_category_n_counts({}, {}) == NCounts(n_a=0, n_c=0)


class TestRenderCategoricalRepoLevelTable:
    def test_renders_one_row_per_category(self):
        a_by_repo = {1: {"setup": 9, "teardown": 1}}
        other_by_repo = {2: {"setup": 1, "teardown": 9}}
        results = compare_categorical_repo_level(a_by_repo, other_by_repo, "fixture_type_kind")
        n = repo_level_category_n_counts(a_by_repo, other_by_repo)
        rendered = render_categorical_repo_level_table(results, "c", n)
        assert "| setup |" in rendered
        assert "| teardown |" in rendered

    def test_n_column_shown_for_every_row(self):
        a_by_repo = {1: {"setup": 9, "teardown": 1}}
        other_by_repo = {2: {"setup": 1, "teardown": 9}, 3: {"setup": 2, "teardown": 8}}
        results = compare_categorical_repo_level(a_by_repo, other_by_repo, "fixture_type_kind")
        n = repo_level_category_n_counts(a_by_repo, other_by_repo)
        rendered = render_categorical_repo_level_table(results, "c", n)
        setup_line = next(line for line in rendered.splitlines() if line.startswith("| setup |"))
        assert "| 1 | 2 |" in setup_line  # n_A=1, n_C=2

    def test_proportions_rendered_as_percentages(self):
        a_by_repo = {1: {"setup": 3, "teardown": 1}}  # 75%
        other_by_repo = {2: {"setup": 1, "teardown": 3}}  # 25%
        results = compare_categorical_repo_level(a_by_repo, other_by_repo, "fixture_type_kind")
        n = repo_level_category_n_counts(a_by_repo, other_by_repo)
        rendered = render_categorical_repo_level_table(results, "c", n)
        setup_line = next(line for line in rendered.splitlines() if line.startswith("| setup |"))
        assert "75.0%" in setup_line
        assert "25.0%" in setup_line

    def test_p_values_rendered_exactly_not_as_significant_yes_no(self):
        a_by_repo = {1: {"setup": 9, "teardown": 1}}
        other_by_repo = {2: {"setup": 1, "teardown": 9}}
        results = compare_categorical_repo_level(a_by_repo, other_by_repo, "fixture_type_kind")
        n = repo_level_category_n_counts(a_by_repo, other_by_repo)
        rendered = render_categorical_repo_level_table(results, "c", n)
        assert "significant (p<0.05)" not in rendered
        assert " (yes)" not in rendered and " (no)" not in rendered

    def test_no_categories_renders_placeholder_row(self):
        rendered = render_categorical_repo_level_table({}, "c", NCounts(0, 0))
        assert "_(no categories)_" in rendered

    def test_insufficient_data_marked_per_category(self):
        # other_by_repo's only repo has zero classified rows for this
        # variable at all -> its proportion list is empty (not a 0.0 value)
        # -> compute_continuous_balance()'s insufficient_data path.
        a_by_repo = {1: {"setup": 5}}
        other_by_repo = {2: {}}
        results = compare_categorical_repo_level(a_by_repo, other_by_repo, "fixture_type_kind")
        n = repo_level_category_n_counts(a_by_repo, other_by_repo)
        rendered = render_categorical_repo_level_table(results, "c", n)
        setup_line = next(line for line in rendered.splitlines() if line.startswith("| setup |"))
        assert "_insufficient data_" in setup_line


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
        branch across rq1-3/balance.py (which only guards against
        insufficient_data/error, not this reason) hits a KeyError reading
        it. Real regression: reproduced via rq2.py's
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
        overall = BalanceTest(variable="commit_type", test_type="chi-square", p_value=0.5, is_balanced=True)
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
