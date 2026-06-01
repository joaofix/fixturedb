"""Shared CLI argument helpers for collection entry points."""

from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path
from typing import Iterable


def add_language_arg(
    parser: ArgumentParser,
    choices: Iterable[str],
    help_text: str = "Limit to one language",
) -> None:
    parser.add_argument("--language", choices=list(choices), help=help_text)


def add_repos_per_language_arg(
    parser: ArgumentParser,
    default: int | None,
    help_text: str = "Repositories per language (None = all)",
) -> None:
    parser.add_argument(
        "--repos-per-language", type=int, default=default, help=help_text
    )


def add_workers_arg(
    parser: ArgumentParser,
    default: int,
    help_text: str = "Number of concurrent worker threads",
) -> None:
    parser.add_argument("--workers", type=int, default=default, help=help_text)


def add_output_db_arg(
    parser: ArgumentParser,
    default: Path | None,
    help_text: str,
) -> None:
    parser.add_argument("--output-db", type=Path, default=default, help=help_text)


def add_repo_dir_arg(
    parser: ArgumentParser,
    default: Path | None,
    help_text: str = "Directory containing repo-QC CSVs",
) -> None:
    parser.add_argument(
        "--repo-dir", dest="repo_qc_dir", type=Path, default=default, help=help_text
    )


def add_output_dir_arg(
    parser: ArgumentParser,
    default: Path,
    help_text: str,
) -> None:
    parser.add_argument("--output-dir", type=Path, default=default, help=help_text)


def add_commit_dir_arg(
    parser: ArgumentParser,
    default: Path,
    help_text: str,
) -> None:
    parser.add_argument(
        "--commit-dir", dest="commit_qc_dir", type=Path, default=default, help=help_text
    )


def add_raw_search_dir_arg(parser: ArgumentParser, help_text: str) -> None:
    parser.add_argument(
        "--raw-search-dir",
        dest="raw_search_dir",
        type=Path,
        default=None,
        help=help_text,
    )


def add_test_commits_csv_arg(parser: ArgumentParser, help_text: str) -> None:
    parser.add_argument(
        "--test-commits-csv", type=Path, default=None, help=help_text
    )
