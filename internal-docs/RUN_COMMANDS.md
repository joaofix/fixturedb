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
python3 -m collection discover-repos --dataset a --workers 16 \
  && curl -d "Dataset A 1/5: discover-repos finished" ntfy.sh/joaofix_fixturedb \
  && python3 -m collection discover-commits --dataset a --workers 16 \
  && curl -d "Dataset A 2/5: discover-commits finished" ntfy.sh/joaofix_fixturedb \
  && python3 -m collection.dedupe_commits_by_sha --dataset a \
  && curl -d "Dataset A 3/5: dedupe_commits_by_sha finished" ntfy.sh/joaofix_fixturedb \
  && python3 -m collection filter-test-commits --dataset a --workers 16 \
  && curl -d "Dataset A 4/5: filter-test-commits finished" ntfy.sh/joaofix_fixturedb \
  && python3 -m collection extract-fixtures --dataset a --workers 16 \
  && curl -d "Dataset A 5/5: extract-fixtures finished (collection complete)" ntfy.sh/joaofix_fixturedb
```

```bash
# Dataset B (human-authored, within-repo control) — run after Dataset A completes
python3 -m collection discover-repos --dataset b \
  && curl -d "Dataset B 1/5: discover-repos finished" ntfy.sh/joaofix_fixturedb \
  && python3 -m collection filter-test-commits --dataset b --workers 16 \
  && curl -d "Dataset B 2/5: filter-test-commits finished" ntfy.sh/joaofix_fixturedb \
  && python3 -m collection.dedupe_commits_by_sha --dataset b \
  && curl -d "Dataset B 3/5: dedupe_commits_by_sha finished" ntfy.sh/joaofix_fixturedb \
  && python3 -m collection extract-fixtures --dataset b --workers 16 \
  && curl -d "Dataset B 4/5: extract-fixtures finished" ntfy.sh/joaofix_fixturedb \
  && python3 -m collection.dedupe_fixtures_by_sha --dataset b \
  && curl -d "Dataset B 5/5: dedupe_fixtures_by_sha finished (collection complete)" ntfy.sh/joaofix_fixturedb
```

```bash
# Dataset C (human-authored, cross-repo baseline) — independent of A/B
python3 -m collection discover-repos --dataset c \
  && curl -d "Dataset C 1/4: discover-repos (pass 1) finished" ntfy.sh/joaofix_fixturedb \
  && python3 -m collection.dedupe_dataset_c_repos \
  && curl -d "Dataset C 2/4: dedupe_dataset_c_repos finished" ntfy.sh/joaofix_fixturedb \
  && python3 -m collection discover-repos --dataset c \
  && curl -d "Dataset C 3/4: discover-repos (pass 2, post-dedupe) finished" ntfy.sh/joaofix_fixturedb \
  && python3 -m collection extract-fixtures --dataset c --workers 16 \
  && curl -d "Dataset C 4/4: extract-fixtures finished (collection complete)" ntfy.sh/joaofix_fixturedb
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
  - `extract-fixtures --dataset a` honors `--workers` (added later than the rest of
    this table -- it used to ignore the flag entirely, single-threaded by design,
    with no `ThreadPoolExecutor` anywhere in `agent_corpus.py`). Now shares the same
    thread-pool harness as `--dataset b` (`collection/parallel_utils.py
    ::run_parallel_per_repo()` -- each repo's result is persisted immediately as it
    completes, so a crash mid-batch only loses whatever repo was still in flight).
    `--dataset c` still has its own separate `ThreadPoolExecutor`, not this harness
    -- see that collector's own comment for why.
  - `extract-fixtures --dataset b` *did* silently drop `--workers` the same way
    until `collection/__main__.py` was fixed to actually pass it through to
    `HumanCorpusCollector.run()` — that same fix also removed a `languages=...` kwarg
    the collector never accepted, which meant a real (non-mocked) `extract-fixtures
    --dataset b` run crashed with `TypeError` before reaching any fixture extraction
    at all. Caught via `tests/collection/test_main_cli.py`'s
    `test_dataset_b_run_call_matches_real_signature` (uses `autospec=True` so the
    mock enforces the real method signature instead of silently accepting anything).
  - If you split `extract-fixtures --dataset b` into separate per-language calls
    (rather than the single all-languages call above), no `--force` is needed
    between them, and none should be added — each call correctly gates on its
    own `human_within_complete:{lang}` DB checkpoint regardless of what other
    languages already ran. This didn't always hold: a dataset-wide
    `database_has_rows(output_db, "fixtures")` check used to run before that,
    so a repo tagged one language but containing test files in another (a
    genuine, expected outcome, not a bug -- see
    `docs/architecture/collection.md`'s "Repository deduplication") could make
    an earlier language's run insert a handful of rows that then caused every
    subsequent `--language X` call to see the DB as "already has fixture
    rows" and skip X entirely, silently, even without `--force`. Removed in
    `collection/__main__.py`; regression test:
    `test_dataset_b_does_not_skip_when_db_already_has_fixtures_from_another_language`.
    Datasets A and C still have this dataset-wide gate -- untouched, since
    neither is ever run split per-language today.
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
  duplicate content in the corpus. Until this was fixed, the *second*
  `discover-repos --dataset c` call never actually applied the filter either
  (`__main__.py` called `select_repos()`/`write_per_language_files()`
  directly, skipping `filter_known_duplicates()` entirely) — every run
  through at least 2026-07-21 silently kept all known duplicates regardless
  of how many times this command chain ran; one such run measured 16.2% of
  the whole Dataset C corpus as duplicate content this way (worst cluster: 5
  OpenJDK-derived repos sharing one commit). Requires `GITHUB_TOKEN` (one
  `commits?until=...` API call per candidate repo — real GitHub REST API
  traffic, unlike every other command in this file) and is independently
  checkpointed/resumable — see `collection/dedupe_dataset_c_repos.py`'s module
  docstring. Standalone/manual by design: only rerun it when
  `github-search-raw/` is refreshed or Dataset C's candidate pool otherwise
  changes, not on every Dataset C build.
- **`dedupe_commits_by_sha.py` (Datasets A and B) removes commits duplicated
  across repo_names that share git history** — org transfers/renames whose
  history has since diverged (e.g. `camunda-cloud/zeebe`/`camunda/zeebe`),
  which `agent_repository_counter.py`'s own current-HEAD-commit dedup can't
  catch (see that module and `docs/reference/limitations.md`'s
  "Repository-Level Duplication"). Unlike Dataset C's dedup, this makes no
  API calls (everything it needs -- `commit_sha`, `repo_name`, `stars`,
  `created_at` -- is already sitting in the commit-level and repo-level
  CSVs from the steps before it), so it's cheap to run every time. Placed
  right before `filter-test-commits`/`extract-fixtures`; see
  `collection/dedupe_commits_by_sha.py`'s module docstring for the
  commit-SHA-as-proof-of-shared-history reasoning and why this is safer
  than filtering at the repo level. **This is a one-time, permanent fix for
  Dataset A only** — `extract-fixtures --dataset a` reads its commits
  straight from the file this step just cleaned, so a duplicate removed
  here never gets extracted, on this run or any future one. **It has no
  effect on Dataset B's fixtures** — `extract-fixtures --dataset b`
  (`HumanCorpusCollector`) never reads `datasets/b/test-commits/*.csv` at
  all; it independently re-clones and re-scans every repo's full history
  itself, silently rediscovering the exact same duplicate commits under
  every repo_name variant regardless of how clean that CSV is. Confirmed on
  a real run: 36.6% of Dataset B's extracted python fixtures shared a
  `commit_sha` with a different `repo_name`. That's what the next step
  below actually fixes for B.
- **`dedupe_fixtures_by_sha.py` (Dataset B only) removes the same
  cross-repo-name duplicate commits, but from the already-extracted
  fixture CSVs and `db/b.db` directly** — a recurring cleanup, not a
  one-time fix like the step above. Run it after *every*
  `extract-fixtures --dataset b` invocation, including per-language
  re-runs, not just once; a clean state finds nothing to remove and
  leaves everything untouched, so it's always safe to run again. Reuses
  the exact same duplicate-detection logic as `dedupe_commits_by_sha.py`
  (same `find_duplicate_commit_rows`/`pick_cluster_survivor`), just aimed
  at `datasets/b/fixtures/*.csv` instead, and additionally cascades the
  removal into `db/b.db`'s `fixtures`/`mock_usages` tables and re-syncs
  the denormalized aggregate columns
  (`test_files.num_fixtures`/`total_fixture_loc`,
  `repositories.num_fixtures`/`num_mock_usages`) for every repo touched,
  since those are snapshot columns written once at persist time, not kept
  live. Restructuring `extract-fixtures --dataset b` to consume the
  deduped commit CSV directly (making this a one-time fix like Dataset
  A's) is a real architecture change, deliberately deferred — see
  `collection/dedupe_fixtures_by_sha.py`'s module docstring and
  `internal-docs/methodology-improvements/repo-deduplication.md` section 9.
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

### Required before running any `research_questions/` script

Dataset C's full collection is ~3.3x Dataset A's size -- running the RQ
comparisons against that imbalance is methodologically unsound. Every
`research_questions/*.py` script (`rq1.py`/`rq2.py`/`rq3.py`/`balance.py`/
`language_contamination.py`) reads a sampled-down Dataset C
(`db/c_sampled.db` + `datasets/c/fixtures-sampled/`) instead of the full one
(`db/c.db` + `datasets/c/fixtures/`) -- this is enforced, not optional (see
`collection/research_questions/_shared.py::require_db_or_none()`'s and
`language_contamination.py::check_dataset()`'s "c" handling): if the sampled
artifact doesn't exist yet, Dataset C's section just reports "not available,"
it never silently falls back to the full DB.

Run this once Dataset A and C have both finished `extract-fixtures`,
**before** running any `research_questions/` script:

```bash
python -m collection sample-c-repos --match-dataset a
  && curl -d "sample-c-repos finished" ntfy.sh/joaofix_fixturedb
```

Samples whole Dataset C repos (never splits one -- see
`collection/dataset_sampler.py::sample_repos_by_language()`'s docstring for
why fixture-level sampling would distort RQ2's setup-to-teardown metrics),
stratified by language using Dataset C's own original per-language
proportions, down to `--match-dataset a`'s current live fixture count (or
pass an explicit `--target-count N` instead). Writes `db/c_sampled.db` +
`datasets/c/fixtures-sampled/*.csv` + a summary at `output/sample_c_repos.json`
-- `db/c.db`/`datasets/c/fixtures/*.csv` are read-only inputs, never
modified. Re-running it fully rebuilds the sampled artifact (not additive) --
safe to re-run after any change to Dataset A's or C's underlying data.

### One-time: backfill "All commits" for Dataset A's summary table

`dataset_findings.py`'s "Commits and Repositories Summary" section reports
"All commits" (non-merge commits since `AGENT_CORPUS_START_DATE`, agent+
human+bot alike) straight from `db/a.db`'s `repositories.total_commits_
since_agent_start` column. `agent_corpus.py`'s `analyze` stage now always
sets this column going forward (it already computed the number live, to
derive `agent_adoption_intensity` -- this just also persists it), so a
fresh Dataset A collection needs nothing extra. Repos collected *before*
this column existed have it `NULL`; backfill them once:

```bash
python -m collection backfill-total-commits --workers 16 \
  && curl -d "backfill-total-commits finished" ntfy.sh/joaofix_fixturedb
```

Re-clones (shallow-since, blob-filtered -- same clone shape `analyze`
already uses) every repo in `db/a.db` still missing the column and re-derives
it via the same `count_total_commits_since()` call, so a backfilled row
means exactly the same thing as one a fresh `analyze` run would produce.
Resumable and safe to re-run: each repo is written to the DB the moment it's
computed, and already-populated repos are never re-selected. Repos that fail
to re-clone (renamed/deleted/network trouble) are left `NULL` and picked up
by the next run -- `dataset_findings.py`'s query sums only non-NULL rows, so
a partial backfill just under-counts rather than crashing.

## See also

- `AGENTS.md` — full verb-to-dataset matrix and repo/module layout
- `docs/getting-started/repository-structure.md` — full directory layout
- `docs/usage/reproducing.md` — reproducing published results end-to-end
