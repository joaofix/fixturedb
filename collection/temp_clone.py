"""Shared helpers for temporary repository clones used by QC scripts."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


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
    except KeyboardInterrupt:
        # Propagate user interrupt so callers can shutdown cleanly
        raise
    except Exception:
        pass

    cleanup_tempdir(temp_root)
    return None, None


def cleanup_tempdir(temp_root: Path | None) -> None:
    """Delete the temporary clone root directory if it exists."""
    if temp_root is not None:
        shutil.rmtree(temp_root, ignore_errors=True)
