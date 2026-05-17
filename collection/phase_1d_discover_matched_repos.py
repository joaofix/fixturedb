#!/usr/bin/env python3
"""
Phase 1D: Discover matched repositories for Tier 2 (SEART-based).

This script is only run if Phase 1C indicates Tier 1 is insufficient.
It uses SEART (Software Engineering Artifacts Repository) to find supplementary
repos with agent activity to supplement Tier 1 and reach statistical power.

Matching criteria:
  - Agent configuration files (CLAUDE.md, .cursorrules, etc.)
  - Same programming language as targets
  - Similar star count (within tolerance of corpus)
  - At least 100 commits, 5 test files
    - Confirmed agent commit activity (2021+)

Output: JSON file with Tier 2 repos for Phase 3 extraction.

NOTE: This is a placeholder implementation. In production, this would:
  1. Call SEART API with appropriate search filters
  2. Parse results and filter by matching criteria
  3. Clone repos and verify agent activity
"""

import json
import logging
import sys
from pathlib import Path
from datetime import datetime

from .config import (
    TIER2_MATCHING_MIN_STARS,
    TIER2_MATCHING_MAX_STARS,
    TIER2_MIN_COMMITS,
    TIER2_MIN_TEST_FILES,
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Execute Phase 1D matched repo discovery."""
    
    project_root = Path(__file__).parent
    output_dir = project_root / 'output'
    
    # Load Phase 1C assessment
    phase_1c_files = sorted(output_dir.glob('phase_1c_assessment_*.json'))
    
    if not phase_1c_files:
        logger.error("No Phase 1C output found")
        logger.error("Please run: python phase_1c_assess_tier1_yield.py")
        return 1
    
    phase_1c_file = phase_1c_files[-1]
    
    logger.info("=" * 70)
    logger.info("PHASE 1D: Discover Matched Repositories (Tier 2)")
    logger.info("=" * 70)
    logger.info(f"Loading Phase 1C assessment: {phase_1c_file.name}")
    logger.info("")
    
    # Load assessment
    try:
        with open(phase_1c_file) as f:
            assessment = json.load(f)
    except Exception as e:
        logger.error(f"Error loading Phase 1C assessment: {e}")
        return 1
    
    # Check if Tier 2 is actually needed
    if assessment.get('tier1_sufficient'):
        logger.warning("⚠ Phase 1C indicates Tier 1 is SUFFICIENT")
        logger.warning("Phase 1D (Tier 2 matching) is not needed.")
        logger.warning("")
        logger.warning("If you still want to run Tier 2 matching for comparison,")
        logger.warning("you can do so, but it's not required for statistical power.")
        logger.warning("")
    
    logger.info("Tier 2 Matching Criteria:")
    logger.info(f"  Star range: {TIER2_MATCHING_MIN_STARS}-{TIER2_MATCHING_MAX_STARS}")
    logger.info(f"  Minimum commits: {TIER2_MIN_COMMITS}")
    logger.info(f"  Minimum test files: {TIER2_MIN_TEST_FILES}")
    logger.info(f"  Must have agent config files: True")
    logger.info("")
    
    logger.info("=" * 70)
    logger.info("SEART QUERY PLAN")
    logger.info("=" * 70)
    logger.info("")
    logger.info("This is a PLACEHOLDER implementation.")
    logger.info("In production, Phase 1D would:")
    logger.info("")
    logger.info("1. Query SEART for repos with agent config files:")
    logger.info("   - Search for files: CLAUDE.md, .cursorrules, .copilot-instructions.md, etc.")
    logger.info("   - Filter by language (Python, Java, etc.)")
    logger.info("   - Filter by star range")
    logger.info("")
    logger.info("2. For each matching repo:")
    logger.info("   - Clone repository")
    logger.info("   - Verify agent commits (Co-authored-by trailers)")
    logger.info("   - Check min commits and test files")
    logger.info("   - Extract agent commit metadata")
    logger.info("")
    logger.info("3. Select stratified sample:")
    logger.info("   - Match domain labels from corpus (if available)")
    logger.info("   - Balance agent type distribution")
    logger.info("   - Target specific count based on Phase 1C gap")
    logger.info("")
    logger.info("4. Output Tier 2 repos ready for Phase 3 extraction")
    logger.info("")
    
    # Create placeholder output
    tier2_results = {
        'match_scope': 'cross_repo',
        'status': 'PLACEHOLDER',
        'message': 'Phase 1D is a placeholder. In production, use SEART API to discover matching repos.',
        'matching_criteria': {
            'star_range': [TIER2_MATCHING_MIN_STARS, TIER2_MATCHING_MAX_STARS],
            'min_commits': TIER2_MIN_COMMITS,
            'min_test_files': TIER2_MIN_TEST_FILES,
            'must_have_agent_configs': True,
        },
        'repos_needed': max(0, assessment.get('minimum_repos', 30) - assessment.get('repos_with_agent', 0)),
        'repos_found': [],
        'timestamp': datetime.now().isoformat(),
    }
    
    # Save placeholder output
    tier2_file = output_dir / f'phase_1d_tier2_repos_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    with open(tier2_file, 'w') as f:
        json.dump(tier2_results, f, indent=2)
    
    logger.info("=" * 70)
    logger.info("PLACEHOLDER OUTPUT")
    logger.info("=" * 70)
    logger.info("")
    logger.info(f"Tier 2 repos needed: {tier2_results['repos_needed']}")
    logger.info("Tier 2 repos found: 0 (placeholder - requires SEART API integration)")
    logger.info("")
    logger.info(f"Output saved to: {tier2_file.name}")
    logger.info("")
    
    logger.info("To proceed with full implementation:")
    logger.info("1. Integrate SEART API client")
    logger.info("2. Implement repo matching and filtering logic")
    logger.info("3. Add repository cloning and verification")
    logger.info("4. Update Phase 3 to process both Tier 1 and Tier 2 repos")
    logger.info("")
    
    # For now, recommend proceeding with available Tier 1 data
    logger.info("For now, you can proceed with available Tier 1 data:")
    logger.info("  1. python phase_2_extract_pre_2021.py")
    logger.info("  2. python phase_3_extract_llm.py")
    logger.info("  3. Continue with Phases 4-8")
    logger.info("")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
