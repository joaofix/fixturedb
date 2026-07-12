"""`python -m collection toy --dataset {a,b,c}`: a small, real, end-to-end run.

Runs the exact same step functions the real pipeline uses, with every path
rooted under `toy-dataset/` instead of `datasets/`+`db/` (via each function's
`root`/explicit-dir parameters) -- never a parallel toy-only implementation.
Because `root` is a parameter, not a mutable global, a toy run is structurally
unable to write into the real `datasets/`/`db/` tree.

This performs real, small-scale network I/O (cloning a handful of repos) --
it is a smoke test of the real pipeline, not a mock.
"""

from __future__ import annotations

from . import paths
from .logging_utils import get_logger

logger = get_logger(__name__)

DEFAULT_TOY_REPOS = 5


def _toy_db_root():
    return paths.TOY_ROOT / "db"


def run_toy(dataset: str, language: str | None = None, repos: int = DEFAULT_TOY_REPOS) -> int:
    """Build one dataset end-to-end under toy-dataset/, capped to `repos` repos."""
    root = paths.TOY_ROOT
    db_root = _toy_db_root()
    languages = [language] if language else None

    if dataset == "a":
        from .agent_corpus import AgentCorpusCollector
        from .repository_quality_control import (
            agent_commit_counter,
            agent_repository_counter,
        )
        from .test_commit_filter import collect_agent_test_commits

        agent_repository_counter.run(
            limit=repos,
            languages=languages,
            source_dir=paths.RAW_SEARCH_DIR,
            output_dir=paths.stage_dir("a", "repos", root=root),
        )
        agent_commit_counter.run(
            input_dir=paths.stage_dir("a", "repos", root=root),
            output_dir=paths.stage_dir("a", "commits", root=root),
        )
        collect_agent_test_commits(
            paths.stage_dir("a", "commits", root=root),
            paths.stage_dir("a", "test-commits", root=root),
        )
        collector = AgentCorpusCollector(
            output_db=paths.db_path("a", root=db_root),
            repo_qc_dir=paths.stage_dir("a", "repos", root=root),
            commit_qc_dir=paths.stage_dir("a", "test-commits", root=root),
        )
        stats, db_path = collector.run(repos_per_language=repos, language=language)
        logger.info(f"[toy a] {stats.fixtures_collected} fixtures in {db_path}")
        return 0

    if dataset == "b":
        from .human_corpus import HumanCorpusCollector
        from .repo_resolve import resolve_dataset_b_repos

        resolve_dataset_b_repos(
            source_dir=paths.default_repo_source("b", root=root),
            output_dir=paths.stage_dir("b", "repos", root=root),
            language=language,
        )
        collector = HumanCorpusCollector(
            output_db=paths.db_path("b", root=db_root),
            repo_qc_dir=paths.stage_dir("b", "repos", root=root),
            test_commits_csv=paths.stage_dir("b", "test-commits", root=root),
        )
        stats, db_path = collector.run(repos_per_language=repos, language=language)
        logger.info(f"[toy b] {stats.fixtures_collected} fixtures in {db_path}")
        return 0

    if dataset == "c":
        from .config import DATASET_C_MIN_CREATED_DATE, HUMAN_CORPUS_CUTOFF_DATE
        from .dataset_c import collect_dataset_c_fixtures
        from .select_dataset_c_repos import select_repos, write_per_language_files

        selected = select_repos(
            raw_dir=paths.RAW_SEARCH_DIR,
            min_created=DATASET_C_MIN_CREATED_DATE,
            cutoff_date=HUMAN_CORPUS_CUTOFF_DATE,
        )
        if language:
            selected = [r for r in selected if r.get("language") == language]
        selected = selected[:repos]
        write_per_language_files(selected, paths.stage_dir("c", "repos", root=root))

        counts, db_path = collect_dataset_c_fixtures(
            selected,
            clones_dir=paths.ROOT_DIR / "clones",
            output_db=paths.db_path("c", root=db_root),
            workers=4,
            language=language,
        )
        logger.info(f"[toy c] {counts} -> {db_path}")
        return 0

    raise ValueError(f"unknown dataset {dataset!r}; expected one of {paths.DATASETS}")
