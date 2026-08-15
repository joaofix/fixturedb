"""
RQ2 -- Setup and Teardown Characterization (Quantitative): how do
agent-generated fixtures compare to human-written ones in setup and
teardown provision?

One metric, computed per dataset (A/C): **fixture_type "kind" distribution**
-- setup / teardown / other. `fixture_type` alone can't cleanly split into
setup vs teardown for every type, so classification reuses two existing
tables from detector_shared.py -- the exact same ones `has_teardown_pair`
itself is computed from -- rather than a duplicate, drifting lookup:
  - `TYPE_BASED_TEARDOWN_PAIRS`: types where setup/teardown are different
    fixture_types (before_each/after_each, junit5_before_each/
    junit5_after_each, ...) -- classified by type alone.
  - `NAME_BASED_TEARDOWN_PAIRS`: types where setup and teardown share ONE
    fixture_type, distinguished only by fixture name (unittest_setup's
    setUp/tearDown, pytest_class_method's setup_method/teardown_method) --
    classified by (type, name).
Everything else (pytest_decorator -- setup with an *optional* teardown via
`yield`, not captured by type or name; junit_rule/junit_class_rule/
vitest_around_each/vitest_around_all -- inherently both at once, see
ALWAYS_HAS_TEARDOWN_TYPES; testng_data_provider -- neither, it's not a
lifecycle hook) buckets as "other" instead of forcing a fake split.

For each repo, this yields three proportions -- setup_pct/teardown_pct/
other_pct (that repo's classified fixtures falling in each kind, summing
to 100%). The paper's one reported table is: median per-repo setup_pct/
teardown_pct for A and C, per language and Overall, plus one repo-level
effect size + BH-FDR-corrected p-value per language.

That test reuses `compare_categorical_repo_level()` (`_shared.py`) exactly
as already used elsewhere in this package -- per-repo category
proportions compared via Mann-Whitney U + Cliff's delta, one BalanceTest
per category (setup/teardown/other), the same de-clustering fix RQ1/RQ3's
repo-level aggregates already apply: a plain chi-square over fixture-level
counts treats a repo's hundreds of correlated fixtures as that many
independent observations, inflating both the statistic and its effect
size; this instead compares one proportion per repo, so each repo counts
once. **The table's single "V (A<->C)"/"p (BH)" column pair per row is the
`setup` category's own test** -- setup_pct and teardown_pct aren't
independent (together with other_pct they sum to 100% per repo), so one
test represents the whole row; setup is picked since it's the table's
first descriptive column. The column is labeled "V" for consistency with
the paper's other effect-size columns, but the number itself is Cliff's
delta (from the Mann-Whitney test above), not literally Cramer's V (which
would come from a chi-square test instead) -- flagged explicitly here and
in the table's own intro text so this isn't a silent mislabel.
`teardown`'s median rides along from the same per-(language) test call,
purely descriptive (no separate significance test of its own). `other` is
computed and available (`kind_counts_by_repo*`) but not shown in the main
table.

The Overall row is `setup`'s pooled (dataset-wide) test, raw p-value, never
BH-corrected (a single test needs no multiple-comparison correction, same
convention as every other RQ1-3 comparison table's Overall row). Each
language's row is BH-FDR-corrected against the other 3 languages' `setup`
tests only -- this variable's own family, independent of every other
metric and of the Overall row (see `apply_fdr_correction()`'s docstring).

A vs C only -- Dataset B (contemporary within-repo human baseline) is still
collected (db/b.db) but out of scope for this script's reported
comparisons; see rq1.py's module docstring.

**Unimodality check (Python teardown_pct)**: a second, distinct metric --
Hartigan & Hartigan's (1985) dip test for unimodality, run separately per
dataset on the per-repo Python `teardown_pct` distribution the table
above already summarizes down to one median (`_render_teardown_dip_test()`,
`run_dip_test()` in `_shared.py`). This is a single-distribution shape
diagnostic, not an A vs C comparison test -- it exists to check whether
Python's near-zero/near-100% median split (see
internal-docs/methodology-improvements/pytest-yield-teardown-vs-fixture-kind.md
for why that split exists at all -- `pytest_decorator`'s `"other"`
classification, not a real absence of teardown) reflects a genuinely
bimodal population (most repos cluster at one extreme, a distinct
minority at the other) or a smooth continuum that the median alone
doesn't reveal. Reported alongside a text histogram of each
distribution (`render_ascii_histogram()`) since this package's reports
are plain markdown with no image pipeline.

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
from ..between_group_comparison import BalanceTest
from ..db import db_session
from ..detector_shared import NAME_BASED_TEARDOWN_PAIRS, TYPE_BASED_TEARDOWN_PAIRS
from ..logging_utils import get_logger
from ._shared import (
    COMPARISONS,
    DATASET_LABELS,
    OUTPUT_DIR,
    LanguageLeakage,
    NCounts,
    apply_fdr_correction,
    compare_categorical_repo_level,
    compute_language_leakage,
    continuous_effect_size_cell,
    format_p_value,
    pct,
    render_ascii_histogram,
    render_language_leakage_table,
    repo_level_category_n_counts,
    repo_level_category_proportions,
    require_db_or_none,
    run_dip_test,
    write_markdown_report,
)

logger = get_logger(__name__)

TYPE_BASED_SETUP_TYPES: set[str] = set(TYPE_BASED_TEARDOWN_PAIRS.keys())
TYPE_BASED_TEARDOWN_TYPES: set[str] = set(TYPE_BASED_TEARDOWN_PAIRS.values())

# fixture_type -> {setup names} / {teardown names}, for the fixture_types
# where type alone is ambiguous and the fixture's own name disambiguates.
NAME_BASED_SETUP_NAMES: dict[str, set[str]] = {
    ft: set(names.keys()) for ft, names in NAME_BASED_TEARDOWN_PAIRS.items()
}
NAME_BASED_TEARDOWN_NAMES: dict[str, set[str]] = {
    ft: set(names.values()) for ft, names in NAME_BASED_TEARDOWN_PAIRS.items()
}


def _kind(fixture_type: str, name: str | None = None) -> str:
    if fixture_type in TYPE_BASED_SETUP_TYPES:
        return "setup"
    if fixture_type in TYPE_BASED_TEARDOWN_TYPES:
        return "teardown"
    if fixture_type in NAME_BASED_TEARDOWN_PAIRS and name is not None:
        if name in NAME_BASED_SETUP_NAMES[fixture_type]:
            return "setup"
        if name in NAME_BASED_TEARDOWN_NAMES[fixture_type]:
            return "teardown"
    return "other"


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


def _fetch_kinds_and_repo_counts(
    conn: sqlite3.Connection,
) -> tuple[
    dict[str, int],
    dict[int, dict[str, int]],
    dict[str, dict[int, dict[str, int]]],
]:
    """Single pass over every fixture: dataset-level kind distribution
    (descriptive only), per-repo {setup/teardown/other: count} (Overall),
    and the same per-repo counts bucketed by each fixture's own language
    too -- classified once via `_kind()` so these views can't disagree
    with each other (a second, SQL-side classification would just be
    `_kind()` duplicated in a different language).

    `kind_counts_by_repo` feeds compare_categorical_repo_level() for the
    Overall row's repo-declustered test; `kind_counts_by_repo_and_language`
    feeds the same per language -- grouped by each fixture's own language
    (test_files.language), not the repo's tag, so a repo with fixtures in
    more than one language contributes to each language's own repo-level
    proportions separately. Both also feed repo_level_category_n_counts()
    for the table's n_A/n_C columns."""
    kind_distribution = {"setup": 0, "teardown": 0, "other": 0}
    kind_counts_by_repo: dict[int, dict[str, int]] = {}
    kind_counts_by_repo_and_language: dict[str, dict[int, dict[str, int]]] = {}

    rows = conn.execute(
        "SELECT f.repo_id, f.fixture_type, f.name, tf.language FROM fixtures f "
        "JOIN test_files tf ON f.file_id = tf.id WHERE f.fixture_type IS NOT NULL"
    ).fetchall()
    for repo_id, fixture_type, name, language in rows:
        kind = _kind(fixture_type, name)
        kind_distribution[kind] += 1

        repo_kind_counts = kind_counts_by_repo.setdefault(
            repo_id, {"setup": 0, "teardown": 0, "other": 0}
        )
        repo_kind_counts[kind] += 1

        lang_repo_counts = kind_counts_by_repo_and_language.setdefault(
            language, {}
        ).setdefault(repo_id, {"setup": 0, "teardown": 0, "other": 0})
        lang_repo_counts[kind] += 1

    return kind_distribution, kind_counts_by_repo, kind_counts_by_repo_and_language


def _render_dataset_summary(metrics: DatasetMetrics) -> str:
    lines = [f"### {DATASET_LABELS[metrics.dataset]} -- {metrics.n_fixtures:,} fixtures", ""]

    total_kind = sum(metrics.kind_distribution.values())
    lines += ["**fixture_type kind distribution**", "", "| Kind | Count | % |", "|---|---|---|"]
    for kind in ("setup", "teardown", "other"):
        count = metrics.kind_distribution.get(kind, 0)
        kind_pct = 100 * count / total_kind if total_kind else 0.0
        lines.append(f"| {kind} | {count:,} | {kind_pct:.1f}% |")
    lines.append("")

    lines.append(render_language_leakage_table(metrics.language_leakage))

    return "\n".join(lines)


def _kind_proportion_row(
    label: str,
    setup_test: BalanceTest,
    teardown_test: BalanceTest,
    n: NCounts,
    *,
    corrected: bool,
) -> str:
    """One row: descriptive setup/teardown medians (from each category's
    own repo-level BalanceTest) plus setup's own effect size/p-value,
    which stands in for the whole row -- see this module's docstring for
    why. `corrected` selects between setup_test's raw p (Overall, a single
    pooled test) and its BH-adjusted p (per-language rows, already computed
    by apply_fdr_correction() before this is called)."""
    d = setup_test.details
    if d.get("reason") == "insufficient_data" or "error" in d:
        return f"| {label} | {n.n_a} | {n.n_c} | -- | -- | -- | -- | -- | -- |"
    p_cell = (
        format_p_value(d["adjusted_p_value"]) if corrected else format_p_value(setup_test.p_value)
    )
    td = teardown_test.details
    return (
        f"| {label} | {n.n_a} | {n.n_c} | "
        f"{pct(d.get('agent_median'))} | {pct(d.get('human_median'))} | "
        f"{pct(td.get('agent_median'))} | {pct(td.get('human_median'))} | "
        f"{continuous_effect_size_cell(setup_test)} | {p_cell} |"
    )


def _render_kind_proportion_table(a: DatasetMetrics, other: DatasetMetrics) -> str:
    """The paper's one RQ2 table -- see this module's docstring for the
    full methodology (repo-level setup/teardown/other proportions, Mann-
    Whitney U + Cliff's delta via compare_categorical_repo_level(), the
    "V" labeling caveat)."""
    other_label = other.dataset.upper()
    lines = [
        "Per-repository proportions: for each repo, "
        "`setup_pct`/`teardown_pct`/`other_pct` = that repo's "
        "setup/teardown/other-classified fixtures divided by its total "
        "classified fixtures (the three sum to 100% per repo; `other_pct` "
        "isn't shown below). Median is taken over those per-repo "
        "proportions, not a single pooled fixture-level percentage. "
        f'"V (A↔{other_label})"/"p (BH)" are the `setup` category\'s own '
        "repo-level Mann-Whitney U + Cliff's delta test (`setup`/`teardown` "
        "aren't independent -- together with `other` they sum to 100% per "
        "repo -- so this one test represents the row). The column is "
        "labeled \"V\" for consistency with the paper's other effect-size "
        "columns, but the number is Cliff's delta, not literally Cramer's "
        "V. Overall is a single pooled test (raw p, never BH-corrected); "
        "each language's p is BH-FDR-corrected against the other 3 "
        "languages' `setup` tests only.",
        "",
        "| Language | n_A | "
        f"n_{other_label} | Setup A (%) | Setup {other_label} (%) | "
        f"Teardown A (%) | Teardown {other_label} (%) | V (A↔{other_label}) | p (BH) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]

    overall = compare_categorical_repo_level(
        a.kind_counts_by_repo, other.kind_counts_by_repo, "fixture_type_kind"
    )
    overall_n = repo_level_category_n_counts(a.kind_counts_by_repo, other.kind_counts_by_repo)
    lines.append(
        _kind_proportion_row(
            "Overall", overall["setup"], overall["teardown"], overall_n, corrected=False
        )
    )

    languages = sorted(
        set(a.kind_counts_by_repo_and_language) & set(other.kind_counts_by_repo_and_language)
    )
    per_language_results: dict[str, dict[str, BalanceTest]] = {}
    per_language_n: dict[str, NCounts] = {}
    for language in languages:
        a_by_repo = a.kind_counts_by_repo_and_language[language]
        other_by_repo = other.kind_counts_by_repo_and_language[language]
        per_language_results[language] = compare_categorical_repo_level(
            a_by_repo, other_by_repo, f"fixture_type_kind_{language}"
        )
        per_language_n[language] = repo_level_category_n_counts(a_by_repo, other_by_repo)

    corrected_setup = apply_fdr_correction(
        {language: result["setup"] for language, result in per_language_results.items()}
    )
    for language in languages:
        lines.append(
            _kind_proportion_row(
                language,
                corrected_setup[language],
                per_language_results[language]["teardown"],
                per_language_n[language],
                corrected=True,
            )
        )

    lines.append("")
    return "\n".join(lines)


def _python_teardown_proportions(metrics: DatasetMetrics) -> list[float]:
    """Per-repo teardown_pct for Python repos only -- the same per-repo
    proportions the Python row of _render_kind_proportion_table() already
    summarizes down to one median; this exposes the underlying
    distribution itself for _render_teardown_dip_test()."""
    python_by_repo = metrics.kind_counts_by_repo_and_language.get("python", {})
    return repo_level_category_proportions(python_by_repo, "teardown")


def _render_teardown_dip_test(a: DatasetMetrics, other: DatasetMetrics) -> str:
    """## Unimodality Check: Python Teardown Proportion (Dip Test).

    Hartigan & Hartigan's (1985) dip test, run separately per dataset on
    the per-repo Python teardown_pct distribution -- a single-distribution
    shape diagnostic (is this one distribution unimodal?), not an A vs C
    comparison test the way every other table in this report is. Reported
    side by side purely for reading convenience. See run_dip_test()'s
    docstring in _shared.py for the exact method (tabulated critical
    values, deterministic) and null hypothesis."""
    other_label = other.dataset.upper()
    lines = [
        "## Unimodality Check: Python Teardown Proportion (Dip Test)",
        "",
        "Hartigan & Hartigan's dip test for unimodality [CITE: Hartigan & "
        "Hartigan 1985, The Dip Test of Unimodality], run on the same "
        "per-repo Python `teardown_pct` values the table above summarizes "
        "as a single median -- separately per dataset, since this tests "
        "whether *one* distribution is unimodal, not whether two "
        "distributions differ. Null hypothesis: the distribution is "
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
        _render_kind_proportion_table(a, other),
        _render_teardown_dip_test(a, other),
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
