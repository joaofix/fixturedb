"""
Phase 4: Analyze fixture distribution and determine sampling requirements.

This script analyzes the extracted fixtures to understand their distribution
across fixture types, scopes, and other dimensions. Used to inform sampling
strategy for the paired within-repository study.

Input:
    - paired-study database produced by the collection pipeline

Output:
  - JSON file with distribution analysis
"""

import json
import logging
import sys
from pathlib import Path
from datetime import datetime

from .db import db_session

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def analyze_database_distribution(db_path: Path) -> dict:
    """
    Analyze fixture distribution in a database.

    Args:
        db_path: Path to database file

    Returns:
        Dict with distribution analysis
    """
    stats = {
        "total_fixtures": 0,
        "by_type": {},
        "by_scope": {},
        "by_category": {},
        "repositories": 0,
        "test_files": 0,
    }

    try:
        with db_session(db_path) as conn:
            # Total fixtures
            result = conn.execute("SELECT COUNT(*) as count FROM fixtures").fetchone()
            stats["total_fixtures"] = result["count"]

            # By fixture_type
            rows = conn.execute(
                "SELECT fixture_type, COUNT(*) as count FROM fixtures "
                "GROUP BY fixture_type ORDER BY count DESC"
            ).fetchall()
            stats["by_type"] = {row["fixture_type"]: row["count"] for row in rows}

            # By scope
            rows = conn.execute(
                "SELECT scope, COUNT(*) as count FROM fixtures "
                "GROUP BY scope ORDER BY count DESC"
            ).fetchall()
            stats["by_scope"] = {row["scope"]: row["count"] for row in rows}

            # By category
            rows = conn.execute(
                "SELECT category, COUNT(*) as count FROM fixtures "
                "WHERE category IS NOT NULL "
                "GROUP BY category ORDER BY count DESC"
            ).fetchall()
            stats["by_category"] = {row["category"]: row["count"] for row in rows}

            # Repository count
            result = conn.execute(
                "SELECT COUNT(*) as count FROM repositories"
            ).fetchone()
            stats["repositories"] = result["count"]

            # Test file count
            result = conn.execute("SELECT COUNT(*) as count FROM test_files").fetchone()
            stats["test_files"] = result["count"]

    except Exception as e:
        logger.error(f"Failed to analyze {db_path}: {e}")

    return stats


def main():
    """Execute Phase 4 distribution analysis."""

    project_root = Path(__file__).parent
    human_db = project_root / "data" / "fixturedb-human.db"
    agent_db = project_root / "data" / "fixturedb-agent.db"
    output_dir = project_root / "output"
    output_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"phase_4_distribution_analysis_{timestamp}.json"

    logger.info("=" * 70)
    logger.info("PHASE 4: Analyze Fixture Distribution")
    logger.info("=" * 70)
    logger.info("")

    # Check if databases exist
    if not human_db.exists():
        logger.error(f"fixturedb-human.db not found: {human_db}")
        logger.error("Please run Phase 2 first")
        return 1

    if not agent_db.exists():
        logger.error(f"fixturedb-agent.db not found: {agent_db}")
        logger.error("Please run Phase 3 first")
        return 1

    try:
        # Analyze both databases
        logger.info("Analyzing fixturedb-human.db...")
        human_stats = analyze_database_distribution(human_db)
        logger.info(f"  Total fixtures: {human_stats['total_fixtures']}")
        logger.info(f"  Repositories: {human_stats['repositories']}")
        logger.info(f"  Test files: {human_stats['test_files']}")

        logger.info("")
        logger.info("Analyzing fixturedb-agent.db...")
        agent_stats = analyze_database_distribution(agent_db)
        logger.info(f"  Total fixtures: {agent_stats['total_fixtures']}")
        logger.info(f"  Repositories: {agent_stats['repositories']}")
        logger.info(f"  Test files: {agent_stats['test_files']}")

        logger.info("")
        logger.info("=" * 70)
        logger.info("DISTRIBUTION ANALYSIS")
        logger.info("=" * 70)

        # Compare distributions
        logger.info("")
        logger.info("Human Fixtures by Type:")
        for fixture_type, count in sorted(
            human_stats["by_type"].items(), key=lambda x: x[1], reverse=True
        ):
            pct = (
                (count / human_stats["total_fixtures"] * 100)
                if human_stats["total_fixtures"]
                else 0
            )
            logger.info(f"  {fixture_type}: {count} ({pct:.1f}%)")

        logger.info("")
        logger.info("Agent Fixtures by Type:")
        for fixture_type, count in sorted(
            agent_stats["by_type"].items(), key=lambda x: x[1], reverse=True
        ):
            pct = (
                (count / agent_stats["total_fixtures"] * 100)
                if agent_stats["total_fixtures"]
                else 0
            )
            logger.info(f"  {fixture_type}: {count} ({pct:.1f}%)")

        logger.info("")
        logger.info("Human Fixtures by Scope:")
        for scope, count in sorted(
            human_stats["by_scope"].items(), key=lambda x: x[1], reverse=True
        ):
            pct = (
                (count / human_stats["total_fixtures"] * 100)
                if human_stats["total_fixtures"]
                else 0
            )
            logger.info(f"  {scope}: {count} ({pct:.1f}%)")

        logger.info("")
        logger.info("Agent Fixtures by Scope:")
        for scope, count in sorted(
            agent_stats["by_scope"].items(), key=lambda x: x[1], reverse=True
        ):
            pct = (
                (count / agent_stats["total_fixtures"] * 100)
                if agent_stats["total_fixtures"]
                else 0
            )
            logger.info(f"  {scope}: {count} ({pct:.1f}%)")

        # Determine sampling target
        min_count = min(human_stats["total_fixtures"], agent_stats["total_fixtures"])
        max_count = max(human_stats["total_fixtures"], agent_stats["total_fixtures"])

        logger.info("")
        logger.info("=" * 70)
        logger.info("SAMPLING RECOMMENDATION")
        logger.info("=" * 70)
        logger.info(f"Human fixtures available: {human_stats['total_fixtures']}")
        logger.info(f"Agent fixtures available: {agent_stats['total_fixtures']}")
        logger.info(f"Minimum (bottleneck): {min_count}")
        logger.info(f"Balanced target: {min_count}")
        logger.info("")
        logger.info("For fair comparison, sample both datasets to:")
        logger.info(f"  Target fixture count: {min_count}")
        logger.info(f"  Stratification: fixture_type")
        logger.info(f"  Tolerance: 2%")

        # Prepare output
        output_data = {
            "timestamp": datetime.now().isoformat(),
            "phase": "Phase 4 - Distribution Analysis",
            "human_db": {
                "path": str(human_db),
                "statistics": human_stats,
            },
            "agent_db": {
                "path": str(agent_db),
                "statistics": agent_stats,
            },
            "sampling_recommendation": {
                "target_count": min_count,
                "stratify_by": "fixture_type",
                "tolerance": 0.02,
                "random_seed": 42,
            },
        }

        # Save results
        with open(output_file, "w") as f:
            json.dump(output_data, f, indent=2)

        logger.info("")
        logger.info(f"Analysis saved to: {output_file}")
        logger.info("")
        logger.info("PHASE 4 COMPLETE")
        logger.info("Next: Run Phase 5 to perform stratified sampling")

        return 0

    except Exception as e:
        logger.error(f"Error during analysis: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
