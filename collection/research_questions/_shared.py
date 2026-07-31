"""Helpers shared across collection/research_questions/ scripts (rq1.py,
rq2.py, rq3.py, language_contamination.py) -- kept here once instead of
duplicated per-script, per this package's convention: leverage
already-collected data first, import logic from collection/ second, write
new logic only as a last resort (and then, only once).
"""

from __future__ import annotations

import sqlite3
import statistics
from dataclasses import dataclass, field
from pathlib import Path

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
    script uses so it can run against whatever subset of A/B/C is collected."""
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


def render_stratified_categorical_table(results: dict[str, BalanceTest]) -> str:
    """Markdown table for compute_stratified_categorical_balance()'s output."""
    lines = [
        "| Language | chi2 | dof | p-value | significant (p<0.05) |",
        "|---|---|---|---|---|",
    ]
    if not results:
        lines.append("| _(no language shared by both datasets)_ | -- | -- | -- | -- |")
    else:
        for language, t in results.items():
            d = t.details
            if d.get("reason") == "insufficient_data":
                lines.append(f"| {language} | -- | -- | -- | _insufficient data_ |")
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
                lines.append(f"| {language} | -- | -- | -- | _test failed ({d['error']})_ |")
                continue
            sig = "yes" if t.p_value < 0.05 else "no"
            dof = d.get("degrees_of_freedom", "--")
            lines.append(f"| {language} | {fmt(t.statistic, 1)} | {dof} | {t.p_value:.4g} | {sig} |")
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
