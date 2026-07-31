"""Tests for collection/research_questions/_shared.py -- the helpers rq1.py,
rq2.py, rq3.py, and language_contamination.py all import instead of each
redefining their own copy.
"""

from __future__ import annotations

from collection.db import (
    db_session,
    initialise_db,
    insert_fixture,
    upsert_repository,
    upsert_test_file,
)
from collection.research_questions._shared import (
    LanguageLeakage,
    compute_language_leakage,
    compute_stratified_categorical_balance,
    fetch_categorical_column,
    fetch_continuous_column,
    fmt,
    render_language_leakage_table,
    render_stratified_categorical_table,
    require_db_or_none,
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


class TestFmt:
    def test_none_renders_as_dashes(self):
        assert fmt(None) == "--"

    def test_rounds_to_requested_digits(self):
        assert fmt(3.14159, 2) == "3.14"
        assert fmt(3.14159, 0) == "3"


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
                "num_parameters": 0,
                "has_teardown_pair": 0,
                "raw_source": "",
                "framework": "pytest",
                "num_mocks": 0,
            }
            base.update(overrides)
            insert_fixture(conn, base)


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


class TestRenderStratifiedCategoricalTable:
    def test_renders_one_row_per_language(self):
        a_dist = {"python": {"has_mock": 90, "no_mock": 10}}
        other_dist = {"python": {"has_mock": 10, "no_mock": 90}}
        results = compute_stratified_categorical_balance(a_dist, other_dist, "has_mock")
        rendered = render_stratified_categorical_table(results)
        assert "| python |" in rendered

    def test_no_results_renders_placeholder_row(self):
        rendered = render_stratified_categorical_table({})
        assert "_(no language shared by both datasets)_" in rendered

    def test_insufficient_data_marked_per_language(self):
        a_dist = {"python": {"has_mock": 0, "no_mock": 0}}
        other_dist = {"python": {"has_mock": 5, "no_mock": 5}}
        results = compute_stratified_categorical_balance(a_dist, other_dist, "has_mock")
        rendered = render_stratified_categorical_table(results)
        assert "_insufficient data_" in rendered

    def test_chi2_failure_marked_as_test_failed_not_not_significant(self):
        """Regression: a real scipy failure (a whole category at 0 on both
        sides for one language -- e.g. neither dataset has any "teardown"
        fixtures in javascript) gets caught by compute_categorical_balance()
        and returned as p_value=1.0/is_balanced=True so callers don't
        crash. Rendered plainly, that reads as a genuine "not significant"
        result, which is wrong -- the test never ran. Reproduced directly
        via the same 3-category shape (setup/teardown/other) that triggers
        it for real in rq2.py's fixture_type_kind, not a synthetic error."""
        a_dist = {"javascript": {"setup": 3, "teardown": 0, "other": 2}}
        other_dist = {"javascript": {"setup": 1, "teardown": 0, "other": 4}}
        results = compute_stratified_categorical_balance(a_dist, other_dist, "fixture_type_kind")
        assert "error" in results["javascript"].details
        rendered = render_stratified_categorical_table(results)
        assert "_test failed" in rendered
        assert "| javascript | -- | -- | -- |" in rendered


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
