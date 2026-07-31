from __future__ import annotations

import csv
from pathlib import Path

from collection.db import (
    db_session,
    initialise_db,
    insert_fixture,
    insert_mock_usage,
    set_repo_analysed,
    update_test_file_counts,
    upsert_repository,
    upsert_test_file,
)
from collection.dedupe_commits_by_sha import AUDIT_FIELDNAMES
from collection.dedupe_fixtures_by_sha import dedupe_fixtures_and_db


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


FIXTURE_FIELDNAMES = ["repo_name", "language", "commit_sha", "file_path", "fixture_name", "start_line", "loc"]


def _fixture_row(repo_name, commit_sha, fixture_name="fx", start_line="1", loc="5", file_path="tests/test_x.py"):
    return {
        "repo_name": repo_name,
        "language": "python",
        "commit_sha": commit_sha,
        "file_path": file_path,
        "fixture_name": fixture_name,
        "start_line": start_line,
        "loc": loc,
    }


def _seed_db(db_path: Path, *, repo_name: str, github_id: int, stars: int, num_fixtures_rows: list[dict]):
    """Insert one repo plus its fixtures (each dict: file_path, name, start_line, loc, commit_sha),
    with the repo's/file's aggregate columns deliberately overcounted (simulating the
    pre-dedup persisted state), and return (repo_id, {file_path: file_id})."""
    with db_session(db_path) as conn:
        repo_id, _ = upsert_repository(
            conn,
            {
                "github_id": github_id,
                "full_name": repo_name,
                "language": "python",
                "stars": stars,
                "forks": 0,
                "description": "",
                "topics": "[]",
                "created_at": "2020-01-01T00:00:00",
                "pushed_at": "2020-01-01T00:00:00",
                "clone_url": "",
                "domain": "other",
                "repo_age_years": None,
                "num_contributors": 1,
            },
        )
        file_ids: dict[str, int] = {}
        for row in num_fixtures_rows:
            file_path = row["file_path"]
            if file_path not in file_ids:
                file_ids[file_path] = upsert_test_file(conn, repo_id, file_path, "python")
        for row in num_fixtures_rows:
            file_id = file_ids[row["file_path"]]
            insert_fixture(
                conn,
                {
                    "file_id": file_id,
                    "repo_id": repo_id,
                    "name": row["name"],
                    "fixture_type": "pytest_decorator",
                    "scope": "per_test",
                    "start_line": row["start_line"],
                    "end_line": row["start_line"] + 1,
                    "loc": row["loc"],
                    "cyclomatic_complexity": 1,
                    "max_nesting_depth": 0,
                    "num_objects_instantiated": 0,
                    "num_external_calls": 0,
                    "num_parameters": 0,
                    "has_teardown_pair": 0,
                    "raw_source": "def fx(): pass",
                    "framework": "pytest",
                    "num_mocks": 0,
                    "commit_sha": row["commit_sha"],
                    "commit_kind": "human",
                },
            )
        for file_path, file_id in file_ids.items():
            rows_here = [r for r in num_fixtures_rows if r["file_path"] == file_path]
            # Deliberately stale: pretend one extra fixture was counted, matching
            # the real-world scenario of a snapshot column written before dedup ran.
            update_test_file_counts(
                conn, file_id, num_test_funcs=1, num_fixtures=len(rows_here) + 1,
                file_loc=100, total_fixture_loc=sum(r["loc"] for r in rows_here) + 5,
            )
        set_repo_analysed(
            conn, repo_id, num_test_files=len(file_ids),
            num_fixtures=len(num_fixtures_rows) + 1, num_mock_usages=1,
        )
        # A mock usage attached to the first fixture, to verify cascade delete.
        first_fixture_id = conn.execute(
            "SELECT id FROM fixtures WHERE repo_id = ? ORDER BY id LIMIT 1", (repo_id,)
        ).fetchone()["id"]
        insert_mock_usage(
            conn,
            {
                "fixture_id": first_fixture_id,
                "repo_id": repo_id,
                "framework": "unittest_mock",
                "category": "mock",
                "target_identifier": "x",
                "num_interactions_configured": 0,
                "raw_snippet": "",
            },
        )
    return repo_id, file_ids


class TestDedupeFixturesAndDb:
    def test_cross_repo_duplicate_removed_from_csv_and_db(self, tmp_path: Path):
        fixtures_dir = tmp_path / "fixtures"
        repos_dir = tmp_path / "repos"
        db_path = tmp_path / "b.db"
        initialise_db(db_path)

        _write_csv(
            fixtures_dir / "python_fixtures.csv",
            FIXTURE_FIELDNAMES,
            [
                _fixture_row("org/old-name", "shared-sha", fixture_name="fx"),
                _fixture_row("org/new-name", "shared-sha", fixture_name="fx"),
                _fixture_row("org/new-name", "unique-sha", fixture_name="other_fx"),
            ],
        )
        _write_csv(
            repos_dir / "python_repo.csv",
            ["repo_name", "language", "stars", "created_at"],
            [
                {"repo_name": "org/old-name", "language": "python", "stars": "10", "created_at": "2016-01-01"},
                {"repo_name": "org/new-name", "language": "python", "stars": "500", "created_at": "2016-01-01"},
            ],
        )

        old_repo_id, old_files = _seed_db(
            db_path, repo_name="org/old-name", github_id=1, stars=10,
            num_fixtures_rows=[{"file_path": "tests/test_x.py", "name": "fx", "start_line": 1, "loc": 5, "commit_sha": "shared-sha"}],
        )
        new_repo_id, new_files = _seed_db(
            db_path, repo_name="org/new-name", github_id=2, stars=500,
            num_fixtures_rows=[
                {"file_path": "tests/test_x.py", "name": "fx", "start_line": 1, "loc": 5, "commit_sha": "shared-sha"},
                {"file_path": "tests/test_x.py", "name": "other_fx", "start_line": 10, "loc": 3, "commit_sha": "unique-sha"},
            ],
        )

        audit_path = fixtures_dir / "duplicate_fixtures_removed.csv"
        summary = dedupe_fixtures_and_db(
            fixtures_dir, repos_dir, db_path, pattern="*_fixtures.csv", audit_output_path=audit_path
        )

        assert summary["duplicate_rows_removed"] == 1
        assert summary["distinct_duplicate_commits"] == 1
        assert summary["fixtures_deleted"] == 1
        assert summary["mock_usages_deleted"] == 1
        assert summary["repos_resynced"] == 1
        assert summary["files_resynced"] == 1

        with (fixtures_dir / "python_fixtures.csv").open(newline="", encoding="utf-8") as fh:
            remaining = list(csv.DictReader(fh))
        assert len(remaining) == 2
        assert {r["repo_name"] for r in remaining} == {"org/new-name"}

        with audit_path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            assert reader.fieldnames == AUDIT_FIELDNAMES
            audit_rows = list(reader)
        assert len(audit_rows) == 1
        assert audit_rows[0]["repo_removed"] == "org/old-name"
        assert audit_rows[0]["repo_kept"] == "org/new-name"

        with db_session(db_path) as conn:
            # Losing repo's duplicate fixture and its mock usage are gone.
            old_fixtures = conn.execute(
                "SELECT * FROM fixtures WHERE repo_id = ?", (old_repo_id,)
            ).fetchall()
            assert len(old_fixtures) == 0
            old_mocks = conn.execute(
                "SELECT * FROM mock_usages WHERE repo_id = ?", (old_repo_id,)
            ).fetchall()
            assert len(old_mocks) == 0

            # Surviving repo's fixtures (both the duplicate winner and the
            # unrelated unique fixture) are untouched.
            new_fixtures = conn.execute(
                "SELECT name FROM fixtures WHERE repo_id = ?", (new_repo_id,)
            ).fetchall()
            assert {r["name"] for r in new_fixtures} == {"fx", "other_fx"}

            # Losing repo's aggregate columns are re-synced to the real
            # (now zero) count, not left stale at their pre-delete values.
            old_file_row = conn.execute(
                "SELECT num_fixtures, total_fixture_loc FROM test_files WHERE id = ?",
                (old_files["tests/test_x.py"],),
            ).fetchone()
            assert old_file_row["num_fixtures"] == 0
            assert old_file_row["total_fixture_loc"] == 0

            old_repo_row = conn.execute(
                "SELECT num_fixtures, num_mock_usages FROM repositories WHERE id = ?",
                (old_repo_id,),
            ).fetchone()
            assert old_repo_row["num_fixtures"] == 0
            assert old_repo_row["num_mock_usages"] == 0

            # Surviving repo's own (independently stale-seeded) aggregate
            # columns are untouched -- it wasn't part of any cascade delete.
            new_repo_row = conn.execute(
                "SELECT num_fixtures FROM repositories WHERE id = ?", (new_repo_id,)
            ).fetchone()
            assert new_repo_row["num_fixtures"] == 3  # deliberately stale seed value, untouched

    def test_no_duplicates_leaves_csv_and_db_untouched(self, tmp_path: Path):
        fixtures_dir = tmp_path / "fixtures"
        repos_dir = tmp_path / "repos"
        db_path = tmp_path / "b.db"
        initialise_db(db_path)

        _write_csv(
            fixtures_dir / "python_fixtures.csv",
            FIXTURE_FIELDNAMES,
            [_fixture_row("org/a", "sha1")],
        )
        _write_csv(
            repos_dir / "python_repo.csv",
            ["repo_name", "language", "stars", "created_at"],
            [{"repo_name": "org/a", "language": "python", "stars": "1", "created_at": "2020-01-01"}],
        )
        _seed_db(
            db_path, repo_name="org/a", github_id=1, stars=1,
            num_fixtures_rows=[{"file_path": "tests/test_x.py", "name": "fx", "start_line": 1, "loc": 5, "commit_sha": "sha1"}],
        )

        audit_path = fixtures_dir / "duplicate_fixtures_removed.csv"
        summary = dedupe_fixtures_and_db(
            fixtures_dir, repos_dir, db_path, pattern="*_fixtures.csv", audit_output_path=audit_path
        )

        assert summary["duplicate_rows_removed"] == 0
        assert summary["fixtures_deleted"] == 0
        assert not audit_path.exists()

        with db_session(db_path) as conn:
            count = conn.execute("SELECT COUNT(*) AS n FROM fixtures").fetchone()["n"]
        assert count == 1
