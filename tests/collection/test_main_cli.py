"""Unit tests for the collection.__main__ CLI dispatch.

Covers the unified verb + --dataset flag design that replaced the old
numbered phase scripts (phase_1a-1d, phase_3_extract_agent.py) and the
separate pipeline.py/collection/__main__.py surfaces. Focuses on Dataset A,
the first dataset wired end-to-end; dispatch functions are mocked at the
implementation-module boundary so these tests exercise argument resolution
and default-path wiring (via collection.paths), not the underlying collection
logic itself (covered elsewhere).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from collection import paths
from collection.__main__ import main


class TestDiscoverRepos:
    def test_dataset_a_resolves_defaults_from_paths(self, tmp_path):
        with patch(
            "collection.repository_quality_control.agent_repository_counter.run",
            return_value=0,
        ) as mock_run:
            rc = main(["discover-repos", "--dataset", "a", "--language", "python"])

        assert rc == 0
        mock_run.assert_called_once_with(
            limit=0,
            since="2025-01-01",
            workers=8,
            languages=["python"],
            source_dir=paths.RAW_SEARCH_DIR,
            output_dir=paths.stage_dir("a", "repos"),
        )

    def test_explicit_dirs_override_defaults(self, tmp_path):
        src = tmp_path / "src"
        out = tmp_path / "out"
        with patch(
            "collection.repository_quality_control.agent_repository_counter.run",
            return_value=0,
        ) as mock_run:
            main(
                [
                    "discover-repos",
                    "--dataset",
                    "a",
                    "--source-dir",
                    str(src),
                    "--output-dir",
                    str(out),
                ]
            )

        assert mock_run.call_args.kwargs["source_dir"] == src
        assert mock_run.call_args.kwargs["output_dir"] == out

    def test_dataset_c_delegates_to_select_dataset_c_repos(self):
        with patch(
            "collection.select_dataset_c_repos.select_repos",
            return_value=[{"repo_name": "o/r", "language": "python"}],
        ) as mock_select:
            with patch(
                "collection.select_dataset_c_repos.filter_known_duplicates",
                return_value=[{"repo_name": "o/r", "language": "python"}],
            ):
                with patch(
                    "collection.select_dataset_c_repos.write_per_language_files",
                    return_value={"python": 1},
                ) as mock_write:
                    rc = main(["discover-repos", "--dataset", "c"])

        assert rc == 0
        mock_select.assert_called_once()
        mock_write.assert_called_once_with(
            [{"repo_name": "o/r", "language": "python"}],
            paths.stage_dir("c", "repos"),
        )

    def test_dataset_c_filters_known_duplicates_before_writing(self):
        """Regression test: discover-repos --dataset c used to never call
        filter_known_duplicates() at all, so the "run discover-repos twice"
        workflow documented in RUN_COMMANDS.md never actually dropped known
        duplicate repos -- see internal-docs/RUN_COMMANDS.md's dedup note.
        """
        with patch(
            "collection.select_dataset_c_repos.select_repos",
            return_value=[
                {"repo_name": "keep/me", "language": "python"},
                {"repo_name": "drop/me", "language": "python"},
            ],
        ):
            with patch(
                "collection.select_dataset_c_repos.filter_known_duplicates",
                return_value=[{"repo_name": "keep/me", "language": "python"}],
            ) as mock_filter:
                with patch(
                    "collection.select_dataset_c_repos.write_per_language_files",
                    return_value={"python": 1},
                ) as mock_write:
                    rc = main(["discover-repos", "--dataset", "c"])

        assert rc == 0
        mock_filter.assert_called_once_with(
            [
                {"repo_name": "keep/me", "language": "python"},
                {"repo_name": "drop/me", "language": "python"},
            ],
            duplicate_repos_csv=paths.stage_dir("c", "repos") / "duplicate_repos.csv",
        )
        # write_per_language_files must receive the *filtered* list, not
        # select_repos()'s raw output -- "drop/me" must never reach it.
        mock_write.assert_called_once_with(
            [{"repo_name": "keep/me", "language": "python"}],
            paths.stage_dir("c", "repos"),
        )

    def test_dataset_c_duplicate_csv_follows_custom_output_dir(self, tmp_path):
        with patch(
            "collection.select_dataset_c_repos.select_repos", return_value=[]
        ):
            with patch(
                "collection.select_dataset_c_repos.filter_known_duplicates",
                return_value=[],
            ) as mock_filter:
                with patch(
                    "collection.select_dataset_c_repos.write_per_language_files",
                    return_value={},
                ):
                    main(
                        [
                            "discover-repos",
                            "--dataset",
                            "c",
                            "--output-dir",
                            str(tmp_path),
                        ]
                    )

        mock_filter.assert_called_once_with(
            [], duplicate_repos_csv=tmp_path / "duplicate_repos.csv"
        )

    def test_invalid_dataset_rejected_by_argparse(self):
        with patch("sys.exit") as mock_exit:
            mock_exit.side_effect = SystemExit
            try:
                main(["discover-repos", "--dataset", "z"])
            except SystemExit:
                pass

    def test_dataset_b_delegates_to_repo_resolve(self):
        with patch(
            "collection.repo_resolve.resolve_dataset_b_repos",
            return_value={"python": 1},
        ) as mock_resolve:
            rc = main(["discover-repos", "--dataset", "b"])

        assert rc == 0
        mock_resolve.assert_called_once_with(
            source_dir=paths.default_repo_source("b"),
            output_dir=paths.stage_dir("b", "repos"),
            language=None,
        )


class TestDiscoverCommits:
    def test_dataset_a_resolves_defaults(self):
        with patch(
            "collection.repository_quality_control.agent_commit_counter.run",
            return_value=0,
        ) as mock_run:
            rc = main(["discover-commits", "--dataset", "a"])

        assert rc == 0
        mock_run.assert_called_once_with(
            since="2025-01-01",
            workers=4,
            input_dir=paths.stage_dir("a", "repos"),
            output_dir=paths.stage_dir("a", "commits"),
        )

    def test_dataset_b_and_c_rejected_by_argparse(self):
        # "b"/"c" are rejected at the argparse level (choices=("a",)) before
        # ever reaching _cmd_discover_commits, since the verb doesn't apply.
        for dataset in ("b", "c"):
            try:
                main(["discover-commits", "--dataset", dataset])
                raised = False
            except SystemExit:
                raised = True
            assert raised

    def test_tier2_runs_assessment_before_commit_scan(self):
        fake_assessment = MagicMock(sufficient=True, summary="all good")
        with patch(
            "collection.tier2_discovery.assess_tier1_yield",
            return_value=fake_assessment,
        ) as mock_assess:
            with patch(
                "collection.repository_quality_control.agent_commit_counter.run",
                return_value=0,
            ) as mock_run:
                main(["discover-commits", "--dataset", "a", "--tier2"])

        mock_assess.assert_called_once()
        mock_run.assert_called_once()

    def test_tier2_discovers_and_merges_when_insufficient(self, tmp_path):
        fake_assessment = MagicMock(
            sufficient=False, summary="insufficient", repos_with_agent=2
        )
        with patch(
            "collection.tier2_discovery.assess_tier1_yield",
            return_value=fake_assessment,
        ):
            with patch(
                "collection.tier2_discovery.load_corpus_repos",
                return_value=[{"full_name": "owner/existing"}],
            ):
                with patch(
                    "collection.tier2_discovery.discover_tier2_repos",
                    return_value=[
                        {"repo_name": "owner/new-repo", "discovery_tier": 2}
                    ],
                ) as mock_discover:
                    with patch(
                        "collection.__main__._merge_tier2_repos_into_csv"
                    ) as mock_merge:
                        with patch(
                            "collection.repository_quality_control.agent_commit_counter.run",
                            return_value=0,
                        ):
                            main(["discover-commits", "--dataset", "a", "--tier2"])

        mock_discover.assert_called_once()
        exclude_arg = mock_discover.call_args.kwargs["exclude"]
        assert exclude_arg == {"owner/existing"}
        mock_merge.assert_called_once()


class TestFilterTestCommits:
    def test_dataset_a(self):
        with patch(
            "collection.test_commit_filter.collect_agent_test_commits"
        ) as mock_run:
            rc = main(["filter-test-commits", "--dataset", "a"])

        assert rc == 0
        mock_run.assert_called_once_with(
            paths.stage_dir("a", "commits"),
            paths.stage_dir("a", "test-commits"),
            workers=12,
        )

    def test_dataset_b(self):
        with patch(
            "collection.human_test_commit_filter.collect_human_test_commits"
        ) as mock_run:
            rc = main(["filter-test-commits", "--dataset", "b"])

        assert rc == 0
        mock_run.assert_called_once_with(
            paths.stage_dir("b", "repos"),
            paths.stage_dir("b", "test-commits"),
            workers=12,
            language=None,
        )


class TestExtractFixtures:
    def test_dataset_a_skips_when_db_already_has_fixtures(self):
        with patch("collection.resume_utils.database_has_rows", return_value=True):
            with patch(
                "collection.agent_corpus.AgentCorpusCollector"
            ) as MockCollector:
                rc = main(["extract-fixtures", "--dataset", "a"])

        assert rc == 0
        MockCollector.assert_not_called()

    def test_dataset_a_force_reextracts_even_if_db_has_rows(self):
        stats = MagicMock(fixtures_collected=5)
        with patch("collection.resume_utils.database_has_rows", return_value=True):
            with patch(
                "collection.agent_corpus.AgentCorpusCollector"
            ) as MockCollector:
                MockCollector.return_value.run.return_value = (
                    stats,
                    paths.db_path("a"),
                )
                rc = main(["extract-fixtures", "--dataset", "a", "--force"])

        assert rc == 0
        MockCollector.assert_called_once()

    def test_dataset_a_resolves_defaults(self):
        stats = MagicMock(fixtures_collected=5)
        with patch("collection.resume_utils.database_has_rows", return_value=False):
            with patch(
                "collection.agent_corpus.AgentCorpusCollector"
            ) as MockCollector:
                MockCollector.return_value.run.return_value = (
                    stats,
                    paths.db_path("a"),
                )
                rc = main(["extract-fixtures", "--dataset", "a"])

        assert rc == 0
        MockCollector.assert_called_once_with(
            output_db=paths.db_path("a"),
            repo_qc_dir=paths.stage_dir("a", "repos"),
            commit_qc_dir=paths.stage_dir("a", "test-commits"),
        )

    def test_dataset_b_resolves_defaults(self):
        stats = MagicMock(fixtures_collected=5)
        with patch("collection.resume_utils.database_has_rows", return_value=False):
            with patch(
                "collection.human_corpus.HumanCorpusCollector"
            ) as MockCollector:
                MockCollector.return_value.run.return_value = (
                    stats,
                    paths.db_path("b"),
                )
                rc = main(["extract-fixtures", "--dataset", "b"])

        assert rc == 0
        MockCollector.assert_called_once_with(
            output_db=paths.db_path("b"),
            repo_qc_dir=paths.stage_dir("b", "repos"),
            test_commits_csv=paths.stage_dir("b", "test-commits"),
        )

    def test_dataset_b_run_call_matches_real_signature(self):
        """Regression: `collector.run(...)` was called with `languages=...`, a
        kwarg HumanCorpusCollector.run() has never accepted (it takes
        `language`, singular, no plural form) -- a plain MagicMock swallows
        any kwarg silently, so this TypeError was invisible to
        test_dataset_b_resolves_defaults above and would only surface on a
        real, non-mocked run. autospec=True makes the mock enforce the real
        method signature instead."""
        stats = MagicMock(fixtures_collected=5)
        with patch("collection.resume_utils.database_has_rows", return_value=False):
            with patch(
                "collection.human_corpus.HumanCorpusCollector", autospec=True
            ) as MockCollector:
                MockCollector.return_value.run.return_value = (
                    stats,
                    paths.db_path("b"),
                )
                rc = main(["extract-fixtures", "--dataset", "b", "--workers", "16"])

        assert rc == 0
        MockCollector.return_value.run.assert_called_once_with(
            repos_per_language=None,
            language=None,
            workers=16,
            force=False,
        )

    def test_dataset_c_resolves_defaults(self):
        fake_repos = [{"full_name": "o/r", "language": "python"}]
        with patch("collection.resume_utils.database_has_rows", return_value=False):
            with patch(
                "collection.dataset_c.load_dataset_c_repos",
                return_value=fake_repos,
            ) as mock_load:
                with patch(
                    "collection.dataset_c.collect_dataset_c_fixtures",
                    return_value=({"python": 1}, paths.db_path("c")),
                ) as mock_extract:
                    rc = main(["extract-fixtures", "--dataset", "c"])

        assert rc == 0
        mock_load.assert_called_once_with(paths.stage_dir("c", "repos") / "all.csv")
        mock_extract.assert_called_once_with(
            fake_repos,
            clones_dir=paths.ROOT_DIR / "clones",
            output_db=paths.db_path("c"),
            workers=8,
            language=None,
        )

    def test_dataset_c_language_filter_selects_per_language_csv(self):
        with patch("collection.resume_utils.database_has_rows", return_value=False):
            with patch(
                "collection.dataset_c.load_dataset_c_repos", return_value=[]
            ) as mock_load:
                with patch(
                    "collection.dataset_c.collect_dataset_c_fixtures",
                    return_value=({}, paths.db_path("c")),
                ):
                    main(
                        [
                            "extract-fixtures",
                            "--dataset",
                            "c",
                            "--language",
                            "python",
                        ]
                    )

        mock_load.assert_called_once_with(
            paths.stage_dir("c", "repos") / "python_repo.csv"
        )


class TestAnalyzeDistribution:
    def test_defaults_to_a_vs_b(self):
        with patch(
            "collection.dataset_pipeline.analyze_distribution",
            return_value={
                "a": {"statistics": {"total_fixtures": 10}},
                "b": {"statistics": {"total_fixtures": 5}},
                "sampling_recommendation": {"target_count": 5},
            },
        ) as mock_analyze:
            rc = main(["analyze-distribution"])

        assert rc == 0
        mock_analyze.assert_called_once_with("a", "b")

    def test_explicit_dataset_and_against(self):
        with patch(
            "collection.dataset_pipeline.analyze_distribution",
            return_value={
                "b": {"statistics": {"total_fixtures": 5}},
                "c": {"statistics": {"total_fixtures": 3}},
                "sampling_recommendation": {"target_count": 3},
            },
        ) as mock_analyze:
            main(["analyze-distribution", "--dataset", "b", "--against", "c"])

        mock_analyze.assert_called_once_with("b", "c")


class TestSample:
    def test_resolves_defaults(self):
        with patch("collection.dataset_pipeline.sample_dataset") as mock_sample:
            rc = main(["sample", "--dataset", "a"])

        assert rc == 0
        mock_sample.assert_called_once_with(
            "a", target_count=None, stratify_by="fixture_type", tolerance=0.02, seed=42
        )

    def test_explicit_target_count(self):
        with patch("collection.dataset_pipeline.sample_dataset") as mock_sample:
            main(["sample", "--dataset", "a", "--target-count", "50"])

        assert mock_sample.call_args.kwargs["target_count"] == 50


class TestExport:
    def test_resolves_defaults(self):
        with patch("collection.dataset_pipeline.export_dataset") as mock_export:
            rc = main(["export", "--dataset", "a"])

        assert rc == 0
        mock_export.assert_called_once_with("a", version="1.0")


class TestValidate:
    def test_pass_returns_zero(self):
        with patch(
            "collection.dataset_pipeline.validate_dataset",
            return_value={
                "valid": True,
                "zip_path": "/x/a.zip",
                "independence_validation": {"issues": []},
            },
        ):
            rc = main(["validate", "--dataset", "a"])

        assert rc == 0

    def test_fail_returns_one(self):
        with patch(
            "collection.dataset_pipeline.validate_dataset",
            return_value={
                "valid": False,
                "zip_path": "/x/a.zip",
                "independence_validation": {"issues": ["missing column"]},
            },
        ):
            rc = main(["validate", "--dataset", "a"])

        assert rc == 1
