"""Tests for collection/research_questions/rq3.py.

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
from collection.research_questions.rq3 import (
    DatasetMetrics,
    _render_category_aggregate_descriptive_table,
    _render_category_by_language_table,
    compare_datasets_repo_level,
    generate_report,
    load_dataset_metrics,
    write_report,
)


def _make_multi_repo_db(root, dataset: str, repos: list[list[float]]) -> None:
    """Create db/{dataset}.db with one repo per entry in `repos`, each
    entry a list of `num_mocks` values for that repo's fixtures.

    Dataset "c" writes to c_sampled.db, not c.db -- see _make_db()'s
    docstring for why."""
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

    Dataset "c" writes to c_sampled.db, not c.db -- require_db_or_none()
    resolves "c" there exclusively (see _shared.py), so a test DB built at
    the full c.db path would be invisible to load_dataset_metrics()/
    generate_report() and silently look like "not collected yet."
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


def _make_multi_repo_framework_db(root, dataset: str, repos: list[list[str]]) -> None:
    """Create db/{dataset}.db with one repo per entry in `repos`, each a
    list of mock `framework` values (one fixture+mock per entry) -- for
    testing framework_by_repo/category_by_repo's repo-declustering,
    analogous to _make_multi_repo_db() above (which varies `num_mocks`
    instead).

    Dataset "c" writes to c_sampled.db, not c.db -- see _make_db()'s
    docstring for why."""
    db_file = (root / "c_sampled.db") if dataset == "c" else paths.db_path(dataset, root=root)
    initialise_db(db_file)
    with db_session(db_file) as conn:
        for repo_idx, frameworks in enumerate(repos):
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
            for i, framework in enumerate(frameworks):
                fixture_id = insert_fixture(
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
                        "num_parameters": 0,
                        "has_teardown_pair": 0,
                        "raw_source": "",
                        "framework": "pytest",
                        "num_mocks": 1,
                    },
                )
                insert_mock_usage(
                    conn,
                    {
                        "fixture_id": fixture_id,
                        "repo_id": repo_id,
                        "framework": framework,
                        "category": "mock",
                        "target_identifier": "",
                        "num_interactions_configured": 0,
                        "raw_snippet": "",
                    },
                )


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
        the per-language repo-level-proportion test
        (_render_category_by_language_table()) needs this nesting to
        never mix one language's category mix into another's."""
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
        # C summary, A-vs-C comparison, A-vs-C repo-level: 3 total.
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

    def test_a_vs_c_comparison_includes_stratified_mock_prevalence(self, tmp_path):
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
        assert "### has_mock" in report
        has_mock_section = report.split("### has_mock")[1].split(
            "**Mocking framework distribution"
        )[0]
        # python is shared by both A and C -> a real row; java only exists
        # in A, so it must not appear at all (no data to compare against).
        assert "| python |" in has_mock_section
        assert "| java |" not in has_mock_section

    def test_categorical_insufficient_data_when_no_mock_usages(self, tmp_path):
        # No mock_usages rows at all in either dataset -> has_mock's Overall
        # row is NOT insufficient (has_mock/no_mock is derived from every
        # fixture, mocked or not) -- category's per-language table is what
        # goes empty, since it needs >=1 mock_usages row to have anything
        # to compare.
        _make_db(tmp_path, "a", [{"language": "python", "fixtures": [{"overrides": {"num_mocks": 0}}]}])
        _make_db(tmp_path, "c", [{"language": "python", "fixtures": [{"overrides": {"num_mocks": 0}}]}])
        report = generate_report(db_root=tmp_path)
        category_section = report.split("| Language | Category |")[1].split(
            "Aggregate category distribution"
        )[0]
        assert "_(no language shared by both datasets)_" in category_section

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

    def test_framework_by_language_table_shows_raw_fixture_weighted_percentages(self, tmp_path):
        """The descriptive framework table (2026-08-12 fix) is intentionally
        NOT repo-declustered -- it makes no statistical claim (see this
        module's docstring: "no statistical test or effect size is
        needed"), so a prolific repo's fixtures dominate the percentage
        exactly as raw pooled counts would suggest, same as any other
        purely descriptive count."""
        _make_multi_repo_framework_db(
            tmp_path, "a", [["unittest_mock"] * 100, ["pytest_mock"]]
        )
        _make_multi_repo_framework_db(
            tmp_path, "c", [["unittest_mock"] * 100, ["pytest_mock"]]
        )

        report = generate_report(db_root=tmp_path)
        assert "**Mocking framework distribution (descriptive, per language)**" in report
        table_section = report.split("**Mocking framework distribution")[1].split(
            "**Test-double category distribution"
        )[0]
        unittest_mock_line = next(
            line for line in table_section.splitlines()
            if line.startswith("| python | unittest_mock |")
        )
        # 100 of 101 fixtures -> ~99.0%, matching raw pooled counts.
        assert "99.0% | 99.0%" in unittest_mock_line
        assert "### framework" not in report  # no chi-square table anymore
        assert "### category" not in report

    def test_framework_by_language_table_shows_union_of_both_sides_top_3(self, tmp_path):
        """A framework prominent only in C (not in A's own top 3 at all)
        must still get a row, with A's real percentage (here 0%) shown
        alongside -- the union of both sides' top 3, not just A's top 3
        with C's numbers filled in opportunistically."""
        _make_multi_repo_framework_db(
            tmp_path, "a", [["fw_a"] * 8, ["fw_shared"] * 2],
        )
        _make_multi_repo_framework_db(
            tmp_path, "c", [["fw_c"] * 8, ["fw_shared"] * 2],
        )

        report = generate_report(db_root=tmp_path)
        table_section = report.split("**Mocking framework distribution")[1].split(
            "**Test-double category distribution"
        )[0]
        fw_c_line = next(
            line for line in table_section.splitlines() if line.startswith("| python | fw_c |")
        )
        # fw_c never appears in A at all, but is C's dominant framework --
        # still gets a row, with A's (real, 0%) percentage alongside it.
        assert "| python | fw_c | 0.0% | 80.0% |" in fw_c_line


class TestRenderCategoryByLanguageTable:
    """Direct DatasetMetrics construction (bypassing the DB) for precise
    statistical-correctness checks that would need an unwieldy number of
    synthetic repos to demonstrate reliably through the real pipeline."""

    def test_bh_fdr_scoped_independently_per_language(self):
        """Real risk this covers: if BH-FDR were accidentally applied once
        across ALL languages' categories combined instead of once per
        language, a language with only a null (no real difference)
        pattern could still show as "significant" by riding along with
        another language's much stronger effect, or vice versa. python
        here has a stark, perfectly-separated 5-repos-per-side split
        (every A repo 90% mock, every C repo 10% mock); java has an
        identical distribution on both sides (a real null). Each
        language's own family must be corrected using only its own
        p-values."""
        a = DatasetMetrics(
            dataset="a",
            n_fixtures=0,
            n_mock_usages=0,
            category_by_repo_and_language={
                "python": {i: {"mock": 9, "stub": 1} for i in range(5)},
                "java": {i: {"mock": 5, "stub": 5} for i in range(100, 105)},
            },
        )
        other = DatasetMetrics(
            dataset="c",
            n_fixtures=0,
            n_mock_usages=0,
            category_by_repo_and_language={
                "python": {i: {"mock": 1, "stub": 9} for i in range(5)},
                "java": {i: {"mock": 5, "stub": 5} for i in range(100, 105)},
            },
        )
        rendered = _render_category_by_language_table(a, other)
        python_mock_line = next(
            line for line in rendered.splitlines() if line.startswith("| python | mock |")
        )
        java_mock_line = next(
            line for line in rendered.splitlines() if line.startswith("| java | mock |")
        )
        python_p_bh = python_mock_line.rstrip("|").rsplit("|", 1)[-1].strip()
        java_p_bh = java_mock_line.rstrip("|").rsplit("|", 1)[-1].strip()
        # python's perfect separation survives its own 2-test (mock/stub)
        # correction. java's proportions are literally identical on both
        # sides (5/5 every repo) -- compute_continuous_balance()'s
        # "identical_distributions" shortcut fires (raw p=1.0, no
        # adjusted_p_value at all, since apply_fdr_correction() treats
        # anything with a `details["reason"]` -- identical_distributions
        # included, not just insufficient_data -- as not part of the
        # correction family). That itself is the property worth locking
        # in here: a trivially-identical language's "--" must never turn
        # into a borrowed/adjusted value just because it shares a render
        # call with a language that has a real, testable effect.
        assert python_p_bh != "1.000" and float(python_p_bh) < 0.05
        assert java_p_bh == "--"
        assert "0.000" in java_mock_line  # Cliff's delta is 0 -- no difference at all

    def test_insufficient_data_row_when_a_language_has_no_shared_category(self):
        a = DatasetMetrics(
            dataset="a",
            n_fixtures=0,
            n_mock_usages=0,
            category_by_repo_and_language={"python": {1: {"mock": 5}}},
        )
        other = DatasetMetrics(
            dataset="c", n_fixtures=0, n_mock_usages=0, category_by_repo_and_language={}
        )
        rendered = _render_category_by_language_table(a, other)
        assert "_(no language shared by both datasets)_" in rendered

    def test_no_shared_language_at_all_renders_placeholder(self):
        a = DatasetMetrics(dataset="a", n_fixtures=0, n_mock_usages=0)
        other = DatasetMetrics(dataset="c", n_fixtures=0, n_mock_usages=0)
        rendered = _render_category_by_language_table(a, other)
        assert "_(no language shared by both datasets)_" in rendered


class TestRenderCategoryAggregateDescriptiveTable:
    def test_renders_plain_percentages_no_test_or_effect_size(self):
        a = DatasetMetrics(
            dataset="a", n_fixtures=0, n_mock_usages=0,
            category_dist={"mock": 8, "stub": 2},
        )
        other = DatasetMetrics(
            dataset="c", n_fixtures=0, n_mock_usages=0,
            category_dist={"mock": 4, "stub": 4, "spy": 2},
        )
        rendered = _render_category_aggregate_descriptive_table(a, other)
        mock_line = next(line for line in rendered.splitlines() if line.startswith("| mock |"))
        assert "| mock | 80.0% | 40.0% |" in mock_line
        # spy never appears in A -- still gets a row, at 0%.
        spy_line = next(line for line in rendered.splitlines() if line.startswith("| spy |"))
        assert "| spy | 0.0% | 20.0% |" in spy_line
        # No p-value/effect-size columns at all -- purely descriptive.
        assert "δ" not in rendered
        assert "p (BH)" not in rendered


class TestWriteReport:
    def test_writes_file_matching_generate_report(self, tmp_path):
        _make_db(tmp_path, "a", [{"language": "python", "fixtures": [{"overrides": {"num_mocks": 1}, "mocks": [{}]}]}])
        out_dir = tmp_path / "out"
        path = write_report(out_dir, db_root=tmp_path)
        assert path == out_dir / "rq3.md"
        assert path.read_text() == generate_report(db_root=tmp_path)
