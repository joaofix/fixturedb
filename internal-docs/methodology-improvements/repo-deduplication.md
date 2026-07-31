# Repo-Level Deduplication: Forks, Org Transfers, and Shadow Copies

**Date**: 2026-07-17
**Context**: Manual, fixture-by-fixture review of the freshly-collected Dataset C sample (see `validation-samples/human-fixtures-dataset-c/REVIEW_METHODOLOGY.md`) found a large share of the corpus was duplicate content — different `repo_name`s that are actually the same repository, counted as independent data points. This document records the investigation, the fix, and what was deliberately left unfixed.

---

## 1. Problem

Two different `repo_name` values in `github-search-raw/*.csv.gz` can point at git histories that are partly or fully identical: GitHub org transfers, community mirrors, and "shadow copies" (an independently-created repo object that received a raw `git push` of another repo's existing history) all produce this. Each such pair is counted as two independent repositories — and every fixture in the shared history is counted twice — silently inflating sample size and violating the independence assumption behind every downstream statistical test.

Grouping already-collected fixtures by `commit_sha` and flagging SHAs shared across more than one `repo_name` (a cheap check applied *after* the fact, not part of the pipeline) found:

| Dataset | Duplicate fixtures | Rate |
|---|---:|---:|
| A | 132 / 46,831 | 0.3% |
| B | 33,002 / 184,772 | **17.9%** |
| C | 34,653 / 214,436 | 16.2% |

The worst single cluster: `jetbrains/jetbrainsruntime`, `openjdk/loom`, `openjdk/valhalla`, `sap/sapmachine`, and `openjdk/jdk` all resolve to the same commit (`f5ee356540d7aa4a7663c0d5d74f5fdb0726b426`) — 3,460 identical fixtures each, 17,300 fixtures, 21.9% of Java's entire Dataset C corpus.

All three datasets ultimately source from the same `github-search-raw/*.csv.gz` files (Dataset B's pool is *by construction* Dataset A's own already-found repos, per `repo_resolve.py`'s docstring), so this is a sourcing-level defect, not something specific to Dataset C's own methodology.

## 2. Why "exclude forks" doesn't catch this

SEART GHS's own crawl exposes an `isFork` column, and the query used to build `github-search-raw/` already claims to exclude forks. Checked directly against the raw data: `isFork=true` appears **zero times** across the entire ~24,245-repo raw pool, yet every repo in every cluster found above is a confirmed real duplicate. GitHub's own fork bookkeeping only covers repos created via the "Fork" button/API — org transfers and independently-created shadow copies (a plain `git push` of existing history into a brand-new repo object) are invisible to it. `isFork` cannot be tightened or configured around this; it simply doesn't track the phenomenon.

The only signal that reliably catches all of these regardless of mechanism is content identity itself: **a shared git commit SHA is a cryptographic guarantee of identical history up to that commit**, not a heuristic. It can never produce a false-positive dedup — only a false negative, if the specific commit checked doesn't happen to be one the two repos actually share.

## 3. Two different mechanisms, matched to what's cheap and correct for each dataset's shape

- **Dataset C** looks at exactly one commit per repo — a fixed cutoff snapshot (`HUMAN_CORPUS_CUTOFF_DATE = 2020-12-31`). A repo either duplicates another's cutoff commit or it doesn't; a clean binary, checkable with one GitHub API call per repo. Implemented in `collection/dedupe_dataset_c_repos.py`.
- **Dataset A** has an *open* collection window (`agent_corpus_start_date: 2025-01-01` through whenever collection runs). No single date fully characterizes "are these duplicates" here, and two repos can *partially* overlap (share commits from a mirrored period, each also carrying unique commits from before/after). A complete fix needs full in-window commit-set comparison per repo — genuinely harder, deliberately **not attempted** (see §6). There is, however, a free, zero-cost partial signal already sitting in the raw data: `lastCommitSHA` (SEART's snapshot of each repo's current HEAD at crawl time). Implemented in `collection/repository_quality_control/agent_repository_counter.py`'s `_dedupe_by_last_commit_sha()`.
- **Dataset B**: no code change — `repo_resolve.py` already resolves Dataset B's repo pool from Dataset A's own (now partially-deduped) output, so it inherits Dataset A's fix automatically.

### Shared logic

Both mechanisms need the same "given a cluster of repos sharing an identity key, pick a survivor" decision and the same output CSV schema. Centralized in `collection/repo_dedup_utils.py`: `pick_cluster_survivor()` (highest stars, tie-break lowest `github_id`) and `find_duplicate_clusters()` (groups by an injected key function, applies the tie-break, shapes the output rows).

## 4. Empirical checks behind the design decisions

**`lastCommitSHA` was checked empirically before deciding to rely on it.** Grouping the raw `github-search-raw/*.csv.gz` rows by this column found only 74 of ~24,245 repos (0.3%) — e.g. it does correctly confirm `deepmind/pysc2`/`google-deepmind/pysc2` are still identical today. But it **misses** a real, already-confirmed duplicate pair in Dataset A's own collected data: `datahub-project/datahub`/`linkedin/datahub`. `linkedin/datahub`'s SEART record is frozen at a stale 2022 snapshot, while the live repo has apparently continued being mirrored since — so its `lastCommitSHA` no longer matches the live `datahub-project/datahub` HEAD, even though the underlying content overlap is real. This is exactly the open-window, partial-overlap problem being deferred (§6), not a bug in the simpler check — it's accepted as a known, documented gap rather than silently assumed away.

**The GitHub commits API's `until=` filter was checked against real data before being trusted.** It filters by **committer date**, not author date (which is what `dataset_c.py::find_cutoff_commit()` itself uses for the real extraction cutoff). Confirmed via a real test against `callstack/linaria`: the API returned a commit 3 weeks earlier than the author-date-correct one would be. This is safe to accept without further work: a SHA match is still proof of identical content regardless of which date field found it, so it can never cause a false-positive dedup — only a false negative if a cluster's shared history happens to diverge right around one member's rebase point.

**The real ~8,900-repo Dataset C sweep was run and independently verified**, not just unit-tested. `dedupe_dataset_c_repos.py` was run against the actual Dataset C candidate pool (`datasets/c/repos/*_repo.csv`, 8,907 repos across 4 languages): found 789 duplicate repos across 696 clusters. Cross-checked against every cluster already found by hand during the manual fixture review — the 5-repo OpenJDK cluster, `deepmind/pysc2`, `miserlou/zappa`, `pedroCabrera/PyFlow` — all reproduced exactly, same SHAs, same survivor picks. Full structural/consistency review afterward (no self-references, no repo listed as both survivor and removal, no repo appearing twice as a removal, `stars_removed` never exceeds `stars_kept`, `cluster_size` matches actual group sizes) found nothing wrong. As an independent cross-check: 789 removed + 696 survivors = 1,485 repos touched, 16.67% of the 8,907-repo pool — close to the 16.2% fixture-level duplicate rate the manual review found, despite being a different unit of measurement (repo count vs. fixture count).

Two of the 696 clusters mix `language` tags across their member rows (e.g. a java-tagged and a javascript-tagged repo sharing one cluster). Checked the raw candidate CSVs directly: every member of both clusters has a distinct `github_id` — these are genuinely separate GitHub repo objects (the "shadow copy" pattern this tool targets), not one repo double-counted across two per-language raw files. The `language` field on each output row simply reflects which raw SEART file that specific repo was crawled under (a live, current-crawl attribute), unrelated to the frozen cutoff-commit content — and it has no bearing on correctness, since `filter_known_duplicates()` matches purely by `repo_name`.

## 5. What gets persisted, and where

- **`datasets/c/repos/duplicate_repos.csv`** (+ `datasets/c/repos/dedupe_dataset_c_repos.checkpoint.json` for resumability) — Dataset C's list. Lives under `datasets/c/`, not `github-search-raw/`, because the result is specific to Dataset C's own `HUMAN_CORPUS_CUTOFF_DATE`; a different reference date produces a different list entirely, so it's not a property of the raw data itself. Consulted by `select_dataset_c_repos.py` at build time (pure CSV filter, no API calls at runtime) before `datasets/c/repos/{lang}_repo.csv` is written.
- **`github-search-raw/duplicate_repos_by_current_commit.csv`** — Dataset A's list, written by `write_last_commit_sha_duplicates_csv()` every time `agent_repository_counter.run()` runs. Lives alongside the raw SEART exports (not under `datasets/a/`) because current-HEAD collisions are a property of the raw candidate pool itself, not parameterized by any dataset-specific value — contrast with Dataset C's list above.

## 6. Explicitly out of scope as of §1–5 (partially closed by §8 below)

- **Full Dataset A/B dedup** (catching partial-overlap pairs like `datahub-project/datahub`/`linkedin/datahub`, whose current `lastCommitSHA` no longer matches): the *repo-level* version of this (full in-window commit-set comparison per repo, deciding up front which repo_names are "the same repo") remains not implemented — see §8 for why a commit-level approach turned out to be the better fix, not just an easier one.
- **Post-hoc dedup of already-collected `datasets/{a,b,c}/fixtures/*.csv`**: §8's commit-level mechanism *is* retroactive — see §8.2.

## 7. Status (superseded by §8 for Datasets A/B)

Closed for the scope described in §1–5. Implementation: `collection/repo_dedup_utils.py` (shared tie-break/clustering/CSV-write), `collection/dedupe_dataset_c_repos.py` (Dataset C mechanism, standalone CLI, rerun manually whenever `github-search-raw/` is refreshed), `agent_repository_counter.py`'s `_dedupe_by_last_commit_sha()`/`write_last_commit_sha_duplicates_csv()` (Dataset A mechanism, runs automatically every `discover-repos --dataset a`). Tests added for all of the above; full suite and ruff green. The real Dataset C sweep has been run once against the current `github-search-raw/` snapshot and its output verified against known clusters (§4) — due for a re-run only if/when the raw SEART data is refreshed.

## 8. Follow-up: commit-level dedup for Datasets A and B

Found while investigating an unrelated symptom: the Dataset A/B cross-check (`human_test_commit_filter.py`'s `dataset_a_missing` disagreement reason) showed extreme, exact-repeat concentration on a handful of repos -- three repo_names (`camunda-cloud/zeebe`, `camunda/zeebe`, `camunda/camunda`) each showing precisely the same disagreement count, same for a second cluster (`off-grid-ai/mobile`, `off-grid-ai/off-grid-ai-mobile`, `alichherawalla/off-grid-mobile-ai`). All three camunda entries share an identical `created_at` down to the second -- proof they're the same GitHub repo object, not three coincidentally-related projects.

Quantified across all of Dataset A's repo pool: repos sharing an exact `created_at` with at least one other repo -- a strong, cheap duplicate signal -- came to 3,912 of ~23,684 (16.5%), across 1,833 clusters. Confirmed via code reading, not guesswork: `agent_repository_counter.py::_dedupe_by_last_commit_sha()` is exactly as conservative as designed (§3) -- these clusters have already diverged (different current `lastCommitSHA`), so the repo-level pre-filter correctly, and unhelpfully, lets them through.

### 8.1 Why commit-level, not repo-level

§6's original framing was "full in-window commit-set comparison per repo" -- decide in advance which repo_names are the same repo. That's the wrong layer. A git commit SHA is a content hash (tree + parents + metadata): if the same `commit_sha` shows up under two different `repo_name`s in *already-collected* commit data, that's proof they share history up to that commit, with no historical analysis needed -- the "were these ever in sync" question is answered for free the moment the commits exist in hand. And it can never over-remove: a commit unique to one repo_name simply has no duplicate `commit_sha` anywhere else, so it's untouched regardless of how the cluster's repo-level metadata compares.

Implemented in `collection/dedupe_commits_by_sha.py`: for each `commit_sha` shared by more than one `repo_name`, keep exactly one repo_name's copy (`pick_cluster_survivor()`, same as §3 -- highest stars, tie-broken by earliest `created_at` this time, since commit-level rows are never joined against a repo's numeric `github_id`). Runs independently per dataset (`--dataset a` against `datasets/a/commits/`, `--dataset b` against `datasets/b/test-commits/` -- Dataset B does its own live commit scan of each repo rather than reusing Dataset A's classification, so deduping Dataset A's output alone would not have stopped Dataset B independently rediscovering the same commits under every duplicate name).

### 8.2 Applied retroactively, real numbers

Both already-collected datasets were backed up to `past-datasets/{a,b}-pre-commit-dedup-2026-07-30/` before anything was touched.

- **Dataset A** (`datasets/a/commits/`): 3,912 / 400,736 commit rows removed (~1.0%). Cascaded into the already-extracted downstream artifacts (`datasets/a/test-commits/*.csv`, `datasets/a/fixtures/*.csv`, `db/a.db`) by matching the exact `(commit_sha, repo_name)` pairs `dedupe_commits_by_sha.py` flagged -- 161 fixtures / 80 mock_usages removed from `db/a.db` across 11 repos. Re-verified: zero remaining cross-repo `commit_sha` collisions in `db/a.db`'s `fixtures` table.
- **Dataset B** (`datasets/b/test-commits/`): 2,609 / 411,841 commit rows removed (~0.6%), including exactly the `datahub-project/datahub`/`linkedin/datahub` pair named in §4 as the confirmed real example the repo-level check misses -- 1,600 of the 2,609. `extract-fixtures --dataset b` had not yet run at the time of this fix, so Dataset B's fixtures were generated correctly from the start; no cascade needed.

Neither the camunda nor off-grid-ai clusters that motivated this investigation were removed by this pass: none of their repo_name variants have *any* rows in Dataset A's own `datasets/a/commits/*.csv` (confirmed directly, not inferred), so there's no shared `commit_sha` for this mechanism to key on. Root cause not yet identified -- plausibly `discover-commits --dataset a` failing to clone/scan that specific (large) repository under any of its names, but unconfirmed. Documented as the new residual gap in `docs/reference/limitations.md`'s "Repository-Level Duplication" section.

### 8.3 Status

Closed for the commit-level mechanism described here for Dataset A. **For Dataset B, superseded by §9** — §8.2's "no cascade needed" was true only because `extract-fixtures --dataset b` hadn't run yet at the time; once it did, a second, distinct gap surfaced. `collection/repo_dedup_utils.py::pick_cluster_survivor()` gained an optional `tie_break_key` parameter (default unchanged, so §3's two existing callers are unaffected). Tests added; full suite and ruff green. `internal-docs/RUN_COMMANDS.md` updated to run `dedupe_commits_by_sha.py` between commit collection and fixture extraction for both datasets going forward.

## 9. Follow-up: `dedupe_commits_by_sha.py` doesn't protect Dataset B's fixtures at all

Found while investigating Dataset B's first real python `extract-fixtures` run (2026-07-30). §8 assumed that deduping `datasets/b/test-commits/*_human_test_commit.csv` before extraction would keep duplicate commits out of Dataset B's fixtures, the same way it does for Dataset A. That assumption is false, and turned out to have never been true.

**Root cause**: `extract-fixtures --dataset a` (`AgentCorpusCollector`) genuinely reads its commit list from `datasets/a/commits/*.csv` — dedupe that file, and the extractor simply never sees the removed rows again. `extract-fixtures --dataset b` (`HumanCorpusCollector`) does not work this way: it resolves its repo list from `datasets/b/repos/*.csv` and, for every repo, independently re-clones and re-scans that repo's entire commit history from scratch (`_process_human_repository` -> `_scan_and_extract`, its own `Tier1RepositoryScanner.scan_repo_commit_roles()` call — the *exact* same call `filter-test-commits` makes, duplicated work). It never opens `datasets/b/test-commits/*.csv` as an input, only writes to it as an audit trail. So no matter how clean that file is, extraction re-derives the same duplicate commits from raw git history under every repo_name variant, every time.

**Confirmed empirically**, not just by code reading, on the real first Dataset B python run: 20,989 of 57,272 extracted fixtures (36.6%) shared a `commit_sha` with a fixture under a different `repo_id`. Real example beyond camunda/off-grid-ai (§8): `phidatahq/phidata` and `agno-agi/agno` — identical `created_at` to the second (`2022-05-04T03:23:02`), confirmed same repo, both still independently cloned and scanned. Also found: `instructor-ai/instructor` / `567-labs/instructor` / `jxnl/instructor` (3-way rename chain), `ArcadeAI/arcade-ai` / `ArcadeAI/arcade-mcp`, `agentscope-ai/agentscope` / `modelscope/agentscope`.

### 9.1 Why not fixed the same way as §8

Restructuring `HumanCorpusCollector` to consume the deduped commit CSV directly (making this a one-time fix like Dataset A's, instead of a recurring cleanup) is possible in principle — `filter-test-commits`'s scan computes the exact same `commit_roles` data extraction redundantly recomputes, so extraction could skip straight to `AgentFixtureExtractor._extract_from_agent_commits()` with a pre-filtered commit list. Deliberately deferred, for two concrete reasons:

1. `agent_adoption_intensity` (per-repo agent-vs-human commit ratio) is currently a side effect of the full rescan (`compute_adoption_intensity()` needs `agent_commit_count`/`total_commit_count`, both derived from `commit_roles`). `filter-test-commits` sees this same data but currently only keeps an aggregate `commits_scanned` counter, not a per-repo breakdown — would need its output extended first.
2. It introduces a staleness window: extraction would reflect the repo's state as of when `filter-test-commits` ran, not extraction time, so a human test commit pushed to a repo in the gap between the two steps (realistically hours to days, since `filter-test-commits` alone took ~22h on the full run) would be silently missed until `filter-test-commits` is rerun.

Both are solvable, just not solved yet — tracked as a real follow-up, not abandoned.

### 9.2 What was built instead: a recurring post-extraction cascade

`collection/dedupe_fixtures_by_sha.py` — same duplicate-detection core as `dedupe_commits_by_sha.py` (`find_duplicate_commit_rows`/`pick_cluster_survivor`, reused unchanged; `dedupe_commit_csvs()` itself is reused directly, since it already filters by `(commit_sha, repo_name)` pairs regardless of how many rows in a file share one commit_sha — exactly the fixtures-CSV shape, multiple fixture rows per commit), but aimed at `datasets/b/fixtures/*.csv` and run *after* `extract-fixtures --dataset b` instead of before. Additionally cascades into `db/b.db`'s `fixtures`/`mock_usages` tables (fixtures already exist there by this point, unlike §8.2's timing) and re-syncs the denormalized aggregate columns `set_repo_analysed()`/`update_test_file_counts()` write once at persist time and don't keep live (`test_files.num_fixtures`/`total_fixture_loc`, `repositories.num_fixtures`/`num_mock_usages`) for every repo touched, so they don't go stale after the delete.

Unlike §8's mechanism, this is explicitly **not** a one-time fix — it must run after every `extract-fixtures --dataset b` invocation, including per-language re-runs, until (and unless) §9.1's restructuring happens. Idempotent: a clean state finds nothing to remove and leaves every file/table untouched, so re-running it costs nothing.

    python -m collection.dedupe_fixtures_by_sha --dataset b

`internal-docs/RUN_COMMANDS.md` updated: Dataset B's chain gained a 5th step running this after `extract-fixtures`, and its Notes section now explicitly states which of the two dedupe tools is one-time (A) versus recurring (B), so this doesn't get silently assumed-fixed again.

### 9.3 Status

Open by design — this is a standing recurring step, not a closed investigation, until §9.1's restructuring is done (not currently planned). Tests added (`tests/collection/test_dedupe_fixtures_by_sha.py`): cross-repo duplicate removed from both CSV and DB with aggregate-column re-sync verified, clean-state no-op case. Full suite and ruff green.
