"""
RQ5 -- manual coding results: reads the completed repository-level coding
sheet (`rq5/rq5_repository_coding_sheet.csv`) and computes the final RQ5
fixture-guidance numbers.

Denominators:

- repositories with a root agent file (from `db/rq5_agent_files.db`) for the
  share coded `yes`, overall and per primary language;
- repositories with a fixture keyword match (the sheet's rows) for the
  precision of the keyword search.

Refuses to run while any row is uncoded or holds a value outside the allowed
ones (see `rq5/README.md`). No coding is inferred here.

python -m collection.research_questions.rq5_coding
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..rq5_agent_file_scan import (
    CATEGORY_VALUES,
    CODE_FIXTURE_GUIDANCE_VALUES,
    CSV_OUTPUT_DIR,
    DB_PATH,
    REPOSITORY_SHEET_FIELDNAMES,
    REPOSITORY_SHEET_NAME,
    load_repo_guidance,
    snippet_row_ids,
)
from ._shared import OUTPUT_DIR, pct, write_markdown_report
from .rq5 import DISPLAY_LABELS, DISPLAY_LANGUAGES

SHEET_PATH = CSV_OUTPUT_DIR / REPOSITORY_SHEET_NAME


class CodingIncompleteError(ValueError):
    """The coding sheet has uncoded or invalid rows."""


def load_coded_sheet(path: Path = SHEET_PATH) -> list[dict[str, Any]]:
    """The sheet's rows, validated. Raises `CodingIncompleteError` listing every
    problem: an empty or unknown `code_fixture_guidance`, a `yes` without a
    category or an evidence row id, an evidence row id that is not one of the
    repository's snippets, or an unknown category."""
    if not path.exists():
        raise CodingIncompleteError(f"{path} does not exist")
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        missing = set(REPOSITORY_SHEET_FIELDNAMES) - set(reader.fieldnames or ())
        if missing:
            raise CodingIncompleteError(f"{path} is missing columns: {', '.join(sorted(missing))}")
        rows = list(reader)

    uncoded: list[str] = []
    problems: list[str] = []
    coded: list[dict[str, Any]] = []
    for row in rows:
        repo = row["repository"]
        guidance = row["code_fixture_guidance"].strip().lower()
        evidence = row["evidence_row_id"].strip()
        categories = [c.strip() for c in row["category"].split(";") if c.strip()]

        if not guidance:
            uncoded.append(repo)
            continue
        if guidance not in CODE_FIXTURE_GUIDANCE_VALUES:
            problems.append(f"{repo}: code_fixture_guidance {guidance!r} is not one of {CODE_FIXTURE_GUIDANCE_VALUES}")
        unknown = [c for c in categories if c not in CATEGORY_VALUES]
        if unknown:
            problems.append(f"{repo}: unknown category {', '.join(unknown)}")
        if guidance == "yes":
            if not categories:
                problems.append(f"{repo}: coded yes without a category")
            if not evidence:
                problems.append(f"{repo}: coded yes without an evidence_row_id")
            elif not evidence.isdigit() or int(evidence) not in snippet_row_ids(row["fixture_snippets"]):
                problems.append(f"{repo}: evidence_row_id {evidence!r} is not one of this repository's snippets")
        coded.append({"repository": repo, "language": row["primary_language"], "guidance": guidance, "categories": categories})

    if uncoded or problems:
        lines = []
        if uncoded:
            shown = ", ".join(uncoded[:10]) + (" ..." if len(uncoded) > 10 else "")
            lines.append(f"{len(uncoded)} of {len(rows)} rows are still uncoded (code_fixture_guidance empty): {shown}")
        lines += problems
        raise CodingIncompleteError(f"{path} is not fully coded:\n" + "\n".join(lines))
    return coded


def agent_file_counts(db_path: Path = DB_PATH) -> Counter:
    """Repositories with at least one root agent file, per language, plus the
    total under the key `"all"`."""
    counts: Counter = Counter()
    for record in load_repo_guidance(frozenset(), db_path):
        if record["agent_files"]:
            counts[record["language"]] += 1
            counts["all"] += 1
    return counts


def compute_results(coded: list[dict[str, Any]], with_agent_file: Counter) -> dict[str, Any]:
    guidance = Counter(r["guidance"] for r in coded)
    yes_by_language = Counter(r["language"] for r in coded if r["guidance"] == "yes")
    categories = Counter(c for r in coded if r["guidance"] == "yes" for c in r["categories"])
    return {
        "with_agent_file": with_agent_file,
        "with_fixture_match": len(coded),
        "yes": guidance["yes"],
        "no": guidance["no"],
        "unsure": guidance["unsure"],
        "yes_by_language": yes_by_language,
        "categories": categories,
    }


def _ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else numerator / denominator


def generate_report(results: dict[str, Any]) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    total = results["with_agent_file"]["all"]
    matched = results["with_fixture_match"]
    lines = [
        "# RQ5 -- Manual coding of fixture guidance",
        "",
        f"Generated: {generated_at}",
        "",
        f"Source: `rq5/{REPOSITORY_SHEET_NAME}`, one row per repository with a fixture keyword match.",
        "",
        "## Code fixture guidance",
        "",
        "| Statistic | Count | Percentage | Denominator |",
        "|---|---|---|---|",
        f"| Coded `yes` | {results['yes']:,} | {pct(_ratio(results['yes'], total))} | "
        f"{total:,} repositories with a root agent file |",
        "",
        "## By primary language",
        "",
        "| Language | With root agent file | Coded `yes` | Percentage |",
        "|---|---|---|---|",
    ]
    for language in DISPLAY_LANGUAGES:
        denominator = results["with_agent_file"][language]
        yes = results["yes_by_language"][language]
        lines.append(f"| {DISPLAY_LABELS[language]} | {denominator:,} | {yes:,} | {pct(_ratio(yes, denominator))} |")
    lines += [
        "",
        "## Keyword search precision",
        "",
        "| Coding | Repositories | Percentage of repositories with a fixture match |",
        "|---|---|---|",
    ]
    for value in CODE_FIXTURE_GUIDANCE_VALUES:
        lines.append(f"| `{value}` | {results[value]:,} | {pct(_ratio(results[value], matched))} |")
    lines += [
        f"| Total | {matched:,} | -- |",
        "",
        f"Precision: {results['yes']:,} of {matched:,} ({pct(_ratio(results['yes'], matched))}); "
        f"{results['unsure']:,} coded `unsure`.",
        "",
        "## Categories",
        "",
        "Repositories coded `yes` per category. A repository can have more than one category.",
        "",
        "| Category | Repositories |",
        "|---|---|",
    ]
    for category in CATEGORY_VALUES:
        lines.append(f"| {category} | {results['categories'][category]:,} |")
    lines.append("")
    return "\n".join(lines)


def write_report(
    output_dir: Path = OUTPUT_DIR, *, sheet_path: Path = SHEET_PATH, db_path: Path = DB_PATH
) -> Path:
    results = compute_results(load_coded_sheet(sheet_path), agent_file_counts(db_path))
    return write_markdown_report(output_dir, "rq5_coding.md", generate_report(results))


def main() -> None:
    parser = argparse.ArgumentParser(description="RQ5 results from the completed repository-level coding sheet.")
    parser.add_argument("--sheet", type=Path, default=SHEET_PATH, help=f"Coding sheet (default: {SHEET_PATH})")
    args = parser.parse_args()
    try:
        path = write_report(sheet_path=args.sheet)
    except CodingIncompleteError as exc:
        raise SystemExit(str(exc)) from None
    print(f"RQ5 coding report written to {path}")


if __name__ == "__main__":
    main()
