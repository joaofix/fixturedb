"""
Phase 3: Extract agent-generated fixtures from verified agent commits.

This script extracts fixtures from commits verified to be authored/co-authored by AI agents.
Uses commit-by-commit extraction with completeness validation.

Input: phase_1b_verified_agents_*.json (output from Phase 1B)
Output:
    - SQL inserts into fixturedb-agent.db
    - JSON with extraction statistics and validation results
"""

import json
import logging
import sys
from pathlib import Path
from datetime import datetime

from .fixture_extractor import AgentFixtureExtractor
from .db import initialise_db
from .config import AGENT_DATASET_START_DATE

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Execute Phase 3 LLM fixture extraction."""

    project_root = Path(__file__).parent
    clones_dir = project_root / 'clones'
    output_db = project_root / 'data' / 'fixturedb-agent.db'
    output_dir = project_root / 'output'
    output_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    stats_file = output_dir / f'phase_3_extraction_stats_{timestamp}.json'

    logger.info("=" * 70)
    logger.info("PHASE 3: Extract agent-Generated Fixtures")
    logger.info("=" * 70)
    logger.info(f"Target database: {output_db}")
    logger.info(f"Clones directory: {clones_dir}")
    logger.info(f"Statistics will be saved to: {stats_file}")
    logger.info("")

    # Verify clones directory exists
    if not clones_dir.exists():
        logger.error(f"Clones directory not found: {clones_dir}")
        logger.error("Repositories must be cloned before running Phase 3")
        return 1

    # Find and load Phase 1B results
    phase_1b_results = None
    phase_1b_files = sorted(output_dir.glob('phase_1b_verified_agents_*.json'))

    if phase_1b_files:
        phase_1b_file = phase_1b_files[-1]  # Use latest
        logger.info(f"Loading Phase 1B results from: {phase_1b_file}")
        try:
            with open(phase_1b_file, 'r') as f:
                phase_1b_results = json.load(f)
            
            agent_commits = {
                repo_name: data['agent_commits']
                for repo_name, data in phase_1b_results['repositories'].items()
            }
            
            logger.info(
                f"Found {len(agent_commits)} repositories with agent commits"
            )
        except Exception as e:
            logger.error(f"Failed to load Phase 1B results: {e}")
            return 1
    else:
        logger.error("Phase 1B results not found")
        logger.error("Please run Phase 1B before Phase 3")
        return 1

    if not agent_commits:
        logger.error("No agent commits found in Phase 1B results")
        return 1

    logger.info("")

    try:
        # Initialize target database
        logger.info("Initializing fixturedb-agent.db...")
        initialise_db(output_db)
        logger.info("Database initialized")
        logger.info("")

        # Run extraction
        logger.info("Starting agent fixture extraction...")
        extractor = AgentFixtureExtractor(
            clones_dir=clones_dir,
            start_date=AGENT_DATASET_START_DATE,
        )

        stats = extractor.extract_all(
            agent_commits=agent_commits,
            show_progress=True
        )

        logger.info("")
        logger.info("Inserting extracted fixtures into fixturedb-agent.db...")
        logger.info("Setting match_scope=within_repo for all fixtures (within-repo: corpus repositories)")
        logger.info("")

        # Insert all extracted fixtures with tier=1 label (Tier 1: corpus repos)
        inserted_count = extractor.insert_all(
            target_db=output_db,
            match_scope='within_repo'  # All Phase 1A/1B results are from within-repo (corpus repos)
        )

        logger.info("")
        logger.info("=" * 70)
        logger.info("EXTRACTION RESULTS SUMMARY")
        logger.info("=" * 70)
        logger.info(f"Repositories with agent commits: {stats.repositories_with_agent_commits}")
        logger.info(f"Repositories processed: {len(stats.repositories_processed)}")
        logger.info(f"Total fixtures extracted: {stats.total_fixtures_extracted}")
        logger.info(f"Fixtures inserted into fixturedb-llm.db: {inserted_count}")
        logger.info(f"Completely added fixtures: {stats.completely_added_fixtures}")
        logger.info(f"Partially modified fixtures: {stats.partially_modified_fixtures}")
        logger.info("")
        logger.info("Fixtures by agent:")
        for agent, count in sorted(
            stats.fixtures_by_agent.items(),
            key=lambda x: x[1],
            reverse=True
        ):
            logger.info(f"  {agent}: {count}")

        if stats.repositories_failed:
            logger.info("")
            logger.warning(f"Failed repositories: {len(stats.repositories_failed)}")
            for repo, error in stats.repositories_failed[:5]:
                logger.warning(f"  {repo}: {error}")

        # Prepare output data
        output_data = {
            'timestamp': datetime.now().isoformat(),
            'phase': 'Phase 3 - LLM Extraction',
            'statistics': {
                'repositories_with_agent_commits': stats.repositories_with_agent_commits,
                'repositories_processed': len(stats.repositories_processed),
                'total_fixtures_extracted': stats.total_fixtures_extracted,
                'completely_added_fixtures': stats.completely_added_fixtures,
                'partially_modified_fixtures': stats.partially_modified_fixtures,
                'fixtures_by_agent': stats.fixtures_by_agent,
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
        logger.info("PHASE 3 COMPLETE")
        logger.info("Next: Run Phase 4 to analyze fixture distribution")

        return 0

    except Exception as e:
        logger.error(f"Error during extraction: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
