# Run Commands: Toy and Full Datasets

Copy-paste reference for actually running collection, one command per dataset. All
verbs go through the unified CLI: `python -m collection <verb> --dataset {a,b,c}`
(see `AGENTS.md` for the full verb-to-dataset matrix and `collection/paths.py` for
where each verb reads/writes).

Dataset A = agent-authored fixtures. Dataset B = human-authored, within-repo control
(same repos as A). Dataset C = human-authored, cross-repo baseline (independent
pre-2021 repo pool).

## Toy datasets

Small, real, end-to-end runs under `toy-dataset/` — structurally isolated from
`datasets/`/`db/` (see `collection/paths.py`'s `root=TOY_ROOT` parameter), so these
are always safe to run without touching real collected data. Default is 5 repos;
add `--language <lang>` to restrict to one language, `--stratified` for a
Cochran-sized representative sample instead of a fixed count.

```bash
# Dataset A
python -m collection toy --dataset a

# Dataset B
python -m collection toy --dataset b

# Dataset C
python -m collection toy --dataset c
```

Each run writes `toy-dataset/{dataset}/...` (mirroring the real `datasets/{dataset}/`
layout) plus `toy-dataset/db/{dataset}.db`, and finishes by writing
`toy-dataset/{dataset}/summary.yaml`.

## Full datasets

No single verb runs a dataset end-to-end — each dataset chains a different subset of
verbs (not every verb applies to every dataset; `discover-commits` is Dataset A only,
`filter-test-commits` is Datasets A/B only). Chained below with `&&` so each block is
one command to paste.

**Run Dataset A first.** Dataset B's repo pool is resolved from Dataset A's output
(same agent-enabled repos, human commits only) — see `collection/repo_resolve.py`.

```bash
# Dataset A (agent-authored fixtures)
python -m collection discover-repos --dataset a --workers 16 \
  && python -m collection discover-commits --dataset a --workers 16 \
  && python -m collection filter-test-commits --dataset a --workers 16 \
  && python -m collection extract-fixtures --dataset a
```

```bash
# Dataset B (human-authored, within-repo control) — run after Dataset A completes
python -m collection discover-repos --dataset b --workers 16 \
  && python -m collection filter-test-commits --dataset b --workers 16 \
  && python -m collection extract-fixtures --dataset b --workers 16
```

```bash
# Dataset C (human-authored, cross-repo baseline) — independent of A/B
python -m collection discover-repos --dataset c --workers 16 \
  && python -m collection extract-fixtures --dataset c --workers 16
```

Each writes `datasets/{dataset}/...` and `db/{dataset}.db`.

### Notes

- **`--workers N`** sets concurrent worker threads for that verb's clone/scan-bound
  work; DB and CSV writes stay on the main thread regardless. All of this is git
  clone / disk I/O, not GitHub REST API calls, so the real ceiling is GitHub's
  concurrent-connection abuse detection and the single SQLite writer serializing DB
  inserts — **not CPU core count**. More cores don't relax either constraint, so
  even on a 24-core box the commands above pin every verb to 16, the top of the
  range the codebase itself documents as safe without further testing (see
  `--workers`'s help text on the `toy` verb, `collection/__main__.py`, for the exact
  reasoning). Push higher only after you've watched a run for clone failures /
  `database is locked` retries at 16 and confirmed there's headroom.
  - `discover-repos`/`discover-commits`/`filter-test-commits` all honor `--workers`
    directly.
  - `extract-fixtures --dataset a` **ignores `--workers` entirely** — its collector
    interleaves DB writes into a per-repo loop and stays single-threaded by design
    (confirmed: no `ThreadPoolExecutor` anywhere in `agent_corpus.py`). Passing the
    flag wouldn't error, just silently do nothing, so it's omitted above rather than
    left in as a no-op that looks like it's doing something.
  - `extract-fixtures --dataset b` *did* silently drop `--workers` the same way
    until `collection/__main__.py` was fixed to actually pass it through to
    `HumanCorpusCollector.run()` — that same fix also removed a `languages=...` kwarg
    the collector never accepted, which meant a real (non-mocked) `extract-fixtures
    --dataset b` run crashed with `TypeError` before reaching any fixture extraction
    at all. Caught via `tests/collection/test_main_cli.py`'s
    `test_dataset_b_run_call_matches_real_signature` (uses `autospec=True` so the
    mock enforces the real method signature instead of silently accepting anything).
- **`--language <lang>`** narrows any verb to one language (default: all four —
  python/java/javascript/typescript). Useful for a partial/incremental run.
- **`--tier2`** (Dataset A's `discover-commits` only): if Tier-1 commit-trailer
  detection yields too few agent commits, also runs Tier-2 SEART-based discovery
  against `db/corpus.db`. Requires that DB to exist first — bootstrap it with
  `python -m collection paired` if you intend to use `--tier2`. Off by default; the
  commands above don't need it.
- Each verb is checkpointed and safe to re-run — already-completed languages/repos
  are skipped, not redone (see each collector's `is_global_checkpoint_completed`
  usage in `collection/db.py`).

### After collection

Not part of "running" a dataset, but the usual next steps once a dataset's
`extract-fixtures` has completed:

```bash
python -m collection summarize --dataset a   # writes datasets/a/summary.yaml
python -m collection sample     --dataset a   # stratified-samples db/a.db
python -m collection export     --dataset a   # writes export/a.zip
python -m collection validate   --dataset a   # checks export/a.zip
```

Same four commands with `--dataset b` / `--dataset c` for the other two datasets.
`analyze-distribution` is the one pair-aware verb (defaults to `--dataset a --against b`)
since its whole job is comparing two already-extracted datasets.

## See also

- `AGENTS.md` — full verb-to-dataset matrix and repo/module layout
- `docs/getting-started/repository-structure.md` — full directory layout
- `docs/usage/reproducing.md` — reproducing published results end-to-end
