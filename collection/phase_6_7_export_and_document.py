"""
Phase 6-7: Create databases and export as ZIP archives.

This script:
1. Creates filtered databases containing only sampled fixtures
2. Exports to CSV format
3. Generates documentation (README, SCHEMA, AGENTS for LLM)
4. Creates standalone ZIP archives

Input:
  - phase_5_sampling_results_*.json (from Phase 5)
  - fixturedb-human.db, fixturedb-llm.db (from Phases 2-3)

Output:
  - fixturedb-human_v1.0_export.zip
  - fixturedb-llm_v1.0_export.zip
"""

import json
import logging
import sys
from pathlib import Path
from datetime import datetime

from .dataset_exporter import HumanDatasetExporter, LLMDatasetExporter

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Execute Phase 6-7 export and documentation."""

    project_root = Path(__file__).parent
    human_db = project_root / 'data' / 'fixturedb-human.db'
    llm_db = project_root / 'data' / 'fixturedb-llm.db'
    output_dir = project_root / 'output'
    output_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    export_stats_file = output_dir / f'phase_67_export_stats_{timestamp}.json'

    logger.info("=" * 70)
    logger.info("PHASE 6-7: Database Export & Documentation")
    logger.info("=" * 70)
    logger.info("")

    # Load Phase 5 sampling results
    phase_5_files = sorted(output_dir.glob('phase_5_sampling_results_*.json'))
    if not phase_5_files:
        logger.error("Phase 5 sampling results not found")
        logger.error("Please run Phase 5 first")
        return 1

    phase_5_file = phase_5_files[-1]
    logger.info(f"Loading Phase 5 results from: {phase_5_file}")

    try:
        with open(phase_5_file, 'r') as f:
            phase_5_results = json.load(f)

        human_sampled_ids = phase_5_results['human_sampling']['sampled_fixture_ids']
        llm_sampled_ids = phase_5_results['llm_sampling']['sampled_fixture_ids']

        logger.info(f"Human sampled fixtures: {len(human_sampled_ids)}")
        logger.info(f"LLM sampled fixtures: {len(llm_sampled_ids)}")

    except Exception as e:
        logger.error(f"Failed to load Phase 5 results: {e}")
        return 1

    logger.info("")

    try:
        # Export human dataset
        logger.info("=" * 70)
        logger.info("Exporting Human Dataset")
        logger.info("=" * 70)

        human_export_dir = project_root / 'output' / 'human_export'
        human_export_dir.mkdir(exist_ok=True)

        human_exporter = HumanDatasetExporter(human_db, human_export_dir)
        human_result = human_exporter.export(human_sampled_ids, version="1.0")

        logger.info(f"CSV files: {len(human_result.csv_files)}")
        logger.info(f"Documentation files: {len(human_result.documentation_files)}")
        logger.info(f"ZIP archive: {human_result.zip_path.name}")
        logger.info(f"Total size: {human_result.total_size_mb:.1f} MB")

        logger.info("")

        # Export LLM dataset
        logger.info("=" * 70)
        logger.info("Exporting LLM Dataset")
        logger.info("=" * 70)

        llm_export_dir = project_root / 'output' / 'llm_export'
        llm_export_dir.mkdir(exist_ok=True)

        llm_exporter = LLMDatasetExporter(llm_db, llm_export_dir)
        llm_result = llm_exporter.export(llm_sampled_ids, version="1.0")

        logger.info(f"CSV files: {len(llm_result.csv_files)}")
        logger.info(f"Documentation files: {len(llm_result.documentation_files)}")
        logger.info(f"ZIP archive: {llm_result.zip_path.name}")
        logger.info(f"Total size: {llm_result.total_size_mb:.1f} MB")

        logger.info("")
        logger.info("=" * 70)
        logger.info("EXPORT SUMMARY")
        logger.info("=" * 70)
        logger.info("")
        logger.info(f"Human Dataset ZIP: {human_result.zip_path.name}")
        logger.info(f"  - Size: {human_result.total_size_mb:.1f} MB")
        logger.info(f"  - Fixtures: {human_result.fixture_count}")
        logger.info(f"  - Repositories: {human_result.repository_count}")
        logger.info("")
        logger.info(f"LLM Dataset ZIP: {llm_result.zip_path.name}")
        logger.info(f"  - Size: {llm_result.total_size_mb:.1f} MB")
        logger.info(f"  - Fixtures: {llm_result.fixture_count}")
        logger.info(f"  - Repositories: {llm_result.repository_count}")

        # Prepare export statistics
        export_stats = {
            'timestamp': datetime.now().isoformat(),
            'phase': 'Phase 6-7 - Export & Documentation',
            'human_dataset': {
                'zip_path': str(human_result.zip_path),
                'size_mb': human_result.total_size_mb,
                'fixture_count': human_result.fixture_count,
                'repository_count': human_result.repository_count,
                'csv_files': [f.name for f in human_result.csv_files],
                'documentation_files': [f.name for f in human_result.documentation_files],
            },
            'llm_dataset': {
                'zip_path': str(llm_result.zip_path),
                'size_mb': llm_result.total_size_mb,
                'fixture_count': llm_result.fixture_count,
                'repository_count': llm_result.repository_count,
                'csv_files': [f.name for f in llm_result.csv_files],
                'documentation_files': [f.name for f in llm_result.documentation_files],
            },
        }

        with open(export_stats_file, 'w') as f:
            json.dump(export_stats, f, indent=2)

        logger.info("")
        logger.info(f"Export statistics saved to: {export_stats_file}")
        logger.info("")
        logger.info("PHASE 6-7 COMPLETE")
        logger.info("Next: Run Phase 8 to validate standalone independence")

        return 0

    except Exception as e:
        logger.error(f"Error during export: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
