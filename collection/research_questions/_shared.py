"""Helpers shared across collection/research_questions/ scripts (rq1.py,
rq2.py, rq3.py, language_contamination.py) -- kept here once instead of
duplicated per-script, per this package's convention: leverage
already-collected data first, import logic from collection/ second, write
new logic only as a last resort (and then, only once).
"""

from __future__ import annotations

import sqlite3
import statistics
from dataclasses import dataclass, field, replace
from pathlib import Path

import diptest
import numpy as np
from scipy.stats import false_discovery_control

from ..between_group_comparison import (
    BalanceTest,
    compute_categorical_balance,
    compute_continuous_balance,
)
from ..config import ROOT_DIR
from ..logging_utils import get_logger
from ..paths import DB_ROOT, db_path

logger = get_logger(__name__)

OUTPUT_DIR = ROOT_DIR / "research_questions"

DATASET_LABELS = {
    "a": "Dataset A (agent-authored)",
    "b": "Dataset B (human-authored, contemporary)",
    "c": "Dataset C (human-authored, pre-LLM)",
}

# (dataset compared against A, comparison label). Dataset B (contemporary
# within-repo human baseline) is still collected (db/b.db, paired_collection.py)
# but intentionally excluded here -- these scripts only ever report A vs C now.
COMPARISONS = [("c", "A vs C")]

# Java fixture_types detected on a field_declaration, not a method/function --
# @Rule/@ClassRule (detector_java.py). Lizard's function-based analysis
# structurally cannot find a "function" in a bare field declaration (verified
# directly: feeding lizard.analyze_file() a `@Rule public X y = new X();`
# snippet returns an empty function_list every time, even when the
# initializer contains real branching logic), so cyclomatic_complexity and
# num_parameters silently fall back to analyze_function_complexity()'s
# hardcoded defaults (1 and 0) rather than a real measurement -- correct by
# coincidence for the ~99-100% of these that are a plain `new X(...)`
# initializer, but not an actual analysis. loc/max_nesting_depth remain
# genuinely measured (not Lizard-derived), but represent a structurally
# different code unit (a field, not a function body) than every other
# fixture_type in any language this project extracts from -- pooling them
# into the same LOC/CC/nesting_depth comparison mixes two different kinds of
# "fixture." rq1.py excludes this set from those three continuous-metric
# comparisons (repo-level and per-language) while keeping it in
# fixture_type/scope categorical distributions, where "this repo declared N
# JUnit Rules" is still a meaningful, correctly-measured fact. A single
# shared constant (not hardcoded per-caller) so any future script needing
# the same exclusion filters consistently instead of re-deriving or
# duplicating this list. See
# internal-docs/methodology-improvements/junit-rule-fixtures.md for the
# full investigation this constant came out of.
NO_BODY_FIXTURE_TYPES = {"junit_rule", "junit_class_rule"}


def require_db_or_none(dataset: str, db_root: Path = DB_ROOT) -> Path | None:
    """db/{dataset}.db's path, or None (with a warning logged) if it doesn't
    exist yet -- the shared "skip, don't error" convention every rqN.py
    script uses so it can run against whatever subset of A/B/C is collected.

    Dataset "c" is a hard exception: this resolves to db/c_sampled.db, never
    the full db/c.db. The full Dataset C is ~3.3x Dataset A's size, and
    running the RQ comparisons against that imbalance is methodologically
    unsound -- see `python -m collection sample-c-repos`
    (collection/dataset_pipeline.py::sample_dataset_c_repos()), which builds
    c_sampled.db from a random, language-stratified, whole-repo sample sized
    to match Dataset A. If c_sampled.db doesn't exist yet, this behaves
    exactly like any other missing DB (warn, return None, dataset skipped) --
    there is deliberately no fallback to the full db/c.db here, in any
    circumstance. This substitution only applies within research_questions/
    -- db/c.db itself is untouched and still used normally by collection,
    export/validate/summarize, and analyze-distribution."""
    if dataset == "c":
        db_file = db_root / "c_sampled.db"
    else:
        db_file = db_path(dataset, root=db_root)
    if not db_file.exists():
        logger.warning(f"{db_file} not found; skipping dataset {dataset!r}")
        return None
    return db_file


def summarize_continuous(values: list[float]) -> dict:
    if not values:
        return {"n": 0, "mean": None, "median": None, "min": None, "max": None, "stdev": None}
    return {
        "n": len(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "min": min(values),
        "max": max(values),
        "stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
    }


def run_dip_test(values: list[float]) -> dict | None:
    """Hartigan & Hartigan's (1985) dip test for unimodality, via the
    `diptest` package (Cython port of the original Fortran/C algorithm --
    exact tabulated critical values by default, not a bootstrap p-value,
    so this is deterministic: no seed needed, reruns always agree).

    Null hypothesis: the distribution is unimodal. The alternative is
    multimodal (at least bimodal) -- a low p-value is evidence *against*
    unimodality. This is a single-distribution shape diagnostic, not a
    between-group comparison -- run it once per dataset/group, not on a
    combined sample.

    Returns None (not a crash, not a 0/1 result) for fewer than 4 values
    -- the library's own diptest() warns "Dip test is not valid for n <=
    3" at that size, so this mirrors summarize_continuous()'s "too little
    data" convention rather than reporting a number that isn't
    meaningful. Otherwise {"n", "dip_statistic", "p_value"}."""
    if len(values) <= 3:
        return None
    dip_statistic, p_value = diptest.diptest(np.asarray(values, dtype=float))
    return {"n": len(values), "dip_statistic": float(dip_statistic), "p_value": float(p_value)}


def render_ascii_histogram(
    values: list[float],
    *,
    n_bins: int = 10,
    bar_width: int = 40,
    value_range: tuple[float, float] = (0.0, 1.0),
) -> str:
    """Fixed-width-bar text histogram of `values` over `value_range`
    (default 0..1, for proportions like teardown_pct) as a fenced code
    block, so bar alignment survives markdown rendering. research_questions/
    reports are plain markdown with no image pipeline, so this renders the
    distribution's shape inline instead of needing a separate PNG file and
    a path for the report to reference.

    Values outside `value_range` clamp into the nearest edge bin rather
    than being dropped, so every input value is always represented in
    the total count."""
    if not values:
        return "_(no data)_"
    lo, hi = value_range
    bin_width = (hi - lo) / n_bins
    counts = [0] * n_bins
    for v in values:
        idx = int((v - lo) / bin_width) if v < hi else n_bins - 1
        idx = max(0, min(idx, n_bins - 1))
        counts[idx] += 1

    max_count = max(counts)
    lines = ["```"]
    for i, count in enumerate(counts):
        bin_lo = lo + i * bin_width
        bin_hi = bin_lo + bin_width
        bar_len = round(bar_width * count / max_count) if max_count else 0
        bar = "#" * bar_len
        lines.append(f"{bin_lo:5.2f}-{bin_hi:5.2f} | {bar} ({count})")
    lines.append("```")
    return "\n".join(lines)


def fmt(value: float | None, digits: int = 2) -> str:
    return "--" if value is None else f"{value:.{digits}f}"


def pct(value: float | None, digits: int = 1) -> str:
    """`value` (a 0..1 proportion) as a percentage string, e.g. "72.3%" --
    "--" (no "%") if `value` is None, same missing-data convention as fmt()."""
    return "--" if value is None else f"{100 * value:.{digits}f}%"


def format_p_value(p: float) -> str:
    """Exact p-value for a table cell -- "<.001" below that threshold
    (matches conventional reporting style: below the display precision, an
    exact figure like "0.0003" implies false precision), else 3 decimals
    (e.g. "0.031"). Replaces every "significant (p<0.05)" yes/no column
    and every f"{p:.4g}"-style call across rq1.py/rq2.py/rq3.py -- a paper
    reviewer wants the actual p-value, not just a pass/fail against an
    arbitrary alpha."""
    return "<.001" if p < 0.001 else f"{p:.3f}"


@dataclass(frozen=True)
class NCounts:
    """Repo counts feeding one comparison test -- always COUNT(DISTINCT
    repo_id) among the rows that actually fed *this specific test*, never
    a fixture/mock count, even when the test itself is fixture-level.
    That's deliberate: showing the real repo population behind even a
    fixture-level chi-square is exactly the context a reader needs to
    judge pseudo-replication risk themselves (see docs/reference/
    limitations.md's "Categorical Pseudo-Replication")."""

    n_a: int
    n_c: int


def apply_fdr_correction(tests: dict[str, BalanceTest]) -> dict[str, BalanceTest]:
    """Benjamini-Hochberg FDR correction across `tests` -- one "family" of
    related hypotheses tested together (e.g. every RQ1 metric in one A-vs-B
    comparison, or every language in one stratified breakdown).

    Why this exists: each RQ script runs many hypothesis tests (RQ1 alone
    is 9 per comparison -- 6 continuous + 3 categorical -- times 2
    comparisons, before today's per-language stratification multiplied
    that further). At uncorrected alpha=0.05, some fraction of "significant"
    results are expected by chance alone as the test count grows. BH-FDR
    (via scipy's false_discovery_control, the standard choice here --
    Bonferroni is needlessly conservative for this many related,
    non-independent tests) controls the expected proportion of false
    positives among the tests flagged significant, without scipy's
    documented, harsher family-wise-error alternatives.

    Tests with no real p-value (insufficient_data/error) pass through
    unchanged -- they were never really "tested" and have nothing to
    correct. Returns NEW BalanceTest objects (dataclasses.replace) with
    `adjusted_p_value`/`significant_after_correction` added to `details`;
    the original `p_value`/`is_balanced` fields are left untouched, so
    both the raw and corrected verdicts stay visible.

    A test excluded here (no `adjusted_p_value` added) must be one every
    `_row()`-style renderer across rq1-3/balance.py already treats as
    "not really tested" and skips before reading `adjusted_p_value` --
    currently `reason="insufficient_data"` (compute_continuous_balance()/
    compute_categorical_balance() when one side has no data at all -- a
    placeholder p_value=1.0, no real statistic) or `"error" in details`.
    `reason="identical_distributions"` (both sides' values are one single,
    equal value -- e.g. two repos each 100% teardown) is deliberately
    *not* excluded: unlike insufficient_data, it's a fully computed real
    result (p_value=1.0, cliffs_delta=0.0, real medians) that just took a
    shortcut past the Mann-Whitney call -- BH-correctable like any other
    p_value, and every renderer's own "skip this row" guard already only
    checks for insufficient_data/error specifically, so leaving it out
    here left it with no `adjusted_p_value` for those renderers' `corrected`
    branch to read -- a real, previously-latent KeyError, not just here."""
    testable_keys = [
        k
        for k, t in tests.items()
        if t.details.get("reason") != "insufficient_data" and "error" not in t.details
    ]
    result = dict(tests)
    if not testable_keys:
        return result

    p_values = [tests[k].p_value for k in testable_keys]
    adjusted = false_discovery_control(p_values, method="bh")

    for key, adj_p in zip(testable_keys, adjusted):
        t = tests[key]
        result[key] = replace(
            t,
            details={
                **t.details,
                "adjusted_p_value": float(adj_p),
                "significant_after_correction": bool(adj_p < 0.05),
            },
        )
    return result


def fdr_cell(t: BalanceTest) -> str:
    """BH-FDR-adjusted p-value + verdict, formatted for one table cell --
    '--' if apply_fdr_correction() wasn't run on this test (or it was
    insufficient_data/error to begin with)."""
    adj_p = t.details.get("adjusted_p_value")
    if adj_p is None:
        return "--"
    sig = "yes" if t.details.get("significant_after_correction") else "no"
    return f"{adj_p:.4g} ({sig})"


def compute_stratified_categorical_balance(
    a_dist_by_language: dict[str, dict[str, int]],
    other_dist_by_language: dict[str, dict[str, int]],
    variable: str,
) -> dict[str, BalanceTest]:
    """Per-language chi-square balance test, restricted to languages with
    data on both sides.

    Why this matters: an aggregate (dataset-wide) categorical comparison
    can look "significant" purely because the two datasets have different
    language mixes -- e.g. Dataset B is far more python-heavy than Dataset
    A, and python fixtures behave differently from java/js/ts ones on
    several RQ2/RQ3 metrics regardless of authorship. Stratifying by
    language isolates whether a difference holds *within* a language, not
    just in the aggregate. See docs/research-questions.md and the
    2026-07-31 RQ1-3 findings review in this session's history for the
    concrete cases this caught (RQ2 teardown-kind distribution, RQ3 mock
    prevalence).
    """
    results: dict[str, BalanceTest] = {}
    for language in sorted(set(a_dist_by_language) & set(other_dist_by_language)):
        results[language] = compute_categorical_balance(
            human_dist=other_dist_by_language[language],
            agent_dist=a_dist_by_language[language],
            variable=f"{variable}_{language}",
        )
    return results


def compute_stratified_continuous_balance(
    a_values_by_language: dict[str, list[float]],
    other_values_by_language: dict[str, list[float]],
    variable: str,
) -> dict[str, BalanceTest]:
    """Per-language Mann-Whitney U + Cliff's delta, restricted to languages
    with data on both sides -- continuous analogue of
    compute_stratified_categorical_balance() above (same rationale: a
    pooled comparison can look significant purely because the two datasets
    have different language mixes; this checks whether the difference
    holds *within* a language). `a_values_by_language`/
    `other_values_by_language` are typically repo-level (one value per
    repo per language, e.g. from repo_level_means() grouped by language)
    rather than raw per-fixture values, so this doesn't reintroduce the
    fixture-clustering pseudo-replication repo_level_means() exists to fix
    -- see render_comparison_table()'s docstring for where this is used."""
    results: dict[str, BalanceTest] = {}
    for language in sorted(set(a_values_by_language) & set(other_values_by_language)):
        results[language] = compute_continuous_balance(
            human_values=other_values_by_language[language],
            agent_values=a_values_by_language[language],
            variable=f"{variable}_{language}",
        )
    return results


def categorical_effect_size_cell(t: BalanceTest) -> str:
    """Cramér's V + magnitude, formatted for one table cell -- '--' if the
    test didn't run (insufficient_data/error). p-values shrink with sample
    size alone; this is what actually says how big the difference is."""
    v = t.details.get("cramers_v")
    if v is None:
        return "--"
    return f"{v:.3f} ({t.details.get('cramers_v_magnitude', '?')})"


def continuous_effect_size_cell(t: BalanceTest) -> str:
    """Cliff's delta + magnitude, formatted for one table cell -- '--' if
    the test didn't run (insufficient_data/error)."""
    delta = t.details.get("cliffs_delta")
    if delta is None:
        return "--"
    return f"{delta:.3f} ({t.details.get('cliffs_delta_magnitude', '?')})"


def _statistic_cell(t: BalanceTest) -> str:
    """`t.statistic` labeled by which test produced it -- one column serves
    both Mann-Whitney U and chi-square (with its degrees of freedom)
    tests, since render_comparison_table() is metric-agnostic."""
    if t.statistic is None:
        return "--"
    if t.test_type == "chi-square":
        dof = t.details.get("degrees_of_freedom", "--")
        return f"chi2={fmt(t.statistic, 1)} (df={dof})"
    return f"U={fmt(t.statistic, 1)}"


def _effect_size_value_cell(t: BalanceTest) -> str:
    """The raw effect-size number (Cramer's V or Cliff's delta) alone --
    magnitude is a separate column, see _effect_size_magnitude_cell()."""
    if t.test_type == "chi-square":
        return fmt(t.details.get("cramers_v"), 3)
    return fmt(t.details.get("cliffs_delta"), 3)


def _effect_size_magnitude_cell(t: BalanceTest) -> str:
    """negligible/small/medium/large label for _effect_size_value_cell()'s
    number -- see _cramers_v_magnitude()/_cliffs_delta_magnitude() in
    between_group_comparison.py for the exact thresholds."""
    if t.test_type == "chi-square":
        return t.details.get("cramers_v_magnitude") or "--"
    return t.details.get("cliffs_delta_magnitude") or "--"


def _comparison_row(label: str, t: BalanceTest, n: NCounts, *, corrected: bool) -> str:
    """One row of render_comparison_table() -- n columns are always shown
    (computable independently of whether the test itself could run);
    Statistic/effect-size/p columns fall back to an insufficient_data/
    test-failed marker matching the reasons documented on
    compute_categorical_balance()/compute_continuous_balance() themselves."""
    d = t.details
    if d.get("reason") == "insufficient_data":
        return f"| {label} | {n.n_a} | {n.n_c} | -- | -- | _insufficient data_ | -- | -- |"
    if "error" in d:
        # compute_categorical_balance() catches chi2_contingency failures
        # (e.g. a whole category at 0 on both sides -- a zero expected-
        # frequency cell) and returns p_value=1.0/is_balanced=True as a
        # safe default so callers never crash on it. That default reads as
        # a real "not significant" result if rendered plainly here, which
        # is actively misleading -- it means the test couldn't run at all.
        return f"| {label} | {n.n_a} | {n.n_c} | -- | -- | _test failed ({d['error']})_ | -- | -- |"
    p_adj = "--"
    if corrected:
        adj_p = d.get("adjusted_p_value")
        if adj_p is not None:
            p_adj = format_p_value(adj_p)
    return (
        f"| {label} | {n.n_a} | {n.n_c} | {_statistic_cell(t)} | "
        f"{_effect_size_value_cell(t)} | {_effect_size_magnitude_cell(t)} | "
        f"{format_p_value(t.p_value)} | {p_adj} |"
    )


def render_comparison_table(
    overall: BalanceTest,
    overall_n: NCounts,
    per_language: dict[str, BalanceTest] | None,
    per_language_n: dict[str, NCounts] | None,
    *,
    other_dataset: str,
) -> str:
    """The one table every A-vs-C comparison in rq1.py/rq2.py/rq3.py
    renders through: `| Language | n_A | n_<other> | Statistic | Effect
    size value | Magnitude | p (raw) | p (BH-adj) |`.

    "Overall" is always the first row -- `overall`'s own raw p-value,
    never BH-corrected (a single pooled test needs no multiple-comparison
    correction), so its "p (BH-adj)" cell is always "--".

    If `per_language` is given, applies apply_fdr_correction() to it here
    -- one family = exactly this variable's per-language tests, nothing
    else (not the Overall row, not other variables' tests) -- and adds one
    row per language (sorted alphabetically), each with its own raw + BH-
    adjusted p. If `per_language` is None, the table is Overall-only (this
    metric has no per-language family defined for it -- e.g. RQ1's
    commit_type, RQ3's num_mocks/num_interactions_configured).

    Branches on `t.test_type` ("mann-whitney-u" -> U statistic + Cliff's
    delta; "chi-square" -> chi2(df) + Cramer's V) via _statistic_cell()/
    _effect_size_*_cell() so one function serves every metric in every
    script, continuous or categorical alike -- BalanceTest already carries
    which kind it is, no extra parameter needed.
    """
    lines = [
        f"| Language | n_A | n_{other_dataset.upper()} | Statistic | "
        "Effect size value | Magnitude | p (raw) | p (BH-adj) |",
        "|---|---|---|---|---|---|---|---|",
        _comparison_row("Overall", overall, overall_n, corrected=False),
    ]
    if per_language:
        corrected = apply_fdr_correction(per_language)
        for language in sorted(corrected):
            lines.append(
                _comparison_row(
                    language, corrected[language], per_language_n[language], corrected=True
                )
            )
    lines.append("")
    return "\n".join(lines)


def fetch_continuous_column(conn: sqlite3.Connection, table: str, column: str) -> list[float]:
    """All non-null values of `column` in `table` -- e.g. fixtures.loc,
    mock_usages.num_interactions_configured. `table`/`column` are always
    developer-supplied constants, never user input."""
    rows = conn.execute(f"SELECT {column} FROM {table} WHERE {column} IS NOT NULL").fetchall()
    return [row[0] for row in rows]


def fetch_categorical_column(conn: sqlite3.Connection, table: str, column: str) -> dict[str, int]:
    """Value -> count of `column` in `table`, non-null values only."""
    rows = conn.execute(
        f"SELECT {column}, COUNT(*) FROM {table} WHERE {column} IS NOT NULL GROUP BY {column}"
    ).fetchall()
    return {row[0]: row[1] for row in rows}


def fetch_categorical_column_by_repo(
    conn: sqlite3.Connection, table: str, column: str
) -> dict[int, dict[str, int]]:
    """{repo_id: {category: count}} for `column` in `table`, non-null
    values only -- the per-repo grouping repo_level_category_proportions()
    needs. Categorical analogue of fetch_continuous_column_by_repo() below."""
    rows = conn.execute(
        f"SELECT repo_id, {column}, COUNT(*) FROM {table} "
        f"WHERE {column} IS NOT NULL GROUP BY repo_id, {column}"
    ).fetchall()
    by_repo: dict[int, dict[str, int]] = {}
    for repo_id, category, count in rows:
        by_repo.setdefault(repo_id, {})[category] = count
    return by_repo


def fetch_continuous_column_by_repo(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    *,
    exclude_fixture_types: set[str] | None = None,
) -> dict[int, list[float]]:
    """{repo_id: [values]} for `column` in `table`, non-null values only --
    the per-repo grouping repo_level_means() needs.

    exclude_fixture_types, when given, adds `fixture_type NOT IN (...)` to
    the query -- `table` must have a fixture_type column (i.e. be
    "fixtures") when this is passed; callers against other tables (e.g.
    rq3.py's mock_usages calls) must leave it None. Exists for
    NO_BODY_FIXTURE_TYPES (see its own docstring) -- a general opt-in filter
    rather than something baked into the query unconditionally, since most
    callers/columns have no reason to exclude anything.
    """
    params: tuple = ()
    where = f"{column} IS NOT NULL"
    if exclude_fixture_types:
        placeholders = ", ".join("?" for _ in exclude_fixture_types)
        where += f" AND fixture_type NOT IN ({placeholders})"
        params = tuple(exclude_fixture_types)
    rows = conn.execute(
        f"SELECT repo_id, {column} FROM {table} WHERE {where}", params
    ).fetchall()
    by_repo: dict[int, list[float]] = {}
    for repo_id, value in rows:
        by_repo.setdefault(repo_id, []).append(value)
    return by_repo


def repo_level_means(by_repo: dict[int, list[float]]) -> list[float]:
    """One mean value per repo, from fetch_continuous_column_by_repo()'s
    output -- declusters a fixture-level metric so a Mann-Whitney U test on
    this instead of the raw per-fixture values treats each *repo* as one
    observation, not each fixture.

    Why this matters: fixtures cluster within repos -- they share authorship
    conventions, framework choices, project style. Treating every fixture
    as independent (as the plain fixture-level tests elsewhere in this
    package do) understates true variance and inflates apparent
    significance, a classic pseudo-replication problem. This doesn't
    replace the fixture-level tests (they answer a real, different
    question -- "is the typical fixture different" -- at a finer grain
    this can't see), it's a complementary, more conservative view: "is the
    typical *repo* different," immune to a handful of unusually prolific
    repos dominating the fixture-level result.
    """
    return [sum(vals) / len(vals) for vals in by_repo.values() if vals]


def repo_level_category_proportions(
    by_repo: dict[int, dict[str, int]], category: str
) -> list[float]:
    """One proportion value per repo (this category's count / total
    classified count in that repo), from fetch_categorical_column_by_repo()'s
    output -- repos with zero classified rows for this variable are
    skipped (an empty ratio, not a 0.0 one). Categorical analogue of
    repo_level_means(): feeds compute_continuous_balance() so a
    Mann-Whitney U + Cliff's delta test treats each *repo* as one
    observation instead of each fixture/mock -- see
    compare_categorical_repo_level()'s docstring for why chi-square on raw
    counts needs this same fix."""
    return [
        counts.get(category, 0) / total
        for counts in by_repo.values()
        if (total := sum(counts.values()))
    ]


def compare_categorical_repo_level(
    a_by_repo: dict[int, dict[str, int]],
    other_by_repo: dict[int, dict[str, int]],
    variable: str,
) -> dict[str, BalanceTest]:
    """Per-category Mann-Whitney U + Cliff's delta on repo-level
    proportions -- one BalanceTest per category seen on either side (union).

    Why this exists: a plain chi-square on fixture/mock-level counts (as
    compute_categorical_balance() runs elsewhere in this package) treats
    every row as an independent draw, but rows cluster within repos --
    they share a framework choice, a team convention, a codebase. A repo
    contributing hundreds of correlated rows is effectively one
    independent observation, not hundreds; treating it as hundreds
    inflates the chi-square statistic and partially corrupts Cramer's V
    (which normalizes by n, and n is inflated by the same clustering).
    This computes, per repo, what fraction of its classified rows fall in
    each category, then compares those per-repo proportions between
    groups with Mann-Whitney -- the same de-clustering repo_level_means()
    already applies to RQ1/RQ2's continuous metrics, extended here to
    categorical ones. Doesn't replace the fixture-level chi-square (a
    different, still-real question -- "is the typical row different"),
    it's the complementary, repo-declustered view."""
    categories = sorted(
        {c for counts in a_by_repo.values() for c in counts}
        | {c for counts in other_by_repo.values() for c in counts}
    )
    return {
        category: compute_continuous_balance(
            human_values=repo_level_category_proportions(other_by_repo, category),
            agent_values=repo_level_category_proportions(a_by_repo, category),
            variable=f"{variable}_{category}_repo_proportion",
        )
        for category in categories
    }


def repo_level_category_n_counts(
    a_by_repo: dict[int, dict[str, int]], other_by_repo: dict[int, dict[str, int]]
) -> NCounts:
    """Repo counts feeding compare_categorical_repo_level()'s tests -- one
    value per side, not per category: a repo's "total" (the proportion
    denominator) is summed across *all* categories for this variable, so
    the set of repos with a nonzero total -- and therefore the set that
    repo_level_category_proportions() actually draws from -- is identical
    for every category. Same population every row in
    render_categorical_repo_level_table() draws from, hence one NCounts
    for the whole table rather than one per row."""
    return NCounts(
        n_a=sum(1 for counts in a_by_repo.values() if sum(counts.values())),
        n_c=sum(1 for counts in other_by_repo.values() if sum(counts.values())),
    )


def render_categorical_repo_level_table(
    results: dict[str, BalanceTest], other_dataset: str, n: NCounts
) -> str:
    """Markdown table for compare_categorical_repo_level()'s output -- one
    row per category, per-repo proportions (not raw counts) shown as
    percentages. Applies BH-FDR across the categories shown first (one
    "family" per variable -- see apply_fdr_correction()'s docstring)."""
    corrected = apply_fdr_correction(results)
    lines = [
        "| Category | A median | A mean | "
        f"{other_dataset.upper()} median | {other_dataset.upper()} mean | n_A | "
        f"n_{other_dataset.upper()} | Statistic | Effect size value | Magnitude | "
        "p (raw) | p (BH-adj) |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    if not corrected:
        lines.append(
            "| _(no categories)_ | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- |"
        )
    else:
        for category, t in corrected.items():
            d = t.details
            if d.get("reason") == "insufficient_data":
                lines.append(
                    f"| {category} | -- | -- | -- | -- | {n.n_a} | {n.n_c} | -- | -- | "
                    "_insufficient data_ | -- | -- |"
                )
                continue
            adj_p = d.get("adjusted_p_value")
            p_adj = format_p_value(adj_p) if adj_p is not None else "--"
            lines.append(
                f"| {category} | "
                f"{pct(d.get('agent_median'))} | {pct(d.get('agent_mean'))} | "
                f"{pct(d.get('human_median'))} | {pct(d.get('human_mean'))} | "
                f"{n.n_a} | {n.n_c} | {_statistic_cell(t)} | {_effect_size_value_cell(t)} | "
                f"{_effect_size_magnitude_cell(t)} | {format_p_value(t.p_value)} | {p_adj} |"
            )
    lines.append("")
    return "\n".join(lines)


@dataclass
class LanguageLeakage:
    """One repo-tagged language's cross-language fixture leakage: how many
    of its fixtures have their OWN detected language (test_files.language)
    differ from the repo's tagged language (repositories.language), and
    which language(s) they leaked into."""

    repo_language: str
    total: int
    leaked: int
    leaked_by_language: dict[str, int] = field(default_factory=dict)

    @property
    def pct(self) -> float:
        return 100 * self.leaked / self.total if self.total else 0.0


def compute_language_leakage(conn: sqlite3.Connection) -> list[LanguageLeakage]:
    """Per-repo-language breakdown of cross-language fixture leakage -- see
    docs/reference/limitations.md's "Cross-Language Fixture Leakage".

    No new column needed: a fixture's own language is already set on
    test_files.language (from the fixture's own file extension, at persist
    time -- corpus_utils.py::persist_repository_and_fixtures()), separate
    from repositories.language (the repo's SEART-assigned tag). A mismatch
    between the two, joined via fixtures.file_id/repo_id, is leakage.
    """
    rows = conn.execute(
        """
        SELECT r.language, tf.language, COUNT(*)
        FROM fixtures f
        JOIN test_files tf ON f.file_id = tf.id
        JOIN repositories r ON f.repo_id = r.id
        GROUP BY r.language, tf.language
        """
    ).fetchall()

    totals: dict[str, int] = {}
    leaked_by_language: dict[str, dict[str, int]] = {}
    for repo_language, fixture_language, count in rows:
        totals[repo_language] = totals.get(repo_language, 0) + count
        if fixture_language != repo_language:
            bucket = leaked_by_language.setdefault(repo_language, {})
            bucket[fixture_language] = bucket.get(fixture_language, 0) + count

    return [
        LanguageLeakage(
            repo_language=lang,
            total=totals[lang],
            leaked=sum(leaked_by_language.get(lang, {}).values()),
            leaked_by_language=leaked_by_language.get(lang, {}),
        )
        for lang in sorted(totals)
    ]


def render_language_leakage_table(leakage: list[LanguageLeakage]) -> str:
    """Markdown table for one dataset's compute_language_leakage() output."""
    total = sum(r.total for r in leakage)
    leaked = sum(r.leaked for r in leakage)
    pct = 100 * leaked / total if total else 0.0

    lines = [
        "**Cross-language fixture leakage** (a fixture's own detected language "
        "differs from its repo's tagged language -- see "
        "[Limitations § Cross-Language Fixture Leakage]"
        "(../docs/reference/limitations.md#cross-language-fixture-leakage))",
        "",
        f"{leaked:,}/{total:,} fixtures ({pct:.2f}%) leaked.",
        "",
        "| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |",
        "|---|---|---|---|---|",
    ]
    if not leakage:
        lines.append("| _(no data)_ | -- | -- | -- | -- |")
    else:
        for r in leakage:
            breakdown = (
                ", ".join(
                    f"{lang}={count:,}"
                    for lang, count in sorted(r.leaked_by_language.items(), key=lambda kv: -kv[1])
                )
                if r.leaked_by_language
                else "--"
            )
            lines.append(
                f"| {r.repo_language} | {r.total:,} | {r.leaked:,} | {r.pct:.2f}% | {breakdown} |"
            )
    lines.append("")
    return "\n".join(lines)


def write_markdown_report(output_dir: Path, filename: str, report: str) -> Path:
    """Write `report` to `output_dir/filename`, fully replacing any prior
    content -- `Path.write_text()` always truncates before writing, so a
    dataset shrinking between runs (e.g. a retroactive dedup fix) can never
    leave stale rows from a previous, larger report behind. Every rqN.py /
    language_contamination.py script's write_report() calls this instead of
    writing the file itself, so this guarantee lives in exactly one place
    rather than four separately-trusted copies."""
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / filename
    output_path.write_text(report)
    return output_path
