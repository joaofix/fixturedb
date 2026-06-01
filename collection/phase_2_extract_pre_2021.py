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
import logging
import sys
from pathlib import Path
from datetime import datetime

from .cli_utils import add_output_db_arg, add_repos_per_language_arg, add_repo_dir_arg
from .human_corpus import HumanCorpusCollector
from .resume_utils import database_has_rows

# Logging is configured via collection.logging_utils.configure_logging()
from collection.logging_utils import get_logger

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

    if database_has_rows(output_db, "fixtures"):
        logger.info(
            f"Existing human fixture database detected ({output_db.name}); "
            "skipping extraction and reusing the current results"
        )
        return 0

    # Verify source database exists
    if not source_db.exists():
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
        collector = HumanCorpusCollector(
            corpus_db_path=source_db,
            clones_dir=clones_dir,
            output_db=output_db,
            repo_qc_dir=repo_qc_dir,
        )
        stats, db_path = collector.run(
            repos_per_language=args.repos_per_language, language=None
        )

        logger.info("")
        logger.info("=" * 70)
        logger.info("EXTRACTION RESULTS SUMMARY")
        logger.info("=" * 70)
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

        # Prepare output data
        output_data = {
            "timestamp": datetime.now().isoformat(),
            "phase": "Phase 2 - Human Fixture Collection",
            "statistics": {
                "repos_scanned": stats.repos_scanned,
                "repos_passed_qc": stats.repos_passed_qc,
                "fixtures_collected": stats.fixtures_collected,
                "repos_by_language": stats.repos_by_language,
            },
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
