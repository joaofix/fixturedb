"""
Phase 3: Extract agent-generated fixtures from the quality-controlled commit dataset.

This script now uses the QCed repo/commit CSV exports as input instead of the
raw discovery pipeline or Phase 1B JSON artifacts.
"""

import argparse
import sys
from pathlib import Path

# Logging is configured via collection.logging_utils.configure_logging()
from collection.logging_utils import get_logger

from .agent_corpus import AgentCorpusCollector
from .agent_patterns import PAPER_AGENT_REPOSITORY_LANGUAGES
from .cli_utils import add_output_db_arg, add_repo_dir_arg, add_repos_per_language_arg

# AGENT dataset start date is configured in collection.config as AGENT_CORPUS_START_DATE
from .resume_utils import database_has_rows

logger = get_logger(__name__)


def main():
    """Execute Phase 3 agent fixture extraction."""

    parser = argparse.ArgumentParser(
        description="Extract agent fixtures from user-provided QC datasets"
    )
    project_root = Path(__file__).resolve().parents[1]
    add_output_db_arg(
        parser,
        project_root / "data" / "fixturedb-agent.db",
        "Output database path",
    )
    add_repo_dir_arg(
        parser,
        project_root / "github-search-agent" / "agent_repositories",
        "Directory containing *_agent_repo.csv files",
    )
    add_repos_per_language_arg(parser, None)
    parser.add_argument(
        "--languages",
        nargs="+",
        choices=sorted(PAPER_AGENT_REPOSITORY_LANGUAGES),
        help="Limit extraction to one or more languages",
    )
    parser.add_argument(
        "--commit-dir",
        dest="commit_qc_dir",
        type=Path,
        default=project_root / "github-search-agent" / "agent_repositories",
        help="Directory containing *_agent_commit_qc.csv files",
    )
    args = parser.parse_args()

    output_db = args.output_db
    repo_qc_dir = args.repo_qc_dir
    commit_qc_dir = args.commit_qc_dir
    output_dir = project_root / "output"
    output_dir.mkdir(exist_ok=True)

    logger.info("=" * 70)
    logger.info("PHASE 3: Extract agent-generated fixtures from QC input")
    logger.info("=" * 70)
    logger.info(f"Target database: {output_db}")
    logger.info(f"QC repo input: {repo_qc_dir}")
    logger.info(f"QC commit input: {commit_qc_dir}")
    logger.info("")

    if database_has_rows(output_db, "fixtures"):
        logger.info(
            f"Existing agent fixture database detected ({output_db.name}); "
            "skipping extraction and reusing the current results"
        )
        return 0

    try:
        collector = AgentCorpusCollector(
            output_db=output_db,
            repo_qc_dir=repo_qc_dir,
            commit_qc_dir=commit_qc_dir,
        )
        stats, db_path = collector.run(
            repos_per_language=args.repos_per_language,
            languages=args.languages,
            language=None,
        )

        logger.info("")
        logger.info("PHASE 3 COMPLETE")
        logger.info(f"Fixture database available at: {db_path}")
        logger.info("Next: run the analysis and export stages")

        return 0

    except Exception as e:
        logger.error(f"Error during extraction: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
