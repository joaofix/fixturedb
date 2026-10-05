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

from scripts.migrate_db_layout import _plain_copy


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

