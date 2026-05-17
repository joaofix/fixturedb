"""
Human vs Agent Fixture Collection Pipeline

This package orchestrates the two-tier collection of fixtures comparing human-created
(pre-2021, through 2020-12-31) vs agent-generated (2021+) fixtures.

Two-Tier Methodology:
  Tier 1: Search existing corpus repos for agent commits (within-repo comparison)
  Tier 2: Discover matched repos via SEART (between-repo comparison, if Tier 1 insufficient)

Phases:
  Phase 1A: Scan corpus repos for agent commits (Tier 1)
  Phase 1B: Verify agent commits (Co-authored-by trailers)
  Phase 1C: Assess if Tier 1 meets statistical power thresholds
  Phase 1D: Discover matched repos (Tier 2) if needed
  Phase 2: Extract pre-2021 human fixtures (snapshot-based)
  Phase 3: Extract AGENT fixtures (Tier 1 + Tier 2 with tier labels)
  Phase 4: Analyze fixture distribution
  Phase 5: Stratified sampling to balance human/AGENT counts
  Phase 6-7: Export and documentation
  Phase 8: Final validation

Usage:
  python -m collection toy
  python -m collection phase-1a
  python -m collection phase-1b
  python -m collection phase-1c
  python -m collection phase-1d
  python -m collection phase-2
  python -m collection phase-3
  python -m collection phase-4
  python -m collection phase-5
  python -m collection phase-6-7
  python -m collection phase-8
"""

__version__ = "2.0.0"
__author__ = "ICSME NIER 2026"
