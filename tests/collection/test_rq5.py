"""RQ5 report: statistics and rendering over the guidance files (AGENTS.md,
CLAUDE.md, GEMINI.md at any depth)."""

import pytest

from collection.research_questions.rq5 import (
    code_block_counts,
    file_name_counts,
    generate_report,
    group_stats,
    guidance_file_summary,
    load_corpus_counts,
    write_report,
)
from collection.rq5_agent_file_scan import (
    _repo_row,
    _scan_result,
    initialise_rq5_db,
    load_fixture_match_rows,
    load_repo_guidance,
    load_rq5_keyword_catalog,
    persist_result,
    record_scan_meta,
)


def _file(repo, path, language, test_terms=(), fixture_terms=(), symlink_target=""):
    return {
        "repo_name": repo,
        "file_path": path,
        "file_name": path.rsplit("/", 1)[-1],
        "file_type": path.rsplit("/", 1)[-1],
        "location": "root" if "/" not in path else "nested",
        "symlink_target": symlink_target,
        "language": language,
        "commit_sha": f"sha-{repo}",
        "has_test": bool(test_terms),
        "has_fixture": bool(fixture_terms),
        "test_match_count": len(test_terms),
        "fixture_match_count": len(fixture_terms),
        "matched_test_keywords": ",".join(test_terms),
        "matched_fixture_keywords": ",".join(fixture_terms),
        "github_url": f"https://github.com/{repo}/blob/sha-{repo}/{path}",
    }


def _match(repo, path, keyword, keyword_list, in_block=False):
    return {
        "repo_name": repo,
        "file_path": path,
        "location": "root" if "/" not in path else "nested",
        "keyword_list": keyword_list,
        "keyword": keyword,
        "line_number": 1,
        "line_context": keyword,
        "line_before_2": "",
        "line_before_1": "",
        "line_after_1": "",
        "line_after_2": "",
        "in_code_block": in_block,
    }


def _persist(db_path, repo, language, files=(), *, fetch_ok=True, error=None, truncated=False, links=None):
    """Each of `files` is `(path, test_terms, fixture_terms)`; `links` maps a
    path to its symlink target. A nested file's fixture matches are in a code
    block."""
    links = links or {}
    rows, matches = [], []
    for path, test_terms, fixture_terms in files:
        rows.append(_file(repo, path, language, test_terms, fixture_terms, links.get(path, "")))
        matches += [_match(repo, path, k, "test") for k in test_terms]
        matches += [_match(repo, path, k, "fixture", in_block="/" in path) for k in fixture_terms]
    repo_row = _repo_row(
        repo,
        language,
        "2026-01-01T00:00:00+00:00",
        fetch_ok=fetch_ok,
        error_reason=error,
        commit_sha=f"sha-{repo}" if fetch_ok else None,
        commit_date="2025-12-31" if fetch_ok else None,
        num_guidance_files=len(rows),
        num_root_files=sum(1 for r in rows if r["location"] == "root"),
        tree_truncated=truncated,
    )
    persist_result(_scan_result(repo_row, rows, matches), db_path)


@pytest.fixture
def scanned_db(tmp_path):
    """Corpus of 7 repos: 6 analyzed, 1 skipped.

    - a (python): root AGENTS.md with "tests" and "fixture"
    - b (python): root AGENTS.md with "tested"; docs/CLAUDE.md with "conftest"
    - c (java): pkg/AGENTS.md only, with "testing"
    - d (javascript): analyzed, no guidance file
    - e (typescript): root AGENTS.md and a CLAUDE.md symlink, no keyword; tree truncated
    - g (typescript): web/GEMINI.md only, with "fixtures"
    - f (java): skipped
    """
    db_path = tmp_path / "rq5.db"
    initialise_rq5_db(db_path)
    record_scan_meta("2026-03-01", db_path)
    _persist(db_path, "owner/a", "python", [("AGENTS.md", ["tests"], ["fixture"])])
    _persist(db_path, "owner/b", "python", [("AGENTS.md", ["tested"], []), ("docs/CLAUDE.md", [], ["conftest"])])
    _persist(db_path, "owner/c", "java", [("pkg/AGENTS.md", ["testing"], [])])
    _persist(db_path, "owner/d", "javascript")
    _persist(
        db_path, "owner/e", "typescript", [("AGENTS.md", [], []), ("CLAUDE.md", [], [])],
        truncated=True, links={"CLAUDE.md": "docs/ai.md"},
    )
    _persist(db_path, "owner/g", "typescript", [("web/GEMINI.md", [], ["fixtures"])])
    _persist(db_path, "owner/f", "java", fetch_ok=False, error="tree_fetch_failed")
    return db_path


class TestGroupStats:
    def test_counts(self, scanned_db):
        stats = group_stats(load_repo_guidance(scanned_db))
        assert (stats.analyzed, stats.with_guidance_file, stats.with_root_file) == (6, 5, 3)
        assert (stats.test, stats.fixture) == (3, 3)


class TestGuidanceFileSummary:
    def test_counts(self, scanned_db):
        summary = guidance_file_summary(load_repo_guidance(scanned_db), scanned_db)
        assert summary == {
            "with_root_file": 3,
            "nested_only": 2,  # c, g
            "with_nested_file": 3,  # b, c, g
            "nested_files": 3,
            "fixture_only_nested": 2,  # b, g
            "symlinked_files": 1,
            "truncated_trees": 1,
        }

    def test_file_name_counts(self, scanned_db):
        assert file_name_counts(scanned_db) == [
            ("AGENTS.md", 4, 4, 3, 1),
            ("CLAUDE.md", 2, 2, 1, 1),
            ("GEMINI.md", 1, 1, 0, 1),
        ]


class TestCodeBlockCounts:
    def test_counts(self, scanned_db):
        counts = code_block_counts(load_fixture_match_rows(scanned_db), ["fixture", "fixtures", "conftest"])
        assert counts["all"] == (3, 2)
        assert counts["conftest"] == (1, 1)
        assert counts["fixture"] == (1, 0)


class TestCorpusCounts:
    def test_total_analyzed_and_skipped_reasons(self, scanned_db):
        counts = load_corpus_counts(scanned_db)
        assert (counts["total"], counts["analyzed"], counts["skipped"]) == (7, 6, 1)
        assert counts["skipped_by_reason"] == [("tree_fetch_failed", 1)]


class TestGenerateReport:
    def test_says_not_available_when_no_scan_exists(self, tmp_path):
        assert "Not available" in generate_report(db_path=tmp_path / "missing.db")

    def test_overall_statistics(self, scanned_db):
        report = generate_report(db_path=scanned_db)
        assert "| # | Statistic | Repositories | % | Denominator |" in report
        assert "| 1 | Repositories in the corpus | 7 | -- | -- |" in report
        assert "| 1 | Repositories analyzed | 6 | 85.7% | corpus |" in report
        assert "| 2 | With a guidance file | 5 | 83.3% | analyzed |" in report
        assert "| 2a | -- with a guidance file at the root | 3 | 60.0% | with guidance file |" in report
        assert "| 3 | With a test keyword (`ardic_test_keywords`) | 3 | 60.0% | with guidance file |" in report
        assert "| 4 | With a fixture keyword match (`fixture_keywords`) | 3 | 60.0% | with guidance file |" in report
        assert "referred" not in report.lower()

    def test_by_language(self, scanned_db):
        report = generate_report(db_path=scanned_db)
        assert "| Python | 2 | 2 (100.0%) | 100.0% | 100.0% |" in report
        assert "| Java | 1 | 1 (100.0%) | 100.0% | 0.0% |" in report
        assert "| JavaScript | 1 | 0 (0.0%) | -- | -- |" in report
        assert "| TypeScript | 2 | 2 (100.0%) | 0.0% | 50.0% |" in report

    def test_guidance_file_section(self, scanned_db):
        report = generate_report(db_path=scanned_db)
        assert "| Repositories with a guidance file at the root | 3 |" in report
        assert "| Repositories with guidance files in subdirectories only | 2 |" in report
        assert "| Repositories whose fixture match is only in subdirectory files | 2 |" in report
        assert "| Guidance files read through a symbolic link | 1 |" in report
        assert "| AGENTS.md | 4 | 4 | 3 | 1 |" in report

    def test_fixture_term_table_lists_every_term(self, scanned_db):
        report = generate_report(db_path=scanned_db)
        assert "| fixture | 1 |" in report
        assert "| conftest | 1 |" in report
        assert "| fixtures | 1 |" in report
        for term in load_rq5_keyword_catalog()["fixture_keywords"]:
            assert f"| {term} |" in report

    def test_code_block_table(self, scanned_db):
        report = generate_report(db_path=scanned_db)
        assert "| All terms | 3 | 2 | 66.7% |" in report

    def test_reports_snapshot_catalogs_skipped_count_and_keyword_lists(self, scanned_db):
        report = generate_report(db_path=scanned_db)
        catalog = load_rq5_keyword_catalog()
        assert "Snapshot date: 2026-03-01" in report
        assert "Keyword catalog: `collection/heuristics/rq5_agent_file_keywords.yaml`." in report
        assert "File names: `collection/heuristics/rq5_agent_guidance_files.yaml`." in report
        assert "AGENTS.md, CLAUDE.md, GEMINI.md" in report
        assert ", ".join(catalog["excluded_dirs"]) in report
        assert "Repositories skipped (no commit at or before the snapshot, or a failed fetch): 1 of 7." in report
        assert ", ".join(catalog["ardic_test_keywords"]) in report
        assert "| tree_fetch_failed | 1 |" in report
        assert "`test_keywords`" not in report


class TestWriteReport:
    def test_writes_rq5_markdown_into_the_output_dir(self, scanned_db, tmp_path):
        out_dir = tmp_path / "research-questions"
        path = write_report(out_dir, db_path=scanned_db)
        assert path == out_dir / "rq5.md"
        assert path.read_text(encoding="utf-8").startswith("# RQ5")
