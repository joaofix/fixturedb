"""Lowest-level clone primitive: subprocess `git clone` into a fresh tempdir.

No DB, no throttling, no config — just clone-to-tempdir plus credential-gated
(private repo) failure detection. Two other modules build on this:
`ephemeral_clone.py` wraps it with throttling/disk-safety/cleanup context
managers for transient inspection, and `persistent_clone.py` is an independent,
DB-tracked workflow for the durable corpus clone directory.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path


class CloneUnavailable(Exception):
    """Raised by `clone_to_tempdir` when a repo could not be cloned after
    retrying, for a reason that is NOT a confirmed permanent condition
    (private/deleted repo, detected via `_output_requests_credentials` --
    that case still returns `(None, None)`, unchanged). A network blip, DNS
    failure, or a sustained outage all raise this instead of returning
    `(None, None)`, so a caller can tell "we don't actually know if this
    repo is cloneable" apart from "confirmed: it isn't" -- callers must
    not treat the two the same way (e.g. checkpointing a repo as
    permanently done because of a transient failure silently hides it from
    every future run; see human_test_commit_filter.py/test_commit_filter.py
    for where this bit a real Dataset B collection when the network dropped
    mid-run)."""


CREDENTIAL_PROMPT_PATTERNS = [
    re.compile(r"Username.*:", re.IGNORECASE),
    re.compile(r"Password.*:", re.IGNORECASE),
    re.compile(r"Personal access token.*:", re.IGNORECASE),
    re.compile(r"repository.*not found", re.IGNORECASE),
    re.compile(r"does not exist", re.IGNORECASE),
    re.compile(r"remote: Repository not found", re.IGNORECASE),
    re.compile(r"fatal: could not read Username", re.IGNORECASE),
    re.compile(r"Authentication failed", re.IGNORECASE),
    re.compile(r"PERMISSION_DENIED", re.IGNORECASE),
]


def _output_requests_credentials(stderr: str) -> bool:
    """Check if stderr output indicates a credential prompt or private repo error."""
    for pattern in CREDENTIAL_PROMPT_PATTERNS:
        if pattern.search(stderr):
            return True
    return False


def clone_to_tempdir(
    repo_full_name: str,
    clone_url: str,
    clone_args: list[str],
    *,
    timeout: int,
    prefix: str,
    retries: int = 2,
    backoff_base: float = 3.0,
) -> tuple[Path | None, Path | None]:
    """Clone a repo into a temporary directory and return (repo_path, temp_root).

    The caller is responsible for removing `temp_root` with `cleanup_tempdir()`.

    A credential prompt (private/deleted repo -- see
    `_output_requests_credentials`) is a confirmed, permanent condition and
    returns `(None, None)` immediately, no retry. Any other failure (network
    error, timeout, transient GitHub 5xx) is retried up to `retries` times
    with exponential backoff; if every attempt fails, raises
    `CloneUnavailable` instead of returning `(None, None)` -- a generic
    "confirmed None" here would be indistinguishable from a repo genuinely
    having nothing to clone, and a caller that checkpoints on that basis
    would silently and permanently miscategorize a repo that was never
    actually reached (see `CloneUnavailable`'s docstring). `retries` only
    defends against a brief blip within one call -- it will not survive a
    sustained outage; recovering from that is the checkpoint layer's job.
    """
    owner, name = repo_full_name.split("/")

    for attempt in range(retries + 1):
        temp_root = Path(tempfile.mkdtemp(prefix=prefix))
        repo_path = temp_root / f"{owner}__{name}"

        try:
            result = subprocess.run(
                ["git", "clone", *clone_args, clone_url, str(repo_path)],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode == 0:
                return repo_path, temp_root
            if _output_requests_credentials(result.stderr):
                cleanup_tempdir(temp_root)
                return None, None
        except KeyboardInterrupt:
            cleanup_tempdir(temp_root)
            raise
        except Exception:
            pass

        cleanup_tempdir(temp_root)
        if attempt < retries:
            time.sleep(backoff_base * (2**attempt))

    raise CloneUnavailable(f"clone failed after {retries + 1} attempt(s): {repo_full_name}")


def cleanup_tempdir(temp_root: Path | None) -> None:
    """Delete the temporary clone root directory if it exists."""
    if temp_root is not None:
        shutil.rmtree(temp_root, ignore_errors=True)


def clone_repo_for_commit_scan(clone_url: str, target_dir: Path) -> bool:
    """
    Clone a repository with full commit history but without downloading large blobs.

    This is the history used for agent-commit detection and fixture extraction.
    Returns False if the repo requires credentials (private/removed repo).
    """
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [
                "git",
                "clone",
                "--filter=blob:limit=10m",
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
            return False
        return bool(
            result.returncode == 0
            and target_dir.exists()
            and (list(target_dir.glob(".git")) or list(target_dir.iterdir()))
        )
    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return False


def shallow_clone_repo(clone_url: str, target_dir: Path) -> bool:
    """
    Shallow-clone a repository (depth 1) for quick agent config detection.

    Returns False if the repo requires credentials (private/removed repo).
    """
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
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
            timeout=120,
        )
        if _output_requests_credentials(result.stderr):
            return False
        return result.returncode == 0 and target_dir.exists()
    except Exception:
        return False
