"""
RQ1 -- General Metrics Overview (Quantitative): how do agent-generated and
human-written fixtures compare across structural metrics?

Computes, per dataset (A/C), summary statistics for the RQ1 metrics (LOC,
cyclomatic complexity, nesting depth, scope, fixture_type, commit_type),
plus an A vs C comparison. Dataset B (contemporary within-repo human
baseline) is still collected (db/b.db, paired_collection.py) but out of
scope for this script's reported comparisons.

`num_parameters` is dropped from the comparative (Mann-Whitney) analysis:
0 params is the overwhelming majority in both datasets (most fixtures take
no arguments), which makes a distributional test not very informative.
Still shown per-dataset descriptively (`_render_dataset_summary()`'s
existing "Continuous metrics" table, unaffected) plus a dedicated
floor-percentage footnote (`% of fixtures at 0 params`, no test) in the
comparison section, so the floor-binding is documented transparently
rather than silently dropped. `cyclomatic_complexity` also floors heavily
(CC=1 is the large majority) but is tested anyway, same as `loc`/
`max_nesting_depth` -- unlike `num_parameters`, it's kept in the primary
comparative analysis.

Every remaining continuous/categorical comparison renders through
_shared.py's render_comparison_table(): one "Overall" row (uncorrected,
single pooled test) plus, for metrics with a defined per-language family,
one BH-corrected row per language, corrected independently of every other
metric and of their own Overall row (see render_comparison_table()'s
docstring). `loc`/`cyclomatic_complexity`/`max_nesting_depth`/`scope`/
`fixture_type` each have a 4-language family; `commit_type` doesn't, and
renders Overall-only.

Continuous metrics are repo-level throughout (one value per repo, per
language for the per-language rows) -- not the raw per-fixture values --
so this doesn't reintroduce the fixture-clustering pseudo-replication the
categorical repo-level proportion fix (see below) exists to correct.
fixture_type's Overall/per-language rows stay fixture-level chi-square
(pseudo-replicated, like every per-language categorical test here --
that's a known, documented limitation, not fixed by this table) --
`fixture_type` is also re-tested in "Repo-level aggregates" with per-repo
category proportions (Mann-Whitney U + Cliff's delta), which IS the
repo-declustered version and the one reported in the paper; see
compare_categorical_repo_level()'s docstring in _shared.py.

A dataset is skipped (not an error) if its db/{dataset}.db does not exist
yet -- lets this run against whatever subset of A/C has been collected so
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
    NCounts,
    compare_categorical_repo_level,
    compute_language_leakage,
    compute_stratified_categorical_balance,
    compute_stratified_continuous_balance,
    fetch_categorical_column,
    fetch_categorical_column_by_repo,
    fetch_continuous_column,
    fetch_continuous_column_by_repo,
    fmt,
    pct,
    render_categorical_repo_level_table,
    render_comparison_table,
    render_language_leakage_table,
    repo_level_category_n_counts,
    repo_level_means,
    require_db_or_none,
    summarize_continuous,
    write_markdown_report,
)

logger = get_logger(__name__)

# Mann-Whitney-tested continuous metrics -- see this module's docstring for
# why num_parameters is dropped from this list (still fetched fixture-level
# for the descriptive table + floor-percentage footnote, just not tested).
CONTINUOUS_METRICS = ["loc", "cyclomatic_complexity", "max_nesting_depth"]
# metric -> the value that "floored" means "structurally minimal" for it
# (0 params: no arguments) -- drives the descriptive floor-percentage
# footnote only, no comparative test.
FLOOR_CHECK_METRICS = {"num_parameters": 0}
# Fixture-level fetch + the per-dataset descriptive "Continuous metrics"
# table in _render_dataset_summary() still show all 4 -- that table was
# never a comparison, so dropping num_parameters from CONTINUOUS_METRICS
# (the Mann-Whitney-tested list) doesn't affect it.
DESCRIPTIVE_CONTINUOUS_METRICS = CONTINUOUS_METRICS + list(FLOOR_CHECK_METRICS)
# num_objects_instantiated/num_external_calls are still detected and
# persisted (fixtures.num_objects_instantiated/num_external_calls) --
# excluded here only because they're not part of the paper's reported RQ1
# metrics, not because collection stopped computing them.
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
    repo_level_continuous_by_language: dict[str, dict[str, list[float]]] = field(
        default_factory=dict
    )
    fixture_type_by_language: dict[str, dict[str, int]] = field(default_factory=dict)
    fixture_type_by_repo: dict[int, dict[str, int]] = field(default_factory=dict)
    fixture_type_n_by_language: dict[str, int] = field(default_factory=dict)
    scope_by_language: dict[str, dict[str, int]] = field(default_factory=dict)
    scope_n_by_language: dict[str, int] = field(default_factory=dict)
    scope_n: int = 0
    commit_type_n: int = 0
    # metric -> % of fixtures at FLOOR_CHECK_METRICS' floor value (descriptive
    # only -- see this module's docstring).
    floor_pct: dict[str, float] = field(default_factory=dict)


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


def _fetch_scope_by_language(conn: sqlite3.Connection) -> dict[str, dict[str, int]]:
    """scope distribution per fixture's own language -- fixture_type
    analogue, same rationale (see _fetch_fixture_type_by_language()'s
    docstring), applied to `scope`."""
    rows = conn.execute(
        "SELECT tf.language, f.scope, COUNT(*) FROM fixtures f "
        "JOIN test_files tf ON f.file_id = tf.id "
        "WHERE f.scope IS NOT NULL "
        "GROUP BY tf.language, f.scope"
    ).fetchall()
    by_language: dict[str, dict[str, int]] = {}
    for language, scope, count in rows:
        by_language.setdefault(language, {})[scope] = count
    return by_language


def _fetch_repo_count_by_language(conn: sqlite3.Connection, column: str) -> dict[str, int]:
    """Distinct repo_id count per fixture's own language, for fixtures with
    a non-null `column` -- the per-language n_A/n_C render_comparison_table()
    needs: how many repos actually contributed to *this* variable's test in
    that language, independent of how many fixtures they contributed."""
    rows = conn.execute(
        f"SELECT tf.language, COUNT(DISTINCT f.repo_id) FROM fixtures f "
        f"JOIN test_files tf ON f.file_id = tf.id "
        f"WHERE f.{column} IS NOT NULL GROUP BY tf.language"
    ).fetchall()
    return dict(rows)


def _fetch_repo_count(conn: sqlite3.Connection, column: str) -> int:
    """Distinct repo_id count for fixtures with a non-null `column`,
    dataset-wide -- the Overall row's n_A/n_C for a metric with no other
    repo-count source already loaded (scope, commit_type)."""
    return conn.execute(
        f"SELECT COUNT(DISTINCT repo_id) FROM fixtures WHERE {column} IS NOT NULL"
    ).fetchone()[0]


def _fetch_continuous_by_repo_and_language(
    conn: sqlite3.Connection,
) -> dict[str, dict[str, dict[int, list[float]]]]:
    """{metric: {language: {repo_id: [values]}}} for every CONTINUOUS_METRICS
    column, one query pass over fixtures joined to test_files -- feeds
    repo_level_means() per (metric, language) for the per-language
    continuous family tests, the same repo-declustering repo_level_continuous
    already applies pooled (see compute_stratified_continuous_balance()'s
    docstring in _shared.py for why per-language stays repo-level too)."""
    columns_sql = ", ".join(f"f.{m}" for m in CONTINUOUS_METRICS)
    rows = conn.execute(
        f"SELECT f.repo_id, tf.language, {columns_sql} FROM fixtures f "
        "JOIN test_files tf ON f.file_id = tf.id"
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
    """Load RQ1 metrics for `dataset`, or None if its db doesn't exist yet."""
    db_file = require_db_or_none(dataset, db_root)
    if db_file is None:
        return None

    with db_session(db_file) as conn:
        n_fixtures = conn.execute("SELECT COUNT(*) FROM fixtures").fetchone()[0]
        # DESCRIPTIVE_CONTINUOUS_METRICS (4), not CONTINUOUS_METRICS (3) --
        # num_parameters is still fetched fixture-level for the per-dataset
        # descriptive table and the floor-percentage footnote, just no
        # longer Mann-Whitney tested (see module docstring).
        continuous_raw = {
            m: fetch_continuous_column(conn, "fixtures", m) for m in DESCRIPTIVE_CONTINUOUS_METRICS
        }
        categorical = {m: fetch_categorical_column(conn, "fixtures", m) for m in CATEGORICAL_METRICS}
        fixture_type_by_language = _fetch_fixture_type_by_language(conn)
        fixture_type_by_repo = fetch_categorical_column_by_repo(conn, "fixtures", "fixture_type")
        fixture_type_n_by_language = _fetch_repo_count_by_language(conn, "fixture_type")
        scope_by_language = _fetch_scope_by_language(conn)
        scope_n_by_language = _fetch_repo_count_by_language(conn, "scope")
        scope_n = _fetch_repo_count(conn, "scope")
        commit_type_n = _fetch_repo_count(conn, "commit_type")
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
        # family tests.
        repo_level_continuous = {
            m: repo_level_means(fetch_continuous_column_by_repo(conn, "fixtures", m))
            for m in CONTINUOUS_METRICS
        }
        continuous_by_repo_and_language = _fetch_continuous_by_repo_and_language(conn)
        repo_level_continuous_by_language = {
            metric: {
                language: repo_level_means(by_repo) for language, by_repo in by_language.items()
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
        fixture_type_by_language=fixture_type_by_language,
        fixture_type_by_repo=fixture_type_by_repo,
        fixture_type_n_by_language=fixture_type_n_by_language,
        scope_by_language=scope_by_language,
        scope_n_by_language=scope_n_by_language,
        scope_n=scope_n,
        commit_type_n=commit_type_n,
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
    never fixture-level -- see this module's docstring."""
    return {
        metric: compute_continuous_balance(
            human_values=other.repo_level_continuous[metric],
            agent_values=a.repo_level_continuous[metric],
            variable=metric,
        )
        for metric in CONTINUOUS_METRICS
    }


def compare_datasets_categorical(
    a: DatasetMetrics, other: DatasetMetrics
) -> dict[str, BalanceTest]:
    """A vs `other`: pooled fixture-level chi-square per categorical metric
    (scope, fixture_type, commit_type) -- the Overall row for each metric's
    table."""
    return {
        metric: compute_categorical_balance(
            human_dist=other.categorical[metric],
            agent_dist=a.categorical[metric],
            variable=metric,
        )
        for metric in CATEGORICAL_METRICS
    }


def _render_dataset_summary(metrics: DatasetMetrics) -> str:
    lines = [f"### {DATASET_LABELS[metrics.dataset]} -- {metrics.n_fixtures:,} fixtures", ""]

    lines += ["**Continuous metrics**", "", "| Metric | n | median | mean | min | max | stdev |",
              "|---|---|---|---|---|---|---|"]
    for metric in DESCRIPTIVE_CONTINUOUS_METRICS:
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


def _render_continuous_metric(
    metric: str, a: DatasetMetrics, other: DatasetMetrics, overall: BalanceTest
) -> str:
    """One metric's full table (Overall + per-language family rows),
    repo-level throughout -- see compare_datasets_repo_level()'s docstring."""
    overall_n = NCounts(
        len(a.repo_level_continuous[metric]), len(other.repo_level_continuous[metric])
    )
    per_language = compute_stratified_continuous_balance(
        a.repo_level_continuous_by_language[metric],
        other.repo_level_continuous_by_language[metric],
        metric,
    )
    per_language_n = {
        language: NCounts(
            len(a.repo_level_continuous_by_language[metric].get(language, [])),
            len(other.repo_level_continuous_by_language[metric].get(language, [])),
        )
        for language in per_language
    }
    lines = [f"### {metric}", ""]
    lines.append(
        render_comparison_table(
            overall, overall_n, per_language, per_language_n, other_dataset=other.dataset
        )
    )
    return "\n".join(lines)


def _render_categorical_metric(
    metric: str,
    a: DatasetMetrics,
    other: DatasetMetrics,
    overall: BalanceTest,
    overall_n: NCounts,
    a_by_language: dict[str, dict[str, int]] | None,
    other_by_language: dict[str, dict[str, int]] | None,
    a_n_by_language: dict[str, int],
    other_n_by_language: dict[str, int],
) -> str:
    """One categorical metric's table -- Overall-only if `a_by_language`/
    `other_by_language` is None (no family defined for this metric, e.g.
    commit_type), else Overall + per-language family rows."""
    per_language = None
    per_language_n = None
    if a_by_language is not None and other_by_language is not None:
        per_language = compute_stratified_categorical_balance(
            a_by_language, other_by_language, metric
        )
        per_language_n = {
            language: NCounts(
                a_n_by_language.get(language, 0), other_n_by_language.get(language, 0)
            )
            for language in per_language
        }
    lines = [f"### {metric}", ""]
    lines.append(
        render_comparison_table(
            overall, overall_n, per_language, per_language_n, other_dataset=other.dataset
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
    categorical_overall = compare_datasets_categorical(a, other)
    lines = [f"## {label}: {DATASET_LABELS['a']} vs {DATASET_LABELS[other.dataset]}", ""]

    lines += [
        "**Continuous metrics (Mann-Whitney U on repo-level values, two-sided)** "
        "-- one mean value per repo (per language, for the per-language rows), "
        "not per fixture, so fixtures clustering within a repo can't inflate "
        "the result. Effect size is Cliff's delta (thresholds: negligible "
        "<0.147, small <0.33, medium <0.474, else large; positive means the "
        "comparison dataset tends to have larger values than A, negative means "
        "A tends to have larger values). The Overall row is a single pooled "
        "test, not BH-corrected; each metric's per-language rows are BH-FDR "
        "corrected against each other only (one family per metric, 4 languages).",
        "",
        _render_floor_percentage_footnote(a, other),
    ]
    for metric in CONTINUOUS_METRICS:
        lines.append(_render_continuous_metric(metric, a, other, continuous_overall[metric]))

    lines += [
        "**Categorical metrics (chi-square)** -- Effect size is Cramer's V "
        "(thresholds: negligible <0.1, small <0.3, medium <0.5, else large). "
        "Same Overall-uncorrected / per-language-family-corrected convention "
        "as the continuous metrics above. `scope`/`fixture_type` each have a "
        "per-language family; `commit_type` doesn't (renders Overall-only).",
        "",
    ]
    lines.append(
        _render_categorical_metric(
            "scope",
            a,
            other,
            categorical_overall["scope"],
            NCounts(a.scope_n, other.scope_n),
            a.scope_by_language,
            other.scope_by_language,
            a.scope_n_by_language,
            other.scope_n_by_language,
        )
    )
    lines.append(
        _render_categorical_metric(
            "fixture_type",
            a,
            other,
            categorical_overall["fixture_type"],
            NCounts(len(a.fixture_type_by_repo), len(other.fixture_type_by_repo)),
            a.fixture_type_by_language,
            other.fixture_type_by_language,
            a.fixture_type_n_by_language,
            other.fixture_type_n_by_language,
        )
    )
    lines += [
        "> **`fixture_type`'s result above is not used in the paper.** It's "
        "a pooled/per-language fixture-level chi-square, which treats "
        "fixtures clustered within a repo as independent observations and "
        "inflates both chi2 and Cramer's V (see [Limitations § Categorical "
        "Pseudo-Replication](../docs/reference/limitations.md#categorical-"
        "pseudo-replication)). The paper reports the repo-level "
        '`fixture_type` proportion test in "Repo-level aggregates" below '
        "instead. `scope`/`commit_type` above are unaffected and are used "
        "as-is.",
        "",
    ]
    lines.append(
        _render_categorical_metric(
            "commit_type",
            a,
            other,
            categorical_overall["commit_type"],
            NCounts(a.commit_type_n, other.commit_type_n),
            None,
            None,
            {},
            {},
        )
    )

    return "\n".join(lines)


def _render_repo_level_comparison(
    label: str, a: DatasetMetrics, other: DatasetMetrics
) -> str:
    lines = [
        f"### {label}: {DATASET_LABELS['a']} vs {DATASET_LABELS[other.dataset]}",
        "",
        "**fixture_type, repo-level (Mann-Whitney U on per-repo category "
        "proportions, two-sided)** -- the fixture_type chi-square table "
        "above treats every fixture as an independent observation, but "
        "fixtures cluster within repos (shared framework choice, project "
        "convention), which inflates chi2 and partially corrupts Cramer's "
        "V. This instead compares, per repo, what fraction of its "
        "fixtures are each fixture_type -- so each repo counts once "
        "regardless of how many fixtures it contributed. **This is the "
        "`fixture_type` result reported in the paper.**",
        "",
    ]
    fixture_type_repo_level = compare_categorical_repo_level(
        a.fixture_type_by_repo, other.fixture_type_by_repo, "fixture_type"
    )
    n = repo_level_category_n_counts(a.fixture_type_by_repo, other.fixture_type_by_repo)
    lines.append(render_categorical_repo_level_table(fixture_type_repo_level, other.dataset, n))

    return "\n".join(lines)


def generate_report(*, db_root: Path = paths.DB_ROOT) -> str:
    loaded = {ds: load_dataset_metrics(ds, db_root=db_root) for ds in ("a", "c")}
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
        "## Repo-level aggregates",
        "",
        "fixture_type re-tested with one *proportion-per-repo* value per "
        "category instead of pooled/per-language fixture-level chi-square, "
        "so each repo counts once regardless of how many fixtures it "
        "contributed -- see compare_categorical_repo_level()'s docstring in "
        "_shared.py. (The continuous metrics above are already repo-level "
        "throughout, including their per-language rows, so they don't need "
        "a separate view here.)",
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
