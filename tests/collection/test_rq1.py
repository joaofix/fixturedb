"""Tests for collection/research_questions/rq1.py.

Builds tiny synthetic db/{dataset}.db files under tmp_path (via the real
schema, initialise_db()) and checks the loading, summary-statistics, and
report-rendering logic -- never touching the real db/ or research_questions/
directories. The Mann-Whitney U / chi-square math itself is already covered
by tests/between_group/test_between_group_comparison.py; these tests focus
on rq1.py's own wiring: SQL aggregation, missing-db handling, and markdown
rendering (including the "insufficient data" fallback path).
"""

from __future__ import annotations

from collection import paths
from collection.db import (
    db_session,
    initialise_db,
    insert_fixture,
    upsert_repository,
    upsert_test_file,
)
from collection.research_questions._shared import format_p_value
from collection.research_questions.rq1 import (
    CONTINUOUS_METRICS,
    PAPER_CONTINUOUS_METRICS,
    DatasetMetrics,
    _floor_percentage,
    compare_datasets_repo_level,
    compare_datasets_repo_level_median_diagnostic,
    generate_report,
    load_dataset_metrics,
    write_report,
)


def _make_multi_repo_db(root, dataset: str, repos: list[list[float]]) -> None:
    """Create db/{dataset}.db with one repo per entry in `repos`, each
    entry a list of `loc` values for that repo's fixtures.

    Dataset "c" writes to c_sampled.db instead of the full c.db --
    research_questions/ reads Dataset C's fixture-level sample-down, see
    _shared.py::require_db_or_none()'s docstring."""
    db_file = (root / "c_sampled.db") if dataset == "c" else paths.db_path(dataset, root=root)
    initialise_db(db_file)
    with db_session(db_file) as conn:
        for repo_idx, loc_values in enumerate(repos):
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
            for i, loc in enumerate(loc_values):
                insert_fixture(
                    conn,
                    {
                        "file_id": file_id,
                        "repo_id": repo_id,
                        "name": f"fixture_{repo_idx}_{i}",
                        "fixture_type": "pytest_decorator",
                        "start_line": i,
                        "end_line": i + 1,
                        "loc": loc,
                        "cyclomatic_complexity": 1,
                        "num_comment_lines": 0,
                        "comment_density": 0.0,
                        "num_parameters": 0,
                        "raw_source": "",
                        "num_mocks": 0,
                    },
                )


def _make_db(root, dataset: str, fixtures: list[dict]) -> None:
    """Create db/{dataset}.db under `root` with one repo/file and `fixtures` rows.

    Each dict in `fixtures` may override any of the base columns below
    (loc, cyclomatic_complexity, fixture_type, ...).

    Dataset "c" writes to c_sampled.db instead of the full c.db --
    research_questions/ reads Dataset C's fixture-level sample-down, see
    _shared.py::require_db_or_none()'s docstring.
    """
    db_file = (root / "c_sampled.db") if dataset == "c" else paths.db_path(dataset, root=root)
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
        for i, overrides in enumerate(fixtures):
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


def _make_multi_language_db(root, dataset: str, files: list[dict]) -> None:
    """Create db/{dataset}.db with one repo and one test_file per `files`
    entry -- each entry: {"language": str, "fixtures": [fixture_dict, ...]}.
    Lets a single repo contribute fixtures in more than one language, for
    testing language-stratified aggregation (fixture_type_by_language).

    Dataset "c" writes to c_sampled.db instead of the full c.db --
    research_questions/ reads Dataset C's fixture-level sample-down, see
    _shared.py::require_db_or_none()'s docstring."""
    db_file = (root / "c_sampled.db") if dataset == "c" else paths.db_path(dataset, root=root)
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
        for file_idx, file_spec in enumerate(files):
            language = file_spec["language"]
            file_id = upsert_test_file(
                conn, repo_id, f"tests/test_{file_idx}.{language}", language
            )
            for i, overrides in enumerate(file_spec["fixtures"]):
                base = {
                    "file_id": file_id,
                    "repo_id": repo_id,
                    "name": f"fixture_{file_idx}_{i}",
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


class TestPaperMetricsTiering:
    """PAPER_CONTINUOUS_METRICS is the exhaustive, final continuous set --
    exactly loc/cyclomatic_complexity/comment_density. max_nesting_depth
    (which used to be Mann-Whitney tested but rendered under a separate
    "Other Extracted Features" tier) was dropped from the extracted metric
    set entirely, so CONTINUOUS_METRICS is now identical to it -- there is
    no more "other" continuous tier."""

    def test_paper_continuous_metrics_is_exactly_three(self):
        assert PAPER_CONTINUOUS_METRICS == ["loc", "cyclomatic_complexity", "comment_density"]

    def test_continuous_metrics_equals_paper_metrics(self):
        assert CONTINUOUS_METRICS == PAPER_CONTINUOUS_METRICS


class TestFloorPercentage:
    def test_computes_fraction_at_floor(self):
        assert _floor_percentage([1, 1, 2, 3], 1) == 0.5

    def test_none_at_floor_returns_zero_not_none(self):
        assert _floor_percentage([2, 3, 4], 1) == 0.0

    def test_empty_returns_none(self):
        assert _floor_percentage([], 1) is None


class TestLoadDatasetMetrics:
    def test_missing_db_returns_none(self, tmp_path):
        assert load_dataset_metrics("a", db_root=tmp_path) is None

    def test_loads_continuous_and_categorical_values(self, tmp_path):
        _make_db(
            tmp_path,
            "a",
            [
                {"loc": 3, "fixture_type": "before_each"},
                {"loc": 7, "fixture_type": "before_each"},
                {"loc": 5, "fixture_type": "after_each"},
            ],
        )
        metrics = load_dataset_metrics("a", db_root=tmp_path)
        assert isinstance(metrics, DatasetMetrics)
        assert metrics.n_fixtures == 3
        assert sorted(metrics.continuous_raw["loc"]) == [3, 5, 7]
        assert metrics.categorical["fixture_type"] == {"before_each": 2, "after_each": 1}

    def test_loads_agent_type_distribution(self, tmp_path):
        _make_db(
            tmp_path,
            "a",
            [
                {"loc": 1, "agent_type": "claude"},
                {"loc": 1, "agent_type": "claude"},
                {"loc": 1, "agent_type": "copilot"},
            ],
        )
        metrics = load_dataset_metrics("a", db_root=tmp_path)
        assert metrics.agent_type_distribution == {"claude": 2, "copilot": 1}

    def test_repo_level_continuous_by_language_is_one_mean_per_repo_per_language(self, tmp_path):
        _make_multi_language_db(
            tmp_path,
            "a",
            [{"language": "python", "fixtures": [{"loc": 10}, {"loc": 20}]}],
        )
        metrics = load_dataset_metrics("a", db_root=tmp_path)
        # One repo contributing 2 python fixtures -> one repo-level mean (15.0).
        assert metrics.repo_level_continuous_by_language["loc"] == {"python": [15.0]}

    def test_no_body_fixture_types_excluded_from_continuous_metrics_only(self, tmp_path):
        """junit_rule/junit_class_rule (NO_BODY_FIXTURE_TYPES) must not
        contribute to loc/cyclomatic_complexity/comment_density's repo-level
        means (Lizard can't analyze a field declaration -- see
        _shared.py::NO_BODY_FIXTURE_TYPES; comment_density is loc-derived
        and excluded for the same "different kind of code unit" reasoning,
        not because of Lizard specifically), but num_parameters (0 is a
        genuinely correct value for a field, not a Lizard fallback) and the
        fixture_type categorical distribution must still include them."""
        _make_multi_language_db(
            tmp_path,
            "a",
            [
                {
                    "language": "java",
                    "fixtures": [
                        {
                            "fixture_type": "junit_rule",
                            "loc": 2,
                            "cyclomatic_complexity": 1,
                            "num_parameters": 0,
                            "comment_density": 0.9,
                        },
                        {
                            "fixture_type": "junit4_before",
                            "loc": 10,
                            "cyclomatic_complexity": 3,
                            "num_parameters": 2,
                            "comment_density": 0.2,
                        },
                        {
                            "fixture_type": "junit4_before",
                            "loc": 10,
                            "cyclomatic_complexity": 3,
                            "num_parameters": 2,
                            "comment_density": 0.2,
                        },
                    ],
                }
            ],
        )
        metrics = load_dataset_metrics("a", db_root=tmp_path)

        # One repo -- its loc/cc/comment_density means exclude the
        # junit_rule fixture entirely (mean of the two junit4_before
        # fixtures only: loc 10.0, not (2+10+10)/3=7.33; cc 3.0, not 1.67;
        # comment_density 0.2, not (0.9+0.2+0.2)/3=0.433).
        assert metrics.repo_level_continuous["loc"] == [10.0]
        assert metrics.repo_level_continuous["cyclomatic_complexity"] == [3.0]
        assert metrics.repo_level_continuous["comment_density"] == [0.2]
        assert metrics.repo_level_continuous_by_language["loc"] == {"java": [10.0]}

        # num_parameters is NOT excluded -- mean includes all 3 fixtures.
        assert round(metrics.repo_level_continuous["num_parameters"][0], 4) == round(4 / 3, 4)

        # Diagnostic-only median-per-repo view (NOT the paper's methodology
        # -- see this module's docstring): restricted to CONTINUOUS_METRICS,
        # so it exists for loc/cc/comment_density but not num_parameters.
        # Same exclusion applies -- junit_rule is still dropped, and the
        # remaining two junit4_before fixtures are identical, so the median
        # equals the mean here too (loc 10.0, cc 3.0, comment_density 0.2).
        assert metrics.repo_level_continuous_median_diagnostic["loc"] == [10.0]
        assert metrics.repo_level_continuous_median_diagnostic["cyclomatic_complexity"] == [3.0]
        assert metrics.repo_level_continuous_median_diagnostic["comment_density"] == [0.2]
        assert "num_parameters" not in metrics.repo_level_continuous_median_diagnostic

        # fixture_type categorical distribution still counts junit_rule.
        assert metrics.categorical["fixture_type"]["junit_rule"] == 1
        assert metrics.categorical["fixture_type"]["junit4_before"] == 2

    def test_floor_pct_computed_for_num_parameters_only(self, tmp_path):
        _make_db(
            tmp_path,
            "a",
            [
                {"cyclomatic_complexity": 1, "num_parameters": 0},
                {"cyclomatic_complexity": 1, "num_parameters": 2},
                {"cyclomatic_complexity": 3, "num_parameters": 0},
                {"cyclomatic_complexity": 3, "num_parameters": 0},
            ],
        )
        metrics = load_dataset_metrics("a", db_root=tmp_path)
        assert metrics.floor_pct["num_parameters"] == 0.75  # 3 of 4 at 0 params
        # cyclomatic_complexity moved back to a tested metric -- no floor_pct
        # entry for it anymore.
        assert "cyclomatic_complexity" not in metrics.floor_pct


class TestGenerateReport:
    def test_missing_all_dbs_notes_unavailable_without_crashing(self, tmp_path):
        report = generate_report(db_root=tmp_path)
        assert "Dataset A not available" in report
        assert "Not available -- db not collected yet." in report

    def test_dataset_a_only_renders_summary_and_skips_comparisons(self, tmp_path):
        _make_db(tmp_path, "a", [{"loc": 3}, {"loc": 7}])
        report = generate_report(db_root=tmp_path)
        assert "Dataset A (agent-authored) -- 2 fixtures" in report
        assert "## A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)" in report
        # C summary, A-vs-C comparison: 2 total.
        assert report.count("Not available -- db not collected yet.") == 2

    def test_dataset_summary_includes_language_leakage_table(self, tmp_path):
        """_make_db's repo and its one test_file both use "python", so this
        is a no-leakage wiring check -- compute_language_leakage() itself is
        covered against real leaked data in
        test_research_questions_shared.py."""
        _make_db(tmp_path, "a", [{"loc": 3}])
        report = generate_report(db_root=tmp_path)
        assert "Cross-language fixture leakage" in report
        assert "0/1 fixtures (0.00%) leaked." in report

    def test_dataset_summary_includes_agent_type_distribution(self, tmp_path):
        _make_db(
            tmp_path, "a", [{"loc": 1, "agent_type": "claude"}, {"loc": 1, "agent_type": "copilot"}]
        )
        report = generate_report(db_root=tmp_path)
        assert "**agent_type distribution**" in report
        assert "| claude | 1 | 50.0% |" in report
        assert "| copilot | 1 | 50.0% |" in report

    def test_a_vs_c_comparison_renders_significant_difference(self, tmp_path):
        """Sharply different LOC distributions -> Mann-Whitney's Overall
        row (repo-level, per the last task) should show a large effect and
        a small exact p-value. This db has one repo per side (_make_db),
        so the repo-level Overall row collapses to n=1 vs n=1 -- always
        p=1.000 (an n=1-vs-n=1 Mann-Whitney can never reject), so this
        checks the effect-size/formatting machinery, not significance."""
        _make_db(tmp_path, "a", [{"loc": v} for v in [1, 1, 2, 1, 2, 1, 2, 1, 2, 1]])
        _make_db(tmp_path, "c", [{"loc": v} for v in [50, 60, 55, 58, 62, 57, 59, 61, 56, 54]])
        report = generate_report(db_root=tmp_path)
        loc_section = report.split("### loc")[1].split("### cyclomatic_complexity")[0]
        overall_line = next(
            line for line in loc_section.splitlines() if line.startswith("| Overall |")
        )
        assert "| 1 | 1 |" in overall_line  # one repo per side
        assert "large | 1.000" in overall_line
        assert overall_line.rstrip("|").rsplit("|", 1)[-1].strip() == "--"  # never BH-corrected

    def test_paper_continuous_tables_report_per_language_medians(self, tmp_path):
        """loc/cyclomatic_complexity/comment_density's per-language rows
        get "A median"/"C median" columns -- the median of the same
        per-repo mean values the Mann-Whitney test itself runs on. One
        repo per side (_make_db), so the per-repo mean *is* the "median"
        here (a 1-element list's median is that element)."""
        _make_db(tmp_path, "a", [{"loc": v} for v in [2, 4, 6]])  # mean 4.0
        _make_db(tmp_path, "c", [{"loc": v} for v in [10, 20]])  # mean 15.0
        report = generate_report(db_root=tmp_path)
        loc_section = report.split("### loc")[1].split("### cyclomatic_complexity")[0]
        header = next(line for line in loc_section.splitlines() if line.startswith("| Language"))
        assert "A median" in header
        assert "C median" in header
        python_line = next(
            line for line in loc_section.splitlines() if line.startswith("| python |")
        )
        assert "| python | 1 | 1 | 4.00 | 15.00 |" in python_line

    def test_paper_continuous_overall_row_has_dashed_medians(self, tmp_path):
        _make_db(tmp_path, "a", [{"loc": v} for v in [2, 4, 6]])
        _make_db(tmp_path, "c", [{"loc": v} for v in [10, 20]])
        report = generate_report(db_root=tmp_path)
        loc_section = report.split("### loc")[1].split("### cyclomatic_complexity")[0]
        overall_line = next(
            line for line in loc_section.splitlines() if line.startswith("| Overall |")
        )
        assert "| Overall | 1 | 1 | -- | -- | -- | -- | -- | -- |" in overall_line

    def test_paper_continuous_tables_report_per_language_q3_and_p90(self, tmp_path):
        """Q3/P90 use the exact same per-repo means the median column and
        the Mann-Whitney test itself use -- multiple repos per side here
        (unlike the median test above) so Q3/P90 actually differ from the
        median, proving they're real percentiles, not just an alias for
        it."""
        _make_multi_repo_db(tmp_path, "a", [[1], [2], [3], [4]])  # repo means 1,2,3,4
        _make_multi_repo_db(tmp_path, "c", [[10], [20], [30], [40]])  # repo means 10,20,30,40
        report = generate_report(db_root=tmp_path)
        loc_section = report.split("### loc")[1].split("### cyclomatic_complexity")[0]
        header = next(line for line in loc_section.splitlines() if line.startswith("| Language"))
        assert header.index("A median") < header.index("A Q3") < header.index("A P90")
        python_line = next(
            line for line in loc_section.splitlines() if line.startswith("| python |")
        )
        assert (
            "| python | 4 | 4 | 2.50 | 25.00 | 3.25 | 32.50 | 3.70 | 37.00 |" in python_line
        )

    def test_repo_level_aggregate_declusters_a_prolific_repo(self, tmp_path):
        """The core value proposition: a single repo contributing many
        fixtures must not be allowed to dominate the comparison. Dataset A
        here is one repo with 100 fixtures at loc=100 plus one repo with a
        single loc=1 fixture -- fixture-level, the mean is ~99 (dominated
        by the prolific repo). Dataset C is two repos each with one
        loc=50 fixture. Repo-level, A's per-repo means are [100.0, 1.0]
        (mean 50.5) -- much closer to C's 50 than the fixture-level view
        would suggest, and NOT a significant Mann-Whitney difference,
        unlike the fixture-level comparison over the same data."""
        _make_multi_repo_db(tmp_path, "a", [[100.0] * 100, [1.0]])
        _make_multi_repo_db(tmp_path, "c", [[50.0], [50.0]])

        a_metrics = load_dataset_metrics("a", db_root=tmp_path)
        c_metrics = load_dataset_metrics("c", db_root=tmp_path)

        assert sorted(a_metrics.repo_level_continuous["loc"]) == [1.0, 100.0]

        fixture_level = a_metrics.continuous_raw["loc"]
        assert sum(fixture_level) / len(fixture_level) > 95  # dominated by the prolific repo

        repo_level_result = compare_datasets_repo_level(a_metrics, c_metrics)
        t = repo_level_result["loc"]
        assert t.is_balanced  # not significant once each repo counts once

        # loc's Overall row (main "### loc" section) IS the repo-level test
        # now -- there's no separate fixture-level continuous table left to
        # be misled by, and no separate repo-level-only section either.
        report = generate_report(db_root=tmp_path)
        loc_section = report.split("### loc")[1].split("### cyclomatic_complexity")[0]
        overall_line = next(
            line for line in loc_section.splitlines() if line.startswith("| Overall |")
        )
        assert "| 2 | 2 |" in overall_line  # 2 repos per side, not 101 fixtures
        assert format_p_value(t.p_value) in overall_line

    def test_median_diagnostic_uses_per_repo_median_not_mean(self, tmp_path):
        """compare_datasets_repo_level_median_diagnostic() must aggregate
        each repo by its own MEDIAN fixture, not its mean -- the whole
        point of keeping this diagnostic-only view separate from the
        paper's actual compare_datasets_repo_level(). A's one repo has loc
        values [1, 2, 100]: mean 34.33 (pulled toward the 100 outlier),
        median 2. C's one repo is a single loc=2 fixture. Under the
        paper's mean-per-repo methodology the two datasets look very
        different (34.33 vs 2); under the diagnostic median-per-repo view
        they look identical (2 vs 2) -- exactly the kind of information
        loss this module's docstring warns the diagnostic view can
        introduce, which is why it's presented as unusable rather than a
        competing result."""
        _make_db(tmp_path, "a", [{"loc": v} for v in [1, 2, 100]])
        _make_db(tmp_path, "c", [{"loc": 2}])

        a_metrics = load_dataset_metrics("a", db_root=tmp_path)
        c_metrics = load_dataset_metrics("c", db_root=tmp_path)

        assert round(a_metrics.repo_level_continuous["loc"][0], 4) == round(103 / 3, 4)
        assert a_metrics.repo_level_continuous_median_diagnostic["loc"] == [2.0]
        assert c_metrics.repo_level_continuous["loc"] == [2.0]
        assert c_metrics.repo_level_continuous_median_diagnostic["loc"] == [2.0]

        diagnostic = compare_datasets_repo_level_median_diagnostic(a_metrics, c_metrics)
        assert diagnostic["loc"].is_balanced  # identical once median-aggregated
        assert diagnostic["loc"].variable == "loc_median_diagnostic"

    def test_report_includes_median_diagnostic_section_with_disclaimer(self, tmp_path):
        """The report must render the diagnostic median-per-repo section,
        clearly separated from and after the paper's actual Paper Metrics
        section, with a disclaimer that it is not a result to cite."""
        _make_db(tmp_path, "a", [{"loc": v} for v in [1, 2, 100]])
        _make_db(tmp_path, "c", [{"loc": 2}])
        report = generate_report(db_root=tmp_path)

        assert "## Diagnostic: median-per-repo aggregation (NOT used in the paper)" in report
        assert report.index("**Paper Metrics -- Continuous**") < report.index(
            "## Diagnostic: median-per-repo aggregation"
        )
        disclaimer_section = report.split(
            "## Diagnostic: median-per-repo aggregation (NOT used in the paper)"
        )[1]
        assert "not results, do not cite them" in disclaimer_section
        assert "### loc" in disclaimer_section
        assert "### cyclomatic_complexity" in disclaimer_section
        assert "### comment_density" in disclaimer_section

    def test_dataset_summary_continuous_table_is_repo_level_not_fixture_level(
        self, tmp_path
    ):
        """The per-dataset "Continuous metrics" table (_render_dataset_summary())
        must read the same repo-level-means data the comparison tests use,
        not the raw per-fixture values -- same prolific-repo setup as
        test_repo_level_aggregate_declusters_a_prolific_repo above: one repo
        with 100 loc=100 fixtures plus one repo with a single loc=1 fixture.
        Fixture-level, the median is 100 (dominated by the prolific repo's
        100 identical values). Repo-level, the two repos' own means are
        [100.0, 1.0] -- median 50.50, nothing close to the fixture-level
        figure."""
        _make_multi_repo_db(tmp_path, "a", [[100.0] * 100, [1.0]])

        report = generate_report(db_root=tmp_path)
        summary = report.split("### Dataset A")[1].split("###")[0]
        loc_line = next(
            line for line in summary.splitlines() if line.startswith("| loc |")
        )
        assert "| loc | 2 | 50.50 | 50.50 | 1 | 100 |" in loc_line
        assert "100.00" not in loc_line  # the fixture-level median/mean

    def test_num_parameters_has_no_mann_whitney_section(self, tmp_path):
        _make_db(tmp_path, "a", [{"loc": 1}])
        _make_db(tmp_path, "c", [{"loc": 1}])
        report = generate_report(db_root=tmp_path)
        assert "### num_parameters" not in report

    def test_cyclomatic_complexity_has_a_mann_whitney_section(self, tmp_path):
        """Regression: cyclomatic_complexity was dropped from testing, then
        restored -- must have a real Overall row again, same shape as
        loc/comment_density, not just a floor-percentage footnote entry.
        Boundary is "### comment_density", the next (and last) Paper
        Metric."""
        _make_db(tmp_path, "a", [{"cyclomatic_complexity": v} for v in [1, 1, 2, 1, 2, 1, 2, 1, 2, 1]])
        _make_db(tmp_path, "c", [{"cyclomatic_complexity": v} for v in [5, 6, 5, 5, 6, 5, 6, 5, 6, 5]])
        report = generate_report(db_root=tmp_path)
        assert "### cyclomatic_complexity" in report
        cc_section = report.split("### cyclomatic_complexity")[1].split("### comment_density")[0]
        overall_line = next(
            line for line in cc_section.splitlines() if line.startswith("| Overall |")
        )
        assert "| 1 | 1 |" in overall_line  # one repo per side
        assert "large | 1.000" in overall_line

    def test_floor_percentage_footnote_renders(self, tmp_path):
        _make_db(
            tmp_path,
            "a",
            [
                {"cyclomatic_complexity": 1, "num_parameters": 0},
                {"cyclomatic_complexity": 3, "num_parameters": 2},
            ],
        )
        _make_db(
            tmp_path,
            "c",
            [
                {"cyclomatic_complexity": 1, "num_parameters": 0},
                {"cyclomatic_complexity": 1, "num_parameters": 0},
            ],
        )
        report = generate_report(db_root=tmp_path)
        assert "Floor-binding check (descriptive only" in report
        # The footnote renders in the "Other Extracted Features" section,
        # after the Paper Metrics section (loc/cyclomatic_complexity/
        # comment_density) -- boundary is "**Categorical metrics" (the
        # next heading), not "### loc" (which now precedes the footnote).
        footnote_section = report.split("Floor-binding check (descriptive only")[1].split(
            "**Categorical metrics"
        )[0]
        params_line = next(
            line for line in footnote_section.splitlines()
            if line.startswith("| num_parameters |")
        )
        assert "| num_parameters | 0 | 50.0% | 100.0% |" in params_line
        # cyclomatic_complexity moved back to a tested metric -- no footnote
        # row for it anymore.
        assert not any(
            line.startswith("| cyclomatic_complexity |")
            for line in footnote_section.splitlines()
        )

    def test_comment_density_has_a_mann_whitney_section_in_paper_metrics(self, tmp_path):
        """comment_density is the third paper metric (2026-08-17) -- must
        render a real Overall row, positioned inside "Paper Metrics"
        (before "Other Extracted Features"), not just be a descriptive-only
        column."""
        _make_db(
            tmp_path, "a",
            [{"comment_density": v} for v in [0.1, 0.1, 0.2, 0.1, 0.2, 0.1, 0.2, 0.1, 0.2, 0.1]],
        )
        _make_db(
            tmp_path, "c",
            [{"comment_density": v} for v in [0.8, 0.9, 0.8, 0.8, 0.9, 0.8, 0.9, 0.8, 0.9, 0.8]],
        )
        report = generate_report(db_root=tmp_path)
        assert "### comment_density" in report
        assert report.index("**Paper Metrics") < report.index("### comment_density")
        assert report.index("### comment_density") < report.index("**Other Extracted Features")
        cd_section = report.split("### comment_density")[1].split(
            "**Other Extracted Features"
        )[0]
        overall_line = next(
            line for line in cd_section.splitlines() if line.startswith("| Overall |")
        )
        assert "| 1 | 1 |" in overall_line  # one repo per side
        assert "large | 1.000" in overall_line

    def test_paper_and_other_continuous_summary_tables_split_in_per_dataset_section(
        self, tmp_path
    ):
        """The per-dataset "Continuous metrics" table (median/mean/etc.) is
        split into a "Paper" table (loc/cyclomatic_complexity/
        comment_density) and an "Other (not in the paper)" table
        (num_parameters only, now that max_nesting_depth has been dropped
        entirely), not one combined table."""
        _make_db(tmp_path, "a", [{"loc": 5}])
        report = generate_report(db_root=tmp_path)
        summary = report.split("### Dataset A")[1].split("###")[0]
        assert "**Continuous metrics -- Paper**" in summary
        assert "**Continuous metrics -- Other (not in the paper)**" in summary
        paper_table = summary.split("**Continuous metrics -- Paper**")[1].split(
            "**Continuous metrics -- Other"
        )[0]
        other_table = summary.split("**Continuous metrics -- Other")[1]
        assert "| loc |" in paper_table
        assert "| cyclomatic_complexity |" in paper_table
        assert "| comment_density |" in paper_table
        assert "| num_parameters |" in other_table
        assert "| loc |" not in other_table


class TestWriteReport:
    def test_writes_file_matching_generate_report(self, tmp_path):
        _make_db(tmp_path, "a", [{"loc": 4}])
        out_dir = tmp_path / "out"
        path = write_report(out_dir, db_root=tmp_path)
        assert path == out_dir / "rq1.md"
        assert path.read_text() == generate_report(db_root=tmp_path)
