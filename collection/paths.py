"""Central path registry for the collection CLI.

Every subcommand resolves its default input/output directories through this
module instead of hand-computing `Path(__file__).resolve().parents[1]) /
"..."` locally -- that per-script pattern is what caused several of the old
phase scripts to resolve paths one directory too shallow, or relative to the
current working directory instead of the repo root.

`root` is a parameter on every function here (not a module-level global), so
a toy run can pass `root=TOY_ROOT` and get an identical directory shape under
`toy-dataset/` with zero risk of colliding with real `datasets/` output.
"""

from __future__ import annotations

from pathlib import Path

from .config import ROOT_DIR

DATASETS_ROOT = ROOT_DIR / "datasets"
DB_ROOT = ROOT_DIR / "db"
EXPORT_ROOT = ROOT_DIR / "export"
TOY_ROOT = ROOT_DIR / "toy-dataset"
RAW_SEARCH_DIR = ROOT_DIR / "github-search-raw"

# The four stage names that exist anywhere, in pipeline order, per dataset.
STAGE_ORDER: dict[str, list[str]] = {
    "a": ["repos", "commits", "test-commits", "fixtures"],
    "b": ["repos", "test-commits", "fixtures"],
    "c": ["repos", "fixtures"],
}

DATASETS = tuple(STAGE_ORDER.keys())


def _check_dataset(dataset: str) -> None:
    if dataset not in STAGE_ORDER:
        raise ValueError(f"unknown dataset {dataset!r}; expected one of {DATASETS}")


def stage_dir(dataset: str, stage: str, *, root: Path = DATASETS_ROOT) -> Path:
    """Default output directory for `stage` of `dataset`.

    Pass `root=TOY_ROOT` for a toy run's equivalent directory.
    """
    _check_dataset(dataset)
    if stage not in STAGE_ORDER[dataset]:
        raise ValueError(
            f"dataset {dataset!r} has no {stage!r} stage "
            f"(stages: {STAGE_ORDER[dataset]})"
        )
    return root / dataset / stage


def previous_stage_dir(dataset: str, stage: str, *, root: Path = DATASETS_ROOT) -> Path:
    """Default input directory for `stage` = the prior stage's output dir.

    Raises ValueError if `stage` is `dataset`'s first stage (no prior stage
    exists, so there is no sensible default -- the caller must pass an
    explicit input, e.g. RAW_SEARCH_DIR for `discover-repos`).
    """
    _check_dataset(dataset)
    stages = STAGE_ORDER[dataset]
    if stage not in stages:
        raise ValueError(
            f"dataset {dataset!r} has no {stage!r} stage (stages: {stages})"
        )
    idx = stages.index(stage)
    if idx == 0:
        raise ValueError(
            f"{stage!r} is dataset {dataset!r}'s first stage; it has no "
            "default input directory"
        )
    return stage_dir(dataset, stages[idx - 1], root=root)


def default_repo_source(dataset: str, *, root: Path = DATASETS_ROOT) -> Path:
    """Where `discover-repos --dataset {dataset}` defaults its input from.

    - b: Dataset A's fixture-yielding repos if that stage is populated,
      else Dataset A's raw discovered repos.
    - a/c: the raw SEART search export (dataset-agnostic, not under `root`).
    """
    _check_dataset(dataset)
    if dataset == "b":
        fixture_repos = stage_dir("a", "fixtures", root=root) / "repos"
        if fixture_repos.exists() and any(fixture_repos.iterdir()):
            return fixture_repos
        return stage_dir("a", "repos", root=root)
    if dataset in ("a", "c"):
        return RAW_SEARCH_DIR
    raise ValueError(dataset)


def db_path(dataset: str, *, root: Path = DB_ROOT) -> Path:
    _check_dataset(dataset)
    return root / f"{dataset}.db"


def corpus_db_path(*, root: Path = DB_ROOT) -> Path:
    return root / "corpus.db"


def export_path(dataset: str, *, root: Path = EXPORT_ROOT) -> Path:
    _check_dataset(dataset)
    return root / f"{dataset}.zip"
