"""Tests for collection/research_questions/rq2.py.

Builds tiny synthetic db/{dataset}.db files under tmp_path (via the real
schema, initialise_db()) and checks the kind classification, per-repo/
per-language repo-count bookkeeping, and report rendering -- never touching
the real db/ or research_questions/ directories. The Mann-Whitney U math
itself (including compare_categorical_repo_level()'s per-category proportion
test) is already covered by tests/between_group/test_between_group_
comparison.py and tests/collection/test_research_questions_shared.py.
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
    _python_teardown_proportions,
    _render_teardown_dip_test,
    generate_report,
    load_dataset_metrics,
    write_report,
)


def _make_db(root, dataset: str, repos: list[list[dict]]) -> None:
    """Create db/{dataset}.db under `root` with one repo per entry in `repos`,
    each populated with the given list of fixture-field overrides.

    Dataset "c" writes to the full c.db, same as every other dataset --
    Dataset C sampling is deactivated, see _shared.py::
    require_db_or_none()'s docstring.
    """
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


def _make_multi_language_db(root, dataset: str, files: list[dict]) -> None:
    """Create db/{dataset}.db with one repo and one test_file per `files`
    entry -- each entry: {"language": str, "fixtures": [fixture_dict, ...]}.
    Lets a single repo contribute fixtures in more than one language, for
    testing language-stratified aggregation (kind_distribution_by_language,
    per_repo_ratios_by_language).

    Dataset "c" writes to the full c.db, same as every other dataset --
    Dataset C sampling is deactivated, see _shared.py::
    require_db_or_none()'s docstring."""
    db_file = paths.db_path(dataset, root=root)
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
                    "fixture_type": "before_each",
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

    def test_kind_counts_by_repo_groups_all_three_kinds_by_repo_id(self, tmp_path):
        _make_db(
            tmp_path,
            "a",
            [
                # repo 0: 2 setup, 1 teardown, 1 other
                [
                    {"fixture_type": "before_each"},
                    {"fixture_type": "before_each"},
                    {"fixture_type": "after_each"},
                    {"fixture_type": "pytest_decorator"},
                ],
                # repo 1: 1 setup only
                [{"fixture_type": "before_each"}],
            ],
        )
        metrics = load_dataset_metrics("a", db_root=tmp_path)
        assert len(metrics.kind_counts_by_repo) == 2
        assert {"setup": 2, "teardown": 1, "other": 1} in metrics.kind_counts_by_repo.values()
        assert {"setup": 1, "teardown": 0, "other": 0} in metrics.kind_counts_by_repo.values()

    def test_kind_counts_by_repo_and_language_splits_by_fixtures_own_language(self, tmp_path):
        """One repo contributing fixtures in two languages must get its own
        {setup/teardown/other: count} entry under EACH language, keyed by
        that fixture's own test_files.language (not the repo's tag) -- the
        per-language rows' population."""
        _make_multi_language_db(
            tmp_path,
            "a",
            [
                {
                    "language": "python",
                    "fixtures": [{"fixture_type": "before_each"}, {"fixture_type": "after_each"}],
                },
                {"language": "typescript", "fixtures": [{"fixture_type": "before_each"}]},
            ],
        )
        metrics = load_dataset_metrics("a", db_root=tmp_path)
        by_lang = metrics.kind_counts_by_repo_and_language
        assert set(by_lang) == {"python", "typescript"}
        # Same repo_id under both languages (one repo, two languages).
        python_repo_id = next(iter(by_lang["python"]))
        typescript_repo_id = next(iter(by_lang["typescript"]))
        assert python_repo_id == typescript_repo_id
        assert by_lang["python"][python_repo_id] == {"setup": 1, "teardown": 1, "other": 0}
        assert by_lang["typescript"][typescript_repo_id] == {
            "setup": 1,
            "teardown": 0,
            "other": 0,
        }


class TestGenerateReport:
    def test_missing_all_dbs_notes_unavailable_without_crashing(self, tmp_path):
        report = generate_report(db_root=tmp_path)
        assert "Dataset A not available" in report
        assert "Not available -- db not collected yet." in report

    def test_dataset_a_only_renders_summary_and_skips_comparisons(self, tmp_path):
        _make_db(tmp_path, "a", [[{"fixture_type": "before_each"}, {"fixture_type": "after_each"}]])
        report = generate_report(db_root=tmp_path)
        assert "Dataset A (agent-authored) -- 2 fixtures" in report
        assert "## A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)" in report
        # C summary, A-vs-C comparison: 2 total (no separate repo-level
        # section anymore -- the one table below IS the repo-level result).
        assert report.count("Not available -- db not collected yet.") == 2

    def test_dataset_summary_includes_language_leakage_table(self, tmp_path):
        """_make_db's repo and its one test_file both use "python", so this
        is a no-leakage wiring check -- compute_language_leakage() itself is
        covered against real leaked data in
        test_research_questions_shared.py."""
        _make_db(tmp_path, "a", [[{"fixture_type": "before_each"}]])
        report = generate_report(db_root=tmp_path)
        assert "Cross-language fixture leakage" in report
        assert "0/1 fixtures (0.00%) leaked." in report

    def test_removed_metrics_no_longer_appear(self, tmp_path):
        """Ratio/no-teardown-rate/teardown-pair-rate were dropped from the
        paper's reported output entirely -- not just de-pooled."""
        _make_db(
            tmp_path,
            "a",
            [[{"fixture_type": "before_each"}, {"fixture_type": "before_each"}]],
        )
        _make_db(
            tmp_path,
            "c",
            [[{"fixture_type": "before_each"}, {"fixture_type": "after_each"}]],
        )
        report = generate_report(db_root=tmp_path)
        assert "setup_to_teardown_ratio" not in report
        assert "repo_zero_teardown_rate" not in report
        assert "has_teardown_pair rate by fixture_type" not in report
        assert "## Repo-level aggregates" not in report
        assert "ratio undefined" not in report

    def test_a_vs_c_comparison_renders_median_proportions_and_effect_size(self, tmp_path):
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
            "c",
            [
                [{"fixture_type": "before_each"}] + [{"fixture_type": "after_each"}] * 4,
                [{"fixture_type": "before_each"}] + [{"fixture_type": "after_each"}] * 4,
            ],
        )
        report = generate_report(db_root=tmp_path)
        assert (
            "| Language | n_A | n_C | Setup A (%) | Setup C (%) | "
            "Teardown A (%) | Teardown C (%) | V (A↔C) | p (BH) |" in report
        )
        # "python" also appears as a row label in the per-dataset
        # cross-language-leakage tables above -- scope to the comparison
        # section so we don't match those instead.
        comparison_section = report.split("## A vs C:")[1]
        # A: every repo is 4/5 setup, 1/5 teardown. C: every repo is 1/5
        # setup, 4/5 teardown -- both _make_db calls use "python" test
        # files, so Overall and the python row should show identical
        # figures (2 repos, no per-repo variation).
        overall_line = next(
            line for line in comparison_section.splitlines() if line.startswith("| Overall |")
        )
        python_line = next(
            line for line in comparison_section.splitlines() if line.startswith("| python |")
        )
        for line in (overall_line, python_line):
            assert "| 2 | 2 |" in line
            assert "80.0% | 20.0%" in line  # Setup A (%) | Setup C (%)
            assert "20.0% | 80.0%" in line  # Teardown A (%) | Teardown C (%)
            assert "large" in line  # maximally separated -> large Cliff's delta
        # Exact p-values, not a binary significant/not-significant column.
        assert "significant (p<0.05)" not in report

    def test_a_vs_c_comparison_declusters_a_prolific_repo(self, tmp_path):
        """A is one repo with 100 setup-only fixtures plus one repo with a
        single teardown-only fixture -- fixture-weighted, A would look
        ~99% setup (dominated by the prolific repo). Per-repo (what's
        actually reported), A is split 50/50 (1 of 2 repos each way), same
        as C's much smaller but proportionally identical repos."""
        _make_db(
            tmp_path,
            "a",
            [
                [{"fixture_type": "before_each"}] * 100,
                [{"fixture_type": "after_each"}],
            ],
        )
        _make_db(
            tmp_path,
            "c",
            [
                [{"fixture_type": "before_each"}],
                [{"fixture_type": "after_each"}],
            ],
        )
        report = generate_report(db_root=tmp_path)
        overall_line = next(line for line in report.splitlines() if line.startswith("| Overall |"))
        # Per-repo, both A and C are 1-of-2 repos setup-only (50%) --
        # nowhere near a ~99%-setup fixture-weighted figure.
        assert "50.0% | 50.0% | 50.0% | 50.0%" in overall_line


class TestPythonTeardownProportions:
    def test_returns_one_proportion_per_python_repo(self, tmp_path):
        _make_db(
            tmp_path,
            "a",
            [
                # repo 0: 2 setUp, 0 tearDown -> 0.0
                [
                    {"fixture_type": "unittest_setup", "name": "setUp"},
                    {"fixture_type": "unittest_setup", "name": "setUp"},
                ],
                # repo 1: 1 setUp, 1 tearDown -> 0.5
                [
                    {"fixture_type": "unittest_setup", "name": "setUp"},
                    {"fixture_type": "unittest_setup", "name": "tearDown"},
                ],
                # repo 2: 0 setUp, 2 tearDown -> 1.0
                [
                    {"fixture_type": "unittest_setup", "name": "tearDown"},
                    {"fixture_type": "unittest_setup", "name": "tearDown"},
                ],
            ],
        )
        metrics = load_dataset_metrics("a", db_root=tmp_path)
        proportions = _python_teardown_proportions(metrics)
        assert sorted(proportions) == [0.0, 0.5, 1.0]

    def test_repo_with_only_other_kind_fixtures_contributes_zero_not_excluded(self, tmp_path):
        """A repo whose only Python fixtures are pytest_decorator ('other'
        by _kind()) is NOT skipped -- its "other" fixture still counts
        toward repo_level_category_proportions()'s total-classified
        denominator (1), so it contributes a real teardown_pct of 0/1 =
        0.0, same as a repo with a genuine setup-only fixture. This is
        exactly the mechanism pytest-yield-teardown-vs-fixture-kind.md
        documents: a 100%-pytest_decorator repo doesn't drop out of the
        distribution, it silently pins at 0.0 regardless of how much real
        (yield-detected) teardown it actually has -- fixture_type_kind
        simply can't see it."""
        _make_db(
            tmp_path,
            "a",
            [
                [{"fixture_type": "unittest_setup", "name": "setUp"}],
                [{"fixture_type": "pytest_decorator"}],
            ],
        )
        metrics = load_dataset_metrics("a", db_root=tmp_path)
        proportions = _python_teardown_proportions(metrics)
        assert proportions == [0.0, 0.0]

    def test_no_python_fixtures_returns_empty_list(self, tmp_path):
        _make_multi_language_db(
            tmp_path, "a", [{"language": "typescript", "fixtures": [{"fixture_type": "before_each"}]}]
        )
        metrics = load_dataset_metrics("a", db_root=tmp_path)
        assert _python_teardown_proportions(metrics) == []


class TestRenderTeardownDipTest:
    def test_insufficient_data_renders_dashes_not_a_crash(self, tmp_path):
        """Fewer than 4 Python repos on either side -- run_dip_test()
        returns None, and the table must degrade to '--' cells, not
        raise."""
        _make_db(tmp_path, "a", [[{"fixture_type": "unittest_setup", "name": "setUp"}]])
        _make_db(tmp_path, "c", [[{"fixture_type": "unittest_setup", "name": "setUp"}]])
        a_metrics = load_dataset_metrics("a", db_root=tmp_path)
        c_metrics = load_dataset_metrics("c", db_root=tmp_path)
        report = _render_teardown_dip_test(a_metrics, c_metrics)
        assert "## Unimodality Check: Python Teardown Proportion (Dip Test)" in report
        assert "| Dataset A | 1 | -- | -- |" in report
        assert "| Dataset C | 1 | -- | -- |" in report

    def test_sufficient_data_renders_real_statistic_and_p_value(self, tmp_path):
        # 5 repos, teardown_pct = [0, 0, 0, 1, 1] -- >3 repos, so
        # run_dip_test() returns a real result instead of None.
        repos = [
            [{"fixture_type": "unittest_setup", "name": "setUp"}],
            [{"fixture_type": "unittest_setup", "name": "setUp"}],
            [{"fixture_type": "unittest_setup", "name": "setUp"}],
            [{"fixture_type": "unittest_setup", "name": "tearDown"}],
            [{"fixture_type": "unittest_setup", "name": "tearDown"}],
        ]
        _make_db(tmp_path, "a", repos)
        _make_db(tmp_path, "c", repos)
        a_metrics = load_dataset_metrics("a", db_root=tmp_path)
        c_metrics = load_dataset_metrics("c", db_root=tmp_path)
        report = _render_teardown_dip_test(a_metrics, c_metrics)

        lines = report.splitlines()
        a_row = next(line for line in lines if line.startswith("| Dataset A |"))
        assert "| Dataset A | 5 |" in a_row
        assert "--" not in a_row  # a real dip statistic/p-value rendered, not a fallback
        assert "```" in report  # the ASCII histogram's fenced code block

    def test_generate_report_includes_dip_test_section(self, tmp_path):
        _make_db(tmp_path, "a", [[{"fixture_type": "unittest_setup", "name": "setUp"}]])
        _make_db(tmp_path, "c", [[{"fixture_type": "unittest_setup", "name": "setUp"}]])
        report = generate_report(db_root=tmp_path)
        assert "## Unimodality Check: Python Teardown Proportion (Dip Test)" in report


class TestWriteReport:
    def test_writes_file_matching_generate_report(self, tmp_path):
        _make_db(tmp_path, "a", [[{"fixture_type": "before_each"}]])
        out_dir = tmp_path / "out"
        path = write_report(out_dir, db_root=tmp_path)
        assert path == out_dir / "rq2.md"
        assert path.read_text() == generate_report(db_root=tmp_path)
