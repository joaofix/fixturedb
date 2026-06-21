"""Helpers for identifying test commits from git diffs."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable

from pydriller import Repository
from pydriller.domain.commit import ModificationType

from .config import LANGUAGE_CONFIGS, NON_CODE_EXTENSIONS
from .csv_adapter import get_adapter


def is_test_file_path(relative_path: str, language: str) -> bool:
    """Return True when a path matches the configured test-file heuristics."""
    config = LANGUAGE_CONFIGS.get(language)
    if config is None:
        return False

    rel = relative_path.replace("\\", "/").strip()
    if not rel:
        return False

    name = Path(rel).name
    name_lower = name.lower()

    if "." not in name:
        return False

    if any(name_lower.endswith(ext) for ext in NON_CODE_EXTENSIONS):
        return False

    matched = False

    for pattern in config.test_file_suffixes:
        pattern_lower = pattern.lower()
        if pattern_lower.startswith("test_"):
            if name_lower.startswith("test_") and name_lower.endswith(
                pattern_lower.split("test_")[1]
            ):
                matched = True
                break
        elif pattern_lower == "conftest.py":
            if name_lower == "conftest.py":
                matched = True
                break
        else:
            if name_lower.endswith(pattern_lower):
                matched = True
                break

    if not matched:
        rel_parts = rel.lower().split("/")
        for pattern in config.test_path_patterns:
            dir_pattern = pattern.lower().rstrip("/")
            if dir_pattern in rel_parts:
                matched = True
                break

    return matched


def collect_test_files_for_commit(
    repo_path: Path, commit_sha: str, language: str
) -> list[str]:
    """Return the test files touched by a commit."""
    try:
        commits = list(
            Repository(str(repo_path), single=commit_sha).traverse_commits()
        )
    except Exception:
        return []

    if not commits:
        return []

    commit = commits[0]
    test_files: list[str] = []
    seen: set[str] = set()

    for modified_file in commit.modified_files:
        if modified_file.change_type == ModificationType.DELETE:
            continue

        path = modified_file.new_path or modified_file.old_path or ""
        if not path:
            continue

        if path not in seen and is_test_file_path(path, language):
            seen.add(path)
            test_files.append(path)

    return test_files


def write_test_commits_csv(records: Iterable[dict], output_path: Path) -> Path:
    """Write test commit records to CSV for standalone runs."""
    adapter = get_adapter()
    rows = list(records)
    # Ensure test_file_paths is serialised to JSON string for CSV output
    for row in rows:
        tf = row.get("test_file_paths", [])
        if not isinstance(tf, str):
            row["test_file_paths"] = json.dumps(tf, ensure_ascii=False)

    fieldnames = [
        "repo_name",
        "language",
        "commit_sha",
        "commit_role",
        "agent_type",
        "commit_date",
        "test_file_count",
        "test_file_paths",
    ]

    return adapter.write_dicts(Path(output_path), rows, fieldnames)
