"""Tests for collection/research_questions/rq4.py.

Builds tiny synthetic db/{dataset}.db files under tmp_path (via the real
schema, initialise_db()) and checks mock-metric loading, per-language
breakdowns, and report rendering -- never touching the real db/ or
research_questions/ directories. The Mann-Whitney U / chi-square math itself
is already covered by tests/between_group/test_between_group_comparison.py.
"""

from __future__ import annotations

from collection import paths
from collection.db import (
    db_session,
    initialise_db,
    insert_fixture,
    insert_mock_usage,
    upsert_repository,
    upsert_test_file,
)
from collection.research_questions.rq4 import (
    DatasetMetrics,
    _mocking_coverage_indicators,
    _render_mock_counts_table,
    _render_mocking_summary_table,
    compare_datasets_repo_level,
    generate_report,
    load_dataset_metrics,
    write_report,
)


def _make_multi_repo_db(root, dataset: str, repos: list[list[float]]) -> None:
    """Create db/{dataset}.db with one repo per entry in `repos`, each
    entry a list of `num_mocks` values for that repo's fixtures.

    Dataset "c" writes to c_sampled.db instead of the full c.db --
    research_questions/ reads Dataset C's fixture-level sample-down, see
    _shared.py::require_db_or_none()'s docstring."""
    db_file = (root / "c_sampled.db") if dataset == "c" else paths.db_path(dataset, root=root)
    initialise_db(db_file)
    with db_session(db_file) as conn:
        for repo_idx, num_mocks_values in enumerate(repos):
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
            for i, num_mocks in enumerate(num_mocks_values):
                insert_fixture(
                    conn,
                    {
                        "file_id": file_id,
                        "repo_id": repo_id,
                        "name": f"fixture_{repo_idx}_{i}",
                        "fixture_type": "pytest_decorator",
                        "scope": "per_test",
                        "start_line": i,
                        "end_line": i + 1,
                        "loc": 3,
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
                        "num_mocks": num_mocks,
                    },
                )


def _make_db(root, dataset: str, files: list[dict]) -> None:
    """Create db/{dataset}.db under `root` with one repo and one test_file
    per entry in `files`.

    Each `files` entry: {"language": str, "fixtures": [fixture_spec, ...]}.
    Each fixture_spec: {"overrides": {...fixture column overrides...},
    "mocks": [mock_override_dict, ...]} -- both keys optional.

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
        for file_idx, file_spec in enumerate(files):
            language = file_spec["language"]
            file_id = upsert_test_file(conn, repo_id, f"tests/test_{file_idx}.{language}", language)
            for i, fixture_spec in enumerate(file_spec.get("fixtures", [])):
                base = {
                    "file_id": file_id,
                    "repo_id": repo_id,
                    "name": f"fixture_{file_idx}_{i}",
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
                base.update(fixture_spec.get("overrides", {}))
                fixture_id = insert_fixture(conn, base)
                for mock_overrides in fixture_spec.get("mocks", []):
                    mock = {
                        "fixture_id": fixture_id,
                        "repo_id": repo_id,
                        "framework": "unittest_mock",
                        "category": "mock",
                        "target_identifier": "",
                        "raw_snippet": "",
                    }
                    mock.update(mock_overrides)
                    insert_mock_usage(conn, mock)


class TestLoadDatasetMetrics:
    def test_missing_db_returns_none(self, tmp_path):
        assert load_dataset_metrics("a", db_root=tmp_path) is None

    def test_mock_prevalence_and_has_mock_dist(self, tmp_path):
        _make_db(
            tmp_path,
            "a",
            [
                {
                    "language": "python",
                    "fixtures": [
                        {"overrides": {"num_mocks": 2}, "mocks": [{}, {}]},
                        {"overrides": {"num_mocks": 0}},
                        {"overrides": {"num_mocks": 1}, "mocks": [{}]},
                    ],
                }
            ],
        )
        metrics = load_dataset_metrics("a", db_root=tmp_path)
        assert isinstance(metrics, DatasetMetrics)
        assert metrics.n_fixtures == 3
        assert metrics.n_mock_usages == 3
        assert sorted(metrics.num_mocks_raw) == [0, 1, 2]
        assert metrics.has_mock_dist == {"has_mock": 2, "no_mock": 1}

    def test_mock_rate_by_language(self, tmp_path):
        _make_db(
            tmp_path,
            "a",
            [
                {
                    "language": "python",
                    "fixtures": [
                        {"overrides": {"num_mocks": 1}, "mocks": [{}]},
                        {"overrides": {"num_mocks": 0}},
                    ],
                },
                {
                    "language": "java",
                    "fixtures": [{"overrides": {"num_mocks": 0}}],
                },
            ],
        )
        metrics = load_dataset_metrics("a", db_root=tmp_path)
        assert metrics.mock_rate_by_language == {
            "python": {"total": 2, "with_mocks": 1, "rate": 50.0},
            "java": {"total": 1, "with_mocks": 0, "rate": 0.0},
        }

    def test_language_leakage(self, tmp_path):
        """_make_db's repo is always tagged "python" -- the "java" file
        entry here is a leaked fixture by construction, same as
        test_mock_rate_by_language above."""
        _make_db(
            tmp_path,
            "a",
            [
                {"language": "python", "fixtures": [{}, {}]},
                {"language": "java", "fixtures": [{}]},
            ],
        )
        metrics = load_dataset_metrics("a", db_root=tmp_path)
        assert len(metrics.language_leakage) == 1
        row = metrics.language_leakage[0]
        assert row.repo_language == "python"
        assert row.total == 3
        assert row.leaked == 1
        assert row.leaked_by_language == {"java": 1}

    def test_has_mock_by_repo_groups_counts_by_repo_id(self, tmp_path):
        _make_multi_repo_db(tmp_path, "a", [[1.0] * 100, [0.0]])
        metrics = load_dataset_metrics("a", db_root=tmp_path)
        assert len(metrics.has_mock_by_repo) == 2
        assert {"has_mock": 100, "no_mock": 0} in metrics.has_mock_by_repo.values()
        assert {"has_mock": 0, "no_mock": 1} in metrics.has_mock_by_repo.values()

    def test_has_mock_by_repo_and_language_nests_by_language_then_repo(self, tmp_path):
        """A single repo contributing fixtures in two languages must land
        in two separate language buckets, each keyed by that same repo_id
        -- the paper table's per-language Coverage column
        (_mocking_coverage_indicators()) needs this nesting to never mix
        one language's has_mock counts into another's."""
        _make_db(
            tmp_path,
            "a",
            [
                {
                    "language": "python",
                    "fixtures": [
                        {"overrides": {"num_mocks": 1}, "mocks": [{}]},
                        {"overrides": {"num_mocks": 0}},
                    ],
                },
                {
                    "language": "java",
                    "fixtures": [{"overrides": {"num_mocks": 0}}],
                },
            ],
        )
        metrics = load_dataset_metrics("a", db_root=tmp_path)
        assert set(metrics.has_mock_by_repo_and_language) == {"python", "java"}
        (python_repo_id, python_counts), = metrics.has_mock_by_repo_and_language["python"].items()
        (java_repo_id, java_counts), = metrics.has_mock_by_repo_and_language["java"].items()
        assert python_repo_id == java_repo_id
        assert python_counts == {"has_mock": 1, "no_mock": 1}
        assert java_counts == {"has_mock": 0, "no_mock": 1}

    def test_num_mocks_by_repo_groups_raw_values_by_repo_id(self, tmp_path):
        _make_multi_repo_db(tmp_path, "a", [[3.0, 0.0], [5.0]])
        metrics = load_dataset_metrics("a", db_root=tmp_path)
        assert len(metrics.num_mocks_by_repo) == 2
        assert sorted(metrics.num_mocks_by_repo.values()) == [[3.0, 0.0], [5.0]]

    def test_framework_and_category_distribution(self, tmp_path):
        _make_db(
            tmp_path,
            "a",
            [
                {
                    "language": "python",
                    "fixtures": [
                        {
                            "overrides": {"num_mocks": 2},
                            "mocks": [
                                {"framework": "unittest_mock", "category": "stub"},
                                {"framework": "pytest_mock", "category": "mock"},
                            ],
                        }
                    ],
                }
            ],
        )
        metrics = load_dataset_metrics("a", db_root=tmp_path)
        assert metrics.framework_dist == {"unittest_mock": 1, "pytest_mock": 1}
        assert metrics.category_dist == {"stub": 1, "mock": 1}

    def test_framework_by_language(self, tmp_path):
        _make_db(
            tmp_path,
            "a",
            [
                {
                    "language": "python",
                    "fixtures": [
                        {"overrides": {"num_mocks": 1}, "mocks": [{"framework": "unittest_mock"}]}
                    ],
                },
                {
                    "language": "java",
                    "fixtures": [
                        {"overrides": {"num_mocks": 1}, "mocks": [{"framework": "mockito"}]}
                    ],
                },
            ],
        )
        metrics = load_dataset_metrics("a", db_root=tmp_path)
        assert metrics.framework_by_language == {
            "python": {"unittest_mock": 1},
            "java": {"mockito": 1},
        }

class TestGenerateReport:
    def test_missing_all_dbs_notes_unavailable_without_crashing(self, tmp_path):
        report = generate_report(db_root=tmp_path)
        assert "Dataset A not available" in report
        assert "Not available -- db not collected yet." in report

    def test_dataset_a_only_renders_summary_and_skips_comparisons(self, tmp_path):
        _make_db(
            tmp_path,
            "a",
            [{"language": "python", "fixtures": [{"overrides": {"num_mocks": 1}, "mocks": [{}]}]}],
        )
        report = generate_report(db_root=tmp_path)
        assert "Dataset A (agent-authored) -- 1 fixtures, 1 mock usages" in report
        assert "## A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)" in report
        # C summary, A-vs-C main comparison: 2 total.
        assert report.count("Not available -- db not collected yet.") == 2

    def test_dataset_summary_includes_language_leakage_table(self, tmp_path):
        _make_db(
            tmp_path,
            "a",
            [
                {"language": "python", "fixtures": [{}]},
                {"language": "java", "fixtures": [{}]},
            ],
        )
        report = generate_report(db_root=tmp_path)
        assert "Cross-language fixture leakage" in report
        assert "1/2 fixtures (50.00%) leaked." in report
        assert "| python | 2 | 1 | 50.00% | java=1 |" in report

    def test_a_vs_c_comparison_renders_significant_difference(self, tmp_path):
        # Sharply different num_mocks distributions -> Mann-Whitney should flag significance.
        _make_db(
            tmp_path,
            "a",
            [
                {
                    "language": "python",
                    "fixtures": [{"overrides": {"num_mocks": v}} for v in [5, 6, 5, 7, 6, 5, 6, 5, 7, 6]],
                }
            ],
        )
        _make_db(
            tmp_path,
            "c",
            [
                {
                    "language": "python",
                    "fixtures": [{"overrides": {"num_mocks": v}} for v in [0, 0, 1, 0, 0, 1, 0, 0, 1, 0]],
                }
            ],
        )
        report = generate_report(db_root=tmp_path)
        num_mocks_section = report.split("### num_mocks")[1].split("### Mocking Coverage (paper table)")[0]
        fixture_level_section = num_mocks_section.split("**Repo-level**")[0]
        overall_line = next(
            line for line in fixture_level_section.splitlines() if line.startswith("| Overall |")
        )
        # Fully separated groups (every A value exceeds every C value) --
        # a large practical effect, negative (A's values exceed C's).
        assert "-1.000 | large" in overall_line

    def test_repo_level_aggregate_declusters_a_prolific_repo(self, tmp_path):
        """One repo contributing many high-num_mocks fixtures must not
        dominate the comparison -- see the analogous rq2.py test for the
        full reasoning. A: one repo with 100 fixtures at num_mocks=10 plus
        one repo with a single num_mocks=0 fixture (fixture-level mean
        dominated by the prolific repo). C: two repos each with one
        num_mocks=5 fixture. Repo-level, A's per-repo means are
        [10.0, 0.0] (mean 5.0) -- much closer to C's 5.0 than the
        fixture-level view suggests, and not a significant difference."""
        _make_multi_repo_db(tmp_path, "a", [[10.0] * 100, [0.0]])
        _make_multi_repo_db(tmp_path, "c", [[5.0], [5.0]])

        a_metrics = load_dataset_metrics("a", db_root=tmp_path)
        c_metrics = load_dataset_metrics("c", db_root=tmp_path)

        assert sorted(a_metrics.repo_level_continuous["num_mocks"]) == [0.0, 10.0]

        fixture_level = a_metrics.num_mocks_raw
        assert sum(fixture_level) / len(fixture_level) > 9  # dominated by the prolific repo

        t = compare_datasets_repo_level(a_metrics, c_metrics)["num_mocks"]
        assert t.is_balanced  # not significant once each repo counts once

        # num_mocks's repo-level Overall row now lives in the main "###
        # num_mocks" section (its "**Repo-level**" subsection), not a
        # separate "## Repo-level aggregates" table.
        report = generate_report(db_root=tmp_path)
        num_mocks_section = report.split("### num_mocks")[1].split("### Mocking Coverage (paper table)")[0]
        repo_level_section = num_mocks_section.split("**Repo-level**")[1]
        overall_line = next(
            line for line in repo_level_section.splitlines() if line.startswith("| Overall |")
        )
        assert "| 2 | 2 |" in overall_line  # 2 repos per side, not 101 fixtures

    def test_paper_table_present_removed_sections_gone(self, tmp_path):
        _make_db(
            tmp_path,
            "a",
            [{"language": "python", "fixtures": [{"overrides": {"num_mocks": 1}, "mocks": [{}]}]}],
        )
        _make_db(
            tmp_path,
            "c",
            [{"language": "python", "fixtures": [{"overrides": {"num_mocks": 0}}]}],
        )
        report = generate_report(db_root=tmp_path)
        assert "### Mocking Coverage (paper table)" in report
        # Removed entirely -- not moved anywhere.
        assert "## Legacy: Fixture-Level Mock Prevalence" not in report
        assert "### has_mock" not in report
        assert "## Repo-level aggregates" not in report
        assert "**Mocking framework distribution" not in report
        assert "**Test-double category distribution" not in report
        assert "Aggregate category distribution" not in report
        assert "### framework" not in report
        assert "### category" not in report

    def test_mock_counts_table_present_after_paper_table_additive_not_replacing(self, tmp_path):
        """New additional table -- must appear, must come after the
        Coverage/Intensity paper table (not replace or precede it), and
        every other existing section must remain untouched."""
        _make_db(
            tmp_path,
            "a",
            [{"language": "python", "fixtures": [{"overrides": {"num_mocks": 1}, "mocks": [{}]}]}],
        )
        _make_db(
            tmp_path,
            "c",
            [{"language": "python", "fixtures": [{"overrides": {"num_mocks": 0}}]}],
        )
        report = generate_report(db_root=tmp_path)
        assert "### Mock Fixture Counts by Language" in report
        assert "| Language | Mock A (n) | Mock A (%) | Mock C (n) | Mock C (%) |" in report
        assert (
            report.index("### Mocking Coverage (paper table)")
            < report.index("### Mock Fixture Counts by Language")
        )
        counts_section = report.split("### Mock Fixture Counts by Language")[1]
        assert "| Overall | 1 | 100.0% | 0 | 0.0% |" in counts_section
        assert "| python | 1 | 100.0% | 0 | 0.0% |" in counts_section

    def test_paper_table_shows_fixed_four_language_rows_including_absent_ones(self, tmp_path):
        """The paper table always shows all four canonical language rows,
        not an intersection of languages present on both sides --
        java/javascript/typescript here have no data on either side at
        all, and must still render (as insufficient-data dashes, not be
        omitted)."""
        _make_db(
            tmp_path,
            "a",
            [{"language": "python", "fixtures": [{"overrides": {"num_mocks": 1}, "mocks": [{}]}]}],
        )
        _make_db(
            tmp_path,
            "c",
            [{"language": "python", "fixtures": [{"overrides": {"num_mocks": 0}}]}],
        )
        report = generate_report(db_root=tmp_path)
        paper_table_section = report.split("### Mocking Coverage (paper table)")[1]
        for language in ("java", "javascript", "python", "typescript"):
            assert f"| {language} |" in paper_table_section
        java_line = next(
            line for line in paper_table_section.splitlines() if line.startswith("| java |")
        )
        assert "| java | 0 | 0 | -- | -- |" == java_line


class TestMockingCoverageIndicators:
    def test_has_mock_greater_than_zero_is_one_else_zero(self):
        by_repo = {
            1: {"has_mock": 3, "no_mock": 1},
            2: {"has_mock": 0, "no_mock": 5},
        }
        assert sorted(_mocking_coverage_indicators(by_repo)) == [0.0, 1.0]

    def test_empty_dict_returns_empty_list(self):
        assert _mocking_coverage_indicators({}) == []


class TestRenderMockCountsTable:
    """Direct DatasetMetrics construction (bypassing the DB) -- has_mock_dist/
    has_mock_dist_by_language only, the two fields this table reads."""

    def test_header_matches_requested_format(self):
        a = DatasetMetrics(dataset="a", n_fixtures=0, n_mock_usages=0)
        other = DatasetMetrics(dataset="c", n_fixtures=0, n_mock_usages=0)
        rendered = _render_mock_counts_table(a, other)
        assert "### Mock Fixture Counts by Language" in rendered
        assert (
            "| Language | Mock A (n) | Mock A (%) | Mock C (n) | Mock C (%) |" in rendered
        )

    def test_renders_hand_verified_counts_and_percentages(self):
        """A/python: 3 mock / 12 total = 25.0%. C/python: 1 mock / 4 total
        = 25.0% (same rate, different n -- percentages must be computed
        independently per side, not shared)."""
        a = DatasetMetrics(
            dataset="a",
            n_fixtures=0,
            n_mock_usages=0,
            has_mock_dist={"has_mock": 3, "no_mock": 9},
            has_mock_dist_by_language={"python": {"has_mock": 3, "no_mock": 9}},
        )
        other = DatasetMetrics(
            dataset="c",
            n_fixtures=0,
            n_mock_usages=0,
            has_mock_dist={"has_mock": 1, "no_mock": 3},
            has_mock_dist_by_language={"python": {"has_mock": 1, "no_mock": 3}},
        )
        rendered = _render_mock_counts_table(a, other)
        lines = rendered.splitlines()
        assert "| Overall | 3 | 25.0% | 1 | 25.0% |" in lines
        assert "| python | 3 | 25.0% | 1 | 25.0% |" in lines

    def test_language_absent_from_one_side_renders_zero_not_division_error(self):
        a = DatasetMetrics(
            dataset="a",
            n_fixtures=0,
            n_mock_usages=0,
            has_mock_dist={"has_mock": 2, "no_mock": 2},
            has_mock_dist_by_language={"java": {"has_mock": 2, "no_mock": 2}},
        )
        other = DatasetMetrics(dataset="c", n_fixtures=0, n_mock_usages=0)
        rendered = _render_mock_counts_table(a, other)
        lines = rendered.splitlines()
        assert "| java | 2 | 50.0% | 0 | 0.0% |" in lines
        # javascript/python/typescript absent on both sides -- still
        # rendered as zero-filled rows, not omitted.
        for language in ("javascript", "python", "typescript"):
            assert f"| {language} | 0 | 0.0% | 0 | 0.0% |" in lines

    def test_denominator_is_total_fixture_count_no_exclusions(self):
        """Unlike RQ3's setup/teardown table, there is no 'other' category
        to exclude -- the denominator is exactly has_mock + no_mock, the
        language's whole fixture count."""
        a = DatasetMetrics(
            dataset="a",
            n_fixtures=0,
            n_mock_usages=0,
            has_mock_dist={"has_mock": 1, "no_mock": 1},
            has_mock_dist_by_language={"java": {"has_mock": 1, "no_mock": 1}},
        )
        other = DatasetMetrics(dataset="c", n_fixtures=0, n_mock_usages=0)
        rendered = _render_mock_counts_table(a, other)
        java_line = next(line for line in rendered.splitlines() if line.startswith("| java |"))
        assert "| java | 1 | 50.0% | 0 | 0.0% |" == java_line


class TestRenderMockingSummaryTable:
    """Direct DatasetMetrics construction (bypassing the DB) for precise
    rendering checks. Purely descriptive as of 2026-09-27 -- no
    statistical test, no effect size, no BH-FDR (see rq4.py's module
    docstring) -- so these just check the percentage arithmetic and
    column layout, not any Mann-Whitney/correction behavior."""

    def test_renders_real_coverage_numbers(self):
        """A: 4/5 python repos mock (80%). C: 1/5 mocks (20%)."""
        a = DatasetMetrics(
            dataset="a",
            n_fixtures=0,
            n_mock_usages=0,
            has_mock_by_repo_and_language={
                "python": {
                    0: {"has_mock": 1, "no_mock": 0},
                    1: {"has_mock": 1, "no_mock": 0},
                    2: {"has_mock": 1, "no_mock": 0},
                    3: {"has_mock": 1, "no_mock": 0},
                    4: {"has_mock": 0, "no_mock": 2},
                }
            },
        )
        other = DatasetMetrics(
            dataset="c",
            n_fixtures=0,
            n_mock_usages=0,
            has_mock_by_repo_and_language={
                "python": {
                    10: {"has_mock": 1, "no_mock": 0},
                    11: {"has_mock": 0, "no_mock": 3},
                    12: {"has_mock": 0, "no_mock": 3},
                    13: {"has_mock": 0, "no_mock": 3},
                    14: {"has_mock": 0, "no_mock": 3},
                }
            },
        )
        rendered = _render_mocking_summary_table(a, other)
        python_line = next(
            line for line in rendered.splitlines() if line.startswith("| python |")
        )
        assert "| 5 | 5 |" in python_line  # n_A | n_C
        assert "80.0% | 20.0%" in python_line  # Coverage A | Coverage C
        # No statistic/effect-size/p-value columns at all.
        assert python_line.count("|") == 6

    def test_overall_row_pools_every_language(self):
        a = DatasetMetrics(
            dataset="a",
            n_fixtures=0,
            n_mock_usages=0,
            has_mock_by_repo=({1: {"has_mock": 1, "no_mock": 0}, 2: {"has_mock": 0, "no_mock": 1}}),
        )
        other = DatasetMetrics(
            dataset="c",
            n_fixtures=0,
            n_mock_usages=0,
            has_mock_by_repo={10: {"has_mock": 0, "no_mock": 1}},
        )
        rendered = _render_mocking_summary_table(a, other)
        overall_line = next(
            line for line in rendered.splitlines() if line.startswith("| Overall |")
        )
        assert "| 2 | 1 |" in overall_line
        assert "50.0% | 0.0%" in overall_line

    def test_language_absent_from_both_sides_shows_empty_population(self):
        a = DatasetMetrics(
            dataset="a",
            n_fixtures=0,
            n_mock_usages=0,
            has_mock_by_repo_and_language={"python": {1: {"has_mock": 1, "no_mock": 0}}},
        )
        other = DatasetMetrics(
            dataset="c",
            n_fixtures=0,
            n_mock_usages=0,
            has_mock_by_repo_and_language={"python": {10: {"has_mock": 1, "no_mock": 0}}},
        )
        rendered = _render_mocking_summary_table(a, other)
        java_line = next(line for line in rendered.splitlines() if line.startswith("| java |"))
        assert "| java | 0 | 0 | -- | -- |" == java_line

    def test_header_has_no_statistic_columns(self):
        a = DatasetMetrics(dataset="a", n_fixtures=0, n_mock_usages=0)
        other = DatasetMetrics(dataset="c", n_fixtures=0, n_mock_usages=0)
        rendered = _render_mocking_summary_table(a, other)
        assert "| Language | n_A | n_C | Coverage A (%) | Coverage C (%) |" in rendered
        assert "delta" not in rendered
        assert "p_cov" not in rendered
        assert "Intensity" not in rendered


class TestWriteReport:
    def test_writes_file_matching_generate_report(self, tmp_path):
        _make_db(tmp_path, "a", [{"language": "python", "fixtures": [{"overrides": {"num_mocks": 1}, "mocks": [{}]}]}])
        out_dir = tmp_path / "out"
        path = write_report(out_dir, db_root=tmp_path)
        assert path == out_dir / "rq4.md"
        assert path.read_text() == generate_report(db_root=tmp_path)
