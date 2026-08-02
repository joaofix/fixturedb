# Collection Module Architecture

This document describes the architecture, key components, and operational guidance for the `collection` subsystem used to discover, clone, and extract fixtures from repositories.

## Goals

- Produce reproducible, labelled fixture datasets for between-group experiments (within- and inter-repository).
- Ensure clones are ephemeral and disk-safe; minimize SQLite lock contention during bulk inserts.
- Make CSV/IO pluggable for testability and alternate backends.

## Key Components

The collection subsystem has three layered cloning modules — pick the one matching your use case:

- `collection/clone_primitives.py` — the lowest-level primitive: clones a repo into a brand-new tempdir via subprocess, detects credential-gated (private repo) failures. No DB, no throttling, no config.
- `collection/ephemeral_clone.py` — context managers wrapping `clone_primitives.py` with throttling (a global semaphore plus retry/backoff), disk-safety checks (`ensure_free_space()`), and guaranteed cleanup on exit. Exposes `temp_clone_commit_history()` and `clone_with_function()`. Use this for transient inspection — commit-history scans, QC counters.
- `collection/persistent_clone.py` — an independent, DB-tracked workflow that clones into the durable `CLONES_DIR` (not a tempdir), runs pre-clone quality checks, and records status in SQLite via `db.py`. Use this for the main repository corpus, not for one-off inspection.

`clone_repo_for_commit_scan()` and `temp_clone_commit_history()` both accept an optional `shallow_since` date. When set, the clone is bounded via `--shallow-since=<date>` instead of fetching full history — Datasets A and B only ever examine commits since `AGENT_CORPUS_START_DATE`, so most of their clones don't need anything older. Because git's shallow-boundary negotiation can, at a merge commit, silently cut off in-window history that a naive `--shallow-since` clone would need, the result is verified locally (`clone_primitives._shallow_clone_is_truncated`) before being trusted: a flagged clone is discarded and re-fetched with full history, so callers always get a correct clone, just faster when it's safe to be. Callers pass `shallow_since=config.shallow_clone_since(since_date)` explicitly — the primitives themselves stay config-free.

Dataset C's clone site (`dataset_c.py`) and the discover-repos agent-config check (`agent_repository_counter.py`) intentionally leave `shallow_since` unset. Dataset C's temporal logic finds the last commit *before* a fixed cutoff, which a forward-bounded `--shallow-since` doesn't fit, and the agent-config check only needs the working tree at HEAD — a separate, unexplored optimization opportunity, not "bound to the analysis window."

Other key components: `collection/db.py` (database schema and helpers), `collection/csv_adapter.py` (a pluggable CSV adapter — production code uses a file-backed adapter, but tests can swap implementations), and `collection/agent_corpus.py` / `collection/human_corpus.py` / `collection/dataset_c.py` (orchestration of the agent and human extraction flows, calling into the clone manager and DB helpers).

## Dataset A / B / C build map

Each dataset is built through the same `python -m collection <verb> --dataset {a,b,c}` CLI, calling exactly one collector/function per dataset for each verb — there is no runtime branching that decides which dataset a given run produces:

| Dataset | What it is | `extract-fixtures` entry point | Collector / function |
|---|---|---|---|
| A | Agent-authored fixtures | `extract-fixtures --dataset a` | `agent_corpus.AgentCorpusCollector` |
| B | Human-authored fixtures, within-repo matched control | `extract-fixtures --dataset b` | `human_corpus.HumanCorpusCollector.run()` |
| C | Human-authored fixtures, cross-repo pre-2021 baseline | `extract-fixtures --dataset c` | `dataset_c.collect_dataset_c_fixtures()` |

## Clone lifecycle and disk safety

Ephemeral clones (via `ephemeral_clone.py`) are created in a per-run temporary root and removed when the clone context exits — use `temp_clone_commit_history()` for commit-history clones. Before cloning, `ensure_free_space(path, min_bytes)` checks available disk; callers can set `min_free_bytes` to fail early and avoid uncontrolled disk growth. A pruning utility, `prune_old_clones(clones_dir, max_age_seconds)`, recovers disk from stale runs.

Operational note: choose conservative `min_free_bytes` values for shared CI runners, and point `clones_dir` at a large-volume filesystem.

## Concurrency and DB pattern

Extraction uses a pool of workers (`ThreadPoolExecutor`) to parallelize per-repository extraction while preserving a single-writer pattern for cross-references. Avoid nested write transactions with SQLite — per-repo persistence uses short-lived write transactions (via `corpus_utils.persist_repository_and_fixtures()`) to insert repository, test_files, fixtures, and mock_usages rows. DB connections default to `PRAGMA journal_mode=WAL` with a generous `PRAGMA busy_timeout` to reduce transient `database is locked` errors.

## Sampling modes

Dataset B (within-repo, paired) samples human fixtures from the same repositories and same 2025+ temporal window as Dataset A, stratified by language.

Dataset C (cross-repo, unpaired) selects rather than samples repos: `discover-repos --dataset c` (wrapping `select_dataset_c_repos.py`) takes every repo created within a fixed window (`DATASET_C_MIN_CREATED_DATE` to `HUMAN_CORPUS_CUTOFF_DATE`), with no stratification or cap. `dataset_c.py` then checks out each one at its own pinned pre-2021 cutoff commit and extracts every fixture from every test file at that snapshot, with no diff/purity gating. Test-file discovery (`find_test_files_with_language()`) checks every file's own language against its own extension, not the repo's tagged language, so a multi-language repo's non-primary-language test files are found and correctly labeled — the same as Datasets A/B's commit-diff-based discovery (see "Cross-language fixture leakage" in `docs/reference/limitations.md`).

## Repository deduplication

`github-search-raw/`'s source query excludes GitHub-native forks (`isFork`), but not org transfers or independently-created "shadow copies" — two different `repo_name`s that share partly or fully identical git history. A shared commit SHA is a cryptographic guarantee of identical content, so it's used directly as the dedup key throughout. Four mechanisms, matched to each dataset's shape and to how far along the pipeline duplication is detectable, share their tie-break/clustering logic via `collection/repo_dedup_utils.py` (`pick_cluster_survivor()`: highest stars, tie-break lowest `github_id` by default, or an injected `tie_break_key` for callers without one; `find_duplicate_clusters()`: groups by an injected key function):

- **Dataset C** (`collection/dedupe_dataset_c_repos.py`) — a single fixed-cutoff snapshot per repo, so one GitHub API call per candidate (`commits?until=...`) resolves each repo's commit at `HUMAN_CORPUS_CUTOFF_DATE`, and repos resolving to the same commit are clustered. This is a standalone/manual tool, not part of the automatic pipeline — rerun by hand (`python -m collection.dedupe_dataset_c_repos`) whenever `github-search-raw/` is refreshed. Output: `datasets/c/repos/duplicate_repos.csv`, consulted by `select_dataset_c_repos.py` at build time as a pure CSV filter, with no API calls at runtime.
- **Dataset A, repo-level pre-filter** (`agent_repository_counter.py::_dedupe_by_last_commit_sha()`) — no API calls, no separate run. It groups candidates by `lastCommitSHA` (already present in the raw SEART export for free) inline, every time `discover-repos --dataset a` runs, before the has_agent_config clone check. This is zero-cost but only a partial fix: it catches repos still byte-identical *today*, not pairs that have since diverged. It also persists the same rows to `github-search-raw/duplicate_repos_by_current_commit.csv`.
- **Datasets A and B, commit-level post-filter** (`collection/dedupe_commits_by_sha.py`) — catches what the repo-level pre-filter can't: a pair that has diverged still shares commit history up to the divergence point, so any `commit_sha` collected under more than one `repo_name` is still proof of shared identity, discoverable once commits are actually collected rather than needing a live pre-check. Also zero API calls, since everything needed is already in the commit-level and repo-level CSVs. Run explicitly, once per dataset, between commit collection and fixture extraction (`--dataset a` on `datasets/a/commits/`, `--dataset b` on `datasets/b/test-commits/` — B needs its own pass despite inheriting A's repo pool, since B does its own live commit scan rather than reusing A's classification). Writes an audit CSV (`duplicate_commits_removed.csv`) alongside the commit CSVs it rewrites. This step is fully preventive for Dataset A only, since `extract-fixtures --dataset a` reads its commit list from the exact file it cleans — it has no effect on Dataset B's fixtures, because `extract-fixtures --dataset b` never reads `datasets/b/test-commits/*.csv` at all. It independently re-clones and re-scans every repo's full history itself, so it silently rediscovers the same duplicate commits regardless of how clean that file is. See the next item for what actually protects Dataset B.
- **Dataset B, post-extraction fixture-level cascade** (`collection/dedupe_fixtures_by_sha.py`) — the same duplicate-detection core as above, reused directly, but aimed at `datasets/b/fixtures/*.csv` and run *after* `extract-fixtures --dataset b` instead of before, since that's the earliest point where duplicates are both visible and match what extraction actually produced. It also cascades the removal into `db/b.db`'s `fixtures`/`mock_usages` tables and re-syncs the denormalized aggregate columns (`test_files.num_fixtures`/`total_fixture_loc`, `repositories.num_fixtures`/`num_mock_usages`) those deletes leave stale. Unlike every other mechanism here, this is a recurring cleanup, not a one-time fix — run it after every `extract-fixtures --dataset b` invocation, including per-language re-runs. Confirmed at scale on a real run: 36.6% of Dataset B's extracted Python fixtures shared a `commit_sha` with a different `repo_name` before this step ran. See `internal-docs/methodology-improvements/repo-deduplication.md` section 9 for why extraction can't yet consume the deduped commit CSV directly, which would make this one-time too.

Full rationale, empirical checks, and what was deliberately left out of scope: `internal-docs/methodology-improvements/repo-deduplication.md`.

## CSV and IO

Use the `csv_adapter` to read/write CSVs and to plug in alternative persistence backends. Tests override the adapter to avoid filesystem dependencies.

## Operational Runbook (concise)

1. Ensure `clones_dir` is set to a path with sufficient free space.
2. Run `discover-repos`/`filter-test-commits`/`extract-fixtures --dataset b` (Dataset B), then `discover-repos`/`extract-fixtures --dataset c` (Dataset C).
3. Run `discover-repos`/`discover-commits`/`filter-test-commits`/`extract-fixtures --dataset a` (Dataset A).
4. Continue with `analyze-distribution`/`sample`/`export`/`validate` (per dataset).
5. Inspect `db/{a,b,c}.db` and the `repositories`/`fixtures`/`mock_usages` tables for sample provenance.
6. When a manual-validation sample is needed for the paper, run `collection/validation_sampling.py` by hand against that step's output CSV(s) — see [Manual-Validation Sampling](../usage/validation-sampling.md). This isn't part of the automatic runbook.

## Troubleshooting

- Frequent SQLite `database is locked` errors: ensure callers aren't opening nested write transactions.
- Clones filling disk: raise `min_free_bytes` and run `prune_old_clones()` on the clones directory.

## Tests and CI

The collection subsystem has unit and integration tests under `tests/` (e.g. `tests/test_clone_manager.py`, which tests `ephemeral_clone.py`) and a small performance check for bulk inserts. CI runs these to validate logic and performance bounds. These docs intentionally avoid test-level detail.
