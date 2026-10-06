"""
RQ5 -- Agent Configuration Files: how often do root-level agent configuration
files (AGENTS.md, CLAUDE.md) mention test-related and fixture-related guidance,
for the repositories that contribute at least one fixture to Dataset A?

Pure reader over `db/rq5_agent_files.db` (`collection/rq5_agent_file_scan.py`'s
own output). No collection logic lives here.

The report gives numbers and definitions only. Every statistic except the
fenced-code-block table is at the repository level: a repository counts as
matching a keyword list if ANY of its root agent files matches. A fixture
keyword match is not fixture guidance; that is decided by manual coding (see
`rq5_coding.py`). The denominators are:

- "analyzed" repositories (commit found at the snapshot, root tree fetched) for
  the share with at least one root agent file;
- repositories with at least one root agent file for every other share.

The `ardic_test_keywords` statistic uses the keyword set of Ardic et al. (SCAM
2026) with the same computation as the `test_keywords` statistic.

python -m collection.research_questions.rq5
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..db import db_session
from ..rq5_agent_file_scan import (
    CATALOG_PATH,
    DB_PATH,
    REPO_TABLE_NAME,
    load_fixture_match_rows,
    load_repo_guidance,
    load_rq5_keyword_catalog,
    load_scan_meta,
)
from ._shared import OUTPUT_DIR, pct, write_markdown_report

# Paper's row order, matching rq1.py's DISPLAY_LANGUAGES convention.
DISPLAY_LANGUAGES: tuple[str, ...] = ("python", "java", "javascript", "typescript")
DISPLAY_LABELS: dict[str, str] = {
    "python": "Python",
    "java": "Java",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
}


@dataclass
class GroupStats:
    """Counts for one group of repositories (all, or one language).

    `analyzed` is every repository with a successful fetch. `with_agent_file`
    is the subset with at least one root agent file, the denominator for every
    share except the first."""

    analyzed: int = 0
    with_agent_file: int = 0
    test: int = 0
    test_ardic: int = 0
    fixture: int = 0


def group_stats(records: list[dict[str, Any]]) -> GroupStats:
    """Counts over analyzed-repository records (see `load_repo_guidance()`)."""
    with_agent = [r for r in records if r["agent_files"]]
    return GroupStats(
        analyzed=len(records),
        with_agent_file=len(with_agent),
        test=sum(1 for r in with_agent if r["has_test"]),
        test_ardic=sum(1 for r in with_agent if r["has_test_ardic"]),
        fixture=sum(1 for r in with_agent if r["has_fixture"]),
    )


def load_corpus_counts(db_path: Path = DB_PATH) -> dict[str, Any]:
    """Corpus size, analyzed count, and skipped repositories grouped by reason."""
    with db_session(db_path) as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM {REPO_TABLE_NAME}").fetchone()[0]
        reasons = conn.execute(
            f"SELECT error_reason, COUNT(*) FROM {REPO_TABLE_NAME} WHERE fetch_ok = 0 "
            "GROUP BY error_reason ORDER BY COUNT(*) DESC, error_reason"
        ).fetchall()
    skipped = sum(count for _, count in reasons)
    return {
        "total": total,
        "analyzed": total - skipped,
        "skipped": skipped,
        "skipped_by_reason": [(reason, count) for reason, count in reasons],
    }


def fixture_term_counts(records: list[dict[str, Any]], fixture_terms: list[str]) -> Counter:
    """Repositories (among those with a root agent file) containing each
    fixture term. Every catalog term appears, even at zero."""
    counts: Counter = Counter(dict.fromkeys(fixture_terms, 0))
    for record in records:
        if not record["agent_files"]:
            continue
        for term in record["fixture_terms"]:
            counts[term] += 1
    return counts


def code_block_counts(match_rows: list[tuple], fixture_terms: list[str]) -> dict[str, tuple[int, int]]:
    """Fixture matches and those inside a fenced code block, per term (every
    catalog term, even at zero) and under the key `"all"`."""
    counts = {term: [0, 0] for term in [*fixture_terms, "all"]}
    for row in match_rows:
        keyword, in_block = row[3], bool(row[9])
        for key in (keyword, "all"):
            counts.setdefault(key, [0, 0])
            counts[key][0] += 1
            counts[key][1] += in_block
    return {key: (total, in_block) for key, (total, in_block) in counts.items()}


def _ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else numerator / denominator


def render_overall_table(counts: dict[str, Any], stats: GroupStats) -> str:
    lines = [
        "| # | Statistic | Count | Percentage | Denominator |",
        "|---|---|---|---|---|",
        f"| 1 | Repositories in the corpus | {counts['total']:,} | -- | -- |",
        f"| 1 | Repositories analyzed | {stats.analyzed:,} | "
        f"{pct(_ratio(stats.analyzed, counts['total']))} | corpus |",
        f"| 2 | With a root agent file (AGENTS.md or CLAUDE.md) | {stats.with_agent_file:,} | "
        f"{pct(_ratio(stats.with_agent_file, stats.analyzed))} | analyzed |",
        f"| 3 | With a test keyword (`test_keywords`) | {stats.test:,} | "
        f"{pct(_ratio(stats.test, stats.with_agent_file))} | with agent file |",
        f"| 4 | With an Ardic test term (`ardic_test_keywords`) | {stats.test_ardic:,} | "
        f"{pct(_ratio(stats.test_ardic, stats.with_agent_file))} | with agent file |",
        f"| 5 | With a fixture keyword match (`fixture_keywords`) | {stats.fixture:,} | "
        f"{pct(_ratio(stats.fixture, stats.with_agent_file))} | with agent file |",
    ]
    return "\n".join(lines)


def render_by_language_table(records: list[dict[str, Any]]) -> str:
    lines = [
        "| Language | Analyzed | With agent file (% of analyzed) | "
        "Test keyword (% of with agent file) | Ardic test term (%) | Fixture keyword match (%) |",
        "|---|---|---|---|---|---|",
    ]
    for language in DISPLAY_LANGUAGES:
        stats = group_stats([r for r in records if r["language"] == language])
        lines.append(
            f"| {DISPLAY_LABELS[language]} | {stats.analyzed:,} | "
            f"{stats.with_agent_file:,} ({pct(_ratio(stats.with_agent_file, stats.analyzed))}) | "
            f"{pct(_ratio(stats.test, stats.with_agent_file))} | "
            f"{pct(_ratio(stats.test_ardic, stats.with_agent_file))} | "
            f"{pct(_ratio(stats.fixture, stats.with_agent_file))} |"
        )
    return "\n".join(lines)


def render_fixture_term_table(counts: Counter, terms: list[str]) -> str:
    lines = ["| Fixture term | Repositories containing it |", "|---|---|"]
    for term in terms:
        lines.append(f"| {term} | {counts[term]:,} |")
    return "\n".join(lines)


def render_code_block_table(counts: dict[str, tuple[int, int]], terms: list[str]) -> str:
    lines = ["| Fixture term | Fixture matches | In a fenced code block | Percentage |", "|---|---|---|---|"]
    for term in [*terms, "all"]:
        total, in_block = counts[term]
        label = "All terms" if term == "all" else term
        lines.append(f"| {label} | {total:,} | {in_block:,} | {pct(_ratio(in_block, total))} |")
    return "\n".join(lines)


def render_skipped_table(counts: dict[str, Any]) -> str:
    if not counts["skipped_by_reason"]:
        return "No repositories were skipped."
    lines = ["| Reason | Repositories |", "|---|---|"]
    for reason, count in counts["skipped_by_reason"]:
        lines.append(f"| {reason} | {count:,} |")
    return "\n".join(lines)


def generate_report(*, db_path: Path = DB_PATH, catalog_path: Path = CATALOG_PATH) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    catalog = load_rq5_keyword_catalog(catalog_path)
    meta = load_scan_meta(db_path)

    lines = [
        "# RQ5 -- Agent Configuration Files",
        "",
        "> How often do root-level agent configuration files mention test-related "
        "and fixture-related guidance, for the repositories that contribute a fixture "
        "to Dataset A?",
        "",
        f"Generated: {generated_at}",
        "",
    ]

    if not db_path.exists() or not meta:
        lines += ["_Not available -- no RQ5 scan has been run yet._", ""]
        return "\n".join(lines)

    counts = load_corpus_counts(db_path)
    records = load_repo_guidance(set(catalog["ardic_test_keywords"]), db_path)
    stats = group_stats(records)
    all_fixture_terms = list(catalog["fixture_keywords"])

    lines += [
        f"Snapshot date: {meta['snapshot_date']} (each repository's root files are read at "
        "its last commit on or before this date).",
        "Keyword catalog: `collection/heuristics/rq5_agent_file_keywords.yaml`.",
        f"Target files (repository root only, case-insensitive): "
        f"{', '.join(catalog['target_files'])}.",
        f"Repositories skipped (no commit at or before the snapshot, or a failed fetch): "
        f"{counts['skipped']:,} of {counts['total']:,}.",
        "",
        "## Overall",
        "",
        render_overall_table(counts, stats),
        "",
        "## By language",
        "",
        render_by_language_table(records),
        "",
        "## Fixture terms",
        "",
        "Repositories with at least one root agent file that contain each term.",
        "",
        render_fixture_term_table(fixture_term_counts(records, all_fixture_terms), all_fixture_terms),
        "",
        "## Fixture matches in fenced code blocks",
        "",
        "Counted per match (one line of a root agent file matching a term), not per repository.",
        "",
        render_code_block_table(code_block_counts(load_fixture_match_rows(db_path), all_fixture_terms), all_fixture_terms),
        "",
        "## Skipped repositories",
        "",
        render_skipped_table(counts),
        "",
        "## Keyword lists",
        "",
        f"- Test keywords: {', '.join(catalog['test_keywords'])}",
        f"- Ardic test terms (the keyword set of Ardic et al., SCAM 2026): "
        f"{', '.join(catalog['ardic_test_keywords'])}",
        f"- Fixture keywords: {', '.join(catalog['fixture_keywords'])}",
        "",
        "Matching is case-insensitive and whole-word.",
        f"`test_keywords` match {stats.test - stats.test_ardic:,} "
        f"{'repository' if stats.test - stats.test_ardic == 1 else 'repositories'} that "
        "`ardic_test_keywords` do not.",
        "",
    ]
    return "\n".join(lines)


def write_report(output_dir: Path = OUTPUT_DIR, *, db_path: Path = DB_PATH) -> Path:
    report = generate_report(db_path=db_path)
    return write_markdown_report(output_dir, "rq5.md", report)


def main() -> None:
    path = write_report()
    print(f"RQ5 report written to {path}")


if __name__ == "__main__":
    main()
