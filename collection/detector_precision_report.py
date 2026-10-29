"""Manual-validation precision report for the four detector precision
checks: mock detection, pytest scope classification, unittest detection,
and bare before/after.

Reads the rated CSVs `collection.detector_precision_sampling` produces
(`label` column: true_positive/false_positive/unsure, filled in by a
single reviewer -- see `validation-samples/README_detector_precision_validation.md`) and
computes, per case ONLY (not per language or dataset -- the strata are
too small for a separate estimate once split that finely):

    precision = true_positive / (true_positive + false_positive)

`unsure` is reported separately (`unsure_rate = count_unsure /
total_labeled`) and never folded into precision in either direction.
When a case has zero false positives, the 95% upper bound of the false
positive rate is also reported, by the rule of three:
`3 / (true_positive + false_positive)` -- the same denominator precision
itself uses, not `total_labeled` (an `unsure` row was never a clear
negative or positive call to begin with, so it can't anchor an upper
bound on the false-positive rate).

Unlike `validation_v1`'s report (which excluded unrated rows with a soft
note and had a `404` label), this one is **strict**: any row still
carrying an empty `label` is a data error and `compute_precision()`
raises `ValueError` immediately, naming the case and the first unlabeled
row's identity -- there is no `404` category here (every sampled row
comes from the live final datasets) and no silent skip of incomplete
work.

python -m collection.detector_precision_report
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path

from . import paths
from .detector_precision_sampling import CASE_OUTPUT_PATHS

csv.field_size_limit(10**7)

VALID_LABELS = {"true_positive", "false_positive", "unsure"}

DEFAULT_SAMPLES_ROOT = paths.ROOT_DIR / "validation-samples"

# (case key, paper-text label) -- exhaustive: the four cases, in the
# same order CASE_OUTPUT_PATHS defines them.
COMPONENTS: tuple[tuple[str, str], ...] = (
    ("mock_detection", "mock detection"),
    ("pytest_scope", "pytest scope classification"),
    ("unittest_detection", "unittest detection"),
    ("before_after", "bare before/after"),
)


@dataclass(frozen=True)
class PrecisionResult:
    case: str
    paper_label: str
    total_sampled: int
    count_true_positive: int
    count_false_positive: int
    count_unsure: int

    @property
    def total_labeled(self) -> int:
        return self.count_true_positive + self.count_false_positive + self.count_unsure

    @property
    def clearly_labeled(self) -> int:
        """true_positive + false_positive -- precision's own denominator,
        and the rule-of-three's."""
        return self.count_true_positive + self.count_false_positive

    @property
    def precision(self) -> float | None:
        """true_positive / clearly_labeled, as a percentage -- None (not
        0.0) if clearly_labeled is 0, so "not computable" never reads as
        "0% precision"."""
        denominator = self.clearly_labeled
        return 100 * self.count_true_positive / denominator if denominator else None

    @property
    def unsure_rate(self) -> float | None:
        return 100 * self.count_unsure / self.total_labeled if self.total_labeled else None

    @property
    def rule_of_three_upper_bound(self) -> float | None:
        """95% upper bound on the false-positive rate when this case had
        zero false positives, by the rule of three (3 / clearly_labeled).
        None when there were any false positives (the rule only applies
        to a zero-event observation) or clearly_labeled is 0."""
        if self.count_false_positive != 0 or self.clearly_labeled == 0:
            return None
        return 100 * 3 / self.clearly_labeled


def compute_precision(case: str, paper_label: str, rows: list[dict]) -> PrecisionResult:
    """One PrecisionResult from `rows` (CSV DictReader rows carrying a
    `label` column). Raises ValueError on the first row whose `label` is
    empty (not yet reviewed) or outside true_positive/false_positive/
    unsure -- this check has no 404/unrated carve-out; every row must be one of
    the three real labels before this can run."""
    total_sampled = len(rows)
    count_tp = count_fp = count_unsure = 0
    for row in rows:
        label = (row.get("label") or "").strip()
        if not label:
            raise ValueError(
                f"{case}: row {row.get('github_url') or row.get('file_path')!r} "
                "has no label yet -- every sampled row must be labeled "
                "true_positive/false_positive/unsure before a report can be computed"
            )
        if label not in VALID_LABELS:
            raise ValueError(
                f"{case}: row {row.get('github_url') or row.get('file_path')!r} has "
                f"an invalid label {label!r} -- expected one of {sorted(VALID_LABELS)}"
            )
        if label == "true_positive":
            count_tp += 1
        elif label == "false_positive":
            count_fp += 1
        else:
            count_unsure += 1

    return PrecisionResult(
        case=case,
        paper_label=paper_label,
        total_sampled=total_sampled,
        count_true_positive=count_tp,
        count_false_positive=count_fp,
        count_unsure=count_unsure,
    )


def load_component_rows(csv_path: Path) -> list[dict]:
    with csv_path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def compute_all(samples_root: Path = DEFAULT_SAMPLES_ROOT) -> list[PrecisionResult]:
    results = []
    for case, paper_label in COMPONENTS:
        folder, filename = CASE_OUTPUT_PATHS[case]
        rows = load_component_rows(samples_root / folder / filename)
        results.append(compute_precision(case, paper_label, rows))
    return results


def _pct(value: float | None) -> str:
    return f"{value:.1f}%" if value is not None else "--"


def render_table(results: list[PrecisionResult]) -> str:
    lines = [
        "| Case | n sampled | TP | FP | Unsure | Precision | Unsure rate | "
        "Rule-of-three upper bound (95%) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r.paper_label} | {r.total_sampled} | {r.count_true_positive} | "
            f"{r.count_false_positive} | {r.count_unsure} | {_pct(r.precision)} | "
            f"{_pct(r.unsure_rate)} | {_pct(r.rule_of_three_upper_bound)} |"
        )
    return "\n".join(lines)


def render_paper_text(results: list[PrecisionResult]) -> str:
    """One line per case, in drop-in-the-paper phrasing. When there were
    zero false positives, the rule-of-three upper bound is appended
    instead of just the (potentially misleadingly clean) 100% figure."""
    lines = []
    for r in results:
        precision_str = _pct(r.precision) if r.precision is not None else "N/A"
        bound = r.rule_of_three_upper_bound
        bound_text = f"; FP rate <= {bound:.1f}% at 95% confidence (rule of three)" if bound is not None else ""
        lines.append(f"{r.paper_label} ({precision_str}, {r.count_unsure} items unsure{bound_text})")
    return "\n".join(lines)


def generate_report(samples_root: Path = DEFAULT_SAMPLES_ROOT) -> str:
    results = compute_all(samples_root)
    return (
        "# Manual Validation Precision Report\n\n"
        "Precision computed over true_positive/false_positive items only; "
        "`unsure` is reported separately (`Unsure rate`), never folded into "
        "precision. Reported per case only, not per language or dataset -- "
        "the strata are too small for a separate estimate. When a case has "
        "zero false positives, the rule-of-three 95% upper bound on the "
        "false-positive rate is also reported.\n\n"
        f"{render_table(results)}\n\n"
        "## Paper-ready text\n\n"
        f"{render_paper_text(results)}\n"
    )


def write_report(
    output_path: Path | None = None, samples_root: Path = DEFAULT_SAMPLES_ROOT
) -> Path:
    if output_path is None:
        output_path = samples_root / "precision_report.md"
    report = generate_report(samples_root)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    return output_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compute manual-validation precision for the four detector "
            "precision checks from their rated sample CSVs. Fails loudly if "
            "any row is still unlabeled."
        )
    )
    parser.add_argument("--samples-root", type=Path, default=DEFAULT_SAMPLES_ROOT)
    parser.add_argument("--output", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_path = write_report(args.output, args.samples_root)
    print(f"Precision report written to {output_path}")
    print()
    print(generate_report(args.samples_root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
