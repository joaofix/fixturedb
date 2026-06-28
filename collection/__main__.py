"""Command-line entrypoint for the paired-study collection package."""

from __future__ import annotations

import argparse
import sys

from .classify_repos import main as classify_main
from .cli_utils import add_language_arg, add_repos_per_language_arg
from .config import LANGUAGE_CONFIGS
from .paired_collection import main as paired_main


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="collection", description="FixtureDB paired-study collection"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    paired_parser = subparsers.add_parser(
        "paired", help="Run the paired within-repository study"
    )
    add_language_arg(paired_parser, LANGUAGE_CONFIGS, "Limit to one language")
    add_repos_per_language_arg(
        paired_parser, 50, "Repositories per language to consider"
    )
    paired_parser.add_argument(
        "--max-commits-per-role",
        type=int,
        default=8,
        help="Max commits per role to sample per repo",
    )

    classify_parser = subparsers.add_parser(
        "classify", help="Classify repositories into domain categories via LLM"
    )
    add_language_arg(
        classify_parser,
        ["python", "javascript", "java", "typescript"],
        "Limit to one language",
    )
    classify_parser.add_argument(
        "--workers",
        type=int,
        default=10,
        help="Number of concurrent workers (default: %(default)s)",
    )
    classify_parser.add_argument(
        "--skip-readme",
        action="store_true",
        help="Do not fetch README excerpts from GitHub",
    )
    classify_parser.add_argument(
        "--sample",
        type=int,
        default=0,
        help="Process only N repos (for testing)",
    )
    classify_parser.add_argument(
        "--toy",
        action="store_true",
        help="Sample 10 random repos per language (40 total) for a quick end-to-end test",
    )
    classify_parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for --toy sampling (default: 42)",
    )

    subparsers.add_parser("status", help="Print a brief paired-study status summary")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "paired":
        paired_args: list[str] = []
        if getattr(args, "language", None):
            paired_args.extend(["--language", args.language])
        paired_args.extend(["--repos-per-language", str(args.repos_per_language)])
        paired_args.extend(["--max-commits-per-role", str(args.max_commits_per_role)])
        return int(paired_main(paired_args) or 0)

    if args.command == "classify":
        classify_args: list[str] = []
        if getattr(args, "language", None):
            classify_args.extend(["--language", args.language])
        classify_args.extend(["--workers", str(args.workers)])
        if getattr(args, "skip_readme", False):
            classify_args.append("--skip-readme")
        if getattr(args, "sample", 0):
            classify_args.extend(["--sample", str(args.sample)])
        if getattr(args, "toy", False):
            classify_args.append("--toy")
        if getattr(args, "seed", 42) != 42:
            classify_args.extend(["--seed", str(args.seed)])
        return classify_main(classify_args)

    if args.command == "status":
        print("Use `python -m collection paired` to run the study.")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
