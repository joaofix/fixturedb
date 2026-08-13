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
    set_repo_analysed,
    update_agent_commit_stats,
    upsert_repository,
    upsert_test_file,
)
from collection.research_questions.dataset_findings import (
    RepoPurityStats,
    _fetch_agent_commits_touching_tests,
    _fetch_csv_row_counts,
    _fetch_csv_unique_repo_counts,
    _fetch_mock_commit_counts,
    _fetch_raw_seart_repo_counts,
    _fetch_repos_with_agent_config,
    _fetch_repos_with_fixtures,
    _fetch_repos_with_mocks,
    _fetch_repos_with_test_commits,
    _fetch_total_commits_since_agent_start,
    _render_dataset_a_commit_repo_summary,
    _render_dataset_c_repo_summary,
    _render_dataset_c_sampling_summary,
    _render_language_count_table,
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
    def test_missing_sampled_db_still_renders_csv_sourced_rows(self, tmp_path):
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
        """Confirms the section really goes through the c -> c_sampled.db
        redirect: a repo written to the full c.db must NOT appear."""
        _make_db_with_mock_fixtures(
            paths.db_path("c", root=tmp_path),
            [{"language": "python", "fixtures": [{"num_mocks": 1}]}],
        )
        # Full db/c.db has data, but db/c_sampled.db does not exist --
        # With any fixtures/mocks must still be "not available".
        lines = _render_dataset_c_repo_summary(db_root=tmp_path)
        report = "\n".join(lines)
        assert "| With any fixtures | N/A | N/A | N/A | N/A | N/A |" in report

        # Now write the sampled db instead -- must be picked up.
        _make_db_with_mock_fixtures(
            tmp_path / "c_sampled.db",
            [{"language": "python", "fixtures": [{"num_mocks": 1}]}],
        )
        lines = _render_dataset_c_repo_summary(db_root=tmp_path)
        report = "\n".join(lines)
        assert "| With any fixtures | 0 | 0 | 1 | 0 | 1 |" in report


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
