"""Tests for collection/dataset_summary.py.

Writes small synthetic stage CSVs under a tmp_path root (never touching
real datasets/ or toy-dataset/) and checks compute_summary()/write_summary()
read them back correctly -- counts, per-repo/per-file averages, and the
purity-gate acceptance rate for datasets A and B (absent for C, which has
no purity gate at all).
"""

from __future__ import annotations

import csv
from pathlib import Path

import yaml

from collection import paths
from collection.dataset_summary import compute_summary, write_summary


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_fixtures(path: Path, rows: list[dict]) -> None:
    _write_csv(
        path,
        rows,
        ["repo_name", "language", "file_path", "fixture_name"],
    )


class TestReposSection:
    def test_counts_by_language(self, tmp_path):
        _write_csv(
            paths.stage_dir("a", "repos", root=tmp_path) / "python_repo.csv",
            [{"repo_name": "o/r1"}, {"repo_name": "o/r2"}],
            ["repo_name"],
        )
        _write_csv(
            paths.stage_dir("a", "repos", root=tmp_path) / "java_repo.csv",
            [{"repo_name": "o/r3"}],
            ["repo_name"],
        )
        summary = compute_summary("a", root=tmp_path)
        assert summary["repos"] == {
            "total": 3,
            "by_language": {"java": 1, "python": 2},
        }

    def test_missing_repos_dir_is_empty_not_a_crash(self, tmp_path):
        summary = compute_summary("c", root=tmp_path)
        assert summary["repos"] == {"total": 0, "by_language": {}}


class TestFixturesSection:
    def test_totals_and_averages(self, tmp_path):
        # 2 repos, repo1 has 2 fixtures in 1 file, repo2 has 1 fixture in
        # its own file -> 3 fixtures / 2 repos = 1.5, 3 fixtures / 2 files = 1.5
        _write_fixtures(
            paths.stage_dir("c", "fixtures", root=tmp_path) / "python_fixtures.csv",
            [
                {"repo_name": "o/r1", "language": "python", "file_path": "t.py", "fixture_name": "f1"},
                {"repo_name": "o/r1", "language": "python", "file_path": "t.py", "fixture_name": "f2"},
                {"repo_name": "o/r2", "language": "python", "file_path": "t2.py", "fixture_name": "f3"},
            ],
        )
        summary = compute_summary("c", root=tmp_path)
        assert summary["fixtures"]["total"] == 3
        assert summary["fixtures"]["by_language"] == {"python": 3}
        assert summary["fixtures"]["avg_fixtures_per_repo"]["overall"] == 1.5
        assert summary["fixtures"]["avg_fixtures_per_file"]["overall"] == 1.5

    def test_multi_language_averaged_independently(self, tmp_path):
        _write_fixtures(
            paths.stage_dir("c", "fixtures", root=tmp_path) / "python_fixtures.csv",
            [
                {"repo_name": "o/r1", "language": "python", "file_path": "t.py", "fixture_name": "f1"},
                {"repo_name": "o/r1", "language": "python", "file_path": "t.py", "fixture_name": "f2"},
            ],
        )
        _write_fixtures(
            paths.stage_dir("c", "fixtures", root=tmp_path) / "java_fixtures.csv",
            [{"repo_name": "o/r2", "language": "java", "file_path": "T.java", "fixture_name": "f1"}],
        )
        summary = compute_summary("c", root=tmp_path)
        by_lang = summary["fixtures"]["avg_fixtures_per_repo"]["by_language"]
        assert by_lang == {"java": 1.0, "python": 2.0}


class TestPurityGateSection:
    def test_dataset_a_reads_fixture_repos_csv(self, tmp_path):
        repos_dir = paths.stage_dir("a", "fixtures", root=tmp_path) / "repos"
        _write_csv(
            repos_dir / "python_fixture_repos.csv",
            [
                {"repo_name": "o/r1", "accepted": "3", "rejected_mixed_test_diff": "1"},
                {"repo_name": "o/r2", "accepted": "2", "rejected_mixed_test_diff": "4"},
            ],
            ["repo_name", "accepted", "rejected_mixed_test_diff"],
        )
        summary = compute_summary("a", root=tmp_path)
        gate = summary["purity_gate"]
        assert gate["by_language"]["python"] == {
            "accepted": 5,
            "rejected": 5,
            "acceptance_rate": 0.5,
        }
        assert gate["acceptance_rate"] == 0.5

    def test_dataset_b_reads_purity_stats_csv(self, tmp_path):
        _write_csv(
            paths.stage_dir("b", "test-commits", root=tmp_path) / "python_purity_stats.csv",
            [{"language": "python", "commits_accepted": "8", "commits_rejected": "2"}],
            ["language", "commits_accepted", "commits_rejected"],
        )
        summary = compute_summary("b", root=tmp_path)
        gate = summary["purity_gate"]
        assert gate["by_language"]["python"] == {
            "accepted": 8,
            "rejected": 2,
            "acceptance_rate": 0.8,
        }
        assert gate["acceptance_rate"] == 0.8

    def test_dataset_b_purity_stats_file_not_misread_as_test_commits(self, tmp_path):
        """python_purity_stats.csv and python_human_test_commit.csv share a
        directory and a leading filename token -- the test-commit reader
        must not pick up the purity file as if it were commit rows."""
        tc_dir = paths.stage_dir("b", "test-commits", root=tmp_path)
        _write_csv(
            tc_dir / "python_human_test_commit.csv",
            [{"repo_name": "o/r1", "commit_sha": "abc"}],
            ["repo_name", "commit_sha"],
        )
        _write_csv(
            tc_dir / "python_purity_stats.csv",
            [{"language": "python", "commits_accepted": "1", "commits_rejected": "0"}],
            ["language", "commits_accepted", "commits_rejected"],
        )
        summary = compute_summary("b", root=tmp_path)
        assert summary["test_commits"]["by_language"] == {"python": 1}

    def test_dataset_c_has_no_purity_gate_section(self, tmp_path):
        """Dataset C has no test-commits stage and no purity gate --
        section must be absent entirely, not zeroed out."""
        summary = compute_summary("c", root=tmp_path)
        assert "purity_gate" not in summary
        assert "test_commits" not in summary

    def test_absent_when_no_source_file_exists_yet(self, tmp_path):
        """A run predating this instrumentation (or dataset b before any
        repo has been processed) has no purity source file -- must come
        back absent, not a zeroed/fake section."""
        paths.stage_dir("b", "test-commits", root=tmp_path).mkdir(parents=True)
        summary = compute_summary("b", root=tmp_path)
        assert "purity_gate" not in summary


class TestWriteSummary:
    def test_writes_valid_yaml_at_expected_path(self, tmp_path):
        _write_csv(
            paths.stage_dir("c", "repos", root=tmp_path) / "python_repo.csv",
            [{"repo_name": "o/r1"}],
            ["repo_name"],
        )
        out_path = write_summary("c", root=tmp_path)
        assert out_path == paths.summary_path("c", root=tmp_path)
        assert out_path.exists()
        with out_path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        assert data["dataset"] == "c"
        assert data["repos"]["total"] == 1
        assert "generated_at" in data
        assert "sampling_seed" in data

    def test_sampling_seed_only_set_for_dataset_c(self, tmp_path):
        assert compute_summary("a", root=tmp_path)["sampling_seed"] is None
        assert compute_summary("b", root=tmp_path)["sampling_seed"] is None
        assert compute_summary("c", root=tmp_path)["sampling_seed"] is not None
