"""Manual-validation precision report for the two remaining detector
precision checks: mock detection and the pytest setup/teardown/
setup_and_teardown lifecycle heuristic.

Reads the two rated CSVs `collection.detection_validation_sampling`
produces (`rater_label` column: TP/FP/Unsure/404, filled in by a single
reviewer -- see `validation-samples/README_detection_validation.md`) and
computes ONE precision number per file, over clearly-labeled items only:

    precision = TP / (TP + FP)

`Unsure` is reported separately (`unsure_rate = count_unsure /
effective_n`) and never folded into precision in either direction. This
replaces an earlier standard/conservative precision split (`Unsure`
folded into the denominator for a "conservative" figure) -- that
calculation doesn't exist anywhere in this codebase, this module included;
there is deliberately no second precision number computed here.

mock-type classification was dropped entirely from manual validation (see
`detection_validation_sampling.py`'s module docstring) and is never
referenced here -- there is no third row, and `mock_type_sample.csv` is
never loaded or expected to exist.

`404` rows (source no longer accessible) are excluded from
`effective_n` -- not counted as FP, not counted anywhere else. A row with
an empty `rater_label` (not yet reviewed) is excluded from every count
here too, and reported separately (`count_unrated`) rather than treated
as any of the four real labels. A row whose `rater_label` is something
other than TP/FP/Unsure/404/empty is a data error, not a silent
no-op -- `compute_precision()` raises rather than ignoring it.

python -m collection.detection_validation_report
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path

from . import paths

csv.field_size_limit(10**7)

VALID_LABELS = {"TP", "FP", "Unsure", "404"}

DEFAULT_SAMPLES_ROOT = paths.ROOT_DIR / "validation-samples"

# (table label, paper-text label, CSV path relative to DEFAULT_SAMPLES_ROOT)
# -- exhaustive: the two remaining validated components. mock-type is
# gone, deliberately not listed here (see module docstring).
COMPONENTS: tuple[tuple[str, str, str], ...] = (
    ("Mock detection", "mock detection", "mock-detection/mock_detection_sample.csv"),
    (
        "Pytest lifecycle heuristic",
        "the pytest lifecycle heuristic",
        "pytest-lifecycle/pytest_lifecycle_sample.csv",
    ),
)


@dataclass(frozen=True)
class PrecisionResult:
    component: str
    paper_label: str
    total_sampled: int
    count_404: int
    count_unrated: int
    effective_n: int
    count_tp: int
    count_fp: int
    count_unsure: int

    @property
    def precision(self) -> float | None:
        """TP / (TP + FP), as a percentage -- None if there are no TP/FP
        rows at all (nothing to divide), not 0.0 (which would misleadingly
        read as "0% precision" instead of "not computable")."""
        denominator = self.count_tp + self.count_fp
        return 100 * self.count_tp / denominator if denominator else None

    @property
    def unsure_rate(self) -> float | None:
        """count_unsure / effective_n, as a percentage -- reported
        alongside precision, never combined into it. None if effective_n
        is 0 (nothing to rate at all)."""
        return 100 * self.count_unsure / self.effective_n if self.effective_n else None


def compute_precision(component: str, paper_label: str, rows: list[dict]) -> PrecisionResult:
    """One PrecisionResult from `rows` (CSV DictReader rows carrying a
    `rater_label` column). Raises ValueError on any rater_label value
    outside TP/FP/Unsure/404/empty -- a data error, not something to
    silently drop.

    total_sampled is `len(rows)` -- the original sample size, before any
    exclusion (unrated rows included). effective_n excludes both 404s and
    still-unrated rows, so count_tp + count_fp + count_unsure ==
    effective_n always holds by construction (see the module docstring
    for why unrated rows are excluded, not treated as one of the four
    real labels)."""
    total_sampled = len(rows)
    count_unrated = 0
    labels: list[str] = []
    for row in rows:
        label = (row.get("rater_label") or "").strip()
        if not label:
            count_unrated += 1
            continue
        if label not in VALID_LABELS:
            raise ValueError(
                f"{component}: row {row.get('id')!r} has an invalid rater_label "
                f"{label!r} -- expected one of {sorted(VALID_LABELS)} or empty"
            )
        labels.append(label)

    count_404 = labels.count("404")
    effective_labels = [label for label in labels if label != "404"]
    effective_n = len(effective_labels)
    count_tp = effective_labels.count("TP")
    count_fp = effective_labels.count("FP")
    count_unsure = effective_labels.count("Unsure")

    assert count_tp + count_fp + count_unsure == effective_n  # sanity check, per spec

    return PrecisionResult(
        component=component,
        paper_label=paper_label,
        total_sampled=total_sampled,
        count_404=count_404,
        count_unrated=count_unrated,
        effective_n=effective_n,
        count_tp=count_tp,
        count_fp=count_fp,
        count_unsure=count_unsure,
    )


def load_component_rows(csv_path: Path) -> list[dict]:
    with csv_path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def compute_all(samples_root: Path = DEFAULT_SAMPLES_ROOT) -> list[PrecisionResult]:
    results = []
    for table_label, paper_label, relative_path in COMPONENTS:
        rows = load_component_rows(samples_root / relative_path)
        results.append(compute_precision(table_label, paper_label, rows))
    return results


def _pct(value: float | None) -> str:
    return f"{value:.1f}%" if value is not None else "--"


def render_table(results: list[PrecisionResult]) -> str:
    lines = [
        "| Component | n sampled | 404 excluded | Effective n | TP | FP | Unsure | "
        "Precision | Unsure rate |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r.component} | {r.total_sampled} | {r.count_404} | {r.effective_n} | "
            f"{r.count_tp} | {r.count_fp} | {r.count_unsure} | "
            f"{_pct(r.precision)} | {_pct(r.unsure_rate)} |"
        )
    return "\n".join(lines)


def render_paper_text(results: list[PrecisionResult]) -> str:
    """One line per component, in the exact drop-in-the-paper phrasing:
    "<paper_label> (X%, Y items unsure)"."""
    lines = []
    for r in results:
        precision_str = _pct(r.precision) if r.precision is not None else "N/A"
        lines.append(f"{r.paper_label} ({precision_str}, {r.count_unsure} items unsure)")
    return "\n".join(lines)


def generate_report(samples_root: Path = DEFAULT_SAMPLES_ROOT) -> str:
    results = compute_all(samples_root)
    unrated_note = ""
    unrated_total = sum(r.count_unrated for r in results)
    if unrated_total:
        unrated_lines = "\n".join(
            f"- {r.component}: {r.count_unrated} row(s) not yet rated"
            for r in results
            if r.count_unrated
        )
        unrated_note = (
            "\n\n**Note:** some rows are not yet rated (empty `rater_label`) and are "
            f"excluded from every count below, not treated as TP/FP/Unsure/404:\n\n{unrated_lines}"
        )
    return (
        "# Manual Validation Precision Report\n\n"
        "Precision computed only over clearly-labeled TP/FP items; `Unsure` is "
        "reported separately (`unsure_rate`), never folded into precision. "
        "`404` rows (source no longer accessible) are excluded from `effective_n` "
        "entirely, not counted as FP.\n\n"
        f"{render_table(results)}\n\n"
        "## Paper-ready text\n\n"
        f"{render_paper_text(results)}\n"
        f"{unrated_note}\n"
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
            "Compute manual-validation precision for mock detection and the "
            "pytest lifecycle heuristic from their rated sample CSVs."
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
