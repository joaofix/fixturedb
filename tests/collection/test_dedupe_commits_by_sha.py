from __future__ import annotations

import csv
from pathlib import Path

from collection.dedupe_commits_by_sha import (
    AUDIT_FIELDNAMES,
    dedupe_commit_csvs,
    find_duplicate_commit_rows,
)


def _row(repo_name, commit_sha, language="python", **extra):
    return {"repo_name": repo_name, "commit_sha": commit_sha, "language": language, **extra}


class TestFindDuplicateCommitRows:
    def test_commit_shared_by_two_repos_flags_the_lower_stars_one(self):
        rows = [
            _row("org/old-name", "abc123"),
            _row("org/new-name", "abc123"),
        ]
        metadata = {
            "org/old-name": {"stars": "50", "created_at": "2016-01-01"},
            "org/new-name": {"stars": "200", "created_at": "2016-01-01"},
        }
        removed = find_duplicate_commit_rows(rows, metadata)
        assert len(removed) == 1
        assert removed[0]["commit_sha"] == "abc123"
        assert removed[0]["repo_removed"] == "org/old-name"
        assert removed[0]["repo_kept"] == "org/new-name"
        assert removed[0]["cluster_size"] == 2

    def test_tie_on_stars_broken_by_earliest_created_at(self):
        rows = [
            _row("org/renamed", "abc123"),
            _row("org/original", "abc123"),
        ]
        metadata = {
            "org/renamed": {"stars": "100", "created_at": "2020-06-01"},
            "org/original": {"stars": "100", "created_at": "2016-03-20"},
        }
        removed = find_duplicate_commit_rows(rows, metadata)
        assert removed[0]["repo_removed"] == "org/renamed"
        assert removed[0]["repo_kept"] == "org/original"

    def test_commit_seen_only_once_is_never_flagged(self):
        """The overwhelming majority case: a commit_sha unique to one
        repo_name must never appear in the output, regardless of how many
        *other* repos/commits exist in the input."""
        rows = [
            _row("org/a", "sha-a"),
            _row("org/b", "sha-b"),
            _row("org/c", "sha-c"),
        ]
        metadata = {name: {"stars": "10", "created_at": "2020-01-01"} for name in ("org/a", "org/b", "org/c")}
        assert find_duplicate_commit_rows(rows, metadata) == []

    def test_same_repo_name_appearing_twice_for_one_sha_is_not_a_cross_repo_duplicate(self):
        """Two rows, same repo_name, same commit_sha (e.g. an accidental
        re-scan) -- there's only one distinct repo_name here, so this must
        not be treated as a cross-repo-name duplicate."""
        rows = [
            _row("org/a", "abc123"),
            _row("org/a", "abc123"),
        ]
        metadata = {"org/a": {"stars": "10", "created_at": "2020-01-01"}}
        assert find_duplicate_commit_rows(rows, metadata) == []

    def test_cluster_of_three_repo_names_removes_two(self):
        """The real motivating case: camunda-cloud/zeebe, camunda/zeebe,
        camunda/camunda all sharing history up to a commit."""
        rows = [
            _row("camunda-cloud/zeebe", "sha1", language="java"),
            _row("camunda/zeebe", "sha1", language="java"),
            _row("camunda/camunda", "sha1", language="java"),
        ]
        metadata = {
            "camunda-cloud/zeebe": {"stars": "2258", "created_at": "2016-03-20T03:38:04"},
            "camunda/zeebe": {"stars": "3046", "created_at": "2016-03-20T03:38:04"},
            "camunda/camunda": {"stars": "4194", "created_at": "2016-03-20T03:38:04"},
        }
        removed = find_duplicate_commit_rows(rows, metadata)
        assert len(removed) == 2
        assert {r["repo_removed"] for r in removed} == {"camunda-cloud/zeebe", "camunda/zeebe"}
        assert all(r["repo_kept"] == "camunda/camunda" for r in removed)
        assert all(r["cluster_size"] == 3 for r in removed)

    def test_repo_missing_from_metadata_never_wins_survivor_pick(self):
        rows = [
            _row("org/known", "abc123"),
            _row("org/unknown-to-metadata", "abc123"),
        ]
        metadata = {"org/known": {"stars": "1", "created_at": "2020-01-01"}}
        removed = find_duplicate_commit_rows(rows, metadata)
        assert removed[0]["repo_kept"] == "org/known"
        assert removed[0]["repo_removed"] == "org/unknown-to-metadata"

    def test_blank_commit_sha_rows_ignored(self):
        rows = [_row("org/a", ""), _row("org/b", "   ")]
        assert find_duplicate_commit_rows(rows, {}) == []


class TestDedupeCommitCsvs:
    def _write_csv(self, path: Path, fieldnames: list[str], rows: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

    def _write_repos_csv(self, path: Path, rows: list[dict]) -> None:
        self._write_csv(path, ["repo_name", "language", "stars", "created_at"], rows)

    def test_rewrites_commit_csv_and_writes_audit_csv(self, tmp_path: Path):
        commits_dir = tmp_path / "commits"
        repos_dir = tmp_path / "repos"

        self._write_csv(
            commits_dir / "python_commit.csv",
            ["repo_name", "commit_sha", "language", "agent_type"],
            [
                {"repo_name": "org/old-name", "commit_sha": "abc123", "language": "python", "agent_type": "claude"},
                {"repo_name": "org/new-name", "commit_sha": "abc123", "language": "python", "agent_type": "claude"},
                {"repo_name": "org/unrelated", "commit_sha": "def456", "language": "python", "agent_type": "codex"},
            ],
        )
        self._write_repos_csv(
            repos_dir / "python_repo.csv",
            [
                {"repo_name": "org/old-name", "language": "python", "stars": "10", "created_at": "2016-01-01"},
                {"repo_name": "org/new-name", "language": "python", "stars": "500", "created_at": "2016-01-01"},
                {"repo_name": "org/unrelated", "language": "python", "stars": "5", "created_at": "2019-01-01"},
            ],
        )

        audit_path = commits_dir / "duplicate_commits_removed.csv"
        summary = dedupe_commit_csvs(
            commits_dir, repos_dir, pattern="*_commit.csv", audit_output_path=audit_path
        )

        assert summary["total_commit_rows_before"] == 3
        assert summary["duplicate_rows_removed"] == 1
        assert summary["distinct_duplicate_commits"] == 1

        with (commits_dir / "python_commit.csv").open(newline="", encoding="utf-8") as fh:
            remaining = list(csv.DictReader(fh))
        assert len(remaining) == 2
        assert {r["repo_name"] for r in remaining} == {"org/new-name", "org/unrelated"}
        # The unrelated commit's own row is untouched, same fieldnames as before.
        unrelated_row = next(r for r in remaining if r["repo_name"] == "org/unrelated")
        assert unrelated_row["agent_type"] == "codex"

        with audit_path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            assert reader.fieldnames == AUDIT_FIELDNAMES
            audit_rows = list(reader)
        assert len(audit_rows) == 1
        assert audit_rows[0]["repo_removed"] == "org/old-name"
        assert audit_rows[0]["repo_kept"] == "org/new-name"

    def test_no_duplicates_leaves_files_and_skips_audit_csv(self, tmp_path: Path):
        commits_dir = tmp_path / "commits"
        repos_dir = tmp_path / "repos"
        self._write_csv(
            commits_dir / "python_commit.csv",
            ["repo_name", "commit_sha", "language"],
            [{"repo_name": "org/a", "commit_sha": "sha1", "language": "python"}],
        )
        self._write_repos_csv(
            repos_dir / "python_repo.csv",
            [{"repo_name": "org/a", "language": "python", "stars": "1", "created_at": "2020-01-01"}],
        )

        audit_path = commits_dir / "duplicate_commits_removed.csv"
        summary = dedupe_commit_csvs(
            commits_dir, repos_dir, pattern="*_commit.csv", audit_output_path=audit_path
        )

        assert summary["duplicate_rows_removed"] == 0
        assert summary["audit_csv"] is None
        assert not audit_path.exists()

    def test_duplicates_split_across_two_language_files_still_detected(self, tmp_path: Path):
        """The dedup grouping must operate across all commit-level CSVs
        combined, not per-file -- a repo misclassified into a different
        language file by one of its name variants must still be caught."""
        commits_dir = tmp_path / "commits"
        repos_dir = tmp_path / "repos"
        self._write_csv(
            commits_dir / "java_commit.csv",
            ["repo_name", "commit_sha", "language"],
            [{"repo_name": "org/java-variant", "commit_sha": "shared-sha", "language": "java"}],
        )
        self._write_csv(
            commits_dir / "typescript_commit.csv",
            ["repo_name", "commit_sha", "language"],
            [{"repo_name": "org/ts-variant", "commit_sha": "shared-sha", "language": "typescript"}],
        )
        self._write_repos_csv(
            repos_dir / "java_repo.csv",
            [{"repo_name": "org/java-variant", "language": "java", "stars": "10", "created_at": "2020-01-01"}],
        )
        self._write_repos_csv(
            repos_dir / "typescript_repo.csv",
            [{"repo_name": "org/ts-variant", "language": "typescript", "stars": "999", "created_at": "2020-01-01"}],
        )

        audit_path = commits_dir / "duplicate_commits_removed.csv"
        summary = dedupe_commit_csvs(
            commits_dir, repos_dir, pattern="*_commit.csv", audit_output_path=audit_path
        )
        assert summary["duplicate_rows_removed"] == 1

        with (commits_dir / "java_commit.csv").open(newline="", encoding="utf-8") as fh:
            assert list(csv.DictReader(fh)) == []
        with (commits_dir / "typescript_commit.csv").open(newline="", encoding="utf-8") as fh:
            assert len(list(csv.DictReader(fh))) == 1
