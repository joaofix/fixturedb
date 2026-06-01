# Collection Module Architecture

This document describes the architecture, key components, and operational guidance for the `collection` subsystem used to discover, clone, and extract fixtures from repositories.

## Goals
- Produce reproducible, labelled fixture datasets for between-group experiments (within- and inter-repository).
- Ensure clones are ephemeral and disk-safe; minimize SQLite lock contention during bulk inserts.
- Make CSV/IO pluggable for testability and alternate backends.

## Key Components
- `collection/clone_manager.py`: central clone lifecycle and disk-safety logic. Exposes context managers such as `temp_clone_commit_history()` and helpers like `clone_with_function()` and `ensure_free_space()`.
- `collection/db.py`: database schema and helpers. Provides `insert_human_inter_fixtures_coordinated()` (transactional, batched insert) and lower-level insert helpers.
- `collection/csv_adapter.py`: pluggable CSV adapter; production code uses file-backed adapter but tests can swap implementations.
- `collection/agent_corpus.py` and `collection/human_corpus.py`: orchestration of agent and human extraction flows; they call into the clone manager and DB helpers.

Paths:
- `collection/clone_manager.py` ([collection/clone_manager.py](collection/clone_manager.py))
- `collection/db.py` ([collection/db.py](collection/db.py))
- `collection/csv_adapter.py` ([collection/csv_adapter.py](collection/csv_adapter.py))
- `collection/human_corpus.py` ([collection/human_corpus.py](collection/human_corpus.py))
- `collection/agent_corpus.py` ([collection/agent_corpus.py](collection/agent_corpus.py))

## Clone lifecycle and disk safety
- Clones are created in a per-run temporary root and removed when the clone context exits (ephemeral clones). Use `temp_clone_commit_history()` for commit-history clones.
- Before cloning, `ensure_free_space(path, min_bytes)` is used to check available disk; callers can set `min_free_bytes` to fail early and avoid uncontrolled disk growth.
- A pruning utility `prune_old_clones(clones_dir, max_age_seconds)` is provided to recover disk from stale runs.

Operational note: choose conservative `min_free_bytes` values for shared CI runners and tune `clones_dir` to point at a large-volume filesystem.

## Concurrency and DB pattern
- Extraction uses a pool of workers (ThreadPoolExecutor) to parallelize per-repository extraction while preserving a single-writer pattern for cross-references.
- Avoid nested write transactions with SQLite. The implemented pattern is:
  - Per-repo persistence: short-lived write transactions to insert repository, test_files, fixtures, test_commits, and commit_observations.
  - Cross-repo sampled inserts (e.g., `human_inter_fixtures`): coordinated batched inserts inside a single transaction using `insert_human_inter_fixtures_coordinated(db_path, selected_fixtures, seed, batch_size)` to perform lookups and `executemany()` batches.
- DB connection defaults: `PRAGMA journal_mode=WAL`, `PRAGMA busy_timeout` set to a generous value to reduce transient `database is locked` errors.

## Sampling modes
- Within-repository (paired): sample human fixtures from the same repositories and same temporal window as agent fixtures, stratified by language and (optionally) repository.
- Inter-repository (unpaired): build a candidate pool from pre-2021 commits and sample to match per-language agent totals. The pipeline supports a `--mode inter` flag to enable this flow.

## CSV and IO
- Use the `csv_adapter` to read/write CSVs and to plug alternative persistence backends. Tests override the adapter to avoid filesystem dependencies.

## Operational Runbook (concise)
1. Ensure `clones_dir` is set to a path with sufficient free space.
2. Run agent extraction per language to build the agent fixture set.
3. Optionally run the human extraction flow in `within` mode (paired) or `inter` mode (pre-2021 candidate pool + coordinated bulk insert).
4. Inspect `between-group.db` and the `human_within_fixtures` / `human_inter_fixtures` tables for sample provenance.

## Troubleshooting
- If you observe frequent SQLite `database is locked` errors: ensure callers are not opening nested write transactions and prefer the coordinated bulk-insert helper for inter-repo sampled inserts.
- If clones fill disk: raise `min_free_bytes` and run `prune_old_clones()` on the clones directory.

## Tests and CI
- The collection subsystem has unit and integration tests under `tests/` (e.g., `tests/test_clone_manager.py`) and a small performance check for bulk inserts. CI runs these to validate logic and performance bounds. The docs intentionally avoid test-level detail.

If you want, I can add a short diagram or a quick-start checklist for running the collection pipeline on a new machine.
