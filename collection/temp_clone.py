"""Shared helpers for temporary repository clones used by QC scripts."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
import re


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
) -> tuple[Path | None, Path | None]:
    """Clone a repo into a temporary directory and return (repo_path, temp_root).

    The caller is responsible for removing `temp_root` with `cleanup_tempdir()`.
    """
    owner, name = repo_full_name.split("/")
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
            return None, None
    except KeyboardInterrupt:
        raise
    except Exception:
        pass

    cleanup_tempdir(temp_root)
    return None, None


def cleanup_tempdir(temp_root: Path | None) -> None:
    """Delete the temporary clone root directory if it exists."""
    if temp_root is not None:
        shutil.rmtree(temp_root, ignore_errors=True)
