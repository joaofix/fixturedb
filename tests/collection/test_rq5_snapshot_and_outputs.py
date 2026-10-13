"""RQ5: corpus from Dataset A, required snapshot date, the test keywords,
two-line context around each match, and the review outputs."""

import csv
import sqlite3
import sys
from unittest.mock import patch

import pytest
import yaml

from collection.rq5_agent_file_scan import (
    FIXTURE_MATCHES_FIELDNAMES,
    REPO_CSV_FIELDNAMES,
    SKIPPED_CSV_FIELDNAMES,
    _build_patterns,
    _repo_row,
    _scan_result,
    find_keyword_matches,
    initialise_rq5_db,
    load_corpus,
    load_repo_guidance,
    load_rq5_keyword_catalog,
    load_scan_meta,
    main,
    persist_result,
    record_scan_meta,
    run_scan,
    validated_snapshot_date,
    write_review_outputs,
)

ARDIC_TERMS = {"test", "tests", "testing", "tested"}


def _location(path):
    return "root" if "/" not in path else "nested"


def _file(repo, path, test_terms=(), fixture_terms=()):
    return {
        "repo_name": repo,
        "file_path": path,
        "file_name": path.rsplit("/", 1)[-1],
        "file_type": path.rsplit("/", 1)[-1],
        "location": _location(path),
        "symlink_target": "",
        "language": "python",
        "commit_sha": f"sha-{repo}",
        "has_test": bool(test_terms),
        "has_fixture": bool(fixture_terms),
        "test_match_count": len(test_terms),
        "fixture_match_count": len(fixture_terms),
        "matched_test_keywords": ",".join(sorted(test_terms)),
        "matched_fixture_keywords": ",".join(sorted(fixture_terms)),
        "github_url": f"https://github.com/{repo}/blob/sha-{repo}/{path}",
    }


def _match(repo, path, keyword, keyword_list="fixture", line=3):
    return {
        "repo_name": repo,
        "file_path": path,
        "location": _location(path),
        "keyword_list": keyword_list,
        "keyword": keyword,
        "line_number": line,
        "line_context": f"matched {keyword}",
        "line_before_2": "before two",
        "line_before_1": "before one",
        "line_after_1": "after one",
        "line_after_2": "after two",
        "in_code_block": False,
    }


def _persist_repo(db_path, repo, language, *, files=(), matches=(), fetch_ok=True, error_reason=None):
    repo_row = _repo_row(
        repo,
        language,
        "2026-01-01T00:00:00+00:00",
        fetch_ok=fetch_ok,
        error_reason=error_reason,
        commit_sha=f"sha-{repo}" if fetch_ok else None,
        commit_date="2025-12-31" if fetch_ok else None,
        num_guidance_files=len(files),
        num_root_files=sum(1 for f in files if f["location"] == "root"),
    )
    persist_result(_scan_result(repo_row, list(files), list(matches)), db_path)


@pytest.fixture
def v4_db(tmp_path):
    """owner/a: root AGENTS.md with a fixture match. owner/b: root CLAUDE.md with
    a test match and a nested docs/AGENTS.md with a fixture match. owner/c: no
    guidance file. owner/d: skipped."""
    db_path = tmp_path / "rq5.db"
    initialise_rq5_db(db_path)
    _persist_repo(
        db_path,
        "owner/a",
        "python",
        files=[_file("owner/a", "AGENTS.md", ["tests"], ["fixture"])],
        matches=[
            _match("owner/a", "AGENTS.md", "tests", "test"),
            _match("owner/a", "AGENTS.md", "fixture", "fixture"),
        ],
    )
    _persist_repo(
        db_path,
        "owner/b",
        "python",
        files=[
            _file("owner/b", "CLAUDE.md", ["test"]),
            _file("owner/b", "docs/AGENTS.md", [], ["conftest"]),
        ],
        matches=[
            _match("owner/b", "CLAUDE.md", "test", "test"),
            _match("owner/b", "docs/AGENTS.md", "conftest", "fixture", line=7),
        ],
    )
    _persist_repo(db_path, "owner/c", "java")  # analyzed, no guidance file
    _persist_repo(db_path, "owner/d", "java", fetch_ok=False, error_reason="no_commit_at_or_before_cutoff")
    return db_path


class TestValidatedSnapshotDate:
    def test_accepts_a_real_calendar_date(self):
        assert validated_snapshot_date("2026-01-31") == "2026-01-31"

    @pytest.mark.parametrize("value", [None, "", "2026/01/31", "31-01-2026", "2026-02-30", "not-a-date"])
    def test_rejects_missing_or_malformed_dates(self, value):
        with pytest.raises(ValueError):
            validated_snapshot_date(value)


class TestLoadCorpus:
    def test_collects_repos_from_every_fixture_csv_once(self, tmp_path):
        (tmp_path / "python_fixtures.csv").write_text(
            "repo_name,language,fixture_name\nowner/a,python,f1\nowner/a,python,f2\nowner/b,python,f3\n"
        )
        (tmp_path / "java_fixtures.csv").write_text("repo_name,language,fixture_name\nowner/c,java,f4\n")

        corpus = load_corpus(tmp_path)

        assert sorted((r["repo_name"], r["language"]) for r in corpus) == [
            ("owner/a", "python"),
            ("owner/b", "python"),
            ("owner/c", "java"),
        ]

    def test_repo_in_two_languages_keeps_the_first_file_in_filename_order(self, tmp_path):
        (tmp_path / "python_fixtures.csv").write_text("repo_name,language,fixture_name\nowner/a,python,f\n")
        (tmp_path / "java_fixtures.csv").write_text("repo_name,language,fixture_name\nowner/a,java,f\n")

        assert load_corpus(tmp_path) == [{"repo_name": "owner/a", "language": "java"}]

    def test_ignores_csv_files_that_are_not_fixture_outputs(self, tmp_path):
        (tmp_path / "python_repo.csv").write_text("repo_name,language\nowner/x,python\n")
        (tmp_path / "python_fixtures.csv").write_text("repo_name,language,fixture_name\nowner/a,python,f\n")

        assert [r["repo_name"] for r in load_corpus(tmp_path)] == ["owner/a"]


class TestScanMeta:
    def test_records_snapshot_date(self, tmp_path):
        db_path = tmp_path / "rq5.db"
        initialise_rq5_db(db_path)

        record_scan_meta("2026-03-01", db_path)

        meta = load_scan_meta(db_path)
        assert meta["snapshot_date"] == "2026-03-01"
        assert meta == {"snapshot_date": "2026-03-01"}

    def test_resuming_with_the_same_date_is_allowed(self, tmp_path):
        db_path = tmp_path / "rq5.db"
        initialise_rq5_db(db_path)
        record_scan_meta("2026-03-01", db_path)

        record_scan_meta("2026-03-01", db_path)

    def test_refuses_to_mix_snapshot_dates_in_one_database(self, tmp_path):
        db_path = tmp_path / "rq5.db"
        initialise_rq5_db(db_path)
        record_scan_meta("2026-03-01", db_path)

        with pytest.raises(ValueError, match="refusing to continue"):
            record_scan_meta("2026-06-01", db_path)

    def test_run_scan_refuses_to_start_without_a_snapshot_date(self, tmp_path):
        with pytest.raises(ValueError):
            run_scan(corpus=[], db_path=tmp_path / "rq5.db", progress_path=tmp_path / "p.json", notify=False)


class TestCatalogTestKeywords:
    def test_real_catalog_test_keywords_are_exactly_ardics(self):
        catalog = load_rq5_keyword_catalog()
        assert "version" not in catalog
        assert "test_keywords" not in catalog
        assert set(catalog["ardic_test_keywords"]) == ARDIC_TERMS

    def test_real_catalog_does_not_match_framework_names_as_test_keywords(self):
        patterns = _build_patterns(load_rq5_keyword_catalog()["ardic_test_keywords"])
        assert find_keyword_matches("run pytest, jest or junit; add a unit test", patterns) == [
            m for m in find_keyword_matches("run pytest, jest or junit; add a unit test", patterns)
            if m["keyword"] == "test"
        ]
        assert [m["keyword"] for m in find_keyword_matches("run pytest, jest or junit", patterns)] == []

    def test_tested_matches_as_its_own_term_not_as_test(self):
        patterns = _build_patterns(["test", "tested"])
        matches = find_keyword_matches("the suite was tested", patterns)
        assert [m["keyword"] for m in matches] == ["tested"]


class TestContextLines:
    def test_each_match_carries_two_lines_either_side(self):
        content = "one\ntwo\nthis is a test\nfour\nfive"
        [match] = find_keyword_matches(content, _build_patterns(["test"]))
        assert match["line_number"] == 3
        assert match["line_before_2"] == "one"
        assert match["line_before_1"] == "two"
        assert match["line_context"] == "this is a test"
        assert match["line_after_1"] == "four"
        assert match["line_after_2"] == "five"

    def test_context_outside_the_file_is_empty(self):
        [match] = find_keyword_matches("test", _build_patterns(["test"]))
        assert (match["line_before_2"], match["line_before_1"]) == ("", "")
        assert (match["line_after_1"], match["line_after_2"]) == ("", "")


class TestLoadRepoGuidance:
    def test_folds_files_per_repo(self, v4_db):
        records = {r["repository"]: r for r in load_repo_guidance(v4_db)}

        assert set(records) == {"owner/a", "owner/b", "owner/c"}
        assert records["owner/a"]["has_test"] is True
        assert records["owner/a"]["has_fixture"] is True
        assert records["owner/b"]["has_test"] is True
        assert records["owner/b"]["has_fixture"] is True  # from the nested file
        assert records["owner/b"]["guidance_files"] == ["CLAUDE.md", "docs/AGENTS.md"]
        assert records["owner/b"]["root_files"] == ["CLAUDE.md"]
        assert records["owner/c"]["guidance_files"] == []
        assert records["owner/c"]["has_test"] is False

    def test_fixture_flags_per_location(self, v4_db):
        records = {r["repository"]: r for r in load_repo_guidance(v4_db)}
        assert (records["owner/a"]["has_fixture_root"], records["owner/a"]["has_fixture_nested"]) == (True, False)
        assert (records["owner/b"]["has_fixture_root"], records["owner/b"]["has_fixture_nested"]) == (False, True)
        assert records["owner/b"]["fixture_terms"] == {"conftest"}

    def test_skipped_repository_is_excluded(self, v4_db):
        assert "owner/d" not in {r["repository"] for r in load_repo_guidance(v4_db)}


class TestWriteReviewOutputs:
    def test_writes_every_output_with_the_agreed_columns(self, v4_db, tmp_path):
        written = write_review_outputs(v4_db, tmp_path / "out")

        assert set(written) == {"repositories", "fixture_matches", "snippets", "repository_sheet", "skipped", "readme"}
        with written["repositories"].open(encoding="utf-8") as fh:
            repo_rows = list(csv.DictReader(fh))
        assert tuple(repo_rows[0].keys()) == REPO_CSV_FIELDNAMES
        by_repo = {row["repository"]: row for row in repo_rows}
        assert by_repo["owner/a"] == {
            "repository": "owner/a", "commit_sha": "sha-owner/a", "num_guidance_files": "1",
            "guidance_files": "AGENTS.md", "has_root_file": "1", "has_test": "1",
            "has_fixture": "1", "has_fixture_root": "1", "has_fixture_nested": "0",
            "matched_fixture_terms": "fixture",
        }
        b = by_repo["owner/b"]
        assert (b["num_guidance_files"], b["guidance_files"]) == ("2", "CLAUDE.md;docs/AGENTS.md")
        assert (b["has_fixture"], b["has_fixture_root"], b["has_fixture_nested"]) == ("1", "0", "1")
        assert (by_repo["owner/c"]["num_guidance_files"], by_repo["owner/c"]["has_root_file"]) == ("0", "0")

    def test_fixture_matches_have_path_location_and_no_coding_columns(self, v4_db, tmp_path):
        written = write_review_outputs(v4_db, tmp_path / "out")

        with written["fixture_matches"].open(encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        assert tuple(rows[0].keys()) == FIXTURE_MATCHES_FIELDNAMES
        assert [(r["repository"], r["file_path"], r["location"], r["matched_term"]) for r in rows] == [
            ("owner/a", "AGENTS.md", "root", "fixture"),
            ("owner/b", "docs/AGENTS.md", "nested", "conftest"),
        ]
        assert (rows[0]["line_before_2"], rows[0]["line_before_1"]) == ("before two", "before one")
        assert (rows[0]["line_after_1"], rows[0]["line_after_2"]) == ("after one", "after two")
        assert not {"category", "about_fixtures", "notes", "decision"} & set(rows[0])

    def test_skipped_repositories_are_listed_with_their_reason(self, v4_db, tmp_path):
        written = write_review_outputs(v4_db, tmp_path / "out")

        with written["skipped"].open(encoding="utf-8") as fh:
            rows = list(csv.reader(fh))
        assert tuple(rows[0]) == SKIPPED_CSV_FIELDNAMES
        assert rows[1] == ["owner/d", "java", "no_commit_at_or_before_cutoff"]

    def test_no_skipped_file_when_every_repository_was_analyzed(self, v4_db, tmp_path):
        out = tmp_path / "out"
        write_review_outputs(v4_db, out)
        assert (out / "rq5_skipped_repositories.csv").exists()

        with sqlite3.connect(v4_db) as conn:
            conn.execute("UPDATE repo_scan SET fetch_ok = 1, error_reason = NULL")
        written = write_review_outputs(v4_db, out)

        assert "skipped" not in written
        assert not (out / "rq5_skipped_repositories.csv").exists()  # the earlier file is removed


class TestMainRequiresSnapshotDate:
    def test_main_exits_without_a_snapshot_date(self):
        with patch.object(sys, "argv", ["rq5_agent_file_scan.py"]), pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 2
