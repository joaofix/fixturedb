"""RQ5 manual-coding support: the repository-level coding sheet, the rq5/
README, the fenced-code-block counts in the report, and the post-coding
analysis (`collection/research_questions/rq5_coding.py`)."""

import csv

import pytest

from collection.research_questions.rq5 import code_block_counts, generate_report
from collection.research_questions.rq5_coding import (
    CodingIncompleteError,
    agent_file_counts,
    compute_results,
    load_coded_sheet,
)
from collection.research_questions.rq5_coding import (
    generate_report as generate_coding_report,
)
from collection.research_questions.rq5_coding import (
    main as coding_main,
)
from collection.research_questions.rq5_coding import (
    write_report as write_coding_report,
)
from collection.rq5_agent_file_scan import (
    CATEGORY_VALUES,
    REPOSITORY_SHEET_FIELDNAMES,
    REPOSITORY_SHEET_NAME,
    _repo_row,
    _scan_result,
    initialise_rq5_db,
    load_fixture_match_rows,
    persist_result,
    record_scan_meta,
    snippet_row_ids,
    write_review_outputs,
)

ARDIC_TERMS = {"test", "tests", "testing", "tested"}


def _match(repo, file_name, keyword, line, *, keyword_list="fixture", in_code_block=False):
    return {
        "repo_name": repo,
        "file_name": file_name,
        "keyword_list": keyword_list,
        "keyword": keyword,
        "line_number": line,
        "line_context": f"line {line} mentions {keyword}",
        "line_before_2": "",
        "line_before_1": "",
        "line_after_1": "",
        "line_after_2": "",
        "in_code_block": in_code_block,
    }


def _persist(db_path, repo, language, matches=(), *, has_file=True):
    fixture_terms = sorted({m["keyword"] for m in matches if m["keyword_list"] == "fixture"})
    files = []
    if has_file:
        files.append(
            {
                "repo_name": repo,
                "file_name": "AGENTS.md",
                "file_type": "AGENTS.md",
                "language": language,
                "commit_sha": f"sha-{repo}",
                "has_test": False,
                "has_fixture": bool(fixture_terms),
                "test_match_count": 0,
                "fixture_match_count": len(fixture_terms),
                "matched_test_keywords": "",
                "matched_fixture_keywords": ",".join(fixture_terms),
                "github_url": f"https://github.com/{repo}/blob/sha/AGENTS.md",
            }
        )
    row = _repo_row(repo, language, "t", fetch_ok=True, commit_sha=f"sha-{repo}", num_agent_files=len(files))
    persist_result(_scan_result(row, files, list(matches)), db_path)


@pytest.fixture
def coded_db(tmp_path):
    """owner/a (python): fixtures at line 2, conftest at line 9 (in a code
    block), fixture at line 5 -- three matches in one file.
    owner/b (typescript): beforeEach.
    owner/c (python): agent file, no fixture match.
    owner/d (java): no agent file."""
    db_path = tmp_path / "rq5.db"
    initialise_rq5_db(db_path)
    record_scan_meta("2026-03-01", db_path)
    _persist(
        db_path,
        "owner/a",
        "python",
        [
            _match("owner/a", "AGENTS.md", "fixtures", 2),
            _match("owner/a", "AGENTS.md", "fixture", 5),
            _match("owner/a", "AGENTS.md", "conftest", 9, in_code_block=True),
            _match("owner/a", "AGENTS.md", "tests", 1, keyword_list="test"),
        ],
    )
    _persist(db_path, "owner/b", "typescript", [_match("owner/b", "AGENTS.md", "beforeEach", 4)])
    _persist(db_path, "owner/c", "python")
    _persist(db_path, "owner/d", "java", has_file=False)
    return db_path


def _read(path):
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _write_sheet(path, rows):
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=REPOSITORY_SHEET_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


class TestRepositoryCodingSheet:
    def test_one_row_per_repository_with_a_fixture_match_and_empty_coding(self, coded_db, tmp_path):
        out = tmp_path / "out"
        write_review_outputs(ARDIC_TERMS, db_path=coded_db, output_dir=out)
        rows = _read(out / REPOSITORY_SHEET_NAME)

        assert list(rows[0].keys()) == list(REPOSITORY_SHEET_FIELDNAMES)
        assert [(r["repository"], r["primary_language"], r["fixture_match_count"]) for r in rows] == [
            ("owner/a", "python", "3"),
            ("owner/b", "typescript", "1"),
        ]
        for row in rows:
            for column in ("code_fixture_guidance", "evidence_row_id", "category", "notes"):
                assert row[column] == ""

    def test_snippets_follow_the_term_reading_order(self, coded_db, tmp_path):
        out = tmp_path / "out"
        write_review_outputs(ARDIC_TERMS, db_path=coded_db, output_dir=out)
        snippets = _read(out / REPOSITORY_SHEET_NAME)[0]["fixture_snippets"].split("\n")

        assert [s.split(" | ")[0].split("] ")[1] for s in snippets] == ["conftest", "fixture", "fixtures"]

    def test_snippet_ids_are_the_match_sheet_row_positions(self, coded_db, tmp_path):
        out = tmp_path / "out"
        write_review_outputs(ARDIC_TERMS, db_path=coded_db, output_dir=out)
        match_sheet = _read(out / "rq5_fixture_matches.csv")

        for row in _read(out / REPOSITORY_SHEET_NAME):
            for snippet in row["fixture_snippets"].split("\n"):
                row_id = int(snippet[1 : snippet.index("]")])
                term, location, line = snippet.split("] ", 1)[1].split(" | ")
                match = match_sheet[row_id - 1]
                assert match["repository"] == row["repository"]
                assert match["matched_term"] == term
                assert f"{match['file_name']}:{match['line_number']}" == location
                assert match["matched_line"] == line

    def test_refuses_to_overwrite_a_sheet_with_manual_coding(self, coded_db, tmp_path):
        out = tmp_path / "out"
        write_review_outputs(ARDIC_TERMS, db_path=coded_db, output_dir=out)
        sheet = out / REPOSITORY_SHEET_NAME
        rows = _read(sheet)
        rows[0]["notes"] = "started coding"
        _write_sheet(sheet, rows)

        with pytest.raises(ValueError, match="already holds manual coding"):
            write_review_outputs(ARDIC_TERMS, db_path=coded_db, output_dir=out)
        assert _read(sheet)[0]["notes"] == "started coding"

    def test_snippet_row_ids_parses_every_prefix(self):
        assert snippet_row_ids("[3] fixture | A.md:1 | x\n[12] conftest | A.md:2 | [7] y") == {3, 12}


class TestReadme:
    def test_documents_every_allowed_coding_value(self, coded_db, tmp_path):
        out = tmp_path / "out"
        write_review_outputs(ARDIC_TERMS, db_path=coded_db, output_dir=out)
        readme = (out / "README.md").read_text()

        for value in (*CATEGORY_VALUES, "yes", "no", "unsure", "evidence_row_id", REPOSITORY_SHEET_NAME):
            assert value in readme


class TestCodeBlockCounts:
    def test_counts_per_term_and_overall(self, coded_db):
        counts = code_block_counts(load_fixture_match_rows(coded_db), ["fixture", "fixtures", "conftest", "beforeEach", "afterAll"])

        assert counts["conftest"] == (1, 1)
        assert counts["fixture"] == (1, 0)
        assert counts["afterAll"] == (0, 0)
        assert counts["all"] == (4, 1)

    def test_report_has_the_code_block_table_and_no_comparison_claim(self, coded_db):
        report = generate_report(db_path=coded_db)

        assert "## Fixture matches in fenced code blocks" in report
        assert "| conftest | 1 | 1 | 100.0% |" in report
        assert "| All terms | 4 | 1 | 25.0% |" in report
        assert "comparison" not in report.lower()
        assert "the keyword set of Ardic et al." in report


def _coded_rows(db_path, tmp_path, codes):
    """The real sheet for `db_path`, with `codes` (repository -> column values) filled in."""
    out = tmp_path / "out"
    write_review_outputs(ARDIC_TERMS, db_path=db_path, output_dir=out)
    sheet = out / REPOSITORY_SHEET_NAME
    rows = _read(sheet)
    for row in rows:
        row.update(codes.get(row["repository"], {}))
    _write_sheet(sheet, rows)
    return sheet


def _first_id(sheet, repo):
    row = next(r for r in _read(sheet) if r["repository"] == repo)
    return str(min(snippet_row_ids(row["fixture_snippets"])))


class TestLoadCodedSheet:
    def test_fails_when_a_row_is_uncoded(self, coded_db, tmp_path):
        sheet = _coded_rows(coded_db, tmp_path, {"owner/b": {"code_fixture_guidance": "no"}})

        with pytest.raises(CodingIncompleteError, match="1 of 2 rows are still uncoded.*owner/a"):
            load_coded_sheet(sheet)

    def test_fails_on_a_value_outside_the_allowed_ones(self, coded_db, tmp_path):
        sheet = _coded_rows(
            coded_db,
            tmp_path,
            {"owner/a": {"code_fixture_guidance": "maybe"}, "owner/b": {"code_fixture_guidance": "unsure", "category": "misc"}},
        )

        with pytest.raises(CodingIncompleteError) as exc:
            load_coded_sheet(sheet)
        assert "'maybe'" in str(exc.value)
        assert "unknown category misc" in str(exc.value)

    def test_yes_needs_a_category_and_an_evidence_id_from_its_own_snippets(self, coded_db, tmp_path):
        sheet = _coded_rows(
            coded_db,
            tmp_path,
            {"owner/a": {"code_fixture_guidance": "yes"}, "owner/b": {"code_fixture_guidance": "no"}},
        )
        foreign_id = _first_id(sheet, "owner/b")
        rows = _read(sheet)
        rows[0]["evidence_row_id"] = foreign_id
        _write_sheet(sheet, rows)

        with pytest.raises(CodingIncompleteError) as exc:
            load_coded_sheet(sheet)
        assert "owner/a: coded yes without a category" in str(exc.value)
        assert f"evidence_row_id '{foreign_id}' is not one of this repository's snippets" in str(exc.value)

    def test_main_exits_with_the_message_when_uncoded(self, coded_db, tmp_path, monkeypatch):
        sheet = _coded_rows(coded_db, tmp_path, {})
        monkeypatch.setattr("sys.argv", ["rq5_coding", "--sheet", str(sheet)])

        with pytest.raises(SystemExit, match="still uncoded"):
            coding_main()


class TestComputeResults:
    def test_shares_precision_and_categories(self, coded_db, tmp_path):
        sheet = _coded_rows(coded_db, tmp_path, {"owner/b": {"code_fixture_guidance": "unsure"}})
        rows = _read(sheet)
        rows[0].update(
            code_fixture_guidance="yes",
            evidence_row_id=_first_id(sheet, "owner/a"),
            category="strategy; location_placement",
        )
        _write_sheet(sheet, rows)

        results = compute_results(load_coded_sheet(sheet), agent_file_counts(coded_db))

        assert results["with_agent_file"]["all"] == 3
        assert results["with_agent_file"]["python"] == 2
        assert (results["yes"], results["no"], results["unsure"]) == (1, 0, 1)
        assert results["with_fixture_match"] == 2
        assert results["categories"] == {"strategy": 1, "location_placement": 1}

        report = generate_coding_report(results)
        assert "| Coded `yes` | 1 | 33.3% | 3 repositories with a root agent file |" in report
        assert "| Python | 2 | 1 | 50.0% |" in report
        assert "| TypeScript | 1 | 0 | 0.0% |" in report
        assert "Precision: 1 of 2 (50.0%); 1 coded `unsure`." in report
        assert "| strategy | 1 |" in report

        path = write_coding_report(tmp_path / "report", sheet_path=sheet, db_path=coded_db)
        assert path.name == "rq5_coding.md"
