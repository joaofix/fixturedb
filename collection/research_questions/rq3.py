"""
RQ3 -- Mocking (Quantitative): how do agent-generated and human-written
fixtures differ in mock usage?

One paper table (`_render_mocking_summary_table()`), per language and
Overall: two repo-level metrics, both A vs C via Mann-Whitney U + Cliff's
delta (`compute_continuous_balance()`), both reusing the existing mock
detection logic completely unchanged (`fixtures.num_mocks`, already
computed and unmodified by this change):

- **Coverage**: for each repo, a binary indicator -- does it have >=1
  fixture with a mock at all (`num_mocks > 0`)? Population: every repo
  with >=1 fixture (of that language, for the per-language rows; any
  language, for Overall) -- reuses `has_mock_by_repo`/`has_mock_by_repo_
  and_language`, already fetched by the pre-existing has_mock detection
  query. "Coverage A/C (%)" is the share of that population with the
  indicator at 1 -- the mean of a 0/1 list *is* that percentage, so
  `compute_continuous_balance()`'s `agent_mean`/`human_mean` double as the
  column directly (same trick rq2.py's teardown-coverage table uses).
- **Intensity**: among repos WITH >=1 mocking fixture only (coverage=1;
  non-mocking repos are excluded from this metric entirely, not counted
  as 0), the median `fixtures.num_mocks` across that repo's own mocking
  fixtures (`num_mocks > 0` fixtures only within the repo -- its
  non-mocking fixtures don't pull the median toward 0). "Intensity A/C" is
  the median of those per-repo medians (`agent_median`/`human_median`
  from the same `compute_continuous_balance()` call the test itself uses).
  Fetched via a new `_fetch_num_mocks_by_repo_and_language()` (raw
  per-fixture `num_mocks`, grouped by repo and each fixture's own
  language) -- `_mocking_intensities_by_repo()` does the per-repo
  filter+median.

**n_A/n_C is coverage's own population size** (every repo with >=1
fixture, of that language/Overall) -- intensity's population is a strict
subset of this (mocking repos only), so intensity's true n can be smaller
than the row's stated n_A/n_C. One n column pair per row, not one per
metric; the table's intro text states this explicitly rather than leaving
it implicit.

Overall is one pooled, uncorrected test per metric (2 tests total:
coverage, intensity). **Both metrics' per-language tests are BH-FDR
corrected together as one combined 8-test family** (4 languages x 2
metrics), not two separate 4-test families -- both are RQ3 metrics
reported in the same table, so they share one family the same way this
whole package always treats "everything reported in one table" as one
correction family. Fixed four-language row order (java, javascript,
python, typescript) rather than the "languages present on both sides"
intersection convention some of this script's legacy tables (below) use
-- see rq2.py's module docstring for the identical simplification and why
it doesn't change real output (`compute_continuous_balance()` already
degrades a missing-on-one-side language to `insufficient_data` on its
own).

This table replaces three previously-reported tables:

- **Mock prevalence** (fixture-level `has_mock` chi-square, pooled + per
  language) -- kept, computed identically (mock detection logic
  untouched), moved to "## Legacy: Fixture-Level Mock Prevalence (Not
  Used in the Paper)" below the main comparison (it was already marked
  "not used in the paper" before this change -- fixture-level
  pseudo-replication, see docs/reference/limitations.md's "Categorical
  Pseudo-Replication"). The *repo-level* has_mock test that WAS reported
  in the paper (formerly "## Repo-level aggregates") is fully superseded
  by this table's Coverage column -- same statistic (per-repo has_mock
  indicator, Mann-Whitney + Cliff's delta), same population, now computed
  via `compute_continuous_balance()` directly instead of
  `compare_categorical_repo_level()` (a two-category proportion test on a
  binary variable is mathematically the mean-of-the-0/1-indicator test
  this table uses -- same number, cleaner path there).
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
  language/ecosystem-specific -- same 2026-08-12 fix). `category_dist`/
  `category_by_language`/`category_by_repo_and_language` fetches/fields
  are UNCHANGED and still populate the per-dataset summary above -- both
  the per-language repo-level-proportion test and the pooled descriptive
  table are gone from the report.

`num_mocks`/`num_interactions_configured`'s existing continuous Mann-
Whitney tables (fixture-level and repo-level, Overall-only) are
**unchanged** -- not one of the three tables named for replacement, and
conceptually distinct from Coverage/Intensity above (a repo-level *mean*
across every fixture including non-mocking ones, vs Intensity's *median
among mocking fixtures only*).

A vs C only -- Dataset B (contemporary within-repo human baseline) is still
collected (db/b.db) but out of scope for this script's reported
comparisons; see rq1.py's module docstring.

A dataset is skipped (not an error) if its db/{dataset}.db does not exist
yet.

python -m collection.research_questions.rq3
"""

from __future__ import annotations

import sqlite3
import statistics
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
    compute_language_leakage,
    compute_stratified_categorical_balance,
    continuous_effect_size_cell,
    fetch_categorical_column,
    fetch_continuous_column,
    fetch_continuous_column_by_repo,
    fmt,
    format_p_value,
    pct,
    render_comparison_table,
    render_language_leakage_table,
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
# 2026-08-12 (see module docstring). has_mock's chi-square is itself now
# legacy-only (see _render_legacy_mock_prevalence()) -- the paper table's
# Coverage column supersedes it.
CATEGORICAL_METRICS = ["has_mock", "framework", "category"]
TESTED_CATEGORICAL_METRICS = ["has_mock"]

# Fixed row order for the paper table -- see the module docstring for why
# this is a fixed list rather than the "languages present on both sides"
# intersection convention some of this script's other (legacy) tables use.
# Matches rq2.py's RQ2_LANGUAGES.
RQ3_LANGUAGES: tuple[str, ...] = ("java", "javascript", "python", "typescript")


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
    has_mock_by_repo_and_language: dict[str, dict[int, dict[str, int]]] = field(
        default_factory=dict
    )
    # Raw per-fixture num_mocks, grouped by repo (Overall) / (language,
    # repo) (per-language rows) -- feeds _mocking_intensities_by_repo()'s
    # per-repo median-among-mocking-fixtures computation for the paper
    # table's Intensity column. num_mocks_by_repo is exactly continuous_
    # by_repo["num_mocks"] from load_dataset_metrics() below, just also
    # kept on the dataclass instead of only its per-repo *mean*
    # (repo_level_continuous["num_mocks"]).
    num_mocks_by_repo: dict[int, list[float]] = field(default_factory=dict)
    num_mocks_by_repo_and_language: dict[str, dict[int, list[float]]] = field(
        default_factory=dict
    )


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
    category counts. No longer feeds a rendered table (the per-language
    category comparison was removed from the report -- see this module's
    docstring), kept as "raw data accessible" per that removal's own
    terms; still populates `category_by_repo_and_language` on
    DatasetMetrics for programmatic use."""
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


def _fetch_has_mock_by_repo_and_language(
    conn: sqlite3.Connection,
) -> dict[str, dict[int, dict[str, int]]]:
    """{language: {repo_id: {"has_mock": n, "no_mock": n}}} -- has_mock's
    per-(language, repo) analogue of _fetch_category_by_repo_and_language().
    Feeds two things: the legacy per-language chi-square family
    (`has_mock_dist_by_language` is a different, pooled fetch -- see
    below), and, via `_mocking_coverage_indicators()`, the paper table's
    Coverage column (each repo's own has_mock/no_mock counts collapse to
    a single 0/1 "has any mock at all" indicator there). Grouped by each
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


def _fetch_num_mocks_by_repo_and_language(
    conn: sqlite3.Connection,
) -> dict[str, dict[int, list[float]]]:
    """{language: {repo_id: [num_mocks, ...]}} -- every fixture's own raw
    `fixtures.num_mocks` (zero included), grouped by repo and each
    fixture's own language (test_files.language), not the repo's tag --
    same per-language convention as _fetch_has_mock_by_repo_and_language().
    Feeds the paper table's Intensity column
    (`_mocking_intensities_by_repo()` does the per-repo filter-to-mocking-
    fixtures-only + median downstream of this -- this fetch itself doesn't
    filter, so the same raw list could in principle feed a different
    per-repo aggregation later without a second query)."""
    rows = conn.execute(
        "SELECT tf.language, f.repo_id, f.num_mocks FROM fixtures f "
        "JOIN test_files tf ON f.file_id = tf.id WHERE f.num_mocks IS NOT NULL"
    ).fetchall()
    result: dict[str, dict[int, list[float]]] = {}
    for language, repo_id, num_mocks in rows:
        result.setdefault(language, {}).setdefault(repo_id, []).append(num_mocks)
    return result


def _fetch_fixture_repo_count_by_language(conn: sqlite3.Connection) -> dict[str, int]:
    """Distinct repo count per language, among ALL fixtures -- the n_A/n_C
    denominator for has_mock's legacy per-language chi-square rows: every
    repo with a fixture of that language, not just ones with a mock."""
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
        has_mock_by_repo_and_language = _fetch_has_mock_by_repo_and_language(conn)
        num_mocks_by_repo_and_language = _fetch_num_mocks_by_repo_and_language(conn)
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
        has_mock_by_repo_and_language=has_mock_by_repo_and_language,
        num_mocks_by_repo=num_mocks_by_repo,
        num_mocks_by_repo_and_language=num_mocks_by_repo_and_language,
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


# ---------------------------------------------------------------------------
# Paper table: mocking coverage + intensity -- see this module's docstring
# for the full methodology.
# ---------------------------------------------------------------------------


def _mocking_coverage_indicators(by_repo: dict[int, dict[str, int]]) -> list[float]:
    """Per-repo binary indicator: 1.0 if that repo has >=1 fixture with a
    mock (has_mocking), else 0.0. `by_repo` is has_mock_by_repo(_and_
    language)'s shape ({repo_id: {"has_mock": n, "no_mock": n}}) -- every
    entry already represents a repo with >=1 fixture (built from fixtures
    with num_mocks IS NOT NULL), so no extra zero-total filter is needed
    here the way rq2.py's teardown-coverage indicator needs one."""
    return [1.0 if counts.get("has_mock", 0) > 0 else 0.0 for counts in by_repo.values()]


def _mocking_intensities_by_repo(num_mocks_by_repo: dict[int, list[float]]) -> list[float]:
    """Per-repo mocking intensity: median num_mocks among that repo's own
    mocking fixtures only (num_mocks > 0) -- repos with no mocking
    fixtures at all are excluded entirely (not a 0), matching Coverage's
    has_mocking=1 population restriction for this metric. `num_mocks_by_
    repo` is num_mocks_by_repo(_and_language)'s shape ({repo_id:
    [num_mocks, ...]}, every fixture's own value, zeros included --
    filtering to mocking fixtures only happens here, per repo)."""
    intensities = []
    for values in num_mocks_by_repo.values():
        mocking_values = [v for v in values if v > 0]
        if mocking_values:
            intensities.append(statistics.median(mocking_values))
    return intensities


def _render_mocking_row(
    label: str,
    coverage_test: BalanceTest,
    intensity_test: BalanceTest,
    n: NCounts,
    *,
    corrected: bool,
) -> str:
    """One row: Coverage A/C (%) from coverage_test's agent_mean/human_mean
    (mean of a 0/1 list = that percentage), Intensity A/C from
    intensity_test's agent_median/human_median. `corrected` selects
    between each test's own raw p (Overall, single pooled tests) and its
    BH-adjusted p (per-language rows -- both metrics' tests already
    corrected together as one combined family before this is called, see
    _render_mocking_summary_table())."""

    def _p_cell(test: BalanceTest) -> str:
        d = test.details
        if corrected:
            return format_p_value(d["adjusted_p_value"])
        return format_p_value(test.p_value)

    cov_d = coverage_test.details
    if cov_d.get("reason") == "insufficient_data" or "error" in cov_d:
        coverage_cells = "-- | -- | -- | --"
    else:
        coverage_cells = (
            f"{pct(cov_d.get('agent_mean'))} | {pct(cov_d.get('human_mean'))} | "
            f"{continuous_effect_size_cell(coverage_test)} | {_p_cell(coverage_test)}"
        )

    int_d = intensity_test.details
    if int_d.get("reason") == "insufficient_data" or "error" in int_d:
        intensity_cells = "-- | -- | -- | --"
    else:
        intensity_cells = (
            f"{fmt(int_d.get('agent_median'))} | {fmt(int_d.get('human_median'))} | "
            f"{continuous_effect_size_cell(intensity_test)} | {_p_cell(intensity_test)}"
        )

    return f"| {label} | {n.n_a} | {n.n_c} | {coverage_cells} | {intensity_cells} |"


def _render_mocking_summary_table(a: DatasetMetrics, other: DatasetMetrics) -> str:
    """The paper table: per-language + Overall mocking coverage (%) and
    mocking intensity (median mock calls per mocking fixture), each its
    own Mann-Whitney U + Cliff's delta test. See this module's docstring
    for the full methodology, including the combined 8-test BH-FDR
    family and the n_A/n_C-is-coverage's-population caveat."""
    other_label = other.dataset.upper()
    lines = [
        "**Coverage** = % of repos with >=1 fixture containing a mock at "
        "all (population: every repo with >=1 fixture, of that language "
        "for the per-language rows). **Intensity** = median `num_mocks` "
        "across a repo's own mocking fixtures (`num_mocks > 0` only), "
        "then the median of those per-repo values across repos -- "
        "**computed only over repos where Coverage = 1**; non-mocking "
        "repos are excluded from Intensity entirely, not counted as 0. "
        "n_A/n_C is Coverage's population size for that row -- Intensity's "
        "true n can be smaller, since it's a strict subset (mocking repos "
        "only); this table has one n column pair per row, not one per "
        "metric. Both effect sizes are Cliff's delta from a Mann-Whitney U "
        "test on the underlying per-repo values (binary for coverage, the "
        "per-repo median for intensity). Overall is two single pooled "
        "tests (raw p, never BH-corrected). Each language's coverage AND "
        "intensity tests (8 tests: 4 languages x 2 metrics) are BH-FDR "
        "corrected together as one combined family, not two separate "
        "4-test families -- both are RQ3 metrics reported in this same "
        "table.",
        "",
        f"| Language | n_A | n_{other_label} | Coverage A (%) | Coverage {other_label} (%) | "
        f"δ_cov | p_cov | Intensity A | Intensity {other_label} | δ_int | p_int |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]

    overall_coverage = compute_continuous_balance(
        human_values=_mocking_coverage_indicators(other.has_mock_by_repo),
        agent_values=_mocking_coverage_indicators(a.has_mock_by_repo),
        variable="mocking_coverage_overall",
    )
    overall_intensity = compute_continuous_balance(
        human_values=_mocking_intensities_by_repo(other.num_mocks_by_repo),
        agent_values=_mocking_intensities_by_repo(a.num_mocks_by_repo),
        variable="mocking_intensity_overall",
    )
    overall_n = NCounts(len(a.has_mock_by_repo), len(other.has_mock_by_repo))
    lines.append(
        _render_mocking_row("Overall", overall_coverage, overall_intensity, overall_n, corrected=False)
    )

    coverage_tests: dict[str, BalanceTest] = {}
    intensity_tests: dict[str, BalanceTest] = {}
    per_language_n: dict[str, NCounts] = {}
    for language in RQ3_LANGUAGES:
        a_cov_by_repo = a.has_mock_by_repo_and_language.get(language, {})
        other_cov_by_repo = other.has_mock_by_repo_and_language.get(language, {})
        coverage_tests[language] = compute_continuous_balance(
            human_values=_mocking_coverage_indicators(other_cov_by_repo),
            agent_values=_mocking_coverage_indicators(a_cov_by_repo),
            variable=f"mocking_coverage_{language}",
        )
        a_num_mocks_by_repo = a.num_mocks_by_repo_and_language.get(language, {})
        other_num_mocks_by_repo = other.num_mocks_by_repo_and_language.get(language, {})
        intensity_tests[language] = compute_continuous_balance(
            human_values=_mocking_intensities_by_repo(other_num_mocks_by_repo),
            agent_values=_mocking_intensities_by_repo(a_num_mocks_by_repo),
            variable=f"mocking_intensity_{language}",
        )
        per_language_n[language] = NCounts(len(a_cov_by_repo), len(other_cov_by_repo))

    # Explicit request: both metrics' 4 per-language tests share ONE
    # combined 8-test BH-FDR family, not two separate 4-test families.
    combined = {f"{language}__coverage": coverage_tests[language] for language in RQ3_LANGUAGES}
    combined.update(
        {f"{language}__intensity": intensity_tests[language] for language in RQ3_LANGUAGES}
    )
    corrected = apply_fdr_correction(combined)

    for language in RQ3_LANGUAGES:
        lines.append(
            _render_mocking_row(
                language,
                corrected[f"{language}__coverage"],
                corrected[f"{language}__intensity"],
                per_language_n[language],
                corrected=True,
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


def _render_comparison(label: str, a: DatasetMetrics, other: DatasetMetrics) -> str:
    fixture_level = compare_datasets_fixture_level(a, other)
    repo_level = compare_datasets_repo_level(a, other)
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

    lines += ["### Mocking Coverage and Intensity (paper table)", ""]
    lines.append(_render_mocking_summary_table(a, other))

    return "\n".join(lines)


def _render_legacy_mock_prevalence(label: str, a: DatasetMetrics, other: DatasetMetrics) -> str:
    """Fixture-level has_mock chi-square (pooled + per language) -- kept
    for transparency/comparison only, not one of RQ3's reported tables.
    Already fixture-level pseudo-replicated (every fixture treated as an
    independent observation, though fixtures cluster within repos) before
    this table existed -- see this module's docstring and
    [Limitations § Categorical Pseudo-Replication](../docs/reference/
    limitations.md#categorical-pseudo-replication). The repo-level
    `has_mock` result that WAS reported in the paper is superseded by
    _render_mocking_summary_table()'s Coverage column above, not shown
    here."""
    categorical_overall = compare_datasets_categorical(a, other)
    lines = [
        f"### {label}: {DATASET_LABELS['a']} vs {DATASET_LABELS[other.dataset]}",
        "",
        '**has_mock (chi-square)** -- an "Overall" row (single pooled '
        "test, not BH-corrected) plus one BH-corrected row per language "
        "(one family, 4 languages -- see render_comparison_table()'s "
        "docstring in _shared.py). Effect size is Cramer's V (thresholds: "
        "negligible <0.1, small <0.3, medium <0.5, else large).",
        "",
    ]
    lines.append(_render_has_mock(a, other, categorical_overall["has_mock"]))
    return "\n".join(lines)


def generate_report(*, db_root: Path = paths.DB_ROOT) -> str:
    loaded = {ds: load_dataset_metrics(ds, db_root=db_root) for ds in ("a", "c")}
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    lines = [
        "# RQ3 -- Mocking",
        "",
        "> How do agent-generated and human-written fixtures differ in mock "
        "usage -- coverage and intensity?",
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
        "## Legacy: Fixture-Level Mock Prevalence (Not Used in the Paper)",
        "",
        "Kept for transparency/comparison only -- not one of RQ3's "
        "reported tables. Pooled + per-language fixture-level `has_mock` "
        "chi-square, already flagged as repo-level pseudo-replication "
        "(every fixture treated as an independent observation, though "
        "fixtures cluster within repos) before the table above existed "
        "-- see [Limitations § Categorical Pseudo-Replication](../docs/"
        "reference/limitations.md#categorical-pseudo-replication). The "
        "paper's actual mocking-coverage result is the Coverage column in "
        "the main table above, computed at the repo level directly.",
        "",
    ]
    if a_metrics is None:
        lines.append("_Dataset A not available -- no legacy comparisons computed._")
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
                lines.append(_render_legacy_mock_prevalence(label, a_metrics, other_metrics))

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
