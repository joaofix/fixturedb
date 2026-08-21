"""Tests for collection/research_questions/dataset_findings.py.

Builds tiny synthetic db/a.db files under tmp_path (via the real schema,
initialise_db() + upsert_repository()/update_agent_commit_stats(), the same
functions agent_corpus.py itself uses to persist these counters) and checks
the loading, aggregation, and report-rendering logic.
"""

from __future__ import annotations

import csv
import gzip
import json

from collection import paths
from collection.db import (
    db_session,
    initialise_db,
    insert_fixture,
    insert_mock_usage,
    set_repo_analysed,
    update_agent_commit_stats,
    upsert_repository,
    upsert_test_file,
)
from collection.research_questions.dataset_findings import (
    RepoPurityStats,
    _fetch_agent_commits_touching_tests,
    _fetch_aliased_mock_import_counts,
    _fetch_csv_row_counts,
    _fetch_csv_unique_repo_counts,
    _fetch_fixture_counts_by_own_language,
    _fetch_js_hook_complexity_mismatch,
    _fetch_junit3_fallback_counts,
    _fetch_mocha_bare_hook_non_bare_count,
    _fetch_mock_category_classification_breakdown,
    _fetch_mock_commit_counts,
    _fetch_raw_seart_repo_counts,
    _fetch_repos_with_agent_config,
    _fetch_repos_with_fixtures,
    _fetch_repos_with_mocks,
    _fetch_repos_with_test_commits,
    _fetch_total_commits_since_agent_start,
    _render_aliased_mock_import_side_note,
    _render_dataset_a_commit_repo_summary,
    _render_dataset_c_repo_summary,
    _render_dataset_c_sampling_summary,
    _render_fixture_counts_by_language_summary,
    _render_js_hook_complexity_side_note,
    _render_junit3_fallback_side_note,
    _render_language_count_table,
    _render_mocha_bare_hook_side_note,
    _render_mock_category_fallback_side_note,
    generate_report,
    load_repo_purity_stats,
    write_report,
)


def _make_db_with_mock_fixtures(db_file, repos: list[dict]) -> None:
    """Create a DB at `db_file` with one repo per entry in `repos`, each
    with one test_file and one fixture per (name, num_mocks, commit_sha) in
    `repos[i]["fixtures"]`. Used for the mock-commit/mock-repo queries,
    which _make_db() above doesn't cover (no fixtures/test_files rows).
    Also accepts `adoption_intensity`/`total_commits_since_agent_start`, so
    a test needing both fixtures and these fields on the same repo doesn't
    need two separate upserts that could clobber each other (same
    github_id -> ON CONFLICT UPDATE -- a field omitted from one call's dict
    overwrites an earlier call's value with NULL).

    Takes an explicit path rather than (root, dataset) -- db/c_sampled.db
    isn't a "real" dataset letter paths.db_path() will accept, so callers
    that need to write there build the path themselves."""
    initialise_db(db_file)
    with db_session(db_file) as conn:
        for i, r in enumerate(repos):
            repo_id, _ = upsert_repository(
                conn,
                {
                    "github_id": i + 1,
                    "full_name": r.get("full_name", f"owner/repo{i}"),
                    "language": r.get("language", "python"),
                    "stars": 1,
                    "forks": 0,
                    "description": "",
                    "topics": "[]",
                    "created_at": "2019-01-01T00:00:00Z",
                    "pushed_at": "2020-01-01T00:00:00Z",
                    "clone_url": f"https://github.com/owner/repo{i}.git",
                    "num_contributors": 1,
                    "domain": None,
                    "repo_age_years": None,
                    "agent_adoption_intensity": r.get("adoption_intensity"),
                    "total_commits_since_agent_start": r.get("total_commits_since_agent_start"),
                },
            )
            file_id = upsert_test_file(conn, repo_id, f"tests/test_{i}.py", r.get("language", "python"))
            for j, fx in enumerate(r.get("fixtures", [])):
                insert_fixture(
                    conn,
                    {
                        "file_id": file_id,
                        "repo_id": repo_id,
                        "name": fx.get("name", f"fixture_{i}_{j}"),
                        "fixture_type": "pytest_decorator",
                        "scope": "per_test",
                        "start_line": j,
                        "end_line": j + 1,
                        "loc": 5,
                        "cyclomatic_complexity": 1,
                        "max_nesting_depth": 1,
                        "num_objects_instantiated": 0,
                        "num_external_calls": 0,
                        "num_comment_lines": 0,
                        "comment_density": 0.0,
                        "num_parameters": 0,
                        "has_teardown_pair": 0,
                        "raw_source": "",
                        "framework": "pytest",
                        "num_mocks": fx.get("num_mocks", 0),
                        "commit_sha": fx.get("commit_sha", f"sha{i}{j}"),
                    },
                )
            # Mirror what a real collection run does at persist time
            # (persist_repository_and_fixtures() -> set_repo_analysed()) so
            # the denormalized repositories.num_fixtures/num_mock_usages
            # columns _fetch_repos_with_fixtures() reads are realistic, not
            # left at their schema default of 0.
            num_mocks_total = sum(1 for fx in r.get("fixtures", []) if fx.get("num_mocks", 0) > 0)
            set_repo_analysed(
                conn,
                repo_id,
                num_test_files=1,
                num_fixtures=len(r.get("fixtures", [])),
                num_mock_usages=num_mocks_total,
            )


def _make_db_with_typed_fixtures(db_file, fixture_types: list[str], *, language="java") -> None:
    """Create a DB at `db_file` with one repo, one test_file, and one
    fixture per entry in `fixture_types` -- used by the JUnit 3 fallback
    side-note tests below, which need specific fixture_type values
    _make_db_with_mock_fixtures() above doesn't support (hardcodes
    "pytest_decorator")."""
    initialise_db(db_file)
    with db_session(db_file) as conn:
        repo_id, _ = upsert_repository(
            conn,
            {
                "github_id": 1,
                "full_name": "owner/repo",
                "language": language,
                "stars": 1,
                "forks": 0,
                "description": "",
                "topics": "[]",
                "created_at": "2019-01-01T00:00:00Z",
                "pushed_at": "2020-01-01T00:00:00Z",
                "clone_url": "https://github.com/owner/repo.git",
                "num_contributors": 1,
                "domain": None,
                "repo_age_years": None,
            },
        )
        file_id = upsert_test_file(conn, repo_id, "src/test/FooTest.java", language)
        for j, fixture_type in enumerate(fixture_types):
            insert_fixture(
                conn,
                {
                    "file_id": file_id,
                    "repo_id": repo_id,
                    "name": f"fixture_{j}",
                    "fixture_type": fixture_type,
                    "scope": "per_test",
                    "start_line": j,
                    "end_line": j + 1,
                    "loc": 1,
                    "cyclomatic_complexity": 1,
                    "max_nesting_depth": 1,
                    "num_objects_instantiated": 0,
                    "num_external_calls": 0,
                    "num_comment_lines": 0,
                    "comment_density": 0.0,
                    "num_parameters": 0,
                    "has_teardown_pair": 0,
                    "raw_source": "",
                    "framework": "junit",
                    "num_mocks": 0,
                },
            )


def _make_db_with_multi_language_files(
    db_file, repo_language: str, files: list[tuple[str, int]]
) -> None:
    """Create a DB at `db_file` with one repo tagged `repo_language`, and
    one test_file per (language, fixture_count) entry in `files` -- lets a
    single repo contribute fixtures in more than one language, i.e. real
    leakage, unlike every other helper in this file which gives a repo
    exactly one test_file at the repo's own language. Used by the
    "Fixture Counts by Language" tests, which must prove the count is
    grouped by each fixture's own language, not its repo's tag -- mirrors
    test_rq1.py::_make_multi_language_db()'s shape (kept local rather than
    imported cross-file, matching this suite's existing convention of each
    test file owning its own DB-building helpers)."""
    initialise_db(db_file)
    with db_session(db_file) as conn:
        repo_id, _ = upsert_repository(
            conn,
            {
                "github_id": 1,
                "full_name": "owner/repo",
                "language": repo_language,
                "stars": 1,
                "forks": 0,
                "description": "",
                "topics": "[]",
                "created_at": "2019-01-01T00:00:00Z",
                "pushed_at": "2020-01-01T00:00:00Z",
                "clone_url": "https://github.com/owner/repo.git",
                "num_contributors": 1,
                "domain": None,
                "repo_age_years": None,
            },
        )
        for file_idx, (language, fixture_count) in enumerate(files):
            file_id = upsert_test_file(
                conn, repo_id, f"tests/test_{file_idx}.{language}", language
            )
            for j in range(fixture_count):
                insert_fixture(
                    conn,
                    {
                        "file_id": file_id,
                        "repo_id": repo_id,
                        "name": f"fixture_{file_idx}_{j}",
                        "fixture_type": "pytest_decorator",
                        "scope": "per_test",
                        "start_line": j,
                        "end_line": j + 1,
                        "loc": 1,
                        "cyclomatic_complexity": 1,
                        "max_nesting_depth": 1,
                        "num_objects_instantiated": 0,
                        "num_external_calls": 0,
                        "num_comment_lines": 0,
                        "comment_density": 0.0,
                        "num_parameters": 0,
                        "has_teardown_pair": 0,
                        "raw_source": "",
                        "framework": "pytest",
                        "num_mocks": 0,
                    },
                )


def _make_db_with_fixture_rows(db_file, fixtures: list[dict], *, language="python") -> None:
    """Create a DB at `db_file` with one repo, one test_file, and one
    fixture per entry in `fixtures` -- each entry may set fixture_type,
    raw_source, cyclomatic_complexity (all default to sensible values
    otherwise). Used by the JS/TS hook complexity, Mocha bare-hook, and
    aliased-mock-import side-note tests, which each need custom
    raw_source/cyclomatic_complexity per fixture --
    _make_db_with_typed_fixtures() above hardcodes both."""
    initialise_db(db_file)
    with db_session(db_file) as conn:
        repo_id, _ = upsert_repository(
            conn,
            {
                "github_id": 1,
                "full_name": "owner/repo",
                "language": language,
                "stars": 1,
                "forks": 0,
                "description": "",
                "topics": "[]",
                "created_at": "2019-01-01T00:00:00Z",
                "pushed_at": "2020-01-01T00:00:00Z",
                "clone_url": "https://github.com/owner/repo.git",
                "num_contributors": 1,
                "domain": None,
                "repo_age_years": None,
            },
        )
        ext = {"python": "py", "javascript": "js", "typescript": "ts"}.get(language, "txt")
        file_id = upsert_test_file(conn, repo_id, f"src/test_{language}.{ext}", language)
        for j, fx in enumerate(fixtures):
            insert_fixture(
                conn,
                {
                    "file_id": file_id,
                    "repo_id": repo_id,
                    "name": fx.get("name", f"fixture_{j}"),
                    "fixture_type": fx["fixture_type"],
                    "scope": fx.get("scope", "per_test"),
                    "start_line": j,
                    "end_line": j + 1,
                    "loc": 1,
                    "cyclomatic_complexity": fx.get("cyclomatic_complexity", 1),
                    "max_nesting_depth": 1,
                    "num_objects_instantiated": 0,
                    "num_external_calls": 0,
                    "num_comment_lines": 0,
                    "comment_density": 0.0,
                    "num_parameters": 0,
                    "has_teardown_pair": 0,
                    "raw_source": fx.get("raw_source", ""),
                    "framework": fx.get("framework", "unittest"),
                    "num_mocks": 0,
                },
            )


def _make_db_with_mock_usage_rows(db_file, fixtures: list[dict]) -> None:
    """Create a DB at `db_file` with one repo, and one test_file per
    distinct language among `fixtures`, each fixture getting a
    mock_usages row per entry in its own "mocks" list. Each fixture dict:
    raw_source, language (default "python"), and mocks: a list of
    {category, raw_snippet, framework} dicts. Used by the mock-category
    fallback-rate tests, which need real mock_usages rows (category +
    raw_snippet) alongside their owning fixture's raw_source --
    _make_db_with_fixture_rows() above doesn't create mock_usages rows at
    all."""
    initialise_db(db_file)
    with db_session(db_file) as conn:
        repo_id, _ = upsert_repository(
            conn,
            {
                "github_id": 1,
                "full_name": "owner/repo",
                "language": "python",
                "stars": 1,
                "forks": 0,
                "description": "",
                "topics": "[]",
                "created_at": "2019-01-01T00:00:00Z",
                "pushed_at": "2020-01-01T00:00:00Z",
                "clone_url": "https://github.com/owner/repo.git",
                "num_contributors": 1,
                "domain": None,
                "repo_age_years": None,
            },
        )
        file_ids: dict[str, int] = {}
        for i, fx in enumerate(fixtures):
            language = fx.get("language", "python")
            ext = {"python": "py", "javascript": "js", "typescript": "ts", "java": "java"}.get(language, "txt")
            if language not in file_ids:
                file_ids[language] = upsert_test_file(conn, repo_id, f"src/test_{language}.{ext}", language)
            file_id = file_ids[language]
            fixture_id = insert_fixture(
                conn,
                {
                    "file_id": file_id,
                    "repo_id": repo_id,
                    "name": fx.get("name", f"fixture_{i}"),
                    "fixture_type": fx.get("fixture_type", "before_each"),
                    "scope": "per_test",
                    "start_line": i,
                    "end_line": i + 1,
                    "loc": 1,
                    "cyclomatic_complexity": 1,
                    "max_nesting_depth": 1,
                    "num_objects_instantiated": 0,
                    "num_external_calls": 0,
                    "num_comment_lines": 0,
                    "comment_density": 0.0,
                    "num_parameters": 0,
                    "has_teardown_pair": 0,
                    "raw_source": fx.get("raw_source", ""),
                    "framework": fx.get("framework", "unittest"),
                    "num_mocks": len(fx.get("mocks", [])),
                },
            )
            for j, mock in enumerate(fx.get("mocks", [])):
                insert_mock_usage(
                    conn,
                    {
                        "fixture_id": fixture_id,
                        "repo_id": repo_id,
                        "framework": mock.get("framework", "unittest_mock"),
                        "category": mock["category"],
                        "target_identifier": mock.get("target_identifier", f"target_{j}"),
                        "num_interactions_configured": 0,
                        "raw_snippet": mock.get("raw_snippet", ""),
                    },
                )


def _write_csv(path, fieldnames, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_gzip_csv(path, fieldnames, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _make_db(root, repos: list[dict]) -> None:
    """Create db/a.db under `root` with one row per entry in `repos`.

    Each dict may set: full_name, language, adoption_intensity, touching,
    rejected, accepted, total_commits_since_agent_start. Missing keys
    default to sensible values.
    """
    db_file = paths.db_path("a", root=root)
    initialise_db(db_file)
    with db_session(db_file) as conn:
        for i, r in enumerate(repos):
            repo_id, _ = upsert_repository(
                conn,
                {
                    "github_id": i + 1,
                    "full_name": r.get("full_name", f"owner/repo{i}"),
                    "language": r.get("language", "python"),
                    "stars": 1,
                    "forks": 0,
                    "description": "",
                    "topics": "[]",
                    "created_at": "2019-01-01T00:00:00Z",
                    "pushed_at": "2020-01-01T00:00:00Z",
                    "clone_url": f"https://github.com/owner/repo{i}.git",
                    "num_contributors": 1,
                    "domain": None,
                    "repo_age_years": None,
                    "agent_adoption_intensity": r.get("adoption_intensity"),
                    "total_commits_since_agent_start": r.get("total_commits_since_agent_start"),
                },
            )
            update_agent_commit_stats(
                conn,
                repo_id,
                {
                    "agent_commits_touching_tests": r.get("touching", 0),
                    "rejected_mixed_test_diff": r.get("rejected", 0),
                    "accepted": r.get("accepted", 0),
                },
            )


class TestLoadRepoPurityStats:
    def test_missing_db_returns_none(self, tmp_path):
        assert load_repo_purity_stats(db_root=tmp_path) is None

    def test_loads_per_repo_counters(self, tmp_path):
        _make_db(
            tmp_path,
            [
                {
                    "full_name": "owner/repo0",
                    "language": "python",
                    "adoption_intensity": "pervasive",
                    "touching": 10,
                    "rejected": 4,
                    "accepted": 6,
                }
            ],
        )
        stats = load_repo_purity_stats(db_root=tmp_path)
        assert len(stats) == 1
        s = stats[0]
        assert isinstance(s, RepoPurityStats)
        assert s.full_name == "owner/repo0"
        assert s.language == "python"
        assert s.adoption_intensity == "pervasive"
        assert s.touching_tests == 10
        assert s.rejected == 4
        assert s.accepted == 6
        assert s.unclassified == 0
        assert s.rejection_rate == 0.4

    def test_includes_repos_with_zero_touching_tests(self, tmp_path):
        _make_db(tmp_path, [{"full_name": "owner/idle", "touching": 0, "rejected": 0, "accepted": 0}])
        stats = load_repo_purity_stats(db_root=tmp_path)
        assert len(stats) == 1
        assert stats[0].touching_tests == 0
        assert stats[0].rejection_rate is None  # 0/0 is undefined, not 0%

    def test_unclassified_commits_computed_from_residual(self, tmp_path):
        # A per-commit extraction exception leaves a commit counted in
        # touching_tests but classified as neither accepted nor rejected.
        _make_db(tmp_path, [{"touching": 10, "rejected": 3, "accepted": 5}])
        stats = load_repo_purity_stats(db_root=tmp_path)
        assert stats[0].unclassified == 2

    def test_missing_adoption_intensity_stays_none(self, tmp_path):
        _make_db(tmp_path, [{"touching": 1, "rejected": 0, "accepted": 1}])
        stats = load_repo_purity_stats(db_root=tmp_path)
        assert stats[0].adoption_intensity is None


class TestGenerateReportPurityGateSection:
    def test_missing_db_notes_unavailable_without_crashing(self, tmp_path):
        report = generate_report(
            db_root=tmp_path,
            # Isolated, nonexistent dirs -- without this, the new Commits/
            # Repositories summary section falls back to the *real*
            # github-search-raw/ and datasets/ directories on disk, which
            # these older tests (predating that section) never anticipated.
            datasets_root=tmp_path / "unused-datasets",
            raw_search_dir=tmp_path / "unused-raw",
        )
        assert "Not available -- db/a.db not collected yet." in report

    def test_no_repositories_notes_unavailable_without_crashing(self, tmp_path):
        initialise_db(paths.db_path("a", root=tmp_path))
        report = generate_report(
            db_root=tmp_path,
            # Isolated, nonexistent dirs -- without this, the new Commits/
            # Repositories summary section falls back to the *real*
            # github-search-raw/ and datasets/ directories on disk, which
            # these older tests (predating that section) never anticipated.
            datasets_root=tmp_path / "unused-datasets",
            raw_search_dir=tmp_path / "unused-raw",
        )
        assert "Dataset A has no repositories recorded yet." in report

    def test_overall_totals_aggregate_across_repos(self, tmp_path):
        _make_db(
            tmp_path,
            [
                {"touching": 10, "rejected": 4, "accepted": 6},
                {"touching": 20, "rejected": 6, "accepted": 14},
            ],
        )
        report = generate_report(
            db_root=tmp_path,
            # Isolated, nonexistent dirs -- without this, the new Commits/
            # Repositories summary section falls back to the *real*
            # github-search-raw/ and datasets/ directories on disk, which
            # these older tests (predating that section) never anticipated.
            datasets_root=tmp_path / "unused-datasets",
            raw_search_dir=tmp_path / "unused-raw",
        )
        totals_section = report.split("### Overall")[1].split("### By language")[0]
        # 30 touching, 10 rejected, 20 accepted, 0 unclassified, 33.33% rejection rate.
        assert "| 30 | 20 | 10 | 0 | 33.33% |" in totals_section
        assert "2/2 repos had >=1 agent commit touching a test file." in totals_section

    def test_by_language_breakdown(self, tmp_path):
        _make_db(
            tmp_path,
            [
                {"language": "python", "touching": 10, "rejected": 2, "accepted": 8},
                {"language": "java", "touching": 10, "rejected": 8, "accepted": 2},
            ],
        )
        report = generate_report(
            db_root=tmp_path,
            # Isolated, nonexistent dirs -- without this, the new Commits/
            # Repositories summary section falls back to the *real*
            # github-search-raw/ and datasets/ directories on disk, which
            # these older tests (predating that section) never anticipated.
            datasets_root=tmp_path / "unused-datasets",
            raw_search_dir=tmp_path / "unused-raw",
        )
        lang_section = report.split("### By language")[1].split("### By agent adoption intensity")[0]
        assert "| python | 1 | 10 | 2 | 20.00% |" in lang_section
        assert "| java | 1 | 10 | 8 | 80.00% |" in lang_section

    def test_by_adoption_intensity_breakdown_buckets_missing_as_not_set(self, tmp_path):
        _make_db(
            tmp_path,
            [
                {"adoption_intensity": "pervasive", "touching": 10, "rejected": 1, "accepted": 9},
                {"adoption_intensity": None, "touching": 10, "rejected": 9, "accepted": 1},
            ],
        )
        report = generate_report(
            db_root=tmp_path,
            # Isolated, nonexistent dirs -- without this, the new Commits/
            # Repositories summary section falls back to the *real*
            # github-search-raw/ and datasets/ directories on disk, which
            # these older tests (predating that section) never anticipated.
            datasets_root=tmp_path / "unused-datasets",
            raw_search_dir=tmp_path / "unused-raw",
        )
        adoption_section = report.split("### By agent adoption intensity")[1].split(
            "### Per-repo distribution"
        )[0]
        assert "| pervasive | 1 | 10 | 1 | 10.00% |" in adoption_section
        assert "| (not set) | 1 | 10 | 9 | 90.00% |" in adoption_section

    def test_per_repo_distribution_flags_fully_rejected_and_fully_accepted(self, tmp_path):
        _make_db(
            tmp_path,
            [
                {"touching": 5, "rejected": 5, "accepted": 0},  # fully rejected
                {"touching": 5, "rejected": 0, "accepted": 5},  # fully accepted
                {"touching": 0, "rejected": 0, "accepted": 0},  # idle, excluded from distribution
            ],
        )
        report = generate_report(
            db_root=tmp_path,
            # Isolated, nonexistent dirs -- without this, the new Commits/
            # Repositories summary section falls back to the *real*
            # github-search-raw/ and datasets/ directories on disk, which
            # these older tests (predating that section) never anticipated.
            datasets_root=tmp_path / "unused-datasets",
            raw_search_dir=tmp_path / "unused-raw",
        )
        dist_section = report.split("### Per-repo distribution")[1].split(
            "## Agent Adoption Intensity"
        )[0]
        # Only the 2 active repos (touching>0) count toward the distribution.
        assert "| 2 |" in dist_section
        assert "| 1 | 1 |" in dist_section  # 1 repo at 0%, 1 repo at 100%


class TestGenerateReportAdoptionIntensitySection:
    def test_distribution_across_buckets_in_canonical_order(self, tmp_path):
        _make_db(
            tmp_path,
            [
                {"adoption_intensity": "pervasive"},
                {"adoption_intensity": "pervasive"},
                {"adoption_intensity": "experimental"},
                {"adoption_intensity": "no_commits"},
            ],
        )
        report = generate_report(
            db_root=tmp_path,
            # Isolated, nonexistent dirs -- without this, the new Commits/
            # Repositories summary section falls back to the *real*
            # github-search-raw/ and datasets/ directories on disk, which
            # these older tests (predating that section) never anticipated.
            datasets_root=tmp_path / "unused-datasets",
            raw_search_dir=tmp_path / "unused-raw",
        )
        section = report.split("## Agent Adoption Intensity")[1].split(
            "### Funnel and adoption intensity by language"
        )[0]
        table_rows = [
            line
            for line in section.splitlines()
            if line.startswith("|") and "Bucket" not in line and "---" not in line
        ]
        # no_commits, experimental, ..., pervasive canonical order -- not
        # insertion or alphabetical order.
        labels = [row.split("|")[1].strip() for row in table_rows]
        assert labels == ["no_commits", "experimental", "pervasive"]

    def test_percentages_are_of_whole_repo_pool_not_just_active_repos(self, tmp_path):
        _make_db(
            tmp_path,
            [
                {"adoption_intensity": "pervasive", "touching": 10, "rejected": 1, "accepted": 9},
                {"adoption_intensity": "no_commits"},
                {"adoption_intensity": "no_commits"},
                {"adoption_intensity": "no_commits"},
            ],
        )
        report = generate_report(
            db_root=tmp_path,
            # Isolated, nonexistent dirs -- without this, the new Commits/
            # Repositories summary section falls back to the *real*
            # github-search-raw/ and datasets/ directories on disk, which
            # these older tests (predating that section) never anticipated.
            datasets_root=tmp_path / "unused-datasets",
            raw_search_dir=tmp_path / "unused-raw",
        )
        section = report.split("## Agent Adoption Intensity")[1]
        # 1/4 repos pervasive = 25.00%, 3/4 no_commits = 75.00%.
        assert "| pervasive | 1 | 25.00% |" in section
        assert "| no_commits | 3 | 75.00% |" in section

    def test_repos_that_never_reached_the_scan_bucket_as_not_set(self, tmp_path):
        _make_db(tmp_path, [{"adoption_intensity": None}])
        report = generate_report(
            db_root=tmp_path,
            # Isolated, nonexistent dirs -- without this, the new Commits/
            # Repositories summary section falls back to the *real*
            # github-search-raw/ and datasets/ directories on disk, which
            # these older tests (predating that section) never anticipated.
            datasets_root=tmp_path / "unused-datasets",
            raw_search_dir=tmp_path / "unused-raw",
        )
        section = report.split("## Agent Adoption Intensity")[1]
        assert "| (not set) | 1 | 100.00% |" in section

    _BY_LANGUAGE_REPOS = [
        {"language": "python", "adoption_intensity": "pervasive"},
        {"language": "python", "adoption_intensity": "experimental"},
        {"language": "python", "adoption_intensity": "no_commits"},
        {"language": "java", "adoption_intensity": "limited"},
        {"language": "java", "adoption_intensity": "limited"},
    ]

    def _funnel_section(self, report: str) -> str:
        return report.split("### Funnel and adoption intensity by language")[1]

    def test_funnel_table_has_config_no_commits_and_adopted_total(self, tmp_path):
        """Agent Configuration Present is the row's full repo count; No
        commits and the tiers each report their share of it (so those
        percentages sum to 100%); Agent Active Total is Agent Configuration
        Present minus No commits. Language names and column headers match
        the paper's table wording exactly (Java/Python/etc, not the raw
        lowercase DB values). java: 2 repos, both limited -> Config=2,
        No commits=0, Limited=2 (100%), Total=2. python: 3 repos, one each
        of pervasive/experimental/no_commits -> Config=3, No commits=1
        (33.33%), Total=2 (the two adopted repos)."""
        _make_db(tmp_path, self._BY_LANGUAGE_REPOS)
        report = generate_report(
            db_root=tmp_path,
            # Isolated, nonexistent dirs -- without this, the new Commits/
            # Repositories summary section falls back to the *real*
            # github-search-raw/ and datasets/ directories on disk, which
            # these older tests (predating that section) never anticipated.
            datasets_root=tmp_path / "unused-datasets",
            raw_search_dir=tmp_path / "unused-raw",
        )
        section = self._funnel_section(report)

        assert (
            "| Language | Agent Configuration Present | No commits | Experimental "
            "| Limited | Pervasive | Agent Active Total |"
            in section
        )
        assert (
            "| Java | 2 | 0 (0.00%) | 0 (0.00%) | 2 (100.00%) | 0 (0.00%) | 2 |"
            in section
        )
        assert (
            "| Python | 3 | 1 (33.33%) | 1 (33.33%) | 0 (0.00%) | 1 (33.33%) | 2 |"
            in section
        )
        assert (
            "| **Total (All Languages)** | 5 | 1 (20.00%) | 1 (20.00%) | 2 (40.00%) "
            "| 1 (20.00%) | 4 |"
            in section
        )

    def test_funnel_table_omits_tiers_no_repo_uses(self, tmp_path):
        """Only Pervasive/No commits are ever assigned -- Consistent/Limited/
        Experimental columns must not appear at all, matching the overall
        table's same behavior."""
        _make_db(
            tmp_path,
            [
                {"language": "python", "adoption_intensity": "pervasive"},
                {"language": "python", "adoption_intensity": "no_commits"},
            ],
        )
        report = generate_report(
            db_root=tmp_path,
            # Isolated, nonexistent dirs -- without this, the new Commits/
            # Repositories summary section falls back to the *real*
            # github-search-raw/ and datasets/ directories on disk, which
            # these older tests (predating that section) never anticipated.
            datasets_root=tmp_path / "unused-datasets",
            raw_search_dir=tmp_path / "unused-raw",
        )
        section = self._funnel_section(report)

        assert (
            "| Language | Agent Configuration Present | No commits | Pervasive "
            "| Agent Active Total |"
            in section
        )
        for absent in ("Experimental", "Limited", "Consistent"):
            assert absent not in section

    def test_funnel_table_keeps_not_set_out_of_total(self, tmp_path):
        """None (adoption_intensity never computed, e.g. a failed clone)
        means "unknown," not "confirmed zero" -- it gets its own "(not set)"
        column and, like No commits, is excluded from Agent Active Total
        (only repos confirmed to have >=1 agent commit count toward it)."""
        _make_db(
            tmp_path,
            [
                {"language": "python", "adoption_intensity": "no_commits"},
                {"language": "python", "adoption_intensity": None},
                {"language": "python", "adoption_intensity": "pervasive"},
            ],
        )
        report = generate_report(
            db_root=tmp_path,
            # Isolated, nonexistent dirs -- without this, the new Commits/
            # Repositories summary section falls back to the *real*
            # github-search-raw/ and datasets/ directories on disk, which
            # these older tests (predating that section) never anticipated.
            datasets_root=tmp_path / "unused-datasets",
            raw_search_dir=tmp_path / "unused-raw",
        )
        section = self._funnel_section(report)

        assert "(not set)" in section
        # Config=3, No commits=1 (33.33%), (not set)=1 (33.33%),
        # pervasive=1 (33.33%), Total=1 (just the pervasive repo).
        assert (
            "| Python | 3 | 1 (33.33%) | 1 (33.33%) | 1 (33.33%) | 1 |" in section
        )


class TestWriteReport:
    def test_writes_file_matching_generate_report(self, tmp_path):
        _make_db(tmp_path, [{"touching": 4, "rejected": 1, "accepted": 3}])
        out_dir = tmp_path / "out"
        # Isolate datasets_root/raw_search_dir too -- without this, the new
        # Commits/Repositories summary section falls back to the *real*
        # github-search-raw/ and datasets/ directories (whatever's on disk
        # in this environment), which is both a real-data leak into a unit
        # test and, at real-world size, slow enough to make the report's
        # embedded timestamp drift between the two calls below.
        datasets_root = tmp_path / "datasets"
        raw_search_dir = tmp_path / "raw"
        path = write_report(
            out_dir, db_root=tmp_path, datasets_root=datasets_root, raw_search_dir=raw_search_dir
        )
        assert path == out_dir / "dataset_findings.md"
        assert path.read_text() == generate_report(
            db_root=tmp_path, datasets_root=datasets_root, raw_search_dir=raw_search_dir
        )


class TestFetchHelpers:
    """The new data-fetching helpers behind the Commits/Repositories summary
    tables, tested directly against tiny real CSVs/gzip files/DBs -- one
    assertion per helper, not the full rendered report."""

    def test_raw_seart_repo_counts(self, tmp_path):
        raw_dir = tmp_path / "raw"
        _write_gzip_csv(
            raw_dir / "python.csv.gz",
            ["id", "name"],
            [{"id": "1", "name": "o/r1"}, {"id": "2", "name": "o/r2"}],
        )
        _write_gzip_csv(raw_dir / "java.csv.gz", ["id", "name"], [{"id": "3", "name": "o/r3"}])

        counts = _fetch_raw_seart_repo_counts(raw_dir)

        assert counts == {"python": 2, "java": 1}

    def test_raw_seart_repo_counts_missing_dir_returns_none(self, tmp_path):
        assert _fetch_raw_seart_repo_counts(tmp_path / "does-not-exist") is None

    def test_csv_row_counts(self, tmp_path):
        csv_dir = tmp_path / "commits"
        _write_csv(
            csv_dir / "python_commit.csv",
            ["repo_name", "commit_sha"],
            [{"repo_name": "o/r1", "commit_sha": "a"}, {"repo_name": "o/r1", "commit_sha": "b"}],
        )
        _write_csv(csv_dir / "java_commit.csv", ["repo_name", "commit_sha"], [{"repo_name": "o/r2", "commit_sha": "c"}])

        counts = _fetch_csv_row_counts(csv_dir, "_commit.csv")

        assert counts == {"python": 2, "java": 1}

    def test_csv_row_counts_missing_dir_returns_none(self, tmp_path):
        assert _fetch_csv_row_counts(tmp_path / "does-not-exist", "_commit.csv") is None

    def test_csv_unique_repo_counts_dedupes_by_repo_name(self, tmp_path):
        csv_dir = tmp_path / "commits"
        _write_csv(
            csv_dir / "python_commit.csv",
            ["repo_name", "commit_sha"],
            [
                {"repo_name": "o/r1", "commit_sha": "a"},
                {"repo_name": "o/r1", "commit_sha": "b"},  # same repo, 2nd commit
                {"repo_name": "o/r2", "commit_sha": "c"},
            ],
        )

        counts = _fetch_csv_unique_repo_counts(csv_dir, "_commit.csv")

        assert counts == {"python": 2}  # 2 unique repos, not 3 rows

    def test_agent_commits_touching_tests_sums_per_language(self, tmp_path):
        _make_db(
            tmp_path,
            [
                {"language": "python", "touching": 10},
                {"language": "python", "touching": 5},
                {"language": "java", "touching": 3},
            ],
        )
        with db_session(paths.db_path("a", root=tmp_path)) as conn:
            assert _fetch_agent_commits_touching_tests(conn) == {"python": 15, "java": 3}

    def test_repos_with_test_commits_counts_only_nonzero(self, tmp_path):
        _make_db(
            tmp_path,
            [
                {"language": "python", "touching": 1},
                {"language": "python", "touching": 0},
            ],
        )
        with db_session(paths.db_path("a", root=tmp_path)) as conn:
            assert _fetch_repos_with_test_commits(conn) == {"python": 1}

    def test_total_commits_since_agent_start_sums_and_excludes_null(self, tmp_path):
        _make_db(
            tmp_path,
            [
                {"language": "python", "total_commits_since_agent_start": 100},
                {"language": "python", "total_commits_since_agent_start": 50},
                {"language": "java", "total_commits_since_agent_start": 7},
                # Not yet backfilled -- must be excluded from the sum, not
                # counted as 0.
                {"language": "java", "total_commits_since_agent_start": None},
            ],
        )
        with db_session(paths.db_path("a", root=tmp_path)) as conn:
            assert _fetch_total_commits_since_agent_start(conn) == {"python": 150, "java": 7}

    def test_total_commits_since_agent_start_returns_none_on_stale_schema(self, tmp_path):
        """A db/a.db collected before this column existed (and not yet
        self-healed by running backfill_total_commits.py) must degrade to
        None -- same "N/A" treatment as any other missing input -- rather
        than crash the whole report with sqlite3.OperationalError."""
        import sqlite3

        db_path = tmp_path / "stale.db"
        conn = sqlite3.connect(db_path)
        conn.execute(
            "CREATE TABLE repositories (id INTEGER PRIMARY KEY, github_id INTEGER, "
            "full_name TEXT, language TEXT)"
        )
        conn.execute(
            "INSERT INTO repositories (github_id, full_name, language) "
            "VALUES (1, 'owner/prehistoric', 'python')"
        )
        conn.commit()
        conn.close()

        with db_session(db_path) as conn:
            assert _fetch_total_commits_since_agent_start(conn) is None

    def test_repos_with_agent_config_requires_adoption_intensity_set(self, tmp_path):
        _make_db(
            tmp_path,
            [
                {"language": "python", "adoption_intensity": "pervasive"},
                {"language": "python", "adoption_intensity": None},
            ],
        )
        with db_session(paths.db_path("a", root=tmp_path)) as conn:
            assert _fetch_repos_with_agent_config(conn) == {"python": 1}

    def test_mock_commit_counts_distinct_commit_sha(self, tmp_path):
        _make_db_with_mock_fixtures(
            paths.db_path("a", root=tmp_path),
            [
                {
                    "language": "python",
                    "fixtures": [
                        {"name": "f1", "num_mocks": 1, "commit_sha": "sha1"},
                        {"name": "f2", "num_mocks": 2, "commit_sha": "sha1"},  # same commit, 2nd mock fixture
                        {"name": "f3", "num_mocks": 0, "commit_sha": "sha2"},  # no mocks
                    ],
                }
            ],
        )
        with db_session(paths.db_path("a", root=tmp_path)) as conn:
            assert _fetch_mock_commit_counts(conn) == {"python": 1}  # sha1 only, once

    def test_repos_with_mocks(self, tmp_path):
        _make_db_with_mock_fixtures(
            paths.db_path("a", root=tmp_path),
            [
                {"language": "python", "fixtures": [{"num_mocks": 1}]},
                {"language": "python", "fixtures": [{"num_mocks": 0}]},
                {"language": "java", "fixtures": [{"num_mocks": 3}]},
            ],
        )
        with db_session(paths.db_path("a", root=tmp_path)) as conn:
            assert _fetch_repos_with_mocks(conn) == {"python": 1, "java": 1}

    def test_repos_with_fixtures_dataset_c(self, tmp_path):
        _make_db_with_mock_fixtures(
            paths.db_path("c", root=tmp_path),
            [
                {"language": "python", "fixtures": [{"num_mocks": 0}]},
                {"language": "java", "fixtures": []},  # no fixtures at all
            ],
        )
        with db_session(paths.db_path("c", root=tmp_path)) as conn:
            # python has 1 fixture (num_fixtures synced by set_repo_analysed());
            # java has none inserted at all, so num_fixtures stays at its
            # schema default of 0 -- must be excluded.
            assert _fetch_repos_with_fixtures(conn) == {"python": 1}


class TestRenderLanguageCountTable:
    def test_renders_counts_and_computed_total(self):
        table = _render_language_count_table(
            "Commits",
            [("Agent commits", {"java": 1, "javascript": 2, "python": 3, "typescript": 4})],
        )
        assert "| Commits | Java | JavaScript | Python | TypeScript | Total |" in table
        assert "| Agent commits | 1 | 2 | 3 | 4 | 10 |" in table

    def test_none_row_renders_as_na_across_every_column(self):
        table = _render_language_count_table("Commits", [("All commits", None)])
        assert "| All commits | N/A | N/A | N/A | N/A | N/A |" in table

    def test_missing_language_defaults_to_zero(self):
        table = _render_language_count_table("Commits", [("Agent commits", {"python": 5})])
        # Column order is java/javascript/python/typescript/total.
        assert "| Agent commits | 0 | 0 | 5 | 0 | 5 |" in table


class TestDatasetASummarySection:
    def test_missing_db_notes_unavailable(self, tmp_path):
        lines = _render_dataset_a_commit_repo_summary(db_root=tmp_path)
        assert "_Not available -- db/a.db not collected yet._" in lines

    def test_renders_real_counts_end_to_end(self, tmp_path):
        _make_db(
            tmp_path,
            [
                {
                    "language": "python",
                    "touching": 5,
                    "rejected": 2,
                    "accepted": 3,
                    "total_commits_since_agent_start": 42,
                }
            ],
        )
        _make_db_with_mock_fixtures(
            paths.db_path("a", root=tmp_path),
            [
                {
                    "language": "python",
                    "fixtures": [{"num_mocks": 1, "commit_sha": "s1"}],
                    "total_commits_since_agent_start": 42,
                }
            ],
        )
        _write_csv(
            tmp_path / "datasets" / "a" / "commits" / "python_commit.csv",
            ["repo_name", "commit_sha"],
            [{"repo_name": "o/r0", "commit_sha": "s1"}],
        )
        _write_gzip_csv(
            tmp_path / "raw" / "python.csv.gz", ["id", "name"], [{"id": "1", "name": "o/r0"}]
        )

        lines = _render_dataset_a_commit_repo_summary(
            db_root=tmp_path, datasets_root=tmp_path / "datasets", raw_search_dir=tmp_path / "raw"
        )
        report = "\n".join(lines)

        assert "| All commits | 0 | 0 | 42 | 0 | 42 |" in report
        assert "| Agent commits | 0 | 0 | 1 | 0 | 1 |" in report
        assert "| Test commits | 0 | 0 | 5 | 0 | 5 |" in report
        assert "| Mock commits | 0 | 0 | 1 | 0 | 1 |" in report
        assert "| Candidate repos | 0 | 0 | 1 | 0 | 1 |" in report
        assert "| With agent commits | 0 | 0 | 1 | 0 | 1 |" in report

    def test_all_commits_excludes_not_yet_backfilled_repos(self, tmp_path):
        """A repo whose total_commits_since_agent_start is still NULL (not
        yet backfilled) must not poison the sum or silently read as 0."""
        _make_db(
            tmp_path,
            [{"language": "python", "total_commits_since_agent_start": None}],
        )

        lines = _render_dataset_a_commit_repo_summary(
            db_root=tmp_path,
            datasets_root=tmp_path / "datasets",
            raw_search_dir=tmp_path / "raw",
        )
        report = "\n".join(lines)

        # No python entry at all in the SUM(...) GROUP BY result -> the
        # language column falls back to the table renderer's own 0 default,
        # same as any other language with no matching row.
        assert "| All commits | 0 | 0 | 0 | 0 | 0 |" in report


class TestDatasetCSummarySection:
    def test_missing_db_still_renders_csv_sourced_rows(self, tmp_path):
        """Candidate repos/Created within 2016-2020 come from collection
        CSVs, unaffected by whether db/c_sampled.db exists -- only the
        fixture/mock rows should degrade to N/A."""
        _write_gzip_csv(
            tmp_path / "raw" / "python.csv.gz", ["id", "name"], [{"id": "1", "name": "o/r0"}]
        )
        _write_csv(
            tmp_path / "datasets" / "c" / "repos" / "python_repo.csv",
            ["repo_name", "language"],
            [{"repo_name": "o/r0", "language": "python"}],
        )

        lines = _render_dataset_c_repo_summary(
            db_root=tmp_path, datasets_root=tmp_path / "datasets", raw_search_dir=tmp_path / "raw"
        )
        report = "\n".join(lines)

        assert "| Candidate repos | 0 | 0 | 1 | 0 | 1 |" in report
        assert "| Created within 2016-2020 | 0 | 0 | 1 | 0 | 1 |" in report
        assert "| With any fixtures | N/A | N/A | N/A | N/A | N/A |" in report
        assert "| With any mocks | N/A | N/A | N/A | N/A | N/A |" in report

    def test_reads_sampled_db_not_full_db(self, tmp_path):
        """A repo written to db/c_sampled.db must be picked up directly,
        and a full db/c.db existing alongside it must not matter at all
        (not read, not preferred)."""
        _make_db_with_mock_fixtures(
            tmp_path / "c_sampled.db",
            [{"language": "python", "fixtures": [{"num_mocks": 1}]}],
        )
        # db/c_sampled.db has data -- must be picked up directly.
        lines = _render_dataset_c_repo_summary(db_root=tmp_path)
        report = "\n".join(lines)
        assert "| With any fixtures | 0 | 0 | 1 | 0 | 1 |" in report

        # A full db/c.db (the unsampled corpus) existing alongside it must
        # not change anything -- it's never read here.
        _make_db_with_mock_fixtures(
            paths.db_path("c", root=tmp_path),
            [{"language": "python", "fixtures": [{"num_mocks": 5}]}],
        )
        lines = _render_dataset_c_repo_summary(db_root=tmp_path)
        report = "\n".join(lines)
        assert "| With any fixtures | 0 | 0 | 1 | 0 | 1 |" in report


class TestFixtureCountsByLanguageSection:
    """The new "Fixture Counts by Language" table -- total fixtures per
    language, per dataset, grouped by each fixture's own detected
    language rather than its repo's tag. See
    _fetch_fixture_counts_by_own_language()'s docstring for why that
    distinction matters."""

    def test_fetch_groups_by_fixtures_own_language_not_repo_tag(self, tmp_path):
        """The core regression this whole section exists to prevent: a
        repo tagged python with a leaked javascript test file inside it
        must NOT have that javascript fixture counted under python."""
        db_file = tmp_path / "a.db"
        _make_db_with_multi_language_files(
            db_file, repo_language="python", files=[("python", 2), ("javascript", 1)]
        )

        with db_session(db_file) as conn:
            counts = _fetch_fixture_counts_by_own_language(conn)

        assert counts == {"python": 2, "javascript": 1}

    def test_renders_both_datasets_with_totals(self, tmp_path):
        _make_db_with_multi_language_files(
            paths.db_path("a", root=tmp_path), repo_language="python", files=[("python", 3)]
        )
        _make_db_with_multi_language_files(
            tmp_path / "c_sampled.db",
            repo_language="java",
            files=[("java", 5), ("typescript", 2)],
        )

        lines = _render_fixture_counts_by_language_summary(db_root=tmp_path)
        report = "\n".join(lines)

        assert "## Fixture Counts by Language" in report
        assert "| Dataset A (agent-authored) | 0 | 0 | 3 | 0 | 3 |" in report
        assert "| Dataset C (human-authored, pre-LLM) | 5 | 0 | 0 | 2 | 7 |" in report

    def test_missing_dataset_db_degrades_to_na_row(self, tmp_path):
        """Dataset A present, Dataset C not collected yet -- C's row must
        degrade to N/A, A's row must still render real numbers."""
        _make_db_with_multi_language_files(
            paths.db_path("a", root=tmp_path), repo_language="python", files=[("python", 1)]
        )

        lines = _render_fixture_counts_by_language_summary(db_root=tmp_path)
        report = "\n".join(lines)

        assert "| Dataset A (agent-authored) | 0 | 0 | 1 | 0 | 1 |" in report
        assert (
            "| Dataset C (human-authored, pre-LLM) | N/A | N/A | N/A | N/A | N/A |" in report
        )


class TestGenerateReportIncludesNewSections:
    def test_dataset_c_section_renders_even_when_dataset_a_db_missing(self, tmp_path):
        """The old early-return (db/a.db missing -> stop rendering
        entirely) must no longer swallow the Dataset C section."""
        _write_gzip_csv(
            tmp_path / "raw" / "python.csv.gz", ["id", "name"], [{"id": "1", "name": "o/r0"}]
        )
        report = generate_report(
            db_root=tmp_path, datasets_root=tmp_path / "datasets", raw_search_dir=tmp_path / "raw"
        )
        assert "_Not available -- db/a.db not collected yet._" in report
        assert "## Dataset C: Repository Summary" in report
        assert "| Candidate repos | 0 | 0 | 1 | 0 | 1 |" in report

    def test_fixture_counts_by_language_section_included(self, tmp_path):
        _make_db_with_multi_language_files(
            tmp_path / "c_sampled.db", repo_language="python", files=[("python", 2)]
        )
        report = generate_report(
            db_root=tmp_path, datasets_root=tmp_path / "datasets", raw_search_dir=tmp_path / "raw"
        )
        assert "## Fixture Counts by Language" in report
        assert "| Dataset C (human-authored, pre-LLM) | 0 | 0 | 2 | 0 | 2 |" in report


class TestDatasetCSamplingSummarySection:
    def test_not_available_when_summary_file_missing(self, tmp_path):
        lines = _render_dataset_c_sampling_summary(output_dir=tmp_path / "output")
        report = "\n".join(lines)
        assert "## Dataset C: Sampling-Down Summary" in report
        assert "_Not available -- run `python -m collection sample-c-repos" in report

    def test_renders_per_language_table_from_summary_json(self, tmp_path):
        output_dir = tmp_path / "output"
        output_dir.mkdir(parents=True)
        summary = {
            "match_dataset": "a",
            "target_count": 100,
            "sampled_fixture_count": 99,
            "sampled_repo_count": 12,
            "random_seed": 42,
            "distribution_check": {
                "python": {
                    "original_ratio": 0.5,
                    "target_ratio": 0.9,
                    "sampled_ratio": 0.89,
                    "deviation": 0.01,
                    "tolerance_met": True,
                    "dataset_c_available_fixture_count": 500,
                    "dataset_c_available_repo_count": 50,
                    "sampled_fixture_count": 88,
                    "sampled_repo_count": 10,
                },
                "java": {
                    "original_ratio": 0.5,
                    "target_ratio": 0.1,
                    "sampled_ratio": 0.11,
                    "deviation": 0.01,
                    "tolerance_met": True,
                    "dataset_c_available_fixture_count": 11,
                    "dataset_c_available_repo_count": 11,
                    "sampled_fixture_count": 11,
                    "sampled_repo_count": 11,
                },
            },
        }
        (output_dir / "sample_c_repos.json").write_text(json.dumps(summary))

        lines = _render_dataset_c_sampling_summary(output_dir=output_dir)
        report = "\n".join(lines)

        assert "Matched against Dataset a: 99/100 fixtures, 12 repos, seed=42." in report
        assert "| Python | 50.0% | 90.0% | 89.0% | 10/50 | 88/500 |" in report
        # java sampled all 11/11 available repos -- must show the "(all)"
        # shortfall marker.
        assert "| Java | 50.0% | 10.0% | 11.0% | 11/11 (all) | 11/11 |" in report
        # javascript/typescript weren't in distribution_check at all --
        # must still render as N/A rows, not be silently omitted.
        assert "| JavaScript | N/A | N/A | N/A | N/A | N/A |" in report
        assert "| TypeScript | N/A | N/A | N/A | N/A | N/A |" in report

    def test_generate_report_includes_sampling_summary_section(self, tmp_path):
        output_dir = tmp_path / "output"
        output_dir.mkdir(parents=True)
        (output_dir / "sample_c_repos.json").write_text(
            json.dumps(
                {
                    "match_dataset": "a",
                    "target_count": 10,
                    "sampled_fixture_count": 10,
                    "sampled_repo_count": 2,
                    "random_seed": 42,
                    "distribution_check": {},
                }
            )
        )
        report = generate_report(
            db_root=tmp_path,
            datasets_root=tmp_path / "datasets",
            raw_search_dir=tmp_path / "raw",
            sample_output_dir=output_dir,
        )
        assert "## Dataset C: Sampling-Down Summary" in report
        assert "Matched against Dataset a: 10/10 fixtures, 2 repos, seed=42." in report


class TestJunit3FallbackCounts:
    def test_fetch_counts_both_types(self, tmp_path):
        db_file = paths.db_path("a", root=tmp_path)
        _make_db_with_typed_fixtures(
            db_file, ["junit3_setup", "junit3_setup", "junit3_teardown", "before_each"]
        )
        with db_session(db_file) as conn:
            assert _fetch_junit3_fallback_counts(conn) == {
                "junit3_setup": 2,
                "junit3_teardown": 1,
            }

    def test_fetch_counts_missing_type_absent_from_dict(self, tmp_path):
        db_file = paths.db_path("a", root=tmp_path)
        _make_db_with_typed_fixtures(db_file, ["junit3_setup"])
        with db_session(db_file) as conn:
            counts = _fetch_junit3_fallback_counts(conn)
            assert counts == {"junit3_setup": 1}
            assert "junit3_teardown" not in counts

    def test_fetch_counts_no_matching_fixtures_returns_empty_dict(self, tmp_path):
        db_file = paths.db_path("a", root=tmp_path)
        _make_db_with_typed_fixtures(db_file, ["before_each", "after_each"])
        with db_session(db_file) as conn:
            assert _fetch_junit3_fallback_counts(conn) == {}


class TestJunit3FallbackSideNote:
    def test_missing_dbs_render_na_row(self, tmp_path):
        lines = _render_junit3_fallback_side_note(db_root=tmp_path)
        report = "\n".join(lines)
        assert "## JUnit 3 Fallback Detection (Java)" in report
        assert "| Dataset A | N/A | N/A | N/A |" in report
        assert "| Dataset C | N/A | N/A | N/A |" in report

    def test_renders_counts_for_each_db_independently(self, tmp_path):
        # Dataset A: 1 setup only.
        _make_db_with_typed_fixtures(paths.db_path("a", root=tmp_path), ["junit3_setup"])
        # Dataset C: db/c_sampled.db, read directly.
        _make_db_with_typed_fixtures(
            tmp_path / "c_sampled.db",
            ["junit3_setup"] * 3 + ["junit3_teardown"] * 2,
        )
        # A full db/c.db (the unsampled corpus) must not be read or
        # confused with the row above.
        _make_db_with_typed_fixtures(
            paths.db_path("c", root=tmp_path), ["junit3_setup", "junit3_teardown"]
        )

        report = "\n".join(_render_junit3_fallback_side_note(db_root=tmp_path))

        assert "| Dataset A | 1 | 0 | 1 |" in report
        assert "| Dataset C | 3 | 2 | 5 |" in report

    def test_generate_report_includes_junit3_side_note(self, tmp_path):
        report = generate_report(
            db_root=tmp_path, datasets_root=tmp_path / "datasets", raw_search_dir=tmp_path / "raw"
        )
        assert "## JUnit 3 Fallback Detection (Java)" in report


# Exact snippets/expected values re-used across the JS/TS hook complexity
# tests below -- verified directly against _true_outer_hook_complexity()
# before being hardcoded here: raw_simple has no nested construct at all;
# raw_nested_matching has a nested closure but both it and the true outer
# function are cc=1 (so a recorded cc=1 isn't actually wrong); raw_nested_
# mismatch has a branch-free nested closure (cc=1) *and* real branching in
# the outer hook itself (true cc=2) -- the exact failure shape documented
# in js-ts-hook-fixture-complexity.md.
_JS_HOOK_RAW_SIMPLE = "beforeEach(() => {\n  client = new APIClient();\n})"
_JS_HOOK_RAW_NESTED_MATCHING = (
    "beforeEach(() => {\n"
    "    mockApiFetch.mockImplementation(() => {\n"
    "      return {};\n"
    "    });\n"
    "  })"
)
_JS_HOOK_RAW_NESTED_MISMATCH = (
    "beforeEach(() => {\n"
    "    mockApiFetch.mockImplementation((path) => {\n"
    "      return jsonOk({});\n"
    "    });\n"
    "    if (config.auth) {\n"
    "      client.setAuth();\n"
    "    } else {\n"
    "      client.reset();\n"
    "    }\n"
    "  })"
)


class TestJsHookComplexityMismatch:
    def test_no_nested_construct_not_checked(self, tmp_path):
        db_file = paths.db_path("a", root=tmp_path)
        _make_db_with_fixture_rows(
            db_file,
            [{"fixture_type": "before_each", "raw_source": _JS_HOOK_RAW_SIMPLE, "cyclomatic_complexity": 1}],
            language="javascript",
        )
        with db_session(db_file) as conn:
            result = _fetch_js_hook_complexity_mismatch(conn)
        assert result == {"total": 1, "nested_construct": 0, "checked": 0, "mismatched": 0}

    def test_nested_construct_with_correct_recorded_cc_not_mismatched(self, tmp_path):
        db_file = paths.db_path("a", root=tmp_path)
        _make_db_with_fixture_rows(
            db_file,
            [
                {
                    "fixture_type": "before_each",
                    "raw_source": _JS_HOOK_RAW_NESTED_MATCHING,
                    "cyclomatic_complexity": 1,  # matches the true outer cc (1)
                }
            ],
            language="javascript",
        )
        with db_session(db_file) as conn:
            result = _fetch_js_hook_complexity_mismatch(conn)
        assert result == {"total": 1, "nested_construct": 1, "checked": 1, "mismatched": 0}

    def test_nested_construct_with_wrong_recorded_cc_flagged(self, tmp_path):
        db_file = paths.db_path("a", root=tmp_path)
        _make_db_with_fixture_rows(
            db_file,
            [
                {
                    "fixture_type": "after_each",
                    "raw_source": _JS_HOOK_RAW_NESTED_MISMATCH,
                    # Simulates what the real pipeline recorded: function_list[0]
                    # picked the inner branch-free closure (cc=1), silently
                    # missing the outer hook's real if/else (true cc=2).
                    "cyclomatic_complexity": 1,
                }
            ],
            language="javascript",
        )
        with db_session(db_file) as conn:
            result = _fetch_js_hook_complexity_mismatch(conn)
        assert result == {"total": 1, "nested_construct": 1, "checked": 1, "mismatched": 1}

    def test_other_fixture_types_excluded(self, tmp_path):
        db_file = paths.db_path("a", root=tmp_path)
        _make_db_with_fixture_rows(
            db_file,
            [{"fixture_type": "before_all", "raw_source": _JS_HOOK_RAW_NESTED_MISMATCH, "cyclomatic_complexity": 1}],
            language="javascript",
        )
        with db_session(db_file) as conn:
            result = _fetch_js_hook_complexity_mismatch(conn)
        assert result == {"total": 0, "nested_construct": 0, "checked": 0, "mismatched": 0}


class TestJsHookComplexitySideNote:
    def test_missing_dbs_render_na_row(self, tmp_path):
        report = "\n".join(_render_js_hook_complexity_side_note(db_root=tmp_path))
        assert "## JS/TS Hook Fixture Complexity (Lizard `function_list` Selection)" in report
        assert "| Dataset A | N/A | N/A | N/A | N/A | N/A |" in report
        assert "| Dataset C | N/A | N/A | N/A | N/A | N/A |" in report

    def test_renders_real_mismatch_rate(self, tmp_path):
        _make_db_with_fixture_rows(
            paths.db_path("a", root=tmp_path),
            [{"fixture_type": "before_each", "raw_source": _JS_HOOK_RAW_NESTED_MISMATCH, "cyclomatic_complexity": 1}],
            language="javascript",
        )
        report = "\n".join(_render_js_hook_complexity_side_note(db_root=tmp_path))
        assert "| Dataset A | 1 | 1 | 1 | 1 | 100.00% |" in report

    def test_generate_report_includes_js_hook_side_note(self, tmp_path):
        report = generate_report(
            db_root=tmp_path, datasets_root=tmp_path / "datasets", raw_search_dir=tmp_path / "raw"
        )
        assert "## JS/TS Hook Fixture Complexity (Lizard `function_list` Selection)" in report


class TestMochaBareHookNonBareCount:
    def test_bare_calls_all_zero_non_bare(self, tmp_path):
        db_file = paths.db_path("a", root=tmp_path)
        _make_db_with_fixture_rows(
            db_file,
            [
                {"fixture_type": "mocha_before", "raw_source": "before(() => { client = setup(); })"},
                {"fixture_type": "mocha_after", "raw_source": "after(() => { client.close(); })"},
            ],
            language="javascript",
        )
        with db_session(db_file) as conn:
            result = _fetch_mocha_bare_hook_non_bare_count(conn)
        assert result == {"total": 2, "non_bare": 0}

    def test_member_expression_shape_flagged(self, tmp_path):
        """A hypothetical future regression: raw_source captured a
        member-expression call (page.after(...)) instead of a bare one --
        the false-positive shape mocha-before-after-detection.md found
        structurally impossible today. This proves the guard would catch
        it if that guarantee ever broke."""
        db_file = paths.db_path("a", root=tmp_path)
        _make_db_with_fixture_rows(
            db_file,
            [{"fixture_type": "mocha_after", "raw_source": "page.after(() => { page.close(); })"}],
            language="javascript",
        )
        with db_session(db_file) as conn:
            result = _fetch_mocha_bare_hook_non_bare_count(conn)
        assert result == {"total": 1, "non_bare": 1}

    def test_other_fixture_types_excluded(self, tmp_path):
        db_file = paths.db_path("a", root=tmp_path)
        _make_db_with_fixture_rows(
            db_file,
            [{"fixture_type": "before_each", "raw_source": "page.beforeEach(() => {})"}],
            language="javascript",
        )
        with db_session(db_file) as conn:
            result = _fetch_mocha_bare_hook_non_bare_count(conn)
        assert result == {"total": 0, "non_bare": 0}


class TestMochaBareHookSideNote:
    def test_missing_dbs_render_na_row(self, tmp_path):
        report = "\n".join(_render_mocha_bare_hook_side_note(db_root=tmp_path))
        assert "## Mocha Bare `before()`/`after()` Detection (Regression Guard)" in report
        assert "| Dataset A | N/A | N/A |" in report
        assert "| Dataset C | N/A | N/A |" in report

    def test_renders_real_counts(self, tmp_path):
        _make_db_with_fixture_rows(
            paths.db_path("a", root=tmp_path),
            [{"fixture_type": "mocha_before", "raw_source": "before(() => {})"}],
            language="javascript",
        )
        report = "\n".join(_render_mocha_bare_hook_side_note(db_root=tmp_path))
        assert "| Dataset A | 1 | 0 |" in report

    def test_generate_report_includes_mocha_side_note(self, tmp_path):
        report = generate_report(
            db_root=tmp_path, datasets_root=tmp_path / "datasets", raw_search_dir=tmp_path / "raw"
        )
        assert "## Mocha Bare `before()`/`after()` Detection (Regression Guard)" in report


class TestAliasedMockImportCounts:
    def test_no_alias_zero(self, tmp_path):
        db_file = paths.db_path("a", root=tmp_path)
        _make_db_with_fixture_rows(
            db_file,
            [
                {
                    "fixture_type": "unittest_setup",
                    "raw_source": "def setUp(self):\n    from unittest.mock import Mock\n    self.m = Mock()",
                }
            ],
            language="python",
        )
        with db_session(db_file) as conn:
            result = _fetch_aliased_mock_import_counts(conn)
        assert result == {"total_python_fixtures": 1, "aliased_in_body": 0}

    def test_class_level_alias_in_body_detected(self, tmp_path):
        db_file = paths.db_path("a", root=tmp_path)
        _make_db_with_fixture_rows(
            db_file,
            [
                {
                    "fixture_type": "unittest_setup",
                    "raw_source": "def setUp(self):\n    from unittest.mock import patch as p\n    self.p = p",
                }
            ],
            language="python",
        )
        with db_session(db_file) as conn:
            result = _fetch_aliased_mock_import_counts(conn)
        assert result == {"total_python_fixtures": 1, "aliased_in_body": 1}

    def test_module_level_alias_not_flagged(self, tmp_path):
        """import unittest.mock as mock (aliasing the module, not the
        class/function) is not the risky pattern -- see
        aliased-mock-import-prevalence.md §5 -- so it must not be counted
        here."""
        db_file = paths.db_path("a", root=tmp_path)
        _make_db_with_fixture_rows(
            db_file,
            [
                {
                    "fixture_type": "unittest_setup",
                    "raw_source": "def setUp(self):\n    import unittest.mock as mock\n    self.m = mock.MagicMock()",
                }
            ],
            language="python",
        )
        with db_session(db_file) as conn:
            result = _fetch_aliased_mock_import_counts(conn)
        assert result == {"total_python_fixtures": 1, "aliased_in_body": 0}

    def test_non_python_fixtures_excluded(self, tmp_path):
        db_file = paths.db_path("a", root=tmp_path)
        _make_db_with_fixture_rows(
            db_file,
            [{"fixture_type": "before_each", "raw_source": "beforeEach(() => {})"}],
            language="javascript",
        )
        with db_session(db_file) as conn:
            result = _fetch_aliased_mock_import_counts(conn)
        assert result == {"total_python_fixtures": 0, "aliased_in_body": 0}


class TestAliasedMockImportSideNote:
    def test_missing_dbs_render_na_row(self, tmp_path):
        report = "\n".join(_render_aliased_mock_import_side_note(db_root=tmp_path))
        assert "## Aliased Mock Import Detection (Python)" in report
        assert "| Dataset A | N/A | N/A |" in report
        assert "| Dataset C | N/A | N/A |" in report

    def test_renders_real_counts(self, tmp_path):
        _make_db_with_fixture_rows(
            paths.db_path("a", root=tmp_path),
            [
                {
                    "fixture_type": "unittest_setup",
                    "raw_source": "def setUp(self):\n    from unittest.mock import MagicMock as MM",
                }
            ],
            language="python",
        )
        report = "\n".join(_render_aliased_mock_import_side_note(db_root=tmp_path))
        assert "| Dataset A | 1 | 1 |" in report

    def test_generate_report_includes_aliased_mock_side_note(self, tmp_path):
        report = generate_report(
            db_root=tmp_path, datasets_root=tmp_path / "datasets", raw_search_dir=tmp_path / "raw"
        )
        assert "## Aliased Mock Import Detection (Python)" in report


class TestMockCategoryClassificationBreakdown:
    def test_api_name_match_bucketed_correctly(self, tmp_path):
        db_file = tmp_path / "solo.db"
        _make_db_with_mock_usage_rows(
            db_file,
            [
                {
                    "raw_source": "def fixture():\n    m = MagicMock()\n    return m",
                    "mocks": [{"category": "mock", "raw_snippet": "m = MagicMock()"}],
                }
            ],
        )
        with db_session(db_file) as conn:
            result = _fetch_mock_category_classification_breakdown(conn)
        assert result["total"] == 1
        assert result["api_name"] == 1
        assert result["naming_only"] == 0
        assert result["fallback"] == 0

    def test_naming_only_match_bucketed_correctly(self, tmp_path):
        db_file = tmp_path / "solo.db"
        _make_db_with_mock_usage_rows(
            db_file,
            [
                {
                    "language": "typescript",
                    "raw_source": "beforeEach(() => {\n  mockClient = vi.fn();\n})",
                    # The matched call site itself (vi.fn()) is keyword-free --
                    # only "mockClient" elsewhere in the body supplies "mock".
                    "mocks": [{"category": "mock", "raw_snippet": "vi.fn()"}],
                }
            ],
        )
        with db_session(db_file) as conn:
            result = _fetch_mock_category_classification_breakdown(conn)
        assert result["total"] == 1
        assert result["api_name"] == 0
        assert result["naming_only"] == 1
        assert result["fallback"] == 0

    def test_true_fallback_bucketed_correctly(self, tmp_path):
        db_file = tmp_path / "solo.db"
        _make_db_with_mock_usage_rows(
            db_file,
            [
                {
                    "raw_source": "def disable_llm(monkeypatch):\n    monkeypatch.setattr('x.y', lambda: False)",
                    "mocks": [{"category": "mock", "raw_snippet": "monkeypatch.setattr('x.y', lambda: False)"}],
                }
            ],
        )
        with db_session(db_file) as conn:
            result = _fetch_mock_category_classification_breakdown(conn)
        assert result["total"] == 1
        assert result["api_name"] == 0
        assert result["naming_only"] == 0
        assert result["fallback"] == 1

    def test_non_mock_categories_excluded(self, tmp_path):
        db_file = tmp_path / "solo.db"
        _make_db_with_mock_usage_rows(
            db_file,
            [
                {
                    "raw_source": "def fixture():\n    s = stub_thing()",
                    "mocks": [{"category": "stub", "raw_snippet": "stub_thing()"}],
                }
            ],
        )
        with db_session(db_file) as conn:
            result = _fetch_mock_category_classification_breakdown(conn)
        assert result == {"total": 0, "api_name": 0, "naming_only": 0, "fallback": 0, "by_language": {}}

    def test_per_language_breakdown_matches_pooled(self, tmp_path):
        db_file = tmp_path / "solo.db"
        _make_db_with_mock_usage_rows(
            db_file,
            [
                {
                    "language": "python",
                    "raw_source": "def fixture():\n    m = MagicMock()",
                    "mocks": [{"category": "mock", "raw_snippet": "MagicMock()"}],
                },
                {
                    "language": "typescript",
                    "raw_source": "def disable(monkeypatch):\n    monkeypatch.setattr('a', 1)",
                    "mocks": [{"category": "mock", "raw_snippet": "monkeypatch.setattr('a', 1)"}],
                },
            ],
        )
        with db_session(db_file) as conn:
            result = _fetch_mock_category_classification_breakdown(conn)
        assert result["total"] == 2
        assert result["by_language"]["python"] == {
            "total": 1, "api_name": 1, "naming_only": 0, "fallback": 0,
        }
        assert result["by_language"]["typescript"] == {
            "total": 1, "api_name": 0, "naming_only": 0, "fallback": 1,
        }


class TestMockCategoryFallbackSideNote:
    def test_missing_dbs_render_na(self, tmp_path):
        report = "\n".join(_render_mock_category_fallback_side_note(db_root=tmp_path))
        assert "## Mock-Category Fallback Rate" in report
        assert "| Dataset A | N/A | N/A | N/A | N/A |" in report
        assert "| Dataset C | N/A | N/A | N/A | N/A |" in report

    def test_renders_headline_percentages_in_paper_citable_format(self, tmp_path):
        # 3 positive (api_name) + 2 fallback = 5 total -> 60.0% / 40.0%,
        # a round number chosen specifically so the rendered string is
        # unambiguous to assert on.
        db_file = paths.db_path("a", root=tmp_path)
        _make_db_with_mock_usage_rows(
            db_file,
            [
                {"raw_source": "m = MagicMock()", "mocks": [{"category": "mock", "raw_snippet": "MagicMock()"}]},
                {"raw_source": "m = MagicMock()", "mocks": [{"category": "mock", "raw_snippet": "MagicMock()"}]},
                {"raw_source": "m = MagicMock()", "mocks": [{"category": "mock", "raw_snippet": "MagicMock()"}]},
                {
                    "raw_source": "monkeypatch.setattr('a', 1)",
                    "mocks": [{"category": "mock", "raw_snippet": "monkeypatch.setattr('a', 1)"}],
                },
                {
                    "raw_source": "monkeypatch.setattr('b', 2)",
                    "mocks": [{"category": "mock", "raw_snippet": "monkeypatch.setattr('b', 2)"}],
                },
            ],
        )
        report = "\n".join(_render_mock_category_fallback_side_note(db_root=tmp_path))
        assert "| Dataset A | 5 | 3 | 2 | 60.0% / 40.0% |" in report

    def test_generate_report_includes_mock_category_fallback_side_note(self, tmp_path):
        report = generate_report(
            db_root=tmp_path, datasets_root=tmp_path / "datasets", raw_search_dir=tmp_path / "raw"
        )
        assert "## Mock-Category Fallback Rate" in report
