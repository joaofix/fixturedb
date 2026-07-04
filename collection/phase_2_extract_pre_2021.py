"""
Phase 2: Collect human-generated fixtures from agent-enabled repositories.

This script delegates to the human corpus collector, which scans the same
agent-enabled repositories and the same commit window as the agent corpus.

Output:
    - SQL inserts into fixturedb-human.db
    - JSON with extraction statistics
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from .cli_utils import (
    add_output_db_arg,
    add_repo_dir_arg,
    add_repos_per_language_arg,
    add_workers_arg,
)
from .human_corpus import HumanCorpusCollector
from .logging_utils import configure_logging, get_logger

configure_logging(fmt="%(message)s")

logger = get_logger(__name__)


def main():
    """Execute Phase 2 human fixture collection."""

    parser = argparse.ArgumentParser(
        description="Collect human fixtures from user-provided QC datasets"
    )
    project_root = Path(__file__).resolve().parents[1]
    add_output_db_arg(
        parser,
        project_root / "data" / "fixturedb-human.db",
        "Output database path",
    )
    add_repos_per_language_arg(parser, None)
    add_repo_dir_arg(
        parser,
        project_root / "github-search-agent" / "agent_repositories",
        "Directory containing *_agent_repo.csv files",
    )
    parser.add_argument(
        "--source-db",
        type=Path,
        default=project_root / "data" / "corpus.db",
        help="Source database path",
    )
    parser.add_argument(
        "--clones-dir",
        type=Path,
        default=project_root / "clones",
        help="Directory with repository clones",
    )
    parser.add_argument(
        "--language",
        choices=["python", "javascript", "java", "typescript"],
        default=None,
        help="Process a single language (uses dataset_c_{lang}.csv)",
    )
    add_workers_arg(parser, default=4)
    args = parser.parse_args()

    clones_dir = args.clones_dir
    source_db = args.source_db
    output_db = args.output_db
    repo_qc_dir = args.repo_qc_dir
    output_dir = project_root / "output"
    output_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stats_file = output_dir / f"phase_2_extraction_stats_{timestamp}.json"

    logger.info("=" * 70)
    logger.info("PHASE 2: Collect Human Fixtures")
    logger.info("=" * 70)
    logger.info(f"Source database: {source_db}")
    logger.info(f"Target database: {output_db}")
    logger.info(f"Clones directory: {clones_dir}")
    logger.info(f"Repo-QC directory: {repo_qc_dir}")
    logger.info(f"Statistics will be saved to: {stats_file}")
    logger.info("")

    # NOTE: No top-level database_has_rows guard here. Dataset C has its own
    # per-language checkpoint (dataset_c_checkpoint_<lang>.json) and per-repo
    # persistence checkpoints inside collect_dataset_c_fixtures. A blanket
    # skip-if-db-has-rows breaks multi-language workflows.

    # Check if this is a Dataset C run (uses CSV, not corpus.db)
    dataset_c_dir = project_root / "fixtures-from-agents"
    per_lang_csv = (
        dataset_c_dir / f"dataset_c_{args.language}.csv" if args.language else None
    )
    combined_csv = dataset_c_dir / "dataset_c_sample.csv"
    is_dataset_c = (per_lang_csv and per_lang_csv.exists()) or combined_csv.exists()

    # If no language specified and no combined CSV, auto-detect per-language CSVs
    if not is_dataset_c and not args.language:
        per_lang_csvs = sorted(dataset_c_dir.glob("dataset_c_*.csv"))
        if per_lang_csvs:
            is_dataset_c = True
            logger.info(
                "Dataset C mode: auto-detected %d language CSVs: %s",
                len(per_lang_csvs),
                [p.name for p in per_lang_csvs],
            )

    if is_dataset_c:
        logger.info("Dataset C mode activated")

    # Verify source database exists (not needed for Dataset C)
    if not is_dataset_c and not source_db.exists():
        logger.error(f"Source database not found: {source_db}")
        logger.error("Please run corpus collection or ensure corpus.db exists")
        return 1

    # Verify clones directory exists
    if not clones_dir.exists():
        logger.error(f"Clones directory not found: {clones_dir}")
        logger.error("Repositories must be cloned before running Phase 2")
        return 1

    logger.info("")

    try:
        logger.info("Starting human fixture collection...")

        if is_dataset_c:
            from .dataset_c import collect_dataset_c_fixtures
            from .human_corpus import load_dataset_c_repos

            cutoff_csv = dataset_c_dir / "dataset_c_repo_cutoffs.csv"
            if args.language:
                csv_path = per_lang_csv if per_lang_csv else combined_csv
                repos = load_dataset_c_repos(csv_path)
                logger.info(
                    "Dataset C mode: loaded %d repos from %s",
                    len(repos),
                    csv_path,
                )
                stats, db_path = collect_dataset_c_fixtures(
                    agent_repos=repos,
                    clones_dir=clones_dir,
                    output_db=output_db,
                    cutoff_csv=cutoff_csv,
                    workers=getattr(args, "workers", None) or 4,
                    language=args.language,
                )
            else:
                available = sorted(dataset_c_dir.glob("dataset_c_*.csv"))
                all_stats = {}
                for lang_csv in available:
                    lang = lang_csv.stem.replace("dataset_c_", "")
                    lang_repos = load_dataset_c_repos(lang_csv)
                    logger.info(
                        "Dataset C: processing language=%s (%d repos)",
                        lang,
                        len(lang_repos),
                    )
                    stats, db_path = collect_dataset_c_fixtures(
                        agent_repos=lang_repos,
                        clones_dir=clones_dir,
                        output_db=output_db,
                        cutoff_csv=cutoff_csv,
                        workers=getattr(args, "workers", None) or 4,
                        language=lang,
                    )
                    all_stats[lang] = stats
                stats = {
                    "repos_persisted": sum(
                        s.get("repos_persisted", 0) for s in all_stats.values()
                    ),
                    "fixtures_persisted": sum(
                        s.get("fixtures_persisted", 0) for s in all_stats.values()
                    ),
                    "completed_repos": sum(
                        s.get("completed_repos", 0) for s in all_stats.values()
                    ),
                }
        else:
            collector = HumanCorpusCollector(
                corpus_db_path=source_db,
                clones_dir=clones_dir,
                output_db=output_db,
                repo_qc_dir=repo_qc_dir,
            )
            stats, db_path = collector.run(
                repos_per_language=args.repos_per_language,
                language=args.language,
            )

        logger.info("")
        logger.info("=" * 70)
        logger.info("EXTRACTION RESULTS SUMMARY")
        logger.info("=" * 70)
        if hasattr(stats, "repos_scanned"):
            logger.info(f"Total repositories processed: {stats.repos_scanned}")
            logger.info(f"Repositories passed QC: {stats.repos_passed_qc}")
            logger.info(f"Total fixtures extracted: {stats.fixtures_collected}")
            logger.info("")
            logger.info("Fixtures by language:")
            for language_name, count in sorted(
                stats.repos_by_language.items(),
                key=lambda x: x[1],
                reverse=True,
            ):
                logger.info(f"  {language_name}: {count}")
            if stats.qc_skip_reasons:
                logger.info("")
                logger.warning(f"QC skip reasons: {len(stats.qc_skip_reasons)}")
                for reason, count in sorted(
                    stats.qc_skip_reasons.items(), key=lambda x: x[1], reverse=True
                )[:5]:
                    logger.warning(f"  {reason}: {count}")
        else:
            logger.info(f"Repositories persisted: {stats.get('repos_persisted', 0)}")
            logger.info(
                f"Total fixtures extracted: {stats.get('fixtures_persisted', 0)}"
            )
            logger.info(f"Completed repos: {stats.get('completed_repos', 0)}")

        # Prepare output data
        if hasattr(stats, "repos_scanned"):
            stats_payload = {
                "repos_scanned": stats.repos_scanned,
                "repos_passed_qc": stats.repos_passed_qc,
                "fixtures_collected": stats.fixtures_collected,
                "repos_by_language": stats.repos_by_language,
            }
        else:
            stats_payload = {
                "repos_persisted": stats.get("repos_persisted", 0),
                "fixtures_persisted": stats.get("fixtures_persisted", 0),
                "completed_repos": stats.get("completed_repos", 0),
            }
        output_data = {
            "timestamp": datetime.now().isoformat(),
            "phase": "Phase 2 - Human Fixture Collection",
            "statistics": stats_payload,
            "output_database": str(db_path),
        }

        # Save statistics
        with open(stats_file, "w") as f:
            json.dump(output_data, f, indent=2)

        logger.info("")
        logger.info(f"Statistics saved to: {stats_file}")
        logger.info("")
        logger.info("PHASE 2 COMPLETE")
        logger.info("Next: Run the agent corpus and downstream export stages")

        return 0

    except Exception as e:
        logger.error(f"Error during extraction: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
