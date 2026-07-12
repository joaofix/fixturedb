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

import csv
from pathlib import Path

from . import paths
from .logging_utils import get_logger

logger = get_logger(__name__)

DEFAULT_TOY_REPOS = 5


def _toy_db_root():
    return paths.TOY_ROOT / "db"


def _read_csv_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _read_real_agent_positive_rows(language: str | None) -> list[dict]:
    """Read the real, already-collected `datasets/a/repos/*.csv` (default
    root), keeping only `has_agent_config=1` rows -- the actual corpus that
    discover-commits onward operates on. Used by `toy --dataset a
    --stratified` so a validation run doesn't re-clone thousands of raw
    candidates just to rediscover results this repo already has.
    """
    real_dir = paths.stage_dir("a", "repos")
    rows: list[dict] = []
    for csv_path in sorted(real_dir.glob("*_repo.csv")):
        for row in _read_csv_rows(csv_path):
            if language and (row.get("language") or "").strip().lower() != language:
                continue
            if str(row.get("has_agent_config") or "").strip().lower() in (
                "1",
                "true",
            ):
                rows.append(row)
    return rows


def _read_real_dataset_c_rows(language: str | None) -> list[dict]:
    """Read the real, already-selected `datasets/c/repos/*_repo.csv` (default
    root). Used by `toy --dataset c --stratified`.
    """
    real_dir = paths.stage_dir("c", "repos")
    rows: list[dict] = []
    for csv_path in sorted(real_dir.glob("*_repo.csv")):
        for row in _read_csv_rows(csv_path):
            lang = (row.get("language") or "").strip().lower()
            if language and lang != language:
                continue
            try:
                github_id = int(row.get("github_id") or 0)
            except ValueError:
                github_id = 0
            rows.append(
                {
                    "repo_name": row.get("repo_name", ""),
                    "language": lang,
                    "clone_url": row.get("clone_url", ""),
                    "github_id": github_id,
                }
            )
    return rows


def _write_repo_csvs_per_language(rows: list[dict], output_dir: Path) -> None:
    from .csv_adapter import get_adapter

    by_lang: dict[str, list[dict]] = {}
    for row in rows:
        lang = (row.get("language") or "unknown").strip().lower()
        by_lang.setdefault(lang, []).append(row)

    output_dir.mkdir(parents=True, exist_ok=True)
    adapter = get_adapter()
    for lang, lang_rows in by_lang.items():
        fieldnames = list(lang_rows[0].keys())
        adapter.write_dicts(output_dir / f"{lang}_repo.csv", lang_rows, fieldnames)


def run_toy(
    dataset: str,
    language: str | None = None,
    repos: int = DEFAULT_TOY_REPOS,
    stratified: bool = False,
) -> int:
    """Build one dataset end-to-end under toy-dataset/.

    Default mode caps at `repos` repos (global cap for a/c, per-language cap
    for b -- see collection/paths.py's STAGE_ORDER note). `stratified=True`
    ignores `repos` and instead draws a per-language sample sized by
    `sampling.cochran_sample_size` against each language's real,
    already-collected population -- a representative validation run instead
    of a quick smoke test. See internal-docs/methodology-improvements/ for
    the sample-size derivation.
    """
    root = paths.TOY_ROOT
    db_root = _toy_db_root()
    languages = [language] if language else None

    if dataset == "a":
        from .agent_corpus import AgentCorpusCollector
        from .repository_quality_control import (
            agent_commit_counter,
            agent_repository_counter,
        )
        from .sampling import sample_stratified_by_population
        from .test_commit_filter import collect_agent_test_commits

        if stratified:
            sampled = sample_stratified_by_population(
                _read_real_agent_positive_rows(language), language=language
            )
            _write_repo_csvs_per_language(
                sampled, paths.stage_dir("a", "repos", root=root)
            )
            logger.info(
                "[toy a stratified] sampled %d repos across %d language(s)",
                len(sampled),
                len({r.get("language") for r in sampled}),
            )
        else:
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
        stats, db_path = collector.run(
            repos_per_language=None if stratified else repos, language=language
        )
        logger.info(f"[toy a] {stats.fixtures_collected} fixtures in {db_path}")
        return 0

    if dataset == "b":
        from .human_corpus import HumanCorpusCollector
        from .repo_resolve import resolve_dataset_b_repos

        resolve_dataset_b_repos(
            source_dir=paths.default_repo_source("b", root=root),
            output_dir=paths.stage_dir("b", "repos", root=root),
            language=language,
            stratified=stratified,
        )
        collector = HumanCorpusCollector(
            output_db=paths.db_path("b", root=db_root),
            repo_qc_dir=paths.stage_dir("b", "repos", root=root),
            test_commits_csv=paths.stage_dir("b", "test-commits", root=root),
        )
        stats, db_path = collector.run(
            repos_per_language=None if stratified else repos, language=language
        )
        logger.info(f"[toy b] {stats.fixtures_collected} fixtures in {db_path}")
        return 0

    if dataset == "c":
        from .config import DATASET_C_MIN_CREATED_DATE, HUMAN_CORPUS_CUTOFF_DATE
        from .dataset_c import collect_dataset_c_fixtures
        from .sampling import sample_stratified_by_population
        from .select_dataset_c_repos import select_repos, write_per_language_files

        if stratified:
            selected = sample_stratified_by_population(
                _read_real_dataset_c_rows(language), language=language
            )
        else:
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
