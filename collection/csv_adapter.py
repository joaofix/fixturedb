"""Pluggable CSV adapter abstraction.

Provides a default filesystem-backed adapter but allows tests or alternate
backends (in-memory, S3, DB export) to be plugged in via `set_adapter()`.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable, Iterator


class CSVAdapter:
    """Adapter interface — override methods as needed."""

    def read_dicts(self, path: Path) -> Iterator[dict]:
        path = Path(path)
        with path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                yield dict(row)

    def write_dicts(
        self, path: Path, rows: Iterable[dict], fieldnames: list[str]
    ) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        rows_list = list(rows)
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            for r in rows_list:
                writer.writerow({k: r.get(k, "") for k in fieldnames})
        return path


_adapter: CSVAdapter | None = None


def get_adapter() -> CSVAdapter:
    global _adapter
    if _adapter is None:
        _adapter = CSVAdapter()
    return _adapter


def set_adapter(adapter: CSVAdapter) -> None:
    global _adapter
    _adapter = adapter
