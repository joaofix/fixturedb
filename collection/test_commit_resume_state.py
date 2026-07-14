"""Checkpoint/resume state for test-commit filtering (agent and human).

Split out of test_commit_filter.py: this is a self-contained concern (load
already-written per-language CSVs + a JSON checkpoint, resume a filtering
run without rescanning completed repos) shared by both the agent-side and
human-side filtering modules.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

from .logging_utils import get_logger

logger = get_logger(__name__)

AGENT_TEST_COMMITS_CHECKPOINT = "agent_test_commits.checkpoint.json"
HUMAN_TEST_COMMITS_CHECKPOINT = "human_test_commits.checkpoint.json"


def _load_test_commit_resume_state(
    output_dir: Path, role: str = "agent"
) -> tuple[dict[str, list[dict]], dict[str, set[str]], set[str], dict[str, int]]:
    """Generic resume loader for test-commit filtering.

    role: 'agent' or 'human' determines filename patterns and checkpoint name.
    """
    rows_by_language: dict[str, list[dict]] = defaultdict(list)
    seen_commit_shas_by_language: dict[str, set[str]] = defaultdict(set)
    completed_repos: set[str] = set()
    counts = {
        "repos_processed": 0,
        "commits_scanned": 0,
        "repos_with_test_commits": 0,
        "test_commits_found": 0,
    }

    output_dir = Path(output_dir)
    pattern = "*_test_commit.csv" if role == "agent" else "*_human_test_commit.csv"
    suffix = "_test_commit.csv" if role == "agent" else "_human_test_commit.csv"
    checkpoint_name = (
        AGENT_TEST_COMMITS_CHECKPOINT
        if role == "agent"
        else HUMAN_TEST_COMMITS_CHECKPOINT
    )

    if output_dir.exists():
        for csv_path in sorted(output_dir.glob(pattern), key=lambda p: p.name):
            language = csv_path.name.replace(suffix, "")
            with csv_path.open("r", encoding="utf-8", newline="") as fh:
                for row in csv.DictReader(fh):
                    row_dict = dict(row)
                    rows_by_language[language].append(row_dict)
                    commit_sha = (row_dict.get("commit_sha") or "").strip()
                    if commit_sha:
                        seen_commit_shas_by_language[language].add(commit_sha)

    checkpoint_path = output_dir / checkpoint_name
    if checkpoint_path.exists():
        with checkpoint_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        for key in counts:
            counts[key] = int(data.get(key, 0) or 0)
        completed_repos.update(
            str(repo_name).strip()
            for repo_name in data.get("completed_repos", [])
            if str(repo_name or "").strip()
        )

    return rows_by_language, seen_commit_shas_by_language, completed_repos, counts


def _save_test_commit_resume_state(
    output_dir: Path,
    counts: dict[str, int],
    completed_repos: set[str],
    role: str = "agent",
) -> None:
    """Generic resume saver for test-commit filtering.

    role: 'agent' or 'human' determines the checkpoint filename.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_name = (
        AGENT_TEST_COMMITS_CHECKPOINT
        if role == "agent"
        else HUMAN_TEST_COMMITS_CHECKPOINT
    )
    checkpoint_path = output_dir / checkpoint_name
    checkpoint = {
        "repos_processed": int(counts.get("repos_processed", 0) or 0),
        "commits_scanned": int(counts.get("commits_scanned", 0) or 0),
        "repos_with_test_commits": int(counts.get("repos_with_test_commits", 0) or 0),
        "test_commits_found": int(counts.get("test_commits_found", 0) or 0),
        "completed_repos": sorted(completed_repos),
    }
    with checkpoint_path.open("w", encoding="utf-8") as fh:
        json.dump(checkpoint, fh, ensure_ascii=False, indent=2)
        fh.flush()
        try:
            import os

            os.fsync(fh.fileno())
        except Exception:
            logger.debug("Unable to fsync checkpoint %s", checkpoint_path)


# Backwards-compatible wrappers for existing names
def _load_agent_test_commit_resume_state(output_dir: Path):
    return _load_test_commit_resume_state(output_dir, role="agent")


def _save_agent_test_commit_resume_state(
    output_dir: Path, counts: dict[str, int], completed_repos: set[str]
):
    return _save_test_commit_resume_state(
        output_dir, counts, completed_repos, role="agent"
    )
