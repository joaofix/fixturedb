"""RQ5 category coding: the random category sample, the codebook, the coded
prefix, the category analysis in `rq5_coding`, and the agreement support
(`collection/rq5_category_sample.py`)."""

import csv
from collections import Counter

import pytest

from collection.research_questions.rq5_coding import (
    checkpoint_warning,
    compute_category_results,
    compute_results,
    generate_report,
)
from collection.rq5_category_sample import (
    AGREEMENT_SEED,
    AGREEMENT_SHEET_NAME,
    AGREEMENT_SIZE,
    EXPECTED_CHECKPOINTS,
    EXPECTED_POPULATION,
    SAMPLE_SEED,
    CODEBOOK_NAME,
    CODEBOOK_TEMPLATE,
    SAMPLE_FIELDNAMES,
    SAMPLE_NAME,
    Category,
    CategoryCodingError,
    check_checkpoints,
    check_sample_matches_population,
    checkpoint_label,
    checkpoint_sizes,
    cohens_kappa,
    compare_codings,
    load_codebook,
    load_coded_sample,
    load_snippets,
    load_yes_population,
    sample_margin_of_error,
    shuffle_population,
    snippets_cell,
    write_agreement_sheet,
    write_category_sample,
    write_codebook_template,
)
from collection.paths import ROOT_DIR
from collection.rq5_agent_file_scan import FIXTURE_MATCHES_CSV_NAME, REPOSITORY_SHEET_NAME
from collection.sampling import margin_of_error

MATCH_FIELDS = (
    "repository", "file_path", "location", "line_number", "matched_term",
    "line_before_2", "line_before_1", "matched_line", "line_after_1", "line_after_2", "in_code_block",
)
LANGUAGES = ("python", "typescript", "java", "javascript")
CODEBOOK = """\
categories:
  - code: location
    name: Fixture location
    definition: Says where fixtures live.
  - code: cleanup
    name: Cleanup
    definition: Says how fixtures clean up.
"""


def _read(path):
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _write(path, fieldnames, rows):
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def rq5_dir(tmp_path):
    """A coding sheet with 40 repositories coded yes (o/r00..o/r39), one no and
    one unsure, and a matches file: each repository has one fixture match in
    AGENTS.md; o/r00 also has a nested line matching two terms."""
    out = tmp_path / "rq5"
    out.mkdir()
    sheet, matches = [], []
    names = [f"o/r{i:02d}" for i in range(40)] + ["o/zno", "o/zunsure"]
    for i, name in enumerate(names):
        decision = "yes" if i < 40 else ("no" if name == "o/zno" else "unsure")
        sheet.append({
            "repository": name, "primary_language": LANGUAGES[i % 4], "fixture_match_count": "1",
            "fixture_location": "root", "decision": decision, "notes": "",
        })
        matches.append({
            "repository": name, "file_path": "AGENTS.md", "location": "root", "line_number": "3",
            "matched_term": "fixture", "line_before_2": "far before", "line_before_1": "before " + name,
            "matched_line": "use the fixture in " + name, "line_after_1": "after " + name,
            "line_after_2": "far after", "in_code_block": "0",
        })
    for term in ("conftest", "fixtures"):
        matches.append({
            "repository": "o/r00", "file_path": "tests/AGENTS.md", "location": "nested", "line_number": "7",
            "matched_term": term, "line_before_2": "", "line_before_1": "", "matched_line": "conftest fixtures",
            "line_after_1": "", "line_after_2": "", "in_code_block": "0",
        })
    _write(out / REPOSITORY_SHEET_NAME, list(sheet[0]), sheet)
    _write(out / FIXTURE_MATCHES_CSV_NAME, MATCH_FIELDS, matches)
    return out


def _sample(rq5_dir):
    return write_category_sample(rq5_dir, expected_population=40, expected_checkpoints=(29, 37))


def _code(rq5_dir, codes_by_order, *, codebook=CODEBOOK):
    """Fill `categories` of the sample rows given by sample_order."""
    (rq5_dir / CODEBOOK_NAME).write_text(codebook, encoding="utf-8")
    path = rq5_dir / SAMPLE_NAME
    rows = _read(path)
    for row in rows:
        row["categories"] = codes_by_order.get(int(row["sample_order"]), row["categories"])
    _write(path, SAMPLE_FIELDNAMES, rows)
    return rows


class TestCheckpointsAndMarginOfError:
    def test_the_design_checkpoints_for_556_are_83_and_228(self):
        assert checkpoint_sizes(556) == (83, 228)
        assert check_checkpoints(556) == (83, 228)

    def test_fails_loudly_on_another_population_or_other_checkpoints(self):
        with pytest.raises(CategoryCodingError, match="fixes the population at 556"):
            check_checkpoints(555)
        with pytest.raises(CategoryCodingError, match=r"expected \(82, 228\)"):
            check_checkpoints(556, expected_checkpoints=(82, 228))

    def test_margin_of_error_inverts_cochran_at_the_checkpoints(self):
        assert sample_margin_of_error(83, 556) == pytest.approx(0.0993, abs=1e-4)
        assert sample_margin_of_error(228, 556) == pytest.approx(0.0499, abs=1e-4)
        assert sample_margin_of_error(83, 556) <= 0.10 and sample_margin_of_error(228, 556) <= 0.05

    def test_margin_of_error_edge_cases(self):
        assert margin_of_error(556, 556) == 0.0
        with pytest.raises(ValueError):
            margin_of_error(0, 556)
        with pytest.raises(ValueError):
            margin_of_error(557, 556)

    def test_checkpoint_labels(self):
        assert [checkpoint_label(o, (83, 228)) for o in (1, 83, 84, 228, 229)] == ["83", "83", "228", "228", ""]


class TestPopulationAndShuffle:
    def test_population_is_the_yes_rows_in_sheet_order_with_their_sheet_row(self, rq5_dir):
        population = load_yes_population(rq5_dir / REPOSITORY_SHEET_NAME)
        assert [p["repository"] for p in population] == [f"o/r{i:02d}" for i in range(40)]
        assert population[0]["sheet_row"] == 1 and population[-1]["sheet_row"] == 40

    def test_fails_when_a_decision_is_missing(self, rq5_dir):
        sheet = rq5_dir / REPOSITORY_SHEET_NAME
        rows = _read(sheet)
        rows[5]["decision"] = ""
        _write(sheet, list(rows[0]), rows)
        with pytest.raises(CategoryCodingError, match="without a final decision"):
            load_yes_population(sheet)

    def test_shuffle_is_a_reproducible_permutation(self):
        items = [{"repository": str(i)} for i in range(100)]
        first, again, other = shuffle_population(items, 20261012), shuffle_population(items, 20261012), shuffle_population(items, 1)
        assert first == again
        assert first != other
        assert sorted(r["repository"] for r in first) == sorted(r["repository"] for r in items)
        assert items == [{"repository": str(i)} for i in range(100)]  # input untouched


class TestSnippets:
    def test_one_entry_per_line_with_every_id_and_term(self, rq5_dir):
        snippets = load_snippets(rq5_dir / FIXTURE_MATCHES_CSV_NAME)
        root, nested = snippets["o/r00"]
        assert (root["ids"], root["terms"]) == ([1], ["fixture"])
        assert (nested["ids"], nested["terms"]) == ([43, 44], ["conftest", "fixtures"])

    def test_cell_has_ids_path_matched_line_and_one_line_of_context(self, rq5_dir):
        cell = snippets_cell(load_snippets(rq5_dir / FIXTURE_MATCHES_CSV_NAME)["o/r00"], 1)
        assert cell == (
            "[1] AGENTS.md:3 (fixture)\n  before o/r00\n> use the fixture in o/r00\n  after o/r00\n\n"
            "[43, 44] tests/AGENTS.md:7 (conftest, fixtures)\n> conftest fixtures"
        )
        assert "far before" not in cell

    def test_a_cell_over_the_limit_is_cut_with_a_pointer_to_the_markdown(self, rq5_dir):
        entries = load_snippets(rq5_dir / FIXTURE_MATCHES_CSV_NAME)["o/r00"]
        limit = len(snippets_cell(entries, 7)) - 1  # one character too long for the whole text
        cell = snippets_cell(entries, 7, limit=limit)
        assert len(cell) <= limit
        assert cell.startswith("[1] AGENTS.md:3")
        assert cell.endswith("[1 more matched lines not shown: see section 7 of rq5_snippets.md]")


class TestWriteCategorySample:
    def test_every_yes_repository_once_in_shuffled_order_with_checkpoints(self, rq5_dir):
        rows = _read(_sample(rq5_dir))
        assert list(rows[0]) == list(SAMPLE_FIELDNAMES)
        assert "fixture_match_count" not in rows[0]
        assert [int(r["sample_order"]) for r in rows] == list(range(1, 41))
        assert sorted(r["repository"] for r in rows) == [f"o/r{i:02d}" for i in range(40)]
        assert [r["repository"] for r in rows] != [f"o/r{i:02d}" for i in range(40)]
        assert [r["checkpoint"] for r in rows] == ["29"] * 29 + ["37"] * 8 + [""] * 3
        assert all(r[c] == "" for r in rows for c in ("open_code", "categories", "notes"))
        by_repo = {r["repository"]: r for r in rows}
        assert by_repo["o/r01"]["primary_language"] == "typescript"
        assert by_repo["o/r01"]["snippets"].startswith("[2] AGENTS.md:3 (fixture)")

    def test_rewriting_gives_the_same_sample_and_leaves_the_sheet_alone(self, rq5_dir):
        sheet_before = (rq5_dir / REPOSITORY_SHEET_NAME).read_bytes()
        first = _sample(rq5_dir).read_bytes()
        assert _sample(rq5_dir).read_bytes() == first
        assert (rq5_dir / REPOSITORY_SHEET_NAME).read_bytes() == sheet_before

    def test_refuses_to_overwrite_a_coded_sample(self, rq5_dir):
        _sample(rq5_dir)
        _code(rq5_dir, {1: "location"})
        coded = (rq5_dir / SAMPLE_NAME).read_bytes()
        with pytest.raises(CategoryCodingError, match="refusing to overwrite"):
            _sample(rq5_dir)
        assert (rq5_dir / SAMPLE_NAME).read_bytes() == coded

    def test_fails_loudly_when_the_population_is_not_the_designed_one(self, rq5_dir):
        with pytest.raises(CategoryCodingError, match="fixes the population at 556"):
            write_category_sample(rq5_dir)
        assert not (rq5_dir / SAMPLE_NAME).exists()


class TestCodebook:
    def test_template_is_written_once_and_never_overwritten(self, rq5_dir):
        assert write_codebook_template(rq5_dir) == rq5_dir / CODEBOOK_NAME
        assert load_codebook(rq5_dir / CODEBOOK_NAME) == []
        (rq5_dir / CODEBOOK_NAME).write_text(CODEBOOK, encoding="utf-8")
        assert write_codebook_template(rq5_dir) is None
        assert (rq5_dir / CODEBOOK_NAME).read_text(encoding="utf-8") == CODEBOOK
        assert "categories: []" in CODEBOOK_TEMPLATE

    def test_loads_code_name_and_definition(self, rq5_dir):
        (rq5_dir / CODEBOOK_NAME).write_text(CODEBOOK, encoding="utf-8")
        assert load_codebook(rq5_dir / CODEBOOK_NAME) == [
            Category("location", "Fixture location", "Says where fixtures live."),
            Category("cleanup", "Cleanup", "Says how fixtures clean up."),
        ]

    @pytest.mark.parametrize(
        "entry,message",
        [
            ("  - {code: Two Words, name: N, definition: D}", "not one snake_case word"),
            ("  - {code: ok, name: N}", "name and definition are required"),
            ("  - {code: ok, name: N, definition: D}\n  - {code: ok, name: M, definition: E}", "duplicate codes: ok"),
        ],
    )
    def test_rejects_invalid_entries(self, rq5_dir, entry, message):
        (rq5_dir / CODEBOOK_NAME).write_text("categories:\n" + entry + "\n", encoding="utf-8")
        with pytest.raises(CategoryCodingError, match=message):
            load_codebook(rq5_dir / CODEBOOK_NAME)


class TestCodedPrefix:
    def _load(self, rq5_dir):
        return load_coded_sample(rq5_dir / SAMPLE_NAME, load_codebook(rq5_dir / CODEBOOK_NAME))

    def test_the_prefix_is_the_rows_coded_from_the_top(self, rq5_dir):
        _sample(rq5_dir)
        _code(rq5_dir, {1: "location", 2: "location; cleanup", 3: "cleanup"})
        sample = self._load(rq5_dir)
        assert (sample.size, sample.population, sample.checkpoints, sample.checkpoint_reached) == (3, 40, (29, 37), None)

    def test_coding_out_of_order_fails(self, rq5_dir):
        _sample(rq5_dir)
        _code(rq5_dir, {1: "location", 2: "", 3: "cleanup"})
        with pytest.raises(CategoryCodingError, match=r"coding out of order: the coded prefix ends at sample_order 1"):
            self._load(rq5_dir)

    def test_a_code_outside_the_codebook_fails(self, rq5_dir):
        _sample(rq5_dir)
        _code(rq5_dir, {1: "location; mocking"})
        with pytest.raises(CategoryCodingError, match="not in the codebook: mocking"):
            self._load(rq5_dir)

    def test_a_stale_sample_fails(self, rq5_dir):
        _sample(rq5_dir)
        _code(rq5_dir, {})
        sheet = rq5_dir / REPOSITORY_SHEET_NAME
        rows = _read(sheet)
        rows[0]["decision"] = "no"
        _write(sheet, list(rows[0]), rows)
        with pytest.raises(CategoryCodingError, match="no longer matches"):
            check_sample_matches_population(self._load(rq5_dir), sheet)


def _results():
    coded = [{"repository": f"r{i}", "language": "python", "decision": "yes"} for i in range(40)]
    coded += [{"repository": "x", "language": "java", "decision": "unsure"}]
    return compute_results(coded, Counter({"all": 100, "python": 60, "java": 40}))


class TestCategoryAnalysis:
    def test_not_started_and_not_coded_yet(self, rq5_dir):
        assert compute_category_results(rq5_dir / REPOSITORY_SHEET_NAME) is None
        assert "Not started" in generate_report(_results(), None)
        _sample(rq5_dir)
        write_codebook_template(rq5_dir)
        category = compute_category_results(rq5_dir / REPOSITORY_SHEET_NAME)
        assert "Not coded yet: none of the 40 repositories" in generate_report(_results(), category)
        assert checkpoint_warning(category) is None

    def test_at_a_checkpoint(self, rq5_dir):
        _sample(rq5_dir)
        codes = {o: "location" for o in range(1, 30)}
        codes.update({1: "location; cleanup", 2: "cleanup"})
        _code(rq5_dir, codes)
        category = compute_category_results(rq5_dir / REPOSITORY_SHEET_NAME)

        assert (category["size"], category["checkpoint_reached"]) == (29, 29)
        assert category["category_counts"] == {"location": 28, "cleanup": 2}
        assert category["categories_per_repository"] == (1, 1, 2)
        assert category["margin_of_error"] == pytest.approx(margin_of_error(29, 40))
        assert checkpoint_warning(category) is None

        report = generate_report(_results(), category)
        assert "seed 20261012" in report and "checkpoint 29 reached. Sample size: 29. Confidence: 95%." in report
        assert "| Fixture location | Says where fixtures live. | 28 | 96.6% |" in report
        assert "| Cleanup | Says how fixtures clean up. | 2 | 6.9% |" in report
        assert "A repository can belong to several categories, so percentages do not add up to 100%." in report
        assert "Categories per repository: median 1, minimum 1, maximum 2." in report
        sample_python = sum(1 for r in _read(rq5_dir / SAMPLE_NAME)[:29] if r["primary_language"] == "python")
        assert f"| Python | {sample_python} | " in report and "| 10 | 25.0% |" in report
        assert "No second coding yet." in report

    def test_off_checkpoint_warns_and_reports_the_actual_size(self, rq5_dir):
        _sample(rq5_dir)
        _code(rq5_dir, {o: "location" for o in range(1, 31)})
        category = compute_category_results(rq5_dir / REPOSITORY_SHEET_NAME)
        assert category["size"] == 30
        assert "30 repositories, which is not a checkpoint (29, 37)" in checkpoint_warning(category)
        assert "no checkpoint reached (29 and 37): the coded prefix stops at 30" in generate_report(_results(), category)


class TestAgreement:
    def test_cohens_kappa_matches_a_hand_computation(self):
        # observed 0.75; chance 0.5*0.25 + 0.5*0.75 = 0.5; kappa (0.75-0.5)/0.5
        assert cohens_kappa([True, True, False, False], [True, False, False, False]) == pytest.approx(0.5)
        assert cohens_kappa([True, False], [True, False]) == pytest.approx(1.0)
        assert cohens_kappa([False, False], [False, False]) is None

    def test_compare_codings_per_category_and_averages(self):
        codebook = [Category("a", "A", "d"), Category("b", "B", "d")]
        first = {"r1": {"a"}, "r2": {"a"}, "r3": set(), "r4": set()}
        second = {"r1": {"a"}, "r2": set(), "r3": set(), "r4": set()}
        result = compare_codings(first, second, codebook)
        (_, agree_a, kappa_a), (_, agree_b, kappa_b) = result.per_category
        assert (agree_a, kappa_a) == (0.75, pytest.approx(0.5))
        assert (agree_b, kappa_b) == (1.0, None)
        assert result.mean_agreement == pytest.approx(0.875)
        assert result.mean_kappa == pytest.approx(0.5)

    def test_agreement_sheet_draws_20_from_the_coded_prefix(self, rq5_dir):
        _sample(rq5_dir)
        rows = _code(rq5_dir, {o: "location" for o in range(1, 30)})
        path = write_agreement_sheet(rq5_dir)
        drawn = _read(path)
        prefix = {r["repository"] for r in rows[:29]}
        assert len(drawn) == 20 and {r["repository"] for r in drawn} <= prefix
        assert [int(r["sample_order"]) for r in drawn] == sorted(int(r["sample_order"]) for r in drawn)
        assert all(r["categories"] == "" and r["snippets"] for r in drawn)
        assert write_agreement_sheet(rq5_dir).read_bytes() == path.read_bytes()

    def test_agreement_sheet_needs_20_coded_and_never_overwrites_coding(self, rq5_dir):
        _sample(rq5_dir)
        _code(rq5_dir, {o: "location" for o in range(1, 10)})
        with pytest.raises(CategoryCodingError, match="9 repositories; 20 are needed"):
            write_agreement_sheet(rq5_dir)
        _code(rq5_dir, {o: "location" for o in range(1, 30)})
        path = write_agreement_sheet(rq5_dir)
        rows = _read(path)
        rows[0]["categories"] = "cleanup"
        _write(path, list(rows[0]), rows)
        with pytest.raises(CategoryCodingError, match="refusing to overwrite"):
            write_agreement_sheet(rq5_dir)

    def test_report_shows_pending_then_the_agreement_table(self, rq5_dir):
        _sample(rq5_dir)
        sample_rows = _code(rq5_dir, {o: "location" for o in range(1, 30)})
        path = write_agreement_sheet(rq5_dir)
        rows = _read(path)
        rows[0]["categories"] = "location"
        _write(path, list(rows[0]), rows)
        category = compute_category_results(rq5_dir / REPOSITORY_SHEET_NAME)
        assert f"Pending: `{AGREEMENT_SHEET_NAME}` has 1 of 20 repositories coded." in generate_report(_results(), category)

        codes = {r["repository"]: r["categories"] for r in sample_rows}
        for i, row in enumerate(rows):
            row["categories"] = "location; cleanup" if i == 0 else codes[row["repository"]]
        _write(path, list(rows[0]), rows)
        category = compute_category_results(rq5_dir / REPOSITORY_SHEET_NAME)
        report = generate_report(_results(), category)
        assert "A second coder coded 20 repositories" in report
        assert "| Fixture location | 100.0% | n/a |" in report
        assert "| Cleanup | 95.0% | 0.00 |" in report
        assert "| Average | 97.5% | 0.00 |" in report


class TestInstructions:
    """research-questions/rq5/CATEGORY_CODING.md states the design constants."""

    def test_the_instructions_match_the_code(self):
        text = (ROOT_DIR / "research-questions" / "rq5" / "CATEGORY_CODING.md").read_text(encoding="utf-8")
        assert f"**{SAMPLE_SEED}**" in text and f"**{AGREEMENT_SEED}**" in text
        assert f"the {EXPECTED_POPULATION} repositories coded `yes`" in text
        for checkpoint in EXPECTED_CHECKPOINTS:
            assert f"**{checkpoint}**" in text
        assert f"{AGREEMENT_SIZE} repositories" in text
        for name in (SAMPLE_NAME, CODEBOOK_NAME, AGREEMENT_SHEET_NAME):
            assert name in text
        assert "rq5_category_sample sample" in text and "rq5_category_sample agreement-sheet" in text
