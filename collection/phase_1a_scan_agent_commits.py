#!/usr/bin/env python3
"""
Phase 1A (Revised): Scan corpus repositories for agent commits (Tier 1).

This script searches the existing ~500-repo corpus for agent commits (2021+).
Uses Co-authored-by trailer detection to identify agent-written code.

This implements the "Tier 1 within-repo comparison" methodology from the two-tier approach.

Output: JSON file with agent commits found in corpus repos for Phase 1B verification.
"""

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# Logging is configured via collection.logging_utils.configure_logging()
from collection.logging_utils import get_logger

from .resume_utils import latest_matching_file
from .tiered_agent_corpus_scanner import Tier1RepositoryScanner

logger = get_logger(__name__)


def load_corpus_repos(corpus_db: Path) -> list:
    """
    Load repository list from corpus.db.

    Args:
        corpus_db: Path to corpus.db

    Returns:
        List of repo metadata dicts with keys: id, full_name, clone_url, status, etc.
    """
    repos = []

    try:
        conn = sqlite3.connect(corpus_db)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Load all repositories with status='analysed' or similar
        cursor.execute("""
            SELECT id, full_name, clone_url, status, stars, language
            FROM repositories
            WHERE status IN ('analysed', 'cloned')
            ORDER BY full_name
        """)

        for row in cursor.fetchall():
            repos.append(dict(row))

        conn.close()

    except sqlite3.Error as e:
        logger.error(f"Error querying corpus.db: {e}")
        return []

    return repos


def main():
    """Execute Phase 1A agent commit scanning (Tier 1)."""

    project_root = Path(__file__).resolve().parents[1]
    clones_dir = project_root / "clones"
    corpus_db = project_root / "data" / "corpus.db"
    output_dir = project_root / "output"
    output_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"phase_1a_agent_commits_tier1_{timestamp}.json"
    latest_output = latest_matching_file(
        output_dir, "phase_1a_agent_commits_tier1_*.json"
    )

    logger.info("=" * 70)
    logger.info("PHASE 1A: Scan Corpus Repos for Agent Commits (Tier 1)")
    logger.info("=" * 70)
    logger.info(f"Corpus database: {corpus_db}")
    logger.info(f"Clones directory: {clones_dir}")
    logger.info(f"Output file: {output_file}")
    logger.info("")

    if latest_output:
        logger.info(
            f"Phase 1A already completed previously ({latest_output.name}); "
            "skipping rescan to save time"
        )
        return 0

    # Verify corpus database exists
    if not corpus_db.exists():
        logger.error(f"Corpus database not found: {corpus_db}")
        logger.error("Please ensure corpus.db exists from previous collection phases")
        return 1

    # Verify clones directory exists
    if not clones_dir.exists():
        logger.error(f"Clones directory not found: {clones_dir}")
        logger.error("Please clone repositories before running Phase 1A")
        return 1

    # Load corpus repos
    logger.info("Loading repositories from corpus.db...")
    corpus_repos = load_corpus_repos(corpus_db)

    if not corpus_repos:
        logger.error("No repositories found in corpus.db")
        return 1

    logger.info(f"Loaded {len(corpus_repos)} repositories from corpus")
    logger.info("")

    try:
        # Initialize Tier 1 scanner
        scanner = Tier1RepositoryScanner(corpus_db_path=corpus_db)

        # Scan each repo for agent commits
        logger.info("Scanning repos for agent commits (2021+)...")
        logger.info("")

        tier1_results = {
            "tier": 1,
            "repos_scanned": 0,
            "repos_with_agent_commits": 0,
            "total_agent_commits": 0,
            "agents_by_type": {},
            "repo_details": {},  # {repo_name: {commits: [...]}}
            "timestamp": datetime.now().isoformat(),
        }

        for i, repo_meta in enumerate(corpus_repos, 1):
            repo_name = repo_meta["full_name"]
            repo_id = repo_meta.get("id")

            # Construct path to cloned repo
            # Repo names might be stored as "owner/repo" or "owner__repo"
            repo_clone_name = repo_name.replace("/", "__")
            repo_path = clones_dir / repo_clone_name

            if not repo_path.exists():
                # Try alternative naming
                repo_path = clones_dir / repo_name.split("/")[-1]

            if not repo_path.exists():
                logger.debug(
                    f"[{i}/{len(corpus_repos)}] Repo not found on disk: {repo_name}"
                )
                continue

            logger.info(f"[{i}/{len(corpus_repos)}] Scanning {repo_name}...")

            # Scan this repo
            agent_commits = scanner.scan_repo_for_agent_commits(repo_path)

            if agent_commits:
                tier1_results["repos_with_agent_commits"] += 1
                tier1_results["total_agent_commits"] += len(agent_commits)

                # Track by agent type
                for commit in agent_commits:
                    agent_type = commit.agent_type
                    tier1_results["agents_by_type"][agent_type] = (
                        tier1_results["agents_by_type"].get(agent_type, 0) + 1
                    )

                # Store commit details
                tier1_results["repo_details"][repo_name] = {
                    "repo_id": repo_id,
                    "commits": [
                        {
                            "sha": c.commit_sha,
                            "agent_type": c.agent_type,
                            "date": c.commit_date,
                            "author": c.author_name,
                        }
                        for c in agent_commits
                    ],
                }

                logger.info(f"  ✓ Found {len(agent_commits)} agent commits")

            tier1_results["repos_scanned"] += 1

        logger.info("")
        logger.info("=" * 70)
        logger.info("TIER 1 SCAN RESULTS")
        logger.info("=" * 70)
        logger.info(f"Repositories scanned: {tier1_results['repos_scanned']}")
        logger.info(
            f"Repositories with agent commits: {tier1_results['repos_with_agent_commits']}"
        )
        logger.info(
            f"Total agent commits found: {tier1_results['total_agent_commits']}"
        )
        logger.info("Agent distribution:")
        for agent, count in sorted(
            tier1_results["agents_by_type"].items(), key=lambda x: x[1], reverse=True
        ):
            logger.info(f"  {agent}: {count}")
        logger.info("")

        # Save results
        logger.info(f"Saving results to {output_file}...")
        with open(output_file, "w") as f:
            json.dump(tier1_results, f, indent=2)
        logger.info("✓ Results saved")
        logger.info("")

        # Recommendations for next phase
        logger.info("=" * 70)
        logger.info("NEXT STEPS")
        logger.info("=" * 70)
        logger.info("1. Run: python phase_1b_verify_agent_commits.py")
        logger.info("   (Verify Co-authored-by trailers in detected commits)")
        logger.info("")
        logger.info("2. Run: python phase_1c_assess_tier1_yield.py")
        logger.info("   (Assess if Tier 1 alone is sufficient for statistical power)")
        logger.info("")
        logger.info(
            "3. If Tier 1 insufficient, run: python phase_1d_discover_matched_repos.py"
        )
        logger.info("   (Find supplementary repos via SEART matching)")
        logger.info("")

        return 0

    except Exception as e:
        logger.error(f"Error during Phase 1A: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
