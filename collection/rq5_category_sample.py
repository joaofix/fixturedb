"""
RQ5 category coding: a random sample of the repositories coded `yes`, coded
with this study's own categories of fixture guidance.

- `sample` writes `research-questions/rq5/rq5_category_sample.csv`: every
  repository coded `yes` in `rq5_repository_coding_sheet.csv`, in one random
  permutation (seed `SAMPLE_SEED`, not stratified), with empty coding columns
  (the matched lines are read in `rq5_snippets.md`). Rows are coded from the
  top; the first `CHECKPOINTS` rows are the Cochran sample sizes for a 10% and
  a 5% margin of error. It also writes an empty `rq5_category_codebook.yaml` when there is none.
  This is how the sample of the first coding pass (556 repositories) was made.
  The decision review of 2026-10-13 changed the `yes` population to 586 (8
  left, 38 joined), and the sample was rebuilt once, by hand, as a proportional
  stratified sample (`sampling_design()`, `TOP_UP_SEED`): the coded rows of the
  556 that are still `yes` keep their order and coding, and the 38 are
  interleaved at the same rate. `sample` is not run again.
- `agreement-sheet` draws `AGREEMENT_SIZE` repositories (seed `AGREEMENT_SEED`)
  from the coded prefix and writes `rq5_agreement_sheet.csv` for a second coder.
- `agreement` compares the two codings: percent agreement and Cohen's kappa
  per category.

Only reads the repository coding sheet; never writes it, and never overwrites a
sheet that holds coding. The coders' instructions are in
`research-questions/rq5/CATEGORY_CODING.md`.

python -m collection.rq5_category_sample sample
python -m collection.rq5_category_sample agreement-sheet
python -m collection.rq5_category_sample agreement
"""

from __future__ import annotations

import argparse
import csv
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .rq5_agent_file_scan import (
    CSV_OUTPUT_DIR,
    DECISION_VALUES,
    REPOSITORY_SHEET_NAME,
)
from .sampling import cochran_sample_size, margin_of_error

SAMPLE_SEED = 20261012
AGREEMENT_SEED = 20261013
AGREEMENT_SIZE = 20
CONFIDENCE_Z = 1.96  # 95% confidence
CHECKPOINT_MARGINS: tuple[float, ...] = (0.10, 0.05)
# The design fixes the population (the repositories coded `yes`) and the
# checkpoints derived from it; a different count means the coding sheet changed.
EXPECTED_POPULATION = 556
EXPECTED_CHECKPOINTS: tuple[int, ...] = (83, 228)
# The one-time rebuild after the 2026-10-13 decision review (see the module
# docstring): strata, the seed of the added stratum, and the checkpoints of the
# rebuilt sample (88 = the 82 coded rows still `yes` + 6 of the 38 added, the
# first size >= Cochran's 83 for N = 586 where both strata have the same rate).
TOP_UP_SEED = 20261014
ORIGINAL_STRATUM = 548  # coded `yes` in the first pass and still `yes`
ADDED_STRATUM = 38  # coded `yes` in the review
REVIEWED_POPULATION = ORIGINAL_STRATUM + ADDED_STRATUM
REVIEWED_CHECKPOINTS: tuple[int, ...] = (88, 233)

SAMPLE_NAME = "rq5_category_sample.csv"
CODEBOOK_NAME = "rq5_category_codebook.yaml"
AGREEMENT_SHEET_NAME = "rq5_agreement_sheet.csv"
SAMPLE_CODING_COLUMNS: tuple[str, ...] = ("open_code", "categories", "notes")
SAMPLE_FIELDNAMES: tuple[str, ...] = (
    "sample_order",
    "checkpoint",
    "repository",
    *SAMPLE_CODING_COLUMNS,
)
AGREEMENT_FIELDNAMES: tuple[str, ...] = ("sample_order", "repository", "categories")
CODE_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
CODEBOOK_TEMPLATE = """\
# RQ5 categories of fixture guidance: this study's own, built by open coding
# rq5_category_sample.csv. One entry per category:
#   - code: one word, snake_case (the value used in the sheets' `categories`)
#     name: short display name
#     definition: what a repository's guidance must say to get this category
#     note: optional, a hint for coders on a boundary case (not shown in results)
categories: []
"""


class CategoryCodingError(ValueError):
    """A category sheet or the codebook is inconsistent."""


# --------------------------------------------------------------------------
# Population and checkpoints
# --------------------------------------------------------------------------


def checkpoint_sizes(
    population: int, margins: tuple[float, ...] = CHECKPOINT_MARGINS, confidence_z: float = CONFIDENCE_Z
) -> tuple[int, ...]:
    """Cochran sample sizes (p = 0.5, finite population correction, rounded
    up) for each margin of error."""
    return tuple(cochran_sample_size(population, margin, confidence_z) for margin in margins)


def check_checkpoints(
    population: int,
    *,
    expected_population: int | None = EXPECTED_POPULATION,
    expected_checkpoints: tuple[int, ...] | None = EXPECTED_CHECKPOINTS,
) -> tuple[int, ...]:
    """The checkpoint sizes for `population`, failing loudly if the population
    or the sizes are not the ones the design fixed (pass `None` to skip a
    check)."""
    if expected_population is not None and population != expected_population:
        raise CategoryCodingError(
            f"{population} repositories are coded yes, but the category design fixes the population at "
            f"{expected_population}; the repository coding sheet changed"
        )
    sizes = checkpoint_sizes(population)
    if expected_checkpoints is not None and sizes != tuple(expected_checkpoints):
        raise CategoryCodingError(
            f"Cochran checkpoints for N={population} are {sizes}, expected {tuple(expected_checkpoints)}"
        )
    return sizes


def sampling_design(population: int) -> str:
    """How the sample of `population` repositories is ordered, for the report:
    the rebuilt, stratified sample for the reviewed population, otherwise the
    single permutation written by `sample`."""
    if population == REVIEWED_POPULATION:
        return (
            f"a proportional stratified random sample: the {ORIGINAL_STRATUM:,} repositories coded `yes` in "
            f"the first pass and still `yes`, in their random order (seed {SAMPLE_SEED}), and the "
            f"{ADDED_STRATUM:,} coded `yes` in the decision review, in a random order (seed {TOP_UP_SEED}), "
            "interleaved so that every checkpoint holds both at the same rate"
        )
    return f"one random permutation (seed {SAMPLE_SEED}, not stratified)"


def sample_margin_of_error(sample_size: int, population: int) -> float:
    """Margin of error at 95% confidence for `sample_size` of `population`."""
    return margin_of_error(sample_size, population, CONFIDENCE_Z)


def load_yes_population(sheet_path: Path) -> list[dict[str, Any]]:
    """The repositories coded `yes`, in the coding sheet's order, each with its
    1-based row in the sheet (= its section in `rq5_snippets.md`). Fails if any
    row is undecided or has an unknown decision: the population must be final."""
    with sheet_path.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    problems = [
        f"{row['repository']}: decision {row['decision']!r}"
        for row in rows
        if row["decision"].strip().lower() not in DECISION_VALUES
    ]
    if problems:
        shown = "; ".join(problems[:10]) + (" ..." if len(problems) > 10 else "")
        raise CategoryCodingError(f"{sheet_path} has {len(problems)} rows without a final decision: {shown}")
    return [
        {"repository": row["repository"], "sheet_row": index}
        for index, row in enumerate(rows, start=1)
        if row["decision"].strip().lower() == "yes"
    ]


def shuffle_population(population: list[dict[str, Any]], seed: int = SAMPLE_SEED) -> list[dict[str, Any]]:
    """One simple random permutation of `population` (input order kept fixed
    by the caller), reproducible from `seed`."""
    shuffled = list(population)
    random.Random(seed).shuffle(shuffled)
    return shuffled


# --------------------------------------------------------------------------
# Writing the sheets
# --------------------------------------------------------------------------


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _has_coding(path: Path, columns: tuple[str, ...]) -> bool:
    return path.exists() and any((row.get(c) or "").strip() for row in _read_rows(path) for c in columns)


def write_codebook_template(output_dir: Path = CSV_OUTPUT_DIR) -> Path | None:
    """Write an empty `rq5_category_codebook.yaml`, unless one already exists."""
    path = output_dir / CODEBOOK_NAME
    if path.exists():
        return None
    path.write_text(CODEBOOK_TEMPLATE, encoding="utf-8")
    return path


def write_category_sample(
    output_dir: Path = CSV_OUTPUT_DIR,
    *,
    seed: int = SAMPLE_SEED,
    expected_population: int | None = EXPECTED_POPULATION,
    expected_checkpoints: tuple[int, ...] | None = EXPECTED_CHECKPOINTS,
) -> Path:
    """Write `rq5_category_sample.csv` (see the module docstring) from the
    repository coding sheet in `output_dir`. Raises rather than overwrite a
    sample that holds coding."""
    path = output_dir / SAMPLE_NAME
    if _has_coding(path, SAMPLE_CODING_COLUMNS):
        raise CategoryCodingError(f"{path} already holds coding; refusing to overwrite it")
    population = load_yes_population(output_dir / REPOSITORY_SHEET_NAME)
    sizes = check_checkpoints(
        len(population), expected_population=expected_population, expected_checkpoints=expected_checkpoints
    )

    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=SAMPLE_FIELDNAMES)
        writer.writeheader()
        for order, repo in enumerate(shuffle_population(population, seed), start=1):
            writer.writerow(
                {
                    "sample_order": order,
                    "checkpoint": checkpoint_label(order, sizes),
                    "repository": repo["repository"],
                    **dict.fromkeys(SAMPLE_CODING_COLUMNS, ""),
                }
            )
    return path


def checkpoint_label(order: int, sizes: tuple[int, ...]) -> str:
    """The first checkpoint whose sample includes row `order`, or "" past the last."""
    for size in sorted(sizes):
        if order <= size:
            return str(size)
    return ""


# --------------------------------------------------------------------------
# Reading the coding
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Category:
    code: str
    name: str
    definition: str


def load_codebook(path: Path) -> list[Category]:
    """The categories of `rq5_category_codebook.yaml`, validated: each has a
    snake_case `code`, a `name` and a `definition`, and codes are unique."""
    if not path.exists():
        raise CategoryCodingError(f"{path} does not exist; run `python -m collection.rq5_category_sample sample`")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = data.get("categories") or []
    if not isinstance(entries, list):
        raise CategoryCodingError(f"{path}: `categories` must be a list")
    categories: list[Category] = []
    problems: list[str] = []
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            problems.append(f"entry {index} is not a mapping")
            continue
        code, name, definition = (str(entry.get(k) or "").strip() for k in ("code", "name", "definition"))
        if not CODE_PATTERN.match(code):
            problems.append(f"entry {index}: code {code!r} is not one snake_case word")
        if not name or not definition:
            problems.append(f"entry {index} ({code}): name and definition are required")
        categories.append(Category(code, name, definition))
    codes = [c.code for c in categories]
    duplicates = sorted({c for c in codes if codes.count(c) > 1})
    if duplicates:
        problems.append(f"duplicate codes: {', '.join(duplicates)}")
    if problems:
        raise CategoryCodingError(f"{path} is invalid:\n" + "\n".join(problems))
    return categories


def parse_categories(value: str) -> list[str]:
    return [c.strip() for c in (value or "").split(";") if c.strip()]


def _unknown_codes(rows: list[dict[str, str]], codes: set[str], label: str) -> list[str]:
    problems = []
    for row in rows:
        unknown = [c for c in parse_categories(row.get("categories", "")) if c not in codes]
        if unknown:
            problems.append(f"{label} {row.get('sample_order')} ({row['repository']}): not in the codebook: {', '.join(unknown)}")
    return problems


@dataclass(frozen=True)
class CodedSample:
    rows: list[dict[str, str]]  # every row of the sample, in sample order
    coded: list[dict[str, str]]  # the coded prefix
    population: int
    checkpoints: tuple[int, ...]

    @property
    def size(self) -> int:
        return len(self.coded)

    @property
    def checkpoint_reached(self) -> int | None:
        """The checkpoint the coded prefix ends exactly at, if any."""
        return self.size if self.size in self.checkpoints else None


def load_coded_sample(sample_path: Path, codebook: list[Category]) -> CodedSample:
    """The coded prefix of `rq5_category_sample.csv`: the rows from
    `sample_order` 1 whose `categories` is filled, up to the first empty one.
    Fails if a row after the prefix is coded (coding out of order), if the
    rows are not in sample order, or if a code is not in the codebook."""
    rows = _read_rows(sample_path)
    orders = [int(row["sample_order"]) for row in rows]
    if orders != list(range(1, len(rows) + 1)):
        raise CategoryCodingError(f"{sample_path}: rows are not in sample_order 1..{len(rows)}")
    filled = [bool(parse_categories(row["categories"])) for row in rows]
    prefix = filled.index(False) if False in filled else len(rows)
    out_of_order = [rows[i] for i in range(prefix, len(rows)) if filled[i]]
    problems = []
    if out_of_order:
        shown = ", ".join(f"{r['sample_order']} ({r['repository']})" for r in out_of_order[:10])
        problems.append(
            f"coding out of order: the coded prefix ends at sample_order {prefix}, but these later rows have "
            f"categories: {shown}"
        )
    problems += _unknown_codes(rows, {c.code for c in codebook}, "sample_order")
    if problems:
        raise CategoryCodingError(f"{sample_path} is inconsistent:\n" + "\n".join(problems))
    checkpoints = tuple(sorted({int(row["checkpoint"]) for row in rows if row["checkpoint"].strip()}))
    return CodedSample(rows=rows, coded=rows[:prefix], population=len(rows), checkpoints=checkpoints)


def check_sample_matches_population(sample: CodedSample, sheet_path: Path) -> None:
    """Fail if the sample's repositories are not exactly the repositories coded
    `yes` in the coding sheet (the sample is stale)."""
    yes = {repo["repository"] for repo in load_yes_population(sheet_path)}
    sampled = {row["repository"] for row in sample.rows}
    if yes != sampled:
        added, dropped = sorted(yes - sampled), sorted(sampled - yes)
        raise CategoryCodingError(
            f"the category sample no longer matches the repositories coded yes "
            f"(now yes but not sampled: {added[:5]}; sampled but no longer yes: {dropped[:5]})"
        )


# --------------------------------------------------------------------------
# Agreement
# --------------------------------------------------------------------------


def write_agreement_sheet(
    output_dir: Path = CSV_OUTPUT_DIR, *, seed: int = AGREEMENT_SEED, size: int = AGREEMENT_SIZE
) -> Path:
    """Draw `size` repositories at random from the coded prefix of the sample
    and write `rq5_agreement_sheet.csv` with an empty `categories` column, in
    sample order (the matched lines are read in `rq5_snippets.md`). Raises
    rather than overwrite a sheet that holds coding."""
    path = output_dir / AGREEMENT_SHEET_NAME
    if _has_coding(path, ("categories",)):
        raise CategoryCodingError(f"{path} already holds coding; refusing to overwrite it")
    codebook = load_codebook(output_dir / CODEBOOK_NAME)
    sample = load_coded_sample(output_dir / SAMPLE_NAME, codebook)
    if sample.size < size:
        raise CategoryCodingError(f"the coded prefix has {sample.size} repositories; {size} are needed")
    drawn = sorted(random.Random(seed).sample(sample.coded, size), key=lambda r: int(r["sample_order"]))
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=AGREEMENT_FIELDNAMES)
        writer.writeheader()
        for row in drawn:
            writer.writerow({**{k: row[k] for k in AGREEMENT_FIELDNAMES if k != "categories"}, "categories": ""})
    return path


def cohens_kappa(first: list[bool], second: list[bool]) -> float | None:
    """Cohen's kappa for two coders' yes/no judgements of the same items, or
    None when it is undefined (chance agreement is 1: both coders gave every
    item the same single value)."""
    if len(first) != len(second) or not first:
        raise ValueError("both codings must judge the same, non-empty list of items")
    n = len(first)
    observed = sum(a == b for a, b in zip(first, second)) / n
    p_first, p_second = sum(first) / n, sum(second) / n
    expected = p_first * p_second + (1 - p_first) * (1 - p_second)
    if expected == 1:
        return None
    return (observed - expected) / (1 - expected)


@dataclass(frozen=True)
class AgreementResult:
    items: int
    per_category: list[tuple[Category, float, float | None]]  # (category, percent agreement, kappa)

    @property
    def mean_agreement(self) -> float:
        return sum(a for _, a, _ in self.per_category) / len(self.per_category)

    @property
    def mean_kappa(self) -> float | None:
        kappas = [k for _, _, k in self.per_category if k is not None]
        return sum(kappas) / len(kappas) if kappas else None


def compare_codings(
    first: dict[str, set[str]], second: dict[str, set[str]], codebook: list[Category]
) -> AgreementResult:
    """Per category, each repository is yes/no for that category in each
    coding; percent agreement and Cohen's kappa over the repositories both
    codings share."""
    if set(first) != set(second):
        raise CategoryCodingError("the two codings do not cover the same repositories")
    if not codebook:
        raise CategoryCodingError("the codebook has no categories")
    repos = sorted(first)
    per_category = []
    for category in codebook:
        a = [category.code in first[r] for r in repos]
        b = [category.code in second[r] for r in repos]
        agreement = sum(x == y for x, y in zip(a, b)) / len(repos)
        per_category.append((category, agreement, cohens_kappa(a, b)))
    return AgreementResult(items=len(repos), per_category=per_category)


def load_agreement(output_dir: Path, codebook: list[Category], sample: CodedSample) -> AgreementResult | None:
    """The agreement between the sample and `rq5_agreement_sheet.csv`, or None
    if the sheet does not exist or is not fully coded yet."""
    path = output_dir / AGREEMENT_SHEET_NAME
    if not path.exists():
        return None
    rows = _read_rows(path)
    if not rows or not all(parse_categories(row["categories"]) for row in rows):
        return None
    problems = _unknown_codes(rows, {c.code for c in codebook}, "sample_order")
    coded = {row["repository"]: set(parse_categories(row["categories"])) for row in sample.coded}
    outside = [row["repository"] for row in rows if row["repository"] not in coded]
    if outside:
        problems.append(f"not in the coded prefix of the sample: {', '.join(outside)}")
    if problems:
        raise CategoryCodingError(f"{path} is inconsistent:\n" + "\n".join(problems))
    second = {row["repository"]: set(parse_categories(row["categories"])) for row in rows}
    first = {repo: coded[repo] for repo in second}
    return compare_codings(first, second, codebook)


def agreement_status(output_dir: Path) -> tuple[int, int] | None:
    """(coded rows, total rows) of the agreement sheet, or None if absent."""
    path = output_dir / AGREEMENT_SHEET_NAME
    if not path.exists():
        return None
    rows = _read_rows(path)
    return sum(bool(parse_categories(r["categories"])) for r in rows), len(rows)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="RQ5 category coding: sample, agreement sheet, agreement.")
    parser.add_argument("command", choices=("sample", "agreement-sheet", "agreement"))
    parser.add_argument("--output-dir", type=Path, default=CSV_OUTPUT_DIR, help=f"default: {CSV_OUTPUT_DIR}")
    args = parser.parse_args()
    out: Path = args.output_dir
    try:
        if args.command == "sample":
            path = write_category_sample(out)
            sizes = checkpoint_sizes(EXPECTED_POPULATION)
            print(f"Category sample written to {path} (seed {SAMPLE_SEED}, checkpoints {sizes})")
            codebook = write_codebook_template(out)
            print(f"Empty codebook written to {codebook}" if codebook else f"Kept the existing {out / CODEBOOK_NAME}")
        elif args.command == "agreement-sheet":
            path = write_agreement_sheet(out)
            print(f"Agreement sheet with {AGREEMENT_SIZE} repositories (seed {AGREEMENT_SEED}) written to {path}")
        else:
            codebook = load_codebook(out / CODEBOOK_NAME)
            sample = load_coded_sample(out / SAMPLE_NAME, codebook)
            result = load_agreement(out, codebook, sample)
            if result is None:
                status = agreement_status(out)
                raise CategoryCodingError(
                    f"{out / AGREEMENT_SHEET_NAME} is "
                    + ("missing" if status is None else f"not fully coded ({status[0]} of {status[1]} rows)")
                )
            print(f"Agreement over {result.items} repositories")
            for category, agreement, kappa in result.per_category:
                print(f"  {category.code}: agreement {agreement:.1%}, kappa {'n/a' if kappa is None else f'{kappa:.2f}'}")
            mean_kappa = result.mean_kappa
            print(
                f"  mean: agreement {result.mean_agreement:.1%}, "
                f"kappa {'n/a' if mean_kappa is None else f'{mean_kappa:.2f}'}"
            )
    except CategoryCodingError as exc:
        raise SystemExit(str(exc)) from None


if __name__ == "__main__":
    main()
