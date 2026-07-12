"""Unit tests for collection.toy.run_toy().

The core guarantee `toy` provides is structural, not a runtime check: every
path it touches is resolved through collection.paths with root=TOY_ROOT, so
a toy run cannot write into the real datasets/ or db/ tree. These tests mock
every underlying step function (real toy runs do live git clones -- that's
exercised manually, not in the unit suite) and assert every path argument
passed to them falls under toy-dataset/, matching what the real (non-toy)
dispatch in test_main_cli.py resolves under datasets/ and db/.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from collection import paths
from collection.toy import run_toy


def _under_toy_root(path) -> bool:
    return paths.TOY_ROOT in path.parents or path == paths.TOY_ROOT


class TestToyDatasetA:
    def test_all_paths_rooted_under_toy_dataset(self):
        with patch(
            "collection.repository_quality_control.agent_repository_counter.run"
        ) as mock_discover_repos:
            with patch(
                "collection.repository_quality_control.agent_commit_counter.run"
            ) as mock_discover_commits:
                with patch(
                    "collection.test_commit_filter.collect_agent_test_commits"
                ) as mock_filter:
                    with patch(
                        "collection.agent_corpus.AgentCorpusCollector"
                    ) as MockCollector:
                        stats = MagicMock(fixtures_collected=1)
                        MockCollector.return_value.run.return_value = (
                            stats,
                            paths.db_path("a", root=paths.TOY_ROOT / "db"),
                        )
                        rc = run_toy("a", repos=2)

        assert rc == 0
        assert _under_toy_root(mock_discover_repos.call_args.kwargs["output_dir"])
        assert _under_toy_root(mock_discover_commits.call_args.kwargs["input_dir"])
        assert _under_toy_root(mock_discover_commits.call_args.kwargs["output_dir"])
        filter_args = mock_filter.call_args.args
        assert _under_toy_root(filter_args[0])
        assert _under_toy_root(filter_args[1])
        ctor_kwargs = MockCollector.call_args.kwargs
        assert _under_toy_root(ctor_kwargs["output_db"])
        assert _under_toy_root(ctor_kwargs["repo_qc_dir"])
        assert _under_toy_root(ctor_kwargs["commit_qc_dir"])

    def test_never_touches_real_datasets_or_db_root(self):
        with patch(
            "collection.repository_quality_control.agent_repository_counter.run"
        ) as mock_discover_repos:
            with patch(
                "collection.repository_quality_control.agent_commit_counter.run"
            ):
                with patch("collection.test_commit_filter.collect_agent_test_commits"):
                    with patch(
                        "collection.agent_corpus.AgentCorpusCollector"
                    ) as MockCollector:
                        stats = MagicMock(fixtures_collected=1)
                        MockCollector.return_value.run.return_value = (
                            stats,
                            paths.db_path("a", root=paths.TOY_ROOT / "db"),
                        )
                        run_toy("a", repos=2)

        out_dir = mock_discover_repos.call_args.kwargs["output_dir"]
        assert paths.DATASETS_ROOT not in out_dir.parents
        assert paths.DB_ROOT not in MockCollector.call_args.kwargs["output_db"].parents


class TestToyDatasetB:
    def test_all_paths_rooted_under_toy_dataset(self):
        with patch("collection.repo_resolve.resolve_dataset_b_repos") as mock_resolve:
            with patch(
                "collection.human_corpus.HumanCorpusCollector"
            ) as MockCollector:
                stats = MagicMock(fixtures_collected=1)
                MockCollector.return_value.run.return_value = (
                    stats,
                    paths.db_path("b", root=paths.TOY_ROOT / "db"),
                )
                rc = run_toy("b", repos=2)

        assert rc == 0
        resolve_kwargs = mock_resolve.call_args.kwargs
        assert _under_toy_root(resolve_kwargs["source_dir"])
        assert _under_toy_root(resolve_kwargs["output_dir"])
        ctor_kwargs = MockCollector.call_args.kwargs
        assert _under_toy_root(ctor_kwargs["output_db"])
        assert _under_toy_root(ctor_kwargs["repo_qc_dir"])
        assert _under_toy_root(ctor_kwargs["test_commits_csv"])


class TestToyDatasetC:
    """write_per_language_files() and the load_dataset_c_repos() read-back
    are deliberately NOT mocked here (unlike every other toy step): they're
    pure local CSV read/write, no network I/O, and this exact write-then-
    read-back round trip is what production toy runs depend on --
    collect_dataset_c_fixtures()'s _process_repo() indexes repo["full_name"],
    but select_repos()/the stratified sampler both produce repo_name-keyed
    dicts, so toy.py re-reads via load_dataset_c_repos() (the same mapping
    the real, non-toy extract-fixtures --dataset c CLI path already uses)
    rather than passing `selected` straight through. Mocking the write would
    make load_dataset_c_repos() read whatever stale toy-dataset/ debris
    happens to already exist on disk instead of this test's own fixture data
    -- exactly the bug this test now guards against.
    """

    def test_all_paths_rooted_under_toy_dataset(self, tmp_path, monkeypatch):
        monkeypatch.setattr(paths, "TOY_ROOT", tmp_path)
        with patch(
            "collection.select_dataset_c_repos.select_repos",
            return_value=[
                {
                    "repo_name": "o/r",
                    "language": "python",
                    "clone_url": "https://github.com/o/r.git",
                    "github_id": 1,
                }
            ],
        ):
            with patch(
                "collection.dataset_c.collect_dataset_c_fixtures",
                return_value=({"python": 1}, paths.db_path("c", root=tmp_path / "db")),
            ) as mock_extract:
                rc = run_toy("c", repos=2)

        assert rc == 0
        assert _under_toy_root(mock_extract.call_args.kwargs["output_db"])
        extracted_repos = mock_extract.call_args.args[0]
        assert [r["full_name"] for r in extracted_repos] == ["o/r"]

    def test_repos_cap_applied_before_extraction(self, tmp_path, monkeypatch):
        monkeypatch.setattr(paths, "TOY_ROOT", tmp_path)
        many_repos = [
            {
                "repo_name": f"o/r{i}",
                "language": "python",
                "clone_url": f"https://github.com/o/r{i}.git",
                "github_id": i,
            }
            for i in range(10)
        ]
        with patch(
            "collection.select_dataset_c_repos.select_repos", return_value=many_repos
        ):
            with patch(
                "collection.dataset_c.collect_dataset_c_fixtures",
                return_value=({}, paths.db_path("c", root=tmp_path / "db")),
            ) as mock_extract:
                run_toy("c", repos=3)

        assert len(mock_extract.call_args.args[0]) == 3


class TestUnknownDataset:
    def test_raises_value_error(self):
        import pytest

        with pytest.raises(ValueError, match="unknown dataset"):
            run_toy("z")
