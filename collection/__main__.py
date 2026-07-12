"""Command-line entrypoint for the FixtureDB collection pipeline.

One CLI, one set of step verbs shared across all three datasets, selected via
`--dataset {a,b,c}`. Each verb resolves its default input/output directories
through `collection.paths` -- see that module's docstring for the directory
layout. Not every verb applies to every dataset (e.g. `discover-commits` is
Dataset A only); invoking one that doesn't apply exits 1 with an explicit
message rather than silently doing nothing.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import paths
from .agent_patterns import PAPER_AGENT_REPOSITORY_LANGUAGES
from .cli_utils import add_language_arg, add_repos_per_language_arg, add_workers_arg
from .config import CLONES_DIR, LANGUAGE_CONFIGS
from .csv_adapter import get_adapter
from .db import db_session
from .logging_utils import get_logger
from .paired_collection import main as paired_main

logger = get_logger(__name__)

_DATASET_CHOICES = ("a", "b", "c")


def _unsupported(verb: str, dataset: str, supported: tuple[str, ...]) -> int:
    print(
        f"`{verb}` does not apply to dataset {dataset!r} "
        f"(supported datasets: {', '.join(supported)})",
        file=sys.stderr,
    )
    return 1


# ---------------------------------------------------------------------------
# discover-repos
# ---------------------------------------------------------------------------


def _cmd_discover_repos(args: argparse.Namespace) -> int:
    if args.dataset == "a":
        from .repository_quality_control import agent_repository_counter

        languages = [args.language] if args.language else None
        return agent_repository_counter.run(
            limit=args.limit or 0,
            since=args.since,
            workers=args.workers,
            languages=languages,
            source_dir=args.source_dir or paths.default_repo_source("a"),
            output_dir=args.output_dir or paths.stage_dir("a", "repos"),
        )

    if args.dataset == "b":
        from .repo_resolve import resolve_dataset_b_repos

        resolve_dataset_b_repos(
            source_dir=args.source_dir or paths.default_repo_source("b"),
            output_dir=args.output_dir or paths.stage_dir("b", "repos"),
            language=args.language,
        )
        return 0

    if args.dataset == "c":
        from .config import DATASET_C_MIN_CREATED_DATE, HUMAN_CORPUS_CUTOFF_DATE
        from .select_dataset_c_repos import select_repos, write_per_language_files

        selected = select_repos(
            raw_dir=args.source_dir or paths.default_repo_source("c"),
            min_created=DATASET_C_MIN_CREATED_DATE,
            cutoff_date=HUMAN_CORPUS_CUTOFF_DATE,
        )
        if args.language:
            selected = [r for r in selected if r.get("language") == args.language]
        write_per_language_files(
            selected, args.output_dir or paths.stage_dir("c", "repos")
        )
        return 0

    return _unsupported("discover-repos", args.dataset, _DATASET_CHOICES)


# ---------------------------------------------------------------------------
# discover-commits (Dataset A only)
# ---------------------------------------------------------------------------

_TIER2_REPO_FIELDNAMES = [
    "repo_name",
    "has_agent_config",
    "language",
    "stars",
    "clone_url",
    "num_contributors",
    "qc_reason",
    "matched_config_file",
    "processed_at",
    "discovery_tier",
]


def _merge_tier2_repos_into_csv(
    corpus_db: Path, discovered: list[dict], output_repos_dir: Path
) -> int:
    """Fetch full repo metadata for newly Tier-2-discovered repos and append
    them to `datasets/a/repos/{lang}_repo.csv`, tagged `discovery_tier=2`, so
    Tier 2 output actually flows into the commit-scan step instead of sitting
    in an unread side artifact (the old phase 1D's failure mode)."""
    if not discovered:
        return 0
    names = [d["repo_name"] for d in discovered]
    with db_session(corpus_db) as conn:
        placeholders = ",".join("?" for _ in names)
        rows = conn.execute(
            f"SELECT full_name, language, stars, clone_url FROM repositories "
            f"WHERE full_name IN ({placeholders})",
            names,
        ).fetchall()

    by_lang: dict[str, list[dict]] = {}
    now = datetime.now(timezone.utc).isoformat()
    for row in rows:
        lang = (row["language"] or "unknown").lower()
        by_lang.setdefault(lang, []).append(
            {
                "repo_name": row["full_name"],
                "has_agent_config": 1,
                "language": lang,
                "stars": row["stars"] or 0,
                "clone_url": row["clone_url"] or "",
                "num_contributors": 0,
                "qc_reason": "",
                "matched_config_file": "",
                "processed_at": now,
                "discovery_tier": 2,
            }
        )

    output_repos_dir.mkdir(parents=True, exist_ok=True)
    for lang, lang_rows in by_lang.items():
        csv_path = output_repos_dir / f"{lang}_repo.csv"
        get_adapter().append_dicts(csv_path, lang_rows, _TIER2_REPO_FIELDNAMES)
    return sum(len(v) for v in by_lang.values())


def _run_tier2_discovery(since: str) -> None:
    from . import tier2_discovery

    corpus_db = paths.corpus_db_path()
    assessment = tier2_discovery.assess_tier1_yield(corpus_db, CLONES_DIR)
    logger.info(assessment.summary)
    if assessment.sufficient:
        logger.info("Tier 1 sufficient; skipping Tier 2 discovery")
        return

    exclude = {
        r["full_name"] for r in tier2_discovery.load_corpus_repos(corpus_db)
    }
    from .config import TIER1_MINIMUM_REPOS_WITH_AGENT

    target = max(1, TIER1_MINIMUM_REPOS_WITH_AGENT - assessment.repos_with_agent)
    discovered = tier2_discovery.discover_tier2_repos(
        corpus_db, exclude=exclude, target_count=target
    )
    merged = _merge_tier2_repos_into_csv(
        corpus_db, discovered, paths.stage_dir("a", "repos")
    )
    logger.info(f"Tier 2 discovery merged {merged} repos into datasets/a/repos/")


def _cmd_discover_commits(args: argparse.Namespace) -> int:
    if args.dataset != "a":
        return _unsupported("discover-commits", args.dataset, ("a",))

    if args.tier2:
        _run_tier2_discovery(args.since)

    from .repository_quality_control import agent_commit_counter

    return agent_commit_counter.run(
        since=args.since,
        workers=args.workers,
        input_dir=args.input_dir or paths.stage_dir("a", "repos"),
        output_dir=args.output_dir or paths.stage_dir("a", "commits"),
    )


# ---------------------------------------------------------------------------
# filter-test-commits
# ---------------------------------------------------------------------------


def _cmd_filter_test_commits(args: argparse.Namespace) -> int:
    from . import test_commit_filter as tcf

    if args.dataset == "a":
        tcf.collect_agent_test_commits(
            args.input_dir or paths.stage_dir("a", "commits"),
            args.output_dir or paths.stage_dir("a", "test-commits"),
            workers=args.workers,
        )
        return 0

    if args.dataset == "b":
        tcf.collect_human_test_commits(
            args.input_dir or paths.stage_dir("b", "repos"),
            args.output_dir or paths.stage_dir("b", "test-commits"),
            workers=args.workers,
            language=args.language,
        )
        return 0

    return _unsupported("filter-test-commits", args.dataset, ("a", "b"))


# ---------------------------------------------------------------------------
# extract-fixtures
# ---------------------------------------------------------------------------


def _cmd_extract_fixtures(args: argparse.Namespace) -> int:
    if args.dataset == "a":
        from .agent_corpus import AgentCorpusCollector
        from .resume_utils import database_has_rows

        output_db = args.output_db or paths.db_path("a")
        if database_has_rows(output_db, "fixtures") and not args.force:
            logger.info(
                f"{output_db} already has fixture rows; skipping "
                "(pass --force to re-extract)"
            )
            return 0

        collector = AgentCorpusCollector(
            output_db=output_db,
            repo_qc_dir=args.repo_dir or paths.stage_dir("a", "repos"),
            commit_qc_dir=args.commit_dir or paths.stage_dir("a", "test-commits"),
        )
        stats, db_path = collector.run(
            repos_per_language=args.repos_per_language,
            languages=args.languages,
            language=args.language,
        )
        logger.info(
            f"Dataset A extraction complete: {stats.fixtures_collected} fixtures in {db_path}"
        )
        return 0

    if args.dataset == "b":
        from .human_corpus import HumanCorpusCollector
        from .resume_utils import database_has_rows

        output_db = args.output_db or paths.db_path("b")
        if database_has_rows(output_db, "fixtures") and not args.force:
            logger.info(
                f"{output_db} already has fixture rows; skipping "
                "(pass --force to re-extract)"
            )
            return 0

        collector = HumanCorpusCollector(
            output_db=output_db,
            repo_qc_dir=args.repo_dir or paths.stage_dir("b", "repos"),
            test_commits_csv=args.commit_dir or paths.stage_dir("b", "test-commits"),
        )
        stats, db_path = collector.run(
            repos_per_language=args.repos_per_language,
            languages=args.languages,
            language=args.language,
        )
        logger.info(
            f"Dataset B extraction complete: {stats.fixtures_collected} fixtures in {db_path}"
        )
        return 0

    if args.dataset == "c":
        from .dataset_c import collect_dataset_c_fixtures
        from .human_corpus import load_dataset_c_repos
        from .resume_utils import database_has_rows

        output_db = args.output_db or paths.db_path("c")
        if database_has_rows(output_db, "fixtures") and not args.force:
            logger.info(
                f"{output_db} already has fixture rows; skipping "
                "(pass --force to re-extract)"
            )
            return 0

        repos_dir = args.repo_dir or paths.stage_dir("c", "repos")
        repo_csv = repos_dir / (f"{args.language}_repo.csv" if args.language else "all.csv")
        repos = load_dataset_c_repos(repo_csv)
        counts, db_path = collect_dataset_c_fixtures(
            repos,
            clones_dir=CLONES_DIR,
            output_db=output_db,
            workers=args.workers,
            language=args.language,
        )
        logger.info(f"Dataset C extraction complete: {counts} fixtures in {db_path}")
        return 0

    return _unsupported("extract-fixtures", args.dataset, _DATASET_CHOICES)


# ---------------------------------------------------------------------------
# analyze-distribution / sample / export / validate
# ---------------------------------------------------------------------------


def _cmd_analyze_distribution(args: argparse.Namespace) -> int:
    from .dataset_pipeline import analyze_distribution

    result = analyze_distribution(args.dataset, args.against)
    rec = result["sampling_recommendation"]
    logger.info(
        f"{args.dataset}: {result[args.dataset]['statistics']['total_fixtures']} fixtures | "
        f"{args.against}: {result[args.against]['statistics']['total_fixtures']} fixtures | "
        f"balanced target: {rec['target_count']}"
    )
    return 0


def _cmd_sample(args: argparse.Namespace) -> int:
    from .dataset_pipeline import sample_dataset

    sample_dataset(
        args.dataset,
        target_count=args.target_count,
        stratify_by=args.stratify_by,
        tolerance=args.tolerance,
        seed=args.seed,
    )
    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    from .dataset_pipeline import export_dataset

    export_dataset(args.dataset, version=args.version)
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    from .dataset_pipeline import validate_dataset

    report = validate_dataset(args.dataset)
    status = "PASSED" if report["valid"] else "FAILED"
    logger.info(f"[validate {args.dataset}] {status}: {report['zip_path']}")
    if not report["valid"]:
        for issue in report["independence_validation"]["issues"]:
            logger.warning(f"  - {issue}")
    return 0 if report["valid"] else 1


def _count_csv_rows(csv_path: Path) -> int:
    with csv_path.open("r", encoding="utf-8", newline="") as fh:
        return sum(1 for _ in fh) - 1  # exclude header


def _cmd_status() -> int:
    for dataset in _DATASET_CHOICES:
        print(f"Dataset {dataset}:")
        for stage in paths.STAGE_ORDER[dataset]:
            stage_path = paths.stage_dir(dataset, stage)
            if not stage_path.exists():
                print(f"  {stage:<14} -- (not started)")
                continue
            csv_files = sorted(p for p in stage_path.glob("*.csv"))
            total_rows = 0
            for f in csv_files:
                try:
                    total_rows += max(0, _count_csv_rows(f))
                except OSError:
                    continue
            print(f"  {stage:<14} {len(csv_files)} file(s), {total_rows} row(s)")

        db_path = paths.db_path(dataset)
        if db_path.exists():
            try:
                with db_session(db_path) as conn:
                    n = conn.execute("SELECT COUNT(*) AS c FROM fixtures").fetchone()["c"]
                print(f"  db/{dataset}.db{'':<8} {n} fixture row(s)")
            except Exception:
                print(f"  db/{dataset}.db{'':<8} (exists, unreadable)")
        else:
            print(f"  db/{dataset}.db{'':<8} (not created)")
        print()

    corpus_db = paths.corpus_db_path()
    print(f"db/corpus.db: {'present' if corpus_db.exists() else 'absent (run `paired` if --tier2 is needed)'}")
    return 0


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def _add_dataset_arg(parser: argparse.ArgumentParser, choices=_DATASET_CHOICES) -> None:
    parser.add_argument(
        "--dataset", choices=list(choices), required=True, help="Which dataset"
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the `python -m collection` argument parser and its subcommands."""
    parser = argparse.ArgumentParser(
        prog="collection", description="FixtureDB collection pipeline"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    discover_repos = subparsers.add_parser(
        "discover-repos", help="Discover candidate repositories for a dataset"
    )
    _add_dataset_arg(discover_repos)
    add_language_arg(discover_repos, sorted(PAPER_AGENT_REPOSITORY_LANGUAGES))
    discover_repos.add_argument("--limit", type=int, default=0)
    discover_repos.add_argument("--since", type=str, default="2025-01-01")
    add_workers_arg(discover_repos, default=8)
    discover_repos.add_argument("--source-dir", type=Path, default=None)
    discover_repos.add_argument("--output-dir", type=Path, default=None)

    discover_commits = subparsers.add_parser(
        "discover-commits", help="Scan discovered repos for agent commits (Dataset A only)"
    )
    _add_dataset_arg(discover_commits, choices=("a",))
    discover_commits.add_argument("--since", type=str, default="2025-01-01")
    add_workers_arg(discover_commits, default=4)
    discover_commits.add_argument("--input-dir", type=Path, default=None)
    discover_commits.add_argument("--output-dir", type=Path, default=None)
    discover_commits.add_argument(
        "--tier2",
        action="store_true",
        help="If Tier-1 corpus yield is insufficient, also run Tier-2 SEART-based "
        "discovery against db/corpus.db and merge results into datasets/a/repos/",
    )

    filter_test_commits = subparsers.add_parser(
        "filter-test-commits", help="Filter commits down to ones touching test files"
    )
    _add_dataset_arg(filter_test_commits, choices=("a", "b"))
    add_language_arg(filter_test_commits, sorted(LANGUAGE_CONFIGS.keys()))
    add_workers_arg(filter_test_commits, default=12)
    filter_test_commits.add_argument("--input-dir", type=Path, default=None)
    filter_test_commits.add_argument("--output-dir", type=Path, default=None)

    extract_fixtures = subparsers.add_parser(
        "extract-fixtures", help="Extract fixtures for a dataset"
    )
    _add_dataset_arg(extract_fixtures)
    add_language_arg(extract_fixtures, sorted(LANGUAGE_CONFIGS.keys()))
    extract_fixtures.add_argument(
        "--languages", nargs="+", choices=sorted(PAPER_AGENT_REPOSITORY_LANGUAGES)
    )
    add_repos_per_language_arg(extract_fixtures, None)
    add_workers_arg(extract_fixtures, default=8)
    extract_fixtures.add_argument("--output-db", type=Path, default=None)
    extract_fixtures.add_argument("--repo-dir", type=Path, default=None)
    extract_fixtures.add_argument("--commit-dir", type=Path, default=None)
    extract_fixtures.add_argument(
        "--force",
        action="store_true",
        help="Re-extract even if the output DB already has fixture rows",
    )

    analyze_distribution = subparsers.add_parser(
        "analyze-distribution",
        help="Compare two datasets' fixture distributions and recommend a balanced sample size",
    )
    # Unlike every other verb, --dataset here defaults to "a" (paired with
    # --against, default "b") rather than being required -- its whole job is
    # comparing two corpora, so a sensible default pair keeps the common case
    # a bare `analyze-distribution` invocation.
    analyze_distribution.add_argument(
        "--dataset",
        choices=list(_DATASET_CHOICES),
        default="a",
        help="Which dataset (default: a)",
    )
    analyze_distribution.add_argument(
        "--against", choices=list(_DATASET_CHOICES), default="b"
    )

    sample = subparsers.add_parser(
        "sample", help="Stratified-sample fixtures from a dataset's DB"
    )
    _add_dataset_arg(sample)
    sample.add_argument(
        "--target-count",
        type=int,
        default=None,
        help="Exact sample size (default: sample everything, no reduction)",
    )
    sample.add_argument("--stratify-by", type=str, default="fixture_type")
    sample.add_argument("--tolerance", type=float, default=0.02)
    sample.add_argument("--seed", type=int, default=42)

    export = subparsers.add_parser(
        "export", help="Export a dataset's sampled fixtures to export/{dataset}.zip"
    )
    _add_dataset_arg(export)
    export.add_argument("--version", type=str, default="1.0")

    validate = subparsers.add_parser(
        "validate", help="Validate export/{dataset}.zip for completeness and independence"
    )
    _add_dataset_arg(validate)

    paired_parser = subparsers.add_parser(
        "paired", help="Bootstrap db/corpus.db via the paired within-repository study"
    )
    add_language_arg(paired_parser, LANGUAGE_CONFIGS, "Limit to one language")
    add_repos_per_language_arg(
        paired_parser, 50, "Repositories per language to consider"
    )
    paired_parser.add_argument(
        "--max-commits-per-role",
        type=int,
        default=8,
        help="Max commits per role to sample per repo",
    )

    toy_parser = subparsers.add_parser(
        "toy", help="Build one dataset end-to-end under toy-dataset/ at small scale"
    )
    _add_dataset_arg(toy_parser)
    add_language_arg(toy_parser, sorted(PAPER_AGENT_REPOSITORY_LANGUAGES))
    toy_parser.add_argument(
        "--repos", type=int, default=5, help="Number of repos to process (default: 5)"
    )

    subparsers.add_parser("status", help="Print a brief pipeline status summary")
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint: dispatch to the appropriate subcommand."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "discover-repos":
        return _cmd_discover_repos(args)

    if args.command == "discover-commits":
        return _cmd_discover_commits(args)

    if args.command == "filter-test-commits":
        return _cmd_filter_test_commits(args)

    if args.command == "extract-fixtures":
        return _cmd_extract_fixtures(args)

    if args.command == "paired":
        paired_args: list[str] = []
        if getattr(args, "language", None):
            paired_args.extend(["--language", args.language])
        paired_args.extend(["--repos-per-language", str(args.repos_per_language)])
        paired_args.extend(["--max-commits-per-role", str(args.max_commits_per_role)])
        return int(paired_main(paired_args) or 0)

    if args.command == "analyze-distribution":
        return _cmd_analyze_distribution(args)

    if args.command == "sample":
        return _cmd_sample(args)

    if args.command == "export":
        return _cmd_export(args)

    if args.command == "validate":
        return _cmd_validate(args)

    if args.command == "toy":
        from .toy import run_toy

        return run_toy(args.dataset, language=args.language, repos=args.repos)

    if args.command == "status":
        return _cmd_status()

    return 0


if __name__ == "__main__":
    sys.exit(main())
