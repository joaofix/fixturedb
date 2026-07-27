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

A dataset is skipped (not an error) if its db/{dataset}.db does not exist
yet -- lets this run against whatever subset of A/B/C has been collected so
far.

python -m collection.research_questions.rq1
"""

from __future__ import annotations

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
    fetch_categorical_column,
    fetch_continuous_column,
    fmt,
    require_db_or_none,
    summarize_continuous,
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

    return DatasetMetrics(
        dataset=dataset,
        n_fixtures=n_fixtures,
        continuous_raw=continuous_raw,
        categorical=categorical,
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


def _render_dataset_summary(metrics: DatasetMetrics) -> str:
    lines = [f"### {DATASET_LABELS[metrics.dataset]} -- {metrics.n_fixtures:,} fixtures", ""]

    lines += ["**Continuous metrics**", "", "| Metric | n | mean | median | min | max | stdev |",
              "|---|---|---|---|---|---|---|"]
    for metric in CONTINUOUS_METRICS:
        s = summarize_continuous(metrics.continuous_raw[metric])
        lines.append(
            f"| {metric} | {s['n']:,} | {fmt(s['mean'])} | {fmt(s['median'])} | "
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

    return "\n".join(lines)


def _render_comparison(label: str, a: DatasetMetrics, other: DatasetMetrics) -> str:
    result = compare_datasets(a, other)
    lines = [f"## {label}: {DATASET_LABELS['a']} vs {DATASET_LABELS[other.dataset]}", ""]

    lines += [
        "**Continuous metrics (Mann-Whitney U, two-sided)**",
        "",
        "| Metric | A mean | A median | "
        + f"{other.dataset.upper()} mean | {other.dataset.upper()} median | U | p-value | significant (p<0.05) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for metric in CONTINUOUS_METRICS:
        t = result["continuous"][metric]
        d = t.details
        if d.get("reason") == "insufficient_data":
            lines.append(f"| {metric} | -- | -- | -- | -- | -- | -- | _insufficient data_ |")
            continue
        sig = "yes" if t.p_value < 0.05 else "no"
        lines.append(
            f"| {metric} | {fmt(d.get('agent_mean'))} | {fmt(d.get('agent_median'))} | "
            f"{fmt(d.get('human_mean'))} | {fmt(d.get('human_median'))} | "
            f"{fmt(t.statistic, 1)} | {t.p_value:.4g} | {sig} |"
        )
    lines.append("")

    lines += [
        "**Categorical metrics (chi-square)**",
        "",
        "| Metric | chi2 | dof | p-value | significant (p<0.05) |",
        "|---|---|---|---|---|",
    ]
    for metric in CATEGORICAL_METRICS:
        t = result["categorical"][metric]
        d = t.details
        if d.get("reason") == "insufficient_data":
            lines.append(f"| {metric} | -- | -- | -- | _insufficient data_ |")
            continue
        sig = "yes" if t.p_value < 0.05 else "no"
        dof = d.get("degrees_of_freedom", "--")
        lines.append(f"| {metric} | {fmt(t.statistic, 1)} | {dof} | {t.p_value:.4g} | {sig} |")
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

    return "\n".join(lines)


def write_report(
    output_dir: Path = OUTPUT_DIR, *, db_root: Path = paths.DB_ROOT
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    report = generate_report(db_root=db_root)
    output_path = output_dir / "rq1.md"
    output_path.write_text(report)
    logger.info(f"RQ1 report written to {output_path}")
    return output_path


def main() -> None:
    path = write_report()
    print(f"RQ1 report written to {path}")


if __name__ == "__main__":
    main()
