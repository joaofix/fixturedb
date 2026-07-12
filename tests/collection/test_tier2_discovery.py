"""Unit tests for collection.tier2_discovery.

Fuses old phase_1a/1b/1c/1d (JSON-relay scripts) into two direct function
calls. These tests exercise the fused functions against a real corpus.db
(via collection.db.initialise_db) and mock only the expensive scan/verify
internals (Tier1RepositoryScanner.assess_tier1, Tier2RepoMatcher's candidate
matching), which are already covered by
tests/collection/test_agent_detection_logic.py and friends.
"""

from __future__ import annotations

import sqlite3
from unittest.mock import patch

import pytest

from collection import tier2_discovery
from collection.db import initialise_db
from collection.tiered_agent_corpus_scanner import Tier1Assessment


def _seed_repos(db_path, rows):
    conn = sqlite3.connect(db_path)
    try:
        for row in rows:
            conn.execute(
                """
                INSERT INTO repositories
                    (github_id, full_name, language, status, clone_url, stars)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    row.get("github_id", 1),
                    row["full_name"],
                    row.get("language", "python"),
                    row.get("status", "analysed"),
                    row.get("clone_url", "https://github.com/x/x.git"),
                    row.get("stars", 100),
                ),
            )
        conn.commit()
    finally:
        conn.close()


class TestLoadCorpusRepos:
    def test_loads_only_analysed_and_cloned_repos(self, tmp_path):
        db_path = tmp_path / "corpus.db"
        initialise_db(db_path)
        _seed_repos(
            db_path,
            [
                {"github_id": 1, "full_name": "o/analysed", "status": "analysed"},
                {"github_id": 2, "full_name": "o/cloned", "status": "cloned"},
                {"github_id": 3, "full_name": "o/discovered", "status": "discovered"},
                {"github_id": 4, "full_name": "o/skipped", "status": "skipped"},
            ],
        )

        repos = tier2_discovery.load_corpus_repos(db_path)

        names = {r["full_name"] for r in repos}
        assert names == {"o/analysed", "o/cloned"}


class TestResolveClonePath:
    def test_prefers_double_underscore_naming(self, tmp_path):
        (tmp_path / "owner__repo").mkdir()
        assert tier2_discovery.resolve_clone_path("owner/repo", tmp_path) == (
            tmp_path / "owner__repo"
        )

    def test_falls_back_to_bare_repo_name(self, tmp_path):
        (tmp_path / "repo").mkdir()
        assert tier2_discovery.resolve_clone_path("owner/repo", tmp_path) == (
            tmp_path / "repo"
        )

    def test_returns_none_when_not_found(self, tmp_path):
        assert tier2_discovery.resolve_clone_path("owner/repo", tmp_path) is None


class TestAssessTier1Yield:
    def test_raises_when_corpus_db_missing(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="corpus.db"):
            tier2_discovery.assess_tier1_yield(
                tmp_path / "missing.db", clones_dir=tmp_path
            )

    def test_raises_when_clones_dir_missing(self, tmp_path):
        db_path = tmp_path / "corpus.db"
        initialise_db(db_path)
        with pytest.raises(FileNotFoundError, match="clones directory"):
            tier2_discovery.assess_tier1_yield(
                db_path, clones_dir=tmp_path / "missing-clones"
            )

    def test_scans_resolved_clone_paths_and_returns_assessment(self, tmp_path):
        db_path = tmp_path / "corpus.db"
        initialise_db(db_path)
        _seed_repos(db_path, [{"github_id": 1, "full_name": "o/repo1"}])
        clones_dir = tmp_path / "clones"
        clones_dir.mkdir()
        (clones_dir / "o__repo1").mkdir()

        expected = Tier1Assessment(repos_with_agent=5, total_agent_commits=50)
        with patch(
            "collection.tier2_discovery.Tier1RepositoryScanner.assess_tier1",
            return_value=expected,
        ) as mock_assess:
            result = tier2_discovery.assess_tier1_yield(db_path, clones_dir=clones_dir)

        assert result is expected
        (call_arg,) = mock_assess.call_args.args
        assert call_arg[0]["name"] == "o/repo1"
        assert call_arg[0]["path"] == str(clones_dir / "o__repo1")


class TestDiscoverTier2Repos:
    def test_zero_target_returns_empty_without_querying(self, tmp_path):
        assert tier2_discovery.discover_tier2_repos(tmp_path, set(), 0) == []

    def test_wraps_matcher_results_with_discovery_tier(self, tmp_path):
        with patch(
            "collection.tier2_discovery.Tier2RepoMatcher.collect_matched_agent_commits",
            return_value={
                "o__repo1": {"sha1": "claude"},
                "o__repo2": {"sha2": "cursor", "sha3": "cursor"},
            },
        ):
            results = tier2_discovery.discover_tier2_repos(
                tmp_path, exclude={"o/existing"}, target_count=2
            )

        by_name = {r["repo_name"]: r for r in results}
        assert by_name["o__repo1"]["agent_commit_count"] == 1
        assert by_name["o__repo2"]["agent_commit_count"] == 2
        assert all(r["discovery_tier"] == 2 for r in results)
