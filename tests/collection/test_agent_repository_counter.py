from __future__ import annotations

import csv
import gzip
from contextlib import contextmanager
from pathlib import Path

import collection.repository_quality_control.agent_repository_counter as qc


def _write_raw_csv(path: Path, rows: list[dict]) -> None:
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def test_read_repo_list_can_filter_multiple_languages(monkeypatch, tmp_path):
    raw_dir = tmp_path / "github-search-raw"
    raw_dir.mkdir()

    _write_raw_csv(
        raw_dir / "java.csv.gz",
        [
            {
                "name": "owner/java-repo",
                "mainLanguage": "java",
                "stargazers": "10",
                "contributors": "2",
            }
        ],
    )
    _write_raw_csv(
        raw_dir / "javascript.csv.gz",
        [
            {
                "name": "owner/javascript-repo",
                "mainLanguage": "javascript",
                "stargazers": "20",
                "contributors": "3",
            }
        ],
    )
    _write_raw_csv(
        raw_dir / "python.csv.gz",
        [
            {
                "name": "owner/python-repo",
                "mainLanguage": "python",
                "stargazers": "30",
                "contributors": "4",
            }
        ],
    )

    repos = qc.read_repo_list(languages=["java", "javascript"], raw_dir=raw_dir)

    assert [repo["full_name"] for repo in repos] == [
        "owner/java-repo",
        "owner/javascript-repo",
    ]
    assert {repo["language"] for repo in repos} == {"java", "javascript"}


def test_read_repo_list_carries_through_github_id_and_last_commit_sha(monkeypatch, tmp_path):
    raw_dir = tmp_path / "github-search-raw"
    raw_dir.mkdir()
    _write_raw_csv(
        raw_dir / "python.csv.gz",
        [
            {
                "id": "12345",
                "name": "owner/python-repo",
                "mainLanguage": "python",
                "stargazers": "10",
                "contributors": "2",
                "lastCommitSHA": "abc123def456",
            }
        ],
    )

    repos = qc.read_repo_list(languages=["python"], raw_dir=raw_dir)

    assert repos[0]["github_id"] == 12345
    assert repos[0]["last_commit_sha"] == "abc123def456"


class TestDedupeByLastCommitSha:
    """The cheap, automatic, zero-cost partial win: repos sharing an
    identical *current* HEAD (SEART's lastCommitSHA) are dropped before the
    has_agent_config clone check. Does not catch pairs that have since
    diverged -- see the function's own docstring."""

    def _repo(self, name, stars, github_id, last_commit_sha):
        return {
            "full_name": name,
            "language": "python",
            "stars": stars,
            "github_id": github_id,
            "last_commit_sha": last_commit_sha,
        }

    def test_cluster_keeps_only_highest_stars(self):
        repos = [
            self._repo("owner/low", 10, 2, "shared-sha"),
            self._repo("owner/high", 100, 1, "shared-sha"),
        ]
        survivors = qc._dedupe_by_last_commit_sha(repos)
        assert [r["full_name"] for r in survivors] == ["owner/high"]

    def test_repos_with_distinct_shas_all_survive(self):
        repos = [
            self._repo("owner/a", 10, 1, "sha-a"),
            self._repo("owner/b", 20, 2, "sha-b"),
        ]
        survivors = qc._dedupe_by_last_commit_sha(repos)
        assert {r["full_name"] for r in survivors} == {"owner/a", "owner/b"}

    def test_repos_with_missing_sha_never_clustered_together(self):
        """Two repos both missing last_commit_sha must not be treated as
        matching each other -- that would drop unrelated repos."""
        repos = [
            self._repo("owner/a", 10, 1, ""),
            self._repo("owner/b", 20, 2, ""),
        ]
        survivors = qc._dedupe_by_last_commit_sha(repos)
        assert {r["full_name"] for r in survivors} == {"owner/a", "owner/b"}

    def test_empty_list_returns_empty(self):
        assert qc._dedupe_by_last_commit_sha([]) == []


class TestWriteLastCommitShaDuplicatesCsv:
    """The persisted counterpart of _dedupe_by_last_commit_sha() -- writes
    the same rows to a consultable CSV, living alongside the raw SEART
    exports (see DUPLICATE_REPOS_ARTIFACT_PATH's docstring for why)."""

    def _repo(self, name, stars, github_id, last_commit_sha):
        return {
            "full_name": name,
            "language": "python",
            "stars": stars,
            "github_id": github_id,
            "last_commit_sha": last_commit_sha,
        }

    def test_writes_one_row_per_dropped_duplicate(self, tmp_path):
        repos = [
            self._repo("owner/low", 10, 2, "shared-sha"),
            self._repo("owner/high", 100, 1, "shared-sha"),
        ]
        artifact_path = tmp_path / "duplicate_repos_by_current_commit.csv"

        rows = qc.write_last_commit_sha_duplicates_csv(repos, artifact_path)

        assert len(rows) == 1
        assert rows[0]["repo_to_remove"] == "owner/low"
        assert rows[0]["repo_to_keep"] == "owner/high"
        assert artifact_path.exists()
        with artifact_path.open(newline="", encoding="utf-8") as fh:
            written_rows = list(csv.DictReader(fh))
        assert len(written_rows) == 1
        assert written_rows[0]["repo_to_remove"] == "owner/low"

    def test_no_duplicates_still_writes_header_only_file(self, tmp_path):
        repos = [self._repo("owner/a", 10, 1, "sha-a")]
        artifact_path = tmp_path / "duplicate_repos_by_current_commit.csv"

        rows = qc.write_last_commit_sha_duplicates_csv(repos, artifact_path)

        assert rows == []
        assert artifact_path.exists()
        with artifact_path.open(newline="", encoding="utf-8") as fh:
            assert list(csv.DictReader(fh)) == []


def test_run_writes_duplicate_repos_artifact_next_to_raw_source(monkeypatch, tmp_path):
    """run() must never write its artifact into the real github-search-raw/
    -- it derives the path from source_dir, so tests (and any future caller
    passing a non-default source_dir) stay isolated."""
    raw_dir = tmp_path / "github-search-raw"
    raw_dir.mkdir()
    _write_raw_csv(
        raw_dir / "python.csv.gz",
        [
            {
                "id": "1",
                "name": "owner/low-stars",
                "mainLanguage": "python",
                "stargazers": "10",
                "contributors": "1",
                "lastCommitSHA": "shared-sha",
            },
            {
                "id": "2",
                "name": "owner/high-stars",
                "mainLanguage": "python",
                "stargazers": "100",
                "contributors": "1",
                "lastCommitSHA": "shared-sha",
            },
        ],
    )

    monkeypatch.setattr(qc, "temp_clone_commit_history", _fake_temp_clone(tmp_path))
    monkeypatch.setattr(qc, "scan_cloned_repo_for_agent_configs", lambda repo_path: None)

    qc.run(
        workers=1,
        source_dir=raw_dir,
        output_dir=tmp_path / "out",
        languages=["python"],
    )

    artifact_path = raw_dir / "duplicate_repos_by_current_commit.csv"
    assert artifact_path.exists()
    with artifact_path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 1
    assert rows[0]["repo_to_remove"] == "owner/low-stars"


def test_run_never_clones_a_dropped_duplicate(monkeypatch, tmp_path):
    """The real point of dedupe-before-clone: a repo dropped as a duplicate
    must never reach temp_clone_commit_history (has_agent_config check)."""
    raw_dir = tmp_path / "github-search-raw"
    raw_dir.mkdir()
    _write_raw_csv(
        raw_dir / "python.csv.gz",
        [
            {
                "id": "1",
                "name": "owner/low-stars",
                "mainLanguage": "python",
                "stargazers": "10",
                "contributors": "1",
                "lastCommitSHA": "shared-sha",
            },
            {
                "id": "2",
                "name": "owner/high-stars",
                "mainLanguage": "python",
                "stargazers": "100",
                "contributors": "1",
                "lastCommitSHA": "shared-sha",
            },
        ],
    )

    cloned_repos = []

    def fake_temp_clone(clone_url, full_name, prefix="", timeout=60):
        cloned_repos.append(full_name)

        @contextmanager
        def _ctx():
            yield None

        return _ctx()

    monkeypatch.setattr(qc, "temp_clone_commit_history", fake_temp_clone)
    monkeypatch.setattr(qc, "scan_cloned_repo_for_agent_configs", lambda repo_path: None)

    output_dir = tmp_path / "out"
    qc.run(
        workers=1,
        source_dir=raw_dir,
        output_dir=output_dir,
        languages=["python"],
    )

    assert cloned_repos == ["owner/high-stars"]


def _fake_temp_clone(repo_path: Path):
    @contextmanager
    def _ctx(clone_url, full_name, prefix="", timeout=60):
        yield repo_path

    return _ctx


def test_process_single_records_matched_config_file(monkeypatch, tmp_path):
    monkeypatch.setattr(
        qc, "scan_cloned_repo_for_agent_configs", lambda repo_path: "CLAUDE.md"
    )
    monkeypatch.setattr(qc, "temp_clone_commit_history", _fake_temp_clone(tmp_path))

    row = qc._process_single(
        {"full_name": "owner/repo", "language": "python", "stars": 10}, since="2025-01-01"
    )

    assert row["has_agent_config"] == 1
    assert row["matched_config_file"] == "CLAUDE.md"


def test_process_single_empty_matched_config_file_when_no_match(monkeypatch, tmp_path):
    monkeypatch.setattr(qc, "scan_cloned_repo_for_agent_configs", lambda repo_path: None)
    monkeypatch.setattr(qc, "temp_clone_commit_history", _fake_temp_clone(tmp_path))

    row = qc._process_single(
        {"full_name": "owner/repo", "language": "python", "stars": 10}, since="2025-01-01"
    )

    assert row["has_agent_config"] == 0
    assert row["matched_config_file"] == ""
    assert row["qc_reason"] == "no_agent_config"
