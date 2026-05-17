"""
Phase 5: Perform stratified sampling to create balanced datasets.

This script samples fixtures from both fixturedb-human.db and fixturedb-llm.db
to create two balanced datasets of equal size, stratified by fixture_type.

Input:
  - phase_4_distribution_analysis_*.json (from Phase 4)
  - fixturedb-human.db (from Phase 2)
  - fixturedb-llm.db (from Phase 3)

Output:
  - JSON file with sampling results and fixture IDs
"""

import json
import logging
import sys
from pathlib import Path
from datetime import datetime

from .dataset_sampler import StratifiedSampler
from .db import db_session

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_fixtures_from_db(db_path: Path) -> list:
    """
    Load all fixtures from a database.

    Args:
        db_path: Path to database file

    Returns:
        List of fixture dicts with id, fixture_type, etc.
    """
    fixtures = []

    try:
        with db_session(db_path) as conn:
            rows = conn.execute(
                "SELECT id, fixture_type, scope, loc, name FROM fixtures "
                "ORDER BY id"
            ).fetchall()

            fixtures = [dict(row) for row in rows]

    except Exception as e:
        logger.error(f"Failed to load fixtures from {db_path}: {e}")

    return fixtures


def main():
    """Execute Phase 5 stratified sampling."""

    project_root = Path(__file__).parent
    human_db = project_root / 'data' / 'fixturedb-human.db'
    llm_db = project_root / 'data' / 'fixturedb-llm.db'
    output_dir = project_root / 'output'
    output_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = output_dir / f'phase_5_sampling_results_{timestamp}.json'

    logger.info("=" * 70)
    logger.info("PHASE 5: Stratified Sampling")
    logger.info("=" * 70)
    logger.info("")

    # Load Phase 4 results for recommendation
    phase_4_files = sorted(output_dir.glob('phase_4_distribution_analysis_*.json'))
    target_count = None

    if phase_4_files:
        phase_4_file = phase_4_files[-1]
        logger.info(f"Loading Phase 4 results from: {phase_4_file}")
        try:
            with open(phase_4_file, 'r') as f:
                phase_4_results = json.load(f)
            target_count = phase_4_results['sampling_recommendation']['target_count']
            logger.info(f"Target sample size (from Phase 4): {target_count}")
        except Exception as e:
            logger.warning(f"Failed to load Phase 4 results: {e}")

    if not target_count:
        logger.error("Phase 4 results not found or invalid")
        logger.error("Please run Phase 4 first")
        return 1

    logger.info("")

    # Load fixtures from both databases
    logger.info("Loading fixtures from databases...")
    human_fixtures = load_fixtures_from_db(human_db)
    llm_fixtures = load_fixtures_from_db(llm_db)

    logger.info(f"Human fixtures available: {len(human_fixtures)}")
    logger.info(f"LLM fixtures available: {len(llm_fixtures)}")

    if not human_fixtures or not llm_fixtures:
        logger.error("Failed to load fixtures from databases")
        return 1

    logger.info("")

    try:
        # Perform stratified sampling
        logger.info("Performing stratified sampling...")
        sampler = StratifiedSampler(random_seed=42)

        logger.info("")
        logger.info("Sampling from human dataset...")
        human_result = sampler.sample(
            human_fixtures,
            target_count=target_count,
            stratify_by='fixture_type',
            tolerance=0.02,
        )

        logger.info("")
        logger.info("Sampling from LLM dataset...")
        llm_result = sampler.sample(
            llm_fixtures,
            target_count=target_count,
            stratify_by='fixture_type',
            tolerance=0.02,
        )

        logger.info("")
        logger.info("=" * 70)
        logger.info("SAMPLING RESULTS")
        logger.info("=" * 70)

        # Human sampling results
        logger.info("")
        logger.info("Human Dataset Sampling:")
        logger.info(f"  Target: {human_result.target_count}")
        logger.info(f"  Sampled: {human_result.sampled_count}")
        logger.info(f"  Stratify by: {human_result.stratify_by}")

        human_stats = sampler.get_sample_statistics(human_result)
        logger.info(f"  All strata within tolerance: {human_stats['all_strata_within_tolerance']}")
        logger.info("")
        logger.info("  Distribution check (fixture_type):")
        for stratum, check in sorted(human_result.distribution_check.items()):
            status = "✓" if check['tolerance_met'] else "✗"
            logger.info(
                f"    {stratum}: {check['original_ratio']*100:.1f}% → "
                f"{check['sampled_ratio']*100:.1f}% (dev: {check['deviation']*100:.2f}%) {status}"
            )

        # LLM sampling results
        logger.info("")
        logger.info("LLM Dataset Sampling:")
        logger.info(f"  Target: {llm_result.target_count}")
        logger.info(f"  Sampled: {llm_result.sampled_count}")
        logger.info(f"  Stratify by: {llm_result.stratify_by}")

        llm_stats = sampler.get_sample_statistics(llm_result)
        logger.info(f"  All strata within tolerance: {llm_stats['all_strata_within_tolerance']}")
        logger.info("")
        logger.info("  Distribution check (fixture_type):")
        for stratum, check in sorted(llm_result.distribution_check.items()):
            status = "✓" if check['tolerance_met'] else "✗"
            logger.info(
                f"    {stratum}: {check['original_ratio']*100:.1f}% → "
                f"{check['sampled_ratio']*100:.1f}% (dev: {check['deviation']*100:.2f}%) {status}"
            )

        # Prepare output
        output_data = {
            'timestamp': datetime.now().isoformat(),
            'phase': 'Phase 5 - Stratified Sampling',
            'sampling_config': {
                'target_count': target_count,
                'stratify_by': 'fixture_type',
                'tolerance': 0.02,
                'random_seed': 42,
            },
            'human_sampling': {
                'sampled_count': human_result.sampled_count,
                'target_count': human_result.target_count,
                'all_strata_within_tolerance': human_stats['all_strata_within_tolerance'],
                'distribution_check': human_result.distribution_check,
                'sampled_fixture_ids': human_result.sampled_ids,
            },
            'llm_sampling': {
                'sampled_count': llm_result.sampled_count,
                'target_count': llm_result.target_count,
                'all_strata_within_tolerance': llm_stats['all_strata_within_tolerance'],
                'distribution_check': llm_result.distribution_check,
                'sampled_fixture_ids': llm_result.sampled_ids,
            },
        }

        # Save results
        with open(output_file, 'w') as f:
            json.dump(output_data, f, indent=2)

        logger.info("")
        logger.info(f"Sampling results saved to: {output_file}")
        logger.info("")
        logger.info("PHASE 5 COMPLETE")
        logger.info("Next: Run Phase 6 to create filtered databases for export")

        return 0

    except Exception as e:
        logger.error(f"Error during sampling: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
