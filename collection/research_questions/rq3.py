"""RQ3 -- setup and teardown fixtures in agent-written and human-written code.

Each fixture has a `fixture_role`: setup, teardown, setup_and_teardown or other.

Table 1 gives the counts of setup and teardown fixtures per language. It has no
test.

Table 2 gives teardown coverage: for each repository, whether it has at least
one teardown fixture. The table shows the share of repositories with a
teardown, per language and overall. It has no test.

A supplementary table shows how each fixture was classified, per language.

Writes `research_questions/rq3.md`. Run with `python -m collection.research_questions.rq3`.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .. import paths
from ..db import db_session
from ..logging_utils import get_logger
from ._shared import (
    COMPARISONS,
    DATASET_LABELS,
    OUTPUT_DIR,
    LanguageLeakage,
    compute_language_leakage,
    pct,
    render_language_leakage_table,
    require_db_or_none,
    write_markdown_report,
)

logger = get_logger(__name__)

# Fixed row order for both paper tables -- see the module docstring for why
# this is a fixed list rather than the "languages present on both sides"
# intersection convention used elsewhere in this package.
RQ3_LANGUAGES: tuple[str, ...] = ("java", "javascript", "python", "typescript")


@dataclass
class DatasetMetrics:
    dataset: str
    n_fixtures: int
    kind_distribution: dict[str, int] = field(default_factory=dict)
    kind_counts_by_repo: dict[int, dict[str, int]] = field(default_factory=dict)
    kind_counts_by_repo_and_language: dict[str, dict[int, dict[str, int]]] = field(
        default_factory=dict
    )
    language_leakage: list[LanguageLeakage] = field(default_factory=list)


def load_dataset_metrics(
    dataset: str, *, db_root: Path = paths.DB_ROOT
) -> DatasetMetrics | None:
    """Load RQ3 metrics for `dataset`, or None if its db doesn't exist yet."""
    db_file = require_db_or_none(dataset, db_root)
    if db_file is None:
        return None

    with db_session(db_file) as conn:
        n_fixtures = conn.execute("SELECT COUNT(*) FROM fixtures").fetchone()[0]
        (
            kind_distribution,
            kind_counts_by_repo,
            kind_counts_by_repo_and_language,
        ) = _fetch_kinds_and_repo_counts(conn)
        language_leakage = compute_language_leakage(conn)

    return DatasetMetrics(
        dataset=dataset,
        n_fixtures=n_fixtures,
        kind_distribution=kind_distribution,
        kind_counts_by_repo=kind_counts_by_repo,
        kind_counts_by_repo_and_language=kind_counts_by_repo_and_language,
        language_leakage=language_leakage,
    )


def _empty_kind_counts() -> dict[str, int]:
    """A fresh {setup/teardown/setup_and_teardown/other: 0} dict -- the one
    place that dict literal is spelled out, so every kind_distribution/
    kind_counts_by_repo(_and_language) entry stays in sync if a kind is
    ever added or renamed."""
    return dict.fromkeys(("setup", "teardown", "setup_and_teardown", "other"), 0)


def _fetch_kinds_and_repo_counts(
    conn: sqlite3.Connection,
) -> tuple[
    dict[str, int],
    dict[int, dict[str, int]],
    dict[str, dict[int, dict[str, int]]],
]:
    """Single pass over every fixture: dataset-level kind distribution
    (descriptive only), per-repo {setup/teardown/setup_and_teardown/other:
    count} (Overall), and the same per-repo counts bucketed by each
    fixture's own language too -- reading fixtures.fixture_role
    directly, already classified once at extraction time (see this
    module's docstring), so this is a straight read, not a
    re-classification.

    `kind_counts_by_repo` feeds Table 2's Overall row (via
    _teardown_coverage_indicators()); `kind_counts_by_repo_and_language`
    feeds both tables' per-language rows -- Table 1's raw counts
    (_language_kind_totals(), summed across repos) and Table 2's
    per-language coverage percentage -- grouped by each fixture's own
    language (test_files.language), not the repo's tag, so a repo with
    fixtures in more than one language contributes to each language
    separately."""
    kind_distribution = _empty_kind_counts()
    kind_counts_by_repo: dict[int, dict[str, int]] = {}
    kind_counts_by_repo_and_language: dict[str, dict[int, dict[str, int]]] = {}

    rows = conn.execute(
        "SELECT f.repo_id, f.fixture_role, tf.language FROM fixtures f "
        "JOIN test_files tf ON f.file_id = tf.id WHERE f.fixture_type IS NOT NULL"
    ).fetchall()
    for repo_id, kind, language in rows:
        kind_distribution[kind] += 1

        repo_kind_counts = kind_counts_by_repo.setdefault(
            repo_id, _empty_kind_counts()
        )
        repo_kind_counts[kind] += 1

        lang_repo_counts = kind_counts_by_repo_and_language.setdefault(
            language, {}
        ).setdefault(repo_id, _empty_kind_counts())
        lang_repo_counts[kind] += 1

    return kind_distribution, kind_counts_by_repo, kind_counts_by_repo_and_language


def _render_dataset_summary(metrics: DatasetMetrics) -> str:
    lines = [f"### {DATASET_LABELS[metrics.dataset]} -- {metrics.n_fixtures:,} fixtures", ""]

    total_kind = sum(metrics.kind_distribution.values())
    lines += ["**fixture_type kind distribution**", "", "| Kind | Count | % |", "|---|---|---|"]
    for kind in ("setup", "teardown", "setup_and_teardown", "other"):
        count = metrics.kind_distribution.get(kind, 0)
        kind_pct = 100 * count / total_kind if total_kind else 0.0
        lines.append(f"| {kind} | {count:,} | {kind_pct:.1f}% |")
    lines.append("")

    lines.append(render_language_leakage_table(metrics.language_leakage))

    return "\n".join(lines)


def _language_kind_totals(
    kind_counts_by_repo_and_language: dict[str, dict[int, dict[str, int]]],
) -> dict[str, dict[str, int]]:
    """{language: {setup/teardown/setup_and_teardown/other: total count
    across every repo}} -- Table 1's per-language raw counts, summed from
    the same per-repo counts Table 2 and the dip test draw their per-repo
    populations/proportions from (no separate fetch/classification pass)."""
    totals: dict[str, dict[str, int]] = {}
    for language, by_repo in kind_counts_by_repo_and_language.items():
        lang_totals = totals.setdefault(language, _empty_kind_counts())
        for repo_counts in by_repo.values():
            for kind, count in repo_counts.items():
                lang_totals[kind] += count
    return totals


def _effective_setup_count(kind_counts: dict[str, int]) -> int:
    """Setup-providing fixture count: 'setup' plus 'setup_and_teardown' --
    the latter genuinely provides setup too, so excluding it here would
    undercount."""
    return kind_counts.get("setup", 0) + kind_counts.get("setup_and_teardown", 0)


def _effective_teardown_count(kind_counts: dict[str, int]) -> int:
    """Teardown-providing fixture count: 'teardown' plus
    'setup_and_teardown', for the same reason as _effective_setup_count()."""
    return kind_counts.get("teardown", 0) + kind_counts.get("setup_and_teardown", 0)


def _answerable_total(kind_counts: dict[str, int]) -> int:
    """Denominator for Table 1's Setup%/Teardown% cells: setup + teardown +
    setup_and_teardown, excluding 'other'. A fixture classified 'other'
    (e.g. a JUnit `@Rule`/`@ClassRule` field, or a TestNG `@DataProvider`
    -- see _render_kind_classification_coverage_table()'s docstring) was
    never a candidate to be setup or teardown in the first place (no
    setup/teardown pairing mechanism applies to it, and unlike
    pytest_decorator there's no body-analysis fallback either), so it
    shouldn't dilute the percentage of the fixtures that WERE classified
    one way or the other -- a language with a large 'other' share (java,
    see the coverage table below) would otherwise report artificially low
    Setup%/Teardown% purely because of how many of its fixtures could not
    be classified at all, not because of its actual setup/teardown
    provision."""
    return kind_counts.get("setup", 0) + kind_counts.get("teardown", 0) + kind_counts.get(
        "setup_and_teardown", 0
    )


def _pct_cell(count: int, total: int) -> str:
    """`count` formatted as "N (P%)", P = count/total*100 to one decimal
    place -- just "N" (no percentage) if total is 0, the zero-filled-row
    case for a language absent from this dataset (see
    _render_kind_counts_table()'s "zero, not omitted" convention), which
    would otherwise divide by zero. `total` is always the language's (or,
    for the Total row, the dataset's) *answerable* fixture count -- setup +
    teardown + setup_and_teardown, excluding 'other' (see
    _answerable_total()'s docstring for why) -- not the raw setup/teardown
    sum, since a setup_and_teardown fixture is in both; see
    _render_kind_counts_table()'s docstring for how that denominator keeps
    Setup%/Teardown% consistent with each other."""
    if total == 0:
        return f"{count:,}"
    return f"{count:,} ({100 * count / total:.1f}%)"


def _render_kind_counts_table(a: DatasetMetrics, other: DatasetMetrics) -> str:
    """Table 1 (tab:rq3-counts): absolute setup/teardown fixture counts per
    language, each also shown as a percentage of that language's
    *answerable* fixture count (setup + teardown + setup_and_teardown,
    excluding 'other' -- see _answerable_total()'s docstring for why, not
    just the raw setup/teardown counts). Purely descriptive -- no
    statistics. "other"-classified fixtures are excluded from both the
    counts themselves and the percentage denominator -- they were never a
    setup/teardown candidate to begin with. A 'setup_and_teardown'-
    classified fixture (pytest_decorator only -- see this module's
    docstring) counts toward *both* columns, since it genuinely provides
    both -- so the two columns are not mutually exclusive and
    Setup+Teardown (and Setup%+Teardown%) can exceed the dataset's
    answerable fixture count (100%)."""
    other_label = other.dataset.upper()
    lines = [
        "Raw counts of setup-classified and teardown-classified fixtures, "
        "each also shown as a percentage of that language's *answerable* "
        "fixture count (setup + teardown + setup_and_teardown -- "
        '"other"-classified fixtures, e.g. a JUnit `@Rule` or a TestNG '
        "`@DataProvider` (see the Fixture Kind Classification Coverage by "
        "Language table below), are excluded from both the counts "
        "themselves and this percentage denominator, since they were "
        "never a setup/teardown candidate in the first place; a fixture "
        "classified as providing both -- e.g. a pytest fixture with setup "
        "code before its `yield` -- is counted in both columns, so they "
        "are not mutually exclusive and the two percentages can sum past "
        "100%). Total is the dataset-wide sum across every language "
        "present, not just the four rows below. Purely descriptive -- no "
        "significance test.",
        "",
        f"| Language | Setup A | Setup {other_label} | Teardown A | Teardown {other_label} |",
        "|---|---|---|---|---|",
        (
            f"| Total | {_pct_cell(_effective_setup_count(a.kind_distribution), _answerable_total(a.kind_distribution))} | "
            f"{_pct_cell(_effective_setup_count(other.kind_distribution), _answerable_total(other.kind_distribution))} | "
            f"{_pct_cell(_effective_teardown_count(a.kind_distribution), _answerable_total(a.kind_distribution))} | "
            f"{_pct_cell(_effective_teardown_count(other.kind_distribution), _answerable_total(other.kind_distribution))} |"
        ),
    ]

    a_totals = _language_kind_totals(a.kind_counts_by_repo_and_language)
    other_totals = _language_kind_totals(other.kind_counts_by_repo_and_language)
    for language in RQ3_LANGUAGES:
        a_kind = a_totals.get(language, {})
        other_kind = other_totals.get(language, {})
        a_total = _answerable_total(a_kind)
        other_total = _answerable_total(other_kind)
        lines.append(
            f"| {language} | {_pct_cell(_effective_setup_count(a_kind), a_total)} | "
            f"{_pct_cell(_effective_setup_count(other_kind), other_total)} | "
            f"{_pct_cell(_effective_teardown_count(a_kind), a_total)} | "
            f"{_pct_cell(_effective_teardown_count(other_kind), other_total)} |"
        )

    lines.append("")
    return "\n".join(lines)


def _teardown_coverage_indicators(by_repo: dict[int, dict[str, int]]) -> list[float]:
    """Per-repo binary indicator: 1.0 if that repo has >=1 teardown-
    providing fixture (classified 'teardown' or 'setup_and_teardown' --
    see _effective_teardown_count()), else 0.0. Population is repos with
    >=1 classified (setup/teardown/setup_and_teardown/other) fixture -- a
    repo with none is skipped, not counted as 0-coverage. `_coverage_pct()`
    takes the mean of these 0/1 values directly -- that mean *is* "% of
    repos with >=1 teardown fixture",
    Table 2's Coverage A/C (%) columns."""
    return [
        1.0 if _effective_teardown_count(counts) > 0 else 0.0
        for counts in by_repo.values()
        if sum(counts.values())
    ]


def _render_teardown_coverage_row(
    label: str, n_a: int, n_c: int, pct_a: float | None, pct_c: float | None
) -> str:
    """One row of Table 2 -- purely descriptive (no statistical test, see
    this module's docstring): `pct_a`/`pct_c` are just the mean of each
    side's 0/1 coverage indicator list, `None` when that side's population
    is empty."""
    if pct_a is None and pct_c is None:
        return f"| {label} | {n_a} | {n_c} | -- | -- |"
    return f"| {label} | {n_a} | {n_c} | {pct(pct_a)} | {pct(pct_c)} |"


def _coverage_pct(indicators: list[float]) -> float | None:
    """Mean of a 0/1 indicator list as a 0..1 proportion (pct()'s own
    expected input -- it multiplies by 100 itself), or None if the
    population (the list itself) is empty -- shared by Table 2's Overall
    and per-language rows."""
    return sum(indicators) / len(indicators) if indicators else None


def _render_teardown_coverage_table(a: DatasetMetrics, other: DatasetMetrics) -> str:
    """Table 2 (tab:rq3-coverage): % of repos with >=1 teardown-classified
    fixture, per language and Overall. Purely descriptive -- no
    statistical test."""
    other_label = other.dataset.upper()
    lines = [
        "Per-repository binary coverage: 1 if a repo has >=1 teardown-"
        "classified fixture, else 0 (population: repos with >=1 setup/"
        'teardown/other-classified fixture). "Coverage A/C (%)" is the '
        "share of that population with the indicator at 1. Purely "
        "descriptive -- no statistical test.",
        "",
        f"| Language | n_A | n_{other_label} | Coverage A (%) | Coverage {other_label} (%) |",
        "|---|---|---|---|---|",
    ]

    a_overall = _teardown_coverage_indicators(a.kind_counts_by_repo)
    other_overall = _teardown_coverage_indicators(other.kind_counts_by_repo)
    lines.append(
        _render_teardown_coverage_row(
            "Overall",
            len(a_overall),
            len(other_overall),
            _coverage_pct(a_overall),
            _coverage_pct(other_overall),
        )
    )

    for language in RQ3_LANGUAGES:
        a_by_repo = _teardown_coverage_indicators(a.kind_counts_by_repo_and_language.get(language, {}))
        other_by_repo = _teardown_coverage_indicators(
            other.kind_counts_by_repo_and_language.get(language, {})
        )
        lines.append(
            _render_teardown_coverage_row(
                language,
                len(a_by_repo),
                len(other_by_repo),
                _coverage_pct(a_by_repo),
                _coverage_pct(other_by_repo),
            )
        )

    lines.append("")
    return "\n".join(lines)


def _render_kind_classification_coverage_table(a: DatasetMetrics, other: DatasetMetrics) -> str:
    """### Fixture Kind Classification Coverage by Language.

    Supplementary -- not part of either main paper table (tab:rq3-counts,
    tab:rq3-coverage), rendered under generate_report()'s "## Supplementary
    Analyses" section. Table 1 above excludes 'other' entirely from its
    own denominator (see _answerable_total()'s docstring) and never shows
    the 'other' slice on its own; this table does, broken out per language
    instead of pooled dataset-wide (the "Per-dataset summary" section's
    kind distribution) -- 'other' fixtures (e.g. a JUnit `@Rule`/
    `@ClassRule` field, or a TestNG `@DataProvider`) aren't spread evenly
    across languages, so a language with a high 'other' share has that
    much smaller a slice of its fixtures represented anywhere in Table 1's
    counts at all (not a diluted rate -- an outright absence). Reuses
    _language_kind_totals() -- the same per-language totals Table 1 itself
    renders from -- so this is a different view of the identical numbers,
    not a separate computation."""
    other_label = other.dataset.upper()
    lines = [
        "### Fixture Kind Classification Coverage by Language",
        "",
        "Per-language, per-dataset breakdown of `fixture_role` "
        "(setup / teardown / setup_and_teardown / other) -- the same "
        "counts behind Table 1 above and the pooled dataset-wide `other` "
        "% in `Per-dataset summary`, just split out per language instead "
        "of pooled. Table 1 excludes `other` entirely from its own "
        "percentage denominator, so it never shows this slice; `other` "
        "fixtures (e.g. a JUnit `@Rule`/`@ClassRule` field, or a TestNG "
        "`@DataProvider` -- neither is inherently setup or teardown) are "
        "not spread evenly across languages, so a language with a high "
        "`other` % has that much smaller a share of its fixtures "
        "represented in Table 1's counts at all. Worth re-checking "
        "whenever a new dataset is extracted -- a new language or "
        "framework can introduce its own unclassifiable fixture types.",
        "",
        "| Dataset | Language | Total fixtures | setup | teardown | "
        "setup_and_teardown | other (count) | other (%) |",
        "|---|---|---|---|---|---|---|---|",
    ]

    a_totals = _language_kind_totals(a.kind_counts_by_repo_and_language)
    other_totals = _language_kind_totals(other.kind_counts_by_repo_and_language)
    for label, totals in (("A", a_totals), (other_label, other_totals)):
        for language in RQ3_LANGUAGES:
            kind_counts = totals.get(language, {})
            total = sum(kind_counts.values())
            other_count = kind_counts.get("other", 0)
            other_pct = 100 * other_count / total if total else 0.0
            lines.append(
                f"| {label} | {language} | {total:,} | "
                f"{kind_counts.get('setup', 0):,} | "
                f"{kind_counts.get('teardown', 0):,} | "
                f"{kind_counts.get('setup_and_teardown', 0):,} | "
                f"{other_count:,} | {other_pct:.1f}% |"
            )

    lines.append("")
    return "\n".join(lines)


def _render_comparison(label: str, a: DatasetMetrics, other: DatasetMetrics) -> str:
    lines = [
        f"## {label}: {DATASET_LABELS['a']} vs {DATASET_LABELS[other.dataset]}",
        "",
        "### Table 1: Fixture Counts by Type (tab:rq3-counts)",
        "",
        _render_kind_counts_table(a, other),
        "### Table 2: Teardown Coverage by Repository (tab:rq3-coverage)",
        "",
        _render_teardown_coverage_table(a, other),
    ]
    return "\n".join(lines)


def generate_report(*, db_root: Path = paths.DB_ROOT) -> str:
    loaded = {ds: load_dataset_metrics(ds, db_root=db_root) for ds in ("a", "c")}
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    lines = [
        "# RQ3 -- Setup and Teardown Characterization",
        "",
        "> How do agent-generated fixtures compare to human-written ones in setup "
        "and teardown provision?",
        "",
        f"Generated: {generated_at}",
        "",
        "See [docs/research-questions.md](../docs/research-questions.md) for "
        "the full RQ3 definition.",
        "",
        "## Per-dataset summary",
        "",
    ]

    for ds in ("a", "c"):
        metrics = loaded[ds]
        if metrics is None:
            lines += [f"### {DATASET_LABELS[ds]}", "", "_Not available -- db not collected yet._", ""]
        else:
            lines.append(_render_dataset_summary(metrics))

    a_metrics = loaded["a"]
    if a_metrics is None:
        lines.append("_Dataset A not available -- no A vs C comparisons computed._")
    else:
        for other_ds, label in COMPARISONS:
            other_metrics = loaded[other_ds]
            if other_metrics is None:
                lines += [
                    f"## {label}: {DATASET_LABELS['a']} vs {DATASET_LABELS[other_ds]}",
                    "",
                    "_Not available -- db not collected yet._",
                    "",
                ]
            else:
                lines.append(_render_comparison(label, a_metrics, other_metrics))

        lines += [
            "## Supplementary Analyses",
            "",
            "Analyses below are not part of either main paper table "
            "(tab:rq3-counts, tab:rq3-coverage) but are kept and computed "
            "since they may still be referenced in prose.",
            "",
        ]
        for other_ds, _label in COMPARISONS:
            other_metrics = loaded[other_ds]
            if other_metrics is not None:
                lines.append(_render_kind_classification_coverage_table(a_metrics, other_metrics))

    return "\n".join(lines)


def write_report(
    output_dir: Path = OUTPUT_DIR, *, db_root: Path = paths.DB_ROOT
) -> Path:
    report = generate_report(db_root=db_root)
    output_path = write_markdown_report(output_dir, "rq3.md", report)
    logger.info(f"RQ3 report written to {output_path}")
    return output_path


def main() -> None:
    path = write_report()
    print(f"RQ3 report written to {path}")


if __name__ == "__main__":
    main()
