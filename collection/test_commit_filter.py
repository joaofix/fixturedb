"""Standalone filtering of agent commit datasets down to test commits."""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .agent_corpus import collect_test_files_for_commit
from .agent_commit_detector import Tier1RepositoryScanner
from .clone_manager import temp_clone_commit_history
from .config import (
    AGENT_CORPUS_START_DATE,
    CLONES_DIR,
    HUMAN_CORPUS_CUTOFF_DATE,
    LANGUAGE_CONFIGS,
)
from .test_commit_utils import write_test_commits_csv

logger = logging.getLogger(__name__)

AGENT_TEST_COMMITS_CHECKPOINT = "agent_test_commits.checkpoint.json"
HUMAN_TEST_COMMITS_CHECKPOINT = "human_test_commits.checkpoint.json"


def _load_agent_commit_rows(commit_qc_dir: Path) -> list[dict]:
    rows: list[dict] = []
    commit_dir = Path(commit_qc_dir)
    csv_paths = sorted(
        {
            *commit_dir.glob("*_agent_commit.csv"),
            *commit_dir.glob("*_agent_commit_qc.csv"),
        },
        key=lambda path: path.name,
    )
    for csv_path in csv_paths:
        with csv_path.open("r", encoding="utf-8", newline="") as fh:
            rows.extend(dict(row) for row in csv.DictReader(fh))
    return rows


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
    pattern = "*_agent_test_commit_qc.csv" if role == "agent" else "*_human_test_commit_qc.csv"
    suffix = "_agent_test_commit_qc.csv" if role == "agent" else "_human_test_commit_qc.csv"
    checkpoint_name = AGENT_TEST_COMMITS_CHECKPOINT if role == "agent" else HUMAN_TEST_COMMITS_CHECKPOINT

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
    checkpoint_name = AGENT_TEST_COMMITS_CHECKPOINT if role == "agent" else HUMAN_TEST_COMMITS_CHECKPOINT
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


def _save_agent_test_commit_resume_state(output_dir: Path, counts: dict[str, int], completed_repos: set[str]):
    return _save_test_commit_resume_state(output_dir, counts, completed_repos, role="agent")


def _load_pre2021_raw_repo_rows(raw_search_dir: Path, language: str | None = None) -> list[dict]:
    """Load pre-2021 repository search rows from github-search-raw CSV.gz files."""
    cutoff_date = HUMAN_CORPUS_CUTOFF_DATE
    language_filter = (language or "").strip().lower() or None
    repo_rows: list[dict] = []

    for csv_path in sorted(Path(raw_search_dir).glob("*.csv.gz"), key=lambda p: p.name):
        try:
            with gzip.open(csv_path, "rt", encoding="utf-8", newline="") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    repo_name = (row.get("name") or row.get("full_name") or "").strip()
                    lang = (row.get("mainLanguage") or row.get("language") or "").strip().lower()
                    created_at = (row.get("createdAt") or row.get("created_at") or "").strip()
                    is_fork = str(row.get("isFork") or row.get("fork") or "").strip().lower()
                    if not repo_name or "/" not in repo_name:
                        continue
                    if language_filter and lang != language_filter:
                        continue
                    if lang and lang not in LANGUAGE_CONFIGS:
                        continue
                    if is_fork in {"1", "true", "yes"}:
                        continue
                    if created_at and created_at[:10] > cutoff_date:
                        continue
                    repo_rows.append(
                        {
                            "repo_name": repo_name,
                            "full_name": repo_name,
                            "language": lang or language_filter or "unknown",
                            "clone_url": (row.get("clone_url") or f"https://github.com/{repo_name}.git").strip(),
                            "created_at": created_at,
                        }
                    )
        except Exception as exc:
            logger.debug("Failed to read raw search CSV %s: %s", csv_path, exc)

    return repo_rows


def _collect_human_test_commits_from_repo_rows(
    repo_rows: list[dict],
    output_dir: Path,
    clones_dir: Path = CLONES_DIR,
    workers: int = 12,
) -> dict:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in repo_rows:
        repo_name = (row.get("repo_name") or row.get("full_name") or "").strip()
        if repo_name:
            grouped[repo_name].append(row)
    test_commit_rows_by_language: dict[str, list[dict]] = defaultdict(list)
    (
        existing_rows_by_lang,
        seen_commit_shas_by_language,
        completed_repos,
        counts,
    ) = _load_test_commit_resume_state(Path(output_dir), role="human")

    repos_processed = counts.get("repos_processed", 0)
    commits_scanned = counts.get("commits_scanned", 0)
    repos_with_test_commits = counts.get("repos_with_test_commits", 0)
    workers = max(1, int(workers or 1))

    # Filter out repos already completed in checkpoint
    repos_to_process = {
        repo_name: repo_rows_for_name
        for repo_name, repo_rows_for_name in grouped.items()
        if repo_name not in completed_repos
    }

    total_repos = len(repos_to_process)

    logger.info(
        "[human-test-commits] Loaded %d repo rows across %d repos (to process=%d)",
        sum(len(v) for v in grouped.values()),
        len(grouped),
        total_repos,
    )
    if completed_repos:
        logger.info(
            "[human-test-commits] Resuming from checkpoint: %d repos already completed, %d repo(s) skipped",
            len(completed_repos),
            len(grouped) - len(repos_to_process),
        )
    logger.info("[human-test-commits] Filtering with %d worker(s)", workers)

    def persist_progress() -> None:
        counts.update(
            {
                "repos_processed": repos_processed,
                "commits_scanned": commits_scanned,
                "repos_with_test_commits": repos_with_test_commits,
                "test_commits_found": sum(
                    len(language_rows) for language_rows in test_commit_rows_by_language.values()
                ),
            }
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        for language, language_rows in sorted(test_commit_rows_by_language.items()):
            write_test_commits_csv(language_rows, output_dir / f"{language}_human_test_commit_qc.csv")
        _save_test_commit_resume_state(output_dir, counts, completed_repos, role="human")

    if workers == 1:
        for repo_name, repo_rows_for_name in repos_to_process.items():
            language, repo_test_commits, repo_count, repo_commits_scanned = _process_repo_human_test_commits(repo_rows_for_name[0])
            repos_processed += repo_count
            commits_scanned += repo_commits_scanned
            new_rows = []
            lang_seen = seen_commit_shas_by_language.setdefault(language, set())
            for row in repo_test_commits:
                commit_sha = (row.get("commit_sha") or "").strip()
                if commit_sha and commit_sha not in lang_seen:
                    lang_seen.add(commit_sha)
                    new_rows.append(row)
            if new_rows:
                repos_with_test_commits += 1
                test_commit_rows_by_language[language].extend(new_rows)
            completed_repos.add(repo_name)
            persist_progress()
            pct = (repos_processed / total_repos * 100) if total_repos else 100
            logger.info(
                "[human-test-commits] Progress: %d/%d repos (%.1f%%), %d commits scanned, %d repos completed",
                repos_processed,
                total_repos,
                pct,
                commits_scanned,
                len(completed_repos),
            )
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(_process_repo_human_test_commits, repo_rows_for_name[0]): repo_name
                for repo_name, repo_rows_for_name in repos_to_process.items()
            }
            try:
                for future in as_completed(futures):
                    language, repo_test_commits, repo_count, repo_commits_scanned = future.result()
                    repos_processed += repo_count
                    commits_scanned += repo_commits_scanned
                    new_rows = []
                    lang_seen = seen_commit_shas_by_language.setdefault(language, set())
                    for row in repo_test_commits:
                        commit_sha = (row.get("commit_sha") or "").strip()
                        if commit_sha and commit_sha not in lang_seen:
                            lang_seen.add(commit_sha)
                            new_rows.append(row)
                    if new_rows:
                        repos_with_test_commits += 1
                        test_commit_rows_by_language[language].extend(new_rows)
                    repo_name = futures.get(future, None)
                    if repo_name:
                        completed_repos.add(repo_name)
                    persist_progress()
                    pct = (repos_processed / total_repos * 100) if total_repos else 100
                    logger.info(
                        "[human-test-commits] Progress: %d/%d repos completed (%.1f%%), %d commits scanned, %d repos completed",
                        repos_processed,
                        total_repos,
                        pct,
                        commits_scanned,
                        len(completed_repos),
                    )
            except KeyboardInterrupt:
                logger.warning("[human-test-commits] Interrupted by user (KeyboardInterrupt). Cancelling remaining jobs...")
                for fut in futures:
                    fut.cancel()
                persist_progress()
                raise

    output_files: dict[str, str] = {}
    total_test_commits = 0
    for language, language_rows in sorted(test_commit_rows_by_language.items()):
        output_path = output_dir / f"{language}_human_test_commit_qc.csv"
        write_test_commits_csv(language_rows, output_path)
        output_files[language] = str(output_path)
        total_test_commits += len(language_rows)

    logger.info(
        "[human-test-commits] Finished: %d repos processed, %d commits scanned, %d human test commits found",
        repos_processed,
        commits_scanned,
        total_test_commits,
    )
    counts.update(
        {
            "repos_processed": repos_processed,
            "commits_scanned": commits_scanned,
            "repos_with_test_commits": repos_with_test_commits,
            "test_commits_found": total_test_commits,
        }
    )
    _save_test_commit_resume_state(output_dir, counts, completed_repos, role="human")
    return {
        "repos_processed": repos_processed,
        "commits_scanned": commits_scanned,
        "repos_with_test_commits": repos_with_test_commits,
        "test_commits_found": total_test_commits,
        "output_files": output_files,
        "output_dir": str(output_dir),
    }


def _process_repo_test_commits(repo_name: str, repo_rows: list[dict]) -> tuple[str, list[dict], int, int]:
    clone_url = (repo_rows[0].get("clone_url") or f"https://github.com/{repo_name}.git").strip()
    language = (repo_rows[0].get("language") or "unknown").strip().lower()

    logger.info("[test-commits] Cloning %s (%s)", repo_name, language)
    with temp_clone_commit_history(
        clone_url, repo_name, prefix="agent-test-commits-", timeout=300
    ) as repo_path:
        if repo_path is None:
            logger.warning("Failed to clone %s while filtering test commits", repo_name)
            return language, [], 1, 0

        test_commit_rows: list[dict] = []
        commits_scanned = 0
        for row in repo_rows:
            commit_sha = (row.get("commit_sha") or "").strip()
            if not commit_sha:
                continue
            commits_scanned += 1
            test_files = collect_test_files_for_commit(repo_path, commit_sha, language)
            if not test_files:
                continue
            test_commit_rows.append(
                {
                    "repo_name": repo_name,
                    "language": language,
                    "commit_sha": commit_sha,
                    "commit_role": "agent",
                    "agent_type": (row.get("agent_type") or "unknown").strip().lower(),
                    "commit_date": row.get("commit_date") or "",
                    "test_file_count": len(test_files),
                    "test_file_paths": json.dumps(test_files, ensure_ascii=False),
                }
            )

    logger.info(
        "[test-commits] %s (%s): scanned %d commits, found %d test commits",
        repo_name,
        language,
        commits_scanned,
        len(test_commit_rows),
    )
    return language, test_commit_rows, 1, commits_scanned


def collect_agent_test_commits(
    commit_qc_dir: Path,
    output_dir: Path,
    clones_dir: Path = CLONES_DIR,
    workers: int = 12,
) -> dict:
    """Filter an agent commit dataset to commits that touch test files."""
    rows = _load_agent_commit_rows(commit_qc_dir)
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        repo_name = (row.get("repo_name") or "").strip()
        if repo_name:
            grouped[repo_name].append(row)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (
        test_commit_rows_by_language,
        seen_commit_shas_by_language,
        completed_repos,
        counts,
    ) = _load_agent_test_commit_resume_state(output_dir)

    repos_processed = counts["repos_processed"]
    commits_scanned = counts["commits_scanned"]
    repos_with_test_commits = counts["repos_with_test_commits"]
    total_repos = len(grouped)
    workers = max(1, int(workers or 1))
    repos_to_process = {
        repo_name: repo_rows
        for repo_name, repo_rows in grouped.items()
        if repo_name not in completed_repos
    }
    skipped_repos = len(grouped) - len(repos_to_process)

    logger.info(
        "[test-commits] Loaded %d commit rows across %d repos from %s",
        len(rows),
        len(grouped),
        commit_qc_dir,
    )
    if completed_repos:
        logger.info(
            "[test-commits] Resuming from checkpoint: %d repos already completed, %d repo(s) skipped",
            len(completed_repos),
            skipped_repos,
        )
    logger.info("[test-commits] Filtering with %d worker(s)", workers)

    def persist_progress() -> None:
        counts.update(
            {
                "repos_processed": repos_processed,
                "commits_scanned": commits_scanned,
                "repos_with_test_commits": repos_with_test_commits,
                "test_commits_found": sum(len(language_rows) for language_rows in test_commit_rows_by_language.values()),
            }
        )
        for language, language_rows in sorted(test_commit_rows_by_language.items()):
            write_test_commits_csv(language_rows, output_dir / f"{language}_agent_test_commit_qc.csv")
        _save_agent_test_commit_resume_state(output_dir, counts, completed_repos)

    if workers == 1:
        for repo_name, repo_rows in repos_to_process.items():
            language, repo_test_commits, repo_count, repo_commits_scanned = _process_repo_test_commits(repo_name, repo_rows)
            repos_processed += repo_count
            commits_scanned += repo_commits_scanned
            new_rows = []
            lang_seen = seen_commit_shas_by_language.setdefault(language, set())
            for row in repo_test_commits:
                commit_sha = (row.get("commit_sha") or "").strip()
                if commit_sha and commit_sha not in lang_seen:
                    lang_seen.add(commit_sha)
                    new_rows.append(row)
            if new_rows:
                repos_with_test_commits += 1
                test_commit_rows_by_language[language].extend(new_rows)
            completed_repos.add(repo_name)
            persist_progress()
            pct = (repos_processed / total_repos * 100) if total_repos else 100
            logger.info(
                "[test-commits] Progress: %d/%d repos (%.1f%%), %d commits scanned, %d repos completed",
                repos_processed,
                total_repos,
                pct,
                commits_scanned,
                len(completed_repos),
            )
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_process_repo_test_commits, repo_name, repo_rows): repo_name for repo_name, repo_rows in repos_to_process.items()}
            try:
                for future in as_completed(futures):
                    repo_name = futures[future]
                    language, repo_test_commits, repo_count, repo_commits_scanned = future.result()
                    repos_processed += repo_count
                    commits_scanned += repo_commits_scanned
                    new_rows = []
                    lang_seen = seen_commit_shas_by_language.setdefault(language, set())
                    for row in repo_test_commits:
                        commit_sha = (row.get("commit_sha") or "").strip()
                        if commit_sha and commit_sha not in lang_seen:
                            lang_seen.add(commit_sha)
                            new_rows.append(row)
                    if new_rows:
                        repos_with_test_commits += 1
                        test_commit_rows_by_language[language].extend(new_rows)
                    completed_repos.add(repo_name)
                    persist_progress()
                    pct = (repos_processed / total_repos * 100) if total_repos else 100
                    logger.info(
                        "[test-commits] Progress: %d/%d repos completed (%.1f%%), %d commits scanned, %d repos completed",
                        repos_processed,
                        total_repos,
                        pct,
                        commits_scanned,
                        len(completed_repos),
                    )
            except KeyboardInterrupt:
                logger.warning("[test-commits] Interrupted by user (KeyboardInterrupt). Cancelling remaining jobs...")
                for fut in futures:
                    fut.cancel()
                persist_progress()
                raise

    output_files: dict[str, str] = {}
    total_test_commits = 0
    for language, language_rows in sorted(test_commit_rows_by_language.items()):
        output_path = output_dir / f"{language}_agent_test_commit_qc.csv"
        output_files[language] = str(output_path)
        total_test_commits += len(language_rows)
        logger.info("[test-commits] Wrote %d agent test commits for %s to %s", len(language_rows), language, output_path)

    logger.info(
        "[test-commits] Finished: %d repos processed, %d commits scanned, %d agent test commits found",
        repos_processed,
        commits_scanned,
        total_test_commits,
    )
    return {
        "repos_processed": repos_processed,
        "commits_scanned": commits_scanned,
        "repos_with_test_commits": repos_with_test_commits,
        "test_commits_found": total_test_commits,
        "output_files": output_files,
        "output_dir": str(output_dir),
    }


def _process_repo_human_test_commits(repo_row: dict) -> tuple[str, list[dict], int, int]:
    repo_name = (repo_row.get("repo_name") or repo_row.get("full_name") or "").strip()
    clone_url = (repo_row.get("clone_url") or f"https://github.com/{repo_name}.git").strip()
    language = (repo_row.get("language") or "unknown").strip().lower()

    logger.info("[human-test-commits] Cloning %s (%s)", repo_name, language)
    with temp_clone_commit_history(clone_url, repo_name, prefix="human-test-commits-", timeout=300) as repo_path:
        if repo_path is None:
            logger.warning("Failed to clone %s while filtering human test commits", repo_name)
            return language, [], 1, 0

        test_commit_rows: list[dict] = []
        commits_scanned = 0
        project_root = Path(__file__).resolve().parents[1]
        scanner = Tier1RepositoryScanner(project_root / "data" / "corpus.db")
        commit_roles = scanner.scan_repo_commit_roles(
            repo_path,
            start_date=HUMAN_CORPUS_CUTOFF_DATE,
            language=language,
            detect_test_files=True,
        )
        for commit in commit_roles:
            commits_scanned += 1
            if commit.commit_role != "human" or not commit.is_test_commit:
                continue
            test_commit_rows.append(
                {
                    "repo_name": repo_name,
                    "language": language,
                    "commit_sha": commit.commit_sha,
                    "commit_role": "human",
                    "agent_type": commit.agent_type,
                    "commit_date": commit.commit_date,
                    "test_file_count": len(commit.test_files),
                    "test_file_paths": json.dumps(commit.test_files, ensure_ascii=False),
                }
            )

    logger.info(
        "[human-test-commits] %s (%s): scanned %d commits, found %d human test commits",
        repo_name,
        language,
        commits_scanned,
        len(test_commit_rows),
    )
    return language, test_commit_rows, 1, commits_scanned


def collect_human_test_commits(
    repo_qc_dir: Path,
    output_dir: Path,
    clones_dir: Path = CLONES_DIR,
    workers: int = 12,
    language: str | None = None,
) -> dict:
    """Filter agent-config repositories to human-authored commits that touch test files.

    Args:
        language: Optional language filter (e.g. 'python')
    """
    grouped: dict[str, list[dict]] = defaultdict(list)
    language_filter = (language or "").strip().lower() or None
    for csv_path in sorted(Path(repo_qc_dir).glob("*_agent_repo.csv"), key=lambda path: path.name):
        with csv_path.open("r", encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                if str(row.get("has_agent_config") or "").strip().lower() not in {"1", "true"}:
                    continue
                row_lang = (row.get("language") or "").strip().lower() or None
                if language_filter and row_lang and row_lang != language_filter:
                    continue
                repo_name = (row.get("repo_name") or row.get("full_name") or "").strip()
                if repo_name:
                    grouped[repo_name].append(row)

    repo_rows = [rows[0] for rows in grouped.values()]
    logger.info(
        "[human-test-commits] Loaded %d repo rows across %d repos from %s",
        sum(len(v) for v in grouped.values()),
        len(grouped),
        repo_qc_dir,
    )
    return _collect_human_test_commits_from_repo_rows(
        repo_rows, Path(output_dir), clones_dir=clones_dir, workers=workers
    )


def collect_human_test_commits_from_raw_search(
    raw_search_dir: Path,
    output_dir: Path,
    clones_dir: Path = CLONES_DIR,
    workers: int = 12,
    language: str | None = None,
) -> dict:
    """Filter github-search-raw repository search results to pre-2021 human test commits."""
    repo_rows = _load_pre2021_raw_repo_rows(raw_search_dir, language=language)
    logger.info(
        "[human-test-commits] Loaded %d pre-2021 repositories from raw search results in %s",
        len(repo_rows),
        raw_search_dir,
    )
    return _collect_human_test_commits_from_repo_rows(repo_rows, Path(output_dir), clones_dir=clones_dir, workers=workers)


def _process_repo_agent_test_commits(repo_row: dict) -> tuple[str, list[dict], int, int]:
    repo_name = (repo_row.get("repo_name") or repo_row.get("full_name") or "").strip()
    clone_url = (repo_row.get("clone_url") or f"https://github.com/{repo_name}.git").strip()
    language = (repo_row.get("language") or "unknown").strip().lower()

    logger.info("[agent-test-commits] Cloning %s (%s)", repo_name, language)
    with temp_clone_commit_history(clone_url, repo_name, prefix="agent-test-commits-", timeout=300) as repo_path:
        if repo_path is None:
            logger.warning("Failed to clone %s while filtering agent test commits", repo_name)
            return language, [], 1, 0

        test_commit_rows: list[dict] = []
        commits_scanned = 0
        project_root = Path(__file__).resolve().parents[1]
        scanner = Tier1RepositoryScanner(project_root / "data" / "corpus.db")
        commit_roles = scanner.scan_repo_commit_roles(
            repo_path,
            start_date=AGENT_CORPUS_START_DATE,
            language=language,
            detect_test_files=True,
        )
        for commit in commit_roles:
            commits_scanned += 1
            if commit.commit_role != "agent" or not commit.is_test_commit:
                continue
            test_commit_rows.append(
                {
                    "repo_name": repo_name,
                    "language": language,
                    "commit_sha": commit.commit_sha,
                    "commit_role": "agent",
                    "agent_type": commit.agent_type,
                    "commit_date": commit.commit_date,
                    "test_file_count": len(commit.test_files),
                    "test_file_paths": json.dumps(commit.test_files, ensure_ascii=False),
                }
            )

    logger.info(
        "[agent-test-commits] %s (%s): scanned %d commits, found %d agent test commits",
        repo_name,
        language,
        commits_scanned,
        len(test_commit_rows),
    )
    return language, test_commit_rows, 1, commits_scanned


def collect_agent_test_commits_from_repos(
    repo_qc_dir: Path,
    output_dir: Path,
    clones_dir: Path = CLONES_DIR,
    workers: int = 12,
) -> dict:
    """Filter agent-config repositories to agent-authored commits that touch test files."""
    grouped: dict[str, list[dict]] = defaultdict(list)
    for csv_path in sorted(Path(repo_qc_dir).glob("*_agent_repo.csv"), key=lambda path: path.name):
        with csv_path.open("r", encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                if str(row.get("has_agent_config") or "").strip().lower() not in {"1", "true"}:
                    continue
                repo_name = (row.get("repo_name") or row.get("full_name") or "").strip()
                if repo_name:
                    grouped[repo_name].append(row)

    test_commit_rows_by_language: dict[str, list[dict]] = defaultdict(list)
    repos_processed = 0
    commits_scanned = 0
    repos_with_test_commits = 0
    workers = max(1, int(workers or 1))
    total_repos = len(grouped)

    logger.info(
        "[agent-test-commits] Loaded %d repo rows across %d repos from %s",
        sum(len(v) for v in grouped.values()),
        total_repos,
        repo_qc_dir,
    )

    if workers == 1:
        for repo_name, repo_rows in grouped.items():
            language, repo_test_commits, repo_count, repo_commits_scanned = _process_repo_agent_test_commits(repo_rows[0])
            repos_processed += repo_count
            commits_scanned += repo_commits_scanned
            if repo_test_commits:
                repos_with_test_commits += 1
                test_commit_rows_by_language[language].extend(repo_test_commits)
            pct = (repos_processed / total_repos * 100) if total_repos else 100
            logger.info("[agent-test-commits] Progress: %d/%d repos (%.1f%%), %d commits scanned", repos_processed, total_repos, pct, commits_scanned)
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_process_repo_agent_test_commits, repo_rows[0]): repo_name for repo_name, repo_rows in grouped.items()}
            try:
                for future in as_completed(futures):
                    language, repo_test_commits, repo_count, repo_commits_scanned = future.result()
                    repos_processed += repo_count
                    commits_scanned += repo_commits_scanned
                    if repo_test_commits:
                        repos_with_test_commits += 1
                        test_commit_rows_by_language[language].extend(repo_test_commits)
                    pct = (repos_processed / total_repos * 100) if total_repos else 100
                    logger.info("[agent-test-commits] Progress: %d/%d repos completed (%.1f%%), %d commits scanned", repos_processed, total_repos, pct, commits_scanned)
            except KeyboardInterrupt:
                logger.warning("[agent-test-commits] Interrupted by user (KeyboardInterrupt). Cancelling remaining jobs...")
                for fut in futures:
                    fut.cancel()
                raise

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_files: dict[str, str] = {}
    total_test_commits = 0
    for language, language_rows in sorted(test_commit_rows_by_language.items()):
        output_path = output_dir / f"{language}_agent_test_commit_qc.csv"
        write_test_commits_csv(language_rows, output_path)
        output_files[language] = str(output_path)
        total_test_commits += len(language_rows)

    logger.info(
        "[agent-test-commits] Finished: %d repos processed, %d commits scanned, %d agent test commits found",
        repos_processed,
        commits_scanned,
        total_test_commits,
    )
    return {
        "repos_processed": repos_processed,
        "commits_scanned": commits_scanned,
        "repos_with_test_commits": repos_with_test_commits,
        "test_commits_found": total_test_commits,
        "output_files": output_files,
        "output_dir": str(output_dir),
    }


def build_pre2021_candidate_pool(raw_commits_dir: Path, cutoff_date: str = HUMAN_CORPUS_CUTOFF_DATE) -> dict:
    candidates: dict[str, list[dict]] = defaultdict(list)
    for csv_path in sorted(Path(raw_commits_dir).glob("**/*_commit*.csv"), key=lambda p: p.name):
        try:
            with csv_path.open("r", encoding="utf-8", newline="") as fh:
                for row in csv.DictReader(fh):
                    repo_name = (row.get("repo_name") or row.get("full_name") or "").strip()
                    commit_date = (row.get("commit_date") or "").strip()
                    if repo_name and commit_date and commit_date <= cutoff_date:
                        candidates[repo_name].append(dict(row))
        except Exception:
            logger.debug("Failed to read raw commits CSV: %s", csv_path)
    return candidates


def _cli_main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Filter agent datasets to test commits (agent or human)")
    parser.add_argument("--mode", choices=["agent", "human"], default="agent")
    parser.add_argument("--commit-dir", dest="commit_qc_dir", type=Path, default=Path("github-search-agent") / "agent_commits", help="Directory containing *_agent_commit.csv files")
    parser.add_argument("--repo-dir", dest="repo_qc_dir", type=Path, default=Path("github-search-agent") / "agent_repositories")
    parser.add_argument("--raw-search-dir", dest="raw_search_dir", type=Path, default=None, help="Directory containing github-search-raw *.csv.gz repository search files")
    parser.add_argument("--output-dir", type=Path, default=Path("output/test-commits"))
    parser.add_argument("--language", type=str, default=None, help="Limit to one language (e.g. python)")
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()

    repo_qc_files = list(Path(args.repo_qc_dir).glob("*_agent_repo.csv")) if Path(args.repo_qc_dir).exists() else []
    if args.mode == "agent":
        if repo_qc_files:
            collect_agent_test_commits_from_repos(args.repo_qc_dir, args.output_dir, workers=args.workers)
        else:
            collect_agent_test_commits(args.commit_qc_dir, args.output_dir, workers=args.workers)
    else:
        if args.raw_search_dir:
            collect_human_test_commits_from_raw_search(
                args.raw_search_dir, args.output_dir, workers=args.workers, language=args.language
            )
        else:
            collect_human_test_commits(
                args.repo_qc_dir, args.output_dir, workers=args.workers, language=args.language
            )


if __name__ == "__main__":
    _cli_main()