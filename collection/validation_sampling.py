"""Cochran-formula manual-validation sampling tool.

Draws a statistically-sized sample from an already-built pipeline output
(agent-repo detection, agent/human commit detection, agent/human fixtures)
for a human reviewer to manually check, at a chosen confidence level and
margin of error. This is a standalone tool, not part of the phase_1a-8
pipeline — it never runs automatically; invoke it explicitly with
`python -m collection.validation_sampling` whenever a manual-validation
sample is needed for one of the STEPS below.

Sample size uses Cochran's formula with the finite-population correction:

    n0 = z^2 * p * (1 - p) / e^2
    n  = n0 / (1 + (n0 - 1) / N)   (N = population size)

Sampling is deterministic by content, not just by seed: rows are sorted by
a hash of their full content before `random.Random(seed).sample(...)` is
applied, so the same seed reproduces the same manually-reviewed rows even
if the source CSV's row order changes between pipeline runs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from math import ceil
from pathlib import Path
from random import Random
from typing import Any

from scipy.stats import norm

from .csv_adapter import get_adapter
from .logging_utils import configure_logging, get_logger

logger = get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "validation-samples"


@dataclass(frozen=True)
class StepConfig:
    """How a validation-sampling step's population should be assembled."""

    population_mode: str  # "combined" or "per_file"


STEPS: dict[str, StepConfig] = {
    "agent-repos": StepConfig(population_mode="combined"),
    "agent-commits-dataset-a": StepConfig(population_mode="combined"),
    "human-commits-dataset-b": StepConfig(population_mode="combined"),
    "agent-fixtures-dataset-a": StepConfig(population_mode="per_file"),
    "human-fixtures-dataset-b": StepConfig(population_mode="per_file"),
    "human-fixtures-dataset-c": StepConfig(population_mode="per_file"),
}


def cochran_sample_size(
    population_size: int | None,
    confidence_level: float = 0.95,
    margin_of_error: float = 0.05,
    proportion: float = 0.5,
) -> int:
    """Return the Cochran sample size for *population_size*, finite-corrected.

    Args:
        population_size: Total number of rows to sample from. None skips the
            finite-population correction (treated as an infinite population).
            0 returns 0 (nothing to sample).
        confidence_level: e.g. 0.95 for 95% confidence.
        margin_of_error: e.g. 0.05 for a 5% margin of error.
        proportion: Assumed population proportion; 0.5 is Cochran's
            conservative default when no prior estimate is available (it
            maximizes the required sample size).
    """
    z = norm.ppf(1 - (1 - confidence_level) / 2)
    n0 = (z**2 * proportion * (1 - proportion)) / margin_of_error**2

    if population_size is None:
        return ceil(n0)
    if population_size <= 0:
        return 0
    n = n0 / (1 + (n0 - 1) / population_size)
    return min(ceil(n), population_size)


def _row_sort_key(row: dict[str, Any]) -> str:
    """Stable, content-derived sort key so sampling doesn't depend on file order."""
    canonical = json.dumps(row, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def sample_rows(rows: list[dict[str, Any]], n: int, seed: int) -> list[dict[str, Any]]:
    """Deterministically sample *n* rows from *rows* given *seed*."""
    if n >= len(rows):
        return list(rows)
    ordered = sorted(rows, key=_row_sort_key)
    return Random(seed).sample(ordered, n)


def _union_fieldnames(per_file_rows: list[list[dict[str, Any]]]) -> list[str]:
    fieldnames: list[str] = []
    seen = set()
    for rows in per_file_rows:
        for row in rows:
            for key in row:
                if key not in seen:
                    seen.add(key)
                    fieldnames.append(key)
    return fieldnames


def run_validation_sampling(
    step: str,
    input_paths: list[Path],
    confidence_level: float = 0.95,
    margin_of_error: float = 0.05,
    proportion: float = 0.5,
    seed: int = 42,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> dict[str, Any]:
    """Run Cochran-sized manual-validation sampling for *step*.

    Returns the metadata dict that is also written to
    `<output_root>/<step>/sample_metadata_<timestamp>.json`.
    """
    if step not in STEPS:
        raise ValueError(f"Unknown step {step!r}; expected one of {sorted(STEPS)}")
    if not input_paths:
        raise ValueError("At least one --input CSV is required")

    adapter = get_adapter()
    step_dir = Path(output_root) / step
    step_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    outputs: list[dict[str, Any]] = []
    mode = STEPS[step].population_mode

    if mode == "combined":
        per_file_rows = [list(adapter.read_dicts(p)) for p in input_paths]
        fieldnames = _union_fieldnames(per_file_rows)
        population = [row for rows in per_file_rows for row in rows]
        n = cochran_sample_size(
            len(population), confidence_level, margin_of_error, proportion
        )
        sampled = sample_rows(population, n, seed)

        out_path = step_dir / f"{step}_sample_{timestamp}.csv"
        adapter.write_dicts(out_path, sampled, fieldnames)
        outputs.append(
            {
                "source_files": [str(p) for p in input_paths],
                "output_file": str(out_path),
                "population_size": len(population),
                "sample_size": len(sampled),
            }
        )
    elif mode == "per_file":
        for path in input_paths:
            rows = list(adapter.read_dicts(path))
            fieldnames = list(rows[0].keys()) if rows else []
            n = cochran_sample_size(
                len(rows), confidence_level, margin_of_error, proportion
            )
            sampled = sample_rows(rows, n, seed)

            out_path = step_dir / f"{path.stem}_sample_{timestamp}.csv"
            adapter.write_dicts(out_path, sampled, fieldnames)
            outputs.append(
                {
                    "source_files": [str(path)],
                    "output_file": str(out_path),
                    "population_size": len(rows),
                    "sample_size": len(sampled),
                }
            )
    else:
        raise ValueError(f"Unknown population_mode {mode!r} for step {step!r}")

    metadata = {
        "step": step,
        "population_mode": mode,
        "confidence_level": confidence_level,
        "margin_of_error": margin_of_error,
        "proportion": proportion,
        "seed": seed,
        "timestamp": timestamp,
        "outputs": outputs,
    }
    metadata_path = step_dir / f"sample_metadata_{timestamp}.json"
    with metadata_path.open("w", encoding="utf-8") as fh:
        json.dump(metadata, fh, indent=2)

    for entry in outputs:
        logger.info(
            "[Validation Sampling] %s: N=%d -> n=%d -> %s",
            step,
            entry["population_size"],
            entry["sample_size"],
            entry["output_file"],
        )

    return metadata


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Draw a Cochran-sized manual-validation sample from a pipeline "
            "output CSV. Not part of the automatic phase pipeline -- run "
            "this by hand whenever a manual-validation sample is needed."
        )
    )
    parser.add_argument(
        "--step",
        required=True,
        choices=sorted(STEPS),
        help="Which pipeline output this sample validates",
    )
    parser.add_argument(
        "--input",
        required=True,
        nargs="+",
        type=Path,
        help="One or more source CSVs (per-language files are fine)",
    )
    parser.add_argument(
        "--confidence-level",
        type=float,
        default=0.95,
        help="Confidence level, e.g. 0.95 for 95%% (default: %(default)s)",
    )
    parser.add_argument(
        "--margin-error",
        type=float,
        default=0.05,
        help="Margin of error, e.g. 0.05 for 5%% (default: %(default)s)",
    )
    parser.add_argument(
        "--proportion",
        type=float,
        default=0.5,
        help="Assumed population proportion (default: %(default)s)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducible sampling (default: %(default)s)",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Root directory for validation-samples output (default: %(default)s)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_logging(fmt="%(message)s")
    args = build_parser().parse_args(argv)
    run_validation_sampling(
        step=args.step,
        input_paths=args.input,
        confidence_level=args.confidence_level,
        margin_of_error=args.margin_error,
        proportion=args.proportion,
        seed=args.seed,
        output_root=args.output_root,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
