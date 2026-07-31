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
from collection.research_questions.rq1 import (
    DatasetMetrics,
    generate_report,
    load_dataset_metrics,
    write_report,
)


def _make_db(root, dataset: str, fixtures: list[dict]) -> None:
    """Create db/{dataset}.db under `root` with one repo/file and `fixtures` rows.

    Each dict in `fixtures` may override any of the base columns below
    (loc, cyclomatic_complexity, scope, fixture_type, commit_type, ...).
    """
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

    def test_null_commit_type_excluded_from_categorical_distribution(self, tmp_path):
        """Dataset C fixtures never set commit_type -- must come back as an
        empty dict, not a fake {'None': n} bucket."""
        _make_db(tmp_path, "c", [{}, {}])
        metrics = load_dataset_metrics("c", db_root=tmp_path)
        assert metrics.categorical["commit_type"] == {}


class TestGenerateReport:
    def test_missing_all_dbs_notes_unavailable_without_crashing(self, tmp_path):
        report = generate_report(db_root=tmp_path)
        assert "Dataset A not available" in report
        assert "Not available -- db not collected yet." in report

    def test_dataset_a_only_renders_summary_and_skips_comparisons(self, tmp_path):
        _make_db(tmp_path, "a", [{"loc": 3}, {"loc": 7}])
        report = generate_report(db_root=tmp_path)
        assert "Dataset A (agent-authored) -- 2 fixtures" in report
        assert "## A vs B: Dataset A (agent-authored) vs Dataset B (human-authored, contemporary)" in report
        assert "## A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)" in report
        # B summary, C summary, A-vs-B comparison, A-vs-C comparison: 4 total.
        assert report.count("Not available -- db not collected yet.") == 4

    def test_dataset_summary_includes_language_leakage_table(self, tmp_path):
        """_make_db's repo and its one test_file both use "python", so this
        is a no-leakage wiring check -- compute_language_leakage() itself is
        covered against real leaked data in
        test_research_questions_shared.py."""
        _make_db(tmp_path, "a", [{"loc": 3}])
        report = generate_report(db_root=tmp_path)
        assert "Cross-language fixture leakage" in report
        assert "0/1 fixtures (0.00%) leaked." in report

    def test_a_vs_b_comparison_renders_significant_difference(self, tmp_path):
        # Sharply different LOC distributions -> Mann-Whitney should flag significance.
        _make_db(tmp_path, "a", [{"loc": v} for v in [1, 1, 2, 1, 2, 1, 2, 1, 2, 1]])
        _make_db(tmp_path, "b", [{"loc": v} for v in [50, 60, 55, 58, 62, 57, 59, 61, 56, 54]])
        report = generate_report(db_root=tmp_path)
        comparison_section = report.split("**Continuous metrics (Mann-Whitney U")[1]
        loc_line = next(
            line for line in comparison_section.splitlines() if line.startswith("| loc |")
        )
        assert loc_line.strip().endswith("| yes |")

    def test_categorical_insufficient_data_when_column_all_null(self, tmp_path):
        # commit_type is never set here -> both sides empty -> insufficient data.
        _make_db(tmp_path, "a", [{"loc": 1}])
        _make_db(tmp_path, "c", [{"loc": 1}])
        report = generate_report(db_root=tmp_path)
        commit_type_line = next(
            line for line in report.splitlines() if line.startswith("| commit_type |")
        )
        assert "_insufficient data_" in commit_type_line


class TestWriteReport:
    def test_writes_file_matching_generate_report(self, tmp_path):
        _make_db(tmp_path, "a", [{"loc": 4}])
        out_dir = tmp_path / "out"
        path = write_report(out_dir, db_root=tmp_path)
        assert path == out_dir / "rq1.md"
        assert path.read_text() == generate_report(db_root=tmp_path)
