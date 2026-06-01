"""Command-line entrypoint for the paired-study collection package."""

from __future__ import annotations

import argparse
import sys

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

    if args.command == "status":
        print("Use `python -m collection paired` to run the study.")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
