"""
Human vs Agent Fixture Collection Pipeline

This package now implements the paired within-repository study for FixtureDB.

Methodology:
  Sample repositories that contain both human and agent commit histories.
  Compare agent commits against non-agent commits inside the same repository.
  Record commit-level observations for paired statistical analysis.

Primary command:
  python -m collection paired

Usage:
  python -m collection paired
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
