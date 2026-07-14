"""Filtering agent commit datasets down to test commits (Dataset A).

Human-side filtering (Dataset B/C) lives in human_test_commit_filter.py;
checkpoint/resume state shared by both lives in test_commit_resume_state.py.
Entry point: `python -m collection filter-test-commits --dataset a`.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from tqdm import tqdm

from collection.logging_utils import get_logger

from . import paths
from .config import AGENT_CORPUS_START_DATE, CLONES_DIR, HUMAN_CORPUS_CUTOFF_DATE
from .ephemeral_clone import temp_clone_commit_history
from .test_commit_resume_state import (
    _load_agent_test_commit_resume_state,
    _save_agent_test_commit_resume_state,
)
from .test_commit_utils import collect_test_files_for_commit, write_test_commits_csv
from .tiered_agent_corpus_scanner import Tier1RepositoryScanner

logger = get_logger(__name__)


def _load_agent_commit_rows(commit_qc_dir: Path) -> list[dict]:
    rows: list[dict] = []
    commit_dir = Path(commit_qc_dir)
    csv_paths = sorted(commit_dir.glob("*_commit.csv"), key=lambda path: path.name)
    for csv_path in csv_paths:
        with csv_path.open("r", encoding="utf-8", newline="") as fh:
            rows.extend(dict(row) for row in csv.DictReader(fh))
    return rows


def _process_repo_test_commits(
    repo_name: str, repo_rows: list[dict]
) -> tuple[str, list[dict], int, int]:
    clone_url = (
        repo_rows[0].get("clone_url") or f"https://github.com/{repo_name}.git"
    ).strip()
    language = (repo_rows[0].get("language") or "unknown").strip().lower()

    logger.debug("[test-commits] Cloning %s (%s)", repo_name, language)
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

    logger.debug(
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
                "test_commits_found": sum(
                    len(language_rows)
                    for language_rows in test_commit_rows_by_language.values()
                ),
            }
        )
        for language, language_rows in sorted(test_commit_rows_by_language.items()):
            write_test_commits_csv(
                language_rows, output_dir / f"{language}_test_commit.csv"
            )
        _save_agent_test_commit_resume_state(output_dir, counts, completed_repos)

    if workers == 1:
        with tqdm(total=total_repos, desc="[test-commits]", unit="repo") as pbar:
            for repo_name, repo_rows in repos_to_process.items():
                language, repo_test_commits, repo_count, repo_commits_scanned = (
                    _process_repo_test_commits(repo_name, repo_rows)
                )
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
                pbar.set_postfix(commits=commits_scanned, test_commits=sum(
                    len(v) for v in test_commit_rows_by_language.values()
                ))
                pbar.update(1)
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    _process_repo_test_commits, repo_name, repo_rows
                ): repo_name
                for repo_name, repo_rows in repos_to_process.items()
            }
            try:
                with tqdm(total=total_repos, desc="[test-commits]", unit="repo") as pbar:
                    for future in as_completed(futures):
                        repo_name = futures[future]
                        language, repo_test_commits, repo_count, repo_commits_scanned = (
                            future.result()
                        )
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
                        pbar.set_postfix(commits=commits_scanned, test_commits=sum(
                            len(v) for v in test_commit_rows_by_language.values()
                        ))
                        pbar.update(1)
            except KeyboardInterrupt:
                logger.warning(
                    "[test-commits] Interrupted by user (KeyboardInterrupt). Cancelling remaining jobs..."
                )
                for fut in futures:
                    fut.cancel()
                persist_progress()
                raise

    output_files: dict[str, str] = {}
    total_test_commits = 0
    for language, language_rows in sorted(test_commit_rows_by_language.items()):
        output_path = output_dir / f"{language}_test_commit.csv"
        output_files[language] = str(output_path)
        total_test_commits += len(language_rows)
        logger.info(
            "[test-commits] Wrote %d agent test commits for %s to %s",
            len(language_rows),
            language,
            output_path,
        )

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


def _process_repo_agent_test_commits(
    repo_row: dict,
) -> tuple[str, list[dict], int, int]:
    repo_name = (repo_row.get("repo_name") or repo_row.get("full_name") or "").strip()
    clone_url = (
        repo_row.get("clone_url") or f"https://github.com/{repo_name}.git"
    ).strip()
    language = (repo_row.get("language") or "unknown").strip().lower()

    logger.debug("[agent-test-commits] Cloning %s (%s)", repo_name, language)
    with temp_clone_commit_history(
        clone_url, repo_name, prefix="agent-test-commits-", timeout=300
    ) as repo_path:
        if repo_path is None:
            logger.warning(
                "Failed to clone %s while filtering agent test commits", repo_name
            )
            return language, [], 1, 0

        test_commit_rows: list[dict] = []
        commits_scanned = 0
        scanner = Tier1RepositoryScanner(paths.corpus_db_path())
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
                    "test_file_paths": json.dumps(
                        commit.test_files, ensure_ascii=False
                    ),
                }
            )

    logger.debug(
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
    for csv_path in sorted(
        Path(repo_qc_dir).glob("*_repo.csv"), key=lambda path: path.name
    ):
        with csv_path.open("r", encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                if str(row.get("has_agent_config") or "").strip().lower() not in {
                    "1",
                    "true",
                }:
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
        with tqdm(total=total_repos, desc="[agent-test-commits]", unit="repo") as pbar:
            for _repo_name, repo_rows in grouped.items():
                language, repo_test_commits, repo_count, repo_commits_scanned = (
                    _process_repo_agent_test_commits(repo_rows[0])
                )
                repos_processed += repo_count
                commits_scanned += repo_commits_scanned
                if repo_test_commits:
                    repos_with_test_commits += 1
                    test_commit_rows_by_language[language].extend(repo_test_commits)
                pbar.set_postfix(commits=commits_scanned, test_commits=sum(
                    len(v) for v in test_commit_rows_by_language.values()
                ))
                pbar.update(1)
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    _process_repo_agent_test_commits, repo_rows[0]
                ): repo_name
                for repo_name, repo_rows in grouped.items()
            }
            try:
                with tqdm(total=total_repos, desc="[agent-test-commits]", unit="repo") as pbar:
                    for future in as_completed(futures):
                        language, repo_test_commits, repo_count, repo_commits_scanned = (
                            future.result()
                        )
                        repos_processed += repo_count
                        commits_scanned += repo_commits_scanned
                        if repo_test_commits:
                            repos_with_test_commits += 1
                            test_commit_rows_by_language[language].extend(repo_test_commits)
                        pbar.set_postfix(commits=commits_scanned, test_commits=sum(
                            len(v) for v in test_commit_rows_by_language.values()
                        ))
                        pbar.update(1)
            except KeyboardInterrupt:
                logger.warning(
                    "[agent-test-commits] Interrupted by user (KeyboardInterrupt). Cancelling remaining jobs..."
                )
                for fut in futures:
                    fut.cancel()
                raise

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_files: dict[str, str] = {}
    total_test_commits = 0
    for language, language_rows in sorted(test_commit_rows_by_language.items()):
        output_path = output_dir / f"{language}_test_commit.csv"
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


def build_pre2021_candidate_pool(
    raw_commits_dir: Path, cutoff_date: str = HUMAN_CORPUS_CUTOFF_DATE
) -> dict:
    """Group pre-cutoff test commits by repo, from `*_commit*.csv` files."""
    candidates: dict[str, list[dict]] = defaultdict(list)
    for csv_path in sorted(
        Path(raw_commits_dir).glob("**/*_commit*.csv"), key=lambda p: p.name
    ):
        try:
            with csv_path.open("r", encoding="utf-8", newline="") as fh:
                for row in csv.DictReader(fh):
                    repo_name = (
                        row.get("repo_name") or row.get("full_name") or ""
                    ).strip()
                    commit_date = (row.get("commit_date") or "").strip()
                    if repo_name and commit_date and commit_date <= cutoff_date:
                        candidates[repo_name].append(dict(row))
        except Exception:
            logger.debug("Failed to read raw commits CSV: %s", csv_path)
    return candidates
