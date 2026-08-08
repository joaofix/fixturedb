"""
RQ1 -- General Metrics Overview (Quantitative): how do agent-generated and
human-written fixtures compare across structural metrics?

Computes, per dataset (A/B/C), summary statistics for the RQ1 metrics (LOC,
cyclomatic complexity, nesting depth, parameters, objects instantiated,
external calls, scope, fixture_type, commit_type), plus A vs B and A vs C
comparisons (Mann-Whitney U for continuous metrics, chi-square for
categorical ones -- reusing collection/between_group_comparison.py's test
functions, which are generic enough to apply here unchanged). B vs C is
intentionally not computed (see docs/research-questions.md's RQ1 section --
B vs C is the secondary A/B-anchored finding, not this script's job).

fixture_type is additionally stratified by language (each fixture's own
test_files.language, not its repo's tag) and re-tested per language. The
pooled fixture_type comparison can look significant purely because A and
B/C have different language mixes -- e.g. pytest_decorator only exists in
Python fixtures, before_each/after_each is the characteristic JS/TS/Mocha
idiom, so a dataset that happens to be more TS-heavy will look more
"hook-based" regardless of any real agent-vs-human mechanism preference.
The stratified table checks whether the difference survives within a
single shared language; see compute_stratified_categorical_balance()'s
docstring in _shared.py for the general rationale (first applied for
RQ2's fixture_type_kind and RQ3's mock prevalence).

A dataset is skipped (not an error) if its db/{dataset}.db does not exist
yet -- lets this run against whatever subset of A/B/C has been collected so
far.

python -m collection.research_questions.rq1
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .. import paths
from ..between_group_comparison import (
    BalanceTest,
    compute_categorical_balance,
    compute_continuous_balance,
)
from ..db import db_session
from ..logging_utils import get_logger
from ._shared import (
    COMPARISONS,
    DATASET_LABELS,
    OUTPUT_DIR,
    LanguageLeakage,
    apply_fdr_correction,
    categorical_effect_size_cell,
    compute_language_leakage,
    compute_stratified_categorical_balance,
    continuous_effect_size_cell,
    fdr_cell,
    fetch_categorical_column,
    fetch_continuous_column,
    fetch_continuous_column_by_repo,
    fmt,
    render_language_leakage_table,
    render_stratified_categorical_table,
    repo_level_means,
    require_db_or_none,
    summarize_continuous,
    write_markdown_report,
)

logger = get_logger(__name__)

CONTINUOUS_METRICS = [
    "loc",
    "cyclomatic_complexity",
    "max_nesting_depth",
    "num_parameters",
    "num_objects_instantiated",
    "num_external_calls",
]
CATEGORICAL_METRICS = ["scope", "fixture_type", "commit_type"]


@dataclass
class DatasetMetrics:
    dataset: str
    n_fixtures: int
    continuous_raw: dict[str, list[float]] = field(default_factory=dict)
    categorical: dict[str, dict[str, int]] = field(default_factory=dict)
    language_leakage: list[LanguageLeakage] = field(default_factory=list)
    agent_type_distribution: dict[str, int] = field(default_factory=dict)
    repo_level_continuous: dict[str, list[float]] = field(default_factory=dict)
    fixture_type_by_language: dict[str, dict[str, int]] = field(default_factory=dict)


def _fetch_fixture_type_by_language(conn: sqlite3.Connection) -> dict[str, dict[str, int]]:
    """fixture_type distribution per fixture's own language (test_files.language,
    not repositories.language -- see compute_language_leakage()'s docstring for
    why those two can differ). compute_stratified_categorical_balance() needs
    this to check whether the pooled fixture_type difference (see this
    module's docstring) holds within a language, not just because the two
    datasets have different language mixes."""
    rows = conn.execute(
        "SELECT tf.language, f.fixture_type, COUNT(*) FROM fixtures f "
        "JOIN test_files tf ON f.file_id = tf.id "
        "WHERE f.fixture_type IS NOT NULL "
        "GROUP BY tf.language, f.fixture_type"
    ).fetchall()
    by_language: dict[str, dict[str, int]] = {}
    for language, fixture_type, count in rows:
        by_language.setdefault(language, {})[fixture_type] = count
    return by_language


def load_dataset_metrics(
    dataset: str, *, db_root: Path = paths.DB_ROOT
) -> DatasetMetrics | None:
    """Load RQ1 metrics for `dataset`, or None if its db doesn't exist yet."""
    db_file = require_db_or_none(dataset, db_root)
    if db_file is None:
        return None

    with db_session(db_file) as conn:
        n_fixtures = conn.execute("SELECT COUNT(*) FROM fixtures").fetchone()[0]
        continuous_raw = {m: fetch_continuous_column(conn, "fixtures", m) for m in CONTINUOUS_METRICS}
        categorical = {m: fetch_categorical_column(conn, "fixtures", m) for m in CATEGORICAL_METRICS}
        fixture_type_by_language = _fetch_fixture_type_by_language(conn)
        language_leakage = compute_language_leakage(conn)
        # Descriptive only, not run through compare_datasets()'s significance
        # tests: agent_type is the group-defining variable for Dataset A
        # (which agent authored this fixture), not a content metric to test
        # A-vs-B/C on -- comparing it against B/C's constant "human"/
        # "human_pre2022" value would be tautological (echoing commit_kind),
        # not a real finding. Still shown for B/C too since it doubles as a
        # sanity check that those corpora really are cleanly non-agent.
        agent_type_distribution = fetch_categorical_column(conn, "fixtures", "agent_type")
        # One mean-per-repo value per continuous metric -- see
        # repo_level_means()'s docstring for why this exists alongside
        # continuous_raw above (pseudo-replication: fixtures cluster within
        # repos, so testing raw fixture values as independent observations
        # inflates apparent significance).
        repo_level_continuous = {
            m: repo_level_means(fetch_continuous_column_by_repo(conn, "fixtures", m))
            for m in CONTINUOUS_METRICS
        }

    return DatasetMetrics(
        dataset=dataset,
        n_fixtures=n_fixtures,
        continuous_raw=continuous_raw,
        categorical=categorical,
        language_leakage=language_leakage,
        agent_type_distribution=agent_type_distribution,
        repo_level_continuous=repo_level_continuous,
        fixture_type_by_language=fixture_type_by_language,
    )


def compare_datasets(
    a: DatasetMetrics, other: DatasetMetrics
) -> dict[str, dict[str, BalanceTest]]:
    """A vs `other`: Mann-Whitney U per continuous metric, chi-square per categorical one."""
    continuous = {
        metric: compute_continuous_balance(
            human_values=other.continuous_raw[metric],
            agent_values=a.continuous_raw[metric],
            variable=metric,
        )
        for metric in CONTINUOUS_METRICS
    }
    categorical = {
        metric: compute_categorical_balance(
            human_dist=other.categorical[metric],
            agent_dist=a.categorical[metric],
            variable=metric,
        )
        for metric in CATEGORICAL_METRICS
    }
    return {"continuous": continuous, "categorical": categorical}


def compare_datasets_repo_level(
    a: DatasetMetrics, other: DatasetMetrics
) -> dict[str, BalanceTest]:
    """A vs `other`, one mean value per repo instead of one value per
    fixture -- see repo_level_means()'s docstring for why this
    complements, rather than replaces, compare_datasets() above."""
    return {
        metric: compute_continuous_balance(
            human_values=other.repo_level_continuous[metric],
            agent_values=a.repo_level_continuous[metric],
            variable=metric,
        )
        for metric in CONTINUOUS_METRICS
    }


def _render_dataset_summary(metrics: DatasetMetrics) -> str:
    lines = [f"### {DATASET_LABELS[metrics.dataset]} -- {metrics.n_fixtures:,} fixtures", ""]

    lines += ["**Continuous metrics**", "", "| Metric | n | median | mean | min | max | stdev |",
              "|---|---|---|---|---|---|---|"]
    for metric in CONTINUOUS_METRICS:
        s = summarize_continuous(metrics.continuous_raw[metric])
        lines.append(
            f"| {metric} | {s['n']:,} | {fmt(s['median'])} | {fmt(s['mean'])} | "
            f"{fmt(s['min'], 0)} | {fmt(s['max'], 0)} | {fmt(s['stdev'])} |"
        )
    lines.append("")

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


def _render_comparison(label: str, a: DatasetMetrics, other: DatasetMetrics) -> str:
    result = compare_datasets(a, other)
    # BH-FDR correction, one family per table (continuous metrics together,
    # categorical metrics together) -- see apply_fdr_correction()'s
    # docstring for why RQ1's 9 tests per comparison need this.
    continuous_corrected = apply_fdr_correction(result["continuous"])
    categorical_corrected = apply_fdr_correction(result["categorical"])
    lines = [f"## {label}: {DATASET_LABELS['a']} vs {DATASET_LABELS[other.dataset]}", ""]

    lines += [
        "**Continuous metrics (Mann-Whitney U, two-sided)** -- p-values shrink with "
        "sample size alone; Cliff's delta is what says how big the difference "
        "actually is (thresholds: negligible <0.147, small <0.33, medium <0.474, "
        "else large; positive means the comparison dataset tends to have larger "
        "values than A, negative means A tends to have larger values). BH-FDR corrects "
        "for running all 6 of these tests together (see apply_fdr_correction()'s "
        "docstring).",
        "",
        "| Metric | A median | A mean | "
        + f"{other.dataset.upper()} median | {other.dataset.upper()} mean | U | p-value | "
        "significant (p<0.05) | Cliff's delta (effect size) | BH-FDR adjusted p (sig?) |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for metric in CONTINUOUS_METRICS:
        t = continuous_corrected[metric]
        d = t.details
        if d.get("reason") == "insufficient_data":
            lines.append(
                f"| {metric} | -- | -- | -- | -- | -- | -- | _insufficient data_ | -- | -- |"
            )
            continue
        sig = "yes" if t.p_value < 0.05 else "no"
        lines.append(
            f"| {metric} | {fmt(d.get('agent_median'))} | {fmt(d.get('agent_mean'))} | "
            f"{fmt(d.get('human_median'))} | {fmt(d.get('human_mean'))} | "
            f"{fmt(t.statistic, 1)} | {t.p_value:.4g} | {sig} | {continuous_effect_size_cell(t)} | "
            f"{fdr_cell(t)} |"
        )
    lines.append("")

    lines += [
        "**Categorical metrics (chi-square)** -- Cramer's V thresholds: "
        "negligible <0.1, small <0.3, medium <0.5, else large. BH-FDR corrects "
        "for running all 3 of these tests together.",
        "",
        "| Metric | chi2 | dof | p-value | significant (p<0.05) | Cramer's V (effect size) | "
        "BH-FDR adjusted p (sig?) |",
        "|---|---|---|---|---|---|---|",
    ]
    for metric in CATEGORICAL_METRICS:
        t = categorical_corrected[metric]
        d = t.details
        if d.get("reason") == "insufficient_data":
            lines.append(f"| {metric} | -- | -- | -- | _insufficient data_ | -- | -- |")
            continue
        sig = "yes" if t.p_value < 0.05 else "no"
        dof = d.get("degrees_of_freedom", "--")
        lines.append(
            f"| {metric} | {fmt(t.statistic, 1)} | {dof} | {t.p_value:.4g} | {sig} | "
            f"{categorical_effect_size_cell(t)} | {fdr_cell(t)} |"
        )
    lines.append("")

    lines += [
        "**fixture_type, stratified by language (chi-square per language)** -- "
        "the pooled fixture_type comparison above can look significant purely "
        f"because {DATASET_LABELS['a']} and {DATASET_LABELS[other.dataset]} have "
        "different language mixes (see this module's docstring); this checks "
        "whether the mechanism difference holds within each shared language.",
        "",
    ]
    stratified = compute_stratified_categorical_balance(
        a.fixture_type_by_language,
        other.fixture_type_by_language,
        "fixture_type",
    )
    lines.append(render_stratified_categorical_table(stratified))

    return "\n".join(lines)


def _render_repo_level_comparison(
    label: str, a: DatasetMetrics, other: DatasetMetrics
) -> str:
    result = compare_datasets_repo_level(a, other)
    corrected = apply_fdr_correction(result)
    lines = [
        f"### {label}: {DATASET_LABELS['a']} vs {DATASET_LABELS[other.dataset]}",
        "",
        "| Metric | A median | A mean | "
        + f"{other.dataset.upper()} median | {other.dataset.upper()} mean | U | p-value | "
        "significant (p<0.05) | Cliff's delta (effect size) | BH-FDR adjusted p (sig?) |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for metric in CONTINUOUS_METRICS:
        t = corrected[metric]
        d = t.details
        if d.get("reason") == "insufficient_data":
            lines.append(
                f"| {metric} | -- | -- | -- | -- | -- | -- | _insufficient data_ | -- | -- |"
            )
            continue
        sig = "yes" if t.p_value < 0.05 else "no"
        lines.append(
            f"| {metric} | {fmt(d.get('agent_median'))} | {fmt(d.get('agent_mean'))} | "
            f"{fmt(d.get('human_median'))} | {fmt(d.get('human_mean'))} | "
            f"{fmt(t.statistic, 1)} | {t.p_value:.4g} | {sig} | {continuous_effect_size_cell(t)} | "
            f"{fdr_cell(t)} |"
        )
    lines.append("")
    return "\n".join(lines)


def generate_report(*, db_root: Path = paths.DB_ROOT) -> str:
    loaded = {ds: load_dataset_metrics(ds, db_root=db_root) for ds in ("a", "b", "c")}
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    lines = [
        "# RQ1 -- General Metrics Overview",
        "",
        "> How do agent-generated and human-written fixtures compare across "
        "structural metrics?",
        "",
        f"Generated: {generated_at}",
        "",
        "See [docs/research-questions.md](../docs/research-questions.md) for "
        "the full RQ1 definition.",
        "",
        "## Per-dataset summary",
        "",
    ]

    for ds in ("a", "b", "c"):
        metrics = loaded[ds]
        if metrics is None:
            lines += [f"### {DATASET_LABELS[ds]}", "", "_Not available -- db not collected yet._", ""]
        else:
            lines.append(_render_dataset_summary(metrics))

    a_metrics = loaded["a"]
    if a_metrics is None:
        lines.append("_Dataset A not available -- no A vs B / A vs C comparisons computed._")
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
        "## Repo-level aggregates",
        "",
        "The comparisons above treat every fixture as an independent "
        "observation, but fixtures cluster within repos (shared authorship "
        "conventions, framework choices, project style) -- a handful of "
        "unusually prolific repos can dominate a fixture-level result. This "
        "section re-runs the continuous metrics with one *mean-per-repo* "
        "value per repo instead, so each repo counts once regardless of how "
        "many fixtures it contributed. A finding that holds in both views is "
        "on firmer ground than one that only shows up fixture-level.",
        "",
    ]
    if a_metrics is None:
        lines.append("_Dataset A not available -- no repo-level comparisons computed._")
    else:
        for other_ds, label in COMPARISONS:
            other_metrics = loaded[other_ds]
            if other_metrics is None:
                lines += [
                    f"### {label}: {DATASET_LABELS['a']} vs {DATASET_LABELS[other_ds]}",
                    "",
                    "_Not available -- db not collected yet._",
                    "",
                ]
            else:
                lines.append(_render_repo_level_comparison(label, a_metrics, other_metrics))

    return "\n".join(lines)


def write_report(
    output_dir: Path = OUTPUT_DIR, *, db_root: Path = paths.DB_ROOT
) -> Path:
    report = generate_report(db_root=db_root)
    output_path = write_markdown_report(output_dir, "rq1.md", report)
    logger.info(f"RQ1 report written to {output_path}")
    return output_path


def main() -> None:
    path = write_report()
    print(f"RQ1 report written to {path}")


if __name__ == "__main__":
    main()
