#!/usr/bin/env python3
"""One-time migration: split old data/*.db files into the new db/ layout.

Old layout (pre CLI-redesign):
    data/fixturedb-agent.db  -- Dataset A
    data/fixturedb-human.db  -- Datasets B and C, sharing one file with no
                                populated discriminator column
    data/corpus.db           -- pre-A/B/C "paired study" corpus

New layout:
    db/a.db, db/b.db, db/c.db, db/corpus.db

`fixturedb-agent.db` and `corpus.db` are plain copies (single-dataset files
already). `fixturedb-human.db` requires a real split: since it has no
discriminator column, B and C rows are told apart by cross-referencing
`repositories.full_name` against the already-migrated
`datasets/{b,c}/fixtures/*.csv` (the CSVs are the ground truth for which repo
belongs to which dataset -- see internal-docs and the CLI-redesign plan).

Idempotent: does nothing if the corresponding old file is missing (e.g. on a
checkout where data/ is empty) or the new file already exists. Safe to run
from any clone, including ones with real local collection data.

Usage: python -m scripts.migrate_db_layout
"""

from __future__ import annotations

import csv
import shutil
import sqlite3
from pathlib import Path

from collection.config import ROOT_DIR
from collection.db import initialise_db
from collection.logging_utils import get_logger

logger = get_logger(__name__)

OLD_DATA_DIR = ROOT_DIR / "data"
NEW_DB_DIR = ROOT_DIR / "db"
DATASETS_ROOT = ROOT_DIR / "datasets"

# Tables in a repo-graph, in FK-safe insertion order, and the column each one
# uses to reach back to `repositories.id` (directly or transitively).
_CHILD_TABLES = [
    ("test_files", "repo_id"),
    ("fixtures", "repo_id"),  # also has file_id -> test_files.id, remapped separately
    ("commit_observations", "repo_id"),
    ("test_commits", "repo_id"),
    ("mock_usages", "repo_id"),  # also has fixture_id -> fixtures.id, remapped separately
    ("checkpoints", "repo_id"),
]


def _load_repo_names_from_fixture_csvs(fixtures_dir: Path) -> set[str]:
    names: set[str] = set()
    if not fixtures_dir.exists():
        return names
    for csv_path in fixtures_dir.glob("*.csv"):
        with csv_path.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                repo_name = row.get("repo_name")
                if repo_name:
                    names.add(repo_name)
    return names


def _copy_repo_graph(
    src_conn: sqlite3.Connection, dst_conn: sqlite3.Connection, repo_names: set[str]
) -> int:
    """Copy every repo (and its dependent rows) whose full_name is in
    `repo_names` from `src_conn` into `dst_conn`, remapping autoincrement ids.
    Returns the number of repos copied.
    """
    if not repo_names:
        return 0

    placeholders = ",".join("?" for _ in repo_names)
    repo_rows = src_conn.execute(
        f"SELECT * FROM repositories WHERE full_name IN ({placeholders})",
        sorted(repo_names),
    ).fetchall()

    repo_id_map: dict[int, int] = {}
    for row in repo_rows:
        old_id = row["id"]
        cols = [c for c in row.keys() if c != "id"]
        placeholders_vals = ",".join("?" for _ in cols)
        cursor = dst_conn.execute(
            f"INSERT INTO repositories ({','.join(cols)}) VALUES ({placeholders_vals})",
            [row[c] for c in cols],
        )
        repo_id_map[old_id] = cursor.lastrowid

    if not repo_id_map:
        return 0

    file_id_map: dict[int, int] = {}
    fixture_id_map: dict[int, int] = {}

    old_repo_ids = list(repo_id_map.keys())
    ph = ",".join("?" for _ in old_repo_ids)

    # test_files first (fixtures.file_id depends on it)
    for row in src_conn.execute(
        f"SELECT * FROM test_files WHERE repo_id IN ({ph})", old_repo_ids
    ).fetchall():
        cols = [c for c in row.keys() if c != "id"]
        values = [
            repo_id_map[row["repo_id"]] if c == "repo_id" else row[c] for c in cols
        ]
        cursor = dst_conn.execute(
            f"INSERT INTO test_files ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})",
            values,
        )
        file_id_map[row["id"]] = cursor.lastrowid

    for row in src_conn.execute(
        f"SELECT * FROM fixtures WHERE repo_id IN ({ph})", old_repo_ids
    ).fetchall():
        cols = [c for c in row.keys() if c != "id"]
        values = []
        for c in cols:
            if c == "repo_id":
                values.append(repo_id_map[row["repo_id"]])
            elif c == "file_id":
                values.append(file_id_map.get(row["file_id"]))
            else:
                values.append(row[c])
        cursor = dst_conn.execute(
            f"INSERT INTO fixtures ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})",
            values,
        )
        fixture_id_map[row["id"]] = cursor.lastrowid

    for table, repo_col in (
        ("commit_observations", "repo_id"),
        ("test_commits", "repo_id"),
        ("checkpoints", "repo_id"),
    ):
        for row in src_conn.execute(
            f"SELECT * FROM {table} WHERE {repo_col} IN ({ph})", old_repo_ids
        ).fetchall():
            cols = [c for c in row.keys() if c != "id"]
            values = [
                repo_id_map[row[repo_col]] if c == repo_col else row[c] for c in cols
            ]
            dst_conn.execute(
                f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})",
                values,
            )

    for row in src_conn.execute(
        f"SELECT * FROM mock_usages WHERE repo_id IN ({ph})", old_repo_ids
    ).fetchall():
        if row["fixture_id"] not in fixture_id_map:
            continue  # fixture wasn't copied (shouldn't happen, defensive)
        cols = [c for c in row.keys() if c != "id"]
        values = []
        for c in cols:
            if c == "repo_id":
                values.append(repo_id_map[row["repo_id"]])
            elif c == "fixture_id":
                values.append(fixture_id_map[row["fixture_id"]])
            else:
                values.append(row[c])
        dst_conn.execute(
            f"INSERT INTO mock_usages ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})",
            values,
        )

    dst_conn.commit()
    return len(repo_id_map)


def _plain_copy(src: Path, dst: Path, label: str) -> None:
    if not src.exists():
        logger.info(f"{label}: no source at {src}, skipping")
        return
    if dst.exists():
        logger.info(f"{label}: destination {dst} already exists, skipping")
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    logger.info(f"{label}: copied {src} -> {dst}")


def _split_human_db(src: Path, b_dst: Path, c_dst: Path) -> None:
    if not src.exists():
        logger.info(f"human DB split: no source at {src}, skipping")
        return
    if b_dst.exists() or c_dst.exists():
        logger.info(
            f"human DB split: {b_dst} or {c_dst} already exists, skipping"
        )
        return

    b_repo_names = _load_repo_names_from_fixture_csvs(DATASETS_ROOT / "b" / "fixtures")
    c_repo_names = _load_repo_names_from_fixture_csvs(DATASETS_ROOT / "c" / "fixtures")

    b_dst.parent.mkdir(parents=True, exist_ok=True)
    initialise_db(b_dst)
    initialise_db(c_dst)

    src_conn = sqlite3.connect(src)
    src_conn.row_factory = sqlite3.Row
    try:
        b_conn = sqlite3.connect(b_dst)
        b_conn.row_factory = sqlite3.Row
        try:
            b_count = _copy_repo_graph(src_conn, b_conn, b_repo_names)
        finally:
            b_conn.close()

        c_conn = sqlite3.connect(c_dst)
        c_conn.row_factory = sqlite3.Row
        try:
            c_count = _copy_repo_graph(src_conn, c_conn, c_repo_names)
        finally:
            c_conn.close()
    finally:
        src_conn.close()

    logger.info(f"human DB split: {b_count} repos -> {b_dst}, {c_count} repos -> {c_dst}")


def main() -> int:
    NEW_DB_DIR.mkdir(parents=True, exist_ok=True)

    _plain_copy(OLD_DATA_DIR / "fixturedb-agent.db", NEW_DB_DIR / "a.db", "Dataset A")
    _split_human_db(
        OLD_DATA_DIR / "fixturedb-human.db", NEW_DB_DIR / "b.db", NEW_DB_DIR / "c.db"
    )
    _plain_copy(OLD_DATA_DIR / "corpus.db", NEW_DB_DIR / "corpus.db", "corpus.db")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
