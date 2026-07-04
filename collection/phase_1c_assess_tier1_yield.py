#!/usr/bin/env python3
"""
Phase 1C: Assess Tier 1 yield and determine if Tier 2 matching is needed.

This script evaluates the results from Phase 1A (Tier 1 agent commits in corpus)
and determines whether statistical power is sufficient or if Tier 2 supplementary
repos are needed.

Output: Decision report and recommendation for the test-commit-aware pipeline.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

# Logging is configured via collection.logging_utils.configure_logging()
from collection.logging_utils import get_logger

from .config import TIER1_MINIMUM_AGENT_COMMITS, TIER1_MINIMUM_REPOS_WITH_AGENT
from .resume_utils import latest_matching_file

logger = get_logger(__name__)


def main():
    """Execute Phase 1C assessment."""

    project_root = Path(__file__).resolve().parents[1]
    output_dir = project_root / "output"

    # Find most recent Phase 1A output
    phase_1a_files = sorted(output_dir.glob("phase_1a_agent_commits_tier1_*.json"))

    if not phase_1a_files:
        logger.error("No Phase 1A output found")
        logger.error("Please run: python phase_1a_scan_agent_commits.py")
        return 1

    phase_1a_file = phase_1a_files[-1]
    latest_assessment = latest_matching_file(output_dir, "phase_1c_assessment_*.json")

    logger.info("=" * 70)
    logger.info("PHASE 1C: Assess Tier 1 Yield")
    logger.info("=" * 70)
    logger.info(f"Loading Phase 1A results: {phase_1a_file.name}")
    logger.info("")

    if latest_assessment:
        logger.info(
            f"Phase 1C already completed previously ({latest_assessment.name}); "
            "skipping reassessment to save time"
        )
        return 0

    # Load Phase 1A results
    try:
        with open(phase_1a_file) as f:
            tier1_results = json.load(f)
    except Exception as e:
        logger.error(f"Error loading Phase 1A results: {e}")
        return 1

    # Extract key metrics
    repos_with_agent = tier1_results.get("repos_with_agent_commits", 0)
    total_agent_commits = tier1_results.get("total_agent_commits", 0)
    agents_by_type = tier1_results.get("agents_by_type", {})

    logger.info("Tier 1 Statistics:")
    logger.info(f"  Repositories scanned: {tier1_results.get('repos_scanned', 0)}")
    logger.info(f"  Repositories with agent commits: {repos_with_agent}")
    logger.info(f"  Total agent commits found: {total_agent_commits}")
    logger.info(f"  Agent distribution: {agents_by_type}")
    logger.info("")

    # Assess sufficiency
    min_repos = TIER1_MINIMUM_REPOS_WITH_AGENT
    min_commits = TIER1_MINIMUM_AGENT_COMMITS

    repos_sufficient = repos_with_agent >= min_repos
    commits_sufficient = total_agent_commits >= min_commits
    tier1_sufficient = repos_sufficient and commits_sufficient

    logger.info("Sufficiency Assessment:")
    logger.info(
        f"  Minimum repos for Tier 1: {min_repos} (found: {repos_with_agent}) {'✓' if repos_sufficient else '✗'}"
    )
    logger.info(
        f"  Minimum commits for Tier 1: {min_commits} (found: {total_agent_commits}) {'✓' if commits_sufficient else '✗'}"
    )
    logger.info("")

    # Generate decision
    assessment = {
        "tier1_sufficient": tier1_sufficient,
        "tier2_recommended": not tier1_sufficient,
        "repos_with_agent": repos_with_agent,
        "total_agent_commits": total_agent_commits,
        "agents_by_type": agents_by_type,
        "minimum_repos": min_repos,
        "minimum_commits": min_commits,
        "timestamp": datetime.now().isoformat(),
    }

    # Save assessment
    assessment_file = (
        output_dir
        / f"phase_1c_assessment_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    with open(assessment_file, "w") as f:
        json.dump(assessment, f, indent=2)

    logger.info("=" * 70)
    logger.info("ASSESSMENT DECISION")
    logger.info("=" * 70)

    if tier1_sufficient:
        logger.info("✓ Tier 1 SUFFICIENT")
        logger.info("")
        logger.info(
            "The corpus repos provide adequate agent fixture data for statistical power."
        )
        logger.info(
            "You can proceed directly to test-commit detection and fixture extraction for both corpora."
        )
        logger.info("")
        logger.info("Next steps:")
        logger.info(
            "  1. python phase_2_extract_human.py (Dataset B: detect human test "
            "commits and extract fixtures)"
        )
        logger.info(
            "  2. python phase_2b_extract_dataset_c.py (Dataset C: pre-2021 "
            "cross-repo baseline fixtures)"
        )
        logger.info(
            "  3. python phase_3_extract_agent.py (Dataset A: detect agent test "
            "commits and extract fixtures)"
        )
        logger.info("  4. Continue with Phases 4-8")

    else:
        logger.info("⚠ Tier 1 INSUFFICIENT")
        logger.info("")
        logger.info("The corpus repos have limited agent fixture data.")
        logger.info(
            "Tier 2 matching (supplementary repos) is recommended to reach statistical power."
        )
        logger.info("")
        logger.info(
            f"Gap: Need {min_repos - repos_with_agent} more repos or {min_commits - total_agent_commits} more commits"
        )
        logger.info("")
        logger.info("Next steps:")
        logger.info(
            "  1. python phase_1d_discover_matched_repos.py (find Tier 2 repos via SEART)"
        )
        logger.info("  2. Integrate Tier 2 repos into collection pipeline")
        logger.info(
            "  3. python phase_2_extract_human.py (Dataset B: detect human test "
            "commits and extract fixtures)"
        )
        logger.info(
            "  4. python phase_2b_extract_dataset_c.py (Dataset C: pre-2021 "
            "cross-repo baseline fixtures)"
        )
        logger.info(
            "  5. python phase_3_extract_agent.py (Dataset A: detect agent test "
            "commits and extract fixtures with tier labels)"
        )
        logger.info("  6. Continue with Phases 4-8")

    logger.info("")
    logger.info(f"Assessment saved to: {assessment_file.name}")
    logger.info("")

    return 0


if __name__ == "__main__":
    sys.exit(main())
