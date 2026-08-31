"""
RQ2 -- Setup and Teardown Characterization (Quantitative): how do
agent-generated fixtures compare to human-written ones in setup and
teardown provision?

Two paper tables, both keyed on **fixtures.fixture_type_kind** -- setup /
teardown / setup_and_teardown / other. This is a persisted DB column, set
once at *extraction* time (not computed here) by
`detector_shared._classify_fixture_kinds()` for every fixture type except
`pytest_decorator`, plus `detector_python._detect_python()`'s own direct
body-analysis classification for `pytest_decorator` -- see those two
functions' docstrings for the exact per-type rules and why `pytest_decorator`
needs its own mechanism (type/name alone can't split it: every pytest
fixture is just named whatever the developer called it; see
internal-docs/methodology-improvements/pytest-yield-teardown-vs-fixture-kind.md).
This module just reads the column and renders it -- no classification logic
lives here, so a dataset's `fixture_type_kind` numbers are identical
regardless of when its RQ2 report is (re)generated relative to extraction.

Table 1's Setup/Teardown columns and Table 2's teardown-coverage indicator
both treat a `setup_and_teardown`-classified fixture as counting toward
*both* setup and teardown -- it genuinely provides both, so excluding it
from either column would undercount that dataset's real setup/teardown
provision.

**Table 1 (tab:rq2-counts) -- absolute fixture counts**
(`_render_kind_counts_table()`): purely descriptive, no statistics. For
each language and a Total row, the raw count of setup-classified and
teardown-classified fixtures in each dataset ("other" fixtures, e.g. a
bare `@pytest.fixture`, are excluded from both columns -- this table
answers "how many", not "what fraction"). Total is the dataset-wide sum
across every language present, not just the four rows shown.

**Table 2 (tab:rq2-coverage) -- teardown coverage**
(`_render_teardown_coverage_table()`): the inferential table. For each
repo, a binary indicator -- does it have >=1 teardown-classified fixture
at all (1) or none (0)? Compared between datasets via Mann-Whitney U +
Cliff's delta (`compute_continuous_balance()` on the 0/1 values directly
-- the mean of a 0/1 list *is* "% of repos with >=1 teardown fixture", so
`agent_mean`/`human_mean` from the same call double as the "Coverage A/C
(%)" columns, no separate aggregation needed). Population (and n_A/n_C):
repos with >=1 setup/teardown/other-classified fixture -- the same
"denominator" convention `repo_level_category_proportions()` uses
elsewhere in this package (a repo with zero classified fixtures is
skipped, not counted as 0-coverage). Overall is one pooled, uncorrected
test; each language's p is BH-FDR-corrected against the other 3
languages' tests only (this variable's own family -- see
`apply_fdr_correction()`'s docstring).

Both tables render a fixed four-language row order (java, javascript,
python, typescript) rather than this package's usual "intersection of
languages present on both sides" convention (`compute_stratified_*_
balance()`) -- a deliberate simplification matching the paper's table
spec; `compute_continuous_balance()` already degrades a missing-on-one-
side language to its existing `insufficient_data` fallback, so this only
changes behavior for a language genuinely absent from one side (both real
A/C collections have fixtures in all four).

These two tables replace the single, previously-reported repo-level
median setup_pct/teardown_pct/other_pct proportion table (Mann-Whitney U
+ Cliff's delta on per-repo *proportions*, "V" labeled for paper-column
consistency though the number was Cliff's delta) -- the paper settled on
two narrower tables (one purely descriptive, one inferential-but-simpler:
a binary coverage rate instead of a continuous proportion) instead of one
combined table. `compare_categorical_repo_level()`/
`repo_level_category_proportions()` (`_shared.py`) are still used
elsewhere in this package (rq1.py/rq3.py) -- only rq2.py's own use of them
for that removed table is gone.

A vs C only -- Dataset B (contemporary within-repo human baseline) is still
collected (db/b.db) but out of scope for this script's reported
comparisons; see rq1.py's module docstring.

## Supplementary analyses (not part of either main table)

**Unimodality check (Python teardown_pct)**: Hartigan & Hartigan's (1985)
dip test for unimodality, run separately per dataset on the per-repo
Python `teardown_pct` distribution (`_render_teardown_dip_test()`,
`run_dip_test()` in `_shared.py`, `_python_teardown_proportions()` for the
underlying per-repo values -- unrelated to Table 2's binary coverage
indicator, this is the continuous 0..1 proportion the old table used to
summarize as a median). A single-distribution shape diagnostic, not an A
vs C comparison test -- it exists to check whether Python's near-zero/
near-100% split (see internal-docs/methodology-improvements/
pytest-yield-teardown-vs-fixture-kind.md for why that split exists at all
-- `pytest_decorator`'s `"other"` classification, not a real absence of
teardown) reflects a genuinely bimodal population or a smooth continuum.
Reported alongside a text histogram of each distribution
(`render_ascii_histogram()`) since this package's reports are plain
markdown with no image pipeline. Kept and still computed (not part of
either paper table, but may still be cited in prose) -- rendered under
`generate_report()`'s "## Supplementary Analyses" section, after both
main tables.

**`has_teardown_pair`**: no separate analysis of this fixtures-table
column exists in this script (it never has -- `fixture_type_kind` above is
computed by its own, independent teardown-detection pass at extraction
time, built from the same lookup tables `has_teardown_pair` itself is
computed from, not derived from that column). Nothing to relabel as
supplementary here.

A dataset is skipped (not an error) if its db/{dataset}.db does not exist
yet.

python -m collection.research_questions.rq2
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .. import paths
from ..between_group_comparison import BalanceTest, compute_continuous_balance
from ..db import db_session
from ..logging_utils import get_logger
from ._shared import (
    COMPARISONS,
    DATASET_LABELS,
    OUTPUT_DIR,
    LanguageLeakage,
    NCounts,
    apply_fdr_correction,
    compute_language_leakage,
    continuous_effect_size_cell,
    format_p_value,
    pct,
    render_ascii_histogram,
    render_language_leakage_table,
    repo_level_category_n_counts,
    require_db_or_none,
    run_dip_test,
    write_markdown_report,
)

logger = get_logger(__name__)

# Fixed row order for both paper tables -- see the module docstring for why
# this is a fixed list rather than the "languages present on both sides"
# intersection convention used elsewhere in this package.
RQ2_LANGUAGES: tuple[str, ...] = ("java", "javascript", "python", "typescript")


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
    """Load RQ2 metrics for `dataset`, or None if its db doesn't exist yet."""
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
    fixture's own language too -- reading fixtures.fixture_type_kind
    directly, already classified once at extraction time (see this
    module's docstring), so this is a straight read, not a
    re-classification.

    `kind_counts_by_repo` feeds Table 2's Overall row (via
    _teardown_coverage_indicators() + compute_continuous_balance());
    `kind_counts_by_repo_and_language` feeds both tables' per-language rows
    -- Table 1's raw counts (_language_kind_totals(), summed across repos)
    and Table 2's per-language coverage test -- grouped by each fixture's
    own language (test_files.language), not the repo's tag, so a repo with
    fixtures in more than one language contributes to each language
    separately. Both also feed repo_level_category_n_counts() for Table
    2's n_A/n_C columns."""
    kind_distribution = _empty_kind_counts()
    kind_counts_by_repo: dict[int, dict[str, int]] = {}
    kind_counts_by_repo_and_language: dict[str, dict[int, dict[str, int]]] = {}

    rows = conn.execute(
        "SELECT f.repo_id, f.fixture_type_kind, tf.language FROM fixtures f "
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


def _render_kind_counts_table(a: DatasetMetrics, other: DatasetMetrics) -> str:
    """Table 1 (tab:rq2-counts): absolute setup/teardown fixture counts per
    language, purely descriptive -- no statistics, "other"-classified
    fixtures excluded from both columns. A 'setup_and_teardown'-classified
    fixture (pytest_decorator only -- see this module's docstring) counts
    toward *both* columns, since it genuinely provides both -- so the two
    columns are not mutually exclusive and Setup+Teardown can exceed the
    dataset's total fixture count."""
    other_label = other.dataset.upper()
    lines = [
        "Raw counts of setup-classified and teardown-classified fixtures "
        '("other"-classified fixtures, e.g. a bare `@pytest.fixture`, are '
        "excluded from both columns; a fixture classified as providing "
        "both -- e.g. a pytest fixture with setup code before its `yield` "
        "-- is counted in both columns, so they are not mutually "
        "exclusive). Total is the dataset-wide sum across every language "
        "present, not just the four rows below. Purely descriptive -- no "
        "significance test.",
        "",
        f"| Language | Setup A | Setup {other_label} | Teardown A | Teardown {other_label} |",
        "|---|---|---|---|---|",
        (
            f"| Total | {_effective_setup_count(a.kind_distribution):,} | "
            f"{_effective_setup_count(other.kind_distribution):,} | "
            f"{_effective_teardown_count(a.kind_distribution):,} | "
            f"{_effective_teardown_count(other.kind_distribution):,} |"
        ),
    ]

    a_totals = _language_kind_totals(a.kind_counts_by_repo_and_language)
    other_totals = _language_kind_totals(other.kind_counts_by_repo_and_language)
    for language in RQ2_LANGUAGES:
        a_kind = a_totals.get(language, {})
        other_kind = other_totals.get(language, {})
        lines.append(
            f"| {language} | {_effective_setup_count(a_kind):,} | "
            f"{_effective_setup_count(other_kind):,} | "
            f"{_effective_teardown_count(a_kind):,} | "
            f"{_effective_teardown_count(other_kind):,} |"
        )

    lines.append("")
    return "\n".join(lines)


def _teardown_coverage_indicators(by_repo: dict[int, dict[str, int]]) -> list[float]:
    """Per-repo binary indicator: 1.0 if that repo has >=1 teardown-
    providing fixture (classified 'teardown' or 'setup_and_teardown' --
    see _effective_teardown_count()), else 0.0. Population is repos with
    >=1 classified (setup/teardown/setup_and_teardown/other) fixture -- a
    repo with none is skipped, not counted as 0-coverage, matching
    repo_level_category_proportions()'s convention elsewhere in this
    package. Feeds compute_continuous_balance() directly: the mean of
    these 0/1 values *is* "% of repos with >=1 teardown fixture", so that
    call's agent_mean/human_mean double as Table 2's Coverage A/C (%)
    columns."""
    return [
        1.0 if _effective_teardown_count(counts) > 0 else 0.0
        for counts in by_repo.values()
        if sum(counts.values())
    ]


def _render_teardown_coverage_row(
    label: str, test: BalanceTest, n: NCounts, *, corrected: bool
) -> str:
    """One row of Table 2 -- coverage percentages come from the same
    compute_continuous_balance() call's agent_mean/human_mean (see
    _teardown_coverage_indicators()'s docstring), delta from Cliff's delta.
    `corrected` selects between `test`'s raw p (Overall, a single pooled
    test) and its BH-adjusted p (per-language rows, already computed by
    apply_fdr_correction() before this is called)."""
    d = test.details
    if d.get("reason") == "insufficient_data" or "error" in d:
        return f"| {label} | {n.n_a} | {n.n_c} | -- | -- | -- | -- |"
    p_cell = format_p_value(d["adjusted_p_value"]) if corrected else format_p_value(test.p_value)
    return (
        f"| {label} | {n.n_a} | {n.n_c} | "
        f"{pct(d.get('agent_mean'))} | {pct(d.get('human_mean'))} | "
        f"{continuous_effect_size_cell(test)} | {p_cell} |"
    )


def _render_teardown_coverage_table(a: DatasetMetrics, other: DatasetMetrics) -> str:
    """Table 2 (tab:rq2-coverage): % of repos with >=1 teardown-classified
    fixture, Mann-Whitney U + Cliff's delta on the per-repo binary
    indicator, BH-FDR-corrected across the four-language family. See this
    module's docstring for the full methodology."""
    other_label = other.dataset.upper()
    lines = [
        "Per-repository binary coverage: 1 if a repo has >=1 teardown-"
        "classified fixture, else 0 (population: repos with >=1 setup/"
        'teardown/other-classified fixture). "Coverage A/C (%)" is the '
        'share of that population with the indicator at 1. "delta" is '
        "Cliff's delta from a Mann-Whitney U test on the indicator between "
        "datasets. Overall is a single pooled test (raw p, never "
        "BH-corrected); each language's p is BH-FDR-corrected against the "
        "other 3 languages' tests only.",
        "",
        f"| Language | n_A | n_{other_label} | Coverage A (%) | Coverage {other_label} (%) | delta | p (BH) |",
        "|---|---|---|---|---|---|---|",
    ]

    overall_test = compute_continuous_balance(
        human_values=_teardown_coverage_indicators(other.kind_counts_by_repo),
        agent_values=_teardown_coverage_indicators(a.kind_counts_by_repo),
        variable="teardown_coverage_overall",
    )
    overall_n = repo_level_category_n_counts(a.kind_counts_by_repo, other.kind_counts_by_repo)
    lines.append(_render_teardown_coverage_row("Overall", overall_test, overall_n, corrected=False))

    per_language_tests: dict[str, BalanceTest] = {}
    per_language_n: dict[str, NCounts] = {}
    for language in RQ2_LANGUAGES:
        a_by_repo = a.kind_counts_by_repo_and_language.get(language, {})
        other_by_repo = other.kind_counts_by_repo_and_language.get(language, {})
        per_language_tests[language] = compute_continuous_balance(
            human_values=_teardown_coverage_indicators(other_by_repo),
            agent_values=_teardown_coverage_indicators(a_by_repo),
            variable=f"teardown_coverage_{language}",
        )
        per_language_n[language] = repo_level_category_n_counts(a_by_repo, other_by_repo)

    corrected_tests = apply_fdr_correction(per_language_tests)
    for language in RQ2_LANGUAGES:
        lines.append(
            _render_teardown_coverage_row(
                language, corrected_tests[language], per_language_n[language], corrected=True
            )
        )

    lines.append("")
    return "\n".join(lines)


def _python_teardown_proportions(metrics: DatasetMetrics) -> list[float]:
    """Per-repo teardown_pct for Python repos only -- a continuous 0..1
    proportion, distinct from Table 2's binary coverage indicator; this
    exposes the underlying distribution for _render_teardown_dip_test().

    A local reimplementation of repo_level_category_proportions() rather
    than a direct call: that shared helper reads a single category key,
    but a 'setup_and_teardown'-classified fixture is teardown-providing
    too (see _effective_teardown_count()), and this variable's numerator
    needs to reflect that the same way Table 2's coverage indicator
    does -- the denominator (all classified fixtures in the repo) is
    unaffected either way."""
    python_by_repo = metrics.kind_counts_by_repo_and_language.get("python", {})
    return [
        _effective_teardown_count(counts) / total
        for counts in python_by_repo.values()
        if (total := sum(counts.values()))
    ]


def _render_teardown_dip_test(a: DatasetMetrics, other: DatasetMetrics) -> str:
    """### Unimodality Check: Python Teardown Proportion (Dip Test).

    Supplementary -- not part of either main paper table (tab:rq2-counts,
    tab:rq2-coverage), rendered under generate_report()'s "## Supplementary
    Analyses" section since it may still be cited in prose. Hartigan &
    Hartigan's (1985) dip test, run separately per dataset on the per-repo
    Python teardown_pct distribution -- a single-distribution shape
    diagnostic (is this one distribution unimodal?), not an A vs C
    comparison test the way both main tables are. Reported side by side
    purely for reading convenience. See run_dip_test()'s docstring in
    _shared.py for the exact method (tabulated critical values,
    deterministic) and null hypothesis."""
    other_label = other.dataset.upper()
    lines = [
        "### Unimodality Check: Python Teardown Proportion (Dip Test)",
        "",
        "Hartigan & Hartigan's dip test for unimodality [CITE: Hartigan & "
        "Hartigan 1985, The Dip Test of Unimodality], run on the per-repo "
        "Python `teardown_pct` distribution (each repo's teardown-"
        "classified fixtures divided by its total classified fixtures) -- "
        "separately per dataset, since this tests whether *one* "
        "distribution is unimodal, not whether two distributions differ. "
        "Not the same value as Table 2's binary coverage indicator. Null "
        "hypothesis: the distribution is "
        "unimodal; a low p-value is evidence of multimodality (e.g. a "
        'real "most repos provide none, a distinct minority provide '
        'all" split, rather than a smooth continuum from 0% to 100%).',
        "",
    ]

    values_by_label = {
        label: _python_teardown_proportions(metrics)
        for label, metrics in (("A", a), (other_label, other))
    }

    header = ["Dataset", "n (Python repos)", "Dip statistic", "p-value"]
    lines += ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    for label, values in values_by_label.items():
        result = run_dip_test(values)
        if result is None:
            lines.append(f"| Dataset {label} | {len(values)} | -- | -- |")
        else:
            lines.append(
                f"| Dataset {label} | {result['n']} | "
                f"{result['dip_statistic']:.4f} | {format_p_value(result['p_value'])} |"
            )
    lines.append("")

    for label, values in values_by_label.items():
        lines += [
            f"**Dataset {label} -- teardown_pct distribution across "
            f"{len(values)} Python repos**",
            "",
            render_ascii_histogram(values),
            "",
        ]

    return "\n".join(lines)


def _render_comparison(label: str, a: DatasetMetrics, other: DatasetMetrics) -> str:
    lines = [
        f"## {label}: {DATASET_LABELS['a']} vs {DATASET_LABELS[other.dataset]}",
        "",
        "### Table 1: Fixture Counts by Type (tab:rq2-counts)",
        "",
        _render_kind_counts_table(a, other),
        "### Table 2: Teardown Coverage by Repository (tab:rq2-coverage)",
        "",
        _render_teardown_coverage_table(a, other),
    ]
    return "\n".join(lines)


def generate_report(*, db_root: Path = paths.DB_ROOT) -> str:
    loaded = {ds: load_dataset_metrics(ds, db_root=db_root) for ds in ("a", "c")}
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    lines = [
        "# RQ2 -- Setup and Teardown Characterization",
        "",
        "> How do agent-generated fixtures compare to human-written ones in setup "
        "and teardown provision?",
        "",
        f"Generated: {generated_at}",
        "",
        "See [docs/research-questions.md](../docs/research-questions.md) for "
        "the full RQ2 definition.",
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
            "(tab:rq2-counts, tab:rq2-coverage) but are kept and computed "
            "since they may still be referenced in prose.",
            "",
        ]
        for other_ds, _label in COMPARISONS:
            other_metrics = loaded[other_ds]
            if other_metrics is not None:
                lines.append(_render_teardown_dip_test(a_metrics, other_metrics))

    return "\n".join(lines)


def write_report(
    output_dir: Path = OUTPUT_DIR, *, db_root: Path = paths.DB_ROOT
) -> Path:
    report = generate_report(db_root=db_root)
    output_path = write_markdown_report(output_dir, "rq2.md", report)
    logger.info(f"RQ2 report written to {output_path}")
    return output_path


def main() -> None:
    path = write_report()
    print(f"RQ2 report written to {path}")


if __name__ == "__main__":
    main()
