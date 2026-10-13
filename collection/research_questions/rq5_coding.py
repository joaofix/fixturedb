"""
RQ5 -- manual coding results: reads the completed repository-level coding
sheet (`research-questions/rq5/rq5_repository_coding_sheet.csv`) and computes the final RQ5
fixture-guidance numbers, then the categories of the coded part of the random
category sample (`rq5_category_sample.csv`, see `collection/rq5_category_sample.py`).

Denominators:

- repositories with a guidance file (from `db/rq5_agent_files.db`) for the
  share coded `yes`, overall and per primary language;
- repositories with a fixture keyword match (the sheet's rows) for the
  precision of the keyword search;
- the coded sample (the prefix of the category sample whose `categories` is
  filled) for the category shares.

Refuses to run while any row is uncoded or holds a value outside the allowed
ones (see `research-questions/rq5/README.md`), or while the category sample is
inconsistent (coded out of order, a code not in the codebook, stale against the
sheet). No coding is inferred here.

python -m collection.research_questions.rq5_coding
"""

from __future__ import annotations

import argparse
import csv
import statistics
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
    load_repo_languages,
)
from ..rq5_category_sample import (
    AGREEMENT_SHEET_NAME,
    CODEBOOK_NAME,
    SAMPLE_NAME,
    AgreementResult,
    CategoryCodingError,
    agreement_status,
    check_sample_matches_population,
    load_agreement,
    load_codebook,
    load_coded_sample,
    parse_categories,
    sample_margin_of_error,
    sampling_design,
)
from ._shared import OUTPUT_DIR, pct, write_markdown_report
from .rq5 import DISPLAY_LABELS, DISPLAY_LANGUAGES

SHEET_PATH = CSV_OUTPUT_DIR / REPOSITORY_SHEET_NAME


class CodingIncompleteError(ValueError):
    """The coding sheet has uncoded or invalid rows."""


def load_coded_sheet(path: Path = SHEET_PATH) -> list[dict[str, Any]]:
    """The sheet's rows, validated. Raises `CodingIncompleteError` listing every
    problem: an empty or unknown `decision`."""
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
        if not decision:
            uncoded.append(repo)
            continue
        if decision not in DECISION_VALUES:
            problems.append(f"{repo}: decision {decision!r} is not one of {DECISION_VALUES}")
        coded.append({"repository": repo, "decision": decision})

    if uncoded or problems:
        lines = []
        if uncoded:
            shown = ", ".join(uncoded[:10]) + (" ..." if len(uncoded) > 10 else "")
            lines.append(f"{len(uncoded)} of {len(rows)} rows are still uncoded (decision empty): {shown}")
        lines += problems
        raise CodingIncompleteError(f"{path} is not fully coded:\n" + "\n".join(lines))
    return coded


def attach_languages(coded: list[dict[str, Any]], languages: dict[str, str]) -> list[dict[str, Any]]:
    """`coded` with each repository's primary language (from the scan
    database; the coding sheet does not repeat it)."""
    missing = [row["repository"] for row in coded if row["repository"] not in languages]
    if missing:
        raise CodingIncompleteError(f"no language in the scan database for: {', '.join(missing[:10])}")
    return [{**row, "language": languages[row["repository"]]} for row in coded]


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
    return {
        "with_guidance_file": with_guidance_file,
        "with_fixture_match": len(coded),
        "yes": decisions["yes"],
        "no": decisions["no"],
        "yes_by_language": yes_by_language,
    }


def compute_category_results(
    sheet_path: Path = SHEET_PATH, languages: dict[str, str] | None = None
) -> dict[str, Any] | None:
    """The category analysis of the coded prefix of the category sample next
    to `sheet_path`, or None if the sample has not been written yet. Primary
    languages come from `languages` (default: the scan database)."""
    directory = sheet_path.parent
    sample_path = directory / SAMPLE_NAME
    if not sample_path.exists():
        return None
    codebook = load_codebook(directory / CODEBOOK_NAME)
    sample = load_coded_sample(sample_path, codebook)
    check_sample_matches_population(sample, sheet_path)

    languages = load_repo_languages() if languages is None else languages
    unknown = [row["repository"] for row in sample.rows if row["repository"] not in languages]
    if unknown:
        raise CategoryCodingError(f"no language in the scan database for: {', '.join(unknown[:10])}")
    coded = sample.coded
    per_repo = [set(parse_categories(row["categories"])) for row in coded]
    sizes = [len(codes) for codes in per_repo]
    return {
        "population": sample.population,
        "checkpoints": sample.checkpoints,
        "size": sample.size,
        "checkpoint_reached": sample.checkpoint_reached,
        "margin_of_error": sample_margin_of_error(sample.size, sample.population) if coded else None,
        "codebook": codebook,
        "category_counts": Counter(code for codes in per_repo for code in codes),
        "categories_per_repository": (statistics.median(sizes), min(sizes), max(sizes)) if sizes else None,
        "sample_languages": Counter(languages[row["repository"]] for row in coded),
        "population_languages": Counter(languages[row["repository"]] for row in sample.rows),
        "agreement": load_agreement(directory, codebook, sample) if coded else None,
        "agreement_status": agreement_status(directory),
    }


def checkpoint_warning(category: dict[str, Any] | None) -> str | None:
    """A warning when the coded prefix does not end exactly at a checkpoint."""
    if not category or not category["size"] or category["checkpoint_reached"] is not None:
        return None
    return (
        f"The coded category sample has {category['size']} repositories, which is not a checkpoint "
        f"({', '.join(str(c) for c in category['checkpoints'])}); the results use the actual size."
    )


def _ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else numerator / denominator


def _kappa(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def render_category_section(category: dict[str, Any] | None) -> list[str]:
    lines = ["## Categories", ""]
    if category is None:
        return [*lines, f"Not started: `research-questions/rq5/{SAMPLE_NAME}` has not been written yet.", ""]
    population, size = category["population"], category["size"]
    checkpoints = " and ".join(str(c) for c in category["checkpoints"])
    if not size:
        return [
            *lines,
            f"Not coded yet: none of the {population:,} repositories in `research-questions/rq5/{SAMPLE_NAME}` "
            f"has categories (checkpoints {checkpoints}).",
            "",
        ]
    reached = category["checkpoint_reached"]
    checkpoint_text = (
        f"checkpoint {reached} reached"
        if reached is not None
        else f"no checkpoint reached ({checkpoints}): the coded prefix stops at {size}"
    )
    lines += [
        "### Sampling",
        "",
        f"Population: the {population:,} repositories coded `yes`, ordered as {sampling_design(population)}; "
        f"coded from the top; {checkpoint_text}. Sample size: {size:,}. "
        f"Confidence: 95%. Margin of error: {pct(category['margin_of_error'])} (p = 0.5, with the finite "
        "population correction).",
        "",
        "### Categories of fixture guidance",
        "",
        "| Category | Definition | Repositories | % of sample |",
        "|---|---|---|---|",
    ]
    counts = category["category_counts"]
    # Most frequent first; ties keep the codebook order.
    for entry in sorted(category["codebook"], key=lambda e: -counts[e.code]):
        count = counts[entry.code]
        lines.append(f"| {entry.name} | {entry.definition} | {count:,} | {pct(_ratio(count, size))} |")
    median, minimum, maximum = category["categories_per_repository"]
    lines += [
        "",
        "A repository can belong to several categories, so percentages do not add up to 100%.",
        "",
        f"Categories per repository: median {median:g}, minimum {minimum}, maximum {maximum}.",
        "",
        "### Languages",
        "",
        f"| Language | Coded sample (n = {size:,}) | % | All `yes` repositories (N = {population:,}) | % |",
        "|---|---|---|---|---|",
    ]
    sample_languages, population_languages = category["sample_languages"], category["population_languages"]
    for language in DISPLAY_LANGUAGES:
        s, p = sample_languages[language], population_languages[language]
        lines.append(
            f"| {DISPLAY_LABELS[language]} | {s:,} | {pct(_ratio(s, size))} | {p:,} | {pct(_ratio(p, population))} |"
        )
    lines += ["", "### Agreement", ""]
    agreement: AgreementResult | None = category["agreement"]
    status = category["agreement_status"]
    if agreement is None:
        lines.append(
            "No second coding yet."
            if status is None
            else f"Pending: `{AGREEMENT_SHEET_NAME}` has {status[0]} of {status[1]} repositories coded."
        )
    else:
        lines += [
            f"A second coder coded {agreement.items} repositories drawn at random from the coded sample. Per "
            "category, each repository counts as yes or no for that category in each coding.",
            "",
            "| Category | Agreement | Cohen's kappa |",
            "|---|---|---|",
        ]
        for entry, share, kappa in agreement.per_category:
            lines.append(f"| {entry.name} | {pct(share)} | {_kappa(kappa)} |")
        lines.append(f"| Average | {pct(agreement.mean_agreement)} | {_kappa(agreement.mean_kappa)} |")
        if any(kappa is None for _, _, kappa in agreement.per_category):
            lines += [
                "",
                "n/a: kappa is undefined when both coders gave every repository the same value; the average "
                "kappa leaves those categories out.",
            ]
    lines.append("")
    return lines


def generate_report(results: dict[str, Any], category: dict[str, Any] | None = None) -> str:
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
        f"Precision: {results['yes']:,} of {matched:,} ({pct(_ratio(results['yes'], matched))}).",
        "",
    ]
    lines += render_category_section(category)
    return "\n".join(lines)


def write_report(
    output_dir: Path = OUTPUT_DIR, *, sheet_path: Path = SHEET_PATH, db_path: Path = DB_PATH
) -> tuple[Path, str | None]:
    """Write `rq5_coding.md`; returns its path and the checkpoint warning, if any."""
    languages = load_repo_languages(db_path)
    coded = attach_languages(load_coded_sheet(sheet_path), languages)
    results = compute_results(coded, guidance_file_counts(db_path))
    category = compute_category_results(sheet_path, languages)
    path = write_markdown_report(output_dir, "rq5_coding.md", generate_report(results, category))
    return path, checkpoint_warning(category)


def main() -> None:
    parser = argparse.ArgumentParser(description="RQ5 results from the completed repository-level coding sheet.")
    parser.add_argument("--sheet", type=Path, default=SHEET_PATH, help=f"Coding sheet (default: {SHEET_PATH})")
    args = parser.parse_args()
    try:
        path, warning = write_report(sheet_path=args.sheet)
    except (CodingIncompleteError, CategoryCodingError) as exc:
        raise SystemExit(str(exc)) from None
    if warning:
        print(f"WARNING: {warning}")
    print(f"RQ5 coding report written to {path}")


if __name__ == "__main__":
    main()
