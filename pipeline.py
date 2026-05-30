#!/usr/bin/env python3
"""Entrypoint for FixtureDB pipeline: paired study, human corpus, agent corpus, and between-group analysis."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from collection.config import LANGUAGE_CONFIGS, DATA_DIR
from collection.paired_collection import main as paired_main
from collection.human_corpus import (
    HumanCorpusCollector,
    select_human_corpus_repositories,
)
from collection.agent_corpus import AgentCorpusCollector
from collection.between_group_comparison import BetweenGroupComparator
from collection.repository_quality_control.agent_repository_counter import (
    run as run_agent_repo_qc,
)
from collection.repository_quality_control.agent_commit_counter import (
    run as run_agent_commit_qc,
)
from collection.test_commit_filter import collect_agent_test_commits

try:
    sys.stdout.reconfigure(line_buffering=True, write_through=True)
    sys.stderr.reconfigure(line_buffering=True, write_through=True)
except Exception:
    pass

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent
MANUAL_REPO_QC_DIR = PROJECT_ROOT / "github-search-agent"


class TeeStream:
    def __init__(self, *streams):
        self._streams = streams

    def write(self, data):
        for stream in self._streams:
            stream.write(data)
            stream.flush()

    def flush(self):
        for stream in self._streams:
            stream.flush()


def configure_output_tee(log_file: Path | None) -> None:
    if not log_file:
        logging.basicConfig(
            level=logging.INFO, format="%(message)s", stream=sys.stdout, force=True
        )
        return

    log_file = Path(log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    file_handle = log_file.open("a", buffering=1)
    sys.stdout = TeeStream(sys.stdout, file_handle)
    sys.stderr = TeeStream(sys.stderr, file_handle)
    logging.basicConfig(
        level=logging.INFO, format="%(message)s", stream=sys.stdout, force=True
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pipeline.py",
        description="FixtureDB: Paired study, between-group analysis, and corpus collection",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # Paired study commands (backward compatible)
    for name in ("paired", "run"):
        p = sub.add_parser(name, help="Run the paired within-repository study")
        p.add_argument(
            "--language", choices=list(LANGUAGE_CONFIGS), help="Limit to one language"
        )
        p.add_argument(
            "--repos-per-language",
            type=int,
            default=None,
            help="Repositories per language (None = all)",
        )
        p.add_argument(
            "--max-commits-per-role",
            type=int,
            default=8,
            help="Max commits per role to sample per repo",
        )

    # Full between-group pipeline (new default)
    full_parser = sub.add_parser(
        "full",
        help="Run the complete between-group study pipeline (human + agent + comparison)",
    )
    full_parser.add_argument(
        "--language", choices=list(LANGUAGE_CONFIGS), help="Limit to one language"
    )
    full_parser.add_argument(
        "--repos-per-language",
        type=int,
        default=None,
        help="Repositories per language (None = all)",
    )
    full_parser.add_argument(
        "--github-token",
        type=str,
        default=None,
        help="GitHub API token (optional, for agent corpus)",
    )
    full_parser.add_argument(
        "--output-db",
        type=Path,
        default=None,
        help="Output database path (default: data/between-group.db)",
    )
    full_parser.add_argument(
        "--repo-dir",
        dest="repo_qc_dir",
        type=Path,
        default=MANUAL_REPO_QC_DIR,
        help="Directory containing the hand-built agent-enabled repository CSVs",
    )
    full_parser.add_argument(
        "--commit-dir",
        dest="commit_qc_dir",
        type=Path,
        default=MANUAL_REPO_QC_DIR,
        help="Directory containing agent commit/test-commit CSVs",
    )
    full_parser.add_argument(
        "--log-file",
        type=Path,
        default=Path("/tmp/toy_full_build_env_run.log"),
        help="Log file path for tee'd pipeline output",
    )

    # Human corpus collection (between-group design)
    human_parser = sub.add_parser(
        "human",
        help="Collect human test commits and fixtures from agent-enabled repositories",
    )
    human_parser.add_argument(
        "--language", choices=list(LANGUAGE_CONFIGS), help="Limit to one language"
    )
    human_parser.add_argument(
        "--repos-per-language", type=int, default=None, help="Repositories per language (None = all)"
    )
    human_parser.add_argument(
        "--output-db",
        type=Path,
        default=None,
        help="Output database path (default: data/between-group.db)",
    )
    human_parser.add_argument(
        "--repo-dir",
        dest="repo_qc_dir",
        type=Path,
        default=MANUAL_REPO_QC_DIR,
        help="Directory containing the hand-built agent-enabled repository CSVs",
    )
    human_parser.add_argument(
        "--test-commits-csv",
        type=Path,
        default=None,
        help="Optional CSV export for detected human test commits",
    )
    human_parser.add_argument(
        "--mode",
        choices=["within", "inter", "both"],
        default="within",
        help="Collection mode: within (within-repo), inter (inter-repo sample), or both",
    )

    # Agent corpus collection (between-group design)
    agent_parser = sub.add_parser(
        "agent", help="Collect agent test commits and fixtures (2025+)"
    )
    agent_parser.add_argument(
        "--language", choices=list(LANGUAGE_CONFIGS), help="Limit to one language"
    )
    agent_parser.add_argument(
        "--languages",
        nargs="+",
        choices=sorted(list(LANGUAGE_CONFIGS)),
        help="Limit collection to one or more languages",
    )
    agent_parser.add_argument(
        "--repos-per-language", type=int, default=None, help="Repositories per language (None = all)"
    )
    agent_parser.add_argument(
        "--github-token", type=str, default=None, help="GitHub API token (optional)"
    )
    agent_parser.add_argument(
        "--output-db",
        type=Path,
        default=None,
        help="Output database path (default: data/between-group.db)",
    )
    agent_parser.add_argument(
        "--repo-dir",
        dest="repo_qc_dir",
        type=Path,
        default=MANUAL_REPO_QC_DIR,
        help="Directory containing the hand-built agent-enabled repository CSVs",
    )
    agent_parser.add_argument(
        "--commit-dir",
        dest="commit_qc_dir",
        type=Path,
        default=MANUAL_REPO_QC_DIR,
        help="Directory containing agent commit/test-commit CSVs",
    )
    agent_parser.add_argument(
        "--test-commits-csv",
        type=Path,
        default=None,
        help="Optional CSV export for detected agent test commits",
    )
    agent_parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Parallel workers (note: collector uses configured defaults)",
    )

    # Between-group comparison
    comp_parser = sub.add_parser(
        "between-group-stats", help="Compare human vs agent corpora"
    )
    comp_parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Database path (default: data/between-group.db)",
    )
    comp_parser.add_argument(
        "--human-stats",
        type=Path,
        default=None,
        help="Path to human_corpus_summary JSON (optional)",
    )
    comp_parser.add_argument(
        "--agent-stats",
        type=Path,
        default=None,
        help="Path to agent_corpus_summary JSON (optional)",
    )

    # Status command
    sub.add_parser("status", help="Show latest summaries")

    # Standalone search extension commands (100-star workflow)
    repo_qc_parser = sub.add_parser(
        "agent-repo-qc-100",
        help="Scan merged SEART 100-star candidates and flag repos with agent config files",
    )
    repo_qc_parser.add_argument(
        "--limit", type=int, default=0, help="Limit number of repos to process (0=all)"
    )
    repo_qc_parser.add_argument(
        "--since",
        type=str,
        default="2025-01-01",
        help="Since date (kept for compatibility)",
    )
    repo_qc_parser.add_argument(
        "--workers", type=int, default=8, help="Parallel workers"
    )

    commit_qc_parser = sub.add_parser(
        "agent-commit-qc-100",
        help="Scan commit activity for repos already flagged with agent config",
    )
    commit_qc_parser.add_argument(
        "--since",
        type=str,
        default="2025-01-01",
        help="Since date for agent commit scan",
    )
    commit_qc_parser.add_argument(
        "--workers", type=int, default=4, help="Parallel workers"
    )

    test_commit_parser = sub.add_parser(
        "agent-test-commits",
        help="Build the agent test-commit dataset from agent-commit CSVs",
    )
    test_commit_parser.add_argument(
        "--commit-dir",
        dest="commit_qc_dir",
        type=Path,
        default=PROJECT_ROOT / "github-search-agent" / "agent_commits",
        help="Directory containing *_agent_commit.csv files",
    )
    test_commit_parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory to write per-language agent test commit CSVs (default: commit QC dir)",
    )
    test_commit_parser.add_argument(
        "--workers",
        type=int,
        default=12,
        help="Parallel workers to use when filtering test commits",
    )

    return parser


def cmd_human(args) -> int:
    """Collect human corpus."""
    try:
        human_kwargs = dict(
            corpus_db_path=DATA_DIR / "corpus.db",
            output_db=args.output_db,
            repo_qc_dir=args.repo_qc_dir,
        )
        if hasattr(args, "test_commits_csv"):
            human_kwargs["test_commits_csv"] = getattr(args, "test_commits_csv")
        collector = HumanCorpusCollector(**human_kwargs)
        mode = getattr(args, "mode", "within")
        if mode == "within":
            stats, db_path = collector.run(
                repos_per_language=args.repos_per_language,
                language=args.language,
            )
        elif mode == "inter":
            # Select agent-enabled repos first
            agent_repos = select_human_corpus_repositories(
                args.repo_qc_dir, args.repos_per_language, args.language
            )
            stats, db_path = collector.collect_inter_human(
                agent_repos=agent_repos,
                targets=None,
            )
        else:  # both
            stats, db_path = collector.run(
                repos_per_language=args.repos_per_language,
                language=args.language,
            )
        print(f"\n✓ Human corpus collection complete")
        print(f"  Fixtures collected: {stats.fixtures_collected}")
        print(f"  Repositories analyzed: {stats.repos_passed_qc}")
        print(f"  Output database: {db_path}\n")
        return 0
    except Exception as e:
        logger.error(f"Human corpus collection failed: {e}")
        return 1


def cmd_full(args) -> int:
    """Run the complete between-group pipeline: human + agent + comparison."""
    try:
        output_db = args.output_db or (DATA_DIR / "between-group.db")

        if getattr(args, "log_file", None):
            print(f"Logging live output to {args.log_file}")

        # Stage 1: Human corpus
        print(
            "\n=== Stage 1: Detect human test commits and collect fixtures from agent-enabled repositories ==="
        )
        human_collector = HumanCorpusCollector(
            corpus_db_path=DATA_DIR / "corpus.db",
            output_db=output_db,
            repo_qc_dir=args.repo_qc_dir,
        )
        human_stats, human_db = human_collector.run(
            repos_per_language=args.repos_per_language,
            language=args.language,
        )
        print(
            f"✓ Human corpus collected: {human_stats.fixtures_collected} fixtures from {human_stats.repos_passed_qc} repos"
        )

        # Stage 2: Agent corpus
        print(
            "\n=== Stage 2: Detect agent test commits and collect fixtures (2025+) ==="
        )
        agent_collector = AgentCorpusCollector(
            github_token=args.github_token,
            output_db=output_db,
            repo_qc_dir=args.repo_qc_dir,
            commit_qc_dir=args.commit_qc_dir,
        )
        agent_stats, agent_db = agent_collector.run(
            repos_per_language=args.repos_per_language,
            language=args.language,
        )
        print(
            f"✓ Agent corpus collected: {agent_stats.fixtures_collected} fixtures from {agent_stats.repos_passed_qc} repos"
        )
        print(f"  Agent commits found: {agent_stats.agent_commits_found}")

        # Stage 3: Between-group comparison
        print("\n=== Stage 3: Compare human vs agent corpora ===")
        comparator = BetweenGroupComparator(db_path=output_db)
        comparison = comparator.run(
            human_stats=human_stats.to_dict(), agent_stats=agent_stats.to_dict()
        )
        report_path = comparator.save_report(comparison)
        print(f"✓ Between-group comparison complete")
        print(
            f"  Balance tests run: {comparison.control_variable_summary['total_tests']}"
        )
        print(
            f"  Balanced variables: {comparison.control_variable_summary['balanced_count']}"
        )
        print(
            f"  Imbalanced variables: {comparison.control_variable_summary['imbalanced_count']}"
        )
        print(f"  Report saved: {report_path}")

        if comparison.limitations:
            print("\n  Limitations:")
            for limitation in comparison.limitations:
                print(f"    - {limitation}")

        print(f"\n✓ Full between-group pipeline complete")
        print(f"  Output database: {output_db}\n")
        return 0
    except Exception as e:
        logger.error(f"Between-group pipeline failed: {e}")
        import traceback

        traceback.print_exc()
        return 1


def cmd_agent(args) -> int:
    """Collect agent corpus."""
    try:
        agent_kwargs = dict(
            github_token=args.github_token,
            output_db=args.output_db,
            repo_qc_dir=args.repo_qc_dir,
            commit_qc_dir=args.commit_qc_dir,
        )
        if hasattr(args, "test_commits_csv"):
            agent_kwargs["test_commits_csv"] = getattr(args, "test_commits_csv")
        collector = AgentCorpusCollector(**agent_kwargs)
        stats, db_path = collector.run(
            repos_per_language=args.repos_per_language,
            language=args.language,
        )
        print(f"\n✓ Agent corpus collection complete")
        print(f"  Fixtures collected: {stats.fixtures_collected}")
        print(f"  Repositories analyzed: {stats.repos_passed_qc}")
        print(f"  Agent commits found: {stats.agent_commits_found}")
        print(f"  Output database: {db_path}\n")
        return 0
    except Exception as e:
        logger.error(f"Agent corpus collection failed: {e}")
        return 1


def cmd_between_group_stats(args) -> int:
    """Compare human and agent corpora."""
    try:
        db_path = args.db or (DATA_DIR / "between-group.db")

        # Load stats if provided
        human_stats = None
        agent_stats = None

        if args.human_stats and args.human_stats.exists():
            with open(args.human_stats) as f:
                human_stats = json.load(f)

        if args.agent_stats and args.agent_stats.exists():
            with open(args.agent_stats) as f:
                agent_stats = json.load(f)

        comparator = BetweenGroupComparator(db_path=db_path)
        comparison = comparator.run(human_stats=human_stats, agent_stats=agent_stats)
        report_path = comparator.save_report(comparison)

        # Print summary
        print(f"\n✓ Between-group comparison complete")
        print(
            f"  Balance tests run: {comparison.control_variable_summary['total_tests']}"
        )
        print(
            f"  Balanced variables: {comparison.control_variable_summary['balanced_count']}"
        )
        print(
            f"  Imbalanced variables: {comparison.control_variable_summary['imbalanced_count']}"
        )
        print(f"  Report saved: {report_path}\n")

        if comparison.limitations:
            print("  Limitations:")
            for limitation in comparison.limitations:
                print(f"    - {limitation}")
            print()

        return 0
    except Exception as e:
        logger.error(f"Between-group comparison failed: {e}")
        return 1


def cmd_status() -> None:
    """Show latest summaries."""
    output_dir = Path(__file__).resolve().parent / "output"

    print("\nFixtureDB Pipeline Summary:\n")

    # Paired study
    paired_summaries = sorted(output_dir.glob("paired_study_summary_*.json"))
    if paired_summaries:
        print(f"  Paired Study (within-repo):")
        print(f"    {paired_summaries[-1].name}")

    # Human corpus
    human_summaries = sorted(output_dir.glob("human_corpus_summary_*.json"))
    if human_summaries:
        print(f"\n  Human Corpus (agent-enabled repos):")
        print(f"    {human_summaries[-1].name}")

    # Agent corpus
    agent_summaries = sorted(output_dir.glob("agent_corpus_summary_*.json"))
    if agent_summaries:
        print(f"\n  Agent Corpus (2025+):")
        print(f"    {agent_summaries[-1].name}")

    # Between-group comparison
    comparison_reports = sorted(output_dir.glob("between_group_comparison_*.json"))
    if comparison_reports:
        print(f"\n  Between-Group Comparison:")
        print(f"    {comparison_reports[-1].name}")

    print()


def cmd_agent_repo_qc_100(args) -> int:
    """Standalone step 1: repository-level agent-config scan for 100-star workflow."""
    try:
        return int(
            run_agent_repo_qc(limit=args.limit, since=args.since, workers=args.workers)
            or 0
        )
    except Exception as e:
        logger.error(f"Agent repo QC (100-star) failed: {e}")
        return 1


def cmd_agent_commit_qc_100(args) -> int:
    """Standalone step 2: commit-level agent activity scan for config-positive repos."""
    try:
        return int(run_agent_commit_qc(since=args.since, workers=args.workers) or 0)
    except Exception as e:
        logger.error(f"Agent commit QC (100-star) failed: {e}")
        return 1


def cmd_agent_test_commits(args) -> int:
    """Build the agent test-commit dataset from agent-commit CSV inputs."""
    try:
        output_dir = args.output_dir or args.commit_qc_dir
        stats = collect_agent_test_commits(
            commit_qc_dir=args.commit_qc_dir,
            output_dir=output_dir,
            workers=args.workers,
        )
        print(f"\n✓ Test-commit filtering complete")
        print(f"  Repos processed: {stats['repos_processed']}")
        print(f"  Commits scanned: {stats['commits_scanned']}")
        print(f"  Test commits found: {stats['test_commits_found']}")
        print(f"  Output dir: {stats['output_dir']}")
        for language, path in sorted(stats["output_files"].items()):
            print(f"  {language}: {path}")
        print()
        return 0
    except Exception as e:
        logger.error(f"Test-commit filtering failed: {e}")
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    configure_output_tee(getattr(args, "log_file", None))

    if args.command in {"paired", "run"}:
        paired_args: list[str] = []
        if getattr(args, "language", None):
            paired_args.extend(["--language", args.language])
        paired_args.extend(["--repos-per-language", str(args.repos_per_language)])
        paired_args.extend(["--max-commits-per-role", str(args.max_commits_per_role)])
        return int(paired_main(paired_args) or 0)

    if args.command == "full":
        return cmd_full(args)

    if args.command == "human":
        return cmd_human(args)

    if args.command == "agent":
        return cmd_agent(args)

    if args.command == "between-group-stats":
        return cmd_between_group_stats(args)

    if args.command == "status":
        cmd_status()
        return 0

    if args.command == "agent-repo-qc-100":
        return cmd_agent_repo_qc_100(args)

    if args.command == "agent-commit-qc-100":
        return cmd_agent_commit_qc_100(args)

    if args.command == "agent-test-commits":
        return cmd_agent_test_commits(args)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
