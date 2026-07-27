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
    generate_report,
    load_dataset_metrics,
    write_report,
)


def _make_db(root, dataset: str, files: list[dict]) -> None:
    """Create db/{dataset}.db under `root` with one repo and one test_file
    per entry in `files`.

    Each `files` entry: {"language": str, "fixtures": [fixture_spec, ...]}.
    Each fixture_spec: {"overrides": {...fixture column overrides...},
    "mocks": [mock_override_dict, ...]} -- both keys optional.
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
        assert "## A vs B: Dataset A (agent-authored) vs Dataset B (human-authored, contemporary)" in report
        assert "## A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)" in report
        # B summary, C summary, A-vs-B comparison, A-vs-C comparison: 4 total.
        assert report.count("Not available -- db not collected yet.") == 4

    def test_a_vs_b_comparison_renders_significant_difference(self, tmp_path):
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
            "b",
            [
                {
                    "language": "python",
                    "fixtures": [{"overrides": {"num_mocks": v}} for v in [0, 0, 1, 0, 0, 1, 0, 0, 1, 0]],
                }
            ],
        )
        report = generate_report(db_root=tmp_path)
        comparison_section = report.split("**Continuous metrics (Mann-Whitney U")[1]
        num_mocks_line = next(
            line for line in comparison_section.splitlines() if line.startswith("| num_mocks |")
        )
        assert num_mocks_line.strip().endswith("| yes |")

    def test_categorical_insufficient_data_when_no_mock_usages(self, tmp_path):
        # No mock_usages rows at all in either dataset -> framework/category insufficient data.
        _make_db(tmp_path, "a", [{"language": "python", "fixtures": [{"overrides": {"num_mocks": 0}}]}])
        _make_db(tmp_path, "c", [{"language": "python", "fixtures": [{"overrides": {"num_mocks": 0}}]}])
        report = generate_report(db_root=tmp_path)
        framework_line = next(
            line for line in report.splitlines() if line.startswith("| framework |")
        )
        assert "_insufficient data_" in framework_line


class TestWriteReport:
    def test_writes_file_matching_generate_report(self, tmp_path):
        _make_db(tmp_path, "a", [{"language": "python", "fixtures": [{"overrides": {"num_mocks": 1}, "mocks": [{}]}]}])
        out_dir = tmp_path / "out"
        path = write_report(out_dir, db_root=tmp_path)
        assert path == out_dir / "rq3.md"
        assert path.read_text() == generate_report(db_root=tmp_path)
