from __future__ import annotations

import csv
from unittest.mock import Mock

import requests

from collection.dedupe_dataset_c_repos import (
    OUTPUT_FIELDNAMES,
    fetch_reference_commit_sha,
    find_duplicate_clusters,
    write_duplicate_repos_csv,
)


def _repo(name, language, stars, github_id):
    return {"repo_name": name, "language": language, "stars": stars, "github_id": github_id}


class TestFindDuplicateClusters:
    def test_cluster_of_two_produces_one_removal_row(self, tmp_path):
        repos = [
            _repo("owner/low-stars", "python", 10, 2),
            _repo("owner/high-stars", "python", 100, 1),
        ]
        fake_sha = {"owner/low-stars": "abc123", "owner/high-stars": "abc123"}

        rows = find_duplicate_clusters(
            repos,
            reference_date="2020-12-31",
            github_token="fake",
            checkpoint_path=tmp_path / "checkpoint.json",
            fetch_fn=lambda name, ref, token: fake_sha[name],
        )

        assert len(rows) == 1
        assert rows[0]["repo_to_remove"] == "owner/low-stars"
        assert rows[0]["repo_to_keep"] == "owner/high-stars"
        assert rows[0]["shared_commit_sha"] == "abc123"
        assert rows[0]["cluster_size"] == 2

    def test_cluster_of_five_keeps_only_highest_stars(self, tmp_path):
        repos = [_repo(f"owner/repo{i}", "java", stars, 100 + i) for i, stars in enumerate([10, 50, 999, 20, 5])]
        rows = find_duplicate_clusters(
            repos,
            reference_date="2020-12-31",
            github_token="fake",
            checkpoint_path=tmp_path / "checkpoint.json",
            fetch_fn=lambda name, ref, token: "same-sha",
        )
        removed = {r["repo_to_remove"] for r in rows}
        assert removed == {"owner/repo0", "owner/repo1", "owner/repo3", "owner/repo4"}
        assert all(r["repo_to_keep"] == "owner/repo2" for r in rows)
        assert all(r["cluster_size"] == 5 for r in rows)

    def test_singletons_produce_no_output(self, tmp_path):
        repos = [
            _repo("owner/a", "python", 10, 1),
            _repo("owner/b", "python", 20, 2),
        ]
        rows = find_duplicate_clusters(
            repos,
            reference_date="2020-12-31",
            github_token="fake",
            checkpoint_path=tmp_path / "checkpoint.json",
            fetch_fn=lambda name, ref, token: {"owner/a": "sha-a", "owner/b": "sha-b"}[name],
        )
        assert rows == []

    def test_lookup_failure_never_causes_a_drop(self, tmp_path):
        repos = [
            _repo("owner/a", "python", 10, 1),
            _repo("owner/b", "python", 20, 2),
        ]
        rows = find_duplicate_clusters(
            repos,
            reference_date="2020-12-31",
            github_token="fake",
            checkpoint_path=tmp_path / "checkpoint.json",
            fetch_fn=lambda name, ref, token: None,
        )
        assert rows == []

    def test_checkpoint_resume_does_not_refetch(self, tmp_path):
        repos = [
            _repo("owner/a", "python", 10, 1),
            _repo("owner/b", "python", 20, 2),
        ]
        checkpoint_path = tmp_path / "checkpoint.json"
        call_log = []

        def fetch(name, ref, token):
            call_log.append(name)
            return "same-sha"

        find_duplicate_clusters(
            repos,
            reference_date="2020-12-31",
            github_token="fake",
            checkpoint_path=checkpoint_path,
            fetch_fn=fetch,
        )
        assert sorted(call_log) == ["owner/a", "owner/b"]

        call_log.clear()
        rows = find_duplicate_clusters(
            repos,
            reference_date="2020-12-31",
            github_token="fake",
            checkpoint_path=checkpoint_path,
            fetch_fn=fetch,
        )
        assert call_log == []  # nothing re-fetched
        assert len(rows) == 1


class TestWriteDuplicateReposCsv:
    def test_round_trip(self, tmp_path):
        rows = [
            {
                "repo_to_remove": "owner/dup",
                "repo_to_keep": "owner/original",
                "shared_commit_sha": "abc123",
                "cluster_size": 2,
                "language": "python",
                "stars_removed": 5,
                "stars_kept": 50,
            }
        ]
        out_path = tmp_path / "duplicate_repos.csv"
        write_duplicate_repos_csv(rows, out_path)

        with out_path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            assert reader.fieldnames == OUTPUT_FIELDNAMES
            read_rows = list(reader)
        assert read_rows[0]["repo_to_remove"] == "owner/dup"
        assert read_rows[0]["repo_to_keep"] == "owner/original"


class TestFetchReferenceCommitSha:
    def test_returns_sha_from_first_result(self, monkeypatch):
        response = Mock()
        response.raise_for_status = Mock()
        response.json.return_value = [{"sha": "deadbeef"}]
        monkeypatch.setattr(requests, "get", lambda *a, **k: response)

        sha = fetch_reference_commit_sha("owner/repo", "2020-12-31", "fake-token")
        assert sha == "deadbeef"

    def test_empty_result_returns_none(self, monkeypatch):
        response = Mock()
        response.raise_for_status = Mock()
        response.json.return_value = []
        monkeypatch.setattr(requests, "get", lambda *a, **k: response)

        assert fetch_reference_commit_sha("owner/repo", "2020-12-31", "fake-token") is None

    def test_retries_on_rate_limit_then_succeeds(self, monkeypatch):
        rate_limited_response = Mock()
        rate_limited_response.status_code = 403
        rate_limited_response.headers = {"X-RateLimit-Remaining": "0"}

        success_response = Mock()
        success_response.raise_for_status = Mock()
        success_response.json.return_value = [{"sha": "recovered-sha"}]

        rate_limit_error = requests.HTTPError(response=rate_limited_response)

        call_count = {"n": 0}

        def fake_get(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                error_response = Mock()
                error_response.raise_for_status = Mock(side_effect=rate_limit_error)
                error_response.status_code = 403
                error_response.headers = {"X-RateLimit-Remaining": "0"}
                return error_response
            return success_response

        monkeypatch.setattr(requests, "get", fake_get)
        monkeypatch.setattr("time.sleep", lambda _: None)

        sha = fetch_reference_commit_sha(
            "owner/repo", "2020-12-31", "fake-token", max_retries=2
        )
        assert sha == "recovered-sha"
        assert call_count["n"] == 2

    def test_404_returns_none_without_retry(self, monkeypatch):
        error_response = Mock()
        error_response.status_code = 404
        error_response.headers = {}

        def fake_get(*args, **kwargs):
            resp = Mock()
            resp.raise_for_status = Mock(
                side_effect=requests.HTTPError(response=error_response)
            )
            return resp

        monkeypatch.setattr(requests, "get", fake_get)
        assert fetch_reference_commit_sha("owner/repo", "2020-12-31", "fake-token") is None
