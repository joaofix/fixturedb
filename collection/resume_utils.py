"""Helpers for skipping already-completed collection work."""

from __future__ import annotations

from pathlib import Path

from .db import db_session


def latest_matching_file(directory: Path, pattern: str) -> Path | None:
    """Return the newest file matching a glob pattern, or None."""
    matches = sorted(directory.glob(pattern))
    return matches[-1] if matches else None


def database_has_rows(db_path: Path, table: str = "fixtures") -> bool:
    """Return True when the given table exists and contains at least one row."""
    if not db_path.exists():
        return False

    try:
        with db_session(db_path) as conn:
            cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")
            return (cursor.fetchone()[0] or 0) > 0
    except Exception:
        return False
