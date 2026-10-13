"""RQ5 manual-coding support: the repository-level coding sheet, the rq5/
README, the fenced-code-block counts in the report, and the post-coding
analysis (`collection/research_questions/rq5_coding.py`)."""

import csv
import re

import pytest

from collection.research_questions.rq5 import code_block_counts, generate_report
from collection.research_questions.rq5_coding import (
    CodingIncompleteError,
    compute_results,
    guidance_file_counts,
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
    REPOSITORY_SHEET_FIELDNAMES,
    REPOSITORY_SHEET_NAME,
    SNIPPETS_MARKDOWN_NAME,
    _repo_row,
    _scan_result,
    carry_over_coding,
    fixture_match_keys,
    initialise_rq5_db,
    load_fixture_match_rows,
    persist_result,
    record_scan_meta,
    write_repository_coding_sheet,
    write_review_outputs,
    write_rq5_readme,
    write_snippets_markdown,
)


def _location(path):
    return "root" if "/" not in path else "nested"


def _match(repo, file_path, keyword, line, *, keyword_list="fixture", in_code_block=False):
    return {
        "repo_name": repo,
        "file_path": file_path,
        "location": _location(file_path),
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


def _agent_file(repo, path, language, matches):
    fixture_terms = sorted(
        {m["keyword"] for m in matches if m["keyword_list"] == "fixture" and m["file_path"] == path}
    )
    return {
        "repo_name": repo,
        "file_path": path,
        "file_name": path.rsplit("/", 1)[-1],
        "file_type": path.rsplit("/", 1)[-1],
        "location": _location(path),
        "symlink_target": "",
        "language": language,
        "commit_sha": f"sha-{repo}",
        "has_test": False,
        "has_fixture": bool(fixture_terms),
        "test_match_count": 0,
        "fixture_match_count": len(fixture_terms),
        "matched_test_keywords": "",
        "matched_fixture_keywords": ",".join(fixture_terms),
        "github_url": f"https://github.com/{repo}/blob/sha/{path}",
    }


def _persist(db_path, repo, language, matches=(), *, has_file=True, nested=()):
    """A root AGENTS.md (when `has_file`) plus the `nested` file paths."""
    files = [_agent_file(repo, "AGENTS.md", language, matches)] if has_file else []
    files += [_agent_file(repo, path, language, matches) for path in nested]
    row = _repo_row(
        repo, language, "t", fetch_ok=True, commit_sha=f"sha-{repo}",
        num_guidance_files=len(files), num_root_files=int(has_file),
    )
    persist_result(_scan_result(row, files, list(matches)), db_path)


@pytest.fixture
def coded_db(tmp_path):
    """owner/a (python): fixtures at line 2, conftest at line 9 (in a code
    block), fixture at line 5 -- three matches in one file.
    owner/b (typescript): beforeEach.
    owner/c (python): guidance file, no fixture match.
    owner/d (java): no guidance file."""
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
        write_review_outputs(db_path=coded_db, output_dir=out)
        rows = _read(out / REPOSITORY_SHEET_NAME)

        assert list(rows[0].keys()) == list(REPOSITORY_SHEET_FIELDNAMES)
        assert "fixture_snippets" not in rows[0]  # read in rq5_snippets.md instead
        assert "category" not in rows[0]  # categories are coded in rq5_category_sample.csv
        assert [(r["repository"], r["primary_language"], r["fixture_match_count"]) for r in rows] == [
            ("owner/a", "python", "3"),
            ("owner/b", "typescript", "1"),
        ]
        for row in rows:
            for column in ("decision", "notes"):
                assert row[column] == ""
        assert "evidence_row_id" not in rows[0]

    def test_every_cell_fits_a_spreadsheet_cell(self, coded_db, tmp_path):
        out = tmp_path / "out"
        write_review_outputs(db_path=coded_db, output_dir=out)
        assert all(len(v) <= 32767 and "\n" not in v for row in _read(out / REPOSITORY_SHEET_NAME) for v in row.values())

    def test_snippet_ids_in_the_markdown_are_the_match_sheet_row_positions(self, coded_db, tmp_path):
        out = tmp_path / "out"
        write_review_outputs(db_path=coded_db, output_dir=out)
        match_sheet = _read(out / "rq5_fixture_matches.csv")
        markdown = (out / SNIPPETS_MARKDOWN_NAME).read_text()

        headers = re.findall(r"^\*\*\[([\d, ]+)\]\*\* (.+?) · (root|nested) · \[(.+?):(\d+)\]", markdown, re.M)
        assert headers
        for ids, terms, location, path, line in headers:
            for row_id in ids.split(", "):
                match = match_sheet[int(row_id) - 1]
                assert match["matched_term"] in terms.split(", ")
                assert (match["location"], match["file_path"], match["line_number"]) == (location, path, line)

    def test_the_sheet_writer_refuses_to_overwrite_manual_coding(self, coded_db, tmp_path):
        out = tmp_path / "out"
        write_review_outputs(db_path=coded_db, output_dir=out)
        sheet = out / REPOSITORY_SHEET_NAME
        rows = _read(sheet)
        rows[0]["notes"] = "started coding"
        _write_sheet(sheet, rows)

        with pytest.raises(ValueError, match="already holds manual coding"):
            write_repository_coding_sheet(load_fixture_match_rows(coded_db), coded_db, out)
        assert _read(sheet)[0]["notes"] == "started coding"


class TestSnippetsMarkdown:
    def test_sections_follow_the_sheet_rows_and_leave_the_csv_alone(self, coded_db, tmp_path):
        out = tmp_path / "out"
        write_review_outputs(db_path=coded_db, output_dir=out)
        sheet_before = (out / REPOSITORY_SHEET_NAME).read_bytes()
        markdown = (out / SNIPPETS_MARKDOWN_NAME).read_text()

        sections = [line for line in markdown.splitlines() if line.startswith("## ")]
        repos = [row["repository"] for row in _read(out / REPOSITORY_SHEET_NAME)]
        assert sections == [f"## {n}. {repo}" for n, repo in enumerate(repos, start=1)]
        assert "python · 3 fixture matches · root" in markdown
        assert "typescript · 1 fixture match · root\n" in markdown

        write_snippets_markdown(load_fixture_match_rows(coded_db), coded_db, out)
        assert (out / REPOSITORY_SHEET_NAME).read_bytes() == sheet_before

    def test_each_line_has_its_ids_link_context_and_code_block_marker(self, coded_db, tmp_path):
        path = write_snippets_markdown(load_fixture_match_rows(coded_db), coded_db, tmp_path)
        markdown = path.read_text()
        # Row ids match the match sheet: owner/a's conftest is the third match row.
        assert "**[3]** conftest · root · [AGENTS.md:9](https://github.com/owner/a/blob/sha/AGENTS.md#L9)" in markdown
        assert "AGENTS.md#L9) · in a fenced code block" in markdown
        assert "> line 9 mentions conftest" in markdown
        # Reading order: conftest before fixture before fixtures.
        section_a = markdown.split("## 1. owner/a")[1].split("## 2.")[0]
        assert section_a.index("conftest") < section_a.index("**[2]** fixture ·") < section_a.index("fixtures ·")

    def test_one_line_matching_two_terms_is_shown_once_with_both_ids(self, tmp_path):
        db_path = tmp_path / "rq5.db"
        initialise_rq5_db(db_path)
        _persist(
            db_path,
            "owner/x",
            "python",
            [_match("owner/x", "AGENTS.md", "fixture", 4), _match("owner/x", "AGENTS.md", "fixtures", 4)],
        )

        markdown = write_snippets_markdown(load_fixture_match_rows(db_path), db_path, tmp_path).read_text()

        assert "**[1, 2]** fixture, fixtures · root · " in markdown
        assert markdown.count("> line 4 mentions") == 1
        assert "python · 2 fixture matches · root" in markdown

    def test_fence_is_longer_than_backticks_inside_the_context(self, tmp_path):
        db_path = tmp_path / "rq5.db"
        initialise_rq5_db(db_path)
        match = _match("owner/x", "AGENTS.md", "fixture", 4)
        match["line_before_1"] = "```python"
        _persist(db_path, "owner/x", "python", [match])

        markdown = write_snippets_markdown(load_fixture_match_rows(db_path), db_path, tmp_path).read_text()

        assert "````text\n" in markdown
        assert markdown.rstrip().endswith("````")


class TestReadme:
    def test_states_the_decision_rule(self, tmp_path):
        readme = write_rq5_readme(tmp_path).read_text()

        assert "One verdict per\n  repository, over all of its guidance files." in readme
        assert "Description counts as guidance" in readme
        assert "One such match is enough" in readme
        assert "product or domain term" in readme
        assert "fixtures used by tests" in readme
        assert "inferred from the terms near the match" in readme
        assert "Decide from the matched lines and the lines around them only" in readme

    def test_points_to_the_category_coding_files(self, tmp_path):
        readme = write_rq5_readme(tmp_path).read_text()

        assert "this study's own categories" in readme
        assert "rq5_category_sample.csv" in readme and "rq5_category_codebook.yaml" in readme
        assert "`category`" not in readme
        assert "Ardic" not in readme
        assert "Allowed `category` values" not in readme

    def test_documents_every_allowed_coding_value(self, coded_db, tmp_path):
        out = tmp_path / "out"
        write_review_outputs(db_path=coded_db, output_dir=out)
        readme = (out / "README.md").read_text()

        for value in (
            "yes", "no", "unsure", REPOSITORY_SHEET_NAME, SNIPPETS_MARKDOWN_NAME,
            "fixture_location", "AGENTS.md, CLAUDE.md, GEMINI.md", "carry_over_coding",
        ):
            assert value in readme
        assert "referred" not in readme


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
    write_review_outputs(db_path=db_path, output_dir=out)
    sheet = out / REPOSITORY_SHEET_NAME
    rows = _read(sheet)
    for row in rows:
        row.update(codes.get(row["repository"], {}))
    _write_sheet(sheet, rows)
    return sheet


class TestLoadCodedSheet:
    def test_fails_when_a_row_is_uncoded(self, coded_db, tmp_path):
        sheet = _coded_rows(coded_db, tmp_path, {"owner/b": {"decision": "no"}})

        with pytest.raises(CodingIncompleteError, match="1 of 2 rows are still uncoded.*owner/a"):
            load_coded_sheet(sheet)

    def test_fails_on_a_value_outside_the_allowed_ones(self, coded_db, tmp_path):
        sheet = _coded_rows(
            coded_db,
            tmp_path,
            {"owner/a": {"decision": "maybe"}, "owner/b": {"decision": "unsure"}},
        )

        with pytest.raises(CodingIncompleteError, match="'maybe'"):
            load_coded_sheet(sheet)

    def test_an_extra_category_column_from_the_old_format_is_ignored(self, coded_db, tmp_path):
        sheet = tmp_path / "old_format.csv"
        sheet.write_text(
            "repository,primary_language,fixture_match_count,fixture_location,decision,category,notes\n"
            "owner/a,python,3,root,yes,,\n"
        )

        assert load_coded_sheet(sheet) == [{"repository": "owner/a", "language": "python", "decision": "yes"}]

    def test_main_exits_with_the_message_when_uncoded(self, coded_db, tmp_path, monkeypatch):
        sheet = _coded_rows(coded_db, tmp_path, {})
        monkeypatch.setattr("sys.argv", ["rq5_coding", "--sheet", str(sheet)])

        with pytest.raises(SystemExit, match="still uncoded"):
            coding_main()


class TestComputeResults:
    def test_shares_precision_and_the_yes_or_unsure_share(self, coded_db, tmp_path):
        sheet = _coded_rows(coded_db, tmp_path, {"owner/a": {"decision": "yes"}, "owner/b": {"decision": "unsure"}})

        results = compute_results(load_coded_sheet(sheet), guidance_file_counts(coded_db))

        assert results["with_guidance_file"]["all"] == 3
        assert results["with_guidance_file"]["python"] == 2
        assert (results["yes"], results["no"], results["unsure"]) == (1, 0, 1)
        assert results["with_fixture_match"] == 2

        report = generate_coding_report(results)
        assert "| Coded `yes` | 1 | 33.3% | 3 repositories with a guidance file |" in report
        assert "| Coded `yes` or `unsure` (every `unsure` counted as `yes`) | 2 | 66.7% | 3 repositories" in report
        assert "| Python | 2 | 1 | 50.0% |" in report
        assert "| TypeScript | 1 | 0 | 0.0% |" in report
        assert "Precision: 1 of 2 (50.0%); 1 coded `unsure`." in report
        assert "Not started" in report

        path, warning = write_coding_report(tmp_path / "report", sheet_path=sheet, db_path=coded_db)
        assert path.name == "rq5_coding.md"
        assert warning is None


@pytest.fixture
def nested_db(tmp_path):
    """owner/a: fixture matches in its root AGENTS.md and in a nested
    docs/AGENTS.md. owner/g: a fixture match only in a nested web/CLAUDE.md."""
    db_path = tmp_path / "nested.db"
    initialise_rq5_db(db_path)
    record_scan_meta("2026-03-01", db_path)
    _persist(
        db_path,
        "owner/a",
        "python",
        [
            _match("owner/a", "AGENTS.md", "fixture", 5),
            _match("owner/a", "docs/AGENTS.md", "conftest", 2),
            _match("owner/a", "docs/AGENTS.md", "fixture", 8),
        ],
        nested=["docs/AGENTS.md"],
    )
    _persist(
        db_path,
        "owner/g",
        "typescript",
        [_match("owner/g", "web/CLAUDE.md", "beforeEach", 3)],
        has_file=False,
        nested=["web/CLAUDE.md"],
    )
    return db_path


class TestSheetWithNestedFiles:
    def test_fixture_location_says_where_the_matches_are(self, nested_db, tmp_path):
        out = tmp_path / "out"
        write_review_outputs(db_path=nested_db, output_dir=out)
        rows = {r["repository"]: r for r in _read(out / REPOSITORY_SHEET_NAME)}
        assert rows["owner/a"]["fixture_location"] == "root+nested"
        assert rows["owner/g"]["fixture_location"] == "nested"
        assert rows["owner/a"]["fixture_match_count"] == "3"

    def test_markdown_orders_by_term_then_root_before_nested(self, nested_db, tmp_path):
        markdown = write_snippets_markdown(load_fixture_match_rows(nested_db), nested_db, tmp_path).read_text()
        section = markdown.split("## 1. owner/a")[1].split("## 2.")[0]
        located = re.findall(r"^\*\*\[[\d, ]+\]\*\* (.+?) · (root|nested) · \[(.+?)\]", section, re.M)
        assert located == [
            ("conftest", "nested", "docs/AGENTS.md:2"),
            ("fixture", "root", "AGENTS.md:5"),
            ("fixture", "nested", "docs/AGENTS.md:8"),
        ]

    def test_match_sheet_lists_root_matches_before_nested_ones(self, nested_db, tmp_path):
        out = tmp_path / "out"
        write_review_outputs(db_path=nested_db, output_dir=out)
        rows = _read(out / "rq5_fixture_matches.csv")
        assert [(r["repository"], r["location"], r["file_path"]) for r in rows] == [
            ("owner/a", "root", "AGENTS.md"),
            ("owner/a", "nested", "docs/AGENTS.md"),
            ("owner/a", "nested", "docs/AGENTS.md"),
            ("owner/g", "nested", "web/CLAUDE.md"),
        ]

    def test_snippets_markdown_shows_location_and_link_to_the_nested_file(self, nested_db, tmp_path):
        markdown = write_snippets_markdown(load_fixture_match_rows(nested_db), nested_db, tmp_path).read_text()
        assert "python · 3 fixture matches · root+nested" in markdown
        assert "conftest · nested · [docs/AGENTS.md:2](https://github.com/owner/a/blob/sha/docs/AGENTS.md#L2)" in markdown


def _sheet(path, rows):
    """A coding sheet with the given rows (missing columns left empty)."""
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=REPOSITORY_SHEET_FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in REPOSITORY_SHEET_FIELDNAMES})
    return path


def _matches(path, rows, *, legacy=False):
    """A rq5_fixture_matches.csv with (repository, term, path, line, text) rows;
    `legacy` writes the oldest format (`file_name`, no location)."""
    fields = (
        ["repository", "file_name", "line_number", "matched_term", "matched_line"]
        if legacy
        else ["repository", "file_path", "location", "line_number", "matched_term", "matched_line"]
    )
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for repo, term, file_path, line, text in rows:
            writer.writerow({
                "repository": repo, "file_path": file_path, "file_name": file_path, "location": "root",
                "line_number": line, "matched_term": term, "matched_line": text,
            })
    return path


class TestFixtureMatchKeys:
    def test_keys_ignore_row_order_and_location(self, tmp_path):
        new = _matches(tmp_path / "new.csv", [("o/r", "fixture", "AGENTS.md", 3, "a | b"), ("o/r", "conftest", "docs/T.md", 1, "x")])
        old = _matches(tmp_path / "old.csv", [("o/r", "conftest", "docs/T.md", 1, "x"), ("o/r", "fixture", "AGENTS.md", 3, "a | b")], legacy=True)
        assert fixture_match_keys(new) == fixture_match_keys(old)
        assert fixture_match_keys(new)["o/r"] == {("fixture", "AGENTS.md", "3", "a | b"), ("conftest", "docs/T.md", "1", "x")}

    def test_keys_ignore_the_source_column_of_the_previous_format(self, tmp_path):
        path = tmp_path / "old.csv"
        path.write_text(
            "repository,file_path,source,line_number,matched_term,matched_line\n"
            "o/r,CONTRIBUTING.md,referred,4,fixture,x\n"
        )
        assert fixture_match_keys(path) == {"o/r": {("fixture", "CONTRIBUTING.md", "4", "x")}}


class TestCarryOverCoding:
    def _new(self, nested_db, tmp_path):
        """The real sheet and match file written for `nested_db`."""
        out = tmp_path / "out"
        write_review_outputs(db_path=nested_db, output_dir=out)
        return out / REPOSITORY_SHEET_NAME, out / "rq5_fixture_matches.csv"

    def _carry(self, tmp_path, old_rows, old_matches, new_sheet, new_matches):
        old_sheet = _sheet(tmp_path / "old_sheet.csv", old_rows)
        old_csv = _matches(tmp_path / "old_matches.csv", old_matches)
        return carry_over_coding(old_sheet, new_sheet, old_matches=old_csv, new_matches=new_matches)

    G_MATCH = ("owner/g", "beforeEach", "web/CLAUDE.md", 3, "line 3 mentions beforeEach")

    def test_unchanged_matches_keep_decision_and_notes(self, nested_db, tmp_path):
        new_sheet, new_matches = self._new(nested_db, tmp_path)
        outcome = self._carry(
            tmp_path, [{"repository": "owner/g", "decision": "no", "notes": "data only"}], [self.G_MATCH], new_sheet, new_matches
        )
        row = {r["repository"]: r for r in _read(new_sheet)}["owner/g"]
        assert (row["decision"], row["notes"]) == ("no", "data only")
        assert outcome["unchanged"] == ["owner/g"]

    @pytest.mark.parametrize("decision", ["yes", "no", "unsure"])
    def test_changed_matches_keep_every_decision_as_it_was(self, nested_db, tmp_path, decision):
        new_sheet, new_matches = self._new(nested_db, tmp_path)
        outcome = self._carry(
            tmp_path,
            [{"repository": "owner/a", "decision": decision, "notes": "n"}],
            [("owner/a", "fixture", "CONTRIBUTING.md", 5, "line 5 mentions fixture")],
            new_sheet, new_matches,
        )
        row = {r["repository"]: r for r in _read(new_sheet)}["owner/a"]
        assert (row["decision"], row["notes"]) == (decision, "n")
        assert outcome["matches_changed"] == ["owner/a"]

    def test_a_match_moving_to_another_line_counts_as_changed(self, nested_db, tmp_path):
        new_sheet, new_matches = self._new(nested_db, tmp_path)
        moved = ("owner/g", "beforeEach", "web/CLAUDE.md", 4, "line 3 mentions beforeEach")
        outcome = self._carry(tmp_path, [{"repository": "owner/g", "decision": "no"}], [moved], new_sheet, new_matches)
        assert outcome["matches_changed"] == ["owner/g"]
        assert {r["repository"]: r for r in _read(new_sheet)}["owner/g"]["decision"] == "no"

    def test_repositories_no_longer_in_the_sheet_are_dropped_and_reported(self, nested_db, tmp_path):
        new_sheet, new_matches = self._new(nested_db, tmp_path)
        outcome = self._carry(
            tmp_path, [{"repository": "owner/gone", "decision": "yes"}], [], new_sheet, new_matches
        )
        assert outcome["removed"] == ["owner/gone"]
        assert "owner/gone" not in {r["repository"] for r in _read(new_sheet)}

    def test_uncoded_old_rows_and_new_repositories_are_left_uncoded(self, nested_db, tmp_path):
        new_sheet, new_matches = self._new(nested_db, tmp_path)
        before = _read(new_sheet)
        outcome = self._carry(tmp_path, [{"repository": "owner/a"}], [], new_sheet, new_matches)
        assert _read(new_sheet) == before
        assert outcome == {"unchanged": [], "matches_changed": [], "removed": []}

    def test_refuses_to_overwrite_coding_already_in_the_new_sheet(self, nested_db, tmp_path):
        new_sheet, new_matches = self._new(nested_db, tmp_path)
        rows = _read(new_sheet)
        rows[0]["decision"] = "unsure"
        _write_sheet(new_sheet, rows)
        with pytest.raises(ValueError, match="already holds coding"):
            self._carry(tmp_path, [{"repository": "owner/a", "decision": "yes"}], [], new_sheet, new_matches)
        assert _read(new_sheet)[0]["decision"] == "unsure"

    def test_the_same_scan_carries_everything_over_unchanged(self, nested_db, tmp_path):
        new_sheet, new_matches = self._new(nested_db, tmp_path)
        coded = tmp_path / "coded.csv"
        rows = _read(new_sheet)
        rows[0].update(decision="yes", notes="tips")
        rows[1].update(decision="no", notes="x")
        _write_sheet(coded, rows)
        outcome = carry_over_coding(coded, new_sheet, old_matches=new_matches, new_matches=new_matches)
        assert outcome["unchanged"] == ["owner/a", "owner/g"]
        assert _read(new_sheet) == rows

    def test_an_old_sheet_with_the_previous_columns_carries_over(self, nested_db, tmp_path):
        new_sheet, new_matches = self._new(nested_db, tmp_path)
        old_sheet = tmp_path / "old.csv"
        old_sheet.write_text(
            "repository,primary_language,fixture_match_count,fixture_source,decision,category,notes\n"
            "owner/g,typescript,1,referred,yes,tips,kept\n"
        )
        carry_over_coding(old_sheet, new_sheet, old_matches=_matches(tmp_path / "m.csv", []), new_matches=new_matches)
        row = {r["repository"]: r for r in _read(new_sheet)}["owner/g"]
        assert (row["fixture_location"], row["decision"], row["notes"]) == ("nested", "yes", "kept")
        assert "category" not in row


class TestWriteReviewOutputsKeepsCoding:
    """A rescan rewrites the outputs over a coded sheet: the coding is backed up
    and carried over, repositories that left are dropped, new ones are added
    uncoded."""

    def _rescan(self, nested_db, tmp_path):
        out, backups = tmp_path / "out", tmp_path / "backups"
        write_review_outputs(db_path=nested_db, output_dir=out, backup_dir=backups)
        rows = _read(out / REPOSITORY_SHEET_NAME)
        rows[0].update(decision="unsure", notes="first pass")  # owner/a
        rows[1].update(decision="yes", notes="tips")  # owner/g
        _write_sheet(out / REPOSITORY_SHEET_NAME, rows)
        coded_before = (out / REPOSITORY_SHEET_NAME).read_bytes()
        matches_before = (out / "rq5_fixture_matches.csv").read_bytes()

        # The new scan: owner/a loses its nested matches, owner/g leaves, owner/n is new.
        _persist(nested_db, "owner/a", "python", [_match("owner/a", "AGENTS.md", "fixture", 5)])
        _persist(nested_db, "owner/g", "typescript", has_file=False, nested=["web/CLAUDE.md"])
        _persist(nested_db, "owner/n", "java", [_match("owner/n", "pkg/AGENTS.md", "fixtures", 1)], has_file=False, nested=["pkg/AGENTS.md"])
        written = write_review_outputs(db_path=nested_db, output_dir=out, backup_dir=backups)
        return out, backups, written, coded_before, matches_before

    def test_coding_is_kept_removed_repositories_dropped_and_new_ones_added(self, nested_db, tmp_path):
        out, _, _, _, _ = self._rescan(nested_db, tmp_path)
        rows = {r["repository"]: r for r in _read(out / REPOSITORY_SHEET_NAME)}
        assert set(rows) == {"owner/a", "owner/n"}
        assert (rows["owner/a"]["decision"], rows["owner/a"]["notes"], rows["owner/a"]["fixture_match_count"]) == (
            "unsure", "first pass", "1",
        )
        assert (rows["owner/n"]["decision"], rows["owner/n"]["notes"]) == ("", "")

    def test_the_old_sheet_and_matches_are_backed_up_byte_for_byte(self, nested_db, tmp_path):
        _, backups, _, coded_before, matches_before = self._rescan(nested_db, tmp_path)
        [sheet_backup] = backups.glob("rq5_coding_sheet_backup_*[0-9]Z.csv")
        [matches_backup] = backups.glob("rq5_fixture_matches_backup_*.csv")
        assert sheet_backup.read_bytes() == coded_before
        assert matches_backup.read_bytes() == matches_before

    def test_the_outcome_report_lists_each_coded_repository(self, nested_db, tmp_path):
        _, _, written, _, _ = self._rescan(nested_db, tmp_path)
        report = {r["repository"]: r for r in _read(written["carry_over"])}
        assert (report["owner/a"]["outcome"], report["owner/a"]["decision"]) == ("matches_changed", "unsure")
        assert (report["owner/g"]["outcome"], report["owner/g"]["decision"], report["owner/g"]["notes"]) == (
            "removed", "yes", "tips",
        )
        assert "owner/n" not in report

    def test_an_uncoded_sheet_is_rewritten_without_a_backup(self, nested_db, tmp_path):
        out, backups = tmp_path / "out", tmp_path / "backups"
        write_review_outputs(db_path=nested_db, output_dir=out, backup_dir=backups)
        written = write_review_outputs(db_path=nested_db, output_dir=out, backup_dir=backups)
        assert "carry_over" not in written
        assert not backups.exists()
