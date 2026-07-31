"""Tests for collection/research_questions/rq2.py.

Builds tiny synthetic db/{dataset}.db files under tmp_path (via the real
schema, initialise_db()) and checks the kind classification, per-repo
ratio computation, teardown-rate-by-type breakdown, and report rendering
-- never touching the real db/ or research_questions/ directories. The
Mann-Whitney U / chi-square math itself is already covered by
tests/between_group/test_between_group_comparison.py.
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
from collection.research_questions.rq2 import (
    DatasetMetrics,
    _kind,
    generate_report,
    load_dataset_metrics,
    write_report,
)


def _make_db(root, dataset: str, repos: list[list[dict]]) -> None:
    """Create db/{dataset}.db under `root` with one repo per entry in `repos`,
    each populated with the given list of fixture-field overrides."""
    db_file = paths.db_path(dataset, root=root)
    initialise_db(db_file)
    with db_session(db_file) as conn:
        for repo_idx, fixtures in enumerate(repos):
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
            for i, overrides in enumerate(fixtures):
                base = {
                    "file_id": file_id,
                    "repo_id": repo_id,
                    "name": f"fixture_{repo_idx}_{i}",
                    "fixture_type": "before_each",
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


class TestKind:
    def test_unambiguous_setup_type(self):
        assert _kind("before_each") == "setup"
        assert _kind("junit5_before_each") == "setup"

    def test_unambiguous_teardown_type(self):
        assert _kind("after_each") == "teardown"
        assert _kind("junit5_after_each") == "teardown"

    def test_genuinely_ambiguous_types_are_other(self):
        # pytest_decorator (optional teardown via yield, not type or name);
        # junit_rule/vitest_around_* (inherently both at once);
        # testng_data_provider (not a lifecycle hook at all) -- none of
        # these can be split by type OR name.
        for fixture_type in (
            "pytest_decorator",
            "junit_rule",
            "junit_class_rule",
            "vitest_around_each",
            "vitest_around_all",
            "testng_data_provider",
        ):
            assert _kind(fixture_type) == "other"

    def test_name_based_types_without_a_name_are_other(self):
        # unittest_setup/pytest_class_method need a name to disambiguate --
        # type alone isn't enough.
        assert _kind("unittest_setup") == "other"
        assert _kind("pytest_class_method") == "other"

    def test_name_based_setup_names(self):
        assert _kind("unittest_setup", "setUp") == "setup"
        assert _kind("unittest_setup", "setUpClass") == "setup"
        assert _kind("unittest_setup", "setUpModule") == "setup"
        assert _kind("pytest_class_method", "setup_method") == "setup"
        assert _kind("pytest_class_method", "setup_class") == "setup"

    def test_name_based_teardown_names(self):
        assert _kind("unittest_setup", "tearDown") == "teardown"
        assert _kind("unittest_setup", "tearDownClass") == "teardown"
        assert _kind("unittest_setup", "tearDownModule") == "teardown"
        assert _kind("pytest_class_method", "teardown_method") == "teardown"
        assert _kind("pytest_class_method", "teardown_class") == "teardown"

    def test_name_based_type_with_unrecognized_name_is_other(self):
        assert _kind("unittest_setup", "some_helper_method") == "other"


class TestLoadDatasetMetrics:
    def test_missing_db_returns_none(self, tmp_path):
        assert load_dataset_metrics("a", db_root=tmp_path) is None

    def test_kind_distribution(self, tmp_path):
        _make_db(
            tmp_path,
            "a",
            [
                [
                    {"fixture_type": "before_each"},
                    {"fixture_type": "before_each"},
                    {"fixture_type": "after_each"},
                    {"fixture_type": "pytest_decorator"},
                ]
            ],
        )
        metrics = load_dataset_metrics("a", db_root=tmp_path)
        assert isinstance(metrics, DatasetMetrics)
        assert metrics.n_fixtures == 4
        assert metrics.kind_distribution == {"setup": 2, "teardown": 1, "other": 1}

    def test_kind_distribution_splits_name_based_types(self, tmp_path):
        """unittest_setup/pytest_class_method rows must be classified by
        name, not dumped wholesale into 'other' -- the fix this test file
        exists to cover."""
        _make_db(
            tmp_path,
            "a",
            [
                [
                    {"fixture_type": "unittest_setup", "name": "setUp"},
                    {"fixture_type": "unittest_setup", "name": "tearDown"},
                    {"fixture_type": "pytest_class_method", "name": "setup_method"},
                    {"fixture_type": "junit_rule", "name": "tempFolder"},
                ]
            ],
        )
        metrics = load_dataset_metrics("a", db_root=tmp_path)
        assert metrics.kind_distribution == {"setup": 2, "teardown": 1, "other": 1}

    def test_per_repo_ratio_computed_only_over_repos_with_teardown(self, tmp_path):
        _make_db(
            tmp_path,
            "a",
            [
                # repo 0: 2 setup, 1 teardown -> ratio 2.0
                [
                    {"fixture_type": "before_each"},
                    {"fixture_type": "before_each"},
                    {"fixture_type": "after_each"},
                ],
                # repo 1: 3 setup, 0 teardown -> undefined, counted separately
                [
                    {"fixture_type": "before_each"},
                    {"fixture_type": "before_each"},
                    {"fixture_type": "before_each"},
                ],
                # repo 2: 0 setup, 1 teardown -> excluded entirely (no setup fixtures)
                [{"fixture_type": "after_each"}],
            ],
        )
        metrics = load_dataset_metrics("a", db_root=tmp_path)
        assert metrics.per_repo_ratios == [2.0]
        assert metrics.n_repos_with_setup == 2
        assert metrics.n_repos_zero_teardown == 1

    def test_teardown_rate_by_type(self, tmp_path):
        _make_db(
            tmp_path,
            "a",
            [
                [
                    {"fixture_type": "pytest_decorator", "has_teardown_pair": 1},
                    {"fixture_type": "pytest_decorator", "has_teardown_pair": 0},
                    {"fixture_type": "pytest_decorator", "has_teardown_pair": 0},
                    {"fixture_type": "junit_rule", "has_teardown_pair": 1},
                ]
            ],
        )
        metrics = load_dataset_metrics("a", db_root=tmp_path)
        assert metrics.teardown_rate_by_type["pytest_decorator"] == {"n": 3, "n_with_pair": 1}
        assert metrics.teardown_rate_by_type["junit_rule"] == {"n": 1, "n_with_pair": 1}


class TestGenerateReport:
    def test_missing_all_dbs_notes_unavailable_without_crashing(self, tmp_path):
        report = generate_report(db_root=tmp_path)
        assert "Dataset A not available" in report
        assert "Not available -- db not collected yet." in report

    def test_dataset_a_only_renders_summary_and_skips_comparisons(self, tmp_path):
        _make_db(tmp_path, "a", [[{"fixture_type": "before_each"}, {"fixture_type": "after_each"}]])
        report = generate_report(db_root=tmp_path)
        assert "Dataset A (agent-authored) -- 2 fixtures" in report
        assert "## A vs B: Dataset A (agent-authored) vs Dataset B (human-authored, contemporary)" in report
        assert "## A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)" in report
        assert report.count("Not available -- db not collected yet.") == 4

    def test_dataset_summary_includes_language_leakage_table(self, tmp_path):
        """_make_db's repo and its one test_file both use "python", so this
        is a no-leakage wiring check -- compute_language_leakage() itself is
        covered against real leaked data in
        test_research_questions_shared.py."""
        _make_db(tmp_path, "a", [[{"fixture_type": "before_each"}]])
        report = generate_report(db_root=tmp_path)
        assert "Cross-language fixture leakage" in report
        assert "0/1 fixtures (0.00%) leaked." in report

    def test_zero_teardown_repos_reported(self, tmp_path):
        _make_db(
            tmp_path,
            "a",
            [[{"fixture_type": "before_each"}, {"fixture_type": "before_each"}]],
        )
        report = generate_report(db_root=tmp_path)
        assert "with zero teardown fixtures (ratio undefined): 1 (100.0%)" in report

    def test_a_vs_b_comparison_renders(self, tmp_path):
        _make_db(
            tmp_path,
            "a",
            [
                [{"fixture_type": "before_each"}] * 4 + [{"fixture_type": "after_each"}],
                [{"fixture_type": "before_each"}] * 4 + [{"fixture_type": "after_each"}],
            ],
        )
        _make_db(
            tmp_path,
            "b",
            [
                [{"fixture_type": "before_each"}] + [{"fixture_type": "after_each"}] * 4,
                [{"fixture_type": "before_each"}] + [{"fixture_type": "after_each"}] * 4,
            ],
        )
        report = generate_report(db_root=tmp_path)
        assert "**Per-repo setup-to-teardown ratio (Mann-Whitney U, two-sided)**" in report
        assert "fixture_type_kind" in report
        # Both _make_db calls use "python" test_files -- stratified table
        # should show a real python row, not "no language shared".
        assert "stratified by language" in report
        assert "| python |" in report
        assert "repo_zero_teardown_rate" in report
        # Effect sizes must actually be present, not just the column headers.
        assert "Cliff's delta (effect size):" in report
        assert "Cramer's V (effect size)" in report


class TestWriteReport:
    def test_writes_file_matching_generate_report(self, tmp_path):
        _make_db(tmp_path, "a", [[{"fixture_type": "before_each"}]])
        out_dir = tmp_path / "out"
        path = write_report(out_dir, db_root=tmp_path)
        assert path == out_dir / "rq2.md"
        assert path.read_text() == generate_report(db_root=tmp_path)
