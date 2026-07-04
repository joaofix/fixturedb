"""Phase 2: Extract Dataset B — human-authored fixtures from agent-enabled repos.

Delegates to HumanCorpusCollector, which scans the same repositories and the
same 2025+ commit window as Dataset A (see phase_3_extract_agent.py), keeping
only human (non-agent) commits that fully add a fixture. This is the matched
within-repo control sample for the agent-vs-human comparison.

For Dataset C (the independent pre-2021 cross-repo baseline), see
phase_2b_extract_dataset_c.py instead.

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
    """Execute Phase 2 Dataset B collection."""

    parser = argparse.ArgumentParser(
        description="Collect Dataset B human fixtures from user-provided QC datasets"
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
        help="Process a single language",
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
    logger.info("PHASE 2: Collect Dataset B (Human Fixtures, Within-Repo)")
    logger.info("=" * 70)
    logger.info(f"Source database: {source_db}")
    logger.info(f"Target database: {output_db}")
    logger.info(f"Clones directory: {clones_dir}")
    logger.info(f"Repo-QC directory: {repo_qc_dir}")
    logger.info(f"Statistics will be saved to: {stats_file}")
    logger.info("")

    if not source_db.exists():
        logger.error(f"Source database not found: {source_db}")
        logger.error("Please run corpus collection or ensure corpus.db exists")
        return 1

    if not clones_dir.exists():
        logger.error(f"Clones directory not found: {clones_dir}")
        logger.error("Repositories must be cloned before running Phase 2")
        return 1

    logger.info("")

    try:
        logger.info("Starting Dataset B fixture collection...")

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

        output_data = {
            "timestamp": datetime.now().isoformat(),
            "phase": "Phase 2 - Dataset B Human Fixture Collection",
            "statistics": {
                "repos_scanned": stats.repos_scanned,
                "repos_passed_qc": stats.repos_passed_qc,
                "fixtures_collected": stats.fixtures_collected,
                "repos_by_language": stats.repos_by_language,
            },
            "output_database": str(db_path),
        }

        with open(stats_file, "w") as f:
            json.dump(output_data, f, indent=2)

        logger.info("")
        logger.info(f"Statistics saved to: {stats_file}")
        logger.info("")
        logger.info("PHASE 2 COMPLETE")
        logger.info(
            "Next: Run phase_2b_extract_dataset_c.py (Dataset C), then "
            "phase_3_extract_agent.py (Dataset A) if not already done"
        )

        return 0

    except Exception as e:
        logger.error(f"Error during extraction: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
