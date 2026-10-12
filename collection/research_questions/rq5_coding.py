"""
RQ5 -- manual coding results: reads the completed repository-level coding
sheet (`research-questions/rq5/rq5_repository_coding_sheet.csv`) and computes the final RQ5
fixture-guidance numbers.

Denominators:

- repositories with a guidance file (from `db/rq5_agent_files.db`) for the
  share coded `yes`, overall and per primary language;
- repositories with a fixture keyword match (the sheet's rows) for the
  precision of the keyword search.

Refuses to run while any row is uncoded or holds a value outside the allowed
ones (see `research-questions/rq5/README.md`). No coding is inferred here.
With `--decisions-only`, a `yes` without a category is accepted (categories are
coded after the decisions) and the categories section is marked pending.

python -m collection.research_questions.rq5_coding [--decisions-only]
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..rq5_agent_file_scan import (
    CSV_OUTPUT_DIR,
    DB_PATH,
    DECISION_VALUES,
    REPOSITORY_SHEET_FIELDNAMES,
    REPOSITORY_SHEET_NAME,
    load_repo_guidance,
)
from ._shared import OUTPUT_DIR, pct, write_markdown_report
from .rq5 import DISPLAY_LABELS, DISPLAY_LANGUAGES

SHEET_PATH = CSV_OUTPUT_DIR / REPOSITORY_SHEET_NAME


class CodingIncompleteError(ValueError):
    """The coding sheet has uncoded or invalid rows."""


def load_coded_sheet(path: Path = SHEET_PATH, *, decisions_only: bool = False) -> list[dict[str, Any]]:
    """The sheet's rows, validated. Raises `CodingIncompleteError` listing every
    problem: an empty or unknown `decision`, or a `yes` without a category
    (unless `decisions_only`). Category values are free text: the category set
    is defined during coding."""
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
        decision = row["decision"].strip().lower()
        categories = [c.strip() for c in row["category"].split(";") if c.strip()]

        if not decision:
            uncoded.append(repo)
            continue
        if decision not in DECISION_VALUES:
            problems.append(f"{repo}: decision {decision!r} is not one of {DECISION_VALUES}")
        if decision == "yes" and not decisions_only:
            if not categories:
                problems.append(f"{repo}: coded yes without a category")
        coded.append({"repository": repo, "language": row["primary_language"], "decision": decision, "categories": categories})

    if uncoded or problems:
        lines = []
        if uncoded:
            shown = ", ".join(uncoded[:10]) + (" ..." if len(uncoded) > 10 else "")
            lines.append(f"{len(uncoded)} of {len(rows)} rows are still uncoded (decision empty): {shown}")
        lines += problems
        raise CodingIncompleteError(f"{path} is not fully coded:\n" + "\n".join(lines))
    return coded


def guidance_file_counts(db_path: Path = DB_PATH) -> Counter:
    """Repositories with at least one guidance file, per language, plus the
    total under the key `"all"`."""
    counts: Counter = Counter()
    for record in load_repo_guidance(db_path):
        if record["guidance_files"]:
            counts[record["language"]] += 1
            counts["all"] += 1
    return counts


def compute_results(coded: list[dict[str, Any]], with_guidance_file: Counter) -> dict[str, Any]:
    decisions = Counter(r["decision"] for r in coded)
    yes_by_language = Counter(r["language"] for r in coded if r["decision"] == "yes")
    categories = Counter(c for r in coded if r["decision"] == "yes" for c in r["categories"])
    uncategorised = sum(1 for r in coded if r["decision"] == "yes" and not r["categories"])
    return {
        "with_guidance_file": with_guidance_file,
        "with_fixture_match": len(coded),
        "yes": decisions["yes"],
        "no": decisions["no"],
        "unsure": decisions["unsure"],
        "yes_by_language": yes_by_language,
        "categories": categories,
        "uncategorised": uncategorised,
    }


def _ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else numerator / denominator


def generate_report(results: dict[str, Any]) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    total = results["with_guidance_file"]["all"]
    matched = results["with_fixture_match"]
    lines = [
        "# RQ5 -- Manual coding of fixture guidance",
        "",
        f"Generated: {generated_at}",
        "",
        f"Source: `research-questions/rq5/{REPOSITORY_SHEET_NAME}`, one row per repository with a fixture keyword match in its guidance files.",
        "",
        "## Code fixture guidance",
        "",
        "| Statistic | Count | Percentage | Denominator |",
        "|---|---|---|---|",
        f"| Coded `yes` | {results['yes']:,} | {pct(_ratio(results['yes'], total))} | "
        f"{total:,} repositories with a guidance file |",
        "",
        "## By primary language",
        "",
        "| Language | With guidance file | Coded `yes` | Percentage |",
        "|---|---|---|---|",
    ]
    for language in DISPLAY_LANGUAGES:
        denominator = results["with_guidance_file"][language]
        yes = results["yes_by_language"][language]
        lines.append(f"| {DISPLAY_LABELS[language]} | {denominator:,} | {yes:,} | {pct(_ratio(yes, denominator))} |")
    lines += [
        "",
        "## Keyword search precision",
        "",
        "| Coding | Repositories | Percentage of repositories with a fixture match |",
        "|---|---|---|",
    ]
    for value in DECISION_VALUES:
        lines.append(f"| `{value}` | {results[value]:,} | {pct(_ratio(results[value], matched))} |")
    lines += [
        f"| Total | {matched:,} | -- |",
        "",
        f"Precision: {results['yes']:,} of {matched:,} ({pct(_ratio(results['yes'], matched))}); "
        f"{results['unsure']:,} coded `unsure`.",
        "",
        "## Categories",
        "",
    ]
    if results["uncategorised"]:
        lines.append(
            f"Pending: {results['uncategorised']:,} of {results['yes']:,} repositories coded `yes` "
            "have no category yet. Categories are coded after the decisions."
        )
    else:
        lines += [
            "Repositories coded `yes` per category. A repository can have more than one category.",
            "",
            "| Category | Repositories |",
            "|---|---|",
        ]
        for category, count in sorted(results["categories"].items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"| {category} | {count:,} |")
    lines.append("")
    return "\n".join(lines)


def write_report(
    output_dir: Path = OUTPUT_DIR,
    *,
    sheet_path: Path = SHEET_PATH,
    db_path: Path = DB_PATH,
    decisions_only: bool = False,
) -> Path:
    coded = load_coded_sheet(sheet_path, decisions_only=decisions_only)
    results = compute_results(coded, guidance_file_counts(db_path))
    return write_markdown_report(output_dir, "rq5_coding.md", generate_report(results))


def main() -> None:
    parser = argparse.ArgumentParser(description="RQ5 results from the completed repository-level coding sheet.")
    parser.add_argument("--sheet", type=Path, default=SHEET_PATH, help=f"Coding sheet (default: {SHEET_PATH})")
    parser.add_argument(
        "--decisions-only",
        action="store_true",
        help="Accept `yes` rows without a category and mark the categories section pending.",
    )
    args = parser.parse_args()
    try:
        path = write_report(sheet_path=args.sheet, decisions_only=args.decisions_only)
    except CodingIncompleteError as exc:
        raise SystemExit(str(exc)) from None
    print(f"RQ5 coding report written to {path}")


if __name__ == "__main__":
    main()
