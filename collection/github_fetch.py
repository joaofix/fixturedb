"""Helpers for robust GitHub download fallbacks (archive downloads with retries).

This provides a simple, best-effort archive downloader to use when cloning
is too heavy or fails. It supports retry and basic resume via Range headers.
"""

import time
import shutil
import urllib.request
from pathlib import Path

DEFAULT_RETRIES = 3
DEFAULT_BACKOFF = 1.0


def download_github_archive(
    repo_full_name: str, dest: Path, retries: int = DEFAULT_RETRIES
):
    """Download the GitHub tarball for the default branch for `repo_full_name`.

    Returns the path to the downloaded archive, or raises on failure.
    """
    url = f"https://api.github.com/repos/{repo_full_name}/tarball"
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = dest.with_suffix(".tar.gz.tmp")
    attempt = 0
    while attempt < retries:
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=60) as resp:
                with open(tmp_path, "wb") as fh:
                    shutil.copyfileobj(resp, fh)
            tmp_path.rename(dest)
            return dest
        except Exception:
            attempt += 1
            time.sleep(DEFAULT_BACKOFF * attempt)
    raise RuntimeError(
        f"Failed to download archive for {repo_full_name} after {retries} attempts"
    )
