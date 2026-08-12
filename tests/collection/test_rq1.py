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
    DatasetMetrics,
    compare_datasets_repo_level,
    generate_report,
    load_dataset_metrics,
    write_report,
)


def _make_multi_repo_db(root, dataset: str, repos: list[list[float]]) -> None:
    """Create db/{dataset}.db with one repo per entry in `repos`, each
    entry a list of `loc` values for that repo's fixtures.

    Dataset "c" writes to c_sampled.db, not c.db -- see _make_db()'s
    docstring for why."""
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
                        "scope": "per_test",
                        "start_line": i,
                        "end_line": i + 1,
                        "loc": loc,
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


def _make_multi_repo_fixture_type_db(root, dataset: str, repos: list[list[str]]) -> None:
    """Create db/{dataset}.db with one repo per entry in `repos`, each
    entry a list of `fixture_type` values for that repo's fixtures --
    fixture_type analogue of _make_multi_repo_db() above (which varies
    `loc` instead), for testing fixture_type_by_repo's repo-declustering.

    Dataset "c" writes to c_sampled.db, not c.db -- see _make_db()'s
    docstring for why."""
    db_file = (root / "c_sampled.db") if dataset == "c" else paths.db_path(dataset, root=root)
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
                        "num_parameters": 0,
                        "has_teardown_pair": 0,
                        "raw_source": "",
                        "framework": "pytest",
                        "num_mocks": 0,
                    },
                )


def _make_db(root, dataset: str, fixtures: list[dict]) -> None:
    """Create db/{dataset}.db under `root` with one repo/file and `fixtures` rows.

    Each dict in `fixtures` may override any of the base columns below
    (loc, cyclomatic_complexity, scope, fixture_type, commit_type, ...).

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
        file_id = upsert_test_file(conn, repo_id, "tests/test_foo.py", "python")
        for i, overrides in enumerate(fixtures):
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


def _make_multi_language_db(root, dataset: str, files: list[dict]) -> None:
    """Create db/{dataset}.db with one repo and one test_file per `files`
    entry -- each entry: {"language": str, "fixtures": [fixture_dict, ...]}.
    Lets a single repo contribute fixtures in more than one language, for
    testing language-stratified aggregation (fixture_type_by_language).

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


class TestLoadDatasetMetrics:
    def test_missing_db_returns_none(self, tmp_path):
        assert load_dataset_metrics("a", db_root=tmp_path) is None

    def test_loads_continuous_and_categorical_values(self, tmp_path):
        _make_db(
            tmp_path,
            "a",
            [
                {"loc": 3, "scope": "per_test", "fixture_type": "before_each"},
                {"loc": 7, "scope": "per_test", "fixture_type": "before_each"},
                {"loc": 5, "scope": "per_class", "fixture_type": "after_each"},
            ],
        )
        metrics = load_dataset_metrics("a", db_root=tmp_path)
        assert isinstance(metrics, DatasetMetrics)
        assert metrics.n_fixtures == 3
        assert sorted(metrics.continuous_raw["loc"]) == [3, 5, 7]
        assert metrics.categorical["scope"] == {"per_test": 2, "per_class": 1}
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

    def test_null_commit_type_excluded_from_categorical_distribution(self, tmp_path):
        """Dataset C fixtures never set commit_type -- must come back as an
        empty dict, not a fake {'None': n} bucket."""
        _make_db(tmp_path, "c", [{}, {}])
        metrics = load_dataset_metrics("c", db_root=tmp_path)
        assert metrics.categorical["commit_type"] == {}

    def test_fixture_type_by_language_groups_by_fixtures_own_language(self, tmp_path):
        """Grouped by test_files.language (the fixture's own file), not the
        repo's tagged language -- same distinction compute_language_leakage()
        relies on."""
        _make_multi_language_db(
            tmp_path,
            "a",
            [
                {
                    "language": "python",
                    "fixtures": [
                        {"fixture_type": "pytest_decorator"},
                        {"fixture_type": "pytest_decorator"},
                    ],
                },
                {
                    "language": "typescript",
                    "fixtures": [{"fixture_type": "before_each"}],
                },
            ],
        )
        metrics = load_dataset_metrics("a", db_root=tmp_path)
        assert metrics.fixture_type_by_language == {
            "python": {"pytest_decorator": 2},
            "typescript": {"before_each": 1},
        }

    def test_fixture_type_by_repo_groups_by_repo_id(self, tmp_path):
        _make_multi_repo_db(tmp_path, "a", [[100.0] * 2, [1.0]])
        metrics = load_dataset_metrics("a", db_root=tmp_path)
        # _make_multi_repo_db's fixtures are all fixture_type="pytest_decorator".
        assert len(metrics.fixture_type_by_repo) == 2
        assert {"pytest_decorator": 2} in metrics.fixture_type_by_repo.values()
        assert {"pytest_decorator": 1} in metrics.fixture_type_by_repo.values()

    def test_fixture_type_n_by_language_counts_distinct_repos(self, tmp_path):
        """Two repos both contributing python fixtures -> n=2 for python,
        not the fixture count (3)."""
        _make_multi_language_db(
            tmp_path,
            "a",
            [{"language": "python", "fixtures": [{"fixture_type": "pytest_decorator"}] * 2}],
        )
        metrics = load_dataset_metrics("a", db_root=tmp_path)
        assert metrics.fixture_type_n_by_language == {"python": 1}

    def test_scope_by_language_groups_by_fixtures_own_language(self, tmp_path):
        _make_multi_language_db(
            tmp_path,
            "a",
            [
                {"language": "python", "fixtures": [{"scope": "per_test"}, {"scope": "per_test"}]},
                {"language": "typescript", "fixtures": [{"scope": "per_class"}]},
            ],
        )
        metrics = load_dataset_metrics("a", db_root=tmp_path)
        assert metrics.scope_by_language == {
            "python": {"per_test": 2},
            "typescript": {"per_class": 1},
        }

    def test_scope_n_and_commit_type_n_count_distinct_repos_with_non_null_value(self, tmp_path):
        _make_db(tmp_path, "a", [{"scope": "per_test"}, {"scope": None}, {"commit_type": "feat"}])
        metrics = load_dataset_metrics("a", db_root=tmp_path)
        assert metrics.scope_n == 1  # one repo, has >=1 non-null scope fixture
        assert metrics.commit_type_n == 1

    def test_repo_level_continuous_by_language_is_one_mean_per_repo_per_language(self, tmp_path):
        _make_multi_language_db(
            tmp_path,
            "a",
            [{"language": "python", "fixtures": [{"loc": 10}, {"loc": 20}]}],
        )
        metrics = load_dataset_metrics("a", db_root=tmp_path)
        # One repo contributing 2 python fixtures -> one repo-level mean (15.0).
        assert metrics.repo_level_continuous_by_language["loc"] == {"python": [15.0]}


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
        # C summary, A-vs-C comparison, A-vs-C repo-level: 3 total.
        assert report.count("Not available -- db not collected yet.") == 3

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

    def test_categorical_insufficient_data_when_column_all_null(self, tmp_path):
        # commit_type is never set here -> both sides empty -> insufficient data.
        _make_db(tmp_path, "a", [{"loc": 1}])
        _make_db(tmp_path, "c", [{"loc": 1}])
        report = generate_report(db_root=tmp_path)
        commit_type_section = report.split("### commit_type")[1].split("## Repo-level")[0]
        overall_line = next(
            line for line in commit_type_section.splitlines() if line.startswith("| Overall |")
        )
        assert "_insufficient data_" in overall_line

    def test_categorical_comparison_renders_effect_size(self, tmp_path):
        # A is all per_test scope, C is all per_class -> maximal association.
        _make_db(tmp_path, "a", [{"loc": 1, "scope": "per_test"}] * 10)
        _make_db(tmp_path, "c", [{"loc": 1, "scope": "per_class"}] * 10)
        report = generate_report(db_root=tmp_path)
        scope_section = report.split("### scope")[1].split("### fixture_type")[0]
        overall_line = next(
            line for line in scope_section.splitlines() if line.startswith("| Overall |")
        )
        assert "large" in overall_line

    def test_fixture_type_per_language_family_renders(self, tmp_path):
        _make_multi_language_db(
            tmp_path,
            "a",
            [{"language": "python", "fixtures": [{"fixture_type": "pytest_decorator"}] * 5}],
        )
        _make_multi_language_db(
            tmp_path,
            "c",
            [{"language": "python", "fixtures": [{"fixture_type": "before_each"}] * 5}],
        )
        report = generate_report(db_root=tmp_path)
        fixture_type_section = report.split("### fixture_type")[1].split(
            "not used in the paper"
        )[0]
        assert "| python |" in fixture_type_section
        assert "| Overall |" in fixture_type_section

    def test_fixture_type_per_language_excludes_language_not_shared(self, tmp_path):
        """A has python + java fixtures, C has python only -- java has no
        C-side data to compare against, so compute_stratified_categorical_
        balance() must drop it rather than testing against an empty dist."""
        _make_multi_language_db(
            tmp_path,
            "a",
            [
                {"language": "python", "fixtures": [{"fixture_type": "pytest_decorator"}] * 5},
                {"language": "java", "fixtures": [{"fixture_type": "junit5_before_each"}] * 5},
            ],
        )
        _make_multi_language_db(
            tmp_path,
            "c",
            [{"language": "python", "fixtures": [{"fixture_type": "before_each"}] * 5}],
        )
        report = generate_report(db_root=tmp_path)
        fixture_type_section = report.split("### fixture_type")[1].split(
            "not used in the paper"
        )[0]
        assert "| python |" in fixture_type_section
        assert "| java |" not in fixture_type_section

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

    def test_repo_level_fixture_type_proportion_table_declusters_a_prolific_repo(
        self, tmp_path
    ):
        """fixture_type's repo-level companion to the chi-square table:
        Dataset A is one repo with 100 pytest_decorator fixtures plus one
        repo with a single before_each fixture -- fixture-level, A looks
        ~99% pytest_decorator (dominated by the prolific repo). Per-repo,
        A is split 50/50 (1 of its 2 repos is pytest_decorator-only, the
        other before_each-only) -- much closer to C's per-repo mix."""
        _make_multi_repo_fixture_type_db(
            tmp_path, "a", [["pytest_decorator"] * 100, ["before_each"]]
        )
        _make_multi_repo_fixture_type_db(
            tmp_path, "c", [["pytest_decorator"], ["before_each"]]
        )

        a_metrics = load_dataset_metrics("a", db_root=tmp_path)
        assert len(a_metrics.fixture_type_by_repo) == 2
        assert {"pytest_decorator": 100} in a_metrics.fixture_type_by_repo.values()
        assert {"before_each": 1} in a_metrics.fixture_type_by_repo.values()

        fixture_level = a_metrics.categorical["fixture_type"]
        pooled_pytest_decorator_pct = 100 * fixture_level["pytest_decorator"] / sum(
            fixture_level.values()
        )
        assert pooled_pytest_decorator_pct > 95  # dominated by the prolific repo

        report = generate_report(db_root=tmp_path)
        assert "fixture_type, repo-level" in report
        repo_section = report.split("## Repo-level aggregates")[1]
        section = repo_section.split("fixture_type, repo-level")[1]
        pytest_decorator_line = next(
            line for line in section.splitlines() if line.startswith("| pytest_decorator |")
        )
        # Per-repo, A is 1 of 2 repos pytest_decorator-only (50%), matching
        # C's identical 1-of-2 split -- nowhere near the 99% pooled figure.
        assert "| 50.0% | 50.0% | 50.0% | 50.0% |" in pytest_decorator_line


class TestWriteReport:
    def test_writes_file_matching_generate_report(self, tmp_path):
        _make_db(tmp_path, "a", [{"loc": 4}])
        out_dir = tmp_path / "out"
        path = write_report(out_dir, db_root=tmp_path)
        assert path == out_dir / "rq1.md"
        assert path.read_text() == generate_report(db_root=tmp_path)
