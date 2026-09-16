"""Tests for collection/unittest_heuristic_validation_sampling.py.

Builds tiny synthetic db/{a,c}.db files under tmp_path (via the real
schema, initialise_db()) and checks the DB query's row shape, the
class-header re-parsing logic (against fixed in-memory file content, no
network), and run_unittest_heuristic_sampling()'s end-to-end wiring.
_fetch_file_content() (the only network call in this module) is mocked
throughout -- no real HTTP requests in this test file. The Cochran
sample-size math and stratified allocation themselves are already
covered by tests/collection/test_validation_sampling.py.
"""

from __future__ import annotations

import csv
import sqlite3
from unittest.mock import patch

from collection.db import (
    db_session,
    initialise_db,
    insert_fixture,
    upsert_repository,
    upsert_test_file,
)
from collection.detection_validation_sampling import CSV_FIELDNAMES
from collection.unittest_heuristic_validation_sampling import (
    UNITTEST_LIFECYCLE_NAMES,
    _build_raw_snippet,
    _fetch_unittest_heuristic_candidates,
    _find_enclosing_class_header,
    run_unittest_heuristic_sampling,
)


def _make_db(db_file, language: str, fixtures: list[dict]) -> None:
    """One repo, one test_file, one fixture per entry in `fixtures` (each
    a dict of column overrides). Mirrors the _make_db pattern used across
    tests/collection/test_rq*.py."""
    initialise_db(db_file)
    with db_session(db_file) as conn:
        repo_id, _ = upsert_repository(
            conn,
            {
                "github_id": 1,
                "full_name": "owner/repo",
                "language": language,
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
        file_id = upsert_test_file(conn, repo_id, "tests/test_foo.py", language)
        for i, overrides in enumerate(fixtures):
            base = {
                "file_id": file_id,
                "repo_id": repo_id,
                "name": "setUp",
                "fixture_type": "unittest_setup",
                "scope": "per_test",
                "start_line": i + 1,
                "end_line": i + 3,
                "loc": 2,
                "cyclomatic_complexity": 1,
                "max_nesting_depth": 1,
                "num_objects_instantiated": 0,
                "num_external_calls": 0,
                "num_comment_lines": 0,
                "comment_density": 0.0,
                "num_parameters": 0,
                "has_teardown_pair": 0,
                "fixture_type_kind": "setup",
                "raw_source": "def setUp(self):\n    pass",
                "framework": "unittest",
                "num_mocks": 0,
                "commit_sha": "abc123def456",
            }
            base.update(overrides)
            insert_fixture(conn, base)


class TestFetchUnittestHeuristicCandidates:
    def test_all_six_lifecycle_names_included(self, tmp_path):
        db_file = tmp_path / "a.db"
        _make_db(
            db_file,
            "python",
            [{"name": name, "raw_source": f"def {name}(self): pass"} for name in UNITTEST_LIFECYCLE_NAMES],
        )
        with sqlite3.connect(db_file) as conn:
            rows = _fetch_unittest_heuristic_candidates(conn, "A")
        assert {r["name"] for r in rows} == set(UNITTEST_LIFECYCLE_NAMES)
        assert len(rows) == 6

    def test_async_setup_teardown_excluded(self, tmp_path):
        db_file = tmp_path / "a.db"
        _make_db(
            db_file,
            "python",
            [
                {"name": "setUp"},
                {"name": "asyncSetUp"},
                {"name": "asyncTearDown"},
            ],
        )
        with sqlite3.connect(db_file) as conn:
            rows = _fetch_unittest_heuristic_candidates(conn, "A")
        assert [r["name"] for r in rows] == ["setUp"]

    def test_other_fixture_types_excluded(self, tmp_path):
        db_file = tmp_path / "a.db"
        _make_db(
            db_file,
            "python",
            [
                {"name": "setUp"},
                {"name": "setup_method", "fixture_type": "pytest_class_method"},
            ],
        )
        with sqlite3.connect(db_file) as conn:
            rows = _fetch_unittest_heuristic_candidates(conn, "A")
        assert len(rows) == 1
        assert rows[0]["name"] == "setUp"

    def test_non_python_language_excluded(self, tmp_path):
        db_file = tmp_path / "a.db"
        _make_db(db_file, "java", [{"name": "setUp"}])
        with sqlite3.connect(db_file) as conn:
            rows = _fetch_unittest_heuristic_candidates(conn, "A")
        assert rows == []

    def test_id_embeds_dataset_and_language(self, tmp_path):
        db_file = tmp_path / "a.db"
        _make_db(db_file, "python", [{"name": "setUp"}])
        with sqlite3.connect(db_file) as conn:
            rows = _fetch_unittest_heuristic_candidates(conn, "A")
        assert rows[0]["id"] == "A:python:1"


class TestFindEnclosingClassHeader:
    def test_finds_single_base_class_header(self):
        content = (
            "import unittest\n"
            "\n"
            "class MyTest(unittest.TestCase):\n"
            "    def setUp(self):\n"
            "        self.x = 1\n"
        )
        header = _find_enclosing_class_header(content, "setUp", method_start_line=4)
        assert header == "class MyTest(unittest.TestCase):"

    def test_finds_multiple_base_classes(self):
        content = (
            "class MyTest(BaseA, BaseB):\n"
            "    def setUp(self):\n"
            "        pass\n"
        )
        header = _find_enclosing_class_header(content, "setUp", method_start_line=2)
        assert header == "class MyTest(BaseA, BaseB):"

    def test_module_level_function_has_no_class_header(self):
        content = "def setUpModule():\n    pass\n"
        header = _find_enclosing_class_header(content, "setUpModule", method_start_line=1)
        assert header is None

    def test_line_mismatch_returns_none(self):
        """The method exists but not at the expected line (file drifted
        since extraction) -- must not silently match the wrong method."""
        content = (
            "class MyTest(unittest.TestCase):\n"
            "    def setUp(self):\n"
            "        pass\n"
        )
        header = _find_enclosing_class_header(content, "setUp", method_start_line=99)
        assert header is None

    def test_name_mismatch_returns_none(self):
        content = (
            "class MyTest(unittest.TestCase):\n"
            "    def tearDown(self):\n"
            "        pass\n"
        )
        header = _find_enclosing_class_header(content, "setUp", method_start_line=2)
        assert header is None


class TestBuildRawSnippet:
    def test_fetch_success_includes_class_header(self):
        candidate = {
            "repo_full_name": "owner/repo",
            "commit_sha": "abc123",
            "relative_path": "tests/test_foo.py",
            "name": "setUp",
            "start_line": 2,
            "raw_source": "def setUp(self):\n    self.x = 1",
        }
        file_content = (
            "class MyTest(unittest.TestCase):\n"
            "    def setUp(self):\n"
            "        self.x = 1\n"
        )
        with patch(
            "collection.unittest_heuristic_validation_sampling._fetch_file_content",
            return_value=file_content,
        ):
            snippet = _build_raw_snippet(candidate)
        assert "class MyTest(unittest.TestCase):" in snippet
        assert "def setUp(self):" in snippet

    def test_fetch_failure_falls_back_to_bare_method(self):
        candidate = {
            "repo_full_name": "owner/repo",
            "commit_sha": "abc123",
            "relative_path": "tests/test_foo.py",
            "name": "setUp",
            "start_line": 2,
            "raw_source": "def setUp(self):\n    self.x = 1",
        }
        with patch(
            "collection.unittest_heuristic_validation_sampling._fetch_file_content",
            return_value=None,
        ):
            snippet = _build_raw_snippet(candidate)
        assert snippet == candidate["raw_source"]


class TestRunUnittestHeuristicSampling:
    def test_end_to_end_writes_csv_with_correct_schema(self, tmp_path):
        db_a = tmp_path / "a.db"
        db_c = tmp_path / "c.db"
        _make_db(db_a, "python", [{"name": name} for name in UNITTEST_LIFECYCLE_NAMES])
        _make_db(db_c, "python", [{"name": name} for name in UNITTEST_LIFECYCLE_NAMES])

        output_root = tmp_path / "validation-samples"
        with patch(
            "collection.unittest_heuristic_validation_sampling._fetch_file_content",
            return_value=None,
        ):
            result = run_unittest_heuristic_sampling(
                db_a=db_a, db_c=db_c, seed=42, output_root=output_root
            )

        assert result.step == "unittest-heuristic"
        assert result.output_file == output_root / "unittest-heuristic" / "unittest_heuristic_sample.csv"
        assert result.output_file.exists()
        assert result.population_size == 12  # 6 names x 2 datasets
        assert result.sample_size == 12  # n >= N -> full population

        with result.output_file.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            assert reader.fieldnames == CSV_FIELDNAMES
            rows = list(reader)
        assert len(rows) == 12
        for row in rows:
            assert row["rater_label"] == ""
            assert row["notes"] == ""
            assert row["detected_label"] in UNITTEST_LIFECYCLE_NAMES

    def test_does_not_touch_other_steps_folders(self, tmp_path):
        db_a = tmp_path / "a.db"
        db_c = tmp_path / "c.db"
        _make_db(db_a, "python", [{"name": "setUp"}])
        _make_db(db_c, "python", [{"name": "setUp"}])

        output_root = tmp_path / "validation-samples"
        (output_root / "mock-detection").mkdir(parents=True)
        sentinel = output_root / "mock-detection" / "mock_detection_sample.csv"
        sentinel.write_text("untouched", encoding="utf-8")

        with patch(
            "collection.unittest_heuristic_validation_sampling._fetch_file_content",
            return_value=None,
        ):
            run_unittest_heuristic_sampling(db_a=db_a, db_c=db_c, seed=42, output_root=output_root)

        assert sentinel.read_text(encoding="utf-8") == "untouched"

    def test_stratified_by_dataset(self, tmp_path):
        """A larger, imbalanced population (2 from A, 10 from C) must
        still sample proportionally by dataset, not pooled blind."""
        db_a = tmp_path / "a.db"
        db_c = tmp_path / "c.db"
        _make_db(db_a, "python", [{"name": "setUp"}, {"name": "tearDown"}])
        _make_db(
            db_c,
            "python",
            [{"name": "setUp"} for _ in range(10)],
        )

        output_root = tmp_path / "validation-samples"
        with patch(
            "collection.unittest_heuristic_validation_sampling._fetch_file_content",
            return_value=None,
        ):
            result = run_unittest_heuristic_sampling(
                db_a=db_a, db_c=db_c, seed=42, output_root=output_root
            )

        assert result.population_size == 12
        strata_by_dataset = {tuple(s["key"].values()): s for s in result.strata}
        assert strata_by_dataset[("A",)]["population_size"] == 2
        assert strata_by_dataset[("C",)]["population_size"] == 10
