"""
Clone repositories and apply post-clone quality filters.

This module is the new-collection home for the cloning workflow previously
carried in old-collection. It keeps the repository selection, pre-checks,
clone, and quality-filter logic in one place so other collection phases can
reuse it directly.
"""

import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from tqdm import tqdm

from collection.logging_utils import get_logger

from .config import (
    CLONE_WORKERS,
    CLONES_DIR,
    GITHUB_TOKEN,
    LANGUAGE_CONFIGS,
    MIN_COMMITS,
    MIN_TEST_FILES,
)
from .db import db_session, get_repos_by_status, set_repo_status
from .temp_clone import _output_requests_credentials

logger = get_logger(__name__)


def cleanup_stale_clones(dry_run: bool = False) -> dict:
    """Remove clone directories that should no longer exist on disk."""
    if not CLONES_DIR.exists():
        return {"removed": 0, "kept": 0, "orphaned": 0}

    stale_statuses = {"discovered", "skipped", "error", "analysed"}

    with db_session() as conn:
        rows = conn.execute("SELECT full_name, status FROM repositories").fetchall()
    known = {row["full_name"].replace("/", "__"): row["status"] for row in rows}

    counts = {"removed": 0, "kept": 0, "orphaned": 0}

    for clone_dir in sorted(CLONES_DIR.iterdir()):
        if not clone_dir.is_dir():
            continue

        status = known.get(clone_dir.name)

        if status is None:
            reason = "orphaned (not in database)"
            counts["orphaned"] += 1
        elif status in stale_statuses:
            reason = f"stale (repo status = '{status}')"
            counts["removed"] += 1
        else:
            logger.debug(f"[cleanup] Keep {clone_dir.name} (status='{status}')")
            counts["kept"] += 1
            continue

        if dry_run:
            logger.info(f"[cleanup] Would remove {clone_dir.name}: {reason}")
        else:
            logger.info(f"[cleanup] Removing {clone_dir.name}: {reason}")
            shutil.rmtree(clone_dir, ignore_errors=True)

    return counts


def clone_repo(
    repo_id: int, full_name: str, clone_url: str, language: str
) -> tuple[int, str, str | None, str | None]:
    """
    Clone a repository after fast pre-checks via git and GitHub API.

    Returns (repo_id, status, pinned_commit_or_None, skip_reason_or_None).
    status is one of: 'cloned' | 'skipped' | 'error'.
    """
    target_dir = CLONES_DIR / full_name.replace("/", "__")

    if target_dir.exists():
        try:
            commit = _get_head_sha(target_dir)
            logger.debug(f"[clone] {full_name} already present at {commit[:8]}")
            return repo_id, "cloned", commit, None
        except Exception:
            logger.debug(
                f"[clone] {full_name} directory broken, removing and re-cloning"
            )
            shutil.rmtree(target_dir, ignore_errors=True)

    accessible, requires_creds = _is_accessible_remote(clone_url)
    if requires_creds:
        logger.info(
            f"[clone] Skip {full_name}: repository requires credentials (private or removed)"
        )
        return repo_id, "skipped", None, "requires_credentials"
    if not accessible:
        logger.debug(
            f"[clone] Skip {full_name}: remote not accessible or repo does not exist"
        )
        return repo_id, "error", None, None

    if not _has_sufficient_test_files(full_name, language):
        return repo_id, "skipped", None, "insufficient test files (GitHub API check)"

    logger.info(f"[clone] Cloning {full_name} …")
    try:
        result = subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--single-branch",
                "--no-tags",
                clone_url,
                str(target_dir),
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if _output_requests_credentials(result.stderr):
            shutil.rmtree(target_dir, ignore_errors=True)
            logger.info(f"[clone] Skip {full_name}: repository requires credentials")
            return repo_id, "skipped", None, "requires_credentials"
        if result.returncode != 0:
            message = result.stderr.strip()[:300]
            logger.warning(f"[clone] Failed {full_name}: {message}")
            return repo_id, "error", None, None
    except subprocess.TimeoutExpired:
        shutil.rmtree(target_dir, ignore_errors=True)
        return repo_id, "error", None, None

    commit_count = _count_commits(target_dir)
    if commit_count < MIN_COMMITS:
        shutil.rmtree(target_dir, ignore_errors=True)
        logger.debug(f"[clone] Skip {full_name}: only {commit_count} commits")
        return (
            repo_id,
            "skipped",
            None,
            f"insufficient commits ({commit_count} < {MIN_COMMITS})",
        )

    config = LANGUAGE_CONFIGS.get(language)
    test_file_count = _count_test_files(target_dir, config)
    if test_file_count < MIN_TEST_FILES:
        shutil.rmtree(target_dir, ignore_errors=True)
        logger.debug(f"[clone] Skip {full_name}: only {test_file_count} test files")
        return (
            repo_id,
            "skipped",
            None,
            f"insufficient test files ({test_file_count} < {MIN_TEST_FILES})",
        )

    commit = _get_head_sha(target_dir)
    logger.info(
        f"[clone] ✓ {full_name} ({test_file_count} test files, commit {commit[:8]})"
    )
    return repo_id, "cloned", commit, None


def _get_head_sha(repo_dir: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        timeout=10,
    )
    result.check_returncode()
    return result.stdout.strip()


def _is_accessible_remote(clone_url: str) -> tuple[bool, bool]:
    """Fast check: is the remote repository accessible?

    Returns (accessible, is_credential_required):
    - accessible: True if remote is reachable
    - is_credential_required: True if repo asks for credentials (private or removed)
    """
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--heads", clone_url],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            return True, False
        if _output_requests_credentials(result.stderr):
            return False, True
        return False, False
    except Exception:
        return False, False


def _has_sufficient_test_files(full_name: str, language: str) -> bool:
    """Check if the repository has at least MIN_TEST_FILES via GitHub API."""
    try:
        config = LANGUAGE_CONFIGS.get(language)
        if not config or not config.test_path_patterns:
            return True

        test_patterns = config.test_path_patterns[:3]
        pattern_queries = " OR ".join([f"path:{pattern}" for pattern in test_patterns])
        query = f"repo:{full_name} ({pattern_queries})"

        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if GITHUB_TOKEN:
            headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

        response = requests.get(
            "https://api.github.com/search/code",
            headers=headers,
            params={"q": query, "per_page": "1"},
            timeout=5,
        )

        if response.status_code == 200:
            data = response.json()
            count = data.get("total_count", 0)
            if count < MIN_TEST_FILES:
                logger.debug(
                    f"[clone] Skip {full_name}: only {count} test files found (API check)"
                )
                return False
            return True
        if response.status_code == 422:
            logger.debug(
                f"[clone] Could not validate test files for {full_name} via API"
            )
            return True
        return True
    except Exception as exc:
        logger.debug(f"[clone] Error checking test files for {full_name}: {exc}")
        return True


def _count_commits(repo_dir: Path) -> int:
    """Fetch a small amount of history, then count commits on HEAD."""
    try:
        subprocess.run(
            ["git", "fetch", "--depth", "500", "origin"],
            cwd=repo_dir,
            capture_output=True,
            timeout=60,
        )
        result = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return int(result.stdout.strip())
    except Exception:
        return 0


def _count_test_files(repo_dir: Path, config) -> int:
    """Count files that match the language's test file naming conventions."""
    if config is None:
        return 0

    count = 0
    for suffix in config.test_file_suffixes:
        count += len(list(repo_dir.rglob(f"*{suffix}")))

    for pattern in config.test_path_patterns:
        for path in repo_dir.rglob("*"):
            if pattern in str(path.relative_to(repo_dir)) and path.is_file():
                count += 1
                break

    return count


def clone_pending_repos(
    language: str | None = None, batch_size: int | None = None
) -> dict:
    """Clone all repos in 'discovered' status (optionally filtered by language)."""
    stale = cleanup_stale_clones()
    if any(stale.values()):
        logger.info(f"[cleanup] Stale clones removed before batch: {stale}")

    with db_session() as conn:
        rows = get_repos_by_status(conn, "discovered")
        if language:
            rows = [row for row in rows if row["language"] == language]
        batch = list(rows) if batch_size is None else list(rows)[:batch_size]

    if not batch:
        logger.info("No repos in 'discovered' status to clone.")
        return {"cloned": 0, "skipped": 0, "error": 0}

    batch_total = len(batch)
    logger.info(f"Cloning batch of {batch_total} repos with {CLONE_WORKERS} workers …")
    summary = {"cloned": 0, "skipped": 0, "error": 0}

    with ThreadPoolExecutor(max_workers=CLONE_WORKERS) as executor:
        futures = {
            executor.submit(
                clone_repo,
                row["id"],
                row["full_name"],
                row["clone_url"],
                row["language"],
            ): row
            for row in batch
        }
        with tqdm(total=batch_total, desc="Cloning", unit="repo") as pbar:
            for future in as_completed(futures):
                repo_id, status, commit, skip_reason = future.result()
                summary[status] = summary.get(status, 0) + 1
                pbar.set_description_str(
                    f"Cloning [cloned:{summary['cloned']} skipped:{summary['skipped']} error:{summary['error']}]"
                )
                pbar.update(1)

                with db_session() as conn:
                    set_repo_status(
                        conn,
                        repo_id,
                        status,
                        skip_reason=skip_reason,
                        pinned_commit=commit,
                    )

    logger.info(f"Batch done: {summary}")
    return summary


def delete_clone(full_name: str) -> None:
    """Remove the local clone once extraction is complete."""
    target_dir = CLONES_DIR / full_name.replace("/", "__")
    if target_dir.exists():
        shutil.rmtree(target_dir)
        logger.debug(f"[cleanup] Removed {target_dir}")


def get_clone_path(full_name: str) -> Path:
    return CLONES_DIR / full_name.replace("/", "__")
