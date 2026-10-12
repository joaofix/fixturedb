"""
RQ5 -- Agent Configuration Files: how often do agent configuration files
mention test-related and fixture-related guidance, for the repositories that
contribute at least one fixture to Dataset A?

Pure reader over `db/rq5_agent_files.db` (`collection/rq5_agent_file_scan.py`'s
own output). No collection logic lives here.

The report gives numbers and definitions only. The files are the guidance
files of each repository: AGENTS.md, CLAUDE.md or GEMINI.md at any depth of
its tree. Every statistic except the fenced-code-block table is at the
repository level: a repository counts as matching a keyword list if ANY of its
guidance files matches. A fixture keyword match is not fixture guidance; that
is decided by manual coding (see `rq5_coding.py`). The denominators are:

- "analyzed" repositories (commit found at the snapshot, file list fetched) for
  the share with at least one guidance file;
- repositories with at least one guidance file for every other share.

The test keywords (`ardic_test_keywords`) are the keyword set of Ardic et al.
(SCAM 2026).

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
    FILE_TABLE_NAME,
    GUIDANCE_CATALOG_PATH,
    LOCATION_NESTED,
    LOCATION_ROOT,
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

    `analyzed` is every repository with a successful fetch. `with_guidance_file`
    is the subset with at least one guidance file, the denominator for every
    share except the first."""

    analyzed: int = 0
    with_guidance_file: int = 0
    with_root_file: int = 0
    test: int = 0
    fixture: int = 0


def group_stats(records: list[dict[str, Any]]) -> GroupStats:
    """Counts over analyzed-repository records (see `load_repo_guidance()`)."""
    with_file = [r for r in records if r["guidance_files"]]
    return GroupStats(
        analyzed=len(records),
        with_guidance_file=len(with_file),
        with_root_file=sum(1 for r in with_file if r["root_files"]),
        test=sum(1 for r in with_file if r["has_test"]),
        fixture=sum(1 for r in with_file if r["has_fixture"]),
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


def file_name_counts(db_path: Path = DB_PATH) -> list[tuple[str, int, int, int, int]]:
    """`(file name, files, repositories, root files, nested files)` per catalog
    spelling of the name, most files first."""
    with db_session(db_path) as conn:
        rows = conn.execute(
            f"SELECT file_type, COUNT(*), COUNT(DISTINCT repo_name), "
            f"SUM(location = '{LOCATION_ROOT}'), SUM(location = '{LOCATION_NESTED}') "
            f"FROM {FILE_TABLE_NAME} GROUP BY file_type ORDER BY COUNT(*) DESC, file_type"
        ).fetchall()
    return [(name, files, repos, root, nested) for name, files, repos, root, nested in rows]


def guidance_file_summary(records: list[dict[str, Any]], db_path: Path = DB_PATH) -> dict[str, int]:
    """Where the guidance files are: repositories with root files, with nested
    files only, whose fixture match is only in nested files; files read through
    a symbolic link; repositories whose file list GitHub truncated (fetched
    split into subdirectory listings instead)."""
    with db_session(db_path) as conn:
        symlinked = conn.execute(f"SELECT COUNT(*) FROM {FILE_TABLE_NAME} WHERE symlink_target != ''").fetchone()[0]
        nested_files = conn.execute(
            f"SELECT COUNT(*) FROM {FILE_TABLE_NAME} WHERE location = ?", (LOCATION_NESTED,)
        ).fetchone()[0]
        truncated = conn.execute(
            f"SELECT COUNT(*) FROM {REPO_TABLE_NAME} WHERE fetch_ok = 1 AND tree_truncated = 1"
        ).fetchone()[0]
    with_file = [r for r in records if r["guidance_files"]]
    return {
        "with_root_file": sum(1 for r in with_file if r["root_files"]),
        "nested_only": sum(1 for r in with_file if not r["root_files"]),
        "with_nested_file": sum(1 for r in with_file if len(r["guidance_files"]) > len(r["root_files"])),
        "nested_files": nested_files,
        "fixture_only_nested": sum(1 for r in records if r["has_fixture_nested"] and not r["has_fixture_root"]),
        "symlinked_files": symlinked,
        "truncated_trees": truncated,
    }


def fixture_term_counts(records: list[dict[str, Any]], fixture_terms: list[str]) -> Counter:
    """Repositories containing each fixture term. Every catalog term appears,
    even at zero."""
    counts: Counter = Counter(dict.fromkeys(fixture_terms, 0))
    for record in records:
        for term in record["fixture_terms"]:
            counts[term] += 1
    return counts


def code_block_counts(match_rows: list[dict[str, Any]], fixture_terms: list[str]) -> dict[str, tuple[int, int]]:
    """Fixture matches and those inside a fenced code block, per term (every
    catalog term, even at zero) and under the key `"all"`."""
    counts = {term: [0, 0] for term in [*fixture_terms, "all"]}
    for row in match_rows:
        in_block = bool(row["in_code_block"])
        for key in (row["keyword"], "all"):
            counts.setdefault(key, [0, 0])
            counts[key][0] += 1
            counts[key][1] += in_block
    return {key: (total, in_block) for key, (total, in_block) in counts.items()}


def _ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else numerator / denominator


def render_overall_table(counts: dict[str, Any], stats: GroupStats) -> str:
    def share(value: int) -> str:
        return f"{value:,} | {pct(_ratio(value, stats.with_guidance_file))}"

    lines = [
        "| # | Statistic | Repositories | % | Denominator |",
        "|---|---|---|---|---|",
        f"| 1 | Repositories in the corpus | {counts['total']:,} | -- | -- |",
        f"| 1 | Repositories analyzed | {stats.analyzed:,} | {pct(_ratio(stats.analyzed, counts['total']))} | corpus |",
        f"| 2 | With a guidance file | {stats.with_guidance_file:,} | "
        f"{pct(_ratio(stats.with_guidance_file, stats.analyzed))} | analyzed |",
        f"| 2a | -- with a guidance file at the root | {share(stats.with_root_file)} | with guidance file |",
        f"| 3 | With a test keyword (`ardic_test_keywords`) | {share(stats.test)} | with guidance file |",
        f"| 4 | With a fixture keyword match (`fixture_keywords`) | {share(stats.fixture)} | with guidance file |",
    ]
    return "\n".join(lines)


def render_by_language_table(records: list[dict[str, Any]]) -> str:
    lines = [
        "| Language | Analyzed | With guidance file (% of analyzed) | Test keyword (%) | Fixture keyword match (%) |",
        "|---|---|---|---|---|",
    ]
    for language in DISPLAY_LANGUAGES:
        stats = group_stats([r for r in records if r["language"] == language])
        lines.append(
            f"| {DISPLAY_LABELS[language]} | {stats.analyzed:,} | "
            f"{stats.with_guidance_file:,} ({pct(_ratio(stats.with_guidance_file, stats.analyzed))}) | "
            f"{pct(_ratio(stats.test, stats.with_guidance_file))} | "
            f"{pct(_ratio(stats.fixture, stats.with_guidance_file))} |"
        )
    return "\n".join(lines)


def render_fixture_term_table(term_counts: Counter, terms: list[str]) -> str:
    lines = ["| Fixture term | Repositories |", "|---|---|"]
    for term in terms:
        lines.append(f"| {term} | {term_counts[term]:,} |")
    return "\n".join(lines)


def render_code_block_table(counts: dict[str, tuple[int, int]], terms: list[str]) -> str:
    lines = ["| Fixture term | Matches | In a fenced code block | % |", "|---|---|---|---|"]
    for term in [*terms, "all"]:
        label = "All terms" if term == "all" else term
        total, in_block = counts[term]
        lines.append(f"| {label} | {total:,} | {in_block:,} | {pct(_ratio(in_block, total))} |")
    return "\n".join(lines)


def render_file_name_table(rows: list[tuple[str, int, int, int, int]]) -> str:
    if not rows:
        return "None."
    lines = ["| File name | Files | Repositories | At the root | Nested |", "|---|---|---|---|---|"]
    for name, files, repos, root, nested in rows:
        lines.append(f"| {name} | {files:,} | {repos:,} | {root:,} | {nested:,} |")
    return "\n".join(lines)


def render_skipped_table(counts: dict[str, Any]) -> str:
    if not counts["skipped_by_reason"]:
        return "No repositories were skipped."
    lines = ["| Reason | Repositories |", "|---|---|"]
    for reason, count in counts["skipped_by_reason"]:
        lines.append(f"| {reason} | {count:,} |")
    return "\n".join(lines)


def generate_report(
    *, db_path: Path = DB_PATH, catalog_path: Path = CATALOG_PATH, guidance_path: Path = GUIDANCE_CATALOG_PATH
) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    catalog = load_rq5_keyword_catalog(catalog_path, guidance_path)
    meta = load_scan_meta(db_path)

    lines = [
        "# RQ5 -- Agent Configuration Files",
        "",
        "> How often do agent configuration files mention test-related and fixture-related "
        "guidance, for the repositories that contribute a fixture to Dataset A?",
        "",
        f"Generated: {generated_at}",
        "",
    ]

    if not db_path.exists() or not meta:
        lines += ["_Not available -- no RQ5 scan has been run yet._", ""]
        return "\n".join(lines)

    counts = load_corpus_counts(db_path)
    records = load_repo_guidance(db_path)
    stats = group_stats(records)
    terms = list(catalog["fixture_keywords"])
    summary = guidance_file_summary(records, db_path)

    lines += [
        f"Snapshot date: {meta['snapshot_date']} (each repository's files are read at its last "
        "commit on or before this date).",
        "Keyword catalog: `collection/heuristics/rq5_agent_file_keywords.yaml`.",
        "File names: `collection/heuristics/rq5_agent_guidance_files.yaml`.",
        f"Guidance files: a file named {', '.join(catalog['guidance_files'])} (case-insensitive) at "
        "the root or in any subdirectory; references between files are not followed. Files under "
        f"these directories are not read: {', '.join(catalog['excluded_dirs'])}.",
        f"Repositories skipped (no commit at or before the snapshot, or a failed fetch): "
        f"{counts['skipped']:,} of {counts['total']:,}.",
        "",
        "## Overall",
        "",
        render_overall_table(counts, stats),
        "",
        "## By language",
        "",
        "Shares of repositories with a guidance file.",
        "",
        render_by_language_table(records),
        "",
        "## Guidance files",
        "",
        "| Statistic | Count |",
        "|---|---|",
        f"| Repositories with a guidance file at the root | {summary['with_root_file']:,} |",
        f"| Repositories with a guidance file in a subdirectory | {summary['with_nested_file']:,} |",
        f"| Repositories with guidance files in subdirectories only | {summary['nested_only']:,} |",
        f"| Guidance files in subdirectories | {summary['nested_files']:,} |",
        f"| Repositories whose fixture match is only in subdirectory files | {summary['fixture_only_nested']:,} |",
        f"| Guidance files read through a symbolic link | {summary['symlinked_files']:,} |",
        f"| Repositories whose file list was fetched in parts (GitHub truncated it) | "
        f"{summary['truncated_trees']:,} |",
        "",
        "A symbolic link whose target is another guidance file already read is not counted again.",
        "",
        "### Guidance files per file name",
        "",
        render_file_name_table(file_name_counts(db_path)),
        "",
        "## Fixture terms",
        "",
        "Repositories whose guidance files contain each term.",
        "",
        render_fixture_term_table(fixture_term_counts(records, terms), terms),
        "",
        "## Fixture matches in fenced code blocks",
        "",
        "Counted per match (one line of a file matching a term), not per repository.",
        "",
        render_code_block_table(code_block_counts(load_fixture_match_rows(db_path), terms), terms),
        "",
        "## Skipped repositories",
        "",
        render_skipped_table(counts),
        "",
        "## Keyword lists",
        "",
        f"- Test keywords (the keyword set of Ardic et al., SCAM 2026): "
        f"{', '.join(catalog['ardic_test_keywords'])}",
        f"- Fixture keywords: {', '.join(catalog['fixture_keywords'])}",
        "",
        "Matching is case-insensitive and whole-word.",
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
