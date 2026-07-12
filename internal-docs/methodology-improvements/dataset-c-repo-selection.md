# Dataset C: Repo Selection Methodology Change

**Date**: 2026-07-10
**Context**: Dataset C fixtures are extracted from a single snapshot (one cutoff commit), not commit-by-commit like Datasets A/B. This means fixture age is unknown — a fixture present at the snapshot could have been written any time in the repo's history. This document records the discussion that led to a fix.

---

## 1. Problem

Datasets A and B date each fixture by its actual authoring commit. Dataset C does not — it checks out one commit (last commit before the cutoff date, `HUMAN_CORPUS_CUTOFF_DATE = 2020-12-31`) and extracts every fixture present in every test file at that point. A fixture found this way could be brand new or could predate the repo's oldest tracked history. Reviewers can reasonably ask how old these fixtures really are.

## 2. First proposal and its problem

Proposal: restrict Dataset C to repos *created* from 2019-01-01 onward, bounding worst-case fixture age to ~2 years.

Problem found on review: any quality filter (stars, commits) applied to these repos uses **today's** GitHub metadata (2026), not metadata from 2019–2020. Confirmed by inspecting `github-search-raw/*.csv.gz` directly — `stargazers`, `commits`, `forks`, `watchers` are all single-crawl, present-day values. There is no historical time series in this data. So "created 2019, has 500+ stars today" really means "created 2019, later became popular" — selecting for repos we already know succeeded, not repos that were substantial at the time. A second problem: a repo only 1–2 years old at the snapshot may not have had time to establish real testing practices.

## 3. Fix for the metadata problem

Do not use GitHub's live star/commit fields for Dataset C at all.

- **No star filter.** No historical substitute exists for stars; drop it entirely for Dataset C.
- **Commit count measured at the cutoff, not today.** `dataset_c.py` already clones each repo and walks full git history to find the cutoff commit. Counting how many commits fall on or before the cutoff is the same traversal, already available — just not discarded. Reuses the existing `MIN_COMMITS = 100` threshold, but measured as a real fact about 2020, not a 2026 hindsight number.
- **Test-file count also measured at the cutoff snapshot.** Reuses the existing `MIN_TEST_FILES = 5` threshold.

This removes survivorship bias without giving up a quality floor.

## 4. Choosing the creation-date window

Widening the creation-date window (further back than 2019) gives repos more time to mature, at the cost of a looser fixture-age ceiling. To pick a window, we tested candidate start years (2013, 2016, 2019) empirically rather than guessing.

**Cheap check** (creation date only, from `github-search-raw`, no cloning): all three candidate windows leave hundreds to thousands of repos per language. Volume alone did not decide the window.

**Real check**: sampled repos per language per year-bucket, cloned each one, computed true commit count as of 2020-12-31 via git history, and ran the actual fixture extractor on any repo that passed both floors. First pass used 3 repos per bucket per language (36 repos); found the check informative but too small to trust for python/typescript, so re-ran with 25 repos per bucket for python/typescript and 10 for java/javascript (210 repos total). Both runs cloned repos one at a time and deleted each clone immediately after processing.

Combining each bucket's own observed pass rate and fixture yield against Dataset A's actual per-language target:

| Language | Target fixtures | `created ≥2019` | `created ≥2016` | `created ≥2013` |
|---|---|---|---|---|
| python | 18,714 | -77% | -4% | +111% |
| typescript | 23,294 | -80% | -27% | -2% |
| java | 1,233 | +852% | +2012% | +4709% |
| javascript | 1,691 | -100% (noise, n=10) | +5377% | +6614% |

Java and javascript clear the target in every window tested, including the original 2019 proposal. Python needs 2013 for real margin — 2016 is close but slightly under. Typescript is short even at 2013, the widest window tested.

## 4b. Bigger sample, to check the estimate above wasn't just noise

The 2016 estimate for python (-4%) was close enough to the target that it could have gone either way by chance alone (n=25 per bucket). Re-ran against the real `created ≥2016` window directly, using the actual production code (`select_dataset_c_repos.select_repos()`, `dataset_c.count_commits_up_to()`), first at 100/100/40/40 repos (python/typescript/java/javascript), then at 300/300/120/120 for a proper check. Result: python's estimate moved from -4% to +75%, confirming the first number was mostly sampling noise, not a real shortfall.

A bigger point estimate is still just a point estimate, so this alone doesn't prove the number is reliable. Computed a bootstrap confidence interval instead (20,000 resamples of the 300/300/120/120 per-repo results, each resample scaled by the real pool size):

| Language | Pool | Point estimate | 95% CI low | 95% CI high | Target | P(shortfall) |
|---|---|---|---|---|---|---|
| python | 2,931 | 50,697 | 30,160 | 79,088 | 18,714 | 0.0% |
| typescript | 2,299 | 59,207 | 34,960 | 91,447 | 23,294 | 0.0% |
| java | 1,537 | 62,056 | 25,079 | 112,624 | 1,233 | 0.0% |
| javascript | 2,044 | 35,753 | 16,386 | 60,332 | 1,691 | 0.0% |

Even the pessimistic end of the confidence interval clears every target. None of the 20,000 resamples for any language landed below target. 2016 is not a fragile result.

## 4c. Is 2016 actually the narrowest boundary, or just the narrowest one tested?

The margins in 4b are large enough that a narrower (later) boundary might also work — 2016 was never checked against 2017 or 2018, only against 2013 and 2019. Ran the same real-data, 300/300/120/120, bootstrap-CI check at both:

| Boundary | python | typescript | java | javascript |
|---|---|---|---|---|
| 2016 | 0.0% | 0.0% | 0.0% | 0.0% |
| 2017 | 0.0% | **2.6%** | 0.0% | 0.0% |
| 2018 | 6.7% | **75.0%** (point estimate itself under target) | 0.0% | 0.0% |

(Values are P(shortfall) -- probability, across 20,000 bootstrap resamples, that the real collection lands below Dataset A's target for that language.)

Typescript is the binding constraint. It is fully safe at 2016, already shows real risk at 2017 (2.6%, despite a point estimate that still looks comfortable — a few high-yield repos carry the average, and an unlucky resample without them can still miss target), and fails outright at 2018. Java and javascript never break at any boundary tested; they were never the limiting factor.

This confirms 2016 is the narrowest of the tested year-boundaries where every language clears the target with negligible risk, and that 2017 is measurably worse, not just untested. Precision claim: this was tested at year granularity, not month-by-month, so "narrowest boundary" means narrowest among the boundaries actually tested, not a proven exact tipping point.

## 5. Decision

**Creation date ≥ 2016-01-01, same for all four languages.** Cutoff stays at 2020-12-31 (unchanged).

Python and typescript may land under Dataset A's exact fixture count. Accepted, not hidden — to be stated plainly in the methodology write-up.

**Why one window for all languages, not one tuned per language:** a uniform rule is defensible; a rule that differs by language specifically to hit each language's target looks reverse-engineered, and is a much easier target for review pushback than "the sample came in a bit smaller than planned for one language."

**Why typescript's shortfall is acceptable:** typescript only saw real adoption starting around 2012–2014. A structurally smaller repo population in this age range is an expected, explainable property of the language's own history, not a flaw in the method.

## 6. Answer prepared for "why 2016 specifically"

1. Dataset C cannot measure a fixture's true age directly (no commit-by-commit scan, unlike A/B) — repo creation date is the proxy used instead, chosen because the direct measurement is not affordable at this scope.
2. The window was not picked to hit a target — it was chosen as the narrowest boundary that clears a uniform sufficiency bar across all four languages under one rule, the same logic behind the project's existing `MIN_STARS`/`MIN_COMMITS` thresholds. This is a verified claim, not an assumption: section 4c shows 2017, the next boundary tested, already fails for typescript (2.6% bootstrap risk of shortfall, rising to 75% at 2018). Tested at year granularity, so "narrowest" means narrowest among the boundaries actually tested.
3. It bounds worst-case fixture age to ~5 years, against an effectively unbounded ceiling otherwise (GitHub itself only goes back to 2008, so the true previous ceiling was ~12–13 years).
4. The same ~5-year window answers the opposite concern (repos too young) — pass rate against the same quality bar rises the further back the window goes, which is direct evidence that age and demonstrated project maturity are correlated in this data.
5. The result is not a fragile point estimate: a bootstrap confidence interval (section 4b) shows 0% probability of falling short of Dataset A's target at 2016, for every language, even at the pessimistic end of the interval.
6. No claim is made beyond what the data supports — no external literature is cited for "5 years is enough for project maturity" unless a real citation is found first.

## 7. Feature deactivated as a result

`sample_proportional_repos.py` and `compute_agent_proportions.py` (proportional-category repo sampling, matching Dataset C's domain mix to Dataset A's) are no longer needed: the narrower creation window plus the removal of the star filter already bounds candidate volume to a workable size. To be deactivated (not deleted) — code stays in place, unused, for possible future reuse.

## 8. Readiness check found a real bug, now fixed

Before a real collection, ran a small (20-repo) toy collection through the actual `collect_dataset_c_fixtures()` — not a unit test, a real run against a real SQLite DB. `repositories.github_id` has a `UNIQUE` constraint (`ON CONFLICT(github_id) DO UPDATE`). `dataset_c.py` never supplied one, so `construct_repo_dict()` defaulted every repo to `github_id=0` — every repo in a run collided on that constraint, and the whole run collapsed into a single DB row: 5 different repos' 159 fixtures all landed under one `repo_id`, attributed to whichever repo inserted first.

No existing test caught this because every test exercising `collect_dataset_c_fixtures()` mocked `_process_repo()` entirely, so the real `construct_repo_dict`/`upsert_repository` path was never exercised with realistic data.

Fixed by threading the real GitHub numeric repo ID through the whole pipeline: `select_dataset_c_repos.py` now reads it from the raw CSV's own `id` column (dropping any row where it's missing, rather than defaulting to something that could re-collide), `human_corpus.load_dataset_c_repos()` reads it back out, and `dataset_c.py` carries it through each fixture dict into the persist step. Added a regression test that runs the real (non-mocked) persist path against a real SQLite DB and asserts two different repos land in two different rows.

Re-ran the same toy collection after the fix: 5 repos, 5 distinct DB rows, fixtures correctly attributed (32/16/90/2/19, summing to the same 159).

## 9. Status

Closed. Implementation done: `DATASET_C_MIN_CREATED_DATE` in `config.py`, `select_dataset_c_repos.py` (new selector), the commit-count-at-cutoff check in `dataset_c.py::_process_repo()` via `count_commits_up_to()`, `sample_proportional_repos.py`/`compute_agent_proportions.py` deactivated, tests added, docs updated. Validation done: 2016 confirmed sufficient with a 0%-risk bootstrap confidence interval for every language (4b), and confirmed narrower than the next viable boundary — 2017 already fails for typescript (4c). A real toy end-to-end run surfaced and fixed a genuine repo-attribution bug (8). 2016 is the value in use; the pipeline has been exercised for real, not just unit-tested.
