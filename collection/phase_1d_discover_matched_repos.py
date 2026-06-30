#!/usr/bin/env python3
"""
Phase 1D: Discover matched repositories for Tier 2.

This phase reuses the shared Tier 2 matcher. In the current repository
setup it acts as the Tier 2 discovery/export step and supports resume
behavior so completed runs are not repeated.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

# Logging is configured via collection.logging_utils.configure_logging()
from collection.logging_utils import get_logger

from .agent_commit_detector import Tier2RepoMatcher
from .config import (
    DATA_DIR,
    TIER1_MINIMUM_AGENT_COMMITS,
    TIER1_MINIMUM_REPOS_WITH_AGENT,
)
from .resume_utils import latest_matching_file

logger = get_logger(__name__)


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    output_dir = project_root / "output"
    output_dir.mkdir(exist_ok=True)

    phase_1c_files = sorted(output_dir.glob("phase_1c_assessment_*.json"))
    latest_output = latest_matching_file(output_dir, "phase_1d_tier2_repos_*.json")

    if latest_output:
        logger.info(
            f"Phase 1D already completed previously ({latest_output.name}); skipping rediscovery"
        )
        return 0

    if not phase_1c_files:
        logger.error("No Phase 1C output found")
        logger.error("Please run: python -m collection phase-1c")
        return 1

    phase_1c_file = phase_1c_files[-1]

    logger.info("=" * 70)
    logger.info("PHASE 1D: Discover Matched Repositories (Tier 2)")
    logger.info("=" * 70)
    logger.info(f"Loading Phase 1C assessment: {phase_1c_file.name}")
    logger.info("")

    try:
        with open(phase_1c_file) as f:
            assessment = json.load(f)
    except Exception as exc:
        logger.error(f"Error loading Phase 1C assessment: {exc}")
        return 1

    repos_with_agent = int(assessment.get("repos_with_agent", 0))
    total_agent_commits = int(assessment.get("total_agent_commits", 0))
    repos_needed = max(0, TIER1_MINIMUM_REPOS_WITH_AGENT - repos_with_agent)
    commits_needed = max(0, TIER1_MINIMUM_AGENT_COMMITS - total_agent_commits)

    if assessment.get("tier1_sufficient"):
        logger.warning("Tier 1 is already sufficient; Phase 1D is optional.")

    logger.info(f"Tier 1 gap: {repos_needed} repos / {commits_needed} commits")
    logger.info("Discovering Tier 2 candidates using the shared matcher...")

    matcher = Tier2RepoMatcher(corpus_db_path=DATA_DIR / "corpus.db")
    verified_commits = matcher.collect_matched_agent_commits(
        target_repo_count=max(1, repos_needed),
        exclude_repo_names=set(),
        language=None,
        show_progress=True,
    )

    tier2_results = {
        "match_scope": "cross_repo",
        "status": "COMPLETE",
        "message": "Tier 2 discovery used local corpus candidates and shared verification logic.",
        "matching_criteria": {
            "min_repos_needed": repos_needed,
            "min_commits_gap": commits_needed,
            "must_have_agent_configs": True,
        },
        "repos_needed": repos_needed,
        "repos_found": [
            {
                "repo_name": repo_name,
                "agent_commit_count": len(commits),
                "commits": commits,
            }
            for repo_name, commits in verified_commits.items()
        ],
        "timestamp": datetime.now().isoformat(),
    }

    tier2_file = (
        output_dir
        / f"phase_1d_tier2_repos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    with open(tier2_file, "w") as f:
        json.dump(tier2_results, f, indent=2)

    logger.info("=" * 70)
    logger.info("PHASE 1D COMPLETE")
    logger.info(f"Tier 2 repos found: {len(tier2_results['repos_found'])}")
    logger.info(f"Output saved to: {tier2_file.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
