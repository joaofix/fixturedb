"""Pluggable CSV adapter abstraction.

Provides a default filesystem-backed adapter but allows tests or alternate
backends (in-memory, S3, DB export) to be plugged in via `set_adapter()`.
"""

from __future__ import annotations

import csv
import os
import sys
from pathlib import Path
from typing import Iterable, Iterator

# A single commit can legitimately touch tens of thousands of test files
# (e.g. a mass baseline-regeneration commit), pushing test_file_paths past
# the csv module's default 128KB field limit -- confirmed against a real
# microsoft/TypeScript commit (1.5MB test_file_paths, 21640 files) in
# Dataset B's toy output. Raise it process-wide so read_dicts/append_dicts
# don't crash on real, non-adversarial data.
csv.field_size_limit(sys.maxsize)


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

        Raises ValueError if *path* already exists with a different header
        than *fieldnames* -- silently appending would misalign every column
        after the point of divergence (each row is written positionally
        against *fieldnames*, but read back positionally against the file's
        original first line). This happens whenever a writer's schema grows
        a column and it runs again against a file an older schema version
        produced; fail loudly so the caller can migrate or regenerate the
        file deliberately instead of getting silently corrupted data.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        write_header = not path.exists()
        if not write_header:
            with path.open("r", encoding="utf-8", newline="") as fh:
                existing_header = next(csv.reader(fh), [])
            if existing_header and existing_header != fieldnames:
                raise ValueError(
                    f"append_dicts: {path} already has header {existing_header}, "
                    f"which does not match the fieldnames being appended "
                    f"{fieldnames}. Appending would silently misalign columns "
                    f"past the point of divergence. Migrate or delete the "
                    f"existing file before writing with the new schema."
                )
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
