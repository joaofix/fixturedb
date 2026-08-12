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
    each populated with the given list of fixture-field overrides.

    Dataset "c" writes to c_sampled.db, not c.db -- require_db_or_none()
    resolves "c" there exclusively (see _shared.py), so a test DB built at
    the full c.db path would be invisible to load_dataset_metrics()/
    generate_report() and silently look like "not collected yet."
    """
    db_file = (root / "c_sampled.db") if dataset == "c" else paths.db_path(dataset, root=root)
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


def _make_multi_language_db(root, dataset: str, files: list[dict]) -> None:
    """Create db/{dataset}.db with one repo and one test_file per `files`
    entry -- each entry: {"language": str, "fixtures": [fixture_dict, ...]}.
    Lets a single repo contribute fixtures in more than one language, for
    testing language-stratified aggregation (kind_distribution_by_language,
    per_repo_ratios_by_language).

    Dataset "c" writes to c_sampled.db, not c.db -- see _make_db()'s
    docstring for why."""
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

    def test_kind_n_by_language_counts_distinct_repos(self, tmp_path):
        """One repo contributing fixtures in two languages -> n=1 for each
        language, not the fixture count."""
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
        assert metrics.kind_n_by_language == {"python": 1, "typescript": 1}

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

    def test_per_repo_ratio_by_language_splits_one_repo_across_languages(self, tmp_path):
        """A single repo with setup/teardown fixtures in two languages must
        contribute a separate ratio data point to each language's bucket --
        the whole reason this exists: the pooled per-repo ratio can hide a
        language where teardown is neglected because another language in the
        same repo compensates for it."""
        _make_multi_language_db(
            tmp_path,
            "a",
            [
                {
                    "language": "python",
                    "fixtures": [
                        {"fixture_type": "before_each"},
                        {"fixture_type": "before_each"},
                        {"fixture_type": "after_each"},
                    ],
                },
                {
                    "language": "typescript",
                    "fixtures": [{"fixture_type": "before_each"}] * 3,
                },
            ],
        )
        metrics = load_dataset_metrics("a", db_root=tmp_path)

        # Pooled: 5 setup, 1 teardown across the one repo -> a defined (if
        # skewed) ratio, masking that typescript has zero teardown at all.
        assert metrics.per_repo_ratios == [5.0]
        assert metrics.n_repos_zero_teardown == 0

        # Stratified: python's ratio is visible (2 setup / 1 teardown), and
        # typescript's zero-teardown fixtures show up as undefined, not
        # folded into python's defined ratio.
        assert metrics.per_repo_ratios_by_language == {"python": [2.0], "typescript": []}
        assert metrics.n_repos_with_setup_by_language == {"python": 1, "typescript": 1}
        assert metrics.n_repos_zero_teardown_by_language == {"python": 0, "typescript": 1}


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
        # C summary, A-vs-C comparison, A-vs-C repo-level: 3 total.
        assert report.count("Not available -- db not collected yet.") == 3

    def test_dataset_summary_includes_language_leakage_table(self, tmp_path):
        """_make_db's repo and its one test_file both use "python", so this
        is a no-leakage wiring check -- compute_language_leakage() itself is
        covered against real leaked data in
        test_research_questions_shared.py."""
        _make_db(tmp_path, "a", [[{"fixture_type": "before_each"}]])
        report = generate_report(db_root=tmp_path)
        assert "Cross-language fixture leakage" in report
        assert "0/1 fixtures (0.00%) leaked." in report

    def test_dataset_summary_includes_per_language_ratio_table(self, tmp_path):
        _make_multi_language_db(
            tmp_path,
            "a",
            [
                {
                    "language": "python",
                    "fixtures": [{"fixture_type": "before_each"}, {"fixture_type": "after_each"}],
                },
                {
                    "language": "typescript",
                    "fixtures": [{"fixture_type": "before_each"}],
                },
            ],
        )
        report = generate_report(db_root=tmp_path)
        assert "**Per-repo setup-to-teardown ratio, by language**" in report
        table_section = report.split("**Per-repo setup-to-teardown ratio, by language**")[1]
        table_section = table_section.split("**has_teardown_pair rate by fixture_type**")[0]
        assert "| python | 1 | 0 | 0.0% | 1 | 1.00 | 1.00 | 1.0 | 1.0 |" in table_section
        assert "| typescript | 1 | 1 | 100.0% | 0 |" in table_section

    def test_zero_teardown_repos_reported(self, tmp_path):
        _make_db(
            tmp_path,
            "a",
            [[{"fixture_type": "before_each"}, {"fixture_type": "before_each"}]],
        )
        report = generate_report(db_root=tmp_path)
        assert "with zero teardown fixtures (ratio undefined): 1 (100.0%)" in report

    def test_a_vs_c_comparison_renders(self, tmp_path):
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
        assert "### setup_to_teardown_ratio" in report
        assert "### fixture_type_kind" in report
        assert "### repo_zero_teardown_rate" in report
        # Both _make_db calls use "python" test_files -- each metric's
        # per-language family should show a real python row.
        ratio_section = report.split("### setup_to_teardown_ratio")[1].split(
            "### fixture_type_kind"
        )[0]
        assert "| python |" in ratio_section
        assert "| Overall |" in ratio_section
        # Effect size value + magnitude columns must actually have real
        # data, not just "--" placeholders.
        assert "large" in report or "medium" in report or "small" in report or "negligible" in report
        # Exact p-values, not a binary significant/not-significant column.
        assert "significant (p<0.05)" not in report

    def test_repo_level_aggregate_declusters_a_prolific_repo(self, tmp_path):
        """fixture_type_kind's repo-level companion to the chi-square
        table: A is one repo with 100 setup-only fixtures plus one repo
        with a single teardown-only fixture -- fixture-level, A looks
        ~99% setup (dominated by the prolific repo). Per-repo, A is split
        50/50 (1 of 2 repos each way)."""
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
        assert "## Repo-level aggregates" in report
        repo_section = report.split("## Repo-level aggregates")[1]
        setup_line = next(
            line for line in repo_section.splitlines() if line.startswith("| setup |")
        )
        # Per-repo, both A and C are 1-of-2 repos setup-only (50%) --
        # nowhere near the ~99% pooled figure the chi-square table above sees.
        assert "| 50.0% | 50.0% | 50.0% | 50.0% |" in setup_line


class TestWriteReport:
    def test_writes_file_matching_generate_report(self, tmp_path):
        _make_db(tmp_path, "a", [[{"fixture_type": "before_each"}]])
        out_dir = tmp_path / "out"
        path = write_report(out_dir, db_root=tmp_path)
        assert path == out_dir / "rq2.md"
        assert path.read_text() == generate_report(db_root=tmp_path)
