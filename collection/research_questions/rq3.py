"""
RQ3 -- Mocking (Quantitative): how do agent-generated and human-written
fixtures differ in mock usage -- prevalence, framework selection, category,
and interaction depth?

Five metrics, computed per dataset (A/B/C):

1. **Mock prevalence per fixture** -- `fixtures.num_mocks` (continuous,
   Mann-Whitney), plus a derived has_mock/no_mock split (chi-square) so the
   headline "do agents mock more or less" question has both a magnitude
   answer and a plain yes/no-prevalence one.
2. **Mock prevalence per language** -- same has_mock split, broken down by
   `test_files.language` (joined via `fixtures.file_id`). Descriptive only,
   not run through a significance test -- matches rq2.py's
   teardown_rate_by_type, which is also per-subgroup and descriptive rather
   than tested, to avoid a combinatorial explosion of small-n tests.
3. **Framework distribution** -- `mock_usages.framework` (chi-square
   overall), plus per-language (descriptive), so a reader can see whether
   agents default to the dominant framework per language or show more
   diversity just by reading the table, without a dedicated per-language
   test.
4. **Test-double category distribution** -- `mock_usages.category`
   (dummy/stub/spy/mock/fake, chi-square). Not in the original RQ3 text but
   already deterministically computed by the same detection pass that
   produces `framework` (see detector_shared.py's `_classify_mock_category`,
   substring match against feature_extraction_patterns.yaml's
   `mock_category_keywords`) and squarely inside "mock usage" -- costs
   nothing extra to fold in.
5. **Interaction depth** -- `mock_usages.num_interactions_configured`
   (continuous, Mann-Whitney): among mocks that ARE created, how much is
   configured on them (`.return_value`/`.side_effect`/`when(...).thenReturn`
   style calls)?

The old RQ3's qualitative target-layer coding (boundary/internal/
infrastructure, from `target_identifier`) is deliberately NOT reproduced
here -- dropped in favor of staying purely quantitative, per this RQ's own
note that the qualitative layer "can be dropped ... to keep this purely
quantitative."

A vs B and A vs C only (see rq1.py's rationale -- B vs C deferred until
those datasets exist).

A dataset is skipped (not an error) if its db/{dataset}.db does not exist
yet.

python -m collection.research_questions.rq3
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

CONTINUOUS_METRICS = ["num_mocks", "num_interactions_configured"]
CATEGORICAL_METRICS = ["has_mock", "framework", "category"]


@dataclass
class DatasetMetrics:
    dataset: str
    n_fixtures: int
    n_mock_usages: int
    num_mocks_raw: list[float] = field(default_factory=list)
    num_interactions_raw: list[float] = field(default_factory=list)
    has_mock_dist: dict[str, int] = field(default_factory=dict)
    framework_dist: dict[str, int] = field(default_factory=dict)
    category_dist: dict[str, int] = field(default_factory=dict)
    mock_rate_by_language: dict[str, dict] = field(default_factory=dict)
    framework_by_language: dict[str, dict[str, int]] = field(default_factory=dict)
    language_leakage: list[LanguageLeakage] = field(default_factory=list)
    has_mock_dist_by_language: dict[str, dict[str, int]] = field(default_factory=dict)
    repo_level_continuous: dict[str, list[float]] = field(default_factory=dict)


def _continuous_values(metrics: DatasetMetrics, metric: str) -> list[float]:
    return {
        "num_mocks": metrics.num_mocks_raw,
        "num_interactions_configured": metrics.num_interactions_raw,
    }[metric]


# Which table each continuous metric's repo_id column lives on -- num_mocks
# is a fixtures column, num_interactions_configured a mock_usages one
# (several mocks per fixture, several fixtures per repo); both tables carry
# their own repo_id, so fetch_continuous_column_by_repo() works for either.
_CONTINUOUS_METRIC_TABLES = {
    "num_mocks": "fixtures",
    "num_interactions_configured": "mock_usages",
}


def _categorical_values(metrics: DatasetMetrics, metric: str) -> dict[str, int]:
    return {
        "has_mock": metrics.has_mock_dist,
        "framework": metrics.framework_dist,
        "category": metrics.category_dist,
    }[metric]


def _fetch_mock_rate_by_language(conn: sqlite3.Connection) -> dict[str, dict]:
    rows = conn.execute(
        "SELECT tf.language, COUNT(*), SUM(CASE WHEN f.num_mocks > 0 THEN 1 ELSE 0 END) "
        "FROM fixtures f JOIN test_files tf ON f.file_id = tf.id "
        "GROUP BY tf.language"
    ).fetchall()
    return {
        language: {
            "total": total,
            "with_mocks": with_mocks,
            "rate": 100 * with_mocks / total if total else 0.0,
        }
        for language, total, with_mocks in rows
    }


def _fetch_framework_by_language(conn: sqlite3.Connection) -> dict[str, dict[str, int]]:
    rows = conn.execute(
        "SELECT tf.language, mu.framework, COUNT(*) FROM mock_usages mu "
        "JOIN fixtures f ON mu.fixture_id = f.id "
        "JOIN test_files tf ON f.file_id = tf.id "
        "WHERE mu.framework IS NOT NULL "
        "GROUP BY tf.language, mu.framework"
    ).fetchall()
    result: dict[str, dict[str, int]] = {}
    for language, framework, count in rows:
        result.setdefault(language, {})[framework] = count
    return result


def load_dataset_metrics(
    dataset: str, *, db_root: Path = paths.DB_ROOT
) -> DatasetMetrics | None:
    """Load RQ3 metrics for `dataset`, or None if its db doesn't exist yet."""
    db_file = require_db_or_none(dataset, db_root)
    if db_file is None:
        return None

    with db_session(db_file) as conn:
        n_fixtures = conn.execute("SELECT COUNT(*) FROM fixtures").fetchone()[0]
        n_mock_usages = conn.execute("SELECT COUNT(*) FROM mock_usages").fetchone()[0]
        num_mocks_raw = fetch_continuous_column(conn, "fixtures", "num_mocks")
        num_interactions_raw = fetch_continuous_column(
            conn, "mock_usages", "num_interactions_configured"
        )
        framework_dist = fetch_categorical_column(conn, "mock_usages", "framework")
        category_dist = fetch_categorical_column(conn, "mock_usages", "category")
        mock_rate_by_language = _fetch_mock_rate_by_language(conn)
        framework_by_language = _fetch_framework_by_language(conn)
        language_leakage = compute_language_leakage(conn)
        repo_level_continuous = {
            m: repo_level_means(fetch_continuous_column_by_repo(conn, table, m))
            for m, table in _CONTINUOUS_METRIC_TABLES.items()
        }

    has_mock_dist = {
        "has_mock": sum(1 for n in num_mocks_raw if n > 0),
        "no_mock": sum(1 for n in num_mocks_raw if n == 0),
    }
    # Derived from mock_rate_by_language (total/with_mocks per language),
    # no separate query needed -- this is what
    # compute_stratified_categorical_balance() needs to check whether an
    # A-vs-B/C mock-prevalence difference holds within a language, not just
    # in the aggregate across each dataset's different language mix.
    has_mock_dist_by_language = {
        language: {
            "has_mock": entry["with_mocks"],
            "no_mock": entry["total"] - entry["with_mocks"],
        }
        for language, entry in mock_rate_by_language.items()
    }

    return DatasetMetrics(
        dataset=dataset,
        n_fixtures=n_fixtures,
        n_mock_usages=n_mock_usages,
        num_mocks_raw=num_mocks_raw,
        num_interactions_raw=num_interactions_raw,
        has_mock_dist=has_mock_dist,
        has_mock_dist_by_language=has_mock_dist_by_language,
        framework_dist=framework_dist,
        category_dist=category_dist,
        mock_rate_by_language=mock_rate_by_language,
        framework_by_language=framework_by_language,
        language_leakage=language_leakage,
        repo_level_continuous=repo_level_continuous,
    )


def compare_datasets(
    a: DatasetMetrics, other: DatasetMetrics
) -> dict[str, dict[str, BalanceTest]]:
    """A vs `other`: Mann-Whitney U per continuous metric, chi-square per categorical one."""
    continuous = {
        metric: compute_continuous_balance(
            human_values=_continuous_values(other, metric),
            agent_values=_continuous_values(a, metric),
            variable=metric,
        )
        for metric in CONTINUOUS_METRICS
    }
    categorical = {
        metric: compute_categorical_balance(
            human_dist=_categorical_values(other, metric),
            agent_dist=_categorical_values(a, metric),
            variable=metric,
        )
        for metric in CATEGORICAL_METRICS
    }
    return {"continuous": continuous, "categorical": categorical}


def compare_datasets_repo_level(
    a: DatasetMetrics, other: DatasetMetrics
) -> dict[str, BalanceTest]:
    """A vs `other`, one mean value per repo instead of one value per
    fixture/mock -- see repo_level_means()'s docstring for why this
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
    lines = [
        f"### {DATASET_LABELS[metrics.dataset]} -- {metrics.n_fixtures:,} fixtures, "
        f"{metrics.n_mock_usages:,} mock usages",
        "",
    ]

    total_mock = sum(metrics.has_mock_dist.values())
    mock_pct = 100 * metrics.has_mock_dist.get("has_mock", 0) / total_mock if total_mock else 0.0
    lines.append(f"Mock prevalence: {metrics.has_mock_dist.get('has_mock', 0):,}/{total_mock:,} fixtures ({mock_pct:.1f}%)")
    lines.append("")

    lines += ["**Continuous metrics**", "", "| Metric | n | mean | median | min | max | stdev |",
              "|---|---|---|---|---|---|---|"]
    for metric in CONTINUOUS_METRICS:
        s = summarize_continuous(_continuous_values(metrics, metric))
        lines.append(
            f"| {metric} | {s['n']:,} | {fmt(s['mean'])} | {fmt(s['median'])} | "
            f"{fmt(s['min'], 0)} | {fmt(s['max'], 0)} | {fmt(s['stdev'])} |"
        )
    lines.append("")

    for metric in CATEGORICAL_METRICS:
        dist = _categorical_values(metrics, metric)
        total = sum(dist.values())
        lines += [f"**{metric} distribution**", "", "| Value | Count | % |", "|---|---|---|"]
        if total == 0:
            lines.append("| _(no data)_ | -- | -- |")
        else:
            for value, count in sorted(dist.items(), key=lambda kv: -kv[1]):
                lines.append(f"| {value} | {count:,} | {100 * count / total:.1f}% |")
        lines.append("")

    lines += ["**Mock prevalence by language**", "", "| Language | Fixtures | With >=1 mock | Rate |",
              "|---|---|---|---|"]
    for language, entry in sorted(metrics.mock_rate_by_language.items()):
        lines.append(
            f"| {language} | {entry['total']:,} | {entry['with_mocks']:,} | {entry['rate']:.1f}% |"
        )
    lines.append("")

    lines += ["**Framework distribution by language**", "", "| Language | Framework | Count |",
              "|---|---|---|"]
    for language in sorted(metrics.framework_by_language):
        for framework, count in sorted(
            metrics.framework_by_language[language].items(), key=lambda kv: -kv[1]
        ):
            lines.append(f"| {language} | {framework} | {count:,} |")
    lines.append("")

    lines.append(render_language_leakage_table(metrics.language_leakage))

    return "\n".join(lines)


def _render_comparison(label: str, a: DatasetMetrics, other: DatasetMetrics) -> str:
    result = compare_datasets(a, other)
    # BH-FDR correction, one family per table -- see
    # apply_fdr_correction()'s docstring.
    continuous_corrected = apply_fdr_correction(result["continuous"])
    categorical_corrected = apply_fdr_correction(result["categorical"])
    lines = [f"## {label}: {DATASET_LABELS['a']} vs {DATASET_LABELS[other.dataset]}", ""]

    lines += [
        "**Continuous metrics (Mann-Whitney U, two-sided)** -- p-values shrink with "
        "sample size alone; Cliff's delta is what says how big the difference "
        "actually is (thresholds: negligible <0.147, small <0.33, medium <0.474, "
        "else large; positive means A tends to have larger values). BH-FDR corrects "
        "for running both of these tests together.",
        "",
        "| Metric | A mean | A median | "
        + f"{other.dataset.upper()} mean | {other.dataset.upper()} median | U | p-value | "
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
            f"| {metric} | {fmt(d.get('agent_mean'))} | {fmt(d.get('agent_median'))} | "
            f"{fmt(d.get('human_mean'))} | {fmt(d.get('human_median'))} | "
            f"{fmt(t.statistic, 1)} | {t.p_value:.4g} | {sig} | {continuous_effect_size_cell(t)} | "
            f"{fdr_cell(t)} |"
        )
    lines.append("")

    lines += [
        "**Categorical metrics (chi-square)** -- Cramer's V thresholds: "
        "negligible <0.1, small <0.3, medium <0.5, else large. BH-FDR corrects for "
        "running all 3 of these tests together.",
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
        "**has_mock, stratified by language (chi-square per language)** -- "
        "the aggregate comparison above can look significant purely because "
        f"{DATASET_LABELS['a']} and {DATASET_LABELS[other.dataset]} have different "
        "language mixes; this checks whether the difference holds within each "
        "shared language.",
        "",
    ]
    stratified = compute_stratified_categorical_balance(
        a.has_mock_dist_by_language, other.has_mock_dist_by_language, "has_mock"
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
        "| Metric | A mean | A median | "
        + f"{other.dataset.upper()} mean | {other.dataset.upper()} median | U | p-value | "
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
            f"| {metric} | {fmt(d.get('agent_mean'))} | {fmt(d.get('agent_median'))} | "
            f"{fmt(d.get('human_mean'))} | {fmt(d.get('human_median'))} | "
            f"{fmt(t.statistic, 1)} | {t.p_value:.4g} | {sig} | {continuous_effect_size_cell(t)} | "
            f"{fdr_cell(t)} |"
        )
    lines.append("")
    return "\n".join(lines)


def generate_report(*, db_root: Path = paths.DB_ROOT) -> str:
    loaded = {ds: load_dataset_metrics(ds, db_root=db_root) for ds in ("a", "b", "c")}
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    lines = [
        "# RQ3 -- Mocking",
        "",
        "> How do agent-generated and human-written fixtures differ in mock "
        "usage -- prevalence, framework selection, and interaction depth?",
        "",
        f"Generated: {generated_at}",
        "",
        "See [docs/research-questions.md](../docs/research-questions.md) for "
        "the full RQ3 definition.",
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
        "The comparisons above treat every fixture/mock as an independent "
        "observation, but they cluster within repos (shared authorship "
        "conventions, framework choices, project style) -- a handful of "
        "unusually prolific repos can dominate a fixture-level result. This "
        "section re-runs the continuous metrics with one *mean-per-repo* "
        "value per repo instead, so each repo counts once regardless of how "
        "many fixtures/mocks it contributed.",
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
    output_path = write_markdown_report(output_dir, "rq3.md", report)
    logger.info(f"RQ3 report written to {output_path}")
    return output_path


def main() -> None:
    path = write_report()
    print(f"RQ3 report written to {path}")


if __name__ == "__main__":
    main()
