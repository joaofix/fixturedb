"""
Clone repositories and apply post-clone quality filters.

After cloning we can measure things that are invisible from the GitHub API:
  - actual number of test files (path-based heuristic)
  - commit count
  - pinned HEAD commit SHA

Repos that fail quality thresholds are marked 'skipped' in the DB.
Repos that pass are marked 'cloned' and are ready for AST extraction.
"""

import logging
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

from collection.config import (
    CLONES_DIR,
    LANGUAGE_CONFIGS,
    MIN_COMMITS,
    MIN_TEST_FILES,
    CLONE_WORKERS,
    GITHUB_TOKEN,
)
from collection.db import db_session, get_repos_by_status, set_repo_status

logger = logging.getLogger(__name__)


def cleanup_stale_clones(dry_run: bool = False) -> dict:
    """
    Remove clone directories that should no longer exist on disk.

    A clone directory is considered stale if:
      - Its repo is not in the database at all (orphan from a wiped DB)
      - Its repo status is 'skipped' or 'error' (failed quality checks —
        the directory should have been deleted by clone_repo but wasn't
        if the process was killed mid-flight)
      - Its repo status is 'analysed' (extractor should have deleted it
        but the process was killed before cleanup)

    Directories for repos with status 'discovered' are also cleaned:
    they are partial or interrupted clones — a fresh clone is safer.

    Status 'cloned' directories are LEFT intact: extraction hasn't run
    yet and the clone is still needed.

    Args:
        dry_run: if True, log what would be deleted but do not delete.

    Returns a dict with counts: removed, kept, orphaned.
    """
    if not CLONES_DIR.exists():
        return {"removed": 0, "kept": 0, "orphaned": 0}

    STALE_STATUSES = {"discovered", "skipped", "error", "analysed"}

    # Build a lookup: directory_name → repo status
    # Directory name is full_name with "/" replaced by "__"
    with db_session() as conn:
        rows = conn.execute("SELECT full_name, status FROM repositories").fetchall()
    known = {r["full_name"].replace("/", "__"): r["status"] for r in rows}

    counts = {"removed": 0, "kept": 0, "orphaned": 0}

    for clone_dir in sorted(CLONES_DIR.iterdir()):
        if not clone_dir.is_dir():
            continue

        dir_key = clone_dir.name
        status = known.get(dir_key)

        if status is None:
            # Directory has no matching DB record — fully orphaned
            reason = "orphaned (not in database)"
            counts["orphaned"] += 1
        elif status in STALE_STATUSES:
            reason = f"stale (repo status = '{status}')"
            counts["removed"] += 1
        else:
            # status == 'cloned' — keep it, extraction still needs it
            logger.debug(f"[cleanup] Keep {dir_key} (status='{status}')")
            counts["kept"] += 1
            continue

        if dry_run:
            logger.info(f"[cleanup] Would remove {clone_dir.name}: {reason}")
        else:
            logger.info(f"[cleanup] Removing {clone_dir.name}: {reason}")
            shutil.rmtree(clone_dir, ignore_errors=True)

    return counts


# ---------------------------------------------------------------------------
# Single-repo clone + quality check
# ---------------------------------------------------------------------------


def clone_repo(
    repo_id: int, full_name: str, clone_url: str, language: str
) -> tuple[int, str, str | None]:
    """
    Clone a repository after fast pre-checks via git and GitHub API.

    Pre-checks (before cloning):
      1. Verify repo is accessible via git ls-remote (~2-3 seconds)
      2. Check via GitHub API that repo has ≥5 test files (~1-2 seconds)

    Post-clone checks (after cloning):
      3. Verify commit count ≥50
      4. Verify test file count ≥5 (local count, more accurate than API)

    Returns (repo_id, status, pinned_commit_or_None, skip_reason_or_None).
    status is one of: 'cloned' | 'skipped' | 'error'
    """
    target_dir = CLONES_DIR / full_name.replace("/", "__")

    # If the directory already exists and is a valid git repo, re-use it.
    # This handles the case where the process was killed after a successful
    # clone but before the DB status was updated — we avoid re-cloning.
    if target_dir.exists():
        try:
            commit = _get_head_sha(target_dir)
            logger.debug(f"[clone] {full_name} already present at {commit[:8]}")
            return repo_id, "cloned", commit, None
        except Exception:
            # Directory exists but is broken/partial — wipe and re-clone
            logger.debug(
                f"[clone] {full_name} directory broken, removing and re-cloning"
            )
            shutil.rmtree(target_dir, ignore_errors=True)

    # Pre-check 1: Verify the remote repo is accessible before cloning
    # This avoids wasting time/bandwidth on 404s or network errors
    if not _is_accessible_remote(clone_url):
        logger.debug(
            f"[clone] Skip {full_name}: remote not accessible or repo does not exist"
        )
        return repo_id, "error", None, None

    # Pre-check 2: Quick verify via GitHub API that repo has test files
    # This avoids cloning repos with zero test files (common for non-test projects)
    if not _has_sufficient_test_files(full_name, language):
        return repo_id, "skipped", None, "insufficient test files (GitHub API check)"

    logger.info(f"[clone] Cloning {full_name} …")
    try:
        result = subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                "1",  # snapshot only — no history needed
                "--single-branch",
                "--no-tags",
                clone_url,
                str(target_dir),
            ],
            capture_output=True,
            text=True,
            timeout=300,  # 5-minute hard timeout per repo
        )
        if result.returncode != 0:
            msg = result.stderr.strip()[:300]
            logger.warning(f"[clone] Failed {full_name}: {msg}")
            return repo_id, "error", None, None

    except subprocess.TimeoutExpired:
        shutil.rmtree(target_dir, ignore_errors=True)
        return repo_id, "error", None, None

    # Quality filter 1: commit count
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

    # Quality filter 2: test file count
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
        f"[clone] ✓ {full_name} " f"({test_file_count} test files, commit {commit[:8]})"
    )
    return repo_id, "cloned", commit, None


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


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


def _is_accessible_remote(clone_url: str) -> bool:
    """
    Quick check: is the remote repository accessible?
    Uses git ls-remote which is fast and doesn't require cloning.
    Returns True if accessible, False otherwise.
    """
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--heads", clone_url],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return result.returncode == 0
    except Exception:
        return False


def _has_sufficient_test_files(full_name: str, language: str) -> bool:
    """
    Check if the repository has at least MIN_TEST_FILES via GitHub API.
    This avoids cloning repos that clearly have no test files.

    Uses the GitHub code search API to count test files by examining
    standard test path patterns for the given language.

    Returns True if the repo likely has sufficient test files,
    False if we're confident it doesn't.
    Returns True on API errors (fallback: proceed with clone and check locally).
    """
    try:
        config = LANGUAGE_CONFIGS.get(language)
        if not config or not config.test_path_patterns:
            return True  # No test patterns defined, skip check

        # Build search query: look for files in test directories
        # Example: repo:owner/name filename:test_*.py OR path:tests
        test_patterns = config.test_path_patterns[:3]  # Limit to 3 most common
        pattern_queries = " OR ".join([f"path:{p}" for p in test_patterns])
        query = f"repo:{full_name} ({pattern_queries})"

        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if GITHUB_TOKEN:
            headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

        url = "https://api.github.com/search/code"
        params = {
            "q": query,
            "per_page": 1,  # Just need to know if files exist
        }

        response = requests.get(url, headers=headers, params=params, timeout=5)

        if response.status_code == 200:
            data = response.json()
            count = data.get("total_count", 0)
            if count < MIN_TEST_FILES:
                logger.debug(
                    f"[clone] Skip {full_name}: only {count} test files found (API check)"
                )
                return False
            return True
        elif response.status_code == 422:
            # Invalid search query (too complex) — fallback to clone
            logger.debug(
                f"[clone] Could not validate test files for {full_name} via API"
            )
            return True
        else:
            # Other errors — don't skip, let clone do the check
            return True

    except Exception as e:
        logger.debug(f"[clone] Error checking test files for {full_name}: {e}")
        # On error, return True to proceed with clone (don't skip on error)
        return True


def _count_commits(repo_dir: Path) -> int:
    """
    With --depth 1 git rev-list reports only 1 commit, so we fetch a
    small amount of history first to get a realistic count.
    We cap at 500 to avoid fetching huge histories.
    """
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
    # Also check path-pattern-based directories
    for pattern in config.test_path_patterns:
        for path in repo_dir.rglob("*"):
            if pattern in str(path.relative_to(repo_dir)) and path.is_file():
                count += 1
                break  # count the directory once, not every file in it
    return count


# ---------------------------------------------------------------------------
# Batch cloning
# ---------------------------------------------------------------------------


def clone_pending_repos(
    language: str | None = None, batch_size: int | None = None
) -> dict:
    """
    Clone all repos in 'discovered' status (optionally filtered by language).
    Uses a thread pool for parallel cloning.

    Runs cleanup_stale_clones first to remove leftover directories from any
    previous interrupted run before starting new clones.

    batch_size controls how many repos are processed in this call:
      - None (default): process ALL pending repos — used by `run`
      - int N: process at most N repos — used by `clone --batch N`

    Returns a summary dict.
    """
    # Remove stale directories before starting — keeps disk usage honest
    # and ensures repos in 'discovered' status get a clean fresh clone
    stale = cleanup_stale_clones()
    if any(stale.values()):
        logger.info(f"[cleanup] Stale clones removed before batch: {stale}")
    with db_session() as conn:
        rows = get_repos_by_status(conn, "discovered")
        if language:
            rows = [r for r in rows if r["language"] == language]
        batch = list(rows) if batch_size is None else list(rows)[:batch_size]

    if not batch:
        logger.info("No repos in 'discovered' status to clone.")
        return {"cloned": 0, "skipped": 0, "error": 0}

    batch_total = len(batch)
    logger.info(f"Cloning batch of {batch_total} repos with {CLONE_WORKERS} workers …")
    summary = {"cloned": 0, "skipped": 0, "error": 0}

    # Progress tracking
    processed = 0
    start_time = time.time()
    progress_interval = max(1, batch_total // 20)  # Log ~20 progress updates

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
        for future in as_completed(futures):
            repo_id, status, commit, skip_reason = future.result()
            summary[status] = summary.get(status, 0) + 1
            processed += 1

            with db_session() as conn:
                set_repo_status(
                    conn, repo_id, status, skip_reason=skip_reason, pinned_commit=commit
                )

            # Log progress periodically
            if processed % progress_interval == 0 or processed == batch_total:
                elapsed = time.time() - start_time
                rate = processed / elapsed if elapsed > 0 else 0
                remaining = batch_total - processed
                eta_secs = remaining / rate if rate > 0 else 0
                eta_mins = eta_secs / 60
                percent = (processed / batch_total) * 100

                logger.info(
                    f"[progress] Cloned {processed:4d}/{batch_total} ({percent:5.1f}%) | "
                    f"cloned:{summary['cloned']:3d} skipped:{summary['skipped']:3d} error:{summary['error']:1d} | "
                    f"rate:{rate:5.2f} repos/sec | ETA:{eta_mins:6.1f}min"
                )

    logger.info(f"Batch done: {summary}")
    return summary


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------


def delete_clone(full_name: str) -> None:
    """Remove the local clone once extraction is complete."""
    target_dir = CLONES_DIR / full_name.replace("/", "__")
    if target_dir.exists():
        shutil.rmtree(target_dir)
        logger.debug(f"[cleanup] Removed {target_dir}")


def get_clone_path(full_name: str) -> Path:
    return CLONES_DIR / full_name.replace("/", "__")
