"""
Phase 2: Extract pre-2021 human-created fixtures.

This script extracts fixtures from repositories before 2021 (pre-AI agent era)
using a snapshot-based approach at each repository's pinned commit.

Output:
  - SQL inserts into fixturedb-human.db
  - JSON with extraction statistics
"""

import json
import logging
import sys
from pathlib import Path
from datetime import datetime

from .fixture_extractor import Pre2021FixtureExtractor
from .db import initialise_db, db_session

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Execute Phase 2 pre-2021 fixture extraction."""

    project_root = Path(__file__).parent
    clones_dir = project_root / 'clones'
    source_db = project_root / 'data' / 'corpus.db'
    output_db = project_root / 'data' / 'fixturedb-human.db'
    output_dir = project_root / 'output'
    output_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    stats_file = output_dir / f'phase_2_extraction_stats_{timestamp}.json'

    logger.info("=" * 70)
    logger.info("PHASE 2: Extract Pre-2021 Human Fixtures")
    logger.info("=" * 70)
    logger.info(f"Source database: {source_db}")
    logger.info(f"Target database: {output_db}")
    logger.info(f"Clones directory: {clones_dir}")
    logger.info(f"Statistics will be saved to: {stats_file}")
    logger.info("")

    # Verify source database exists
    if not source_db.exists():
        logger.error(f"Source database not found: {source_db}")
        logger.error("Please run Phase 1 or ensure corpus.db exists")
        return 1

    # Verify clones directory exists
    if not clones_dir.exists():
        logger.error(f"Clones directory not found: {clones_dir}")
        logger.error("Repositories must be cloned before running Phase 2")
        return 1

    # Check if any repositories are cloned
    repo_count = sum(1 for d in clones_dir.iterdir() if d.is_dir())
    if repo_count == 0:
        logger.warning("No repositories found in clones directory")
        logger.warning("Phase 2 requires cloned repositories to extract fixtures")
        return 1

    logger.info(f"Found {repo_count} cloned repositories")
    logger.info("")

    try:
        # Initialize target database
        logger.info("Initializing fixturedb-human.db...")
        initialise_db(output_db)
        logger.info("Database initialized")
        logger.info("")

        # Run extraction
        logger.info("Starting fixture extraction...")
        extractor = Pre2021FixtureExtractor(
            clones_dir=clones_dir,
            source_db=source_db,
        )

        stats = extractor.extract_all(show_progress=True)

        logger.info("")
        logger.info("=" * 70)
        logger.info("EXTRACTION RESULTS SUMMARY")
        logger.info("=" * 70)
        logger.info(f"Total repositories processed: {stats.total_repositories}")
        logger.info(f"Repositories with fixtures: {stats.repositories_with_fixtures}")
        logger.info(f"Total fixtures extracted: {stats.total_fixtures_extracted}")
        logger.info("")
        logger.info("Fixtures by type:")
        for fixture_type, count in sorted(
            stats.fixtures_by_type.items(),
            key=lambda x: x[1],
            reverse=True
        ):
            logger.info(f"  {fixture_type}: {count}")

        if stats.repositories_failed:
            logger.info("")
            logger.warning(f"Failed repositories: {len(stats.repositories_failed)}")
            for repo, error in stats.repositories_failed[:5]:
                logger.warning(f"  {repo}: {error}")

        # Prepare output data
        output_data = {
            'timestamp': datetime.now().isoformat(),
            'phase': 'Phase 2 - Pre-2021 Extraction',
            'statistics': {
                'total_repositories': stats.total_repositories,
                'repositories_with_fixtures': stats.repositories_with_fixtures,
                'total_fixtures_extracted': stats.total_fixtures_extracted,
                'fixtures_by_type': stats.fixtures_by_type,
            },
            'repositories_processed': stats.repositories_processed,
            'repositories_failed': [
                {'repo': repo, 'error': error}
                for repo, error in stats.repositories_failed
            ],
        }

        # Save statistics
        with open(stats_file, 'w') as f:
            json.dump(output_data, f, indent=2)

        logger.info("")
        logger.info(f"Statistics saved to: {stats_file}")
        logger.info("")
        logger.info("PHASE 2 COMPLETE")
        logger.info("Next: Run Phase 3 to extract LLM-generated fixtures")

        return 0

    except Exception as e:
        logger.error(f"Error during extraction: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
