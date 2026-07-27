"""Helpers shared across collection/research_questions/ scripts (rq1.py,
rq2.py, rq3.py, language_contamination.py) -- kept here once instead of
duplicated per-script, per this package's convention: leverage
already-collected data first, import logic from collection/ second, write
new logic only as a last resort (and then, only once).
"""

from __future__ import annotations

import sqlite3
import statistics
from pathlib import Path

from ..config import ROOT_DIR
from ..logging_utils import get_logger
from ..paths import DB_ROOT, db_path

logger = get_logger(__name__)

OUTPUT_DIR = ROOT_DIR / "research_questions"

DATASET_LABELS = {
    "a": "Dataset A (agent-authored)",
    "b": "Dataset B (human-authored, contemporary)",
    "c": "Dataset C (human-authored, pre-LLM)",
}

# (dataset compared against A, comparison label) -- B vs C intentionally
# omitted until Dataset B/C actually exist; see rq1.py's module docstring.
COMPARISONS = [("b", "A vs B"), ("c", "A vs C")]


def require_db_or_none(dataset: str, db_root: Path = DB_ROOT) -> Path | None:
    """db/{dataset}.db's path, or None (with a warning logged) if it doesn't
    exist yet -- the shared "skip, don't error" convention every rqN.py
    script uses so it can run against whatever subset of A/B/C is collected."""
    db_file = db_path(dataset, root=db_root)
    if not db_file.exists():
        logger.warning(f"{db_file} not found; skipping dataset {dataset!r}")
        return None
    return db_file


def summarize_continuous(values: list[float]) -> dict:
    if not values:
        return {"n": 0, "mean": None, "median": None, "min": None, "max": None, "stdev": None}
    return {
        "n": len(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "min": min(values),
        "max": max(values),
        "stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
    }


def fmt(value: float | None, digits: int = 2) -> str:
    return "--" if value is None else f"{value:.{digits}f}"


def fetch_continuous_column(conn: sqlite3.Connection, table: str, column: str) -> list[float]:
    """All non-null values of `column` in `table` -- e.g. fixtures.loc,
    mock_usages.num_interactions_configured. `table`/`column` are always
    developer-supplied constants, never user input."""
    rows = conn.execute(f"SELECT {column} FROM {table} WHERE {column} IS NOT NULL").fetchall()
    return [row[0] for row in rows]


def fetch_categorical_column(conn: sqlite3.Connection, table: str, column: str) -> dict[str, int]:
    """Value -> count of `column` in `table`, non-null values only."""
    rows = conn.execute(
        f"SELECT {column}, COUNT(*) FROM {table} WHERE {column} IS NOT NULL GROUP BY {column}"
    ).fetchall()
    return {row[0]: row[1] for row in rows}
