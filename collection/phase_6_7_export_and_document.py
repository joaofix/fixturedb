"""
Phase 6-7: Create databases and export as ZIP archives.

This script:
1. Creates filtered databases containing only sampled fixtures
2. Exports to CSV format
3. Generates documentation (README, SCHEMA, AGENTS for agent)
4. Creates standalone ZIP archives

Input:
  - phase_5_sampling_results_*.json (from Phase 5)
    - fixturedb-human.db, fixturedb-agent.db (from Phases 2-3)

Output:
  - fixturedb-human_v1.0_export.zip
    - fixturedb-agent_v1.0_export.zip
"""

import json
import csv
import logging
import sys
from pathlib import Path
from datetime import datetime

from .dataset_exporter import HumanDatasetExporter, AgentDatasetExporter
from .db import db_session

# Logging is configured via collection.logging_utils.configure_logging()
from collection.logging_utils import get_logger
from collection.logging_utils import get_logger

logger = get_logger(__name__)


def main():
    """Execute Phase 6-7 export and documentation."""

    project_root = Path(__file__).parent
    human_db = project_root / "data" / "fixturedb-human.db"
    agent_db = project_root / "data" / "fixturedb-agent.db"
    output_dir = project_root / "output"
    output_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    export_stats_file = output_dir / f"phase_67_export_stats_{timestamp}.json"

    logger.info("=" * 70)
    logger.info("PHASE 6-7: Database Export & Documentation")
    logger.info("=" * 70)
    logger.info("")

    # Load Phase 5 sampling results
    phase_5_files = sorted(output_dir.glob("phase_5_sampling_results_*.json"))
    if not phase_5_files:
        logger.error("Phase 5 sampling results not found")
        logger.error("Please run Phase 5 first")
        return 1

    phase_5_file = phase_5_files[-1]
    logger.info(f"Loading Phase 5 results from: {phase_5_file}")

    try:
        with open(phase_5_file, "r") as f:
            phase_5_results = json.load(f)

        human_sampled_ids = phase_5_results["human_sampling"]["sampled_fixture_ids"]
        agent_sampled_ids = phase_5_results["agent_sampling"]["sampled_fixture_ids"]

        logger.info(f"Human sampled fixtures: {len(human_sampled_ids)}")
        logger.info(f"Agent sampled fixtures: {len(agent_sampled_ids)}")

    except Exception as e:
        logger.error(f"Failed to load Phase 5 results: {e}")
        return 1

    logger.info("")

    try:
        balance_report_file = output_dir / "balance_report.csv"

        def _count_rows(db_path: Path, table: str) -> int:
            with db_session(db_path) as conn:
                return conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()[
                    "c"
                ]

        # Export human dataset
        logger.info("=" * 70)
        logger.info("Exporting Human Dataset")
        logger.info("=" * 70)

        human_export_dir = project_root / "output" / "human_export"
        human_export_dir.mkdir(exist_ok=True)

        human_exporter = HumanDatasetExporter(human_db, human_export_dir)
        human_result = human_exporter.export(human_sampled_ids, version="1.0")

        logger.info(f"CSV files: {len(human_result.csv_files)}")
        logger.info(f"Documentation files: {len(human_result.documentation_files)}")
        logger.info(f"ZIP archive: {human_result.zip_path.name}")
        logger.info(f"Total size: {human_result.total_size_mb:.1f} MB")

        logger.info("")

        # Export agent dataset
        logger.info("=" * 70)
        logger.info("Exporting Agent Dataset")
        logger.info("=" * 70)

        agent_export_dir = project_root / "output" / "agent_export"
        agent_export_dir.mkdir(exist_ok=True)

        agent_exporter = AgentDatasetExporter(agent_db, agent_export_dir)
        agent_result = agent_exporter.export(agent_sampled_ids, version="1.0")

        logger.info(f"CSV files: {len(agent_result.csv_files)}")
        logger.info(f"Documentation files: {len(agent_result.documentation_files)}")
        logger.info(f"ZIP archive: {agent_result.zip_path.name}")
        logger.info(f"Total size: {agent_result.total_size_mb:.1f} MB")

        # Emit a compact balance report as a standalone CSV artifact.
        human_raw_fixtures = _count_rows(human_db, "fixtures")
        agent_raw_fixtures = _count_rows(agent_db, "fixtures")
        human_raw_repos = _count_rows(human_db, "repositories")
        agent_raw_repos = _count_rows(agent_db, "repositories")
        human_raw_tests = _count_rows(human_db, "test_files")
        agent_raw_tests = _count_rows(agent_db, "test_files")
        human_raw_mocks = _count_rows(human_db, "mock_usages")
        agent_raw_mocks = _count_rows(agent_db, "mock_usages")

        balanced_target = min(human_raw_fixtures, agent_raw_fixtures)
        with open(balance_report_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["metric", "human", "agent", "value", "notes"],
            )
            writer.writeheader()
            writer.writerow(
                {
                    "metric": "repositories",
                    "human": human_raw_repos,
                    "agent": agent_raw_repos,
                    "value": "",
                    "notes": "raw repository counts",
                }
            )
            writer.writerow(
                {
                    "metric": "test_files",
                    "human": human_raw_tests,
                    "agent": agent_raw_tests,
                    "value": "",
                    "notes": "raw test file counts",
                }
            )
            writer.writerow(
                {
                    "metric": "fixtures",
                    "human": human_raw_fixtures,
                    "agent": agent_raw_fixtures,
                    "value": "",
                    "notes": "raw fixture counts before Phase 5 sampling",
                }
            )
            writer.writerow(
                {
                    "metric": "mock_usages",
                    "human": human_raw_mocks,
                    "agent": agent_raw_mocks,
                    "value": "",
                    "notes": "raw mock usage counts",
                }
            )
            writer.writerow(
                {
                    "metric": "agent_human_fixture_ratio",
                    "human": "",
                    "agent": "",
                    "value": (
                        round(agent_raw_fixtures / human_raw_fixtures, 4)
                        if human_raw_fixtures
                        else 0
                    ),
                    "notes": "ratio of agent fixtures to human fixtures",
                }
            )
            writer.writerow(
                {
                    "metric": "balanced_target",
                    "human": balanced_target,
                    "agent": balanced_target,
                    "value": "",
                    "notes": "Phase 4 target count for balanced sampling",
                }
            )
            writer.writerow(
                {
                    "metric": "sampled_fixtures",
                    "human": len(human_sampled_ids),
                    "agent": len(agent_sampled_ids),
                    "value": "",
                    "notes": "Phase 5 sampled fixtures per dataset",
                }
            )

        logger.info(f"Balance report saved to: {balance_report_file.name}")

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
        logger.info(f"Agent Dataset ZIP: {agent_result.zip_path.name}")
        logger.info(f"  - Size: {agent_result.total_size_mb:.1f} MB")
        logger.info(f"  - Fixtures: {agent_result.fixture_count}")
        logger.info(f"  - Repositories: {agent_result.repository_count}")

        # Prepare export statistics
        export_stats = {
            "timestamp": datetime.now().isoformat(),
            "phase": "Phase 6-7 - Export & Documentation",
            "human_dataset": {
                "zip_path": str(human_result.zip_path),
                "size_mb": human_result.total_size_mb,
                "fixture_count": human_result.fixture_count,
                "repository_count": human_result.repository_count,
                "csv_files": [f.name for f in human_result.csv_files],
                "documentation_files": [
                    f.name for f in human_result.documentation_files
                ],
            },
            "agent_dataset": {
                "zip_path": str(agent_result.zip_path),
                "size_mb": agent_result.total_size_mb,
                "fixture_count": agent_result.fixture_count,
                "repository_count": agent_result.repository_count,
                "csv_files": [f.name for f in agent_result.csv_files],
                "documentation_files": [
                    f.name for f in agent_result.documentation_files
                ],
            },
            "balance_report": str(balance_report_file),
        }

        with open(export_stats_file, "w") as f:
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


if __name__ == "__main__":
    sys.exit(main())
