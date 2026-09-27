"""
RQ3 -- Mocking (Quantitative): how do agent-generated and human-written
fixtures differ in mock usage?

One paper table (`_render_mocking_summary_table()`), per language and
Overall: **Coverage** -- for each repo, a binary indicator -- does it
have >=1 fixture with a mock at all (`num_mocks > 0`)? Population: every
repo with >=1 fixture (of that language, for the per-language rows; any
language, for Overall) -- reuses `has_mock_by_repo`/`has_mock_by_repo_
and_language`, already fetched by the pre-existing has_mock detection
query. "Coverage A/C (%)" is the share of that population with the
indicator at 1 -- just the mean of that 0/1 list per side. **Purely
descriptive -- no statistical test** (removed 2026-09-27, alongside
RQ2's Table 2: the paper's RQ2/RQ3 coverage tables report plain
percentages, no p-value, no effect size, no BH-FDR family. RQ1 is now
the only script in this package that performs BH-FDR correction at all
-- see
[internal-docs/methodology-improvements/bh-fdr-correction-families.md](../../internal-docs/methodology-improvements/bh-fdr-correction-families.md)
for the full before/after inventory).

**Intensity** (median `num_mocks` across a repo's own mocking fixtures,
among repos where Coverage=1) was removed entirely the same day -- no
longer one of the paper's reported metrics. Its whole computation
(`_mocking_intensities_by_repo()`, `_fetch_num_mocks_by_repo_and_
language()`, the `num_mocks_by_repo_and_language` field, and the
combined 8-test BH-FDR family that used to merge it with Coverage) is
gone, not just its rendering. `num_mocks_by_repo` (Overall-only, no
per-language breakdown) stays on `DatasetMetrics` -- it's also what
`has_mock_by_repo` is derived from (the `num_mocks > 0` threshold), an
independent use that predates and outlives Intensity.

Fixed four-language row order (java, javascript, python, typescript)
rather than a "languages present on both sides" intersection convention
-- a deliberate simplification matching the paper's table spec,
predating the statistical-test removal above and unaffected by it.

This table replaces three previously-reported tables:

- **Mock prevalence** (fixture-level `has_mock` chi-square, pooled + per
  language) -- initially kept (computed identically, mock detection
  logic untouched) in a "## Legacy: Fixture-Level Mock Prevalence (Not
  Used in the Paper)" section below the main comparison, since it was
  already marked "not used in the paper" before this change -- fixture-
  level pseudo-replication, see docs/reference/limitations.md's
  "Categorical Pseudo-Replication". Removed entirely (2026-09-27): never
  cited, and `compare_datasets_categorical()`/`_render_has_mock()`/
  `has_mock_n_by_language`/`_fetch_fixture_repo_count_by_language()` had
  no other consumer once it was gone. The *repo-level* has_mock test that
  WAS reported in the paper (formerly "## Repo-level aggregates") is
  fully superseded by this table's Coverage column -- same population,
  same underlying per-repo has_mock indicator. At the time of this
  removal Coverage was still its own Mann-Whitney + Cliff's delta test
  (computed via `compute_continuous_balance()` directly instead of
  `compare_categorical_repo_level()` -- a two-category proportion test
  on a binary variable is mathematically the mean-of-the-0/1-indicator
  test that call runs, same number, cleaner path there); Coverage's own
  test was itself removed the same day, see above.
- **Framework distribution** -- removed from the report entirely (not
  moved to legacy, per request: framework names are language-specific by
  construction, `unittest.mock` Python-only / Sinon JS-only / Mockito
  Java-only, so a pooled A-vs-C view was already confounded by language
  mix -- 2026-08-12, see docs/reference/limitations.md). `mock_usages.
  framework`'s fetch/fields (`framework_dist`, `framework_by_language`)
  are UNCHANGED and still populate each dataset's own descriptive summary
  above -- only the A-vs-C table is gone.
- **Test-double category distribution** -- same treatment: removed from
  the report entirely (category naming conventions are also
  language/ecosystem-specific -- same 2026-08-12 fix). `category_dist`'s
  fetch/field is UNCHANGED and still populates the per-dataset summary
  above -- the per-language repo-level-proportion test and the pooled
  descriptive table are gone from the report. `category_by_language`/
  `category_by_repo_and_language` (the fetches that fed those two removed
  tables) were themselves removed entirely (2026-09-27) after auditing
  found them genuinely dead -- fetched and stored on `DatasetMetrics` but
  never read by anything, not even the per-dataset summary the comment
  above once claimed.

`num_mocks`'s existing continuous Mann-Whitney tables (fixture-level and
repo-level, Overall-only) are **unchanged** -- not one of the three
tables named for replacement, and never had a per-language family or
BH-FDR correction to begin with (Overall-only, a single pooled test).

`num_interactions_configured` (a separate `mock_usages` column estimating
how many interactions were configured on a mock, e.g. `.return_value`/
`.side_effect`/`thenReturn`) was removed entirely (2026-09-26) -- it was
never one of the paper's reported metrics (the paper review only named
`num_mocks`), so its own continuous Mann-Whitney table (the counterpart to
`num_mocks`'s above) is simply gone, not moved to a legacy section.

**Mock Fixture Counts by Language** (`_render_mock_counts_table()`): an
additional, purely descriptive table (no statistics), rendered right
after the Coverage paper table -- NOT a replacement for it.
The RQ2-counts-table analogue for mocking: raw count + percentage of
`has_mock` fixtures per language, both datasets side by side, denominator
is simply that language's total fixture count (no 'other'
category/double-counting complication the way RQ2's setup/teardown kind
has -- has_mock is a clean binary). Reuses has_mock_dist/has_mock_dist_
by_language, the same counts already backing "Mock prevalence"/"Mock
prevalence by language" in the per-dataset summary above.

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
    compute_language_leakage,
    fetch_categorical_column,
    fetch_continuous_column,
    fetch_continuous_column_by_repo,
    fmt,
    pct,
    render_comparison_table,
    render_language_leakage_table,
    repo_level_means,
    require_db_or_none,
    summarize_continuous,
    write_markdown_report,
)

logger = get_logger(__name__)

CONTINUOUS_METRICS = ["num_mocks"]
# All 3 are shown descriptively per dataset (_render_dataset_summary())
# only -- none gets an A-vs-C statistical test here. has_mock's own
# fixture-level chi-square (Overall + per-language) and framework/
# category's pooled treatment were both removed entirely (2026-08-12 for
# framework/category, 2026-09-27 for has_mock) -- the paper table's
# Coverage column is has_mock's repo-level result and supersedes it.
CATEGORICAL_METRICS = ["has_mock", "framework", "category"]

# Fixed row order for the paper table -- see the module docstring for why
# this is a fixed list rather than a "languages present on both sides"
# intersection convention. Matches rq2.py's RQ2_LANGUAGES.
RQ3_LANGUAGES: tuple[str, ...] = ("java", "javascript", "python", "typescript")


@dataclass
class DatasetMetrics:
    dataset: str
    n_fixtures: int
    n_mock_usages: int
    num_mocks_raw: list[float] = field(default_factory=list)
    has_mock_dist: dict[str, int] = field(default_factory=dict)
    framework_dist: dict[str, int] = field(default_factory=dict)
    category_dist: dict[str, int] = field(default_factory=dict)
    mock_rate_by_language: dict[str, dict] = field(default_factory=dict)
    framework_by_language: dict[str, dict[str, int]] = field(default_factory=dict)
    language_leakage: list[LanguageLeakage] = field(default_factory=list)
    has_mock_dist_by_language: dict[str, dict[str, int]] = field(default_factory=dict)
    repo_level_continuous: dict[str, list[float]] = field(default_factory=dict)
    has_mock_by_repo: dict[int, dict[str, int]] = field(default_factory=dict)
    has_mock_by_repo_and_language: dict[str, dict[int, dict[str, int]]] = field(
        default_factory=dict
    )
    # Raw per-fixture num_mocks, grouped by repo -- feeds has_mock_by_repo's
    # derivation below (num_mocks > 0 threshold). Exactly continuous_
    # by_repo["num_mocks"] from load_dataset_metrics() below, just also
    # kept on the dataclass instead of only its per-repo *mean*
    # (repo_level_continuous["num_mocks"]).
    num_mocks_by_repo: dict[int, list[float]] = field(default_factory=dict)


def _continuous_values(metrics: DatasetMetrics, metric: str) -> list[float]:
    return {
        "num_mocks": metrics.num_mocks_raw,
    }[metric]


# Which table each continuous metric's repo_id column lives on -- num_mocks
# is a fixtures column; fetch_continuous_column_by_repo() works for any
# table as long as it carries its own repo_id.
_CONTINUOUS_METRIC_TABLES = {
    "num_mocks": "fixtures",
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


def _fetch_has_mock_by_repo_and_language(
    conn: sqlite3.Connection,
) -> dict[str, dict[int, dict[str, int]]]:
    """{language: {repo_id: {"has_mock": n, "no_mock": n}}} -- has_mock's
    per-(language, repo) breakdown. Feeds, via
    `_mocking_coverage_indicators()`, the paper table's Coverage column
    (each repo's own has_mock/no_mock counts collapse to a single 0/1
    "has any mock at all" indicator there). Grouped by each
    fixture's own language (test_files.language), not the repo's tag --
    same convention every other per-language grouping in this script
    uses -- so a repo with fixtures in more than one language contributes
    to each language's own rows separately, never mixed together. Same
    has_mock/no_mock threshold (`num_mocks > 0`) as has_mock_dist/
    has_mock_by_repo elsewhere in this module, just grouped by language
    too."""
    rows = conn.execute(
        "SELECT tf.language, f.repo_id, "
        "SUM(CASE WHEN f.num_mocks > 0 THEN 1 ELSE 0 END), "
        "SUM(CASE WHEN f.num_mocks = 0 THEN 1 ELSE 0 END) "
        "FROM fixtures f JOIN test_files tf ON f.file_id = tf.id "
        "WHERE f.num_mocks IS NOT NULL "
        "GROUP BY tf.language, f.repo_id"
    ).fetchall()
    result: dict[str, dict[int, dict[str, int]]] = {}
    for language, repo_id, has_mock, no_mock in rows:
        result.setdefault(language, {})[repo_id] = {"has_mock": has_mock, "no_mock": no_mock}
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
        framework_dist = fetch_categorical_column(conn, "mock_usages", "framework")
        category_dist = fetch_categorical_column(conn, "mock_usages", "category")
        mock_rate_by_language = _fetch_mock_rate_by_language(conn)
        framework_by_language = _fetch_framework_by_language(conn)
        has_mock_by_repo_and_language = _fetch_has_mock_by_repo_and_language(conn)
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
    # pooled -- what _mocking_coverage_indicators() needs for the paper
    # table's Coverage column (Overall row).
    has_mock_by_repo = {
        repo_id: {
            "has_mock": sum(1 for n in vals if n > 0),
            "no_mock": sum(1 for n in vals if n == 0),
        }
        for repo_id, vals in num_mocks_by_repo.items()
    }
    # Derived from mock_rate_by_language (total/with_mocks per language),
    # no separate query needed -- feeds the "Mock prevalence by language"
    # descriptive table in _render_dataset_summary().
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
        has_mock_dist=has_mock_dist,
        has_mock_dist_by_language=has_mock_dist_by_language,
        framework_dist=framework_dist,
        category_dist=category_dist,
        mock_rate_by_language=mock_rate_by_language,
        framework_by_language=framework_by_language,
        language_leakage=language_leakage,
        repo_level_continuous=repo_level_continuous,
        has_mock_by_repo=has_mock_by_repo,
        has_mock_by_repo_and_language=has_mock_by_repo_and_language,
        num_mocks_by_repo=num_mocks_by_repo,
    )


def compare_datasets_repo_level(
    a: DatasetMetrics, other: DatasetMetrics
) -> dict[str, BalanceTest]:
    """A vs `other`, one mean value per repo instead of one value per
    fixture -- num_mocks only (no per-language family; see this module's
    docstring)."""
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
    """A vs `other`, raw per-fixture values -- num_mocks's fixture-level
    Overall row (kept alongside the repo-level one; no per-language
    family)."""
    return {
        metric: compute_continuous_balance(
            human_values=_continuous_values(other, metric),
            agent_values=_continuous_values(a, metric),
            variable=metric,
        )
        for metric in CONTINUOUS_METRICS
    }


# ---------------------------------------------------------------------------
# Paper table: mocking coverage -- see this module's docstring for the
# full methodology.
# ---------------------------------------------------------------------------


def _mocking_coverage_indicators(by_repo: dict[int, dict[str, int]]) -> list[float]:
    """Per-repo binary indicator: 1.0 if that repo has >=1 fixture with a
    mock (has_mocking), else 0.0. `by_repo` is has_mock_by_repo(_and_
    language)'s shape ({repo_id: {"has_mock": n, "no_mock": n}}) -- every
    entry already represents a repo with >=1 fixture (built from fixtures
    with num_mocks IS NOT NULL), so no extra zero-total filter is needed
    here the way rq2.py's teardown-coverage indicator needs one."""
    return [1.0 if counts.get("has_mock", 0) > 0 else 0.0 for counts in by_repo.values()]


def _render_mocking_row(label: str, n_a: int, n_c: int, pct_a: float | None, pct_c: float | None) -> str:
    """One row: Coverage A/C (%) is just the mean of the 0/1
    has-any-mock indicator per side. Purely descriptive -- no statistical
    test (removed 2026-09-27, see this module's docstring)."""
    if pct_a is None and pct_c is None:
        return f"| {label} | {n_a} | {n_c} | -- | -- |"
    return f"| {label} | {n_a} | {n_c} | {pct(pct_a)} | {pct(pct_c)} |"


def _coverage_pct(indicators: list[float]) -> float | None:
    """Mean of a 0/1 indicator list as a 0..1 proportion (pct()'s own
    expected input -- it multiplies by 100 itself), or None if the
    population is empty."""
    return sum(indicators) / len(indicators) if indicators else None


def _render_mocking_summary_table(a: DatasetMetrics, other: DatasetMetrics) -> str:
    """The paper table: per-language + Overall mocking coverage (%).
    Purely descriptive -- no statistical test (removed 2026-09-27, see
    this module's docstring for why RQ3 no longer reports one, and for
    Intensity's complete removal)."""
    other_label = other.dataset.upper()
    lines = [
        "**Coverage** = % of repos with >=1 fixture containing a mock at "
        "all (population: every repo with >=1 fixture, of that language "
        "for the per-language rows). Purely descriptive -- no statistical "
        "test.",
        "",
        f"| Language | n_A | n_{other_label} | Coverage A (%) | Coverage {other_label} (%) |",
        "|---|---|---|---|---|",
    ]

    a_overall = _mocking_coverage_indicators(a.has_mock_by_repo)
    other_overall = _mocking_coverage_indicators(other.has_mock_by_repo)
    lines.append(
        _render_mocking_row(
            "Overall",
            len(a_overall),
            len(other_overall),
            _coverage_pct(a_overall),
            _coverage_pct(other_overall),
        )
    )

    for language in RQ3_LANGUAGES:
        a_by_repo = _mocking_coverage_indicators(a.has_mock_by_repo_and_language.get(language, {}))
        other_by_repo = _mocking_coverage_indicators(
            other.has_mock_by_repo_and_language.get(language, {})
        )
        lines.append(
            _render_mocking_row(
                language,
                len(a_by_repo),
                len(other_by_repo),
                _coverage_pct(a_by_repo),
                _coverage_pct(other_by_repo),
            )
        )

    lines.append("")
    return "\n".join(lines)


def _render_mock_counts_table(a: DatasetMetrics, other: DatasetMetrics) -> str:
    """Fixture-level mock counts by language -- the RQ3 analogue of
    rq2.py's Table 1 (tab:rq2-counts): raw count and percentage of
    fixtures with >=1 mock (`has_mock`), per language, both datasets side
    by side. Purely descriptive, no statistics -- neither is the paper's
    actual mocking comparison, the repo-level Coverage table above (also
    purely descriptive, see this module's docstring). Simpler than RQ2's
    counts table
    besides: `has_mock` is a clean binary (a fixture either has >=1 mock
    or it doesn't), so there's no 'other' category to exclude from the
    denominator and no double-counting concern the way RQ2's
    setup_and_teardown kind creates -- the denominator for every row here
    is simply that language's (or, for Overall, the dataset's) total
    fixture count, no exclusions needed. Reuses has_mock_dist/has_mock_
    dist_by_language -- the exact counts already backing 'Mock
    prevalence'/'Mock prevalence by language' in the per-dataset summary
    above -- so this is a different view of identical numbers, not a
    separate computation."""
    other_label = other.dataset.upper()
    lines = [
        "### Mock Fixture Counts by Language",
        "",
        "Raw count of fixtures with >=1 mock (`has_mock`), per language, "
        "each also shown as a percentage of that language's total fixture "
        "count. Unlike RQ2's setup/teardown counts table, `has_mock` is a "
        "clean binary with no 'other' category and no double-counting "
        "concern, so the denominator here is simply the total fixture "
        "count for that language/dataset -- no exclusions. Total is the "
        "dataset-wide sum across every language present, not just the "
        "four rows below. Purely descriptive -- no significance test "
        "(see the Coverage table above for the paper's actual, repo-level "
        "mocking comparison).",
        "",
        f"| Language | Mock A (n) | Mock A (%) | Mock {other_label} (n) | Mock {other_label} (%) |",
        "|---|---|---|---|---|",
    ]

    def _row(label: str, a_dist: dict[str, int], other_dist: dict[str, int]) -> str:
        a_total = sum(a_dist.values())
        other_total = sum(other_dist.values())
        a_mock = a_dist.get("has_mock", 0)
        other_mock = other_dist.get("has_mock", 0)
        a_pct = 100 * a_mock / a_total if a_total else 0.0
        other_pct = 100 * other_mock / other_total if other_total else 0.0
        return f"| {label} | {a_mock:,} | {a_pct:.1f}% | {other_mock:,} | {other_pct:.1f}% |"

    lines.append(_row("Overall", a.has_mock_dist, other.has_mock_dist))
    for language in RQ3_LANGUAGES:
        lines.append(
            _row(
                language,
                a.has_mock_dist_by_language.get(language, {}),
                other.has_mock_dist_by_language.get(language, {}),
            )
        )

    lines.append("")
    return "\n".join(lines)


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
    num_mocks -- see this module's docstring)."""
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


def _render_comparison(label: str, a: DatasetMetrics, other: DatasetMetrics) -> str:
    fixture_level = compare_datasets_fixture_level(a, other)
    repo_level = compare_datasets_repo_level(a, other)
    lines = [f"## {label}: {DATASET_LABELS['a']} vs {DATASET_LABELS[other.dataset]}", ""]

    lines += [
        "**Continuous metrics (Mann-Whitney U, two-sided)** -- num_mocks "
        "has no per-language family (not one of the metrics the paper "
        "review named), so it renders Overall-only, shown at both the "
        "fixture-level (every fixture as an observation) and repo-level "
        "(one mean value per repo) basis. "
        "Effect size is Cliff's delta (thresholds: negligible <0.147, small "
        "<0.33, medium <0.474, else large).",
        "",
    ]
    for metric in CONTINUOUS_METRICS:
        lines.append(
            _render_continuous_metric(metric, a, other, fixture_level[metric], repo_level[metric])
        )

    lines += ["### Mocking Coverage (paper table)", ""]
    lines.append(_render_mocking_summary_table(a, other))

    lines.append(_render_mock_counts_table(a, other))

    return "\n".join(lines)


def generate_report(*, db_root: Path = paths.DB_ROOT) -> str:
    loaded = {ds: load_dataset_metrics(ds, db_root=db_root) for ds in ("a", "c")}
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    lines = [
        "# RQ3 -- Mocking",
        "",
        "> How do agent-generated and human-written fixtures differ in mock "
        "usage -- coverage?",
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
