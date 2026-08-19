# Dataset A's `pushed_at` was never threaded through

**Status: Fixed, 2026-08-19.**

## 1. Found during a manual Dataset A health check

A comprehensive Dataset A health check (100-repo sample, 100-commit
sample, 100-fixture-per-language sample, full schema/distribution audit)
found `repositories.pushed_at` empty for all 3,776 repos in `db/a.db` --
100%, not a partial gap. Same symptom as the bug already found and fixed
in Dataset C's own pipeline (see
[dataset-c-repo-selection.md](dataset-c-repo-selection.md)'s section 11),
but a genuinely separate bug: Dataset A has its own repo-discovery
writer, `collection/repository_quality_control/agent_repository_counter.py`,
entirely independent of Dataset C's `select_dataset_c_repos.py`.

## 2. Root cause: the same class of gap, a different pipeline

Traced end to end, `pushed_at` was missing at every hop:

1. `agent_repository_counter.py`'s raw-CSV scan read `row.get("createdAt")`
   but never `row.get("pushedAt")` -- even though the raw source is the
   same SEART `github-search-raw/*.csv.gz` export Dataset C reads, which
   does have a real `pushedAt` column.
2. `_process_single()`'s `meta`/`row` dicts (the per-repo QC pipeline)
   never carried a `pushed_at` key either.
3. `_TIER2_REPO_FIELDNAMES` in `collection/__main__.py` (Tier 2's fixed
   CSV column schema, for repos discovered via SEART matching rather than
   the direct Tier 1 scan) had no `pushed_at` column, and
   `_merge_tier2_repos_into_csv()`'s row-building dict didn't set one --
   so even though `repositories.pushed_at` already exists as a real DB
   column, Tier 2 never read it back out when merging repos into
   `datasets/a/repos/{lang}_repo.csv`.
4. `agent_corpus.py::_load_qc_repo_rows()` (the function that reads
   `datasets/a/repos/{lang}_repo.csv` back in) called `build_repo_row()`
   -- which already accepts and threads a `pushed_at` parameter, reused
   from Dataset B/C's own `build_repo_row()` calls -- but never passed
   `pushed_at=row.get("pushed_at")` at this call site. This is the one
   hop that doesn't exist in Dataset C's version of the bug: the shared
   helper was already correct, only this one caller wasn't using it.
5. `agent_corpus.py`'s final `construct_repo_dict(..., pushed_at=repo.get("pushed_at", ""))`
   call was already correct -- same as Dataset C's equivalent call site --
   it simply had nothing upstream to read.

No existing test caught any of this: nothing exercised `pushed_at`
end-to-end for Dataset A before now, the same reason section 8 and
section 11 of the Dataset C doc went uncaught for as long as they did.

## 3. Fix

Added the missing line at each of the four hops above (Tier 1's raw scan,
`_process_single()`, Tier 2's `_TIER2_REPO_FIELDNAMES`/merge dict, and
`_load_qc_repo_rows()`'s `build_repo_row()` call), mirroring the existing
`created_at`/`forks` pattern at each site exactly. `pushed_at` is kept at
full ISO precision (no `[:10]` truncation), matching
`select_dataset_c_repos.py`'s identical convention for the same raw
field.

Tier 1's CSV write derives its header dynamically from `list(row.keys())`,
so it picks up the new column automatically. Tier 2's write uses the
fixed `_TIER2_REPO_FIELDNAMES` list, now updated to match --
`append_dicts()` raises `ValueError` on any header mismatch between the
two writers sharing one file, so a schema drift here would have failed
loudly rather than silently, and `tests/collection/test_merge_tier2_repos.py`
already exists specifically to catch this class of drift (originally
written for an earlier `forks`-column version of the same bug).

New tests: `tests/collection/test_agent_repository_counter.py` (Tier 1
raw-CSV read-through, `_process_single()` carries it into the row, both
present and absent-defaults-to-`""` cases), `tests/collection/test_merge_tier2_repos.py`
(Tier 2 carries it through, and the Tier1/Tier2 schema-compatibility test
now also asserts on `pushed_at` specifically), and a new
`tests/collection/test_agent_corpus_repo_loading.py` (direct coverage of
`_load_qc_repo_rows()`, which had no dedicated test at all before this).

## 4. Caveat, not yet acted on

Same as Dataset C's equivalent fix: this doesn't retroactively backfill
`pushed_at` for the 3,776 repos already in `db/a.db`. `datasets/a/repos/{lang}_repo.csv`
only gets the new column after `discover-repos --dataset a` is re-run;
`agent_corpus.py`'s per-language completion checkpoint
(`agent_complete:{lang}`) means a plain re-run of `extract-fixtures --dataset a`
without `--force` would skip every already-`analysed` repo and do nothing.
A full backfill requires re-running discovery, then `extract-fixtures
--dataset a --force` (safe -- `persist_repository_and_fixtures()`'s
upsert/`ON CONFLICT DO NOTHING` makes re-processing idempotent) for every
language.
