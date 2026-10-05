"""RQ2 -- code characteristics of agent-written and human-written fixtures.

Per dataset, summary statistics for the three paper metrics: `loc`,
`cyclomatic_complexity` and `comment_density`. Then an A vs C comparison.

Each repository gives one value per metric: the mean over its fixtures. The
two datasets are compared with a Mann-Whitney U test. The overall row is not
corrected. The per-language rows are corrected with Benjamini-Hochberg, one
family per metric.

The report also has a diagnostic section that uses the per-repository median
instead of the mean. It is not used in the paper. It shows how much the result
depends on that choice.

`fixture_type` is shown as a plain distribution per dataset. It has no test.

Writes `research_questions/rq2.md`. Run with `python -m collection.research_questions.rq2`.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .. import paths
from ..between_group_comparison import (
    BalanceTest,
    compute_continuous_balance,
)
from ..db import db_session
from ..logging_utils import get_logger
from ._shared import (
    COMPARISONS,
    DATASET_LABELS,
    NO_BODY_FIXTURE_TYPES,
    OUTPUT_DIR,
    LanguageLeakage,
    NCounts,
    compute_language_leakage,
    compute_stratified_continuous_balance,
    fetch_categorical_column,
    fetch_continuous_column,
    fetch_continuous_column_by_repo,
    fmt,
    pct,
    percentile,
    render_comparison_table,
    render_language_leakage_table,
    repo_level_means,
    repo_level_medians,
    require_db_or_none,
    summarize_continuous,
    write_markdown_report,
)

logger = get_logger(__name__)

# The three continuous metrics reported in the paper -- exhaustive, not
# illustrative. Order here is this list's own reporting order (both in the
# per-dataset summary and the A-vs-C comparison's "Paper Metrics" section).
PAPER_CONTINUOUS_METRICS = ["loc", "cyclomatic_complexity", "comment_density"]
# Mann-Whitney-tested continuous metrics. These are the paper metrics. max_nesting_depth
# (along with num_objects_instantiated/num_external_calls/has_teardown_pair)
# was dropped from the extracted metric set entirely, so CONTINUOUS_METRICS
# is now exactly the paper set. See this module's docstring for why
# num_parameters is still dropped from this list (fetched fixture-level for
# the descriptive table + floor-percentage footnote, never Mann-Whitney
# tested).
CONTINUOUS_METRICS = PAPER_CONTINUOUS_METRICS
# metric -> the value that "floored" means "structurally minimal" for it
# (0 params: no arguments) -- drives the descriptive floor-percentage
# footnote only, no comparative test.
FLOOR_CHECK_METRICS = {"num_parameters": 0}
# The per-dataset descriptive "Continuous metrics" tables in
# _render_dataset_summary() (repo-level) and the floor-percentage footnote
# (deliberately fixture-level) still show/use all of these -- neither is a
# comparison, so dropping num_parameters from CONTINUOUS_METRICS (the
# Mann-Whitney-tested list) doesn't affect either.
DESCRIPTIVE_CONTINUOUS_METRICS = CONTINUOUS_METRICS + list(FLOOR_CHECK_METRICS)
CATEGORICAL_METRICS = ["fixture_type"]


@dataclass
class DatasetMetrics:
    dataset: str
    n_fixtures: int
    continuous_raw: dict[str, list[float]] = field(default_factory=dict)
    categorical: dict[str, dict[str, int]] = field(default_factory=dict)
    language_leakage: list[LanguageLeakage] = field(default_factory=list)
    agent_type_distribution: dict[str, int] = field(default_factory=dict)
    repo_level_continuous: dict[str, list[float]] = field(default_factory=dict)
    repo_level_continuous_by_language: dict[str, dict[str, list[float]]] = field(
        default_factory=dict
    )
    # Diagnostic-only companion to the two fields above: same repo-level
    # declustering, but each repo contributes its own MEDIAN fixture
    # instead of its mean. Restricted to CONTINUOUS_METRICS (the 3 paper
    # metrics) -- not part of the paper's methodology, never cited as a
    # result, see this module's docstring for why it's kept at all.
    repo_level_continuous_median_diagnostic: dict[str, list[float]] = field(default_factory=dict)
    repo_level_continuous_by_language_median_diagnostic: dict[str, dict[str, list[float]]] = field(
        default_factory=dict
    )
    # metric -> % of fixtures at FLOOR_CHECK_METRICS' floor value (descriptive
    # only -- see this module's docstring).
    floor_pct: dict[str, float] = field(default_factory=dict)


def _fetch_continuous_by_repo_and_language(
    conn: sqlite3.Connection,
) -> dict[str, dict[str, dict[int, list[float]]]]:
    """{metric: {language: {repo_id: [values]}}} for every CONTINUOUS_METRICS
    column, one query pass over fixtures joined to test_files -- feeds both
    repo_level_means() (primary) and repo_level_medians() (diagnostic-only,
    see this module's docstring) per (metric, language) for the
    per-language continuous family tests, the same repo-declustering
    repo_level_continuous already applies pooled (see
    compute_stratified_continuous_balance()'s docstring in _shared.py for
    why per-language stays repo-level too).

    Excludes NO_BODY_FIXTURE_TYPES (see _shared.py) -- this function only
    ever serves CONTINUOUS_METRICS (loc/cyclomatic_complexity/
    comment_density), never num_parameters, so the exclusion applies
    unconditionally rather than needing an opt-in flag the way
    fetch_continuous_column_by_repo()'s does."""
    columns_sql = ", ".join(f"f.{m}" for m in CONTINUOUS_METRICS)
    placeholders = ", ".join("?" for _ in NO_BODY_FIXTURE_TYPES)
    rows = conn.execute(
        f"SELECT f.repo_id, tf.language, {columns_sql} FROM fixtures f "
        "JOIN test_files tf ON f.file_id = tf.id "
        f"WHERE f.fixture_type NOT IN ({placeholders})",
        tuple(NO_BODY_FIXTURE_TYPES),
    ).fetchall()
    result: dict[str, dict[str, dict[int, list[float]]]] = {m: {} for m in CONTINUOUS_METRICS}
    for row in rows:
        repo_id, language = row[0], row[1]
        for metric, value in zip(CONTINUOUS_METRICS, row[2:]):
            if value is None:
                continue
            result[metric].setdefault(language, {}).setdefault(repo_id, []).append(value)
    return result


def _floor_percentage(values: list[float], floor: float) -> float | None:
    """Fraction (0..1) of `values` sitting exactly at `floor` -- documents
    the floor-binding FLOOR_CHECK_METRICS' metrics show (0 params)
    instead of silently dropping them from the report. `None` (not 0.0)
    for no data, so callers can render "no data" rather than a misleading
    "0% at floor". A 0..1 fraction (not already a 0-100 percentage) to
    match pct()'s convention -- see _shared.py."""
    if not values:
        return None
    return sum(1 for v in values if v == floor) / len(values)


def load_dataset_metrics(
    dataset: str, *, db_root: Path = paths.DB_ROOT
) -> DatasetMetrics | None:
    """Load RQ2 metrics for `dataset`, or None if its db doesn't exist yet."""
    db_file = require_db_or_none(dataset, db_root)
    if db_file is None:
        return None

    with db_session(db_file) as conn:
        n_fixtures = conn.execute("SELECT COUNT(*) FROM fixtures").fetchone()[0]
        # DESCRIPTIVE_CONTINUOUS_METRICS (5), not CONTINUOUS_METRICS (4) --
        # num_parameters is still fetched fixture-level for the
        # floor-percentage footnote (a fixture-level question: what fraction
        # of *fixtures* sit at the floor). It is not Mann-Whitney tested, and
        # the per-dataset table does not show it (see repo_level_continuous below).
        continuous_raw = {
            m: fetch_continuous_column(conn, "fixtures", m) for m in DESCRIPTIVE_CONTINUOUS_METRICS
        }
        categorical = {m: fetch_categorical_column(conn, "fixtures", m) for m in CATEGORICAL_METRICS}
        language_leakage = compute_language_leakage(conn)
        # Descriptive only, not run through a significance test: agent_type
        # is the group-defining variable for Dataset A (which agent
        # authored this fixture), not a content metric to test A-vs-C on --
        # comparing it against C's constant "human_pre2022" value would be
        # tautological (echoing commit_kind), not a real finding. Still
        # shown for C too (and for B, if this loader is called on it
        # directly -- it's dataset-letter-agnostic) since it doubles as a
        # sanity check that those corpora really are cleanly non-agent.
        agent_type_distribution = fetch_categorical_column(conn, "fixtures", "agent_type")
        # One mean-per-repo value per continuous metric -- see
        # repo_level_means()'s docstring for why this exists: pseudo-
        # replication (fixtures cluster within repos), fixed by testing one
        # value per repo instead of every fixture as an independent
        # observation. repo_level_continuous_by_language is the same idea,
        # bucketed by each fixture's own language too, for the per-language
        # family tests. Covers DESCRIPTIVE_CONTINUOUS_METRICS (5), not just
        # CONTINUOUS_METRICS (4) -- num_parameters isn't Mann-Whitney tested,
        # but _render_dataset_summary()'s descriptive table reads every
        # metric's median/mean/min/max/stdev from here too, so it stays
        # repo-level throughout, same as the tested metrics, rather than
        # silently reverting to fixture-level for just this one column.
        #
        # CONTINUOUS_METRICS (loc/cyclomatic_complexity/comment_density)
        # exclude NO_BODY_FIXTURE_TYPES -- see that constant's docstring
        # in _shared.py. num_parameters does NOT
        # exclude them: 0 is a correct, not-Lizard-derived value for a
        # field's parameter count, unlike CC (which is a meaningless Lizard
        # fallback default for these), so it
        # has no equivalent reason to drop them.
        #
        # _by_repo_per_metric is also reused below for
        # repo_level_continuous_median_diagnostic, so each metric's
        # per-repo fixture lists are only fetched once regardless of how
        # many aggregations (mean, median) run over them.
        _by_repo_per_metric = {
            m: fetch_continuous_column_by_repo(
                conn,
                "fixtures",
                m,
                exclude_fixture_types=(
                    NO_BODY_FIXTURE_TYPES if m in CONTINUOUS_METRICS else None
                ),
            )
            for m in DESCRIPTIVE_CONTINUOUS_METRICS
        }
        repo_level_continuous = {
            m: repo_level_means(by_repo) for m, by_repo in _by_repo_per_metric.items()
        }
        # Diagnostic-only, NOT the paper's methodology -- see this module's
        # docstring's "Median-per-repo was tried and reverted" section.
        # Restricted to CONTINUOUS_METRICS: num_parameters is never
        # Mann-Whitney tested either way, so it has no diagnostic
        # counterpart to compute.
        repo_level_continuous_median_diagnostic = {
            m: repo_level_medians(_by_repo_per_metric[m]) for m in CONTINUOUS_METRICS
        }
        continuous_by_repo_and_language = _fetch_continuous_by_repo_and_language(conn)
        repo_level_continuous_by_language = {
            metric: {
                language: repo_level_means(by_repo) for language, by_repo in by_language.items()
            }
            for metric, by_language in continuous_by_repo_and_language.items()
        }
        repo_level_continuous_by_language_median_diagnostic = {
            metric: {
                language: repo_level_medians(by_repo) for language, by_repo in by_language.items()
            }
            for metric, by_language in continuous_by_repo_and_language.items()
        }

    floor_pct = {
        metric: _floor_percentage(continuous_raw[metric], floor)
        for metric, floor in FLOOR_CHECK_METRICS.items()
    }

    return DatasetMetrics(
        dataset=dataset,
        n_fixtures=n_fixtures,
        continuous_raw=continuous_raw,
        categorical=categorical,
        language_leakage=language_leakage,
        agent_type_distribution=agent_type_distribution,
        repo_level_continuous=repo_level_continuous,
        repo_level_continuous_by_language=repo_level_continuous_by_language,
        repo_level_continuous_median_diagnostic=repo_level_continuous_median_diagnostic,
        repo_level_continuous_by_language_median_diagnostic=(
            repo_level_continuous_by_language_median_diagnostic
        ),
        floor_pct=floor_pct,
    )


def compare_datasets_repo_level(
    a: DatasetMetrics, other: DatasetMetrics
) -> dict[str, BalanceTest]:
    """A vs `other`, one mean value per repo instead of one value per
    fixture -- the Overall row for each continuous metric's family table.
    Repo-level throughout: the per-language rows (compute_stratified_
    continuous_balance() on repo_level_continuous_by_language) use the
    same one-value-per-repo basis, so a continuous metric's whole table is
    never fixture-level -- see this module's docstring. This is the
    paper's actual methodology -- see compare_datasets_repo_level_median_
    diagnostic() below for the diagnostic-only median-per-repo variant."""
    return {
        metric: compute_continuous_balance(
            human_values=other.repo_level_continuous[metric],
            agent_values=a.repo_level_continuous[metric],
            variable=metric,
        )
        for metric in CONTINUOUS_METRICS
    }


def compare_datasets_repo_level_median_diagnostic(
    a: DatasetMetrics, other: DatasetMetrics
) -> dict[str, BalanceTest]:
    """Diagnostic-only sibling of compare_datasets_repo_level() -- same
    shape, but each repo contributes its own median fixture value instead
    of its mean (repo_level_continuous_median_diagnostic). NOT the paper's
    methodology and never cited as a result -- kept to make visible how
    much a repo's median CC/comment_density collapsing to the metric's
    floor value changes the comparison, purely as an artifact of the
    aggregation choice. See this module's docstring."""
    return {
        metric: compute_continuous_balance(
            human_values=other.repo_level_continuous_median_diagnostic[metric],
            agent_values=a.repo_level_continuous_median_diagnostic[metric],
            variable=f"{metric}_median_diagnostic",
        )
        for metric in CONTINUOUS_METRICS
    }


def _render_continuous_summary_table(label: str, metric_list: list[str], metrics: DatasetMetrics) -> str:
    """One repo-level descriptive table (median/mean/min/max/stdev, `n` =
    repo count) for `metric_list` -- shared by both tiers of
    _render_dataset_summary()'s continuous-metrics section (Paper /
    Other), so the two tables stay identically formatted."""
    lines = [f"**Continuous metrics -- {label}** (repo-level: one mean per repo, not one value per fixture)",
             "", "| Metric | n | median | mean | min | max | stdev |",
             "|---|---|---|---|---|---|---|"]
    for metric in metric_list:
        s = summarize_continuous(metrics.repo_level_continuous[metric])
        lines.append(
            f"| {metric} | {s['n']:,} | {fmt(s['median'])} | {fmt(s['mean'])} | "
            f"{fmt(s['min'], 0)} | {fmt(s['max'], 0)} | {fmt(s['stdev'])} |"
        )
    lines.append("")
    return "\n".join(lines)


def _render_dataset_summary(metrics: DatasetMetrics) -> str:
    lines = [f"### {DATASET_LABELS[metrics.dataset]} -- {metrics.n_fixtures:,} fixtures", ""]

    lines.append(_render_continuous_summary_table("Paper", PAPER_CONTINUOUS_METRICS, metrics))
    lines.append(
        _render_continuous_summary_table(
            "Other (not in the paper)", list(FLOOR_CHECK_METRICS), metrics
        )
    )

    for metric in CATEGORICAL_METRICS:
        dist = metrics.categorical[metric]
        total = sum(dist.values())
        lines += [f"**{metric} distribution**", "", "| Value | Count | % |", "|---|---|---|"]
        if total == 0:
            lines.append("| _(no data)_ | -- | -- |")
        else:
            for value, count in sorted(dist.items(), key=lambda kv: -kv[1]):
                lines.append(f"| {value} | {count:,} | {100 * count / total:.1f}% |")
        lines.append("")

    lines.append(render_language_leakage_table(metrics.language_leakage))

    dist = metrics.agent_type_distribution
    total = sum(dist.values())
    lines += [
        "**agent_type distribution** (descriptive only, not compared against "
        "other datasets -- see load_dataset_metrics()'s docstring for why)",
        "",
        "| Value | Count | % |",
        "|---|---|---|",
    ]
    if total == 0:
        lines.append("| _(no data)_ | -- | -- |")
    else:
        for value, count in sorted(dist.items(), key=lambda kv: -kv[1]):
            lines.append(f"| {value} | {count:,} | {100 * count / total:.1f}% |")
    lines.append("")

    return "\n".join(lines)


def _per_language_medians(
    a_by_language: dict[str, list[float]], other_by_language: dict[str, list[float]]
) -> dict[str, tuple[float | None, float | None]]:
    """{language: (A median, other median)} of the exact same per-repo
    values compute_stratified_continuous_balance() tests for this metric --
    summarize_continuous()'s own median, the same aggregation
    _render_continuous_summary_table() uses for the dataset-wide
    descriptive tables, not a new computation. Only languages present on
    both sides get a real per-language *test* row (render_comparison_
    table()'s `per_language` is already restricted to that intersection),
    so computing this over the union of languages present on either side
    is harmless -- entries for a language missing on one side simply never
    get looked up as a table row. Takes the two by-language dicts directly
    (not a metric name + DatasetMetrics) so it works for either the
    primary (mean-per-repo) or diagnostic (median-per-repo) view -- see
    _render_continuous_metric()'s callers."""
    languages = set(a_by_language) | set(other_by_language)
    return {
        language: (
            summarize_continuous(a_by_language.get(language, []))["median"],
            summarize_continuous(other_by_language.get(language, []))["median"],
        )
        for language in languages
    }


def _per_language_percentile(
    a_by_language: dict[str, list[float]], other_by_language: dict[str, list[float]], q: float
) -> dict[str, tuple[float | None, float | None]]:
    """{language: (A value, other value)} of the qth percentile (0-100) of
    the exact same per-repo values compute_stratified_continuous_
    balance() tests for this metric -- _shared.py's percentile(), not a
    new aggregation. Sibling of _per_language_medians() above (which stays
    on statistics.median() via summarize_continuous() rather than being
    rewritten to call percentile(values, 50) -- no behavior change for the
    already-shipped median columns). Same by-language-dicts-directly and
    union-of-languages reasoning as _per_language_medians()'s docstring."""
    languages = set(a_by_language) | set(other_by_language)
    return {
        language: (
            percentile(a_by_language.get(language, []), q),
            percentile(other_by_language.get(language, []), q),
        )
        for language in languages
    }


def _render_continuous_metric(
    metric: str,
    a_overall: list[float],
    other_overall: list[float],
    a_by_language: dict[str, list[float]],
    other_by_language: dict[str, list[float]],
    overall: BalanceTest,
    other_dataset: str,
    *,
    include_percentile_columns: bool = False,
) -> str:
    """One metric's full table (Overall + per-language family rows),
    repo-level throughout -- see compare_datasets_repo_level()'s docstring.
    Takes the repo-level values directly (not a DatasetMetrics pair) so
    the same renderer serves both the paper's primary (mean-per-repo) view
    and the diagnostic (median-per-repo) view -- see _render_comparison()'s
    two call sites.

    `include_percentile_columns`: adds "A median"/"<OTHER> median", "A
    Q3"/"<OTHER> Q3", and "A P90"/"<OTHER> P90" columns (per
    render_comparison_table()'s per_language_medians/per_language_q3/
    per_language_p90) -- set only for the three paper continuous metrics
    (loc/cyclomatic_complexity/comment_density) -- these are the paper's
    per-language comparison tables, showing the underlying
    distribution (not just its center) alongside the effect size, without
    changing the "Other" tier's table shape. Q3/P90 exist specifically to
    explain an effect that reaches significance despite identical
    medians -- a real difference concentrated in the upper tail of one
    distribution, invisible to the median alone."""
    overall_n = NCounts(len(a_overall), len(other_overall))
    per_language = compute_stratified_continuous_balance(
        a_by_language, other_by_language, metric
    )
    per_language_n = {
        language: NCounts(
            len(a_by_language.get(language, [])),
            len(other_by_language.get(language, [])),
        )
        for language in per_language
    }
    per_language_medians = (
        _per_language_medians(a_by_language, other_by_language)
        if include_percentile_columns
        else None
    )
    per_language_q3 = (
        _per_language_percentile(a_by_language, other_by_language, 75)
        if include_percentile_columns
        else None
    )
    per_language_p90 = (
        _per_language_percentile(a_by_language, other_by_language, 90)
        if include_percentile_columns
        else None
    )
    lines = [f"### {metric}", ""]
    lines.append(
        render_comparison_table(
            overall,
            overall_n,
            per_language,
            per_language_n,
            other_dataset=other_dataset,
            per_language_medians=per_language_medians,
            per_language_q3=per_language_q3,
            per_language_p90=per_language_p90,
        )
    )
    return "\n".join(lines)


def _render_floor_percentage_footnote(a: DatasetMetrics, other: DatasetMetrics) -> str:
    """Descriptive-only footnote for num_parameters, replacing its old
    Mann-Whitney section -- see this module's docstring for why it was
    dropped from comparative testing."""
    lines = [
        "**Floor-binding check (descriptive only -- not a comparative "
        "test)** -- `num_parameters` was dropped from Mann-Whitney testing "
        "(see this module's docstring) because it floors heavily in both "
        "datasets; this documents exactly how heavily, transparently, "
        "instead of silently omitting it.",
        "",
        f"| Metric | Floor value | {DATASET_LABELS['a']} at floor | "
        f"{DATASET_LABELS[other.dataset]} at floor |",
        "|---|---|---|---|",
    ]
    for metric, floor in FLOOR_CHECK_METRICS.items():
        lines.append(
            f"| {metric} | {floor} | {pct(a.floor_pct.get(metric))} | "
            f"{pct(other.floor_pct.get(metric))} |"
        )
    lines.append("")
    return "\n".join(lines)


def _render_comparison(label: str, a: DatasetMetrics, other: DatasetMetrics) -> str:
    continuous_overall = compare_datasets_repo_level(a, other)
    lines = [f"## {label}: {DATASET_LABELS['a']} vs {DATASET_LABELS[other.dataset]}", ""]

    continuous_intro = (
        "(Mann-Whitney U on repo-level values, two-sided) -- one mean value "
        "per repo (per language, for the per-language rows), not per "
        "fixture, so fixtures clustering within a repo can't inflate the "
        "result. Effect size is Cliff's delta (thresholds: negligible "
        "<0.147, small <0.33, medium <0.474, else large; positive means the "
        "comparison dataset tends to have larger values than A, negative "
        "means A tends to have larger values). The Overall row is a single "
        "pooled test, not BH-corrected; each metric's per-language rows are "
        "BH-FDR corrected against each other only (one family per metric, "
        "4 languages)."
    )

    lines += [
        f"**Paper Metrics -- Continuous** {continuous_intro} These three "
        "(`loc`, `cyclomatic_complexity`, `comment_density`) are the only "
        "continuous metrics reported in the paper -- see this module's "
        "docstring. Each per-language row also reports `A median`/`C "
        "median`, `A Q3`/`C Q3` (75th percentile), and `A P90`/`C P90` "
        "(90th percentile) -- the median/Q3/P90 of the same per-repo mean "
        "values the Mann-Whitney test itself runs on, alongside (not a "
        "replacement for) the effect size and p-value. Q3/P90 exist to "
        "explain an effect that reaches significance despite identical "
        "medians -- a real difference concentrated in the upper tail, "
        "invisible to the median alone.",
        "",
    ]
    for metric in PAPER_CONTINUOUS_METRICS:
        lines.append(
            _render_continuous_metric(
                metric,
                a.repo_level_continuous[metric],
                other.repo_level_continuous[metric],
                a.repo_level_continuous_by_language[metric],
                other.repo_level_continuous_by_language[metric],
                continuous_overall[metric],
                other.dataset,
                include_percentile_columns=True,
            )
        )

    lines += [
        "**Other Extracted Features (Not in the Paper)** -- `num_parameters` "
        "is still collected but dropped from Mann-Whitney testing entirely "
        "(see this module's docstring for why); shown here only as a "
        "descriptive floor-percentage footnote, not a comparative test.",
        "",
        _render_floor_percentage_footnote(a, other),
    ]

    median_diagnostic_overall = compare_datasets_repo_level_median_diagnostic(a, other)
    lines += [
        "## Diagnostic: median-per-repo aggregation (NOT used in the paper)",
        "",
        "**This section is presented for transparency only -- these are "
        "not results, do not cite them.** The paper's own methodology "
        "(above) takes each repo's *mean* fixture value, then reports the "
        "median across repos. This section instead takes each repo's "
        "own *median* fixture value first. That interacts badly with "
        "`cyclomatic_complexity`/`comment_density`'s heavy floor-binding "
        "(CC=1, comment_density=0 for most fixtures -- see this module's "
        "docstring): most repos' own median collapses to that exact floor "
        "value, producing near-universal ties across repos and starving "
        "Mann-Whitney of power. The per-language pattern below can and "
        "does diverge substantially from the paper's actual table above "
        "-- that divergence is the point of keeping this section, as a "
        "record of how sensitive the comparison is to this choice, not a "
        "competing result.",
        "",
    ]
    for metric in PAPER_CONTINUOUS_METRICS:
        lines.append(
            _render_continuous_metric(
                metric,
                a.repo_level_continuous_median_diagnostic[metric],
                other.repo_level_continuous_median_diagnostic[metric],
                a.repo_level_continuous_by_language_median_diagnostic[metric],
                other.repo_level_continuous_by_language_median_diagnostic[metric],
                median_diagnostic_overall[metric],
                other.dataset,
                include_percentile_columns=True,
            )
        )

    return "\n".join(lines)




def generate_report(*, db_root: Path = paths.DB_ROOT) -> str:
    loaded = {ds: load_dataset_metrics(ds, db_root=db_root) for ds in ("a", "c")}
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    lines = [
        "# RQ2 -- General Metrics Overview",
        "",
        "> How do agent-generated and human-written fixtures compare across "
        "structural metrics?",
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
