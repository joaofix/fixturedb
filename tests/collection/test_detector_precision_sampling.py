"""Tests for collection/detector_precision_sampling.py.

Builds tiny synthetic db/{a,c_sampled}.db files under tmp_path (via the
real schema, initialise_db()) and checks each case's DB query, the pure
helper functions (URL building, context slicing, import extraction)
against fixed in-memory content (no network), and
run_detector_precision_sampling()'s end-to-end wiring.
_fetch_file_content() (the only network call) is mocked throughout.
"""

from __future__ import annotations

import csv
import sqlite3
from unittest.mock import patch

from collection.db import (
    db_session,
    initialise_db,
    insert_fixture,
    insert_mock_usage,
    upsert_repository,
    upsert_test_file,
)
from collection.detector_precision_sampling import (
    CSV_FIELDNAMES,
    SAMPLE_SIZE_PER_CASE,
    _build_plain_github_url,
    _Candidate,
    _enrich_candidate,
    _extract_test_related_imports,
    _fetch_before_after_candidates,
    _fetch_mock_detection_candidates,
    _fetch_pytest_scope_candidates,
    _fetch_unittest_detection_candidates,
    _sample_case,
    _slice_with_context,
    run_detector_precision_sampling,
)


def _make_db(db_file, language: str, fixtures: list[dict]) -> None:
    """One repo, one test_file, one fixture per entry in `fixtures` (each
    a dict of column overrides, plus an optional "mocks" list of
    mock_usages overrides)."""
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
        ext = {"python": "py", "java": "java", "javascript": "js", "typescript": "ts"}[language]
        file_id = upsert_test_file(conn, repo_id, f"tests/test_foo.{ext}", language)
        for i, overrides in enumerate(fixtures):
            mocks = overrides.pop("mocks", None)
            base = {
                "file_id": file_id,
                "repo_id": repo_id,
                "name": "setUp",
                "fixture_type": "unittest_setup",
                "scope": "per_test",
                "start_line": i * 20 + 1,
                "end_line": i * 20 + 3,
                "loc": 2,
                "cyclomatic_complexity": 1,
                "max_nesting_depth": 1,
                "num_objects_instantiated": 0,
                "num_external_calls": 0,
                "num_comment_lines": 0,
                "comment_density": 0.0,
                "num_parameters": 0,
                "has_teardown_pair": 0,
                "fixture_role": "setup",
                "raw_source": "def setUp(self):\n    pass",
                "framework": "unittest",
                "num_mocks": 0,
                "commit_sha": f"sha{i}",
            }
            base.update(overrides)
            fixture_id = insert_fixture(conn, base)
            for mock in mocks or []:
                insert_mock_usage(
                    conn,
                    {
                        "fixture_id": fixture_id,
                        "repo_id": repo_id,
                        "framework": mock.get("framework", "unittest_mock"),
                        "category": mock.get("category", "mock"),
                        "target_identifier": mock.get("target_identifier", "SomeClient"),
                        "raw_snippet": mock.get("raw_snippet", "Mock()"),
                    },
                )


class TestFetchMockDetectionCandidates:
    def test_only_fixtures_with_mocks_included(self, tmp_path):
        db_file = tmp_path / "a.db"
        _make_db(
            db_file,
            "python",
            [
                {"num_mocks": 1, "mocks": [{"framework": "unittest_mock", "target_identifier": "Client"}]},
                {"num_mocks": 0},
            ],
        )
        with sqlite3.connect(db_file) as conn:
            rows = _fetch_mock_detection_candidates(conn, "A")
        assert len(rows) == 1
        assert "unittest_mock" in rows[0].detector_reported
        assert "Client" in rows[0].detector_reported

    def test_all_four_languages_eligible(self, tmp_path):
        for language in ("python", "java", "javascript", "typescript"):
            db_file = tmp_path / f"{language}.db"
            _make_db(db_file, language, [{"num_mocks": 1, "mocks": [{}]}])
            with sqlite3.connect(db_file) as conn:
                rows = _fetch_mock_detection_candidates(conn, "A")
            assert len(rows) == 1
            assert rows[0].language == language


class TestFetchPytestScopeCandidates:
    def test_excludes_plain_setup(self, tmp_path):
        """Plain `setup` is a fixed-rule assignment, not a judgment call
        -- must never appear in this case's population."""
        db_file = tmp_path / "a.db"
        _make_db(
            db_file,
            "python",
            [
                {"fixture_type": "pytest_decorator", "fixture_role": "setup"},
                {"fixture_type": "pytest_decorator", "fixture_role": "teardown"},
                {"fixture_type": "pytest_decorator", "fixture_role": "setup_and_teardown"},
            ],
        )
        with sqlite3.connect(db_file) as conn:
            rows = _fetch_pytest_scope_candidates(conn, "A")
        assert len(rows) == 2
        assert {r.detector_reported for r in rows} == {"teardown", "setup and teardown"}

    def test_excludes_non_pytest_decorator(self, tmp_path):
        db_file = tmp_path / "a.db"
        _make_db(
            db_file,
            "python",
            [{"fixture_type": "unittest_setup", "fixture_role": "teardown"}],
        )
        with sqlite3.connect(db_file) as conn:
            rows = _fetch_pytest_scope_candidates(conn, "A")
        assert rows == []


class TestFetchUnittestDetectionCandidates:
    def test_all_eight_names_included_no_restriction(self, tmp_path):
        """Unlike validation_v1's 6-name restriction, this case covers
        all 8 fixture_type='unittest_setup' names, including the async
        pair."""
        names = (
            "setUp",
            "tearDown",
            "setUpClass",
            "tearDownClass",
            "setUpModule",
            "tearDownModule",
            "asyncSetUp",
            "asyncTearDown",
        )
        db_file = tmp_path / "a.db"
        _make_db(db_file, "python", [{"name": n} for n in names])
        with sqlite3.connect(db_file) as conn:
            rows = _fetch_unittest_detection_candidates(conn, "A")
        assert {r.extra["method_name"] for r in rows} == set(names)
        assert len(rows) == 8

    def test_non_python_excluded(self, tmp_path):
        db_file = tmp_path / "a.db"
        _make_db(db_file, "java", [{"name": "setUp"}])
        with sqlite3.connect(db_file) as conn:
            rows = _fetch_unittest_detection_candidates(conn, "A")
        assert rows == []


class TestFetchBeforeAfterCandidates:
    def test_only_mocha_before_after_js_ts(self, tmp_path):
        db_file = tmp_path / "a.db"
        _make_db(
            db_file,
            "javascript",
            [
                {"fixture_type": "mocha_before", "name": "before"},
                {"fixture_type": "mocha_after", "name": "after"},
                {"fixture_type": "before_each", "name": "beforeEach"},
            ],
        )
        with sqlite3.connect(db_file) as conn:
            rows = _fetch_before_after_candidates(conn, "A")
        assert len(rows) == 2

    def test_python_and_java_excluded(self, tmp_path):
        for language in ("python", "java"):
            db_file = tmp_path / f"{language}.db"
            _make_db(db_file, language, [{"fixture_type": "mocha_before"}])
            with sqlite3.connect(db_file) as conn:
                rows = _fetch_before_after_candidates(conn, "A")
            assert rows == []


class TestBuildPlainGithubUrl:
    def test_inserts_plain_1_before_anchor(self):
        url = _build_plain_github_url("owner/repo", "abc123", "tests/test_foo.py", 10, 15)
        assert url == "https://github.com/owner/repo/blob/abc123/tests/test_foo.py?plain=1#L10-L15"

    def test_equal_start_end_still_uses_range_anchor(self):
        """Matches `corpus_utils._build_github_url()`'s existing
        convention: start_line > 0 and end_line >= start_line always
        produces a range anchor, even when they're equal."""
        url = _build_plain_github_url("owner/repo", "abc123", "tests/test_foo.py", 10, 10)
        assert url == "https://github.com/owner/repo/blob/abc123/tests/test_foo.py?plain=1#L10-L10"

    def test_missing_required_field_returns_empty(self):
        assert _build_plain_github_url("", "abc123", "tests/test_foo.py", 10, 10) == ""


class TestSliceWithContext:
    def test_includes_five_lines_before_and_after(self):
        content = "\n".join(f"line{i}" for i in range(1, 21))  # lines 1..20
        snippet = _slice_with_context(content, start_line=10, end_line=12, context=5)
        assert "5: line5" in snippet
        assert "9: line9" in snippet
        assert "10: line10" in snippet
        assert "12: line12" in snippet
        assert "13: line13" in snippet
        assert "17: line17" in snippet
        assert "4: line4" not in snippet
        assert "18: line18" not in snippet

    def test_clamps_to_file_bounds(self):
        content = "\n".join(f"line{i}" for i in range(1, 4))  # lines 1..3
        snippet = _slice_with_context(content, start_line=1, end_line=2, context=5)
        assert "1: line1" in snippet
        assert "3: line3" in snippet
        assert "0:" not in snippet


class TestExtractTestRelatedImports:
    def test_python_filters_to_test_keywords(self):
        content = (
            "import os\n"
            "import unittest\n"
            "from unittest import mock\n"
            "import json\n"
        )
        result = _extract_test_related_imports(content, "python")
        assert "import unittest" in result
        assert "from unittest import mock" in result
        assert "import os" not in result
        assert "import json" not in result

    def test_js_filters_to_test_keywords(self):
        content = (
            "import React from 'react';\n"
            "import { beforeEach } from 'mocha';\n"
            "const sinon = require('sinon');\n"
        )
        result = _extract_test_related_imports(content, "javascript")
        assert "mocha" in result
        assert "sinon" in result
        assert "react" not in result.lower()

    def test_no_match_returns_placeholder(self):
        result = _extract_test_related_imports("import os\n", "python")
        assert result == "(no test-related imports found)"


class TestEnrichCandidate:
    def _candidate(self, **overrides):
        base = dict(
            case="mock_detection",
            dataset="A",
            language="python",
            repo_full_name="owner/repo",
            commit_sha="abc123",
            relative_path="tests/test_foo.py",
            start_line=2,
            end_line=3,
            raw_source="def setUp(self):\n    pass",
            detector_reported="unittest_mock: Client",
        )
        base.update(overrides)
        return _Candidate(**base)

    def test_mock_detection_keeps_detector_reported_uses_fetched_context(self):
        file_content = "import unittest\n\nclass T:\n    def setUp(self):\n        pass\n"
        with patch(
            "collection.detector_precision_sampling._fetch_file_content",
            return_value=file_content,
        ):
            row = _enrich_candidate(self._candidate())
        assert row["detector_reported"] == "unittest_mock: Client"
        assert "4: " in row["source_with_context"]

    def test_fetch_failure_falls_back_to_raw_source(self):
        with patch(
            "collection.detector_precision_sampling._fetch_file_content",
            return_value=None,
        ):
            row = _enrich_candidate(self._candidate())
        assert row["source_with_context"] == "def setUp(self):\n    pass"

    def test_unittest_detection_builds_class_and_imports(self):
        file_content = (
            "import unittest\n"
            "\n"
            "class MyTest(unittest.TestCase):\n"
            "    def setUp(self):\n"
            "        pass\n"
        )
        candidate = self._candidate(
            case="unittest_detection",
            start_line=4,
            end_line=5,
            detector_reported="",
            extra={"method_name": "setUp"},
        )
        with patch(
            "collection.detector_precision_sampling._fetch_file_content",
            return_value=file_content,
        ):
            row = _enrich_candidate(candidate)
        assert "class MyTest(unittest.TestCase):" in row["detector_reported"]
        assert "import unittest" in row["detector_reported"]

    def test_before_after_reports_imports_only(self):
        file_content = "const { before, after } = require('mocha');\n"
        candidate = self._candidate(
            case="before_after", language="javascript", detector_reported=""
        )
        with patch(
            "collection.detector_precision_sampling._fetch_file_content",
            return_value=file_content,
        ):
            row = _enrich_candidate(candidate)
        assert "mocha" in row["detector_reported"]

    def test_github_url_has_plain_1(self):
        with patch(
            "collection.detector_precision_sampling._fetch_file_content",
            return_value=None,
        ):
            row = _enrich_candidate(self._candidate())
        assert "?plain=1#L2-L3" in row["github_url"]

    def test_label_and_notes_start_empty(self):
        with patch(
            "collection.detector_precision_sampling._fetch_file_content",
            return_value=None,
        ):
            row = _enrich_candidate(self._candidate())
        assert row["label"] == ""
        assert row["notes"] == ""


class TestSampleCase:
    def _candidates(self, n, dataset="A", language="python"):
        return [
            _Candidate(
                case="mock_detection",
                dataset=dataset,
                language=language,
                repo_full_name="owner/repo",
                commit_sha=f"sha{i}",
                relative_path="tests/test_foo.py",
                start_line=i + 1,
                end_line=i + 2,
                raw_source="x",
            )
            for i in range(n)
        ]

    def test_shortfall_flag_when_population_below_target(self):
        candidates = self._candidates(10)
        sampled, _strata, shortfall = _sample_case("mock_detection", candidates, ("dataset",), seed=42)
        assert shortfall is True
        assert len(sampled) == 10  # all included

    def test_no_shortfall_when_population_meets_target(self):
        candidates = self._candidates(SAMPLE_SIZE_PER_CASE + 50)
        sampled, _strata, shortfall = _sample_case("mock_detection", candidates, ("dataset",), seed=42)
        assert shortfall is False
        assert len(sampled) == SAMPLE_SIZE_PER_CASE

    def test_stratifies_proportionally_by_dataset(self):
        candidates = self._candidates(20, dataset="A") + self._candidates(180, dataset="C")
        sampled, strata, shortfall = _sample_case("mock_detection", candidates, ("dataset",), seed=42)
        assert shortfall is False
        assert len(sampled) == SAMPLE_SIZE_PER_CASE
        by_dataset = {s["key"]["dataset"]: s["sample_size"] for s in strata}
        # 20/200 of 100 = 10, 180/200 of 100 = 90
        assert by_dataset["A"] == 10
        assert by_dataset["C"] == 90

    def test_deterministic_given_same_seed(self):
        candidates = self._candidates(150)
        sampled_1, _, _ = _sample_case("mock_detection", candidates, ("dataset",), seed=42)
        sampled_2, _, _ = _sample_case("mock_detection", candidates, ("dataset",), seed=42)
        assert [c.commit_sha for c in sampled_1] == [c.commit_sha for c in sampled_2]


class TestRunDetectorPrecisionSampling:
    def test_end_to_end_writes_all_four_csvs_with_correct_schema(self, tmp_path):
        db_a = tmp_path / "a.db"
        db_c = tmp_path / "c_sampled.db"
        _make_db(
            db_a,
            "python",
            [
                {"num_mocks": 1, "mocks": [{}]},
                {"fixture_type": "pytest_decorator", "fixture_role": "teardown"},
                {"name": "setUp"},
            ],
        )
        _make_db(db_c, "javascript", [{"fixture_type": "mocha_before"}])

        output_root = tmp_path / "validation-samples"
        with patch(
            "collection.detector_precision_sampling._fetch_file_content",
            return_value=None,
        ):
            results = run_detector_precision_sampling(
                db_a=db_a, db_c_sampled=db_c, seed=42, output_root=output_root
            )

        assert {r.case for r in results} == {
            "mock_detection",
            "pytest_scope",
            "unittest_detection",
            "before_after",
        }
        for r in results:
            assert r.output_file.exists()
            assert r.shortfall is True  # every synthetic population is tiny
            with r.output_file.open(newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                assert reader.fieldnames == CSV_FIELDNAMES
                rows = list(reader)
            for row in rows:
                assert row["label"] == ""
                assert row["notes"] == ""

        assert (output_root / "sample_metadata_detector_precision_validation.json").exists()
        assert (output_root / "README_detector_precision_validation.md").exists()

    def test_does_not_mix_up_cases_across_csvs(self, tmp_path):
        db_a = tmp_path / "a.db"
        db_c = tmp_path / "c_sampled.db"
        # fixture_type deliberately distinct from unittest_setup/pytest_decorator/
        # mocha_before/mocha_after so this row can't double-count into any
        # other case's population.
        _make_db(
            db_a,
            "python",
            [{"fixture_type": "junit_before", "num_mocks": 1, "mocks": [{}]}],
        )
        _make_db(db_c, "python", [{"fixture_type": "pytest_decorator", "fixture_role": "teardown"}])

        output_root = tmp_path / "validation-samples"
        with patch(
            "collection.detector_precision_sampling._fetch_file_content",
            return_value=None,
        ):
            results = run_detector_precision_sampling(
                db_a=db_a, db_c_sampled=db_c, seed=42, output_root=output_root
            )

        by_case = {r.case: r for r in results}
        assert by_case["mock_detection"].population_size == 1
        assert by_case["pytest_scope"].population_size == 1
        assert by_case["unittest_detection"].population_size == 0
        assert by_case["before_after"].population_size == 0
