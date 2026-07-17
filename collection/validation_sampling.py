"""Cochran-formula manual-validation sampling tool.

Draws a statistically-sized sample from an already-built pipeline output for
a human reviewer to manually check, at a chosen confidence level and margin
of error. This is a standalone tool, not part of the phase_1a-8 pipeline --
it never runs automatically; invoke it explicitly with
`python -m collection.validation_sampling` whenever a manual-validation
sample is needed for one of the STEPS below.

Only steps with a real labelling/attribution risk are covered -- not every
pipeline output needs a manual-validation sample. Agent test-commit
detection is deliberately excluded as redundant with the already-validated
commit-attribution logic (same file-matching applied to an already-checked
corpus) -- see docs/usage/validation-sampling.md for the full reduced
validation set and the reasoning behind each inclusion/exclusion.

Dataset B's human-side steps (`human-commits-dataset-b`,
`human-test-commits-dataset-b`, `human-fixtures-dataset-b`) ARE covered,
despite reusing the same detection code as their Dataset A counterparts:
Dataset A's `agent-commits-dataset-a` sample only checks *precision* on the
claimed-agent commits (are these really agent-authored?), never *recall* on
the human side (did a real agent commit get missed by the classifier and
land in the human/control corpus instead, contaminating it?). The Dataset B
steps close that gap and separately re-validate test-commit file-matching
and fixture extraction against Dataset B's own corpus rather than assuming
Dataset A's review transfers.

`human-fixtures-dataset-c` is covered for the same reason: Dataset C uses
the identical `detector.extract_fixtures()` call as A/B, but on a real
sample it turned up two false-positive classes (a substring collision in
the pytest_decorator pattern, a `.tsx`/JSX grammar mismatch) that Dataset
A's own review happened not to catch, since neither edge case appeared in
its particular sample. "Same detector, already validated once" is not
sufficient justification on its own -- each dataset's own corpus can
exercise different edge cases of the same code.

Every step normalizes its source rows to one fixed reviewer-facing schema
(`validation_id, validation_type, language, repo_full_name, item_id,
item_url, detection_signal, evidence, label, reviewer_notes`) regardless of
what columns the underlying pipeline CSV happens to carry, so reviewers get
uniform, self-explanatory columns and a clickable link to the artifact being
judged. Repo and commit steps also stratify their sample proportionally
(repo: by language; commit: by language + agent_type) rather than drawing a
simple pooled sample, so the reviewed set mirrors the corpus composition.

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
from math import ceil, floor
from pathlib import Path
from random import Random
from typing import Any, Callable

from scipy.stats import norm

from .csv_adapter import get_adapter
from .logging_utils import configure_logging, get_logger

logger = get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "validation-samples"

CANONICAL_FIELDNAMES = [
    "validation_id",
    "validation_type",
    "language",
    "repo_full_name",
    "item_id",
    "item_url",
    "detection_signal",
    "evidence",
    "label",
    "reviewer_notes",
]

LABEL_README_TEXT = """# Manual-Validation Samples

Every CSV under `validation-samples/<step>/` shares one fixed schema so a
reviewer can open any of them without needing to know which pipeline step
produced it:

| Column | Meaning |
|---|---|
| `validation_id` | Unique row identifier (`<step>-<n>`), stable for a given sampling run |
| `validation_type` | `repo` \\| `commit` \\| `fixture` \\| `human_commit` \\| `human_test_commit` |
| `language` | Language of the item (`all` is never used -- each row's own language) |
| `repo_full_name` | `owner/repo` slug |
| `item_id` | repo full name / commit SHA / composite fixture key |
| `item_url` | Direct clickable GitHub URL to the item |
| `detection_signal` | What triggered detection (matched config filename, agent type, or fixture type) |
| `evidence` | Raw text/context for the reviewer to judge the detection against |
| `label` | Empty -- reviewer fills in: TP \\| FP \\| Unsure \\| 404 |
| `reviewer_notes` | Empty -- reviewer fills in optional free text |

## Label values

- **TP** -- detection is correct.
- **FP** -- detection is wrong; this is not what was claimed.
- **Unsure** -- reviewer cannot determine with confidence from the available evidence.
- **404** -- artifact no longer accessible (repo went private, commit deleted, file
  removed). Excluded from the precision denominator, not counted as FP.

## Known gap

Commit `evidence` is currently best-effort (`agent_type` + `commit_date` +
author), not the commit message or diff text -- that data isn't captured by
the pipeline yet. See docs/usage/validation-sampling.md for details.

Each `sample_metadata_<timestamp>.json` alongside these CSVs records the
population size (N), sample size (n), confidence level, margin of error,
seed, and (for stratified steps) the per-stratum breakdown used to draw the
sample.
"""


@dataclass(frozen=True)
class StepConfig:
    """How a validation-sampling step's population should be assembled."""

    population_mode: str  # "combined" or "per_file"
    # "repo" | "commit" | "fixture" | "human_commit" | "human_test_commit"
    validation_type: str  # -- selects normalizer/filter
    stratify_by: tuple[str, ...] = ()  # raw-row keys to stratify the sample by


def _is_agent_config_positive(row: dict[str, Any]) -> bool:
    return str(row.get("has_agent_config") or "").strip().lower() in {"1", "true"}


_FILTERS: dict[str, Callable[[dict[str, Any]], bool]] = {
    "repo": _is_agent_config_positive,
}


def _normalize_repo_row(row: dict[str, Any]) -> dict[str, Any]:
    repo_name = row.get("repo_name", "")
    detection_signal = row.get("matched_config_file") or "agent_config_present"
    return {
        "validation_type": "repo",
        "language": row.get("language", ""),
        "repo_full_name": repo_name,
        "item_id": repo_name,
        "item_url": f"https://github.com/{repo_name}",
        "detection_signal": detection_signal,
        "evidence": detection_signal,
    }


def _normalize_commit_row(row: dict[str, Any]) -> dict[str, Any]:
    repo_name = row.get("repo_name", "")
    commit_sha = row.get("commit_sha", "")
    item_url = row.get("commit_url") or (
        f"https://github.com/{repo_name}/commit/{commit_sha}"
        if repo_name and commit_sha
        else ""
    )
    return {
        "validation_type": "commit",
        "language": row.get("language", ""),
        "repo_full_name": repo_name,
        "item_id": commit_sha,
        "item_url": item_url,
        "detection_signal": row.get("agent_type", ""),
        "evidence": (
            f"agent_type={row.get('agent_type', '')}; "
            f"commit_date={row.get('commit_date', '')}; "
            f"author={row.get('author_name', '')} <{row.get('author_email', '')}>"
        ),
    }


def _normalize_fixture_row(row: dict[str, Any]) -> dict[str, Any]:
    repo_name = row.get("repo_name", "")
    commit_sha = row.get("commit_sha", "")
    file_path = row.get("file_path", "")
    start_line = row.get("start_line", "")
    return {
        "validation_type": "fixture",
        "language": row.get("language", ""),
        "repo_full_name": repo_name,
        "item_id": f"{repo_name}:{commit_sha}:{file_path}:{start_line}",
        "item_url": row.get("github_url", ""),
        "detection_signal": row.get("fixture_type", ""),
        "evidence": row.get("raw_source", ""),
    }


def _normalize_human_commit_row(row: dict[str, Any]) -> dict[str, Any]:
    """Contamination check: was a commit classified `commit_role=human`
    correctly, i.e. is it really not agent-authored? Dataset A's
    `agent-commits-dataset-a` sample only validates precision on the claimed-
    agent side of the same classifier; this validates recall on the human
    side -- a real agent commit missed by the classifier would silently
    contaminate the human/control corpus instead of raising a false positive
    anywhere else."""
    repo_name = row.get("repo_name", "")
    commit_sha = row.get("commit_sha", "")
    item_url = row.get("commit_url") or (
        f"https://github.com/{repo_name}/commit/{commit_sha}"
        if repo_name and commit_sha
        else ""
    )
    return {
        "validation_type": "human_commit",
        "language": row.get("language", ""),
        "repo_full_name": repo_name,
        "item_id": commit_sha,
        "item_url": item_url,
        "detection_signal": "classified_as_human",
        "evidence": (
            f"commit_role={row.get('commit_role', '')}; "
            f"commit_date={row.get('commit_date', '')}; "
            f"test_file_count={row.get('test_file_count', '')}"
        ),
    }


def _normalize_human_test_commit_row(row: dict[str, Any]) -> dict[str, Any]:
    """File-path match check: do the paths this commit was flagged for
    (`test_file_paths`) actually look like test files? Same mechanical
    file-path/pattern-matching logic as agent test-commit detection, applied
    here to Dataset B's own corpus rather than assuming Dataset A's review
    transfers."""
    repo_name = row.get("repo_name", "")
    commit_sha = row.get("commit_sha", "")
    item_url = row.get("commit_url") or (
        f"https://github.com/{repo_name}/commit/{commit_sha}"
        if repo_name and commit_sha
        else ""
    )
    return {
        "validation_type": "human_test_commit",
        "language": row.get("language", ""),
        "repo_full_name": repo_name,
        "item_id": commit_sha,
        "item_url": item_url,
        "detection_signal": f"test_file_count={row.get('test_file_count', '')}",
        "evidence": row.get("test_file_paths", ""),
    }


_NORMALIZERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "repo": _normalize_repo_row,
    "commit": _normalize_commit_row,
    "fixture": _normalize_fixture_row,
    "human_commit": _normalize_human_commit_row,
    "human_test_commit": _normalize_human_test_commit_row,
}


STEPS: dict[str, StepConfig] = {
    "agent-repos": StepConfig(
        population_mode="combined", validation_type="repo", stratify_by=("language",)
    ),
    "agent-commits-dataset-a": StepConfig(
        population_mode="combined",
        validation_type="commit",
        stratify_by=("language", "agent_type"),
    ),
    "agent-fixtures-dataset-a": StepConfig(
        population_mode="per_file", validation_type="fixture", stratify_by=()
    ),
    "human-commits-dataset-b": StepConfig(
        population_mode="combined",
        validation_type="human_commit",
        stratify_by=("language",),
    ),
    "human-test-commits-dataset-b": StepConfig(
        population_mode="combined",
        validation_type="human_test_commit",
        stratify_by=("language",),
    ),
    "human-fixtures-dataset-b": StepConfig(
        population_mode="per_file", validation_type="fixture", stratify_by=()
    ),
    "human-fixtures-dataset-c": StepConfig(
        population_mode="per_file", validation_type="fixture", stratify_by=()
    ),
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


def _allocate_stratified(
    strata_sizes: dict[Any, int], total_n: int
) -> dict[Any, int]:
    """Proportionally allocate *total_n* samples across strata (largest-remainder).

    Guarantees `sum(result.values()) == min(total_n, sum(strata_sizes.values()))`
    and `result[key] <= strata_sizes[key]` for every stratum.
    """
    population = sum(strata_sizes.values())
    target = min(total_n, population)
    if target <= 0 or population == 0:
        return dict.fromkeys(strata_sizes, 0)

    exact = {
        key: target * size / population for key, size in strata_sizes.items()
    }
    allocation = {key: min(floor(value), strata_sizes[key]) for key, value in exact.items()}
    remainders = sorted(
        strata_sizes,
        key=lambda key: exact[key] - allocation[key],
        reverse=True,
    )

    remaining = target - sum(allocation.values())
    while remaining > 0:
        progressed = False
        for key in remainders:
            if remaining <= 0:
                break
            if allocation[key] < strata_sizes[key]:
                allocation[key] += 1
                remaining -= 1
                progressed = True
        if not progressed:
            break

    return allocation


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


def _sample_population(
    rows: list[dict[str, Any]],
    stratify_by: tuple[str, ...],
    confidence_level: float,
    margin_of_error: float,
    proportion: float,
    seed: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Sample *rows*, stratifying by *stratify_by* if non-empty.

    Returns (sampled_rows, strata_metadata) where strata_metadata is empty
    when stratify_by is empty.
    """
    n = cochran_sample_size(len(rows), confidence_level, margin_of_error, proportion)

    if not stratify_by:
        return sample_rows(rows, n, seed), []

    strata: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for row in rows:
        key = tuple(str(row.get(field, "")) for field in stratify_by)
        strata.setdefault(key, []).append(row)

    strata_sizes = {key: len(items) for key, items in strata.items()}
    allocation = _allocate_stratified(strata_sizes, n)

    sampled: list[dict[str, Any]] = []
    strata_metadata: list[dict[str, Any]] = []
    for key in sorted(strata):
        n_k = allocation[key]
        stratum_sample = sample_rows(strata[key], n_k, seed)
        sampled.extend(stratum_sample)
        strata_metadata.append(
            {
                "key": dict(zip(stratify_by, key)),
                "population_size": strata_sizes[key],
                "sample_size": len(stratum_sample),
            }
        )

    return sampled, strata_metadata


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

    config = STEPS[step]
    normalize = _NORMALIZERS[config.validation_type]
    row_filter = _FILTERS.get(config.validation_type)

    adapter = get_adapter()
    step_dir = Path(output_root) / step
    step_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    outputs: list[dict[str, Any]] = []

    if config.population_mode == "combined":
        population: list[dict[str, Any]] = []
        for path in input_paths:
            rows = list(adapter.read_dicts(path))
            if row_filter:
                rows = [r for r in rows if row_filter(r)]
            population.extend(rows)

        sampled, strata_metadata = _sample_population(
            population,
            config.stratify_by,
            confidence_level,
            margin_of_error,
            proportion,
            seed,
        )
        normalized = [normalize(r) for r in sampled]
        normalized.sort(key=_row_sort_key)
        rows_out = _finalize_rows(normalized, step)

        out_path = step_dir / f"{step}_sample_{timestamp}.csv"
        adapter.write_dicts(out_path, rows_out, CANONICAL_FIELDNAMES)
        entry: dict[str, Any] = {
            "source_files": [str(p) for p in input_paths],
            "output_file": str(out_path),
            "population_size": len(population),
            "sample_size": len(sampled),
        }
        if strata_metadata:
            entry["strata"] = strata_metadata
        outputs.append(entry)

    elif config.population_mode == "per_file":
        for path in input_paths:
            rows = list(adapter.read_dicts(path))
            if row_filter:
                rows = [r for r in rows if row_filter(r)]

            sampled, strata_metadata = _sample_population(
                rows,
                config.stratify_by,
                confidence_level,
                margin_of_error,
                proportion,
                seed,
            )
            normalized = [normalize(r) for r in sampled]
            normalized.sort(key=_row_sort_key)
            rows_out = _finalize_rows(normalized, step)

            out_path = step_dir / f"{path.stem}_sample_{timestamp}.csv"
            adapter.write_dicts(out_path, rows_out, CANONICAL_FIELDNAMES)
            entry = {
                "source_files": [str(path)],
                "output_file": str(out_path),
                "population_size": len(rows),
                "sample_size": len(sampled),
            }
            if strata_metadata:
                entry["strata"] = strata_metadata
            outputs.append(entry)
    else:
        raise ValueError(
            f"Unknown population_mode {config.population_mode!r} for step {step!r}"
        )

    metadata = {
        "step": step,
        "population_mode": config.population_mode,
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

    _write_label_readme(output_root)

    for entry in outputs:
        logger.info(
            "[Validation Sampling] %s: N=%d -> n=%d -> %s",
            step,
            entry["population_size"],
            entry["sample_size"],
            entry["output_file"],
        )

    return metadata


def _finalize_rows(
    normalized_rows: list[dict[str, Any]], step: str
) -> list[dict[str, Any]]:
    """Assign sequential validation_id/label/reviewer_notes to sorted rows."""
    rows_out = []
    for i, row in enumerate(normalized_rows):
        rows_out.append(
            {
                "validation_id": f"{step}-{i + 1:04d}",
                **row,
                "label": "",
                "reviewer_notes": "",
            }
        )
    return rows_out


def _write_label_readme(output_root: Path) -> None:
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "README.md").write_text(LABEL_README_TEXT, encoding="utf-8")


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
