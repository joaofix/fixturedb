"""Real (non-mocked) tests for collection.dataset_pipeline's Dataset C
sample-down: _fetch_fixture_language_counts(),
_fetch_repo_counts_by_fixture_language(),
_fetch_dataset_c_fixtures_by_own_language(),
_build_sampled_db_from_fixtures(), sample_dataset_c_repos(). Builds tiny
real SQLite DBs via collection.db's own writers
(upsert_repository/upsert_test_file/insert_fixture/insert_mock_usage) --
same convention as test_dataset_pipeline.py -- rather than raw SQL or
mocks, since the id-remapping logic this exists to test is exactly what a
mock would hide.

Fixture-level sampling (not whole-repo, the previous approach) means a
repo's fixtures can now be split across the sample boundary -- several
tests below build repos with a MIX of languages across their own test
files specifically to prove sampling/counting follows each fixture's own
language, not its repo's tag (leakage-aware, matching
research_questions/dataset_findings.py's "Fixture Counts by Language"
table's grouping)."""

from __future__ import annotations

import json

import pytest

from collection.dataset_pipeline import (
    _build_sampled_db_from_fixtures,
    _fetch_dataset_c_fixtures_by_own_language,
    _fetch_fixture_language_counts,
    _fetch_repo_counts_by_fixture_language,
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
    "mocks_on_fixture_0": int, "files": [...]}, ...].

    Default shape (no "files" key): one test_file at the repo's own
    `language`, `num_fixtures` plain fixtures on it, and (if given) that
    many mock_usages rows attached to the repo's first fixture -- same as
    before this suite's fixture-level rewrite.

    `files` (optional) overrides this with an explicit list of
    {"language": str, "num_fixtures": int} entries -- one test_file per
    entry, letting a single repo contribute fixtures in more than one
    language (real leakage), for tests that need to prove grouping is by
    each fixture's own language, not the repo's tag. When given,
    `language`/`num_fixtures`/`mocks_on_fixture_0` are ignored for
    fixture creation (only `language` is still used for the repo's own
    tag)."""
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

            files = spec.get("files") or [
                {
                    "language": spec["language"],
                    "num_fixtures": spec["num_fixtures"],
                }
            ]

            total_fixtures = 0
            total_mocks = 0
            first_fixture_id: int | None = None
            for file_idx, file_spec in enumerate(files):
                file_language = file_spec["language"]
                file_id = upsert_test_file(
                    conn,
                    repo_id,
                    f"tests/test_{spec['github_id']}_{file_idx}.{file_language}",
                    file_language,
                )
                for i in range(file_spec["num_fixtures"]):
                    fixture_id = insert_fixture(
                        conn,
                        {
                            "file_id": file_id,
                            "repo_id": repo_id,
                            "name": f"fixture_{file_idx}_{i}",
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
                            "raw_source": f"def fixture_{file_idx}_{i}(): pass",
                            "framework": "pytest",
                            "num_mocks": 0,
                        },
                    )
                    if first_fixture_id is None:
                        first_fixture_id = fixture_id
                    total_fixtures += 1

            num_mocks = spec.get("mocks_on_fixture_0", 0)
            for _ in range(num_mocks):
                insert_mock_usage(
                    conn,
                    {
                        "fixture_id": first_fixture_id,
                        "repo_id": repo_id,
                        "framework": "unittest_mock",
                        "category": "mock",
                        "target_identifier": "foo",
                        "num_interactions_configured": 1,
                        "raw_snippet": "Mock()",
                    },
                )
                total_mocks += 1

            # Mirror what a real collection run does at persist time
            # (persist_repository_and_fixtures() -> set_repo_analysed()) so
            # the denormalized aggregate columns this test suite relies on
            # are realistic, not left at their schema default of 0.
            set_repo_analysed(
                conn,
                repo_id,
                num_test_files=len(files),
                num_fixtures=total_fixtures,
                num_mock_usages=total_mocks,
            )


def _counts(db_path) -> dict[str, int]:
    with db_session(db_path) as conn:
        return {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("repositories", "test_files", "fixtures", "mock_usages")
        }


class TestFetchFixtureLanguageCounts:
    def test_groups_by_fixture_own_language(self, tmp_path):
        db_path = tmp_path / "c.db"
        _make_repo_db(
            db_path,
            [
                {"github_id": 1, "language": "python", "num_fixtures": 3},
                {"github_id": 2, "language": "java", "num_fixtures": 5},
            ],
        )
        with db_session(db_path) as conn:
            counts = _fetch_fixture_language_counts(conn)
        assert counts == {"python": 3, "java": 5}

    def test_leaked_fixture_counted_under_its_own_language_not_repo_tag(self, tmp_path):
        """A repo tagged python with a leaked javascript test file inside
        it must have that javascript fixture counted under javascript,
        not python -- the whole reason this grouping replaced the old
        repo-tag-based one."""
        db_path = tmp_path / "c.db"
        _make_repo_db(
            db_path,
            [
                {
                    "github_id": 1,
                    "language": "python",
                    "files": [
                        {"language": "python", "num_fixtures": 2},
                        {"language": "javascript", "num_fixtures": 1},
                    ],
                }
            ],
        )
        with db_session(db_path) as conn:
            counts = _fetch_fixture_language_counts(conn)
        assert counts == {"python": 2, "javascript": 1}

    def test_repo_with_no_fixtures_excluded(self, tmp_path):
        db_path = tmp_path / "c.db"
        _make_repo_db(db_path, [{"github_id": 1, "language": "python", "num_fixtures": 0}])
        with db_session(db_path) as conn:
            counts = _fetch_fixture_language_counts(conn)
        assert counts == {}


class TestFetchRepoCountsByFixtureLanguage:
    def test_counts_distinct_repos_not_fixtures(self, tmp_path):
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
            counts = _fetch_repo_counts_by_fixture_language(conn)
        assert counts == {"python": 2, "java": 1}

    def test_single_repo_with_two_languages_counts_once_per_language(self, tmp_path):
        db_path = tmp_path / "c.db"
        _make_repo_db(
            db_path,
            [
                {
                    "github_id": 1,
                    "language": "python",
                    "files": [
                        {"language": "python", "num_fixtures": 2},
                        {"language": "javascript", "num_fixtures": 1},
                    ],
                }
            ],
        )
        with db_session(db_path) as conn:
            counts = _fetch_repo_counts_by_fixture_language(conn)
        assert counts == {"python": 1, "javascript": 1}


class TestFetchDatasetCFixturesByOwnLanguage:
    def test_returns_one_row_per_fixture_with_own_language(self, tmp_path):
        db_path = tmp_path / "c.db"
        _make_repo_db(
            db_path,
            [
                {
                    "github_id": 1,
                    "language": "python",
                    "files": [
                        {"language": "python", "num_fixtures": 2},
                        {"language": "javascript", "num_fixtures": 1},
                    ],
                }
            ],
        )
        with db_session(db_path) as conn:
            rows = _fetch_dataset_c_fixtures_by_own_language(conn)

        by_language: dict[str, int] = {}
        for row in rows:
            by_language[row["language"]] = by_language.get(row["language"], 0) + 1
        assert by_language == {"python": 2, "javascript": 1}
        assert len(rows) == 3


class TestBuildSampledDbFromFixtures:
    def test_copies_only_the_given_fixtures(self, tmp_path):
        source = tmp_path / "c.db"
        _make_repo_db(
            source,
            [
                {"github_id": 1, "language": "python", "num_fixtures": 3},
                {"github_id": 2, "language": "java", "num_fixtures": 5},
            ],
        )
        with db_session(source) as conn:
            python_fixture_ids = [
                row["id"]
                for row in conn.execute(
                    "SELECT f.id FROM fixtures f "
                    "JOIN repositories r ON f.repo_id = r.id "
                    "WHERE r.language = 'python'"
                ).fetchall()
            ]

        output = tmp_path / "c_sampled.db"
        total = _build_sampled_db_from_fixtures(source, output, python_fixture_ids)

        assert total == 3
        with db_session(output) as conn:
            names = {row["full_name"] for row in conn.execute("SELECT full_name FROM repositories")}
        assert names == {"owner/repo1"}

    def test_can_copy_a_partial_subset_of_a_repos_fixtures(self, tmp_path):
        """The core new behavior: unlike the old whole-repo builder, a
        repo can appear in the output with FEWER fixtures than it has in
        the source."""
        source = tmp_path / "c.db"
        _make_repo_db(source, [{"github_id": 1, "language": "python", "num_fixtures": 5}])
        with db_session(source) as conn:
            fixture_ids = [row["id"] for row in conn.execute("SELECT id FROM fixtures").fetchall()]

        output = tmp_path / "c_sampled.db"
        total = _build_sampled_db_from_fixtures(source, output, fixture_ids[:2])

        assert total == 2
        with db_session(output) as conn:
            repo = dict(conn.execute("SELECT * FROM repositories").fetchone())
            fixture_count = conn.execute("SELECT COUNT(*) FROM fixtures").fetchone()[0]
        assert fixture_count == 2
        # Aggregate count recomputed from what was actually copied (2),
        # not carried over from the source repo's real total (5).
        assert repo["num_fixtures"] == 2

    def test_remaps_foreign_keys_not_source_ids(self, tmp_path):
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
            java_fixture_ids = [
                row["id"]
                for row in conn.execute(
                    "SELECT f.id FROM fixtures f "
                    "JOIN repositories r ON f.repo_id = r.id "
                    "WHERE r.language = 'java'"
                ).fetchall()
            ]

        output = tmp_path / "c_sampled.db"
        _build_sampled_db_from_fixtures(source, output, java_fixture_ids)

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

    def test_copies_mock_usages_only_for_sampled_fixtures(self, tmp_path):
        source = tmp_path / "c.db"
        _make_repo_db(
            source,
            [{"github_id": 1, "language": "python", "num_fixtures": 2, "mocks_on_fixture_0": 2}],
        )
        with db_session(source) as conn:
            fixture_ids = [row["id"] for row in conn.execute("SELECT id FROM fixtures ORDER BY id").fetchall()]

        output = tmp_path / "c_sampled.db"
        # Only the fixture WITHOUT mocks -- its mock_usages must not
        # appear in the output at all.
        total = _build_sampled_db_from_fixtures(source, output, [fixture_ids[1]])

        assert total == 1
        with db_session(output) as conn:
            mocks = conn.execute("SELECT * FROM mock_usages").fetchall()
        assert mocks == []

    def test_copies_mock_usages_with_remapped_fixture_and_repo_id(self, tmp_path):
        source = tmp_path / "c.db"
        _make_repo_db(
            source,
            [{"github_id": 1, "language": "python", "num_fixtures": 2, "mocks_on_fixture_0": 2}],
        )
        with db_session(source) as conn:
            fixture_ids = [row["id"] for row in conn.execute("SELECT id FROM fixtures ORDER BY id").fetchall()]

        output = tmp_path / "c_sampled.db"
        _build_sampled_db_from_fixtures(source, output, fixture_ids)

        with db_session(output) as conn:
            mocks = conn.execute("SELECT * FROM mock_usages").fetchall()
            assert len(mocks) == 2
            fixture_ids_out = {row["id"] for row in conn.execute("SELECT id FROM fixtures")}
            for m in mocks:
                assert m["fixture_id"] in fixture_ids_out

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
            fixture_ids = [row["id"] for row in conn.execute("SELECT id FROM fixtures").fetchall()]
        _build_sampled_db_from_fixtures(source, tmp_path / "c_sampled.db", fixture_ids)

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
            fixture_ids = {
                row["language"]: [
                    r["id"]
                    for r in conn.execute(
                        "SELECT f.id FROM fixtures f JOIN repositories r ON f.repo_id = r.id "
                        "WHERE r.language = ?",
                        (row["language"],),
                    ).fetchall()
                ]
                for row in conn.execute("SELECT DISTINCT language FROM repositories").fetchall()
            }

        output = tmp_path / "c_sampled.db"
        _build_sampled_db_from_fixtures(source, output, fixture_ids["python"])
        _build_sampled_db_from_fixtures(source, output, fixture_ids["java"])  # second call

        with db_session(output) as conn:
            names = {row["full_name"] for row in conn.execute("SELECT full_name FROM repositories")}
        assert names == {"owner/repo2"}  # only java's repo -- python's is gone

    def test_empty_fixture_id_list_produces_an_empty_db(self, tmp_path):
        source = tmp_path / "c.db"
        _make_repo_db(source, [{"github_id": 1, "language": "python", "num_fixtures": 2}])

        output = tmp_path / "c_sampled.db"
        total = _build_sampled_db_from_fixtures(source, output, [])

        assert total == 0
        with db_session(output) as conn:
            assert conn.execute("SELECT COUNT(*) FROM repositories").fetchone()[0] == 0


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
            [{"github_id": i, "language": "python", "num_fixtures": 10} for i in range(1, 11)]
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
        # Split 50/50 by Dataset C's own mix, then rounded -- exact for
        # an even population like this one.
        assert result["sampled_fixture_count"] == 50

        summary_path = output_dir / "sample_c_repos.json"
        assert summary_path.exists()
        summary = json.loads(summary_path.read_text())
        assert summary["target_count"] == 50
        assert summary["sampled_fixture_count"] == result["sampled_fixture_count"]

        csv_dir = datasets_root / "c" / "fixtures-sampled"
        assert csv_dir.exists()
        assert any(csv_dir.glob("*_fixtures.csv"))

    def test_match_dataset_reads_live_per_language_fixture_counts(self, tmp_path):
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
        assert result["sampled_fixture_count"] == 37

    def test_matches_exact_per_language_fixture_count_not_approximate(self, tmp_path):
        """The whole point of the change: the old whole-repo sampler could
        only ever land close to a target (repos are indivisible 10-fixture
        chunks here); this must hit it exactly."""
        db_root = tmp_path / "db"
        _make_repo_db(
            db_root / "c.db",
            [{"github_id": i, "language": "python", "num_fixtures": 10} for i in range(1, 21)],
        )
        _make_repo_db(
            db_root / "a.db", [{"github_id": 100, "language": "python", "num_fixtures": 43}]
        )

        result = sample_dataset_c_repos(
            match_dataset="a",
            db_root=db_root,
            datasets_root=tmp_path / "datasets",
            output_dir=tmp_path / "output",
        )

        assert result["sampled_fixture_count"] == 43  # not just "close to"

    def test_uses_fixtures_own_language_not_repo_tag_for_matching(self, tmp_path):
        """Dataset C has a repo tagged python with a leaked javascript
        file inside it. Matching against a's javascript target must be
        able to draw from that leaked fixture -- proving the sample pool
        is grouped by each fixture's own language."""
        db_root = tmp_path / "db"
        _make_repo_db(
            db_root / "c.db",
            [
                {
                    "github_id": 1,
                    "language": "python",
                    "files": [
                        {"language": "python", "num_fixtures": 5},
                        {"language": "javascript", "num_fixtures": 3},
                    ],
                }
            ],
        )
        _make_repo_db(
            db_root / "a.db",
            [{"github_id": 100, "language": "javascript", "num_fixtures": 2}],
        )

        result = sample_dataset_c_repos(
            match_dataset="a",
            db_root=db_root,
            datasets_root=tmp_path / "datasets",
            output_dir=tmp_path / "output",
        )

        assert result["sampled_fixture_count"] == 2
        with db_session(db_root / "c_sampled.db") as conn:
            langs = {
                row["language"]
                for row in conn.execute(
                    "SELECT tf.language FROM fixtures f JOIN test_files tf ON f.file_id = tf.id"
                ).fetchall()
            }
        assert langs == {"javascript"}

    def test_shortfall_language_does_not_affect_other_languages_target(self, tmp_path):
        """Unlike the old whole-repo sampler's cross-language shortfall
        redistribution, a language that can't reach its target here must
        not change any other language's sampled count."""
        db_root = tmp_path / "db"
        _make_repo_db(
            db_root / "c.db",
            [{"github_id": i, "language": "python", "num_fixtures": 5} for i in range(1, 3)]
            + [{"github_id": i, "language": "java", "num_fixtures": 1} for i in range(3, 5)],
        )
        _make_repo_db(
            db_root / "a.db",
            [
                {"github_id": 100, "language": "python", "num_fixtures": 8},
                {"github_id": 101, "language": "java", "num_fixtures": 50},  # c only has 2
            ],
        )

        result = sample_dataset_c_repos(
            match_dataset="a",
            db_root=db_root,
            datasets_root=tmp_path / "datasets",
            output_dir=tmp_path / "output",
        )

        check = result["distribution_check"]
        assert check["python"]["sampled_fixture_count"] == 8
        assert check["python"]["shortfall"] is False
        assert check["java"]["sampled_fixture_count"] == 2  # took everything available
        assert check["java"]["shortfall"] is True

    def test_repos_can_appear_with_a_partial_subset_of_their_fixtures(self, tmp_path):
        db_root = tmp_path / "db"
        _make_repo_db(
            db_root / "c.db",
            [{"github_id": 1, "language": "python", "num_fixtures": 10}],
        )
        _make_repo_db(
            db_root / "a.db", [{"github_id": 100, "language": "python", "num_fixtures": 4}]
        )

        sample_dataset_c_repos(
            match_dataset="a",
            db_root=db_root,
            datasets_root=tmp_path / "datasets",
            output_dir=tmp_path / "output",
        )

        with db_session(db_root / "c_sampled.db") as conn:
            repo = dict(conn.execute("SELECT * FROM repositories").fetchone())
            fixture_count = conn.execute("SELECT COUNT(*) FROM fixtures").fetchone()[0]
        assert fixture_count == 4
        assert repo["num_fixtures"] == 4  # recomputed, not the source's 10
