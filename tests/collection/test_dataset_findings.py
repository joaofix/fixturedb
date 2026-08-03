"""Tests for collection/research_questions/dataset_findings.py.

Builds tiny synthetic db/a.db files under tmp_path (via the real schema,
initialise_db() + upsert_repository()/update_agent_commit_stats(), the same
functions agent_corpus.py itself uses to persist these counters) and checks
the loading, aggregation, and report-rendering logic.
"""

from __future__ import annotations

from collection import paths
from collection.db import (
    db_session,
    initialise_db,
    update_agent_commit_stats,
    upsert_repository,
)
from collection.research_questions.dataset_findings import (
    RepoPurityStats,
    generate_report,
    load_repo_purity_stats,
    write_report,
)


def _make_db(root, repos: list[dict]) -> None:
    """Create db/a.db under `root` with one row per entry in `repos`.

    Each dict may set: full_name, language, adoption_intensity, touching,
    rejected, accepted. Missing keys default to sensible values.
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
        report = generate_report(db_root=tmp_path)
        assert "Not available -- db/a.db not collected yet." in report

    def test_no_repositories_notes_unavailable_without_crashing(self, tmp_path):
        initialise_db(paths.db_path("a", root=tmp_path))
        report = generate_report(db_root=tmp_path)
        assert "Dataset A has no repositories recorded yet." in report

    def test_overall_totals_aggregate_across_repos(self, tmp_path):
        _make_db(
            tmp_path,
            [
                {"touching": 10, "rejected": 4, "accepted": 6},
                {"touching": 20, "rejected": 6, "accepted": 14},
            ],
        )
        report = generate_report(db_root=tmp_path)
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
        report = generate_report(db_root=tmp_path)
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
        report = generate_report(db_root=tmp_path)
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
        report = generate_report(db_root=tmp_path)
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
        report = generate_report(db_root=tmp_path)
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
        report = generate_report(db_root=tmp_path)
        section = report.split("## Agent Adoption Intensity")[1]
        # 1/4 repos pervasive = 25.00%, 3/4 no_commits = 75.00%.
        assert "| pervasive | 1 | 25.00% |" in section
        assert "| no_commits | 3 | 75.00% |" in section

    def test_repos_that_never_reached_the_scan_bucket_as_not_set(self, tmp_path):
        _make_db(tmp_path, [{"adoption_intensity": None}])
        report = generate_report(db_root=tmp_path)
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
        report = generate_report(db_root=tmp_path)
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
        report = generate_report(db_root=tmp_path)
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
        report = generate_report(db_root=tmp_path)
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
        path = write_report(out_dir, db_root=tmp_path)
        assert path == out_dir / "dataset_findings.md"
        assert path.read_text() == generate_report(db_root=tmp_path)
