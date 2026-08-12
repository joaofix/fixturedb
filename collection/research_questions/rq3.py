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
   `test_files.language` (joined via `fixtures.file_id`), a full
   per-language family test.
3. **Framework distribution** -- `mock_usages.framework`. Purely
   descriptive, per language, no statistical test (see below for why).
4. **Test-double category distribution** -- `mock_usages.category`
   (dummy/stub/spy/mock/fake). Per-language repo-level-proportion test
   (see below). Not in the original RQ3 text but already deterministically
   computed by the same detection pass that produces `framework` (see
   detector_shared.py's `_classify_mock_category`, substring match against
   feature_extraction_patterns.yaml's `mock_category_keywords`) and
   squarely inside "mock usage" -- costs nothing extra to fold in.
5. **Interaction depth** -- `mock_usages.num_interactions_configured`
   (continuous, Mann-Whitney): among mocks that ARE created, how much is
   configured on them (`.return_value`/`.side_effect`/`when(...).thenReturn`
   style calls)? No per-language family (not one of the metrics the paper
   review named) -- renders Overall-only, both fixture-level and
   repo-level.

`framework` and `category` deliberately get *no pooled cross-language
analysis at all* (chi-square or otherwise), fixed 2026-08-12: Dataset A is
TypeScript-heavy, Dataset C skews Python/JavaScript, and both variables are
language-specific by construction or convention --
`mock_usages.framework` names literally can't overlap across languages
(`unittest.mock` is Python-only, Sinon is JS-only, Mockito is Java-only),
and test-double category naming conventions vary systematically by
ecosystem too (Sinon's explicit `.spy()`/`.stub()` API vs Python's
monolithic `Mock`/`MagicMock`). Any pooled number for either -- chi-square
*or* the repo-level-proportion Mann-Whitney this package uses everywhere
else to fix pseudo-replication -- reflects each dataset's language mix,
not an authorship-era effect. See docs/reference/limitations.md's
"Categorical Pseudo-Replication" section.

- `framework`: `_render_framework_by_language_table()` -- top 3 frameworks
  per language per dataset (union of both sides' top 3), plain
  percentages, no test/effect size.
- `category`: `_render_category_by_language_table()` -- per language, the
  same repo-level-proportion Mann-Whitney + Cliff's delta
  `compare_categorical_repo_level()` already computes elsewhere in this
  script, just computed once per language instead of pooled, so each
  language's own 5-category family (dummy/stub/spy/mock/fake) is its own
  BH-FDR family, independent of every other language's. A separate,
  clearly-labeled aggregate descriptive (percentages only, no inference)
  table is also shown for reference.

`has_mock` is unaffected by any of this -- a binary yes/no isn't a
language-specific construct the way a framework *name* or a category
*naming convention* is, so its existing pooled + per-language chi-square
family (fixture-level, "not used in the paper" -- see below) and its
pooled repo-level-proportion test (in "Repo-level aggregates", the one
actually reported) both stand unchanged.

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
    apply_fdr_correction,
    compare_categorical_repo_level,
    compute_language_leakage,
    compute_stratified_categorical_balance,
    fetch_categorical_column,
    fetch_continuous_column,
    fetch_continuous_column_by_repo,
    fmt,
    format_p_value,
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

CONTINUOUS_METRICS = ["num_mocks", "num_interactions_configured"]
# All 3 are shown descriptively per dataset (_render_dataset_summary());
# only has_mock also gets an A-vs-C chi-square test (TESTED_CATEGORICAL_
# METRICS below) -- framework/category's pooled treatment was removed
# 2026-08-12 (see module docstring).
CATEGORICAL_METRICS = ["has_mock", "framework", "category"]
TESTED_CATEGORICAL_METRICS = ["has_mock"]


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
    category_by_repo_and_language: dict[str, dict[int, dict[str, int]]] = field(
        default_factory=dict
    )
    language_leakage: list[LanguageLeakage] = field(default_factory=list)
    has_mock_dist_by_language: dict[str, dict[str, int]] = field(default_factory=dict)
    has_mock_n_by_language: dict[str, int] = field(default_factory=dict)
    repo_level_continuous: dict[str, list[float]] = field(default_factory=dict)
    has_mock_by_repo: dict[int, dict[str, int]] = field(default_factory=dict)


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
    `mock_usages.category`. Feeds only the per-dataset descriptive summary
    now (_render_dataset_summary()) -- the A-vs-C comparison uses
    _fetch_category_by_repo_and_language() below instead."""
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


def _fetch_category_by_repo_and_language(
    conn: sqlite3.Connection,
) -> dict[str, dict[int, dict[str, int]]]:
    """{language: {repo_id: {category: count}}} -- per-(repo,language)
    category counts, for the per-language repo-level-proportion test in
    _render_category_by_language_table(). Test-double category choice
    varies systematically by language/ecosystem convention (see this
    module's docstring), so a repo's category mix is compared within one
    language at a time here, never pooled across languages."""
    rows = conn.execute(
        "SELECT tf.language, mu.repo_id, mu.category, COUNT(*) FROM mock_usages mu "
        "JOIN fixtures f ON mu.fixture_id = f.id "
        "JOIN test_files tf ON f.file_id = tf.id "
        "WHERE mu.category IS NOT NULL "
        "GROUP BY tf.language, mu.repo_id, mu.category"
    ).fetchall()
    result: dict[str, dict[int, dict[str, int]]] = {}
    for language, repo_id, category, count in rows:
        result.setdefault(language, {}).setdefault(repo_id, {})[category] = count
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
        category_by_repo_and_language = _fetch_category_by_repo_and_language(conn)
        has_mock_n_by_language = _fetch_fixture_repo_count_by_language(conn)
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
        framework_dist=framework_dist,
        category_dist=category_dist,
        mock_rate_by_language=mock_rate_by_language,
        framework_by_language=framework_by_language,
        category_by_language=category_by_language,
        category_by_repo_and_language=category_by_repo_and_language,
        language_leakage=language_leakage,
        repo_level_continuous=repo_level_continuous,
        has_mock_by_repo=has_mock_by_repo,
    )


def compare_datasets_categorical(
    a: DatasetMetrics, other: DatasetMetrics
) -> dict[str, BalanceTest]:
    """A vs `other`: pooled fixture-level chi-square, has_mock only --
    the Overall row for has_mock's table. framework/category no longer
    get a pooled chi-square test at all (see this module's docstring)."""
    return {
        metric: compute_categorical_balance(
            human_dist=_categorical_values(other, metric),
            agent_dist=_categorical_values(a, metric),
            variable=metric,
        )
        for metric in TESTED_CATEGORICAL_METRICS
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
    alongside the repo-level one; no per-language family for either)."""
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


def _render_has_mock(a: DatasetMetrics, other: DatasetMetrics, overall: BalanceTest) -> str:
    per_language = compute_stratified_categorical_balance(
        a.has_mock_dist_by_language, other.has_mock_dist_by_language, "has_mock"
    )
    per_language_n = {
        language: NCounts(
            a.has_mock_n_by_language.get(language, 0), other.has_mock_n_by_language.get(language, 0)
        )
        for language in per_language
    }
    overall_n = NCounts(len(a.has_mock_by_repo), len(other.has_mock_by_repo))
    lines = ["### has_mock", ""]
    lines.append(
        render_comparison_table(
            overall, overall_n, per_language, per_language_n, other_dataset=other.dataset
        )
    )
    return "\n".join(lines)


def _render_framework_by_language_table(a: DatasetMetrics, other: DatasetMetrics) -> str:
    """Fix (2026-08-12): framework choice is language-specific by
    construction (unittest.mock is Python-only, Sinon is JS-only, Mockito
    is Java-only), so a pooled cross-language comparison just reflects
    each dataset's language mix (Dataset A is TypeScript-heavy, Dataset C
    skews Python/JavaScript) rather than an authorship-era effect. Purely
    descriptive by design -- no test, no effect size. One row per
    (language, framework) for every framework appearing in either side's
    top 3 for that language (the union, not just A's top 3, so a reader
    can see both sides' numbers for the same framework even if it's only
    prominent on one side)."""
    languages = sorted(set(a.framework_by_language) | set(other.framework_by_language))
    lines = [
        f"| Language | Framework | {DATASET_LABELS['a']} (%) | {DATASET_LABELS[other.dataset]} (%) |",
        "|---|---|---|---|",
    ]
    if not languages:
        lines.append("| _(no data)_ | -- | -- | -- |")
        lines.append("")
        return "\n".join(lines)

    for language in languages:
        a_dist = a.framework_by_language.get(language, {})
        other_dist = other.framework_by_language.get(language, {})
        a_total = sum(a_dist.values())
        other_total = sum(other_dist.values())
        a_top3 = {fw for fw, _ in sorted(a_dist.items(), key=lambda kv: -kv[1])[:3]}
        other_top3 = {fw for fw, _ in sorted(other_dist.items(), key=lambda kv: -kv[1])[:3]}
        frameworks = a_top3 | other_top3
        if not frameworks:
            lines.append(f"| {language} | _(no mocks)_ | -- | -- |")
            continue
        ranked = sorted(
            frameworks,
            key=lambda fw: (
                -(a_dist.get(fw, 0) / a_total if a_total else 0.0),
                -(other_dist.get(fw, 0) / other_total if other_total else 0.0),
            ),
        )
        for framework in ranked:
            a_fw_pct = 100 * a_dist.get(framework, 0) / a_total if a_total else 0.0
            other_fw_pct = 100 * other_dist.get(framework, 0) / other_total if other_total else 0.0
            lines.append(f"| {language} | {framework} | {a_fw_pct:.1f}% | {other_fw_pct:.1f}% |")
    lines.append("")
    return "\n".join(lines)


def _render_category_by_language_table(a: DatasetMetrics, other: DatasetMetrics) -> str:
    """Fix (2026-08-12): test-double category naming conventions also vary
    systematically by language/ecosystem (Sinon's explicit .spy()/.stub()
    API vs Python's monolithic Mock/MagicMock), so this reuses
    compare_categorical_repo_level() -- the repo-level-proportion Mann-
    Whitney + Cliff's delta test already used elsewhere in this script to
    fix fixture-clustering pseudo-replication -- computed once per
    language instead of pooled. Each language's own up-to-5-category
    family (dummy/fake/mock/spy/stub) is BH-FDR corrected independently of
    every other language's."""
    languages = sorted(
        set(a.category_by_repo_and_language) & set(other.category_by_repo_and_language)
    )
    lines = [
        f"| Language | Category | {DATASET_LABELS['a']} (median %) | "
        f"{DATASET_LABELS[other.dataset]} (median %) | δ (A vs C) | p (BH) |",
        "|---|---|---|---|---|---|",
    ]
    if not languages:
        lines.append("| _(no language shared by both datasets)_ | -- | -- | -- | -- | -- |")
        lines.append("")
        return "\n".join(lines)

    for language in languages:
        a_by_repo = a.category_by_repo_and_language[language]
        other_by_repo = other.category_by_repo_and_language[language]
        results = compare_categorical_repo_level(a_by_repo, other_by_repo, f"category_{language}")
        corrected = apply_fdr_correction(results)
        for category in sorted(corrected):
            t = corrected[category]
            d = t.details
            if d.get("reason") == "insufficient_data":
                lines.append(f"| {language} | {category} | -- | -- | -- | _insufficient data_ |")
                continue
            adj_p = d.get("adjusted_p_value")
            p_bh = format_p_value(adj_p) if adj_p is not None else "--"
            lines.append(
                f"| {language} | {category} | {pct(d.get('agent_median'))} | "
                f"{pct(d.get('human_median'))} | {fmt(d.get('cliffs_delta'), 3)} | {p_bh} |"
            )
    lines.append("")
    return "\n".join(lines)


def _render_category_aggregate_descriptive_table(a: DatasetMetrics, other: DatasetMetrics) -> str:
    """Pooled category_dist as plain percentages -- descriptive only, kept
    for reference, explicitly NOT a statistical claim (see the per-language
    table above for the actual A-vs-C comparison)."""
    categories = sorted(set(a.category_dist) | set(other.category_dist))
    a_total = sum(a.category_dist.values())
    other_total = sum(other.category_dist.values())
    lines = [
        f"| Category | {DATASET_LABELS['a']} (%) | {DATASET_LABELS[other.dataset]} (%) |",
        "|---|---|---|",
    ]
    if not categories:
        lines.append("| _(no data)_ | -- | -- |")
    for category in categories:
        a_cat_pct = 100 * a.category_dist.get(category, 0) / a_total if a_total else 0.0
        other_cat_pct = 100 * other.category_dist.get(category, 0) / other_total if other_total else 0.0
        lines.append(f"| {category} | {a_cat_pct:.1f}% | {other_cat_pct:.1f}% |")
    lines.append("")
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
        '**has_mock (chi-square)** -- an "Overall" row (single pooled '
        "test, not BH-corrected) plus one BH-corrected row per language "
        "(one family, 4 languages -- see render_comparison_table()'s "
        "docstring in _shared.py). Effect size is Cramer's V (thresholds: "
        "negligible <0.1, small <0.3, medium <0.5, else large). "
        "framework/category are shown further below instead -- see this "
        "module's docstring for why they don't get a chi-square table.",
        "",
    ]
    lines.append(_render_has_mock(a, other, categorical_overall["has_mock"]))
    lines += [
        "> **`has_mock`'s result above is not used in the paper.** It's a "
        "pooled/per-language fixture-level chi-square, which treats "
        "fixtures clustered within a repo as independent observations and "
        "inflates both chi2 and Cramer's V (see [Limitations § Categorical "
        "Pseudo-Replication](../docs/reference/limitations.md#categorical-"
        "pseudo-replication)). The paper reports the repo-level `has_mock` "
        'proportion test in "Repo-level aggregates" below instead.',
        "",
    ]

    lines += [
        "**Mocking framework distribution (descriptive, per language)** -- "
        "no statistical test or effect size: framework names are "
        "language-specific by construction (`unittest.mock` is "
        "Python-only, Sinon is JS-only, Mockito is Java-only), so a pooled "
        "cross-language comparison would just reflect each dataset's "
        "language mix (Dataset A is TypeScript-heavy, Dataset C skews "
        "Python/JavaScript), not an authorship-era effect. Top 3 "
        "frameworks per language per dataset (union of both sides' top 3), "
        "as a percentage of that language's own mock usages.",
        "",
    ]
    lines.append(_render_framework_by_language_table(a, other))

    lines += [
        "**Test-double category distribution, per language (Mann-Whitney U "
        "on per-repo category proportions, two-sided)** -- category naming "
        "conventions also vary systematically by language/ecosystem "
        "(Sinon's explicit `.spy()`/`.stub()` API vs Python's monolithic "
        "`Mock`/`MagicMock`), so this is computed once per language "
        "instead of pooled, reusing the same repo-level-proportion "
        "approach used elsewhere in this script. Each language's own "
        "category family (up to 5: dummy/fake/mock/spy/stub) is BH-FDR "
        "corrected independently of every other language's. Positive "
        "δ means the comparison dataset tends to have a larger "
        "proportion than A.",
        "",
    ]
    lines.append(_render_category_by_language_table(a, other))
    lines += [
        "**Aggregate category distribution (descriptive only -- not used "
        "for inference)** -- pooled across all languages and repos, shown "
        "for reference only; the per-language table above is the real "
        "A-vs-C comparison.",
        "",
    ]
    lines.append(_render_category_aggregate_descriptive_table(a, other))

    return "\n".join(lines)


def _render_repo_level_comparison(
    label: str, a: DatasetMetrics, other: DatasetMetrics
) -> str:
    lines = [
        f"### {label}: {DATASET_LABELS['a']} vs {DATASET_LABELS[other.dataset]}",
        "",
        "**has_mock, repo-level (Mann-Whitney U on per-repo category "
        "proportions, two-sided)** -- the chi-square table above treats "
        "every fixture as an independent observation, but fixtures "
        "cluster within repos (shared framework choice, project "
        "convention), which inflates chi2 and partially corrupts Cramer's "
        "V. This instead compares, per repo, what fraction of its "
        "fixtures have >=1 mock -- so each repo counts once regardless of "
        "how many fixtures it contributed. **This is the `has_mock` "
        "result reported in the paper.** (framework's per-language "
        "descriptive table and category's per-language repo-level "
        "proportion table are both in the main comparison section above "
        "instead -- neither gets a pooled-across-languages view here, see "
        "this module's docstring for why.)",
        "",
    ]
    repo_level = compare_categorical_repo_level(a.has_mock_by_repo, other.has_mock_by_repo, "has_mock")
    n = repo_level_category_n_counts(a.has_mock_by_repo, other.has_mock_by_repo)
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
        "has_mock re-tested with one *proportion-per-repo* value instead "
        "of pooled/per-language fixture-level chi-square, so each repo "
        "counts once regardless of how many fixtures it contributed. "
        "(num_mocks/num_interactions_configured already have their own "
        "repo-level Overall row above, in the main comparison section; "
        "framework/category are handled entirely in the main comparison "
        "section too -- see this module's docstring.)",
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
