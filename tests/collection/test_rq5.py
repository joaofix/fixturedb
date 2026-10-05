"""Tests for collection/research_questions/rq5.py.

Mirrors tests/collection/test_rq1.py's standard: this report's numbers go
straight into the paper, so every statistical calculation (repo-level
aggregation across a repo's files, percentages, per-group isolation,
keyword-frequency counting) is exercised directly, not just the
rendering/plumbing around it. Synthetic DBs are built via
`rq5_agent_file_scan`'s own `initialise_rq5_db()`/`persist_result()`/
`_repo_row()`/`_scan_result()` helpers (the real schema those write),
rather than a second, potentially-drifting hand-rolled schema here.
"""

from __future__ import annotations

from collections import Counter

from collection.research_questions.rq5 import (
    DISPLAY_LANGUAGES,
    RepoGroupStats,
    RepoGuidance,
    _has_unambiguous_fixture_keyword,
    _keyword_repo_counts,
    _repo_group_stats,
    aggregate_repo_guidance,
    generate_report,
    load_agent_files,
    load_repo_counts,
    render_by_language_table,
    render_keyword_table,
    render_overall_table,
    write_report,
)
from collection.rq5_agent_file_scan import (
    _repo_row,
    _scan_result,
    initialise_rq5_db,
    persist_result,
)


def _file_row(
    repo_name,
    file_name,
    file_type,
    language,
    *,
    has_test=False,
    has_fixture=False,
    test_keywords=(),
    fixture_keywords=(),
):
    return {
        "repo_name": repo_name,
        "file_name": file_name,
        "file_type": file_type,
        "language": language,
        "commit_sha": "sha1",
        "has_test": has_test,
        "has_fixture": has_fixture,
        "test_match_count": len(test_keywords),
        "fixture_match_count": len(fixture_keywords),
        "matched_test_keywords": ",".join(test_keywords),
        "matched_fixture_keywords": ",".join(fixture_keywords),
        "github_url": f"https://github.com/{repo_name}/blob/sha1/{file_name}",
    }


def _make_db(tmp_path, repos):
    """`repos`: list of (repo_name, language, [file_dicts]) tuples. Each
    repo is persisted via the scan's own real persist_result()/
    initialise_rq5_db(), matching exactly what a real run writes."""
    db_path = tmp_path / "rq5_agent_files.db"
    initialise_rq5_db(db_path)
    for repo_name, language, files in repos:
        row = _repo_row(
            repo_name, language, "2026-09-08T00:00:00Z", 1, fetch_ok=True, num_agent_files=len(files)
        )
        persist_result(_scan_result(row, files=files), db_path)
    return db_path


class TestLoadAgentFiles:
    def test_missing_db_returns_none(self, tmp_path):
        assert load_agent_files(tmp_path) is None

    def test_empty_db_returns_empty_list_not_none(self, tmp_path):
        db_path = tmp_path / "rq5_agent_files.db"
        initialise_rq5_db(db_path)
        assert load_agent_files(tmp_path) == []

    def test_returns_persisted_file_rows(self, tmp_path):
        files = [_file_row("o/a", "AGENTS.md", "AGENTS.md", "python", has_test=True)]
        _make_db(tmp_path, [("o/a", "python", files)])
        rows = load_agent_files(tmp_path)
        assert len(rows) == 1
        assert rows[0]["file_name"] == "AGENTS.md"

    def test_reads_the_exact_file_the_scan_module_writes(self, tmp_path):
        """_DB_FILENAME is derived from
        rq5_agent_file_scan.DB_PATH rather than a second hardcoded
        literal -- if they ever desync, this fails loudly instead of
        silently reporting "not available" forever."""
        from collection.research_questions import rq5 as rq5_report
        from collection.rq5_agent_file_scan import DB_PATH as scan_db_path

        assert rq5_report._DB_FILENAME == scan_db_path.name


class TestLoadRepoCounts:
    def test_missing_db_returns_none(self, tmp_path):
        assert load_repo_counts(tmp_path) is None

    def test_counts_total_analyzed_and_skipped(self, tmp_path):
        db_path = tmp_path / "rq5_agent_files.db"
        initialise_rq5_db(db_path)
        persist_result(_scan_result(_repo_row("o/a", "python", "t", 1, fetch_ok=True)), db_path)
        persist_result(
            _scan_result(_repo_row("o/b", "python", "t", 1, fetch_ok=False, error_reason="no_commit_at_or_before_cutoff")),
            db_path,
        )
        persist_result(_scan_result(_repo_row("o/c", "python", "t", 1, fetch_ok=True)), db_path)

        counts = load_repo_counts(tmp_path)
        assert counts == {"total": 3, "analyzed": 2, "skipped": 1}


class TestAggregateRepoGuidance:
    def test_repo_with_one_matching_file(self):
        rows = [_file_row("o/a", "AGENTS.md", "AGENTS.md", "python", has_test=True, test_keywords=["test"])]
        by_repo = aggregate_repo_guidance(rows)
        assert by_repo["o/a"].has_test is True
        assert by_repo["o/a"].has_fixture is False
        assert by_repo["o/a"].test_keywords == {"test"}

    def test_repo_has_guidance_if_any_one_of_its_files_matches(self):
        """Core repo-level semantics: AGENTS.md has no test keyword but
        CLAUDE.md does -- the repo as a whole still counts as having test
        guidance (logical OR across a repo's files, not AND)."""
        rows = [
            _file_row("o/a", "AGENTS.md", "AGENTS.md", "python", has_test=False),
            _file_row("o/a", "CLAUDE.md", "CLAUDE.md", "python", has_test=True, test_keywords=["pytest"]),
        ]
        by_repo = aggregate_repo_guidance(rows)
        assert by_repo["o/a"].has_test is True

    def test_a_non_matching_pointer_file_cannot_suppress_a_real_signal(self):
        """A symlinked CLAUDE.md (scanned as its own literal, never-
        matching content -- see rq5_agent_file_scan.read_blob_via_api())
        contributes has_test=False/has_fixture=False for its own row, but
        must never drag the repo's OR-folded signal back down to False."""
        rows = [
            _file_row("o/a", "AGENTS.md", "AGENTS.md", "python", has_fixture=True, fixture_keywords=["fixture"]),
            _file_row("o/a", "CLAUDE.md", "CLAUDE.md", "python", has_fixture=False),
        ]
        by_repo = aggregate_repo_guidance(rows)
        assert by_repo["o/a"].has_fixture is True

    def test_keywords_are_unioned_across_a_repos_files(self):
        rows = [
            _file_row("o/a", "AGENTS.md", "AGENTS.md", "python", test_keywords=["test"]),
            _file_row("o/a", "CLAUDE.md", "CLAUDE.md", "python", test_keywords=["pytest", "test"]),
        ]
        by_repo = aggregate_repo_guidance(rows)
        assert by_repo["o/a"].test_keywords == {"test", "pytest"}

    def test_a_repo_with_zero_agent_files_is_absent_not_zeroed(self):
        """A repo contributing no agent_files rows at all must not appear
        in the result -- "repositories with >=1 root agent file" is
        exactly len(aggregate_repo_guidance(rows)), with no filtering
        needed afterwards."""
        rows = [_file_row("o/a", "AGENTS.md", "AGENTS.md", "python")]
        by_repo = aggregate_repo_guidance(rows)
        assert "o/missing" not in by_repo
        assert len(by_repo) == 1

    def test_distinct_repos_are_kept_independent(self):
        rows = [
            _file_row("o/a", "AGENTS.md", "AGENTS.md", "python", has_test=True),
            _file_row("o/b", "AGENTS.md", "AGENTS.md", "java", has_test=False),
        ]
        by_repo = aggregate_repo_guidance(rows)
        assert len(by_repo) == 2
        assert by_repo["o/a"].has_test is True
        assert by_repo["o/b"].has_test is False
        assert by_repo["o/b"].language == "java"


class TestHasUnambiguousFixtureKeyword:
    def test_false_when_only_ambiguous_keywords_matched(self):
        """"fixture"/"fixtures" alone -- majority test-data-file-sense in
        manual sampling, not the fixture-as-code this stricter count
        targets. See AMBIGUOUS_FIXTURE_KEYWORDS's own docstring."""
        guidance = RepoGuidance(language="python", has_fixture=True, fixture_keywords={"fixture", "fixtures"})
        assert _has_unambiguous_fixture_keyword(guidance) is False

    def test_true_when_an_unambiguous_keyword_is_also_present(self):
        guidance = RepoGuidance(language="python", has_fixture=True, fixture_keywords={"fixture", "conftest"})
        assert _has_unambiguous_fixture_keyword(guidance) is True

    def test_true_for_a_purely_unambiguous_match(self):
        guidance = RepoGuidance(language="python", has_fixture=True, fixture_keywords={"beforeEach"})
        assert _has_unambiguous_fixture_keyword(guidance) is True

    def test_false_when_no_fixture_keywords_at_all(self):
        guidance = RepoGuidance(language="python", has_fixture=False)
        assert _has_unambiguous_fixture_keyword(guidance) is False


class TestRepoGroupStats:
    def test_counts_test_fixture_and_both(self):
        guidances = [
            RepoGuidance(language="python", has_test=True, has_fixture=False),
            RepoGuidance(language="python", has_test=False, has_fixture=True, fixture_keywords={"fixture"}),
            RepoGuidance(language="python", has_test=True, has_fixture=True, fixture_keywords={"conftest"}),
            RepoGuidance(language="python", has_test=False, has_fixture=False),
        ]
        stats = _repo_group_stats(guidances)
        assert stats == RepoGroupStats(
            n=4, n_test=2, n_fixture=2, n_fixture_unambiguous=1, n_test_and_fixture=1
        )

    def test_empty_group_is_all_zero(self):
        assert _repo_group_stats([]) == RepoGroupStats(
            n=0, n_test=0, n_fixture=0, n_fixture_unambiguous=0, n_test_and_fixture=0
        )


class TestKeywordRepoCounts:
    def test_counts_distinct_repos_containing_each_keyword_not_files(self):
        """A repo with the same keyword matched in two of its files must
        still count once -- this counts repositories, not occurrences or
        files."""
        rows = [
            _file_row("o/a", "AGENTS.md", "AGENTS.md", "python", test_keywords=["test"]),
            _file_row("o/a", "CLAUDE.md", "CLAUDE.md", "python", test_keywords=["test", "pytest"]),
            _file_row("o/b", "AGENTS.md", "AGENTS.md", "python", test_keywords=["test"]),
        ]
        by_repo = aggregate_repo_guidance(rows)
        counts = _keyword_repo_counts(list(by_repo.values()), "test_keywords", ["test", "pytest", "jest"])
        assert counts == Counter({"test": 2, "pytest": 1, "jest": 0})

    def test_handles_repos_with_no_matches_at_all(self):
        guidance = RepoGuidance(language="python")
        counts = _keyword_repo_counts([guidance], "test_keywords", ["test"])
        assert counts == Counter({"test": 0})


class TestRenderOverallTable:
    def test_percentages_use_repos_with_an_agent_file_as_denominator(self):
        guidances = [
            RepoGuidance(language="python", has_test=True, has_fixture=False),
            RepoGuidance(language="python", has_test=True, has_fixture=True),
            RepoGuidance(language="python", has_test=False, has_fixture=False),
            RepoGuidance(language="python", has_test=False, has_fixture=False),
        ]
        table = render_overall_table(guidances)
        assert "| Repositories with >=1 root agent file | 4 |" in table
        assert "2 (50.0%)" in table  # 2/4 repos have test guidance
        assert "1 (25.0%)" in table  # 1/4 repos have fixture guidance

    def test_secondary_metric_denominator_is_test_guidance_repos_not_all_repos(self):
        guidances = [
            RepoGuidance(language="python", has_test=True, has_fixture=True),
            RepoGuidance(language="python", has_test=True, has_fixture=False),
            RepoGuidance(language="python", has_test=False, has_fixture=True),
        ]
        table = render_overall_table(guidances)
        line = next(row for row in table.splitlines() if "also have fixture guidance" in row)
        # 1 of the 2 test-guidance repos also has fixture guidance -> 50%, not 1/3.
        assert "1 (50.0%)" in line

    def test_unambiguous_row_excludes_bare_fixture_fixtures_only_repos(self):
        guidances = [
            RepoGuidance(language="python", has_fixture=True, fixture_keywords={"fixture"}),
            RepoGuidance(language="python", has_fixture=True, fixture_keywords={"fixtures"}),
            RepoGuidance(language="python", has_fixture=True, fixture_keywords={"conftest"}),
            RepoGuidance(language="python", has_fixture=False),
        ]
        table = render_overall_table(guidances)
        inclusive_line = next(row for row in table.splitlines() if "fixture keyword (inclusive)" in row)
        unambiguous_line = next(row for row in table.splitlines() if "unambiguous* fixture keyword" in row)
        assert "3 (75.0%)" in inclusive_line
        assert "1 (25.0%)" in unambiguous_line


class TestRenderByLanguageTable:
    def test_each_language_computed_only_from_its_own_repos(self):
        """Python's percentage must never leak into
        Java's row, or vice versa -- deliberately asymmetric group sizes
        and percentages so a cross-group mixup would be visible."""
        guidances = (
            [RepoGuidance(language="python", has_fixture=True)]
            + [RepoGuidance(language="python", has_fixture=False) for _ in range(9)]
            + [RepoGuidance(language="java", has_fixture=True)]
        )
        table = render_by_language_table(guidances)
        python_line = next(row for row in table.splitlines() if row.startswith("| Python"))
        java_line = next(row for row in table.splitlines() if row.startswith("| Java"))
        assert "| 10 |" in python_line
        assert "10.0%" in python_line.split("|")[-3]  # inclusive fixture-keyword column
        assert "| 1 |" in java_line
        assert "100.0%" in java_line.split("|")[-3]

    def test_unambiguous_column_excludes_bare_fixture_fixtures(self):
        guidances = [
            RepoGuidance(language="python", has_fixture=True, fixture_keywords={"fixture"}),
            RepoGuidance(language="python", has_fixture=True, fixture_keywords={"conftest"}),
        ]
        table = render_by_language_table(guidances)
        python_line = next(row for row in table.splitlines() if row.startswith("| Python"))
        assert "100.0%" in python_line.split("|")[-3]  # inclusive: both repos
        assert "50.0%" in python_line.split("|")[-2]  # unambiguous: only the conftest one

    def test_renders_every_display_language_in_order(self):
        table = render_by_language_table([])
        labels = [row.split("|")[1].strip() for row in table.splitlines()[2:]]
        assert labels == ["Python", "Java", "JavaScript", "TypeScript"]
        assert DISPLAY_LANGUAGES == ("python", "java", "javascript", "typescript")

    def test_language_with_zero_repos_renders_dashes_not_a_crash(self):
        guidances = [RepoGuidance(language="python", has_test=True)]
        table = render_by_language_table(guidances)
        java_line = next(row for row in table.splitlines() if row.startswith("| Java"))
        assert "| 0 | -- | -- |" in java_line


class TestRenderKeywordTable:
    def test_sorted_by_count_descending_then_alphabetically(self):
        counts = Counter({"zebra": 2, "apple": 2, "mango": 5, "kiwi": 0})
        table = render_keyword_table(counts, header="Test keyword")
        rows = table.splitlines()[2:]
        keywords_in_order = [row.split("|")[1].strip() for row in rows]
        assert keywords_in_order == ["mango", "apple", "zebra", "kiwi"]


class TestGenerateReport:
    def test_missing_db_reports_not_available(self, tmp_path):
        report = generate_report(db_root=tmp_path)
        assert "Not available" in report
        assert "not collected yet" in report

    def test_collected_but_zero_agent_files_reports_that_distinctly(self, tmp_path):
        db_path = tmp_path / "rq5_agent_files.db"
        initialise_rq5_db(db_path)
        persist_result(_scan_result(_repo_row("o/a", "python", "t", 1, fetch_ok=True)), db_path)

        report = generate_report(db_root=tmp_path)
        assert "No agent files found yet" in report
        assert "Repositories analyzed" in report

    def test_repos_with_fetch_ok_zero_contribute_no_files_and_are_reported_as_skipped(self, tmp_path):
        db_path = tmp_path / "rq5_agent_files.db"
        initialise_rq5_db(db_path)
        persist_result(
            _scan_result(_repo_row("o/bad", "python", "t", 1, fetch_ok=False, error_reason="no_commit_at_or_before_cutoff")),
            db_path,
        )
        persist_result(
            _scan_result(
                _repo_row("o/good", "python", "t", 1, fetch_ok=True, num_agent_files=1),
                files=[_file_row("o/good", "AGENTS.md", "AGENTS.md", "python", has_test=True)],
            ),
            db_path,
        )

        report = generate_report(db_root=tmp_path)
        assert (
            "Repositories analyzed (commit found at/before the snapshot date, "
            "root tree/blob fetch succeeded): 1." in report
        )
        assert "Repositories skipped (no commit at/before the snapshot date, or a fetch failed): 1." in report
        assert "| Repositories with >=1 root agent file | 1 |" in report

    def test_a_repo_with_two_files_counts_once_in_the_overall_denominator(self, tmp_path):
        """The unit is the repository, not the file: one
        repo contributing both AGENTS.md and CLAUDE.md must still count
        as exactly one repo in "repositories with >=1 root agent file"."""
        db_path = tmp_path / "rq5_agent_files.db"
        initialise_rq5_db(db_path)
        persist_result(
            _scan_result(
                _repo_row("o/a", "python", "t", 1, fetch_ok=True, num_agent_files=2),
                files=[
                    _file_row("o/a", "AGENTS.md", "AGENTS.md", "python", has_test=True),
                    _file_row("o/a", "CLAUDE.md", "CLAUDE.md", "python", has_fixture=True),
                ],
            ),
            db_path,
        )

        report = generate_report(db_root=tmp_path)
        assert "| Repositories with >=1 root agent file | 1 |" in report

    def test_includes_snapshot_date_and_keyword_lists(self, tmp_path):
        db_path = tmp_path / "rq5_agent_files.db"
        initialise_rq5_db(db_path)
        persist_result(
            _scan_result(
                _repo_row("o/a", "python", "t", 1, fetch_ok=True, num_agent_files=1),
                files=[_file_row("o/a", "AGENTS.md", "AGENTS.md", "python", test_keywords=["pytest"])],
            ),
            db_path,
        )

        report = generate_report(db_root=tmp_path)
        assert "Snapshot date: 2026-09-08" in report
        assert "pytest" in report
        assert "conftest" in report  # a fixture keyword, from the real catalog

    def test_no_file_type_breakdown_section(self, tmp_path):
        """Explicit project decision (2026-10-02): no per-file-type
        (AGENTS.md/CLAUDE.md/both) breakdown in this report."""
        db_path = tmp_path / "rq5_agent_files.db"
        initialise_rq5_db(db_path)
        persist_result(
            _scan_result(
                _repo_row("o/a", "python", "t", 1, fetch_ok=True, num_agent_files=1),
                files=[_file_row("o/a", "AGENTS.md", "AGENTS.md", "python", has_test=True)],
            ),
            db_path,
        )
        report = generate_report(db_root=tmp_path)
        assert "By file type" not in report


class TestWriteReport:
    def test_writes_to_rq5_md(self, tmp_path):
        out_dir = tmp_path / "out"
        db_dir = tmp_path / "db"
        db_dir.mkdir()
        path = write_report(out_dir, db_root=db_dir)
        assert path == out_dir / "rq5.md"
        assert path.read_text() == generate_report(db_root=db_dir)
