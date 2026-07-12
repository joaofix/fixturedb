"""Unit tests for scripts/migrate_db_layout.py.

fixturedb-human.db has no column distinguishing Dataset B rows from Dataset C
rows -- the only reliable place they're kept apart is the already-migrated
`datasets/{b,c}/fixtures/*.csv` files. These tests build a small fake
old-style DB with repos from both datasets mixed together and confirm the
split correctly separates them (including dependent fixtures/test_files rows,
not just the repositories table), and that everything here is idempotent.
"""

from __future__ import annotations

import csv
import sqlite3

from collection.db import initialise_db
from scripts.migrate_db_layout import _plain_copy, _split_human_db


def _insert_repo(conn, github_id, full_name, language="python"):
    cursor = conn.execute(
        "INSERT INTO repositories (github_id, full_name, language) VALUES (?, ?, ?)",
        (github_id, full_name, language),
    )
    return cursor.lastrowid


def _insert_test_file(conn, repo_id, relative_path="tests/test_x.py"):
    cursor = conn.execute(
        "INSERT INTO test_files (repo_id, relative_path, language) VALUES (?, ?, 'python')",
        (repo_id, relative_path),
    )
    return cursor.lastrowid


def _insert_fixture(conn, file_id, repo_id, name):
    cursor = conn.execute(
        "INSERT INTO fixtures (file_id, repo_id, name, fixture_type) VALUES (?, ?, ?, 'pytest_decorator')",
        (file_id, repo_id, name),
    )
    return cursor.lastrowid


def _write_fixture_csv(path, repo_names):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["repo_name", "language"])
        for name in repo_names:
            writer.writerow([name, "python"])


class TestPlainCopy:
    def test_copies_when_source_exists_and_dest_missing(self, tmp_path):
        src = tmp_path / "src.db"
        src.write_bytes(b"fake db bytes")
        dst = tmp_path / "sub" / "dst.db"

        _plain_copy(src, dst, "test")

        assert dst.read_bytes() == b"fake db bytes"

    def test_noop_when_source_missing(self, tmp_path):
        dst = tmp_path / "dst.db"
        _plain_copy(tmp_path / "missing.db", dst, "test")
        assert not dst.exists()

    def test_noop_when_dest_already_exists(self, tmp_path):
        src = tmp_path / "src.db"
        src.write_bytes(b"new content")
        dst = tmp_path / "dst.db"
        dst.write_bytes(b"existing content")

        _plain_copy(src, dst, "test")

        assert dst.read_bytes() == b"existing content"


class TestSplitHumanDb:
    def test_splits_repos_and_dependent_rows_by_csv_membership(self, tmp_path):
        old_db = tmp_path / "fixturedb-human.db"
        initialise_db(old_db)
        conn = sqlite3.connect(old_db)
        try:
            b_repo_id = _insert_repo(conn, 1, "owner/b-repo")
            c_repo_id = _insert_repo(conn, 2, "owner/c-repo")

            b_file_id = _insert_test_file(conn, b_repo_id)
            c_file_id = _insert_test_file(conn, c_repo_id)

            _insert_fixture(conn, b_file_id, b_repo_id, "b_fixture")
            _insert_fixture(conn, c_file_id, c_repo_id, "c_fixture")
            conn.commit()
        finally:
            conn.close()

        datasets_root = tmp_path / "datasets"
        _write_fixture_csv(
            datasets_root / "b" / "fixtures" / "python_fixtures.csv", ["owner/b-repo"]
        )
        _write_fixture_csv(
            datasets_root / "c" / "fixtures" / "python_fixtures.csv", ["owner/c-repo"]
        )

        b_dst = tmp_path / "db" / "b.db"
        c_dst = tmp_path / "db" / "c.db"

        import scripts.migrate_db_layout as migrate_mod

        original_datasets_root = migrate_mod.DATASETS_ROOT
        migrate_mod.DATASETS_ROOT = datasets_root
        try:
            _split_human_db(old_db, b_dst, c_dst)
        finally:
            migrate_mod.DATASETS_ROOT = original_datasets_root

        b_conn = sqlite3.connect(b_dst)
        b_conn.row_factory = sqlite3.Row
        try:
            b_repos = b_conn.execute("SELECT full_name FROM repositories").fetchall()
            b_fixtures = b_conn.execute("SELECT name FROM fixtures").fetchall()
        finally:
            b_conn.close()
        assert [r["full_name"] for r in b_repos] == ["owner/b-repo"]
        assert [f["name"] for f in b_fixtures] == ["b_fixture"]

        c_conn = sqlite3.connect(c_dst)
        c_conn.row_factory = sqlite3.Row
        try:
            c_repos = c_conn.execute("SELECT full_name FROM repositories").fetchall()
            c_fixtures = c_conn.execute("SELECT name FROM fixtures").fetchall()
        finally:
            c_conn.close()
        assert [r["full_name"] for r in c_repos] == ["owner/c-repo"]
        assert [f["name"] for f in c_fixtures] == ["c_fixture"]

    def test_noop_when_source_missing(self, tmp_path):
        b_dst = tmp_path / "db" / "b.db"
        c_dst = tmp_path / "db" / "c.db"

        _split_human_db(tmp_path / "missing.db", b_dst, c_dst)

        assert not b_dst.exists()
        assert not c_dst.exists()

    def test_noop_when_dest_already_exists(self, tmp_path):
        old_db = tmp_path / "fixturedb-human.db"
        initialise_db(old_db)

        b_dst = tmp_path / "db" / "b.db"
        b_dst.parent.mkdir(parents=True)
        b_dst.write_bytes(b"already migrated")
        c_dst = tmp_path / "db" / "c.db"

        _split_human_db(old_db, b_dst, c_dst)

        assert b_dst.read_bytes() == b"already migrated"
        assert not c_dst.exists()
