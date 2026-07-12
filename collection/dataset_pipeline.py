"""Cross-cutting dataset stages: analyze-distribution, sample, export, validate.

Replaces the old phase_4/5/6_7/8 scripts, which relayed state between each
other through timestamped JSON files under output/ (glob for the latest
`phase_N_*.json`) and hardcoded exactly two datasets (human, agent). Each
function here operates on one dataset at a time, identified by 'a'/'b'/'c',
resolving DB/export paths through collection.paths.

`sample_dataset()` still persists its result to a JSON file (there is a real
CLI-invocation boundary between `sample` and `export`), but at a fixed path
(`output/sample_{dataset}.json`) rather than a timestamped one -- `export`
reads that one file directly instead of globbing for "latest".
"""

from __future__ import annotations

import json
from pathlib import Path

from . import paths
from .dataset_exporter import AgentDatasetExporter, HumanDatasetExporter
from .dataset_sampler import StratifiedSampler
from .dataset_validator import DatasetValidator
from .db import db_session
from .logging_utils import get_logger

logger = get_logger(__name__)

_EXPORTER_CLASSES = {
    "a": AgentDatasetExporter,
    "b": HumanDatasetExporter,
    "c": HumanDatasetExporter,
}


def _sample_output_path(dataset: str, output_dir: Path | None = None) -> Path:
    output_dir = output_dir or (paths.ROOT_DIR / "output")
    return output_dir / f"sample_{dataset}.json"


def analyze_database_distribution(db_path: Path) -> dict:
    """Fixture/repo/test-file counts and fixture_type/scope breakdowns for one DB."""
    stats = {
        "total_fixtures": 0,
        "by_type": {},
        "by_scope": {},
        "repositories": 0,
        "test_files": 0,
    }

    with db_session(db_path) as conn:
        result = conn.execute("SELECT COUNT(*) as count FROM fixtures").fetchone()
        stats["total_fixtures"] = result["count"]

        rows = conn.execute(
            "SELECT fixture_type, COUNT(*) as count FROM fixtures "
            "GROUP BY fixture_type ORDER BY count DESC"
        ).fetchall()
        stats["by_type"] = {row["fixture_type"]: row["count"] for row in rows}

        rows = conn.execute(
            "SELECT scope, COUNT(*) as count FROM fixtures "
            "GROUP BY scope ORDER BY count DESC"
        ).fetchall()
        stats["by_scope"] = {row["scope"]: row["count"] for row in rows}

        result = conn.execute("SELECT COUNT(*) as count FROM repositories").fetchone()
        stats["repositories"] = result["count"]

        result = conn.execute("SELECT COUNT(*) as count FROM test_files").fetchone()
        stats["test_files"] = result["count"]

    return stats


def analyze_distribution(
    dataset: str, against: str, db_root: Path = paths.DB_ROOT
) -> dict:
    """Compare `dataset`'s and `against`'s fixture distributions and
    recommend a balanced sample target (the smaller dataset's total)."""
    db_paths = {
        dataset: paths.db_path(dataset, root=db_root),
        against: paths.db_path(against, root=db_root),
    }
    for name, db_path in db_paths.items():
        if not db_path.exists():
            raise FileNotFoundError(
                f"{db_path} not found; run `extract-fixtures --dataset {name}` first"
            )

    stats = {name: analyze_database_distribution(p) for name, p in db_paths.items()}
    target_count = min(stats[dataset]["total_fixtures"], stats[against]["total_fixtures"])

    return {
        "dataset": dataset,
        "against": against,
        dataset: {"path": str(db_paths[dataset]), "statistics": stats[dataset]},
        against: {"path": str(db_paths[against]), "statistics": stats[against]},
        "sampling_recommendation": {
            "target_count": target_count,
            "stratify_by": "fixture_type",
            "tolerance": 0.02,
            "random_seed": 42,
        },
    }


def sample_dataset(
    dataset: str,
    target_count: int | None = None,
    stratify_by: str = "fixture_type",
    tolerance: float = 0.02,
    seed: int = 42,
    db_root: Path = paths.DB_ROOT,
    output_dir: Path | None = None,
) -> dict:
    """Stratified-sample fixtures from `dataset`'s DB and persist the result.

    `target_count=None` means "sample everything" (no reduction) -- pass an
    explicit value (e.g. from `analyze_distribution()`'s recommendation) to
    balance against another dataset.
    """
    db_path = paths.db_path(dataset, root=db_root)
    if not db_path.exists():
        raise FileNotFoundError(
            f"{db_path} not found; run `extract-fixtures --dataset {dataset}` first"
        )

    with db_session(db_path) as conn:
        rows = conn.execute(
            "SELECT id, fixture_type, scope, loc, name FROM fixtures ORDER BY id"
        ).fetchall()
    fixtures = [dict(row) for row in rows]
    if not fixtures:
        raise ValueError(f"No fixtures found in {db_path}")

    if target_count is None:
        target_count = len(fixtures)

    sampler = StratifiedSampler(random_seed=seed)
    result = sampler.sample(
        fixtures, target_count=target_count, stratify_by=stratify_by, tolerance=tolerance
    )
    stats = sampler.get_sample_statistics(result)

    output = {
        "dataset": dataset,
        "sampled_count": result.sampled_count,
        "target_count": result.target_count,
        "stratify_by": result.stratify_by,
        "random_seed": seed,
        "all_strata_within_tolerance": stats["all_strata_within_tolerance"],
        "distribution_check": result.distribution_check,
        "sampled_fixture_ids": result.sampled_ids,
    }

    out_path = _sample_output_path(dataset, output_dir)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        json.dump(output, f, indent=2)

    logger.info(
        f"[sample {dataset}] {result.sampled_count}/{len(fixtures)} fixtures "
        f"sampled -> {out_path}"
    )
    return output


def export_dataset(
    dataset: str,
    version: str = "1.0",
    db_root: Path = paths.DB_ROOT,
    export_root: Path = paths.EXPORT_ROOT,
    sample_output_dir: Path | None = None,
) -> Path:
    """Export `dataset`'s sampled fixtures to export/{dataset}.zip.

    Requires `sample --dataset {dataset}` to have run first.
    """
    sample_path = _sample_output_path(dataset, sample_output_dir)
    if not sample_path.exists():
        raise FileNotFoundError(
            f"No sample results at {sample_path}; run `sample --dataset {dataset}` first"
        )
    with sample_path.open() as f:
        sample_data = json.load(f)
    sampled_ids = sample_data["sampled_fixture_ids"]

    db_path = paths.db_path(dataset, root=db_root)
    work_dir = export_root / f"_{dataset}_work"
    exporter_cls = _EXPORTER_CLASSES[dataset]
    exporter = exporter_cls(db_path, work_dir)
    result = exporter.export(sampled_ids, version=version)

    final_zip = paths.export_path(dataset, root=export_root)
    final_zip.parent.mkdir(parents=True, exist_ok=True)
    result.zip_path.replace(final_zip)

    logger.info(
        f"[export {dataset}] {result.fixture_count} fixtures, "
        f"{result.total_size_mb:.1f} MB -> {final_zip}"
    )
    return final_zip


def validate_dataset(dataset: str, export_root: Path = paths.EXPORT_ROOT) -> dict:
    """Validate export/{dataset}.zip for completeness and independence."""
    zip_path = paths.export_path(dataset, root=export_root)
    validator = DatasetValidator(zip_path.parent)
    return validator.validate_single(zip_path, is_agent=(dataset == "a"))
