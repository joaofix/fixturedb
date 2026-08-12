"""
RQ3 -- Mocking (Quantitative): how do agent-generated and human-written
fixtures differ in mock usage -- prevalence, framework selection, category,
and interaction depth?

Five metrics, computed per dataset (A/C):

1. **Mock prevalence per fixture** -- `fixtures.num_mocks` (continuous,
   Mann-Whitney), plus a derived has_mock/no_mock split (chi-square) so the
   headline "do agents mock more or less" question has both a magnitude
   answer and a plain yes/no-prevalence one.
2. **Mock prevalence per language** -- same has_mock split, broken down by
   `test_files.language` (joined via `fixtures.file_id`), now a full
   per-language family test (see below), not just descriptive.
3. **Framework distribution** -- `mock_usages.framework` (chi-square
   overall and, now, per language too).
4. **Test-double category distribution** -- `mock_usages.category`
   (dummy/stub/spy/mock/fake, chi-square, overall and per language).
   Not in the original RQ3 text but already deterministically computed by
   the same detection pass that produces `framework` (see
   detector_shared.py's `_classify_mock_category`, substring match
   against feature_extraction_patterns.yaml's `mock_category_keywords`)
   and squarely inside "mock usage" -- costs nothing extra to fold in.
5. **Interaction depth** -- `mock_usages.num_interactions_configured`
   (continuous, Mann-Whitney): among mocks that ARE created, how much is
   configured on them (`.return_value`/`.side_effect`/`when(...).thenReturn`
   style calls)? No per-language family (not one of the metrics the paper
   review named) -- renders Overall-only, both fixture-level and
   repo-level (unchanged from before).

The old RQ3's qualitative target-layer coding (boundary/internal/
infrastructure, from `target_identifier`) is deliberately NOT reproduced
here -- dropped in favor of staying purely quantitative, per this RQ's own
note that the qualitative layer "can be dropped ... to keep this purely
quantitative."

has_mock/framework/category each render through _shared.py's
render_comparison_table(): one "Overall" row (uncorrected, single pooled
test) plus one BH-corrected row per language, family-scoped to exactly
that variable's own 4 languages, corrected independently of the other two
variables and of their own Overall row (see render_comparison_table()'s
docstring). They're also re-tested in "Repo-level aggregates" with
per-repo category proportions (Mann-Whitney U + Cliff's delta) instead of
pooled fixture/mock-level chi-square -- fixtures/mocks cluster within
repos, so the pooled chi-square treats a repo's hundreds of correlated
rows as hundreds of independent observations, inflating both chi2 and
Cramer's V; see compare_categorical_repo_level()'s docstring in
_shared.py. `num_mocks`/`num_interactions_configured` have no per-language
family and are unaffected by any of this.

A vs C only -- Dataset B (contemporary within-repo human baseline) is still
collected (db/b.db) but out of scope for this script's reported
comparisons; see rq1.py's module docstring.

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
    NCounts,
    compare_categorical_repo_level,
    compute_language_leakage,
    compute_stratified_categorical_balance,
    fetch_categorical_column,
    fetch_categorical_column_by_repo,
    fetch_continuous_column,
    fetch_continuous_column_by_repo,
    fmt,
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
    category_by_language: dict[str, dict[str, int]] = field(default_factory=dict)
    language_leakage: list[LanguageLeakage] = field(default_factory=list)
    has_mock_dist_by_language: dict[str, dict[str, int]] = field(default_factory=dict)
    has_mock_n_by_language: dict[str, int] = field(default_factory=dict)
    mock_usage_n_by_language: dict[str, int] = field(default_factory=dict)
    repo_level_continuous: dict[str, list[float]] = field(default_factory=dict)
    has_mock_by_repo: dict[int, dict[str, int]] = field(default_factory=dict)
    framework_by_repo: dict[int, dict[str, int]] = field(default_factory=dict)
    category_by_repo: dict[int, dict[str, int]] = field(default_factory=dict)


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


def _fetch_category_by_language(conn: sqlite3.Connection) -> dict[str, dict[str, int]]:
    """category distribution per fixture's own language -- framework
    analogue (see _fetch_framework_by_language()'s docstring), applied to
    `mock_usages.category`."""
    rows = conn.execute(
        "SELECT tf.language, mu.category, COUNT(*) FROM mock_usages mu "
        "JOIN fixtures f ON mu.fixture_id = f.id "
        "JOIN test_files tf ON f.file_id = tf.id "
        "WHERE mu.category IS NOT NULL "
        "GROUP BY tf.language, mu.category"
    ).fetchall()
    result: dict[str, dict[str, int]] = {}
    for language, category, count in rows:
        result.setdefault(language, {})[category] = count
    return result


def _fetch_fixture_repo_count_by_language(conn: sqlite3.Connection) -> dict[str, int]:
    """Distinct repo count per language, among ALL fixtures -- the n_A/n_C
    denominator for has_mock's per-language rows: every repo with a
    fixture of that language, not just ones with a mock."""
    rows = conn.execute(
        "SELECT tf.language, COUNT(DISTINCT f.repo_id) FROM fixtures f "
        "JOIN test_files tf ON f.file_id = tf.id GROUP BY tf.language"
    ).fetchall()
    return dict(rows)


def _fetch_mock_usage_repo_count_by_language(conn: sqlite3.Connection) -> dict[str, int]:
    """Distinct repo count per language, among mock_usages rows -- the
    n_A/n_C denominator for framework/category's per-language rows (a
    different, smaller population than has_mock's: only repos with >=1
    actual mock in that language). Shared by both framework and category
    since both are drawn from the same mock_usages population."""
    rows = conn.execute(
        "SELECT tf.language, COUNT(DISTINCT mu.repo_id) FROM mock_usages mu "
        "JOIN fixtures f ON mu.fixture_id = f.id "
        "JOIN test_files tf ON f.file_id = tf.id "
        "GROUP BY tf.language"
    ).fetchall()
    return dict(rows)


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
        category_by_language = _fetch_category_by_language(conn)
        has_mock_n_by_language = _fetch_fixture_repo_count_by_language(conn)
        mock_usage_n_by_language = _fetch_mock_usage_repo_count_by_language(conn)
        language_leakage = compute_language_leakage(conn)
        # continuous_by_repo's "num_mocks" entry is reused below (as
        # num_mocks_by_repo) to derive has_mock_by_repo's per-repo
        # has_mock/no_mock counts -- no second query needed.
        continuous_by_repo = {
            m: fetch_continuous_column_by_repo(conn, table, m)
            for m, table in _CONTINUOUS_METRIC_TABLES.items()
        }
        repo_level_continuous = {
            m: repo_level_means(by_repo) for m, by_repo in continuous_by_repo.items()
        }
        num_mocks_by_repo = continuous_by_repo["num_mocks"]
        framework_by_repo = fetch_categorical_column_by_repo(conn, "mock_usages", "framework")
        category_by_repo = fetch_categorical_column_by_repo(conn, "mock_usages", "category")

    has_mock_dist = {
        "has_mock": sum(1 for n in num_mocks_raw if n > 0),
        "no_mock": sum(1 for n in num_mocks_raw if n == 0),
    }
    # Derived from num_mocks_by_repo (fixtures.num_mocks > 0), same
    # threshold has_mock_dist above uses, just grouped by repo instead of
    # pooled -- what compare_categorical_repo_level() needs for the
    # repo-declustered has_mock test (see its docstring in _shared.py).
    has_mock_by_repo = {
        repo_id: {
            "has_mock": sum(1 for n in vals if n > 0),
            "no_mock": sum(1 for n in vals if n == 0),
        }
        for repo_id, vals in num_mocks_by_repo.items()
    }
    # Derived from mock_rate_by_language (total/with_mocks per language),
    # no separate query needed -- this is what
    # compute_stratified_categorical_balance() needs to check whether an
    # A-vs-C mock-prevalence difference holds within a language, not just
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
        has_mock_n_by_language=has_mock_n_by_language,
        mock_usage_n_by_language=mock_usage_n_by_language,
        framework_dist=framework_dist,
        category_dist=category_dist,
        mock_rate_by_language=mock_rate_by_language,
        framework_by_language=framework_by_language,
        category_by_language=category_by_language,
        language_leakage=language_leakage,
        repo_level_continuous=repo_level_continuous,
        has_mock_by_repo=has_mock_by_repo,
        framework_by_repo=framework_by_repo,
        category_by_repo=category_by_repo,
    )


def compare_datasets_categorical(
    a: DatasetMetrics, other: DatasetMetrics
) -> dict[str, BalanceTest]:
    """A vs `other`: pooled fixture/mock-level chi-square per categorical
    metric (has_mock, framework, category) -- the Overall row for each
    metric's table."""
    return {
        metric: compute_categorical_balance(
            human_dist=_categorical_values(other, metric),
            agent_dist=_categorical_values(a, metric),
            variable=metric,
        )
        for metric in CATEGORICAL_METRICS
    }


def compare_datasets_repo_level(
    a: DatasetMetrics, other: DatasetMetrics
) -> dict[str, BalanceTest]:
    """A vs `other`, one mean value per repo instead of one value per
    fixture/mock -- num_mocks/num_interactions_configured only (no
    per-language family; see this module's docstring)."""
    return {
        metric: compute_continuous_balance(
            human_values=other.repo_level_continuous[metric],
            agent_values=a.repo_level_continuous[metric],
            variable=metric,
        )
        for metric in CONTINUOUS_METRICS
    }


def compare_datasets_fixture_level(
    a: DatasetMetrics, other: DatasetMetrics
) -> dict[str, BalanceTest]:
    """A vs `other`, raw per-fixture/mock values -- num_mocks/
    num_interactions_configured's fixture-level Overall row (kept
    alongside the repo-level one, unchanged from before this task; no
    per-language family for either)."""
    return {
        metric: compute_continuous_balance(
            human_values=_continuous_values(other, metric),
            agent_values=_continuous_values(a, metric),
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

    lines += ["**Continuous metrics**", "", "| Metric | n | median | mean | min | max | stdev |",
              "|---|---|---|---|---|---|---|"]
    for metric in CONTINUOUS_METRICS:
        s = summarize_continuous(_continuous_values(metrics, metric))
        lines.append(
            f"| {metric} | {s['n']:,} | {fmt(s['median'])} | {fmt(s['mean'])} | "
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


def _render_continuous_metric(
    metric: str,
    a: DatasetMetrics,
    other: DatasetMetrics,
    fixture_level: BalanceTest,
    repo_level: BalanceTest,
) -> str:
    """Overall-only, both bases shown (no per-language family for
    num_mocks/num_interactions_configured -- see this module's
    docstring)."""
    fixture_n = NCounts(
        len(_continuous_values(a, metric)), len(_continuous_values(other, metric))
    )
    repo_n = NCounts(len(a.repo_level_continuous[metric]), len(other.repo_level_continuous[metric]))
    lines = [f"### {metric}", "", "**Fixture-level**", ""]
    lines.append(
        render_comparison_table(fixture_level, fixture_n, None, None, other_dataset=other.dataset)
    )
    lines += ["**Repo-level** (one mean value per repo)", ""]
    lines.append(
        render_comparison_table(repo_level, repo_n, None, None, other_dataset=other.dataset)
    )
    return "\n".join(lines)


def _render_categorical_metric(
    metric: str,
    a: DatasetMetrics,
    other: DatasetMetrics,
    overall: BalanceTest,
    overall_n: NCounts,
    a_by_language: dict[str, dict[str, int]],
    other_by_language: dict[str, dict[str, int]],
    a_n_by_language: dict[str, int],
    other_n_by_language: dict[str, int],
) -> str:
    per_language = compute_stratified_categorical_balance(a_by_language, other_by_language, metric)
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


def _render_comparison(label: str, a: DatasetMetrics, other: DatasetMetrics) -> str:
    fixture_level = compare_datasets_fixture_level(a, other)
    repo_level = compare_datasets_repo_level(a, other)
    categorical_overall = compare_datasets_categorical(a, other)
    lines = [f"## {label}: {DATASET_LABELS['a']} vs {DATASET_LABELS[other.dataset]}", ""]

    lines += [
        "**Continuous metrics (Mann-Whitney U, two-sided)** -- num_mocks/ "
        "num_interactions_configured have no per-language family (not one "
        "of the metrics the paper review named), so both render Overall-only, "
        "shown at both the fixture-level (every fixture/mock as an "
        "observation) and repo-level (one mean value per repo) basis. "
        "Effect size is Cliff's delta (thresholds: negligible <0.147, small "
        "<0.33, medium <0.474, else large).",
        "",
    ]
    for metric in CONTINUOUS_METRICS:
        lines.append(
            _render_continuous_metric(metric, a, other, fixture_level[metric], repo_level[metric])
        )

    lines += [
        "**Categorical metrics (chi-square)** -- has_mock/framework/category "
        'each have a per-language family: an "Overall" row (single pooled '
        "test, not BH-corrected) plus one BH-corrected row per language "
        "(one family per metric, 4 languages -- see "
        "render_comparison_table()'s docstring in _shared.py). Effect size "
        "is Cramer's V (thresholds: negligible <0.1, small <0.3, medium "
        "<0.5, else large).",
        "",
    ]
    lines.append(
        _render_categorical_metric(
            "has_mock",
            a,
            other,
            categorical_overall["has_mock"],
            NCounts(len(a.has_mock_by_repo), len(other.has_mock_by_repo)),
            a.has_mock_dist_by_language,
            other.has_mock_dist_by_language,
            a.has_mock_n_by_language,
            other.has_mock_n_by_language,
        )
    )
    lines.append(
        _render_categorical_metric(
            "framework",
            a,
            other,
            categorical_overall["framework"],
            NCounts(len(a.framework_by_repo), len(other.framework_by_repo)),
            a.framework_by_language,
            other.framework_by_language,
            a.mock_usage_n_by_language,
            other.mock_usage_n_by_language,
        )
    )
    lines.append(
        _render_categorical_metric(
            "category",
            a,
            other,
            categorical_overall["category"],
            NCounts(len(a.category_by_repo), len(other.category_by_repo)),
            a.category_by_language,
            other.category_by_language,
            a.mock_usage_n_by_language,
            other.mock_usage_n_by_language,
        )
    )
    lines += [
        "> **None of `has_mock`/`framework`/`category` above are used in "
        "the paper.** They're pooled/per-language fixture/mock-level "
        "chi-square, which treats fixtures/mocks clustered within a repo "
        "as independent observations and inflates both chi2 and Cramer's V "
        "(see [Limitations § Categorical Pseudo-Replication]"
        "(../docs/reference/limitations.md#categorical-pseudo-replication)). "
        'The paper reports the repo-level proportion tests in "Repo-level '
        'aggregates" below instead.',
        "",
    ]

    return "\n".join(lines)


def _render_repo_level_comparison(
    label: str, a: DatasetMetrics, other: DatasetMetrics
) -> str:
    lines = [
        f"### {label}: {DATASET_LABELS['a']} vs {DATASET_LABELS[other.dataset]}",
        "",
        "**has_mock / framework / category, repo-level (Mann-Whitney U on "
        "per-repo category proportions, two-sided)** -- the chi-square "
        "tables above treat every fixture/mock as an independent "
        "observation, but they cluster within repos (shared framework "
        "choice, project convention), which inflates chi2 and partially "
        "corrupts Cramer's V. This instead compares, per repo, what "
        "fraction of its fixtures/mocks fall in each category -- so each "
        "repo counts once regardless of how many fixtures/mocks it "
        "contributed. **These are the `has_mock`/`framework`/`category` "
        "results reported in the paper.**",
        "",
    ]
    for variable, a_by_repo, other_by_repo in (
        ("has_mock", a.has_mock_by_repo, other.has_mock_by_repo),
        ("framework", a.framework_by_repo, other.framework_by_repo),
        ("category", a.category_by_repo, other.category_by_repo),
    ):
        lines += [f"_{variable}_", ""]
        repo_level = compare_categorical_repo_level(a_by_repo, other_by_repo, variable)
        n = repo_level_category_n_counts(a_by_repo, other_by_repo)
        lines.append(render_categorical_repo_level_table(repo_level, other.dataset, n))

    return "\n".join(lines)


def generate_report(*, db_root: Path = paths.DB_ROOT) -> str:
    loaded = {ds: load_dataset_metrics(ds, db_root=db_root) for ds in ("a", "c")}
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
        "has_mock/framework/category re-tested with one *proportion-per-repo* "
        "value per category instead of pooled/per-language fixture/mock-level "
        "chi-square, so each repo counts once regardless of how many "
        "fixtures/mocks it contributed. (num_mocks/num_interactions_configured "
        "already have their own repo-level Overall row above, in the main "
        "comparison section.)",
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
