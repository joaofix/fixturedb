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
python -m collection discover-repos --dataset a --workers 8 \
  && python -m collection discover-commits --dataset a --workers 8 \
  && python -m collection filter-test-commits --dataset a --workers 8 \
  && python -m collection extract-fixtures --dataset a --workers 8
```

```bash
# Dataset B (human-authored, within-repo control) — run after Dataset A completes
python -m collection discover-repos --dataset b --workers 8 \
  && python -m collection filter-test-commits --dataset b --workers 8 \
  && python -m collection extract-fixtures --dataset b --workers 8
```

```bash
# Dataset C (human-authored, cross-repo baseline) — independent of A/B
python -m collection discover-repos --dataset c --workers 8 \
  && python -m collection extract-fixtures --dataset c --workers 8
```

Each writes `datasets/{dataset}/...` and `db/{dataset}.db`.

### Notes

- **`--workers N`** sets concurrent worker threads for that verb's clone/scan-bound
  work; DB and CSV writes stay on the main thread regardless. Every verb in the
  chains above accepts it with its own tuned default if omitted (`discover-repos`:
  8, `discover-commits`: 4, `filter-test-commits`: 12, `extract-fixtures`: 8) — the
  commands above pin all of them to 8 for a predictable, uniform load; raise or
  lower per verb as your machine and GitHub rate limits allow.
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
