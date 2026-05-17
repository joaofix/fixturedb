"""
Command-line entrypoint for the collection pipeline.

Usage examples:
    python -m collection toy
    python -m collection phase-1a
    python -m collection phase-3
"""

from __future__ import annotations

import argparse
import sys
from typing import Callable

from . import toy
from .config import LANGUAGE_CONFIGS
from .phase_1a_scan_agent_commits import main as phase_1a_main
from .phase_1b_verify_agent_commits import main as phase_1b_main
from .phase_1c_assess_tier1_yield import main as phase_1c_main
from .phase_1d_discover_matched_repos import main as phase_1d_main
from .phase_2_extract_pre_2021 import main as phase_2_main
from .phase_3_extract_llm import main as phase_3_main
from .phase_4_analyze_distribution import main as phase_4_main
from .phase_5_stratified_sample import main as phase_5_main
from .phase_6_7_export_and_document import main as phase_67_main
from .phase_8_final_validation import main as phase_8_main


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="collection", description="Collection fixture pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    toy_parser = subparsers.add_parser("toy", help="Build a 20-repo-per-language toy validation dataset")
    toy_parser.add_argument("--language", choices=list(LANGUAGE_CONFIGS), help="Limit to one language (default: all languages)")
    toy_parser.add_argument("--repos-per-language", type=int, default=20, help="Target repositories per language for toy mode")
    subparsers.add_parser("phase-1a", help="Scan corpus repos for agent commits")
    subparsers.add_parser("phase-1b", help="Verify agent commits")
    subparsers.add_parser("phase-1c", help="Assess Tier 1 yield")
    subparsers.add_parser("phase-1d", help="Discover matched repos for Tier 2")
    subparsers.add_parser("phase-2", help="Extract pre-2021 human fixtures")
    subparsers.add_parser("phase-3", help="Extract LLM fixtures")
    subparsers.add_parser("phase-4", help="Analyze fixture distribution")
    subparsers.add_parser("phase-5", help="Stratified sampling")
    subparsers.add_parser("phase-6-7", help="Export and document datasets")
    subparsers.add_parser("phase-8", help="Final validation")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    command_map: dict[str, Callable[[], int | None]] = {
        "toy": lambda: toy.main([
            *(["--language", args.language] if args.language else []),
            "--repos-per-language",
            str(args.repos_per_language),
        ]),
        "phase-1a": phase_1a_main,
        "phase-1b": phase_1b_main,
        "phase-1c": phase_1c_main,
        "phase-1d": phase_1d_main,
        "phase-2": phase_2_main,
        "phase-3": phase_3_main,
        "phase-4": phase_4_main,
        "phase-5": phase_5_main,
        "phase-6-7": phase_67_main,
        "phase-8": phase_8_main,
    }

    result = command_map[args.command]()
    return int(result or 0)


if __name__ == "__main__":
    sys.exit(main())