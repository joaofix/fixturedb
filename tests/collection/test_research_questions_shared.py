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
    fetch_categorical_column,
    fetch_continuous_column,
    fmt,
    require_db_or_none,
    summarize_continuous,
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
