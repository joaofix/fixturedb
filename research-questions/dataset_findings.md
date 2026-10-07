# Dataset Findings (outside RQ2-4)

> Descriptive statistics about the datasets themselves -- collection process, composition -- that support paper claims but don't belong to any single RQ2-4 comparison. See this module's docstring for what each section below covers and why it lives here instead of its own script.

Generated: 2026-10-07 14:03:49 UTC

## Diff-Purity Gate (Dataset A)

Of Dataset A's agent commits that touched >=1 test file, how many were rejected for mixing test-file additions with edits/deletions, vs accepted as pure additions?

### Overall

3,606/6,079 repos had >=1 agent commit touching a test file.

| Touching tests | Accepted (pure addition) | Rejected (mixed diff) | Unclassified (extraction error) | Rejection rate |
|---|---|---|---|---|
| 291,801 | 136,590 | 150,525 | 4,686 | 51.58% |

### By language

**Rejection rate by repo language**

| Group | Repos | Touching tests | Rejected | Rejection rate |
|---|---|---|---|---|
| typescript | 2,884 | 152,311 | 80,944 | 53.14% |
| python | 1,967 | 107,773 | 54,990 | 51.02% |
| java | 605 | 16,158 | 7,193 | 44.52% |
| javascript | 623 | 15,559 | 7,398 | 47.55% |

### By agent adoption intensity

**Rejection rate by agent_adoption_intensity**

| Group | Repos | Touching tests | Rejected | Rejection rate |
|---|---|---|---|---|
| consistent | 896 | 140,178 | 72,847 | 51.97% |
| pervasive | 284 | 95,223 | 48,235 | 50.65% |
| limited | 1,271 | 48,444 | 25,358 | 52.34% |
| experimental | 1,155 | 7,956 | 4,085 | 51.34% |
| no_commits | 2,473 | 0 | 0 | -- |

### Per-repo distribution

**Per-repo rejection-rate distribution** (one rate per repo with >=1 test-touching commit -- each repo counted once, not weighted by its commit volume)

| N repos | Median | Mean | Stdev | Min | Max | Repos at 0% rejected | Repos at 100% rejected |
|---|---|---|---|---|---|---|---|
| 3,606 | 0.500 | 0.485 | 0.275 | 0.000 | 1.000 | 412 | 325 |

## Agent Adoption Intensity (Dataset A repo pool)

How Dataset A's whole repo pool splits across agent_adoption_intensity buckets -- bucket *membership*, not the rejection-rate-by-bucket view above. See this module's docstring for the known limitation (bucket label only, no underlying numeric ratio persisted).

### Overall

| Bucket | Repos | % of Dataset A repos |
|---|---|---|
| no_commits | 2,473 | 40.68% |
| experimental | 1,155 | 19.00% |
| limited | 1,271 | 20.91% |
| consistent | 896 | 14.74% |
| pervasive | 284 | 4.67% |

### Funnel and adoption intensity by language

Config -> No commits -> adoption tiers, per language -- the exact shape used for the paper's funnel/adoption table. See this function's docstring for exactly what Config/Total mean and how the percentages are computed.

| Language | Agent Configuration Present | No commits | Experimental | Limited | Consistent | Pervasive | Agent Active Total |
|---|---|---|---|---|---|---|---|
| Java | 605 | 275 (45.45%) | 145 (23.97%) | 109 (18.02%) | 62 (10.25%) | 14 (2.31%) | 330 |
| JavaScript | 623 | 325 (52.17%) | 75 (12.04%) | 125 (20.06%) | 72 (11.56%) | 26 (4.17%) | 298 |
| Python | 1,967 | 697 (35.43%) | 339 (17.23%) | 443 (22.52%) | 360 (18.30%) | 128 (6.51%) | 1,270 |
| TypeScript | 2,884 | 1,176 (40.78%) | 596 (20.67%) | 594 (20.60%) | 402 (13.94%) | 116 (4.02%) | 1,708 |
| **Total (All Languages)** | 6,079 | 2,473 (40.68%) | 1,155 (19.00%) | 1,271 (20.91%) | 896 (14.74%) | 284 (4.67%) | 3,606 |

## Dataset A: Commits and Repositories Summary

"All commits" counts non-merge commits (agent, human, and bot alike) since AGENT_CORPUS_START_DATE -- not full repository lifetime history -- among repos with an agent config file present; the same window and repo population as the rows below it, not an independent measure.

### Commits

| Commits | Java | JavaScript | Python | TypeScript | Total |
|---|---|---|---|---|---|
| All commits | 828,688 | 565,069 | 2,474,059 | 4,320,238 | 8,188,054 |
| Agent commits | 36,168 | 48,424 | 268,629 | 437,249 | 790,470 |
| Test commits | 16,158 | 15,559 | 107,773 | 152,311 | 291,801 |
| Mock commits | 129 | 149 | 3,118 | 1,779 | 5,175 |

### Repositories

| Repositories | Java | JavaScript | Python | TypeScript | Total |
|---|---|---|---|---|---|
| Candidate repos | 3,786 | 5,448 | 8,622 | 6,893 | 24,749 |
| With agent files or directories | 605 | 623 | 1,967 | 2,884 | 6,079 |
| With agent commits | 427 | 449 | 1,516 | 2,154 | 4,546 |
| With test commits | 330 | 298 | 1,270 | 1,708 | 3,606 |
| With mock commits | 42 | 48 | 473 | 391 | 954 |

## Dataset C: Repository Summary

| Repositories | Java | JavaScript | Python | TypeScript | Total |
|---|---|---|---|---|---|
| Candidate repos | 3,786 | 5,448 | 8,622 | 6,893 | 24,749 |
| Created within 2016-2020 | 1,398 | 1,917 | 2,721 | 2,108 | 8,144 |
| With any fixtures | 352 | 420 | 993 | 784 | 2,549 |
| With any mocks | 58 | 95 | 236 | 279 | 668 |

## Fixture Counts by Language

Total extracted fixtures per language, per dataset, counted by each fixture's own detected language -- not its repo's tagged language. This is a different grouping than the "Cross-language fixture leakage" table in rq2.md's per-dataset summaries, which groups by repo language instead, so a repo's language bucket there includes any fixtures written in a different language that were found inside it. The numbers here are the clean per-language totals -- a leaked fixture counts under the language it's actually written in, not its repo's tag.

| Dataset | Java | JavaScript | Python | TypeScript | Total |
|---|---|---|---|---|---|
| Dataset A (agent-authored) | 3,273 | 5,950 | 24,036 | 51,947 | 85,206 |
| Dataset C (human-authored, pre-LLM) | 3,273 | 5,950 | 24,036 | 49,421 | 82,680 |

## Dataset C: Sampling-Down Summary

Matched against Dataset a: 82,680/85,206 fixtures, 2,549 repos, seed=42.

A language whose "Repos sampled" hits its full available count took everything Dataset C had for it and still fell short of the target mix -- the shortfall was redistributed to the other languages, not discarded (see `_allocate_quotas_with_shortfall_reallocation()` in `dataset_sampler.py`).

| Language | Dataset C's own mix | Target (a's mix) | Sampled mix | Repos sampled | Fixtures sampled |
|---|---|---|---|---|---|
| Java | 29.7% | 3.8% | 4.0% | 358/617 | 3,273/55,765 |
| JavaScript | 21.6% | 7.0% | 7.2% | 589/802 | 5,950/40,566 |
| Python | 22.5% | 28.2% | 29.1% | 1,061/1,105 | 24,036/42,274 |
| TypeScript | 26.3% | 61.0% | 59.8% | 749/749 (all) | 49,421/49,421 |

## JUnit 3 Fallback Detection (Java)

Side note, not a comparison: raw counts of `junit3_setup`/`junit3_teardown`, Java's only fixture_types identified without an annotation -- by method name plus a substring check on the enclosing class's superclass, which is not an exact-name or recursive type-resolution check. See `internal-docs/methodology-improvements/junit3-fallback-detection.md` for the full investigation (manual review of every instance found in both datasets at time of writing; all genuine, one only via substring coincidence). Tracked here so a re-collection that picks up a materially different count is easy to notice.

| Dataset | junit3_setup | junit3_teardown | Total |
|---|---|---|---|
| Dataset A | 1 | 0 | 1 |
| Dataset C | 55 | 38 | 93 |

## JS/TS Hook Fixture Complexity (Lizard `function_list` Selection)

Side note, not a comparison: exact re-check, not a sample, of whether each `before_each`/`after_each` fixture's recorded `cyclomatic_complexity` matches the true outer hook function's own complexity. Lizard orders `function_list` by parse-completion, not source position -- a nested closure (a `.catch(() => {})`, a mock callback) that finishes parsing before the outer hook does can land at `function_list[0]`, which `analyze_function_complexity()` unconditionally reads, silently displacing the outer hook's own complexity. Only fixtures whose `raw_source` contains a likely nested construct are re-checked ("Nested construct" column) -- that's the precondition for the issue at all. See `internal-docs/methodology-improvements/js-ts-hook-fixture-complexity.md` for the full investigation.

| Dataset | before_each/after_each | Nested construct | Re-checked | Mismatched | Mismatch rate |
|---|---|---|---|---|---|
| Dataset A | 48,040 | 5,383 | 4,406 | 963 | 21.86% |
| Dataset C | 39,286 | 4,715 | 3,550 | 332 | 9.35% |

## Mocha Bare `before()`/`after()` Detection (Regression Guard)

Side note, not a comparison, and not a live risk estimate -- count of `mocha_before`/`mocha_after` fixtures whose `raw_source` does not start with a bare `before(`/`after(` call, i.e. would indicate the `page.after()`/`browser.before()` false-positive shape investigated in `internal-docs/methodology-improvements/mocha-before-after-detection.md`. That investigation found this is structurally impossible given the detector's exact full-text-equality matching (confirmed 0/80 in a manual sample) -- this should always read 0; a nonzero value would mean the detector's matching logic regressed, not that a real edge case was found.

| Dataset | mocha_before/mocha_after | Non-bare-call shape |
|---|---|---|
| Dataset A | 1,802 | 2 |
| Dataset C | 9,380 | 0 |

## Aliased Mock Import Detection (Python)

Side note, not a comparison, and a lower bound, not a live risk estimate -- count of Python fixtures whose `raw_source` contains a direct class/function-level mock alias (`from unittest.mock import patch as p`, etc.), the one pattern that actually breaks mock detection. This DB-only check can only catch an alias declared *inside* a fixture body -- the far more common top-of-file form is invisible to it by construction (`raw_source` is function-body-only). See `internal-docs/methodology-improvements/aliased-mock-import-prevalence.md` for the real-file sampling that actually calibrates the true rate (found ~0% there too, via a different, network-dependent method this script deliberately doesn't replicate).

| Dataset | Python fixtures | Class/function-level alias in body |
|---|---|---|
| Dataset A | 24,036 | 0 |
| Dataset C | 24,036 | 0 |

## Mock-Category Fallback Rate

Side note, not a comparison: `category='mock'` (`mock_usages.category`) is both a real, specific test-double category (the literal word "mock" found in the fixture body) *and* the classifier's catch-all fallback when none of the 5 category terms (dummy/stub/spy/fake/mock) appear anywhere at all -- nothing in the schema distinguishes which happened for a given row. This reconstructs that split exactly (not an estimate -- see `internal-docs/methodology-improvements/mock-category-fallback-analysis.md`), in the shape the paper cites it: "X% of mock-type classifications result from a positive keyword match, Y% from the fallback."

### Positive match vs. fallback

| Dataset | category='mock' rows | Positive match | Fallback (no keyword) | Positive % / Fallback % |
|---|---|---|---|---|
| Dataset A | 15,418 | 11,005 | 4,413 | 71.4% / 28.6% |
| Dataset C | 4,580 | 3,445 | 1,135 | 75.2% / 24.8% |

### Positive matches split further: framework API name vs. naming-only

"Framework API name" -- the matched call site itself (`mock_usages.raw_snippet`) contains "mock" (`MagicMock(`, `mock.patch(`, `jest.mock(`, ...). "Naming-only" -- the matched call is keyword-free (`jest.fn()`, `vi.fn()`, bare `patch()`, `monkeypatch.setattr()`, ...) but some other identifier in the same fixture body supplied "mock".

| Dataset | n | Framework API name | Naming-only | Fallback |
|---|---|---|---|---|
| Dataset A | 15,418 | 8,517 (55.2%) | 2,488 (16.1%) | 4,413 (28.6%) |
| Dataset C | 4,580 | 2,718 (59.3%) | 727 (15.9%) | 1,135 (24.8%) |

### Per language

The pooled split above can hide a language-specific reversal --
checking per language matters here specifically because it does:

**Dataset A**

| Language | n | Framework API name | Naming-only | Fallback |
|---|---|---|---|---|
| java | 435 | 435 (100.0%) | 0 (0.0%) | 0 (0.0%) |
| javascript | 406 | 221 (54.4%) | 149 (36.7%) | 36 (8.9%) |
| python | 10,262 | 5,742 (56.0%) | 665 (6.5%) | 3,855 (37.6%) |
| typescript | 4,315 | 2,119 (49.1%) | 1,674 (38.8%) | 522 (12.1%) |

**Dataset C**

| Language | n | Framework API name | Naming-only | Fallback |
|---|---|---|---|---|
| java | 162 | 162 (100.0%) | 0 (0.0%) | 0 (0.0%) |
| javascript | 406 | 158 (38.9%) | 106 (26.1%) | 142 (35.0%) |
| python | 2,199 | 1,871 (85.1%) | 140 (6.4%) | 188 (8.5%) |
| typescript | 1,813 | 527 (29.1%) | 481 (26.5%) | 805 (44.4%) |
