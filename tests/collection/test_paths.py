"""Unit tests for the collection.paths path registry.

Covers every (dataset, stage) pair in STAGE_ORDER, the root=TOY_ROOT override
(the mechanism that keeps toy runs from colliding with real datasets/ output),
and the error cases for unsupported dataset/stage combinations.
"""

from __future__ import annotations

import pytest

from collection import paths


class TestStageDir:
    @pytest.mark.parametrize(
        "dataset,stage",
        [
            ("a", "repos"),
            ("a", "commits"),
            ("a", "test-commits"),
            ("a", "fixtures"),
            ("b", "repos"),
            ("b", "test-commits"),
            ("b", "fixtures"),
            ("c", "repos"),
            ("c", "fixtures"),
        ],
    )
    def test_default_root(self, dataset, stage):
        assert paths.stage_dir(dataset, stage) == paths.DATASETS_ROOT / dataset / stage

    def test_toy_root_override(self):
        assert (
            paths.stage_dir("a", "fixtures", root=paths.TOY_ROOT)
            == paths.TOY_ROOT / "a" / "fixtures"
        )

    def test_unknown_dataset_raises(self):
        with pytest.raises(ValueError, match="unknown dataset"):
            paths.stage_dir("z", "repos")

    def test_unknown_stage_for_dataset_raises(self):
        with pytest.raises(ValueError, match="no 'commits' stage"):
            paths.stage_dir("b", "commits")

    def test_dataset_c_has_no_test_commits_or_commits_stage(self):
        for bad_stage in ("commits", "test-commits"):
            with pytest.raises(ValueError):
                paths.stage_dir("c", bad_stage)


class TestPreviousStageDir:
    def test_second_stage_resolves_to_first(self):
        assert paths.previous_stage_dir("a", "commits") == paths.stage_dir("a", "repos")

    def test_last_stage_resolves_to_second_to_last(self):
        assert paths.previous_stage_dir("a", "fixtures") == paths.stage_dir(
            "a", "test-commits"
        )

    def test_first_stage_has_no_previous(self):
        for dataset in paths.DATASETS:
            first_stage = paths.STAGE_ORDER[dataset][0]
            with pytest.raises(ValueError, match="first stage"):
                paths.previous_stage_dir(dataset, first_stage)

    def test_toy_root_propagates(self):
        assert paths.previous_stage_dir(
            "a", "commits", root=paths.TOY_ROOT
        ) == paths.TOY_ROOT / "a" / "repos"


class TestDefaultRepoSource:
    def test_dataset_a_uses_raw_search_dir(self):
        assert paths.default_repo_source("a") == paths.RAW_SEARCH_DIR

    def test_dataset_c_uses_raw_search_dir(self):
        assert paths.default_repo_source("c") == paths.RAW_SEARCH_DIR

    def test_dataset_b_falls_back_to_a_repos_when_a_fixtures_repos_empty(
        self, tmp_path
    ):
        root = tmp_path / "datasets"
        assert paths.default_repo_source("b", root=root) == paths.stage_dir(
            "a", "repos", root=root
        )

    def test_dataset_b_prefers_a_fixtures_repos_when_populated(self, tmp_path):
        root = tmp_path / "datasets"
        fixture_repos_dir = paths.stage_dir("a", "fixtures", root=root) / "repos"
        fixture_repos_dir.mkdir(parents=True)
        (fixture_repos_dir / "python_fixture_repos.csv").write_text("repo_name\n")

        assert paths.default_repo_source("b", root=root) == fixture_repos_dir

    def test_dataset_b_falls_back_when_a_fixtures_repos_exists_but_empty(
        self, tmp_path
    ):
        root = tmp_path / "datasets"
        fixture_repos_dir = paths.stage_dir("a", "fixtures", root=root) / "repos"
        fixture_repos_dir.mkdir(parents=True)

        assert paths.default_repo_source("b", root=root) == paths.stage_dir(
            "a", "repos", root=root
        )

    def test_unknown_dataset_raises(self):
        with pytest.raises(ValueError):
            paths.default_repo_source("z")


class TestDbPaths:
    @pytest.mark.parametrize("dataset", ["a", "b", "c"])
    def test_db_path(self, dataset):
        assert paths.db_path(dataset) == paths.DB_ROOT / f"{dataset}.db"

    def test_db_path_unknown_dataset_raises(self):
        with pytest.raises(ValueError):
            paths.db_path("z")

    def test_corpus_db_path(self):
        assert paths.corpus_db_path() == paths.DB_ROOT / "corpus.db"

    def test_db_root_override(self, tmp_path):
        assert paths.db_path("a", root=tmp_path) == tmp_path / "a.db"
        assert paths.corpus_db_path(root=tmp_path) == tmp_path / "corpus.db"


class TestExportPath:
    @pytest.mark.parametrize("dataset", ["a", "b", "c"])
    def test_export_path(self, dataset):
        assert paths.export_path(dataset) == paths.EXPORT_ROOT / f"{dataset}.zip"

    def test_export_path_unknown_dataset_raises(self):
        with pytest.raises(ValueError):
            paths.export_path("z")
