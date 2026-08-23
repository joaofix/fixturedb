"""Tests for collection/research_questions/rq3.py.

Builds tiny synthetic db/{dataset}.db files under tmp_path (via the real
schema, initialise_db()) and checks mock-metric loading, per-language
breakdowns, and report rendering -- never touching the real db/ or
research_questions/ directories. The Mann-Whitney U / chi-square math itself
is already covered by tests/between_group/test_between_group_comparison.py.
"""

from __future__ import annotations

from collection import paths
from collection.between_group_comparison import compute_continuous_balance
from collection.db import (
    db_session,
    initialise_db,
    insert_fixture,
    insert_mock_usage,
    upsert_repository,
    upsert_test_file,
)
from collection.research_questions._shared import apply_fdr_correction, format_p_value
from collection.research_questions.rq3 import (
    DatasetMetrics,
    _mocking_coverage_indicators,
    _mocking_intensities_by_repo,
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
                        "num_interactions_configured": 0,
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
        one language's has_mock counts into another's, mirroring
        test_category_by_repo_and_language_nests_by_language_then_repo()
        above."""
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

    def test_num_mocks_by_repo_and_language_nests_by_language_then_repo(self, tmp_path):
        """Same nesting requirement as has_mock_by_repo_and_language above,
        for the paper table's Intensity column
        (_mocking_intensities_by_repo())."""
        _make_db(
            tmp_path,
            "a",
            [
                {
                    "language": "python",
                    "fixtures": [
                        {"overrides": {"num_mocks": 3}},
                        {"overrides": {"num_mocks": 0}},
                    ],
                },
                {
                    "language": "java",
                    "fixtures": [{"overrides": {"num_mocks": 7}}],
                },
            ],
        )
        metrics = load_dataset_metrics("a", db_root=tmp_path)
        assert set(metrics.num_mocks_by_repo_and_language) == {"python", "java"}
        (python_repo_id, python_values), = metrics.num_mocks_by_repo_and_language["python"].items()
        (java_repo_id, java_values), = metrics.num_mocks_by_repo_and_language["java"].items()
        assert python_repo_id == java_repo_id
        assert sorted(python_values) == [0, 3]
        assert java_values == [7]

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

    def test_category_by_language(self, tmp_path):
        _make_db(
            tmp_path,
            "a",
            [
                {
                    "language": "python",
                    "fixtures": [
                        {"overrides": {"num_mocks": 1}, "mocks": [{"category": "stub"}]}
                    ],
                },
                {
                    "language": "java",
                    "fixtures": [
                        {"overrides": {"num_mocks": 1}, "mocks": [{"category": "spy"}]}
                    ],
                },
            ],
        )
        metrics = load_dataset_metrics("a", db_root=tmp_path)
        assert metrics.category_by_language == {
            "python": {"stub": 1},
            "java": {"spy": 1},
        }

    def test_has_mock_n_by_language_counts_every_repo_with_a_fixture(self, tmp_path):
        """Every repo with a fixture of that language counts, even ones
        with zero mocks -- has_mock's per-language chi-square tests
        has_mock vs no_mock across ALL fixtures, not just mocked ones."""
        _make_db(
            tmp_path,
            "a",
            [{"language": "python", "fixtures": [{"overrides": {"num_mocks": 0}}]}],
        )
        metrics = load_dataset_metrics("a", db_root=tmp_path)
        assert metrics.has_mock_n_by_language == {"python": 1}

    def test_category_by_repo_and_language_nests_by_language_then_repo(self, tmp_path):
        """A single repo contributing mocks in two languages must land in
        two separate language buckets, each keyed by that same repo_id --
        no rendered table reads this anymore (the per-language category
        comparison was removed from the report), but the raw data is kept
        accessible on DatasetMetrics, so this nesting still needs to never
        mix one language's category mix into another's."""
        _make_db(
            tmp_path,
            "a",
            [
                {
                    "language": "python",
                    "fixtures": [
                        {"overrides": {"num_mocks": 1}, "mocks": [{"category": "stub"}]}
                    ],
                },
                {
                    "language": "java",
                    "fixtures": [
                        {"overrides": {"num_mocks": 1}, "mocks": [{"category": "spy"}]}
                    ],
                },
            ],
        )
        metrics = load_dataset_metrics("a", db_root=tmp_path)
        assert set(metrics.category_by_repo_and_language) == {"python", "java"}
        # _make_db puts every language's fixtures under the same one repo.
        (python_repo_id, python_counts), = metrics.category_by_repo_and_language["python"].items()
        (java_repo_id, java_counts), = metrics.category_by_repo_and_language["java"].items()
        assert python_repo_id == java_repo_id
        assert python_counts == {"stub": 1}
        assert java_counts == {"spy": 1}

    def test_interaction_depth(self, tmp_path):
        _make_db(
            tmp_path,
            "a",
            [
                {
                    "language": "python",
                    "fixtures": [
                        {
                            "overrides": {"num_mocks": 1},
                            "mocks": [{"num_interactions_configured": 3}],
                        }
                    ],
                }
            ],
        )
        metrics = load_dataset_metrics("a", db_root=tmp_path)
        assert metrics.num_interactions_raw == [3]


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
        # C summary, A-vs-C main comparison, A-vs-C legacy mock-prevalence: 3 total.
        assert report.count("Not available -- db not collected yet.") == 3

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
        num_mocks_section = report.split("### num_mocks")[1].split("### num_interactions_configured")[0]
        fixture_level_section = num_mocks_section.split("**Repo-level**")[0]
        overall_line = next(
            line for line in fixture_level_section.splitlines() if line.startswith("| Overall |")
        )
        # Fully separated groups (every A value exceeds every C value) --
        # a large practical effect, negative (A's values exceed C's).
        assert "-1.000 | large" in overall_line

    def test_legacy_mock_prevalence_includes_stratified_has_mock(self, tmp_path):
        _make_db(
            tmp_path,
            "a",
            [
                {"language": "python", "fixtures": [{"overrides": {"num_mocks": 1}}] * 9 + [{"overrides": {"num_mocks": 0}}]},
                {"language": "java", "fixtures": [{"overrides": {"num_mocks": 0}}]},
            ],
        )
        _make_db(
            tmp_path,
            "c",
            [
                {"language": "python", "fixtures": [{"overrides": {"num_mocks": 0}}] * 9 + [{"overrides": {"num_mocks": 1}}]},
            ],
        )
        report = generate_report(db_root=tmp_path)
        assert "## Legacy: Fixture-Level Mock Prevalence (Not Used in the Paper)" in report
        assert "### has_mock" in report
        legacy_section = report.split("## Legacy: Fixture-Level Mock Prevalence")[1]
        has_mock_section = legacy_section.split("### has_mock")[1]
        # python is shared by both A and C -> a real row; java only exists
        # in A, so it must not appear at all (no data to compare against) --
        # this legacy table still uses the intersection convention
        # (compute_stratified_categorical_balance()), unlike the new paper
        # table's fixed four-language rows below.
        assert "| python |" in has_mock_section
        assert "| java |" not in has_mock_section

    def test_repo_level_aggregate_declusters_a_prolific_repo(self, tmp_path):
        """One repo contributing many high-num_mocks fixtures must not
        dominate the comparison -- see the analogous rq1.py test for the
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
        num_mocks_section = report.split("### num_mocks")[1].split("### num_interactions_configured")[0]
        repo_level_section = num_mocks_section.split("**Repo-level**")[1]
        overall_line = next(
            line for line in repo_level_section.splitlines() if line.startswith("| Overall |")
        )
        assert "| 2 | 2 |" in overall_line  # 2 repos per side, not 101 fixtures

    def test_paper_table_and_legacy_sections_present_removed_sections_gone(self, tmp_path):
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
        assert "### Mocking Coverage and Intensity (paper table)" in report
        assert "## Legacy: Fixture-Level Mock Prevalence (Not Used in the Paper)" in report
        # Removed entirely -- not moved anywhere.
        assert "## Repo-level aggregates" not in report
        assert "**Mocking framework distribution" not in report
        assert "**Test-double category distribution" not in report
        assert "Aggregate category distribution" not in report
        assert "### framework" not in report
        assert "### category" not in report

    def test_paper_table_shows_fixed_four_language_rows_including_absent_ones(self, tmp_path):
        """Unlike the legacy has_mock table's intersection convention,
        the paper table always shows all four canonical language rows --
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
        paper_table_section = report.split("### Mocking Coverage and Intensity (paper table)")[1]
        for language in ("java", "javascript", "python", "typescript"):
            assert f"| {language} |" in paper_table_section
        java_line = next(
            line for line in paper_table_section.splitlines() if line.startswith("| java |")
        )
        assert "| java | 0 | 0 | -- | -- | -- | -- | -- | -- | -- | -- |" == java_line


class TestMockingCoverageIndicators:
    def test_has_mock_greater_than_zero_is_one_else_zero(self):
        by_repo = {
            1: {"has_mock": 3, "no_mock": 1},
            2: {"has_mock": 0, "no_mock": 5},
        }
        assert sorted(_mocking_coverage_indicators(by_repo)) == [0.0, 1.0]

    def test_empty_dict_returns_empty_list(self):
        assert _mocking_coverage_indicators({}) == []


class TestMockingIntensitiesByRepo:
    def test_median_computed_over_mocking_fixtures_only(self):
        """Repo 1's zero-mock fixtures must not pull its median toward 0
        -- only the num_mocks > 0 values feed the median."""
        by_repo = {1: [0, 0, 4, 6]}  # mocking values: [4, 6] -> median 5.0
        assert _mocking_intensities_by_repo(by_repo) == [5.0]

    def test_repo_with_no_mocking_fixtures_excluded_entirely(self):
        """A repo whose fixtures are all num_mocks == 0 contributes
        nothing -- not a 0.0 intensity value."""
        by_repo = {1: [0, 0, 0], 2: [3, 5]}
        assert _mocking_intensities_by_repo(by_repo) == [4.0]

    def test_empty_dict_returns_empty_list(self):
        assert _mocking_intensities_by_repo({}) == []


class TestRenderMockingSummaryTable:
    """Direct DatasetMetrics construction (bypassing the DB) for precise
    statistical-correctness checks."""

    def test_renders_real_coverage_and_intensity_numbers(self):
        """A: 4/5 python repos mock (80%), the 4 mocking repos' num_mocks
        medians are [5, 3, 7, 5] -> intensity median 5.0. C: 1/5 mocks
        (20%), that one repo's median is 1.0. Fully separated in both
        metrics -> "large" Cliff's delta for both."""
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
            num_mocks_by_repo_and_language={
                "python": {0: [5], 1: [3], 2: [7], 3: [5], 4: [0, 0]}
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
            num_mocks_by_repo_and_language={
                "python": {10: [1], 11: [0], 12: [0], 13: [0], 14: [0]}
            },
        )
        rendered = _render_mocking_summary_table(a, other)
        python_line = next(
            line for line in rendered.splitlines() if line.startswith("| python |")
        )
        assert "| 5 | 5 |" in python_line  # n_A | n_C
        assert "80.0% | 20.0%" in python_line  # Coverage A | Coverage C
        assert "5.00 | 1.00" in python_line  # Intensity A | Intensity C
        assert "large" in python_line

    def test_overall_row_pools_every_language(self):
        a = DatasetMetrics(
            dataset="a",
            n_fixtures=0,
            n_mock_usages=0,
            has_mock_by_repo=({1: {"has_mock": 1, "no_mock": 0}, 2: {"has_mock": 0, "no_mock": 1}}),
            num_mocks_by_repo={1: [4], 2: [0]},
        )
        other = DatasetMetrics(
            dataset="c",
            n_fixtures=0,
            n_mock_usages=0,
            has_mock_by_repo={10: {"has_mock": 0, "no_mock": 1}},
            num_mocks_by_repo={10: [0]},
        )
        rendered = _render_mocking_summary_table(a, other)
        overall_line = next(
            line for line in rendered.splitlines() if line.startswith("| Overall |")
        )
        assert "| 2 | 1 |" in overall_line
        assert "50.0% | 0.0%" in overall_line

    def test_coverage_and_intensity_insufficient_data_are_independent(self):
        """python has real coverage data (some repos mock, some don't) but
        NO repo has any mocking fixture on the C side with a nonzero
        num_mocks captured for intensity -- so Coverage renders real
        numbers while Intensity independently degrades to dashes, one
        column pair unaffected by the other's data availability."""
        a = DatasetMetrics(
            dataset="a",
            n_fixtures=0,
            n_mock_usages=0,
            has_mock_by_repo_and_language={
                "python": {1: {"has_mock": 1, "no_mock": 0}, 2: {"has_mock": 0, "no_mock": 1}}
            },
            num_mocks_by_repo_and_language={"python": {1: [0, 0], 2: [0]}},
        )
        other = DatasetMetrics(
            dataset="c",
            n_fixtures=0,
            n_mock_usages=0,
            has_mock_by_repo_and_language={
                "python": {10: {"has_mock": 1, "no_mock": 0}, 11: {"has_mock": 0, "no_mock": 1}}
            },
            num_mocks_by_repo_and_language={"python": {10: [0], 11: [0]}},
        )
        rendered = _render_mocking_summary_table(a, other)
        python_line = next(
            line for line in rendered.splitlines() if line.startswith("| python |")
        )
        # Coverage: real numbers (50%/50%, though not a significant
        # difference -- not the point of this test).
        assert "50.0% | 50.0%" in python_line
        # Intensity: no repo anywhere actually has a num_mocks > 0 fixture
        # (has_mock's counts don't have to agree with num_mocks_by_repo_
        # and_language in this synthetic fixture -- they're independent
        # fields), so _mocking_intensities_by_repo() returns [] on both
        # sides -> insufficient_data -> dashes.
        assert "-- | -- | -- | --" in python_line

    def test_n_a_n_c_is_coverage_population_not_intensity_subset(self):
        """5 python repos on each side all have >=1 fixture (n_A/n_C = 5),
        but only 1 repo per side actually mocks -- intensity's true
        population (1 vs 1) is smaller than the row's stated n_A/n_C,
        exactly the documented asymmetry."""
        by_repo_a = {i: {"has_mock": 1 if i == 0 else 0, "no_mock": 0 if i == 0 else 1} for i in range(5)}
        by_repo_c = {i: {"has_mock": 1 if i == 0 else 0, "no_mock": 0 if i == 0 else 1} for i in range(5, 10)}
        a = DatasetMetrics(
            dataset="a", n_fixtures=0, n_mock_usages=0,
            has_mock_by_repo_and_language={"python": by_repo_a},
            num_mocks_by_repo_and_language={"python": {i: [5] if i == 0 else [0] for i in range(5)}},
        )
        other = DatasetMetrics(
            dataset="c", n_fixtures=0, n_mock_usages=0,
            has_mock_by_repo_and_language={"python": by_repo_c},
            num_mocks_by_repo_and_language={"python": {i: [3] if i == 5 else [0] for i in range(5, 10)}},
        )
        rendered = _render_mocking_summary_table(a, other)
        python_line = next(
            line for line in rendered.splitlines() if line.startswith("| python |")
        )
        assert "| 5 | 5 |" in python_line

    def test_bh_fdr_applied_across_both_metrics_combined_not_two_separate_families(self):
        """Explicit request: coverage's 4 per-language tests and
        intensity's 4 per-language tests must be BH-FDR corrected TOGETHER
        as one 8-test family, not as two independent 4-test families.
        Verified by recomputing the same compute_continuous_balance()
        calls independently here, combining all testable ones (python/java
        coverage + python/java intensity -- javascript/typescript have no
        data on either side, so both their tests are insufficient_data and
        excluded from either family regardless) into one dict the same way
        _render_mocking_summary_table() does, and checking the rendered
        adjusted p-values match apply_fdr_correction() run on that combined
        4-testable-entry family -- not on two separate 2-testable-entry
        families, which would produce different numbers for this fixture
        (more than one testable entry per metric)."""
        has_mock_python_a = {i: {"has_mock": 1, "no_mock": 0} for i in range(4)} | {
            4: {"has_mock": 0, "no_mock": 2}
        }
        has_mock_python_c = {i: {"has_mock": 0, "no_mock": 1} for i in range(4)} | {
            4: {"has_mock": 1, "no_mock": 0}
        }
        has_mock_java_a = {i: {"has_mock": 0, "no_mock": 2} for i in range(4)} | {
            4: {"has_mock": 1, "no_mock": 0}
        }
        has_mock_java_c = {i: {"has_mock": 1, "no_mock": 0} for i in range(4)} | {
            4: {"has_mock": 0, "no_mock": 1}
        }
        num_mocks_python_a = {i: [5] for i in range(4)} | {4: [0, 0]}
        num_mocks_python_c = {i: [0] for i in range(4)} | {4: [1]}
        num_mocks_java_a = {i: [0, 0] for i in range(4)} | {4: [9]}
        num_mocks_java_c = {i: [1] for i in range(4)} | {4: [0, 0]}

        a = DatasetMetrics(
            dataset="a", n_fixtures=0, n_mock_usages=0,
            has_mock_by_repo_and_language={"python": has_mock_python_a, "java": has_mock_java_a},
            num_mocks_by_repo_and_language={"python": num_mocks_python_a, "java": num_mocks_java_a},
        )
        other = DatasetMetrics(
            dataset="c", n_fixtures=0, n_mock_usages=0,
            has_mock_by_repo_and_language={"python": has_mock_python_c, "java": has_mock_java_c},
            num_mocks_by_repo_and_language={"python": num_mocks_python_c, "java": num_mocks_java_c},
        )

        # Independently recompute the same 4 testable BalanceTests and
        # correct them together as one family -- this is what the
        # implementation is REQUIRED to match.
        expected = apply_fdr_correction(
            {
                "python__coverage": compute_continuous_balance(
                    human_values=_mocking_coverage_indicators(has_mock_python_c),
                    agent_values=_mocking_coverage_indicators(has_mock_python_a),
                    variable="x",
                ),
                "java__coverage": compute_continuous_balance(
                    human_values=_mocking_coverage_indicators(has_mock_java_c),
                    agent_values=_mocking_coverage_indicators(has_mock_java_a),
                    variable="x",
                ),
                "python__intensity": compute_continuous_balance(
                    human_values=_mocking_intensities_by_repo(num_mocks_python_c),
                    agent_values=_mocking_intensities_by_repo(num_mocks_python_a),
                    variable="x",
                ),
                "java__intensity": compute_continuous_balance(
                    human_values=_mocking_intensities_by_repo(num_mocks_java_c),
                    agent_values=_mocking_intensities_by_repo(num_mocks_java_a),
                    variable="x",
                ),
            }
        )

        rendered = _render_mocking_summary_table(a, other)
        python_line = next(
            line for line in rendered.splitlines() if line.startswith("| python |")
        )
        java_line = next(line for line in rendered.splitlines() if line.startswith("| java |"))

        def _p_cells(line: str) -> list[str]:
            cells = [c.strip() for c in line.strip("|").split("|")]
            return [cells[6], cells[10]]  # p_cov, p_int (0-indexed: Language,n_A,n_C,CovA,CovC,δcov,pcov,IntA,IntC,δint,pint)

        expected_python_p_cov = format_p_value(expected["python__coverage"].details["adjusted_p_value"])
        expected_python_p_int = format_p_value(expected["python__intensity"].details["adjusted_p_value"])
        expected_java_p_cov = format_p_value(expected["java__coverage"].details["adjusted_p_value"])
        expected_java_p_int = format_p_value(expected["java__intensity"].details["adjusted_p_value"])

        assert _p_cells(python_line) == [expected_python_p_cov, expected_python_p_int]
        assert _p_cells(java_line) == [expected_java_p_cov, expected_java_p_int]


class TestWriteReport:
    def test_writes_file_matching_generate_report(self, tmp_path):
        _make_db(tmp_path, "a", [{"language": "python", "fixtures": [{"overrides": {"num_mocks": 1}, "mocks": [{}]}]}])
        out_dir = tmp_path / "out"
        path = write_report(out_dir, db_root=tmp_path)
        assert path == out_dir / "rq3.md"
        assert path.read_text() == generate_report(db_root=tmp_path)
