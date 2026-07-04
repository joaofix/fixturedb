"""Pluggable CSV adapter abstraction.

Provides a default filesystem-backed adapter but allows tests or alternate
backends (in-memory, S3, DB export) to be plugged in via `set_adapter()`.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Iterable, Iterator


class CSVAdapter:
    """Adapter interface — override methods as needed."""

    def read_dicts(self, path: Path) -> Iterator[dict]:
        """Yield each row of *path* as a dict, in file order."""
        path = Path(path)
        with path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                yield dict(row)

    def write_dicts(
        self, path: Path, rows: Iterable[dict], fieldnames: list[str]
    ) -> Path:
        """Overwrite *path* with a header row followed by *rows*."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        rows_list = list(rows)
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            for r in rows_list:
                writer.writerow({k: r.get(k, "") for k in fieldnames})
        return path

    def append_dicts(
        self,
        path: Path,
        rows: Iterable[dict],
        fieldnames: list[str],
        fsync: bool = False,
    ) -> Path:
        """Append rows to *path*, writing the header only if it doesn't exist yet.

        Used by long-running scans that persist results incrementally rather
        than buffering everything in memory. Pass `fsync=True` to force the
        rows to disk immediately (e.g. for crash-safe checkpointing).
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        write_header = not path.exists()
        with path.open("a", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            if write_header:
                writer.writeheader()
            for r in rows:
                writer.writerow({k: r.get(k, "") for k in fieldnames})
            if fsync:
                fh.flush()
                os.fsync(fh.fileno())
        return path


_adapter: CSVAdapter | None = None


def get_adapter() -> CSVAdapter:
    """Return the process-wide `CSVAdapter`, creating the default one if unset."""
    global _adapter
    if _adapter is None:
        _adapter = CSVAdapter()
    return _adapter


def set_adapter(adapter: CSVAdapter) -> None:
    """Override the process-wide `CSVAdapter` (e.g. with a test double)."""
    global _adapter
    _adapter = adapter
