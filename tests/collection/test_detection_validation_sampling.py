"""Tests for collection/detection_validation_sampling.py.

Builds tiny synthetic db/{a,c}.db files under tmp_path (via the real
schema, initialise_db()) and checks the two DB queries' row shape, the
CSV writer's fixed schema, and run_detection_validation_sampling()'s
end-to-end wiring (population/sample counts, strata metadata, files
written). The Cochran sample-size math and stratified allocation
themselves are already covered by tests/collection/test_validation_
sampling.py -- these tests only check this module's own job: the SQL
queries and CSV/metadata output.

Mock-type (dummy/stub/spy/fake/mock category) classification was dropped
from manual validation entirely (2026-09) -- there is deliberately no
TestFetchMockTypeRows here anymore.
"""

from __future__ import annotations

import csv
import json
import sqlite3

from collection.db import (
    db_session,
    initialise_db,
    insert_fixture,
    upsert_repository,
    upsert_test_file,
)
from collection.detection_validation_sampling import (
    CSV_FIELDNAMES,
    _fetch_mock_detection_rows,
    _fetch_pytest_lifecycle_rows,
    run_detection_validation_sampling,
)


def _make_db(db_file, repos: list[dict]) -> None:
    """One repo per entry: {"language": str, "fixtures": [{"overrides":
    dict}]}. Mirrors the _make_db pattern used across tests/collection/
    test_rq*.py."""
    initialise_db(db_file)
    with db_session(db_file) as conn:
        for repo_idx, repo_spec in enumerate(repos):
            repo_id, _ = upsert_repository(
                conn,
                {
                    "github_id": repo_idx + 1,
                    "full_name": f"owner/repo{repo_idx}",
                    "language": repo_spec["language"],
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
            file_id = upsert_test_file(
                conn, repo_id, f"tests/test_{repo_idx}.txt", repo_spec["language"]
            )
            for i, fixture_spec in enumerate(repo_spec["fixtures"]):
                base = {
                    "file_id": file_id,
                    "repo_id": repo_id,
                    "name": f"fixture_{repo_idx}_{i}",
                    "fixture_type": "before_each",
                    "scope": "per_test",
                    "start_line": i + 1,
                    "end_line": i + 5,
                    "loc": 5,
                    "cyclomatic_complexity": 1,
                    "max_nesting_depth": 1,
                    "num_objects_instantiated": 0,
                    "num_external_calls": 0,
                    "num_comment_lines": 0,
                    "comment_density": 0.0,
                    "num_parameters": 0,
                    "has_teardown_pair": 0,
                    "fixture_type_kind": "setup",
                    "raw_source": "def f(): pass",
                    "framework": "pytest",
                    "num_mocks": 0,
                    "commit_sha": "abc123def456",
                }
                base.update(fixture_spec.get("overrides", {}))
                insert_fixture(conn, base)


class TestFetchMockDetectionRows:
    def test_only_fixtures_with_mocks_are_included(self, tmp_path):
        db_file = tmp_path / "a.db"
        _make_db(
            db_file,
            [
                {
                    "language": "python",
                    "fixtures": [
                        {"overrides": {"num_mocks": 2, "raw_source": "def f():\n    m = Mock()"}},
                        {"overrides": {"num_mocks": 0}},
                    ],
                }
            ],
        )
        with sqlite3.connect(db_file) as conn:
            rows = _fetch_mock_detection_rows(conn, "A")
        assert len(rows) == 1
        assert rows[0]["id"] == "A:python:1"
        assert rows[0]["language"] == "python"
        assert rows[0]["detected_label"] == "has_mock=True (num_mocks=2)"
        assert "Mock()" in rows[0]["raw_snippet"]
        assert rows[0]["source_url"].startswith("https://github.com/owner/repo0/blob/abc123def456/")

    def test_dataset_prefix_keeps_ids_unique_across_dbs(self, tmp_path):
        db_a = tmp_path / "a.db"
        db_c = tmp_path / "c.db"
        for db_file in (db_a, db_c):
            _make_db(db_file, [{"language": "java", "fixtures": [{"overrides": {"num_mocks": 1}}]}])
        with sqlite3.connect(db_a) as conn:
            rows_a = _fetch_mock_detection_rows(conn, "A")
        with sqlite3.connect(db_c) as conn:
            rows_c = _fetch_mock_detection_rows(conn, "C")
        # Same underlying row id (1) on both sides -- the dataset prefix is
        # what keeps the combined population's ids from colliding.
        assert rows_a[0]["id"] == "A:java:1"
        assert rows_c[0]["id"] == "C:java:1"


class TestFetchPytestLifecycleRows:
    def test_only_pytest_decorator_with_lifecycle_kind_included(self, tmp_path):
        db_file = tmp_path / "a.db"
        _make_db(
            db_file,
            [
                {
                    "language": "python",
                    "fixtures": [
                        {
                            "overrides": {
                                "fixture_type": "pytest_decorator",
                                "fixture_type_kind": "teardown",
                                "raw_source": "def f():\n    yield",
                            }
                        },
                        # Not pytest_decorator -- excluded regardless of kind.
                        {"overrides": {"fixture_type": "unittest_setup", "fixture_type_kind": "setup"}},
                        # pytest_decorator but 'other' -- excluded (not a
                        # real lifecycle outcome, see this function's docstring).
                        {
                            "overrides": {
                                "fixture_type": "pytest_decorator",
                                "fixture_type_kind": "other",
                            }
                        },
                    ],
                }
            ],
        )
        with sqlite3.connect(db_file) as conn:
            rows = _fetch_pytest_lifecycle_rows(conn, "A")
        assert len(rows) == 1
        assert rows[0]["lifecycle_kind"] == "teardown"
        assert rows[0]["detected_label"] == "teardown"
        assert rows[0]["id"] == "A:python:1"


class TestRunDetectionValidationSampling:
    def test_end_to_end_writes_two_csvs_and_metadata(self, tmp_path):
        db_a = tmp_path / "a.db"
        db_c = tmp_path / "c.db"
        for db_file in (db_a, db_c):
            _make_db(
                db_file,
                [
                    {
                        "language": "python",
                        "fixtures": [
                            {
                                "overrides": {
                                    "num_mocks": 1,
                                    "fixture_type": "pytest_decorator",
                                    "fixture_type_kind": "setup",
                                },
                            },
                            {
                                "overrides": {
                                    "fixture_type": "pytest_decorator",
                                    "fixture_type_kind": "teardown",
                                }
                            },
                        ],
                    }
                ],
            )

        output_root = tmp_path / "validation-samples"
        results = run_detection_validation_sampling(
            db_a=db_a, db_c=db_c, seed=42, output_root=output_root
        )

        assert {r.step for r in results} == {"mock-detection", "pytest-lifecycle"}
        for r in results:
            assert r.output_file.exists()
            with r.output_file.open(newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                assert reader.fieldnames == CSV_FIELDNAMES
                rows = list(reader)
            assert len(rows) == r.sample_size
            for row in rows:
                assert row["rater_label"] == ""
                assert row["notes"] == ""

        # mock-detection: 1 mocking fixture per repo, 2 repos (a+c) -> N=2.
        mock_detection = next(r for r in results if r.step == "mock-detection")
        assert mock_detection.population_size == 2
        assert mock_detection.sample_size == 2  # n >= N -> full population

        metadata_path = output_root / "sample_metadata_detection_validation.json"
        assert metadata_path.exists()
        metadata = json.loads(metadata_path.read_text())
        assert metadata["seed"] == 42
        assert metadata["confidence_level"] == 0.95
        assert metadata["margin_of_error"] == 0.05
        assert len(metadata["results"]) == 2

        assert (output_root / "README_detection_validation.md").exists()
        readme_text = (output_root / "README_detection_validation.md").read_text()
        assert "mock-type" not in readme_text
        assert "mock_type" not in readme_text

    def test_same_seed_reproduces_same_sample(self, tmp_path):
        db_a = tmp_path / "a.db"
        db_c = tmp_path / "c.db"
        for db_file in (db_a, db_c):
            _make_db(
                db_file,
                [
                    {
                        "language": "python",
                        "fixtures": [
                            {"overrides": {"num_mocks": i % 2, "name": f"f{i}"}}
                            for i in range(20)
                        ],
                    }
                ],
            )
        out1 = tmp_path / "run1"
        out2 = tmp_path / "run2"
        run_detection_validation_sampling(db_a=db_a, db_c=db_c, seed=7, output_root=out1)
        run_detection_validation_sampling(db_a=db_a, db_c=db_c, seed=7, output_root=out2)
        csv1 = (out1 / "mock-detection" / "mock_detection_sample.csv").read_text()
        csv2 = (out2 / "mock-detection" / "mock_detection_sample.csv").read_text()
        assert csv1 == csv2
