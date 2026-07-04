"""Git checkout plumbing for repo/commit-level fixture extraction.

Resolves a repo's on-disk clone path, serializes checkout-based extraction
per repo with a flock-based lock (so concurrent workers don't checkout the
same working tree at once), and checks out a specific commit with retry/
backoff for transient failures (stale index locks, shallow-clone history).
"""

import fcntl
import subprocess
from contextlib import contextmanager
from pathlib import Path
from time import sleep

from collection.logging_utils import get_logger

from .clone_primitives import _output_requests_credentials

logger = get_logger(__name__)


def _resolve_repo_path(clones_dir: Path, repo_name: str) -> Path:
    """Resolve a repository path using either slash or double-underscore naming."""
    candidates = [
        clones_dir / repo_name,
        clones_dir / repo_name.replace("/", "__"),
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return candidates[0]


@contextmanager
def _repo_worktree_lock(repo_path: Path):
    """Serialize checkout-based extraction for a repository path."""
    lock_path = repo_path / ".collection.lock"
    lock_path.touch(exist_ok=True)
    lock_file = lock_path.open("r+")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_UN)
        finally:
            lock_file.close()


def _checkout_commit(repo_path: Path, commit_sha: str) -> None:
    """Checkout a commit, falling back to fetching full history if needed.

    Raises RuntimeError if credentials are required (repo became private or was deleted).
    """
    lock_path = repo_path / ".git" / "index.lock"

    for attempt in range(3):
        try:
            result = subprocess.run(
                ["git", "checkout", commit_sha, "--quiet"],
                cwd=repo_path,
                timeout=30,
                check=True,
                capture_output=True,
                text=True,
            )
            return
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr or ""
            stdout = exc.stdout or ""
            combined = stderr.lower() + stdout.lower()
            if _output_requests_credentials(stderr) or _output_requests_credentials(
                stdout
            ):
                raise RuntimeError("Repository requires credentials for checkout")
            if "index.lock" in combined:
                if lock_path.exists():
                    try:
                        lock_path.unlink()
                        logger.warning(
                            "Removed stale git index lock in %s before retrying checkout of %s",
                            repo_path,
                            commit_sha,
                        )
                    except Exception:
                        pass
                sleep(0.5 * (attempt + 1))
                continue

            try:
                result = subprocess.run(
                    ["git", "fetch", "--unshallow", "--tags", "origin"],
                    cwd=repo_path,
                    timeout=300,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                if _output_requests_credentials(result.stderr):
                    raise RuntimeError("Repository requires credentials for fetch")
                result = subprocess.run(
                    ["git", "checkout", commit_sha, "--quiet"],
                    cwd=repo_path,
                    timeout=30,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                return
            except subprocess.CalledProcessError as fetch_exc:
                if _output_requests_credentials(fetch_exc.stderr or ""):
                    raise RuntimeError("Repository requires credentials for fetch")
                raise RuntimeError(f"Failed to checkout {commit_sha}: {fetch_exc}")
            except subprocess.TimeoutExpired:
                raise RuntimeError(f"Checkout timeout for {commit_sha}")
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Checkout timeout for {commit_sha}")

    raise RuntimeError(
        f"Failed to checkout {commit_sha}: stale git index lock persisted after retries"
    )
