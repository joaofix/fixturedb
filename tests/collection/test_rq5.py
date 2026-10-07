"""RQ5 report: statistics and rendering over the v4 database."""

import pytest

from collection.research_questions.rq5 import (
    generate_report,
    group_stats,
    load_corpus_counts,
    write_report,
)
from collection.rq5_agent_file_scan import (
    _repo_row,
    _scan_result,
    initialise_rq5_db,
    load_repo_guidance,
    load_rq5_keyword_catalog,
    persist_result,
    record_scan_meta,
)

ARDIC_TERMS = {"test", "tests", "testing", "tested"}


def _persist(db_path, repo, language, *, test_terms=(), fixture_terms=(), has_file=True, fetch_ok=True, error=None):
    files, matches = [], []
    if has_file:
        files.append(
            {
                "repo_name": repo,
                "file_name": "AGENTS.md",
                "file_type": "AGENTS.md",
                "language": language,
                "commit_sha": f"sha-{repo}",
                "has_test": bool(test_terms),
                "has_fixture": bool(fixture_terms),
                "test_match_count": len(test_terms),
                "fixture_match_count": len(fixture_terms),
                "matched_test_keywords": ",".join(test_terms),
                "matched_fixture_keywords": ",".join(fixture_terms),
                "github_url": f"https://github.com/{repo}/blob/sha-{repo}/AGENTS.md",
            }
        )
    for keyword in test_terms:
        matches.append(_match(repo, keyword, "test"))
    for keyword in fixture_terms:
        matches.append(_match(repo, keyword, "fixture"))
    repo_row = _repo_row(
        repo,
        language,
        "2026-01-01T00:00:00+00:00",
        fetch_ok=fetch_ok,
        error_reason=error,
        commit_sha=f"sha-{repo}" if fetch_ok else None,
        commit_date="2025-12-31" if fetch_ok else None,
        num_agent_files=len(files),
    )
    persist_result(_scan_result(repo_row, files, matches), db_path)


def _match(repo, keyword, keyword_list):
    return {
        "repo_name": repo,
        "file_name": "AGENTS.md",
        "keyword_list": keyword_list,
        "keyword": keyword,
        "line_number": 1,
        "line_context": keyword,
        "line_before_2": "",
        "line_before_1": "",
        "line_after_1": "",
        "line_after_2": "",
        "in_code_block": False,
    }


@pytest.fixture
def scanned_db(tmp_path):
    """Corpus of 6 repos: 5 analyzed, 1 skipped.

    - a (python): agent file, test term "tests" (Ardic), fixture "fixture"
    - b (python): agent file, test term "tested" (Ardic), no fixture
    - c (java): agent file, test term "pytest" (not Ardic), no fixture
    - d (javascript): analyzed, no agent file
    - e (typescript): analyzed, agent file with no keyword at all
    - f (java): skipped
    """
    db_path = tmp_path / "rq5.db"
    initialise_rq5_db(db_path)
    record_scan_meta("2026-03-01", db_path)
    _persist(db_path, "owner/a", "python", test_terms=["tests"], fixture_terms=["fixture"])
    _persist(db_path, "owner/b", "python", test_terms=["tested"])
    _persist(db_path, "owner/c", "java", test_terms=["pytest"])
    _persist(db_path, "owner/d", "javascript", has_file=False)
    _persist(db_path, "owner/e", "typescript")
    _persist(db_path, "owner/f", "java", has_file=False, fetch_ok=False, error="tree_fetch_failed")
    return db_path


class TestGroupStats:
    def test_counts_only_repos_with_an_agent_file_for_the_guidance_shares(self, scanned_db):
        records = load_repo_guidance(ARDIC_TERMS, scanned_db)
        stats = group_stats(records)

        assert stats.analyzed == 5
        assert stats.with_agent_file == 4
        assert stats.test == 3
        assert stats.test_ardic == 2
        assert stats.fixture == 1


class TestCorpusCounts:
    def test_total_analyzed_and_skipped_reasons(self, scanned_db):
        counts = load_corpus_counts(scanned_db)

        assert counts["total"] == 6
        assert counts["analyzed"] == 5
        assert counts["skipped"] == 1
        assert counts["skipped_by_reason"] == [("tree_fetch_failed", 1)]


class TestGenerateReport:
    def test_says_not_available_when_no_scan_exists(self, tmp_path):
        report = generate_report(db_path=tmp_path / "missing.db")
        assert "Not available" in report

    def test_overall_statistics_match_the_stored_repositories(self, scanned_db):
        report = generate_report(db_path=scanned_db)

        assert "| 1 | Repositories in the corpus | 6 |" in report
        assert "| 1 | Repositories analyzed | 5 | 83.3% | corpus |" in report
        assert "| 2 | With a root agent file (AGENTS.md or CLAUDE.md) | 4 | 80.0% | analyzed |" in report
        assert "| 3 | With a test keyword (`test_keywords`) | 3 | 75.0% | with agent file |" in report
        assert "| 4 | With an Ardic test term (`ardic_test_keywords`) | 2 | 50.0% | with agent file |" in report
        assert "| 5 | With a fixture keyword match (`fixture_keywords`) | 1 | 25.0% | with agent file |" in report

    def test_by_language_splits_the_shares(self, scanned_db):
        report = generate_report(db_path=scanned_db)

        assert "| Python | 2 | 2 (100.0%) | 100.0% | 100.0% | 50.0% |" in report
        assert "| Java | 1 | 1 (100.0%) | 100.0% | 0.0% | 0.0% |" in report
        assert "| JavaScript | 1 | 0 (0.0%) | -- | -- | -- |" in report

    def test_fixture_term_table_lists_every_term_even_at_zero(self, scanned_db):
        report = generate_report(db_path=scanned_db)
        catalog = load_rq5_keyword_catalog()

        assert "| fixture | 1 |" in report
        assert "| conftest | 0 |" in report
        for term in catalog["fixture_keywords"]:
            assert f"| {term} |" in report

    def test_reports_snapshot_catalog_skipped_count_and_both_keyword_lists(self, scanned_db):
        report = generate_report(db_path=scanned_db)
        catalog = load_rq5_keyword_catalog()

        assert "Snapshot date: 2026-03-01" in report
        assert "Keyword catalog: `collection/heuristics/rq5_agent_file_keywords.yaml`." in report
        assert "version" not in report
        assert "Repositories skipped (no commit at or before the snapshot, or a failed fetch): 1 of 6." in report
        assert ", ".join(catalog["ardic_test_keywords"]) in report
        assert ", ".join(catalog["test_keywords"]) in report
        assert "| tree_fetch_failed | 1 |" in report


class TestWriteReport:
    def test_writes_rq5_markdown_into_the_output_dir(self, scanned_db, tmp_path):
        out_dir = tmp_path / "research-questions"

        path = write_report(out_dir, db_path=scanned_db)

        assert path == out_dir / "rq5.md"
        assert path.read_text(encoding="utf-8").startswith("# RQ5")
