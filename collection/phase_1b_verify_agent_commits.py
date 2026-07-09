"""
Phase 1B: Verify AI agent commits via Co-authored-by trailer parsing.

This script takes the repositories identified in Phase 1A and verifies agent commits
by parsing Co-authored-by trailers and other metadata from git log.

Input: phase_1a_agent_commits_tier1_*.json (output from Phase 1A)
Output: JSON file with verified agent commits per repository for the test-commit-aware extraction pipeline.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

# Logging is configured via collection.logging_utils.configure_logging()
from collection.logging_utils import get_logger

from .agent_signal_primitives import AgentCommitVerifier
from .config import AGENT_CORPUS_START_DATE
from .resume_utils import latest_matching_file

logger = get_logger(__name__)


def _load_phase1a_candidates(output_dir: Path) -> list[str] | None:
    """Return repo names discovered by Phase 1A, or None if unavailable.

    Returns None (caller should fall back to scanning all cloned repos) when
    no Phase 1A output file is found or it fails to parse.
    """
    phase_1a_files = sorted(output_dir.glob("phase_1a_agent_commits_tier1_*.json"))
    if not phase_1a_files:
        return None

    phase_1a_file = phase_1a_files[-1]  # Use latest
    logger.info(f"Loading Phase 1A results from: {phase_1a_file}")
    try:
        with open(phase_1a_file) as f:
            phase_1a_results = json.load(f)
        return list(phase_1a_results["repo_details"].keys())
    except Exception as e:
        logger.error(f"Failed to load Phase 1A results: {e}")
        logger.info("Will scan all cloned repositories instead")
        return None


def main():
    """Execute Phase 1B agent commit verification."""

    project_root = Path(__file__).resolve().parents[1]
    clones_dir = project_root / "clones"
    output_dir = project_root / "output"
    output_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"phase_1b_verified_agents_{timestamp}.json"
    latest_output = latest_matching_file(output_dir, "phase_1b_verified_agents_*.json")

    logger.info("=" * 70)
    logger.info("PHASE 1B: Verify Agent Commits")
    logger.info("=" * 70)
    logger.info(f"Clones directory: {clones_dir}")
    logger.info(f"Output will be saved to: {output_file}")
    logger.info("")

    if latest_output:
        logger.info(
            f"Phase 1B already completed previously ({latest_output.name}); "
            "skipping re-verification to save time"
        )
        return 0

    # Verify clones directory exists
    if not clones_dir.exists():
        logger.error(f"Clones directory not found: {clones_dir}")
        return 1

    # Find and load Phase 1A results if available
    # This is optional - we can work with all repos if Phase 1A not run
    repo_candidates = _load_phase1a_candidates(output_dir)
    if repo_candidates is not None:
        logger.info(
            f"Found {len(repo_candidates)} repositories with agent files from Phase 1A"
        )
    else:
        # Phase 1A results not available, use all cloned repositories
        repo_candidates = [d.name for d in clones_dir.iterdir() if d.is_dir()]
        logger.info(
            f"No Phase 1A results found. Will verify all {len(repo_candidates)} cloned repositories"
        )

    if not repo_candidates:
        logger.error("No repositories to verify")
        return 1

    logger.info("")

    try:
        # Create verifier
        verifier = AgentCommitVerifier(clones_dir=clones_dir)

        # Run verification
        logger.info("Starting agent commit verification...")
        results = verifier.verify_all(
            repo_candidates, start_date=AGENT_CORPUS_START_DATE, show_progress=True
        )

        logger.info("")
        logger.info("=" * 70)
        logger.info("VERIFICATION RESULTS SUMMARY")
        logger.info("=" * 70)

        summary = verifier.get_verification_summary(results)

        logger.info(
            f"Repositories with agent commits: {summary['total_repositories_verified']}"
        )
        logger.info(
            f"Total agent commits found: {summary['total_agent_commits_found']}"
        )
        logger.info(
            f"Average commits per repo: {summary['average_commits_per_repo']:.1f}"
        )
        logger.info("")
        logger.info("Agent Distribution (by commit count):")
        for agent, count in sorted(
            summary["agent_commit_counts"].items(), key=lambda x: x[1], reverse=True
        ):
            logger.info(f"  {agent}: {count} commits")

        # Prepare output data
        output_data = {
            "timestamp": datetime.now().isoformat(),
            "summary": summary,
            "repositories": {
                repo_name: {
                    "agent_commits": result.agent_commits,
                    "total_commits": result.total_agent_commits,
                }
                for repo_name, result in results.items()
            },
        }

        # Save results to JSON
        with open(output_file, "w") as f:
            json.dump(output_data, f, indent=2)

        logger.info("")
        logger.info(f"Results saved to: {output_file}")
        logger.info("")
        logger.info("PHASE 1B COMPLETE")
        logger.info(
            "Next: Use these verified agents to detect test commits before fixture extraction"
        )

        return 0

    except Exception as e:
        logger.error(f"Error during verification: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
