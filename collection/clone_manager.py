"""CloneManager: small abstraction to manage clone lifecycle and disk safety.

Provides context managers to clone repos (either via an injected clone function
or into a temporary directory) and guarantees cleanup on exit.
"""

import os
import shutil
import shutil as _shutil
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Generator, Optional

from collection.logging_utils import get_logger

logger = get_logger(__name__)

from .temp_clone import cleanup_tempdir, clone_to_tempdir

# Configurable concurrency limit for git clone operations
DEFAULT_MAX_CONCURRENT_CLONES = int(os.getenv("MAX_CONCURRENT_CLONES", "4"))
_CLONE_SEMAPHORE = threading.Semaphore(DEFAULT_MAX_CONCURRENT_CLONES)


def clone_with_throttle(
    clone_fn: Callable[[str, Path], bool],
    clone_url: str,
    target_dir: Path,
    *,
    min_free_bytes: int = 100_000_000,
    retries: int = 3,
    backoff_base: float = 0.5,
):
    """Attempt to clone using a global semaphore to throttle concurrent git processes.

    Retries on failure with exponential backoff. Yields the same as
    `clone_with_function` (context manager yielding the repo path or None).
    """

    @contextmanager
    def _inner():
        # Acquire slot for cloning to protect disk/io
        _CLONE_SEMAPHORE.acquire()
        try:
            attempt = 0
            while attempt < retries:
                attempt += 1
                with clone_with_function(
                    clone_fn, clone_url, target_dir, min_free_bytes=min_free_bytes
                ) as repo_path:
                    if repo_path is not None:
                        yield repo_path
                        return

                # failed; exponential backoff before retrying
                sleep_for = backoff_base * (2 ** (attempt - 1))
                time.sleep(sleep_for)

            # All attempts failed
            yield None
        finally:
            _CLONE_SEMAPHORE.release()

    return _inner()


def ensure_free_space(path: Path, min_bytes: int) -> bool:
    """Return True when `path` has at least `min_bytes` free, else False.

    Swallows exceptions and returns True to avoid blocking in ambiguous environments.
    """
    try:
        stat = shutil.disk_usage(path)
        return stat.free >= int(min_bytes)
    except Exception:
        return True


@contextmanager
def clone_with_function(
    clone_fn: Callable[[str, Path], bool],
    clone_url: str,
    target_dir: Path,
    *,
    min_free_bytes: int = 100_000_000,
) -> Generator[Optional[Path], None, None]:
    """Clone using a provided clone function into `target_dir` and remove it on exit.

    `clone_fn` should accept `(clone_url, target_dir)` and return True on success.
    """
    # Check free space on parent of target_dir
    parent = target_dir.parent if target_dir.parent.exists() else Path.cwd()
    if min_free_bytes and not ensure_free_space(parent, min_free_bytes):
        logger.warning(
            "Insufficient free space on %s for cloning (need %d bytes)",
            parent,
            min_free_bytes,
        )
        yield None
        return

    try:
        ok = clone_fn(clone_url, target_dir)
    except Exception:
        ok = False

    if not ok or not target_dir.exists():
        yield None
        return

    try:
        yield target_dir
    finally:
        _shutil.rmtree(target_dir, ignore_errors=True)


def prune_old_clones(
    clones_dir: Path, max_age_seconds: int = 7 * 24 * 3600, dry_run: bool = False
) -> dict:
    """Remove clone directories under `clones_dir` older than `max_age_seconds`.

    Returns a dict with counts: {removed, kept, errors}.
    """
    counts = {"removed": 0, "kept": 0, "errors": 0}
    now = time.time()
    if not clones_dir.exists() or not clones_dir.is_dir():
        return counts

    for child in sorted(clones_dir.iterdir()):
        if not child.is_dir():
            continue
        try:
            mtime = child.stat().st_mtime
            age = now - mtime
            if age > max_age_seconds:
                if dry_run:
                    logger.info(
                        "Would remove stale clone %s (age=%.1f days)",
                        child,
                        age / 86400,
                    )
                    counts["removed"] += 1
                else:
                    _shutil.rmtree(child, ignore_errors=True)
                    logger.info("Removed stale clone %s", child)
                    counts["removed"] += 1
            else:
                counts["kept"] += 1
        except Exception as e:
            logger.debug("Error pruning clone %s: %s", child, e)
            counts["errors"] += 1

    return counts


@contextmanager
def temp_clone_commit_history(
    clone_url: str,
    repo_full_name: str,
    *,
    prefix: str = "collection-",
    timeout: int = 300,
):
    """Clone history into a temporary directory and cleanup on exit.

    Uses `clone_to_tempdir` helper; yields the repo path (or None on failure).
    """
    repo_path, temp_root = clone_to_tempdir(
        repo_full_name,
        clone_url,
        ["--filter=blob:limit=10m", "--single-branch", "--no-tags"],
        timeout=timeout,
        prefix=prefix,
    )
    if repo_path is None:
        yield None
        return

    try:
        yield repo_path
    finally:
        cleanup_tempdir(temp_root)
