"""Tests for collection/dataset_summary.py.

Writes small synthetic stage CSVs under a tmp_path root (never touching
real datasets/ or toy-dataset/) and checks compute_summary()/write_summary()
read them back correctly -- counts, per-repo/per-file averages (including
the unconditional avg_fixtures_per_repo_overall, which must include repos
that yielded zero fixtures, unlike avg_fixtures_per_repo_with_fixtures),
and the purity-gate acceptance rate for datasets A and B (absent for C,
which has no purity gate at all).
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
    def test_counts_by_repo_language(self, tmp_path):
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
            "by_repo_language": {"java": 1, "python": 2},
        }

    def test_missing_repos_dir_is_empty_not_a_crash(self, tmp_path):
        summary = compute_summary("c", root=tmp_path)
        assert summary["repos"] == {"total": 0, "by_repo_language": {}}


class TestFixturesSection:
    def test_totals_and_with_fixtures_average(self, tmp_path):
        # 2 repos, repo1 has 2 fixtures in 1 file, repo2 has 1 fixture in
        # its own file -> 3 fixtures / 2 repos-with-fixtures = 1.5
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
        assert summary["fixtures"]["by_fixture_language"] == {"python": 3}
        assert summary["fixtures"]["repos_with_at_least_one_fixture"] == 2
        assert summary["fixtures"]["avg_fixtures_per_repo_with_fixtures"]["overall"] == 1.5
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
        by_lang = summary["fixtures"]["avg_fixtures_per_repo_with_fixtures"]["by_fixture_language"]
        assert by_lang == {"java": 1.0, "python": 2.0}

    def test_avg_fixtures_per_repo_overall_includes_zero_yield_repos(self, tmp_path):
        """Regression: avg_fixtures_per_repo_with_fixtures silently divides
        by only the repos that appear in fixtures.csv -- a repo scanned but
        yielding zero fixtures never gets a row there, so it vanishes from
        that average instead of pulling it down. avg_fixtures_per_repo_overall
        must divide by the full repo pool (repos.total) instead, so a
        reviewer sees the true corpus-wide yield, not one inflated by
        silently excluding every unproductive repo."""
        # 4 repos in the pool, but only 1 produced fixtures (3 of them).
        _write_csv(
            paths.stage_dir("c", "repos", root=tmp_path) / "python_repo.csv",
            [{"repo_name": f"o/r{i}"} for i in range(4)],
            ["repo_name"],
        )
        _write_fixtures(
            paths.stage_dir("c", "fixtures", root=tmp_path) / "python_fixtures.csv",
            [
                {"repo_name": "o/r0", "language": "python", "file_path": "t.py", "fixture_name": f"f{i}"}
                for i in range(3)
            ],
        )
        summary = compute_summary("c", root=tmp_path)
        fx = summary["fixtures"]
        assert fx["repos_with_at_least_one_fixture"] == 1
        # Misleading, conditional-on-yield number: 3 fixtures / 1 repo = 3.0
        assert fx["avg_fixtures_per_repo_with_fixtures"]["overall"] == 3.0
        # True number: 3 fixtures / 4 repos in the pool = 0.75
        assert fx["avg_fixtures_per_repo_overall"] == 0.75

    def test_avg_fixtures_per_repo_overall_has_no_per_language_breakdown(self, tmp_path):
        """Deliberately overall-only: a per-language version would require
        crossing repos' assigned language against fixtures' own detected
        language (the same cross-partition ambiguity purity_gate has -- see
        dataset_summary.py's module docstring), so it isn't offered rather
        than asserting a precision this data doesn't have."""
        summary = compute_summary("c", root=tmp_path)
        assert isinstance(summary["fixtures"]["avg_fixtures_per_repo_overall"], float)


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
        assert gate["by_repo_language"]["python"] == {
            "accepted": 5,
            "rejected": 5,
            "acceptance_rate": 0.5,
        }
        assert gate["acceptance_rate_all_languages_combined"] == 0.5

    def test_dataset_b_reads_purity_stats_csv(self, tmp_path):
        _write_csv(
            paths.stage_dir("b", "test-commits", root=tmp_path) / "python_purity_stats.csv",
            [{"language": "python", "commits_accepted": "8", "commits_rejected": "2"}],
            ["language", "commits_accepted", "commits_rejected"],
        )
        summary = compute_summary("b", root=tmp_path)
        gate = summary["purity_gate"]
        assert gate["by_repo_language"]["python"] == {
            "accepted": 8,
            "rejected": 2,
            "acceptance_rate": 0.8,
        }
        assert gate["acceptance_rate_all_languages_combined"] == 0.8

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
        assert summary["test_commits"]["by_repo_language"] == {"python": 1}

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
        assert "generated_at_utc" in data
        assert data["schema_version"] == 1
        assert data["sampling_seed"] is not None

    def test_sampling_seed_omitted_entirely_for_a_and_b(self, tmp_path):
        """Verified this is never anything but null for real A/B collection
        (repo_resolve.py's --stratified capping is a plain rows[:n] slice,
        no RNG at all) -- so the key is absent there instead of shown as
        permanently-empty noise, and present (a real value) only for C."""
        assert "sampling_seed" not in compute_summary("a", root=tmp_path)
        assert "sampling_seed" not in compute_summary("b", root=tmp_path)
        assert "sampling_seed" in compute_summary("c", root=tmp_path)
