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

from scipy.stats import false_discovery_control

from ..between_group_comparison import BalanceTest, compute_categorical_balance
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

# (dataset compared against A, comparison label) -- B vs C intentionally
# omitted until Dataset B/C actually exist; see rq1.py's module docstring.
COMPARISONS = [("b", "A vs B"), ("c", "A vs C")]


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


def fmt(value: float | None, digits: int = 2) -> str:
    return "--" if value is None else f"{value:.{digits}f}"


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
    """
    testable_keys = [
        k for k, t in tests.items() if "reason" not in t.details and "error" not in t.details
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


def render_stratified_categorical_table(results: dict[str, BalanceTest]) -> str:
    """Markdown table for compute_stratified_categorical_balance()'s output.
    Applies BH-FDR correction across the languages shown (one "family" --
    see apply_fdr_correction()'s docstring) before rendering, so callers
    don't need to remember to do it separately."""
    corrected = apply_fdr_correction(results)
    lines = [
        "| Language | chi2 | dof | p-value | significant (p<0.05) | Cramer's V (effect size) | "
        "BH-FDR adjusted p (sig?) |",
        "|---|---|---|---|---|---|---|",
    ]
    if not corrected:
        lines.append("| _(no language shared by both datasets)_ | -- | -- | -- | -- | -- | -- |")
    else:
        for language, t in corrected.items():
            d = t.details
            if d.get("reason") == "insufficient_data":
                lines.append(f"| {language} | -- | -- | -- | _insufficient data_ | -- | -- |")
                continue
            if "error" in d:
                # compute_categorical_balance() catches chi2_contingency
                # failures (e.g. a whole category at 0 on both sides for
                # this language -- a zero expected-frequency cell) and
                # returns p_value=1.0/is_balanced=True as a safe default so
                # callers never crash on it. That default reads as a real
                # "not significant" result if rendered plainly here, which
                # is actively misleading -- it means the test couldn't run
                # at all, not that no difference was found.
                lines.append(f"| {language} | -- | -- | -- | _test failed ({d['error']})_ | -- | -- |")
                continue
            sig = "yes" if t.p_value < 0.05 else "no"
            dof = d.get("degrees_of_freedom", "--")
            lines.append(
                f"| {language} | {fmt(t.statistic, 1)} | {dof} | {t.p_value:.4g} | {sig} | "
                f"{categorical_effect_size_cell(t)} | {fdr_cell(t)} |"
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


def fetch_continuous_column_by_repo(
    conn: sqlite3.Connection, table: str, column: str
) -> dict[int, list[float]]:
    """{repo_id: [values]} for `column` in `table`, non-null values only --
    the per-repo grouping repo_level_means() needs."""
    rows = conn.execute(
        f"SELECT repo_id, {column} FROM {table} WHERE {column} IS NOT NULL"
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
