"""Standalone filtering of agent commit datasets down to test commits."""

from __future__ import annotations

import csv
import json
import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .agent_corpus import collect_test_files_for_commit
from .agent_commit_detector import Tier1RepositoryScanner
from .config import HUMAN_CORPUS_CUTOFF_DATE, AGENT_CORPUS_START_DATE
import argparse
from pathlib import Path
from .config import CLONES_DIR
from .clone_manager import temp_clone_commit_history
from .test_commit_utils import write_test_commits_csv

logger = logging.getLogger(__name__)


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
            reader = csv.DictReader(fh)
            rows.extend(dict(row) for row in reader)
    return rows


def _process_repo_test_commits(
    repo_name: str, repo_rows: list[dict]
) -> tuple[str, list[dict], int, int]:
    clone_url = (
        repo_rows[0].get("clone_url") or f"https://github.com/{repo_name}.git"
    ).strip()
    language = (repo_rows[0].get("language") or "unknown").strip().lower()

    logger.info("[test-commits] Cloning %s (%s)", repo_name, language)

    with temp_clone_commit_history(clone_url, repo_name, prefix="agent-test-commits-", timeout=300) as repo_path:
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

    test_commit_rows_by_language: dict[str, list[dict]] = defaultdict(list)
    repos_processed = 0
    commits_scanned = 0
    repos_with_test_commits = 0
    total_repos = len(grouped)
    workers = max(1, int(workers or 1))

    logger.info(
        "[test-commits] Loaded %d commit rows across %d repos from %s",
        len(rows),
        len(grouped),
        commit_qc_dir,
    )
    logger.info("[test-commits] Filtering with %d worker(s)", workers)

    if workers == 1:
        for repo_name, repo_rows in grouped.items():
            language, repo_test_commits, repo_count, repo_commits_scanned = (
                _process_repo_test_commits(repo_name, repo_rows)
            )
            repos_processed += repo_count
            commits_scanned += repo_commits_scanned
            if repo_test_commits:
                repos_with_test_commits += 1
                test_commit_rows_by_language[language].extend(repo_test_commits)
            pct = (repos_processed / total_repos * 100) if total_repos else 100
            logger.info(
                "[test-commits] Progress: %d/%d repos (%.1f%%), %d commits scanned",
                repos_processed,
                total_repos,
                pct,
                commits_scanned,
            )
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    _process_repo_test_commits, repo_name, repo_rows
                ): repo_name
                for repo_name, repo_rows in grouped.items()
            }
            completed = 0
            try:
                for future in as_completed(futures):
                    language, repo_test_commits, repo_count, repo_commits_scanned = (
                        future.result()
                    )
                    repos_processed += repo_count
                    commits_scanned += repo_commits_scanned
                    if repo_test_commits:
                        repos_with_test_commits += 1
                        test_commit_rows_by_language[language].extend(repo_test_commits)
                    completed += 1
                    pct = (completed / total_repos * 100) if total_repos else 100
                    logger.info(
                        "[test-commits] Progress: %d/%d repos completed (%.1f%%), %d commits scanned",
                        completed,
                        total_repos,
                        pct,
                        commits_scanned,
                    )
            except KeyboardInterrupt:
                logger.warning(
                    "[test-commits] Interrupted by user (KeyboardInterrupt). Cancelling remaining jobs..."
                )
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
            "[test-commits] Wrote %d test commits for %s to %s",
            len(language_rows),
            language,
            output_path,
        )

    logger.info(
        "[test-commits] Finished: %d repos processed, %d commits scanned, %d test commits found",
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


def _process_repo_human_test_commits(
    repo_row: dict,
) -> tuple[str, list[dict], int, int]:
    """Process a single repo row (from repo-QC CSV) and return human test-commit rows."""
    repo_name = (repo_row.get("repo_name") or repo_row.get("full_name") or "").strip()
    clone_url = (
        repo_row.get("clone_url") or f"https://github.com/{repo_name}.git"
    ).strip()
    language = (repo_row.get("language") or "unknown").strip().lower()

    logger.info("[human-test-commits] Cloning %s (%s)", repo_name, language)

    with temp_clone_commit_history(clone_url, repo_name, prefix="human-test-commits-", timeout=300) as repo_path:
        if repo_path is None:
            logger.warning(
                "Failed to clone %s while filtering human test commits", repo_name
            )
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
            if commit.commit_role != "human":
                continue
            if not commit.is_test_commit:
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
                    "test_file_paths": json.dumps(
                        commit.test_files, ensure_ascii=False
                    ),
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
) -> dict:
    """Filter agent-config repositories to human-authored commits that touch test files.

    This produces per-language CSV files named like `<lang>_human_test_commit_qc.csv`.
    """
    grouped: dict[str, list[dict]] = defaultdict(list)

    csv_paths = sorted(
        Path(repo_qc_dir).glob("*_agent_repo.csv"), key=lambda path: path.name
    )
    for csv_path in csv_paths:
        with csv_path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                if str(row.get("has_agent_config") or "").strip().lower() not in {
                    "1",
                    "true",
                }:
                    continue
                repo_name = (row.get("repo_name") or row.get("full_name") or "").strip()
                if repo_name:
                    grouped[repo_name].append(row)
    total_repos = len(grouped)

    test_commit_rows_by_language: dict[str, list[dict]] = defaultdict(list)
    repos_processed = 0
    commits_scanned = 0
    repos_with_test_commits = 0
    workers = max(1, int(workers or 1))
    total_repos = len(grouped)

    logger.info(
        "[human-test-commits] Loaded %d repo rows across %d repos from %s",
        sum(len(v) for v in grouped.values()),
        len(grouped),
        repo_qc_dir,
    )

    if workers == 1:
        for repo_name, repo_rows in grouped.items():
            language, repo_test_commits, repo_count, repo_commits_scanned = (
                _process_repo_human_test_commits(repo_rows[0])
            )
            repos_processed += repo_count
            commits_scanned += repo_commits_scanned
            if repo_test_commits:
                repos_with_test_commits += 1
                test_commit_rows_by_language[language].extend(repo_test_commits)
            pct = (repos_processed / total_repos * 100) if total_repos else 100
            logger.info(
                "[human-test-commits] Progress: %d/%d repos (%.1f%%), %d commits scanned",
                repos_processed,
                total_repos,
                pct,
                commits_scanned,
            )
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    _process_repo_human_test_commits, repo_rows[0]
                ): repo_name
                for repo_name, repo_rows in grouped.items()
            }
            completed = 0
            try:
                for future in as_completed(futures):
                    language, repo_test_commits, repo_count, repo_commits_scanned = (
                        future.result()
                    )
                    repos_processed += repo_count
                    commits_scanned += repo_commits_scanned
                    if repo_test_commits:
                        repos_with_test_commits += 1
                        test_commit_rows_by_language[language].extend(repo_test_commits)
                    completed += 1
                    pct = (completed / total_repos * 100) if total_repos else 100
                    logger.info(
                        "[human-test-commits] Progress: %d/%d repos completed (%.1f%%), %d commits scanned",
                        completed,
                        total_repos,
                        pct,
                        commits_scanned,
                    )
            except KeyboardInterrupt:
                logger.warning(
                    "[human-test-commits] Interrupted by user (KeyboardInterrupt). Cancelling remaining jobs..."
                )
                for fut in futures:
                    fut.cancel()
                raise

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_files: dict[str, str] = {}
    total_test_commits = 0
    for language, language_rows in sorted(test_commit_rows_by_language.items()):
        output_path = output_dir / f"{language}_human_test_commit_qc.csv"
        write_test_commits_csv(language_rows, output_path)
        output_files[language] = str(output_path)
        total_test_commits += len(language_rows)
        logger.info(
            "[human-test-commits] Wrote %d human test commits for %s to %s",
            len(language_rows),
            language,
            output_path,
        )

    logger.info(
        "[human-test-commits] Finished: %d repos processed, %d commits scanned, %d human test commits found",
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
    """Process a single repo row (from repo-QC CSV) and return agent test-commit rows."""
    repo_name = (repo_row.get("repo_name") or repo_row.get("full_name") or "").strip()
    clone_url = (
        repo_row.get("clone_url") or f"https://github.com/{repo_name}.git"
    ).strip()
    language = (repo_row.get("language") or "unknown").strip().lower()

    logger.info("[agent-test-commits] Cloning %s (%s)", repo_name, language)

    with temp_clone_commit_history(clone_url, repo_name, prefix="agent-test-commits-", timeout=300) as repo_path:
        if repo_path is None:
            logger.warning(
                "Failed to clone %s while filtering agent test commits", repo_name
            )
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
            if commit.commit_role != "agent":
                continue
            if not commit.is_test_commit:
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
    """Filter agent-config repositories to agent-authored commits that touch test files.

    Produces per-language `<lang>_agent_test_commit_qc.csv` files.
    """
    grouped: dict[str, list[dict]] = defaultdict(list)

    csv_paths = sorted(
        Path(repo_qc_dir).glob("*_agent_repo.csv"), key=lambda path: path.name
    )
    for csv_path in csv_paths:
        with csv_path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
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
        for repo_name, repo_rows in grouped.items():
            language, repo_test_commits, repo_count, repo_commits_scanned = (
                _process_repo_agent_test_commits(repo_rows[0])
            )
            repos_processed += repo_count
            commits_scanned += repo_commits_scanned
            if repo_test_commits:
                repos_with_test_commits += 1
                test_commit_rows_by_language[language].extend(repo_test_commits)
            pct = (repos_processed / total_repos * 100) if total_repos else 100
            logger.info(
                "[agent-test-commits] Progress: %d/%d repos (%.1f%%), %d commits scanned",
                repos_processed,
                total_repos,
                pct,
                commits_scanned,
            )
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    _process_repo_agent_test_commits, repo_rows[0]
                ): repo_name
                for repo_name, repo_rows in grouped.items()
            }
            completed = 0
            try:
                for future in as_completed(futures):
                    language, repo_test_commits, repo_count, repo_commits_scanned = (
                        future.result()
                    )
                    repos_processed += repo_count
                    commits_scanned += repo_commits_scanned
                    if repo_test_commits:
                        repos_with_test_commits += 1
                        test_commit_rows_by_language[language].extend(repo_test_commits)
                    completed += 1
                    pct = (completed / total_repos * 100) if total_repos else 100
                    logger.info(
                        "[agent-test-commits] Progress: %d/%d repos completed (%.1f%%), %d commits scanned",
                        completed,
                        total_repos,
                        pct,
                        commits_scanned,
                    )
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
        output_path = output_dir / f"{language}_agent_test_commit_qc.csv"
        write_test_commits_csv(language_rows, output_path)
        output_files[language] = str(output_path)
        total_test_commits += len(language_rows)
        logger.info(
            "[agent-test-commits] Wrote %d agent test commits for %s to %s",
            len(language_rows),
            language,
            output_path,
        )

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
    """
    Build a candidate pool of pre-2021 commits by scanning raw commit CSV exports.

    Args:
        raw_commits_dir: Directory containing raw commit CSVs (e.g., github-search-raw)
        cutoff_date: ISO date string upper bound (inclusive). Defaults to HUMAN_CORPUS_CUTOFF_DATE.

    Returns:
        Mapping of repo_full_name -> list of commit row dicts (filtered to commit_date <= cutoff_date)
    """
    candidates: dict[str, list[dict]] = defaultdict(list)
    raw_dir = Path(raw_commits_dir)
    csv_paths = sorted(raw_dir.glob("**/*_commit*.csv"), key=lambda p: p.name)
    for csv_path in csv_paths:
        try:
            with csv_path.open("r", encoding="utf-8", newline="") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    repo_name = (
                        row.get("repo_name") or row.get("full_name") or ""
                    ).strip()
                    commit_date = (row.get("commit_date") or "").strip()
                    if not repo_name or not commit_date:
                        continue
                    # simple lexical compare for ISO YYYY-MM-DD strings
                    if commit_date <= cutoff_date:
                        candidates.setdefault(repo_name, []).append(dict(row))
        except Exception:
            # ignore unreadable files but continue
            logger.debug(f"Failed to read raw commits CSV: {csv_path}")
            continue

    return candidates


def _cli_main():
    # Ensure logging is configured for CLI runs so progress INFO messages are visible
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    parser = argparse.ArgumentParser(
        description="Filter agent datasets to test commits (agent or human)"
    )
    parser.add_argument("--mode", choices=["agent", "human"], default="agent")
    parser.add_argument(
        "--commit-qc-dir",
        type=Path,
        default=Path("github-search-agent") / "agent_repositories",
    )
    parser.add_argument(
        "--repo-qc-dir",
        type=Path,
        default=Path("github-search-agent") / "agent_repositories",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("output/test-commits"))
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()

    # Prefer repo-driven collection when repo QC CSVs are available
    repo_qc_files = (
        list(Path(args.repo_qc_dir).glob("*_agent_repo.csv"))
        if Path(args.repo_qc_dir).exists()
        else []
    )
    if args.mode == "agent":
        if repo_qc_files:
            collect_agent_test_commits_from_repos(
                args.repo_qc_dir, args.output_dir, workers=args.workers
            )
        else:
            collect_agent_test_commits(
                args.commit_qc_dir, args.output_dir, workers=args.workers
            )
    else:
        collect_human_test_commits(
            args.repo_qc_dir, args.output_dir, workers=args.workers
        )


if __name__ == "__main__":
    _cli_main()
