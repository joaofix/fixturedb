"""Dataset-level summary statistics.

Computes repo/commit/fixture counts, per-repo and per-file fixture
averages, and (for datasets A and B, which apply the commit-level purity
gate -- see docs/architecture/agent-detection.md's "Pure-Addition Filter")
the gate's acceptance rate -- by reading a dataset's already-written stage
CSVs, not by re-running collection. Written to summary.yaml
(paths.summary_path()) by `python -m collection summarize --dataset
{a,b,c}`, and automatically at the end of each dataset's `toy` run.

Dataset C has no purity gate (snapshot extraction, not diff-based -- see
dataset_c.py's module docstring) and no test-commits stage at all, so
those sections are simply absent from its summary rather than zeroed out.

Two language partitions exist side by side in this file and are NOT the
same thing, so key names spell out which one applies instead of leaving it
implicit as a bare "by_language" (found confusing on review -- comparable
to code elsewhere using unexplained "tier a"/"tier b" jargon):
- by_repo_language: the language a repo/commit-scan file is named after
  (repos.csv, test-commits.csv, and Dataset A's purity source
  fixture_repos.csv are all organized this way).
- by_fixture_language: each individual fixture's own detected language
  (fixtures.csv is organized this way -- a multi-language repo's fixtures
  can land in more than one language's file even though the repo itself
  has one assigned language). See collection/human_corpus.py's
  fixtures_by_language comment for the extraction-time routing this
  mirrors.
A repo touching both Java and Python test files in one commit will show
up once under repos.by_repo_language (its one assigned language) but can
contribute to fixtures.by_fixture_language under both "java" and
"python" -- purity_gate.by_repo_language is therefore an approximation
for such repos (the commit-level gate itself has no per-language
granularity: one deletion anywhere rejects the whole commit, regardless
of which language's file it was in), not a bug, just a limit of
attributing a commit-wide decision to a single language after the fact.
"""

from __future__ import annotations

import csv
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from . import paths
from .config import DATASET_C_SAMPLING_SEED

# Real fixture/test-commit text (e.g. a mass baseline-regeneration commit's
# test_file_paths) can exceed the csv module's default 128KB field limit --
# see csv_adapter.py for the same fix and why it's needed.
csv.field_size_limit(sys.maxsize)

SCHEMA_VERSION = 1


def _glob_by_language(directory: Path, suffix: str) -> dict[str, list[dict]]:
    """Read every `{lang}{suffix}` file directly in `directory`, keyed by
    the language named in the filename (everything before `suffix`)."""
    rows_by_lang: dict[str, list[dict]] = {}
    if not directory.is_dir():
        return rows_by_lang
    for path in sorted(directory.glob(f"*{suffix}")):
        lang = path.name[: -len(suffix)]
        with path.open("r", newline="", encoding="utf-8") as fh:
            rows_by_lang[lang] = list(csv.DictReader(fh))
    return rows_by_lang


def _avg(total: int, count: int) -> float:
    return round(total / count, 2) if count else 0.0


def _repos_section(dataset: str, root: Path) -> dict[str, Any]:
    repos_dir = paths.stage_dir(dataset, "repos", root=root)
    by_lang = _glob_by_language(repos_dir, "_repo.csv")
    return {
        "total": sum(len(rows) for rows in by_lang.values()),
        "by_repo_language": {
            lang: len(rows) for lang, rows in sorted(by_lang.items())
        },
    }


def _test_commit_suffix(dataset: str) -> str:
    # Dataset A's own commits (agent-authored) vs Dataset B's (human,
    # within the same repos) are written with different filename suffixes
    # -- see agent_corpus.py / human_corpus.py's respective writers.
    return "_test_commit.csv" if dataset == "a" else "_human_test_commit.csv"


def _test_commits_section(dataset: str, root: Path) -> dict[str, Any]:
    tc_dir = paths.stage_dir(dataset, "test-commits", root=root)
    by_lang = _glob_by_language(tc_dir, _test_commit_suffix(dataset))
    return {
        "total": sum(len(rows) for rows in by_lang.values()),
        "by_repo_language": {
            lang: len(rows) for lang, rows in sorted(by_lang.items())
        },
    }


def _purity_gate_section(dataset: str, root: Path) -> dict[str, Any] | None:
    """Commit-level purity-gate acceptance rate, by the repo's assigned
    language (see module docstring for why this differs from
    fixtures.by_fixture_language and is an approximation for
    multi-language repos).

    Dataset A's counts live in fixtures/repos/{lang}_fixture_repos.csv
    (rejected_mixed_test_diff/accepted columns, one row per repo -- summed
    here). Dataset B's live in test-commits/{lang}_purity_stats.csv (one
    already-aggregated row per language, written by
    human_corpus.py::_process_human_within_language). Returns None if
    neither source exists yet (e.g. run predates this instrumentation).
    """
    by_lang: dict[str, dict[str, int]] = {}

    if dataset == "a":
        repo_list_dir = paths.stage_dir(dataset, "fixtures", root=root) / "repos"
        for lang, rows in sorted(
            _glob_by_language(repo_list_dir, "_fixture_repos.csv").items()
        ):
            accepted = sum(int(r.get("accepted") or 0) for r in rows)
            rejected = sum(int(r.get("rejected_mixed_test_diff") or 0) for r in rows)
            by_lang[lang] = {"accepted": accepted, "rejected": rejected}
    elif dataset == "b":
        tc_dir = paths.stage_dir(dataset, "test-commits", root=root)
        for lang, rows in sorted(
            _glob_by_language(tc_dir, "_purity_stats.csv").items()
        ):
            if not rows:
                continue
            by_lang[lang] = {
                "accepted": int(rows[0].get("commits_accepted") or 0),
                "rejected": int(rows[0].get("commits_rejected") or 0),
            }

    if not by_lang:
        return None

    total_accepted = sum(v["accepted"] for v in by_lang.values())
    total_rejected = sum(v["rejected"] for v in by_lang.values())
    total = total_accepted + total_rejected
    return {
        # Every language's commits combined into one rate -- NOT the mean
        # of the four by_repo_language rates below, which can differ from
        # this when languages have very different commit volumes.
        "acceptance_rate_all_languages_combined": _avg(total_accepted, total)
        if total
        else None,
        "by_repo_language": {
            lang: {
                **v,
                "acceptance_rate": _avg(v["accepted"], v["accepted"] + v["rejected"]),
            }
            for lang, v in by_lang.items()
        },
    }


def _fixtures_section(dataset: str, root: Path) -> dict[str, Any]:
    fixtures_dir = paths.stage_dir(dataset, "fixtures", root=root)
    by_lang = _glob_by_language(fixtures_dir, "_fixtures.csv")

    total_fixtures = sum(len(rows) for rows in by_lang.values())
    by_language_count = {lang: len(rows) for lang, rows in sorted(by_lang.items())}

    avg_with_fixtures_by_lang: dict[str, float] = {}
    avg_per_file_by_lang: dict[str, float] = {}
    all_repos_with_fixtures: set[str] = set()
    all_files: set[tuple[str, str]] = set()

    for lang, rows in by_lang.items():
        repos = {r["repo_name"] for r in rows if r.get("repo_name")}
        files = {(r["repo_name"], r["file_path"]) for r in rows if r.get("file_path")}
        all_repos_with_fixtures |= repos
        all_files |= files
        avg_with_fixtures_by_lang[lang] = _avg(len(rows), len(repos))
        avg_per_file_by_lang[lang] = _avg(len(rows), len(files))

    # True corpus-wide average: every repo that was scanned, including the
    # ones that yielded zero fixtures (which never appear in fixtures.csv
    # at all, so they're otherwise invisible to an average). No by-language
    # breakdown here -- that would require crossing repos' assigned
    # language against fixtures' own detected language, the same
    # cross-partition ambiguity purity_gate has (see module docstring); an
    # overall-only number avoids asserting a precision this data doesn't
    # actually have.
    total_repos = _repo_pool_size(dataset, root)

    return {
        "total": total_fixtures,
        "by_fixture_language": by_language_count,
        "repos_with_at_least_one_fixture": len(all_repos_with_fixtures),
        "avg_fixtures_per_repo_with_fixtures": {
            "overall": _avg(total_fixtures, len(all_repos_with_fixtures)),
            "by_fixture_language": avg_with_fixtures_by_lang,
        },
        "avg_fixtures_per_repo_overall": _avg(total_fixtures, total_repos),
        "avg_fixtures_per_file": {
            "overall": _avg(total_fixtures, len(all_files)),
            "by_fixture_language": avg_per_file_by_lang,
        },
    }


def _repo_pool_size(dataset: str, root: Path) -> int:
    repos_dir = paths.stage_dir(dataset, "repos", root=root)
    by_lang = _glob_by_language(repos_dir, "_repo.csv")
    return sum(len(rows) for rows in by_lang.values())


def compute_summary(dataset: str, root: Path = paths.DATASETS_ROOT) -> dict[str, Any]:
    """Compute the summary dict for `dataset` from its already-written
    stage CSVs under `root`. Read-only -- never re-runs collection, so it's
    safe to call any time (including on a partially-collected dataset;
    missing stages just come back empty).
    """
    if dataset not in paths.STAGE_ORDER:
        raise ValueError(f"unknown dataset {dataset!r}; expected one of {paths.DATASETS}")

    summary: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataset": dataset,
        "root": str(root),
    }

    # Only Dataset C's repo selection is ever seeded (A/B's --stratified
    # capping is a plain rows[:n] slice, no RNG involved at all -- see
    # repo_resolve.py -- so this field would be permanently null for them;
    # omitted there entirely rather than shown as always-empty).
    if dataset == "c":
        summary["sampling_seed"] = DATASET_C_SAMPLING_SEED

    summary["repos"] = _repos_section(dataset, root)

    if "test-commits" in paths.STAGE_ORDER[dataset]:
        summary["test_commits"] = _test_commits_section(dataset, root)
        purity = _purity_gate_section(dataset, root)
        if purity is not None:
            summary["purity_gate"] = purity

    summary["fixtures"] = _fixtures_section(dataset, root)

    return summary


def write_summary(dataset: str, root: Path = paths.DATASETS_ROOT) -> Path:
    """Compute and write `dataset`'s summary.yaml under `root`. Returns the
    written path."""
    summary = compute_summary(dataset, root=root)
    out_path = paths.summary_path(dataset, root=root)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(summary, fh, sort_keys=False, default_flow_style=False)
    return out_path
