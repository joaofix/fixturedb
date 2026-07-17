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

## 6. Explicitly out of scope (documented, not forgotten)

- **Full Dataset A/B dedup** (catching partial-overlap pairs like `datahub-project/datahub`/`linkedin/datahub`, whose current `lastCommitSHA` no longer matches): not implemented. Would need full in-window commit-set comparison per repo, not a point-in-time fingerprint, plus a real design decision on how to handle *partial* overlap (drop the repo entirely and lose its unique commits, or dedup at the individual-commit level instead) — meaningfully harder and easy to get subtly wrong. Deliberately deferred rather than rushed. Revisit separately if/when Datasets A/B get re-collected.
- **Post-hoc dedup of already-collected `datasets/{a,b,c}/fixtures/*.csv`**: not implemented. Both mechanisms are forward-looking — they prevent the same problem on the *next* collection/re-collection of each dataset. Nothing here retroactively cleans the data already sitting in `datasets/a/`, `datasets/b/`, or `datasets/c/`; the 16.2%/17.9%/0.3% figures in §1 describe those existing collections as-is. A full re-collection (or a separate, explicitly-scoped patch of the existing fixture CSVs) is needed before the paper's actual analysis numbers can reflect the fix.

## 7. Status

Closed for the scope described above. Implementation: `collection/repo_dedup_utils.py` (shared tie-break/clustering/CSV-write), `collection/dedupe_dataset_c_repos.py` (Dataset C mechanism, standalone CLI, rerun manually whenever `github-search-raw/` is refreshed), `agent_repository_counter.py`'s `_dedupe_by_last_commit_sha()`/`write_last_commit_sha_duplicates_csv()` (Dataset A mechanism, runs automatically every `discover-repos --dataset a`). Tests added for all of the above; full suite and ruff green. The real Dataset C sweep has been run once against the current `github-search-raw/` snapshot and its output verified against known clusters (§4) — due for a re-run only if/when the raw SEART data is refreshed.
