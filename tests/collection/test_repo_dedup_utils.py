from __future__ import annotations

import csv

import pytest

from collection.repo_dedup_utils import (
    OUTPUT_FIELDNAMES,
    find_duplicate_clusters,
    pick_cluster_survivor,
    write_duplicate_repos_csv,
)


class TestPickClusterSurvivor:
    def test_highest_stars_wins(self):
        repos = [
            {"repo_name": "a/low", "stars": 10, "github_id": 1},
            {"repo_name": "b/high", "stars": 100, "github_id": 2},
            {"repo_name": "c/mid", "stars": 50, "github_id": 3},
        ]
        assert pick_cluster_survivor(repos)["repo_name"] == "b/high"

    def test_tie_broken_by_lowest_github_id(self):
        repos = [
            {"repo_name": "a/newer", "stars": 100, "github_id": 999},
            {"repo_name": "b/older", "stars": 100, "github_id": 1},
        ]
        assert pick_cluster_survivor(repos)["repo_name"] == "b/older"

    def test_single_repo_cluster_returns_that_repo(self):
        repos = [{"repo_name": "only/one", "stars": 5, "github_id": 42}]
        assert pick_cluster_survivor(repos)["repo_name"] == "only/one"

    def test_missing_stars_treated_as_zero(self):
        repos = [
            {"repo_name": "a/no-stars", "github_id": 1},
            {"repo_name": "b/one-star", "stars": 1, "github_id": 2},
        ]
        assert pick_cluster_survivor(repos)["repo_name"] == "b/one-star"

    def test_missing_github_id_never_preferred_in_a_tie(self):
        repos = [
            {"repo_name": "a/no-id", "stars": 100},
            {"repo_name": "b/real-id", "stars": 100, "github_id": 5},
        ]
        assert pick_cluster_survivor(repos)["repo_name"] == "b/real-id"

    def test_unparseable_stars_treated_as_zero(self):
        repos = [
            {"repo_name": "a/bad-stars", "stars": "not-a-number", "github_id": 1},
            {"repo_name": "b/real-stars", "stars": 1, "github_id": 2},
        ]
        assert pick_cluster_survivor(repos)["repo_name"] == "b/real-stars"

    def test_empty_cluster_raises(self):
        with pytest.raises(ValueError):
            pick_cluster_survivor([])


def _repo(name, language, stars, github_id, key):
    return {
        "repo_name": name,
        "language": language,
        "stars": stars,
        "github_id": github_id,
        "_key": key,
    }


class TestFindDuplicateClusters:
    def test_cluster_of_two_produces_one_removal_row(self):
        repos = [
            _repo("owner/low-stars", "python", 10, 2, "abc123"),
            _repo("owner/high-stars", "python", 100, 1, "abc123"),
        ]
        rows = find_duplicate_clusters(repos, key_fn=lambda r: r["_key"])

        assert len(rows) == 1
        assert rows[0]["repo_to_remove"] == "owner/low-stars"
        assert rows[0]["repo_to_keep"] == "owner/high-stars"
        assert rows[0]["shared_commit_sha"] == "abc123"
        assert rows[0]["cluster_size"] == 2

    def test_cluster_of_five_keeps_only_highest_stars(self):
        repos = [
            _repo(f"owner/repo{i}", "java", stars, 100 + i, "same-key")
            for i, stars in enumerate([10, 50, 999, 20, 5])
        ]
        rows = find_duplicate_clusters(repos, key_fn=lambda r: r["_key"])
        removed = {r["repo_to_remove"] for r in rows}
        assert removed == {"owner/repo0", "owner/repo1", "owner/repo3", "owner/repo4"}
        assert all(r["repo_to_keep"] == "owner/repo2" for r in rows)
        assert all(r["cluster_size"] == 5 for r in rows)

    def test_singletons_produce_no_output(self):
        repos = [
            _repo("owner/a", "python", 10, 1, "sha-a"),
            _repo("owner/b", "python", 20, 2, "sha-b"),
        ]
        rows = find_duplicate_clusters(repos, key_fn=lambda r: r["_key"])
        assert rows == []

    def test_falsy_key_never_causes_a_cluster(self):
        """Two repos both missing a key must not be treated as matching
        each other -- that would drop unrelated repos."""
        repos = [
            _repo("owner/a", "python", 10, 1, ""),
            _repo("owner/b", "python", 20, 2, None),
        ]
        rows = find_duplicate_clusters(repos, key_fn=lambda r: r["_key"])
        assert rows == []

    def test_uses_full_name_when_repo_name_absent(self):
        repos = [
            {"full_name": "owner/a", "language": "python", "stars": 10, "github_id": 1, "_key": "sha"},
            {"full_name": "owner/b", "language": "python", "stars": 20, "github_id": 2, "_key": "sha"},
        ]
        rows = find_duplicate_clusters(repos, key_fn=lambda r: r["_key"])
        assert rows[0]["repo_to_remove"] == "owner/a"
        assert rows[0]["repo_to_keep"] == "owner/b"


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
