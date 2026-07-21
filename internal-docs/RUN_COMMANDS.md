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
python -m collection discover-repos --dataset b \
  && python -m collection filter-test-commits --dataset b --workers 16 \
  && python -m collection extract-fixtures --dataset b --workers 16
```

```bash
# Dataset C (human-authored, cross-repo baseline) — independent of A/B
python -m collection discover-repos --dataset c \
  && python -m collection.dedupe_dataset_c_repos \
  && python -m collection discover-repos --dataset c \
  && python -m collection extract-fixtures --dataset c --workers 16
```

Each writes `datasets/{dataset}/...` and `db/{dataset}.db`.

### Notes

- **`--workers N`** sets concurrent worker threads for that verb's clone/scan-bound
  work; DB and CSV writes stay on the main thread regardless. **Not CPU core
  count** is the ceiling here — the `discover-repos`/`discover-commits`/
  `filter-test-commits`/`extract-fixtures` commands above make zero GitHub REST API
  calls (verified: the only two `api.github.com` call sites in the whole package,
  `agent_signal_primitives.py`'s Contents-API check and `persistent_clone.py`'s
  Code-Search-API call, both live exclusively inside `Tier2RepoMatcher` in
  `tiered_agent_corpus_scanner.py`, reachable only via `discover-commits --dataset a
  --tier2`, which none of those commands use — `dedupe_dataset_c_repos.py` is a
  separate, real exception, see below). Every clone here is also plain
  anonymous `git clone` over HTTPS — `clone_primitives.py`/`ephemeral_clone.py`
  never read `GITHUB_TOKEN`, so there's no authenticated-tier allowance to raise
  even if you set one. So the actual ceiling is GitHub's own throttling on many
  concurrent *anonymous* clone connections from one IP, plus the single SQLite
  writer serializing DB inserts — neither of which more cores relax. 16 is the top
  of the range the codebase's own `toy`-verb `--workers` help text documents as
  safe without further testing; push higher only after watching a run for clone
  failures / `database is locked` retries at 16 and confirming there's headroom.
  - **If you do add `--tier2`** to `discover-commits --dataset a`, this changes:
    that path calls the real GitHub REST API, and specifically the Code Search API
    (`persistent_clone.py`), which has a much stricter native limit than the
    general API (10 req/min unauthenticated, 30/min authenticated) — a `GITHUB_TOKEN`
    matters a lot there, and 16 concurrent workers hammering that endpoint would
    exhaust it almost immediately. Not a concern for the commands below since none
    use `--tier2`.
  - `discover-commits`/`filter-test-commits` honor `--workers` directly.
    `discover-repos` only does for `--dataset a` (`agent_repository_counter.run()`
    threads its clone-probe step) -- `--dataset b`/`--dataset c` are both a pure
    local CSV/file transform with no `workers` parameter at all
    (`resolve_dataset_b_repos()`, `select_repos()`), so `--workers` there would be
    a silent no-op; omitted above rather than left in as a no-op that looks like
    it's doing something.
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
- **Dataset C's `discover-repos` runs twice, with `dedupe_dataset_c_repos.py` in
  between.** `dedupe_dataset_c_repos.py` needs Dataset C's already-selected
  candidate pool to check for repos sharing an identical commit at
  `HUMAN_CORPUS_CUTOFF_DATE` (org transfers / independently-created "shadow
  copies" — see `docs/architecture/collection.md`'s "Repository deduplication"
  section) — that pool is written by the *first* `discover-repos --dataset c`
  call. Its own output (`datasets/c/repos/duplicate_repos.csv`) is only
  consulted by a *subsequent* `discover-repos --dataset c` call, which is why
  the command chain runs it twice. A missing `duplicate_repos.csv` is not an
  error — `select_dataset_c_repos.py` just treats it as "no known
  duplicates" — so skipping this step doesn't fail loudly, it silently leaves
  duplicate content in the corpus: the last full run found 16.2% of the whole
  Dataset C corpus was duplicate content this way (worst cluster: 5
  OpenJDK-derived repos sharing one commit). Requires `GITHUB_TOKEN` (one
  `commits?until=...` API call per candidate repo — real GitHub REST API
  traffic, unlike every other command in this file) and is independently
  checkpointed/resumable — see `collection/dedupe_dataset_c_repos.py`'s module
  docstring. Standalone/manual by design: only rerun it when
  `github-search-raw/` is refreshed or Dataset C's candidate pool otherwise
  changes, not on every Dataset C build.
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
