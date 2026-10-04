"""
RQ1 -- Fixture Prevalence (Quantitative): how common are tests, fixtures,
setup, and teardown across the raw repo universe -- independent of any
Dataset A/B/C filtering?

Pure reader over `db/rq1_prevalence.db` (`collection/rq1_prevalence_scan.py`'s
own output) -- same role `rq2.py`/`rq3.py`/`rq4.py` play for `db/a.db` +
`db/c.db`. No collection logic lives here; this module only aggregates and
renders what that scan already persisted.

Computes both paper tables over every successfully-scanned repo --
deliberately no `min_test_files` quality floor applied here (2026-10-04
methodology decision): RQ1's whole purpose is to characterize the raw
universe *before* any Dataset A/B/C-style filtering, so applying one of
A/B/C's own floors would partly collapse the distinction RQ1 exists to
draw. A floored variant was reported here through 2026-10-04 (as a
robustness check showing the floor barely moved the numbers) but was
removed once that check had served its purpose -- see git history
(`rq1_prevalence_scan.py` still collects `num_test_files` for every repo
regardless; nothing about collection changed, only this report's
rendering).

A repo with `clone_ok=0` (clone failed, or no commit at/before
`RQ1_CUTOFF_DATE`) is excluded from every count here -- it means "unknown
whether this repo has tests," not "confirmed no tests." Counting it as a
negative would silently bias every percentage down.

**Table 1** (`tab:rq1-prevalence`): for each language (and "All", pooled
across all four), how many repos have >=1 test file, how many of THOSE
have >=1 fixture, and -- of repos **with >=1 test file** (2026-10-04: not
"of repos with >=1 fixture," see `render_table1()`'s own docstring for
why that denominator was the wrong one for the paper's "fixtures are
commonly used in tests" framing) -- what % have >=1 setup-classified /
teardown-classified fixture. `num_setup`/`num_teardown` are read directly
off `repo_prevalence` -- the dual-counting of a `setup_and_teardown`
fixture toward both already happened once, in
`rq1_prevalence_scan.scan_working_tree()` (matching `research_questions/
rq3.py`'s own convention), not redone here. The table's original,
fixture-conditioned definition is kept alongside it, not replaced --
see `render_table1_legacy_fixture_conditioned()` and the report's own
"Legacy" section.

**Table 2** (`tab:rq1-prevalence-median`): for each language (and "All"),
the median fixtures/setup-fixtures/teardown-fixtures per repo, among
repos with >=1 fixture (unchanged by the 2026-10-04 Table 1 denominator
change above -- a median over repos with zero fixtures would trivially
collapse to 0 and isn't informative). "All" is one pooled median across
every repo-with-fixtures regardless of language, not an average of the
four per-language medians.

python -m collection.research_questions.rq1
"""

from __future__ import annotations

import sqlite3
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .. import paths
from ..db import db_session
from ..rq1_prevalence_scan import DB_PATH as _SCAN_DB_PATH
from ._shared import OUTPUT_DIR, fmt, pct, write_markdown_report

# Paper's own row order for both tables -- deliberately NOT
# rq1_prevalence_scan.RQ1_LANGUAGES's alphabetical order (java, javascript,
# python, typescript).
DISPLAY_LANGUAGES: tuple[str, ...] = ("python", "java", "javascript", "typescript")
DISPLAY_LABELS: dict[str, str] = {
    "python": "Python",
    "java": "Java",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
}

# Derived from rq1_prevalence_scan.DB_PATH rather than a second hardcoded
# "rq1_prevalence.db" literal -- a filename change there must not be able
# to silently desync from what this module reads, which would otherwise
# just report "not available" (load_rows() returning None) instead of
# erroring loudly.
_DB_FILENAME = _SCAN_DB_PATH.name


@dataclass
class LanguagePrevalence:
    """One language's (or "All"'s, pooled) Table 1/2 inputs, already
    reduced to exactly what both tables need. `*_per_repo` lists are only
    populated for repos with >=1 fixture (Table 2's own population) --
    `fixtures_per_repo[i]`/`setup_per_repo[i]`/`teardown_per_repo[i]` are
    always the same repo's three counts, index-aligned."""

    n_with_tests: int = 0
    n_with_fixtures: int = 0
    n_with_setup: int = 0
    n_with_teardown: int = 0
    fixtures_per_repo: list[int] = field(default_factory=list)
    setup_per_repo: list[int] = field(default_factory=list)
    teardown_per_repo: list[int] = field(default_factory=list)


def load_rows(db_root: Path = paths.DB_ROOT) -> list[sqlite3.Row] | None:
    """Every `clone_ok=1` row from `repo_prevalence`, or `None` if the db
    doesn't exist yet -- the project's "skip, don't error" convention, so
    a batch regeneration of every `research_questions/` report doesn't
    crash on an RQ whose collection hasn't run yet.

    `clone_ok=0` rows (clone failed, or no commit at/before
    `RQ1_CUTOFF_DATE`) are excluded here, once, so every caller downstream
    automatically treats them as "unknown" rather than needing to
    remember the filter themselves.
    """
    db_path = db_root / _DB_FILENAME
    if not db_path.exists():
        return None
    with db_session(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            "SELECT language, num_test_files, num_fixtures, num_setup, num_teardown "
            "FROM repo_prevalence WHERE clone_ok = 1"
        ).fetchall()


def compute_prevalence(rows: list[sqlite3.Row]) -> dict[str, LanguagePrevalence]:
    """Reduce `clone_ok=1` rows to one `LanguagePrevalence` per language
    plus `"all"` (pooled across every language). No quality floor of any
    kind is applied here -- see this module's own docstring for why RQ1
    deliberately doesn't filter on `min_test_files` the way Dataset
    A/B/C's own collection does."""
    by_language: dict[str, LanguagePrevalence] = {}
    pooled = LanguagePrevalence()
    for row in rows:
        language = row["language"]
        entry = by_language.setdefault(language, LanguagePrevalence())
        for target in (entry, pooled):
            if row["num_test_files"] > 0:
                target.n_with_tests += 1
            if row["num_fixtures"] > 0:
                target.n_with_fixtures += 1
                target.fixtures_per_repo.append(row["num_fixtures"])
                target.setup_per_repo.append(row["num_setup"])
                target.teardown_per_repo.append(row["num_teardown"])
                if row["num_setup"] > 0:
                    target.n_with_setup += 1
                if row["num_teardown"] > 0:
                    target.n_with_teardown += 1
    by_language["all"] = pooled
    return by_language


def _pct_or_none(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else numerator / denominator


def _median_str(values: list[int]) -> str:
    return fmt(statistics.median(values), 1) if values else "--"


def _ordered_rows(by_language: dict[str, LanguagePrevalence]) -> list[tuple[str, LanguagePrevalence]]:
    empty = LanguagePrevalence()
    rows = [("All", by_language.get("all", empty))]
    rows += [(DISPLAY_LABELS[lang], by_language.get(lang, empty)) for lang in DISPLAY_LANGUAGES]
    return rows


def render_table1(by_language: dict[str, LanguagePrevalence]) -> str:
    """tab:rq1-prevalence: Language | Repositories with Tests | Fixture (%)
    | Setup (%) | Teardown (%).

    **Self-explanatory by construction (2026-10-04 restructure), no
    caption needed:** every percentage column -- Fixture (%), Setup (%),
    Teardown (%) -- divides by the exact same population,
    `n_with_tests` (the "Repositories with Tests" column), not by each
    other. The table's previous shape had a `#` column (the raw
    fixture-having count) sitting between "Repositories with Tests" and
    these percentages, which visually invited reading Setup (%)/
    Teardown (%) as continuing to narrow from that `#` count -- the
    *fixture-having* subset -- rather than from "Repositories with
    Tests" again. That was also this table's actual old behavior before
    the same day's earlier methodology change (dividing by
    `n_with_fixtures`, a much easier bar to clear, which pushed every
    language's Setup/Teardown (%) up near 95-99% regardless of how
    common setup/teardown actually is -- see git history). Removing the
    `#` column removes the ambiguity rather than just explaining it away:
    there's no intervening absolute count left to suggest a narrowing
    funnel, so three parallel percentage columns of one clearly-labeled
    population is the whole story. The dropped raw fixture-having count
    is still available in the "Raw numbers" table below (`n (fixtures)`),
    so no information is lost, only this table's own potential for
    misreading."""
    lines = [
        "| Language | Repositories with Tests | Fixture (%) | Setup (%) | Teardown (%) |",
        "|---|---|---|---|---|",
    ]
    for label, entry in _ordered_rows(by_language):
        fixture_pct = pct(_pct_or_none(entry.n_with_fixtures, entry.n_with_tests))
        setup_pct = pct(_pct_or_none(entry.n_with_setup, entry.n_with_tests))
        teardown_pct = pct(_pct_or_none(entry.n_with_teardown, entry.n_with_tests))
        lines.append(
            f"| {label} | {entry.n_with_tests:,} | {fixture_pct} | {setup_pct} | {teardown_pct} |"
        )
    return "\n".join(lines)


def render_table1_legacy_fixture_conditioned(by_language: dict[str, LanguagePrevalence]) -> str:
    """Legacy variant of Table 1, kept for transparency/comparison only --
    not the paper's table (see `render_table1()`'s own docstring and
    generate_report()'s "Legacy" section intro for why). Setup (%)/
    Teardown (%) here divide by `n_with_fixtures` (the fixture-having
    subset, shown in the `#`/`%` columns), the table's original
    definition before the 2026-10-04 methodology change -- a much easier
    bar to clear than "has >=1 test file," which is why these numbers
    sit up near 95-99% regardless of how common setup/teardown actually
    is. Kept exactly as it originally rendered, `#` column included, so
    a reader can directly compare both denominators side by side."""
    lines = [
        "| Language | Repositories with Tests | # | % | Setup (%) | Teardown (%) |",
        "|---|---|---|---|---|---|",
    ]
    for label, entry in _ordered_rows(by_language):
        fixture_pct = pct(_pct_or_none(entry.n_with_fixtures, entry.n_with_tests))
        setup_pct = pct(_pct_or_none(entry.n_with_setup, entry.n_with_fixtures))
        teardown_pct = pct(_pct_or_none(entry.n_with_teardown, entry.n_with_fixtures))
        lines.append(
            f"| {label} | {entry.n_with_tests:,} | {entry.n_with_fixtures:,} | "
            f"{fixture_pct} | {setup_pct} | {teardown_pct} |"
        )
    return "\n".join(lines)


def render_table2(by_language: dict[str, LanguagePrevalence]) -> str:
    """tab:rq1-prevalence-median: Language | Fixture | Setup | Teardown --
    median per repo, among repos with >=1 fixture. "All" is pooled across
    every language's repos, not an average of their four medians."""
    lines = [
        "| Language | Fixture | Setup | Teardown |",
        "|---|---|---|---|",
    ]
    for label, entry in _ordered_rows(by_language):
        lines.append(
            f"| {label} | {_median_str(entry.fixtures_per_repo)} | "
            f"{_median_str(entry.setup_per_repo)} | {_median_str(entry.teardown_per_repo)} |"
        )
    return "\n".join(lines)


def render_raw_numbers(by_language: dict[str, LanguagePrevalence]) -> str:
    """The counts/sums Table 1/2 are themselves computed from -- so a
    reader can verify either table (or compute a mean instead of the
    median) without re-querying the db."""
    lines = [
        "| Language | n (tests) | n (fixtures) | n (setup) | n (teardown) | "
        "sum fixtures | sum setup | sum teardown |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for label, entry in _ordered_rows(by_language):
        lines.append(
            f"| {label} | {entry.n_with_tests:,} | {entry.n_with_fixtures:,} | "
            f"{entry.n_with_setup:,} | {entry.n_with_teardown:,} | "
            f"{sum(entry.fixtures_per_repo):,} | {sum(entry.setup_per_repo):,} | "
            f"{sum(entry.teardown_per_repo):,} |"
        )
    return "\n".join(lines)


def render_median_prose(by_language: dict[str, LanguagePrevalence]) -> str:
    """The paper's own lead-in sentence for Table 2, numbers filled in
    from the "All" (pooled) row."""
    all_entry = by_language.get("all", LanguagePrevalence())
    if not all_entry.fixtures_per_repo:
        return (
            "_Not available -- no repos with fixtures in this population yet._"
        )
    fixtures_median = statistics.median(all_entry.fixtures_per_repo)
    setup_median = statistics.median(all_entry.setup_per_repo)
    teardown_median = statistics.median(all_entry.teardown_per_repo)
    return (
        f"At the median, each repository contains {fmt(fixtures_median, 1)} test "
        f"fixtures, including {fmt(setup_median, 1)} setups and "
        f"{fmt(teardown_median, 1)} teardowns."
    )


def generate_report(*, db_root: Path = paths.DB_ROOT) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    rows = load_rows(db_root)

    lines = [
        "# RQ1 -- Fixture Prevalence",
        "",
        "> How common are tests, fixtures, setup, and teardown across the "
        "raw repo universe, independent of Dataset A/B/C's own filtering?",
        "",
        f"Generated: {generated_at}",
        "",
        "See [docs/research-questions.md](../docs/research-questions.md) for "
        "the full RQ1 definition.",
        "",
    ]

    if rows is None:
        lines += ["_Not available -- db/rq1_prevalence.db not collected yet._", ""]
        return "\n".join(lines)

    lines += [
        f"Population: {len(rows):,} successfully-scanned repos (`clone_ok=1`), "
        "every repo pinned to the same commit-at-or-before cutoff date -- see "
        "`collection/rq1_prevalence_scan.py`'s module docstring. A repo whose "
        "clone failed, or that had no commit at or before that date, is "
        'excluded entirely from every count below ("unknown", never counted '
        'as "confirmed no tests"). No `min_test_files` quality floor is '
        "applied -- every successfully-scanned repo counts here regardless "
        "of how many test files it has, by design (see this module's own "
        "docstring).",
        "",
    ]

    by_language = compute_prevalence(rows)

    lines += [
        "### Table 1: Prevalence of test fixtures in repositories (tab:rq1-prevalence)",
        "",
        render_table1(by_language),
        "",
        "### Table 2: Distribution of test fixtures by repository, median (tab:rq1-prevalence-median)",
        "",
        render_table2(by_language),
        "",
        render_median_prose(by_language),
        "",
        "### Raw numbers",
        "",
        render_raw_numbers(by_language),
        "",
        "## Legacy: Fixture-Conditioned Table 1 (Not Used in the Paper)",
        "",
        "Kept for transparency/comparison only -- this is Table 1's original "
        "Setup (%)/Teardown (%) definition (share of the fixture-having "
        "subset, `#`/`%` below, rather than of all repos with >=1 test "
        "file). Near-universal regardless of language (95-99%) since "
        "clearing \"has >=1 fixture\" is a much easier bar than clearing "
        "\"has >=1 test file\" -- not the paper's table, which is the "
        "Table 1 above.",
        "",
        render_table1_legacy_fixture_conditioned(by_language),
        "",
    ]

    return "\n".join(lines)


def write_report(
    output_dir: Path = OUTPUT_DIR, *, db_root: Path = paths.DB_ROOT
) -> Path:
    report = generate_report(db_root=db_root)
    return write_markdown_report(output_dir, "rq1.md", report)


def main() -> None:
    path = write_report()
    print(f"RQ1 report written to {path}")


if __name__ == "__main__":
    main()
