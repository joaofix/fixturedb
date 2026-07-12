# Collection Module Architecture

This document describes the architecture, key components, and operational guidance for the `collection` subsystem used to discover, clone, and extract fixtures from repositories.

## Goals
- Produce reproducible, labelled fixture datasets for between-group experiments (within- and inter-repository).
- Ensure clones are ephemeral and disk-safe; minimize SQLite lock contention during bulk inserts.
- Make CSV/IO pluggable for testability and alternate backends.

## Key Components

The collection subsystem has three layered cloning modules — pick the one matching your use case:
- `collection/clone_primitives.py`: lowest-level primitive — clones a repo into a brand-new tempdir via subprocess, detects credential-gated (private repo) failures. No DB, no throttling, no config.
- `collection/ephemeral_clone.py`: context managers wrapping `clone_primitives.py` with throttling (a global semaphore + retry/backoff), disk-safety checks (`ensure_free_space()`), and guaranteed cleanup on exit. Exposes `temp_clone_commit_history()` and `clone_with_function()`. Use this for transient inspection (commit-history scans, QC counters).
- `collection/persistent_clone.py`: an independent, DB-tracked workflow that clones into the durable `CLONES_DIR` (not a tempdir), runs pre-clone quality checks, and records status in SQLite via `db.py`. Use this for the main repository corpus, not for one-off inspection.

Other key components:
- `collection/db.py`: database schema and helpers.
- `collection/csv_adapter.py`: pluggable CSV adapter; production code uses file-backed adapter but tests can swap implementations.
- `collection/agent_corpus.py`, `collection/human_corpus.py`, `collection/dataset_c.py`: orchestration of the agent and human extraction flows; they call into the clone manager and DB helpers.

## Dataset A / B / C build map

Each dataset is built through the same `python -m collection <verb> --dataset
{a,b,c}` CLI, calling exactly one collector/function per dataset for each
verb — there is no runtime branching that decides which dataset a given run
produces:

| Dataset | What it is | `extract-fixtures` entry point | Collector / function |
|---|---|---|---|
| A | Agent-authored fixtures | `extract-fixtures --dataset a` | `agent_corpus.AgentCorpusCollector` |
| B | Human-authored fixtures, within-repo matched control | `extract-fixtures --dataset b` | `human_corpus.HumanCorpusCollector.run()` |
| C | Human-authored fixtures, cross-repo pre-2021 baseline | `extract-fixtures --dataset c` | `dataset_c.collect_dataset_c_fixtures()` |

Paths:
- `collection/clone_primitives.py` ([collection/clone_primitives.py](collection/clone_primitives.py))
- `collection/ephemeral_clone.py` ([collection/ephemeral_clone.py](collection/ephemeral_clone.py))
- `collection/persistent_clone.py` ([collection/persistent_clone.py](collection/persistent_clone.py))
- `collection/db.py` ([collection/db.py](collection/db.py))
- `collection/csv_adapter.py` ([collection/csv_adapter.py](collection/csv_adapter.py))
- `collection/agent_corpus.py` ([collection/agent_corpus.py](collection/agent_corpus.py))
- `collection/human_corpus.py` ([collection/human_corpus.py](collection/human_corpus.py))
- `collection/dataset_c.py` ([collection/dataset_c.py](collection/dataset_c.py))

## Clone lifecycle and disk safety
- Clones are created in a per-run temporary root and removed when the clone context exits (ephemeral clones, via `ephemeral_clone.py`). Use `temp_clone_commit_history()` for commit-history clones.
- Before cloning, `ensure_free_space(path, min_bytes)` is used to check available disk; callers can set `min_free_bytes` to fail early and avoid uncontrolled disk growth.
- A pruning utility `prune_old_clones(clones_dir, max_age_seconds)` is provided to recover disk from stale runs.

Operational note: choose conservative `min_free_bytes` values for shared CI runners and tune `clones_dir` to point at a large-volume filesystem.

## Concurrency and DB pattern
- Extraction uses a pool of workers (ThreadPoolExecutor) to parallelize per-repository extraction while preserving a single-writer pattern for cross-references.
- Avoid nested write transactions with SQLite. Per-repo persistence uses short-lived write transactions (via `corpus_utils.persist_repository_and_fixtures()`) to insert repository, test_files, fixtures, and mock_usages rows.
- DB connection defaults: `PRAGMA journal_mode=WAL`, `PRAGMA busy_timeout` set to a generous value to reduce transient `database is locked` errors.

## Sampling modes
- Dataset B (within-repo, paired): sample human fixtures from the same repositories and same 2025+ temporal window as Dataset A, stratified by language.
- Dataset C (cross-repo, unpaired): repos are selected (not sampled) by `discover-repos --dataset c` (wraps `select_dataset_c_repos.py`) -- every repo created within a fixed window (`DATASET_C_MIN_CREATED_DATE` to `HUMAN_CORPUS_CUTOFF_DATE`), no stratification or cap. `dataset_c.py` then checks out each one at its own pinned pre-2021 cutoff commit and extracts every fixture from every test file at that snapshot (no diff/purity gating).

## CSV and IO
- Use the `csv_adapter` to read/write CSVs and to plug alternative persistence backends. Tests override the adapter to avoid filesystem dependencies.

## Operational Runbook (concise)
1. Ensure `clones_dir` is set to a path with sufficient free space.
2. Run `discover-repos`/`filter-test-commits`/`extract-fixtures --dataset b` (Dataset B), then `discover-repos`/`extract-fixtures --dataset c` (Dataset C).
3. Run `discover-repos`/`discover-commits`/`filter-test-commits`/`extract-fixtures --dataset a` (Dataset A).
4. Continue with `analyze-distribution`/`sample`/`export`/`validate` (per dataset).
5. Inspect `db/{a,b,c}.db` and the `repositories` / `fixtures` / `mock_usages` tables for sample provenance.
6. When a manual-validation sample is needed for the paper, run `collection/validation_sampling.py` by hand against that step's output CSV(s) — see [Manual-Validation Sampling](../usage/validation-sampling.md). Not part of this automatic runbook.

## Troubleshooting
- If you observe frequent SQLite `database is locked` errors: ensure callers are not opening nested write transactions.
- If clones fill disk: raise `min_free_bytes` and run `prune_old_clones()` on the clones directory.

## Tests and CI
- The collection subsystem has unit and integration tests under `tests/` (e.g., `tests/test_clone_manager.py`, which tests `ephemeral_clone.py`) and a small performance check for bulk inserts. CI runs these to validate logic and performance bounds. The docs intentionally avoid test-level detail.

If you want, I can add a short diagram or a quick-start checklist for running the collection pipeline on a new machine.
