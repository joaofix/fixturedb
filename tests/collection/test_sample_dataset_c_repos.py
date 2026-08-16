"""Real (non-mocked) tests for collection.dataset_pipeline's Dataset C
sample-down: _fetch_dataset_c_repo_fixture_counts(), _build_sampled_db(),
sample_dataset_c_repos(). Builds tiny real SQLite DBs via collection.db's own
writers (upsert_repository/upsert_test_file/insert_fixture/insert_mock_usage)
-- same convention as test_dataset_pipeline.py -- rather than raw SQL or
mocks, since the id-remapping logic this exists to test is exactly what a
mock would hide.
"""

from __future__ import annotations

import json

import pytest

from collection.dataset_pipeline import (
    _build_sampled_db,
    _fetch_dataset_c_repo_fixture_counts,
    _fetch_repo_language_counts_with_fixtures,
    sample_dataset_c_repos,
)
from collection.db import (
    db_session,
    initialise_db,
    insert_fixture,
    insert_mock_usage,
    set_repo_analysed,
    upsert_repository,
    upsert_test_file,
)


def _make_repo_db(path, repos: list[dict]) -> None:
    """repos: [{"github_id": int, "language": str, "num_fixtures": int,
    "mocks_on_fixture_0": int}, ...]. One test_file per repo, `num_fixtures`
    plain fixtures, and (if given) that many mock_usages rows attached to
    the repo's first fixture."""
    initialise_db(path)
    with db_session(path) as conn:
        for spec in repos:
            repo_id, _ = upsert_repository(
                conn,
                {
                    "github_id": spec["github_id"],
                    "full_name": f"owner/repo{spec['github_id']}",
                    "language": spec["language"],
                    "stars": 1,
                    "forks": 0,
                    "description": "",
                    "topics": "[]",
                    "created_at": "2019-01-01T00:00:00Z",
                    "pushed_at": "2020-01-01T00:00:00Z",
                    "clone_url": f"https://github.com/owner/repo{spec['github_id']}.git",
                    "num_contributors": 1,
                    "domain": None,
                    "repo_age_years": None,
                },
            )
            file_id = upsert_test_file(
                conn, repo_id, f"tests/test_{spec['github_id']}.py", spec["language"]
            )
            fixture_ids = []
            for i in range(spec["num_fixtures"]):
                fixture_ids.append(
                    insert_fixture(
                        conn,
                        {
                            "file_id": file_id,
                            "repo_id": repo_id,
                            "name": f"fixture_{i}",
                            "fixture_type": "pytest_decorator",
                            "scope": "per_test",
                            "start_line": i,
                            "end_line": i + 1,
                            "loc": 5,
                            "cyclomatic_complexity": 1,
                            "max_nesting_depth": 1,
                            "num_objects_instantiated": 0,
                            "num_external_calls": 0,
                            "num_comment_lines": 0,
                            "comment_density": 0.0,
                            "num_parameters": 0,
                            "has_teardown_pair": 0,
                            "raw_source": f"def fixture_{i}(): pass",
                            "framework": "pytest",
                            "num_mocks": 0,
                        },
                    )
                )
            num_mocks = spec.get("mocks_on_fixture_0", 0)
            for _ in range(num_mocks):
                insert_mock_usage(
                    conn,
                    {
                        "fixture_id": fixture_ids[0],
                        "repo_id": repo_id,
                        "framework": "unittest_mock",
                        "category": "mock",
                        "target_identifier": "foo",
                        "num_interactions_configured": 1,
                        "raw_snippet": "Mock()",
                    },
                )

            # Mirror what a real collection run does at persist time
            # (persist_repository_and_fixtures() -> set_repo_analysed()) so
            # the denormalized aggregate columns this test suite relies on
            # (num_test_files/num_fixtures/num_mock_usages) are realistic,
            # not left at their schema default of 0.
            set_repo_analysed(
                conn,
                repo_id,
                num_test_files=1,
                num_fixtures=spec["num_fixtures"],
                num_mock_usages=num_mocks,
            )


def _counts(db_path) -> dict[str, int]:
    with db_session(db_path) as conn:
        return {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("repositories", "test_files", "fixtures", "mock_usages")
        }


class TestFetchDatasetCRepoFixtureCounts:
    def test_groups_by_repo_with_own_language_and_count(self, tmp_path):
        db_path = tmp_path / "c.db"
        _make_repo_db(
            db_path,
            [
                {"github_id": 1, "language": "python", "num_fixtures": 3},
                {"github_id": 2, "language": "java", "num_fixtures": 5},
            ],
        )
        with db_session(db_path) as conn:
            rows = _fetch_dataset_c_repo_fixture_counts(conn)

        by_lang = {r["language"]: r for r in rows}
        assert by_lang["python"]["fixture_count"] == 3
        assert by_lang["java"]["fixture_count"] == 5

    def test_repo_with_no_fixtures_excluded(self, tmp_path):
        db_path = tmp_path / "c.db"
        _make_repo_db(db_path, [{"github_id": 1, "language": "python", "num_fixtures": 0}])
        with db_session(db_path) as conn:
            rows = _fetch_dataset_c_repo_fixture_counts(conn)
        assert rows == []


class TestFetchRepoLanguageCountsWithFixtures:
    def test_counts_repos_not_fixtures(self, tmp_path):
        """Two python repos with different fixture counts must each count
        once towards python's repo count -- this is a repo count, not a
        fixture count (that's _fetch_dataset_c_repo_fixture_counts above)."""
        db_path = tmp_path / "a.db"
        _make_repo_db(
            db_path,
            [
                {"github_id": 1, "language": "python", "num_fixtures": 3},
                {"github_id": 2, "language": "python", "num_fixtures": 50},
                {"github_id": 3, "language": "java", "num_fixtures": 1},
            ],
        )
        with db_session(db_path) as conn:
            counts = _fetch_repo_language_counts_with_fixtures(conn)
        assert counts == {"python": 2, "java": 1}

    def test_repo_with_no_fixtures_excluded(self, tmp_path):
        db_path = tmp_path / "a.db"
        _make_repo_db(db_path, [{"github_id": 1, "language": "python", "num_fixtures": 0}])
        with db_session(db_path) as conn:
            counts = _fetch_repo_language_counts_with_fixtures(conn)
        assert counts == {}


class TestBuildSampledDb:
    def test_copies_only_sampled_repos(self, tmp_path):
        source = tmp_path / "c.db"
        _make_repo_db(
            source,
            [
                {"github_id": 1, "language": "python", "num_fixtures": 3},
                {"github_id": 2, "language": "java", "num_fixtures": 5},
            ],
        )
        with db_session(source) as conn:
            repo_ids = {
                row["language"]: row["repo_id"]
                for row in conn.execute(
                    "SELECT id AS repo_id, language FROM repositories"
                ).fetchall()
            }

        output = tmp_path / "c_sampled.db"
        total = _build_sampled_db(source, output, [repo_ids["python"]])

        assert total == 3
        with db_session(output) as conn:
            names = {row["full_name"] for row in conn.execute("SELECT full_name FROM repositories")}
        assert names == {"owner/repo1"}  # only the sampled (python) repo

    def test_remaps_foreign_keys_not_source_ids(self, tmp_path):
        """Source repo/file/fixture ids must not be assumed to equal the
        destination's -- insert extra unsampled repos first so the sampled
        repo's own source id is guaranteed not to be 1, then verify the
        copied fixture's file_id/repo_id in the output db actually point at
        real rows in that same output db, not stale source ids."""
        source = tmp_path / "c.db"
        _make_repo_db(
            source,
            [
                {"github_id": 1, "language": "python", "num_fixtures": 2},
                {"github_id": 2, "language": "python", "num_fixtures": 2},
                {"github_id": 3, "language": "java", "num_fixtures": 4},
            ],
        )
        with db_session(source) as conn:
            java_repo_id = conn.execute(
                "SELECT id FROM repositories WHERE language = 'java'"
            ).fetchone()[0]

        output = tmp_path / "c_sampled.db"
        _build_sampled_db(source, output, [java_repo_id])

        with db_session(output) as conn:
            fixtures = conn.execute("SELECT * FROM fixtures").fetchall()
            assert len(fixtures) == 4
            for fx in fixtures:
                file_row = conn.execute(
                    "SELECT * FROM test_files WHERE id = ?", (fx["file_id"],)
                ).fetchone()
                repo_row = conn.execute(
                    "SELECT * FROM repositories WHERE id = ?", (fx["repo_id"],)
                ).fetchone()
                assert file_row is not None
                assert repo_row is not None
                assert repo_row["full_name"] == "owner/repo3"

    def test_copies_mock_usages_with_remapped_fixture_and_repo_id(self, tmp_path):
        source = tmp_path / "c.db"
        _make_repo_db(
            source,
            [{"github_id": 1, "language": "python", "num_fixtures": 2, "mocks_on_fixture_0": 2}],
        )
        with db_session(source) as conn:
            repo_id = conn.execute("SELECT id FROM repositories").fetchone()[0]

        output = tmp_path / "c_sampled.db"
        _build_sampled_db(source, output, [repo_id])

        with db_session(output) as conn:
            mocks = conn.execute("SELECT * FROM mock_usages").fetchall()
            assert len(mocks) == 2
            fixture_ids = {row["id"] for row in conn.execute("SELECT id FROM fixtures")}
            for m in mocks:
                assert m["fixture_id"] in fixture_ids

    def test_never_writes_to_source_db(self, tmp_path):
        source = tmp_path / "c.db"
        _make_repo_db(
            source,
            [
                {"github_id": 1, "language": "python", "num_fixtures": 3, "mocks_on_fixture_0": 1},
                {"github_id": 2, "language": "java", "num_fixtures": 5},
            ],
        )
        before = _counts(source)

        with db_session(source) as conn:
            repo_ids = [row["id"] for row in conn.execute("SELECT id FROM repositories")]
        _build_sampled_db(source, tmp_path / "c_sampled.db", repo_ids)

        assert _counts(source) == before

    def test_always_fully_rebuilt_not_appended(self, tmp_path):
        source = tmp_path / "c.db"
        _make_repo_db(
            source,
            [
                {"github_id": 1, "language": "python", "num_fixtures": 2},
                {"github_id": 2, "language": "java", "num_fixtures": 2},
            ],
        )
        with db_session(source) as conn:
            repo_ids = {
                row["language"]: row["id"]
                for row in conn.execute("SELECT id, language FROM repositories")
            }

        output = tmp_path / "c_sampled.db"
        _build_sampled_db(source, output, [repo_ids["python"]])
        _build_sampled_db(source, output, [repo_ids["java"]])  # second call, different repo

        with db_session(output) as conn:
            names = {row["full_name"] for row in conn.execute("SELECT full_name FROM repositories")}
        assert names == {"owner/repo2"}  # only java's repo -- python's from the first call is gone

    def test_repo_aggregate_counts_carried_over_unchanged(self, tmp_path):
        """A repo is never partially included, so num_test_files/
        num_fixtures/num_mock_usages should carry over exactly, not be
        recomputed or reset to 0."""
        source = tmp_path / "c.db"
        _make_repo_db(
            source, [{"github_id": 1, "language": "python", "num_fixtures": 4, "mocks_on_fixture_0": 2}]
        )
        with db_session(source) as conn:
            repo_id = conn.execute("SELECT id FROM repositories").fetchone()[0]
            src_repo = dict(
                conn.execute("SELECT * FROM repositories WHERE id = ?", (repo_id,)).fetchone()
            )

        output = tmp_path / "c_sampled.db"
        _build_sampled_db(source, output, [repo_id])

        with db_session(output) as conn:
            dst_repo = dict(conn.execute("SELECT * FROM repositories").fetchone())
        assert dst_repo["num_fixtures"] == src_repo["num_fixtures"] == 4
        assert dst_repo["num_mock_usages"] == src_repo["num_mock_usages"] == 2


class TestSampleDatasetCRepos:
    def test_requires_exactly_one_of_target_count_or_match_dataset(self, tmp_path):
        with pytest.raises(ValueError, match="exactly one"):
            sample_dataset_c_repos(db_root=tmp_path)
        with pytest.raises(ValueError, match="exactly one"):
            sample_dataset_c_repos(target_count=10, match_dataset="a", db_root=tmp_path)

    def test_raises_when_source_c_db_missing(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="extract-fixtures --dataset c"):
            sample_dataset_c_repos(target_count=10, db_root=tmp_path)

    def test_raises_when_match_dataset_db_missing(self, tmp_path):
        _make_repo_db(tmp_path / "c.db", [{"github_id": 1, "language": "python", "num_fixtures": 5}])
        with pytest.raises(FileNotFoundError, match="extract-fixtures --dataset a"):
            sample_dataset_c_repos(match_dataset="a", db_root=tmp_path)

    def test_end_to_end_with_explicit_target_count(self, tmp_path):
        db_root = tmp_path / "db"
        datasets_root = tmp_path / "datasets"
        output_dir = tmp_path / "output"
        _make_repo_db(
            db_root / "c.db",
            [
                {"github_id": i, "language": "python", "num_fixtures": 10} for i in range(1, 11)
            ]
            + [{"github_id": i, "language": "java", "num_fixtures": 10} for i in range(11, 21)],
        )
        c_counts_before = _counts(db_root / "c.db")

        result = sample_dataset_c_repos(
            target_count=50,
            db_root=db_root,
            datasets_root=datasets_root,
            output_dir=output_dir,
        )

        # Source db/c.db is completely untouched.
        assert _counts(db_root / "c.db") == c_counts_before

        assert (db_root / "c_sampled.db").exists()
        assert abs(result["sampled_fixture_count"] - 50) <= 10

        summary_path = output_dir / "sample_c_repos.json"
        assert summary_path.exists()
        summary = json.loads(summary_path.read_text())
        assert summary["target_count"] == 50
        assert summary["sampled_fixture_count"] == result["sampled_fixture_count"]

        csv_dir = datasets_root / "c" / "fixtures-sampled"
        assert csv_dir.exists()
        assert any(csv_dir.glob("*_fixtures.csv"))

    def test_match_dataset_reads_live_fixture_count(self, tmp_path):
        db_root = tmp_path / "db"
        _make_repo_db(
            db_root / "c.db",
            [{"github_id": i, "language": "python", "num_fixtures": 10} for i in range(1, 21)],
        )
        _make_repo_db(
            db_root / "a.db", [{"github_id": 100, "language": "python", "num_fixtures": 37}]
        )

        result = sample_dataset_c_repos(
            match_dataset="a",
            db_root=db_root,
            datasets_root=tmp_path / "datasets",
            output_dir=tmp_path / "output",
        )

        assert result["target_count"] == 37

    def test_match_dataset_stratifies_by_its_own_mix_not_dataset_cs(self, tmp_path):
        """Dataset C's own fixture-count mix here is 50/50 java/python. The
        match dataset (a.db) is 90% python / 10% java *by repo count*. The
        sample must follow a.db's 90/10 mix, not c.db's own 50/50 -- this is
        the whole point of the change."""
        db_root = tmp_path / "db"
        _make_repo_db(
            db_root / "c.db",
            [{"github_id": i, "language": "python", "num_fixtures": 2} for i in range(1, 6)]
            + [{"github_id": i, "language": "java", "num_fixtures": 1} for i in range(6, 16)],
        )
        _make_repo_db(
            db_root / "a.db",
            [{"github_id": i, "language": "python", "num_fixtures": 1} for i in range(100, 109)]
            + [{"github_id": 200, "language": "java", "num_fixtures": 1}],
        )

        result = sample_dataset_c_repos(
            match_dataset="a",
            db_root=db_root,
            datasets_root=tmp_path / "datasets",
            output_dir=tmp_path / "output",
        )

        check = result["distribution_check"]
        assert check["python"]["target_ratio"] == pytest.approx(0.9)
        assert check["java"]["target_ratio"] == pytest.approx(0.1)
        # java's own C-side fixture-count share (50%) must NOT be what it
        # actually got sampled at -- it should track the 10% target instead.
        assert check["java"]["original_ratio"] == pytest.approx(0.5)
        assert check["java"]["sampled_ratio"] < check["java"]["original_ratio"]
        assert check["python"]["sampled_fixture_count"] > check["java"]["sampled_fixture_count"]
