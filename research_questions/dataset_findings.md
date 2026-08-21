# Dataset Findings (outside RQ1-3)

> Descriptive statistics about the datasets themselves -- collection process, composition -- that support paper claims but don't belong to any single RQ1-3 comparison. See this module's docstring for what each section below covers and why it lives here instead of its own script.

Generated: 2026-08-21 00:06:41 UTC

## Diff-Purity Gate (Dataset A)

Of Dataset A's agent commits that touched >=1 test file, how many were rejected for mixing test-file additions with edits/deletions, vs accepted as pure additions?

### Overall

2,264/3,776 repos had >=1 agent commit touching a test file.

| Touching tests | Accepted (pure addition) | Rejected (mixed diff) | Unclassified (extraction error) | Rejection rate |
|---|---|---|---|---|
| 134,086 | 65,838 | 66,615 | 1,633 | 49.68% |

### By language

**Rejection rate by repo language**

| Group | Repos | Touching tests | Rejected | Rejection rate |
|---|---|---|---|---|
| typescript | 1,899 | 78,419 | 39,878 | 50.85% |
| python | 1,187 | 41,193 | 19,971 | 48.48% |
| java | 323 | 7,456 | 3,557 | 47.71% |
| javascript | 367 | 7,018 | 3,209 | 45.73% |

### By agent adoption intensity

**Rejection rate by agent_adoption_intensity**

| Group | Repos | Touching tests | Rejected | Rejection rate |
|---|---|---|---|---|
| consistent | 583 | 61,202 | 31,149 | 50.90% |
| pervasive | 172 | 43,273 | 20,568 | 47.53% |
| limited | 804 | 25,541 | 12,873 | 50.40% |
| experimental | 705 | 4,070 | 2,025 | 49.75% |
| no_commits | 1,512 | 0 | 0 | -- |

### Per-repo distribution

**Per-repo rejection-rate distribution** (one rate per repo with >=1 test-touching commit -- each repo counted once, not weighted by its commit volume)

| N repos | Median | Mean | Stdev | Min | Max | Repos at 0% rejected | Repos at 100% rejected |
|---|---|---|---|---|---|---|---|
| 2,264 | 0.500 | 0.484 | 0.282 | 0.000 | 1.000 | 273 | 228 |

## Agent Adoption Intensity (Dataset A repo pool)

How Dataset A's whole repo pool splits across agent_adoption_intensity buckets -- bucket *membership*, not the rejection-rate-by-bucket view above. See this module's docstring for the known limitation (bucket label only, no underlying numeric ratio persisted).

### Overall

| Bucket | Repos | % of Dataset A repos |
|---|---|---|
| no_commits | 1,512 | 40.04% |
| experimental | 705 | 18.67% |
| limited | 804 | 21.29% |
| consistent | 583 | 15.44% |
| pervasive | 172 | 4.56% |

### Funnel and adoption intensity by language

Config -> No commits -> adoption tiers, per language -- the exact shape used for the paper's funnel/adoption table. See this function's docstring for exactly what Config/Total mean and how the percentages are computed.

| Language | Agent Configuration Present | No commits | Experimental | Limited | Consistent | Pervasive | Agent Active Total |
|---|---|---|---|---|---|---|---|
| Java | 323 | 150 (46.44%) | 72 (22.29%) | 63 (19.50%) | 32 (9.91%) | 6 (1.86%) | 173 |
| JavaScript | 367 | 191 (52.04%) | 43 (11.72%) | 69 (18.80%) | 52 (14.17%) | 12 (3.27%) | 176 |
| Python | 1,187 | 391 (32.94%) | 203 (17.10%) | 284 (23.93%) | 234 (19.71%) | 75 (6.32%) | 796 |
| TypeScript | 1,899 | 780 (41.07%) | 387 (20.38%) | 388 (20.43%) | 265 (13.95%) | 79 (4.16%) | 1,119 |
| **Total (All Languages)** | 3,776 | 1,512 (40.04%) | 705 (18.67%) | 804 (21.29%) | 583 (15.44%) | 172 (4.56%) | 2,264 |

## Dataset A: Commits and Repositories Summary

"All commits" counts non-merge commits (agent, human, and bot alike) since AGENT_CORPUS_START_DATE -- not full repository lifetime history -- among repos with an agent config file present; the same window and repo population as the rows below it, not an independent measure.

### Commits

| Commits | Java | JavaScript | Python | TypeScript | Total |
|---|---|---|---|---|---|
| All commits | 440,439 | 322,768 | 1,082,913 | 2,362,339 | 4,208,459 |
| Agent commits | 18,421 | 24,594 | 134,702 | 255,428 | 433,145 |
| Test commits | 7,456 | 7,018 | 41,193 | 78,419 | 134,086 |
| Mock commits | 68 | 82 | 1,244 | 997 | 2,391 |

### Repositories

| Repositories | Java | JavaScript | Python | TypeScript | Total |
|---|---|---|---|---|---|
| Candidate repos | 3,786 | 5,448 | 8,622 | 6,893 | 24,749 |
| With agent files or directories | 323 | 367 | 1,187 | 1,899 | 3,776 |
| With agent commits | 219 | 260 | 998 | 1,491 | 2,968 |
| With test commits | 173 | 176 | 796 | 1,119 | 2,264 |
| With mock commits | 26 | 25 | 281 | 242 | 574 |

## Dataset C: Repository Summary

| Repositories | Java | JavaScript | Python | TypeScript | Total |
|---|---|---|---|---|---|
| Candidate repos | 3,786 | 5,448 | 8,622 | 6,893 | 24,749 |
| Created within 2016-2020 | 1,398 | 1,916 | 2,721 | 2,107 | 8,142 |
| With any fixtures | 267 | 398 | 893 | 767 | 2,325 |
| With any mocks | 37 | 87 | 161 | 245 | 530 |

## Fixture Counts by Language

Total extracted fixtures per language, per dataset, counted by each fixture's own detected language -- not its repo's tagged language. This is a different grouping than the "Cross-language fixture leakage" table in rq1.md's per-dataset summaries, which groups by repo language instead, so a repo's language bucket there includes any fixtures written in a different language that were found inside it. The numbers here are the clean per-language totals -- a leaked fixture counts under the language it's actually written in, not its repo's tag.

| Dataset | Java | JavaScript | Python | TypeScript | Total |
|---|---|---|---|---|---|
| Dataset A (agent-authored) | 1,398 | 4,174 | 11,035 | 30,601 | 47,208 |
| Dataset C (human-authored, pre-LLM) | 1,398 | 4,174 | 11,035 | 30,601 | 47,208 |

## Dataset C: Sampling-Down Summary

Matched against Dataset a: 47,208/47,208 fixtures, 2,325 repos, seed=42.

A language whose "Repos sampled" hits its full available count took everything Dataset C had for it and still fell short of the target mix -- the shortfall was redistributed to the other languages, not discarded (see `_allocate_quotas_with_shortfall_reallocation()` in `dataset_sampler.py`).

| Language | Dataset C's own mix | Target (a's mix) | Sampled mix | Repos sampled | Fixtures sampled |
|---|---|---|---|---|---|
| Java | 29.0% | 3.0% | 3.0% | 267/608 | 1,398/55,610 |
| JavaScript | 21.5% | 8.8% | 8.8% | 557/822 | 4,174/41,318 |
| Python | 22.8% | 23.4% | 23.4% | 944/1,120 | 11,035/43,707 |
| TypeScript | 26.7% | 64.8% | 64.8% | 735/762 | 30,601/51,248 |

## JUnit 3 Fallback Detection (Java)

Side note, not a comparison: raw counts of `junit3_setup`/`junit3_teardown`, Java's only fixture_types identified without an annotation -- by method name plus a substring check on the enclosing class's superclass, which is not an exact-name or recursive type-resolution check. See `internal-docs/methodology-improvements/junit3-fallback-detection.md` for the full investigation (manual review of every instance found in both datasets at time of writing; all genuine, one only via substring coincidence). Tracked here so a re-collection that picks up a materially different count is easy to notice.

| Dataset | junit3_setup | junit3_teardown | Total |
|---|---|---|---|
| Dataset A | 0 | 0 | 0 |
| Dataset C | 34 | 11 | 45 |

## JS/TS Hook Fixture Complexity (Lizard `function_list` Selection)

Side note, not a comparison: exact re-check, not a sample, of whether each `before_each`/`after_each` fixture's recorded `cyclomatic_complexity` matches the true outer hook function's own complexity. Lizard orders `function_list` by parse-completion, not source position -- a nested closure (a `.catch(() => {})`, a mock callback) that finishes parsing before the outer hook does can land at `function_list[0]`, which `analyze_function_complexity()` unconditionally reads, silently displacing the outer hook's own complexity. Only fixtures whose `raw_source` contains a likely nested construct are re-checked ("Nested construct" column) -- that's the precondition for the issue at all. See `internal-docs/methodology-improvements/js-ts-hook-fixture-complexity.md` for the full investigation.

| Dataset | before_each/after_each | Nested construct | Re-checked | Mismatched | Mismatch rate |
|---|---|---|---|---|---|
| Dataset A | 28,623 | 2,811 | 2,330 | 517 | 22.19% |
| Dataset C | 24,798 | 2,959 | 2,244 | 226 | 10.07% |

## Mocha Bare `before()`/`after()` Detection (Regression Guard)

Side note, not a comparison, and not a live risk estimate -- count of `mocha_before`/`mocha_after` fixtures whose `raw_source` does not start with a bare `before(`/`after(` call, i.e. would indicate the `page.after()`/`browser.before()` false-positive shape investigated in `internal-docs/methodology-improvements/mocha-before-after-detection.md`. That investigation found this is structurally impossible given the detector's exact full-text-equality matching (confirmed 0/80 in a manual sample) -- this should always read 0; a nonzero value would mean the detector's matching logic regressed, not that a real edge case was found.

| Dataset | mocha_before/mocha_after | Non-bare-call shape |
|---|---|---|
| Dataset A | 1,115 | 0 |
| Dataset C | 5,772 | 0 |

## Aliased Mock Import Detection (Python)

Side note, not a comparison, and a lower bound, not a live risk estimate -- count of Python fixtures whose `raw_source` contains a direct class/function-level mock alias (`from unittest.mock import patch as p`, etc.), the one pattern that actually breaks mock detection. This DB-only check can only catch an alias declared *inside* a fixture body -- the far more common top-of-file form is invisible to it by construction (`raw_source` is function-body-only). See `internal-docs/methodology-improvements/aliased-mock-import-prevalence.md` for the real-file sampling that actually calibrates the true rate (found ~0% there too, via a different, network-dependent method this script deliberately doesn't replicate).

| Dataset | Python fixtures | Class/function-level alias in body |
|---|---|---|
| Dataset A | 11,035 | 0 |
| Dataset C | 11,035 | 0 |

## Mock-Category Fallback Rate

Side note, not a comparison: `category='mock'` (`mock_usages.category`) is both a real, specific test-double category (the literal word "mock" found in the fixture body) *and* the classifier's catch-all fallback when none of the 5 category terms (dummy/stub/spy/fake/mock) appear anywhere at all -- nothing in the schema distinguishes which happened for a given row. This reconstructs that split exactly (not an estimate -- see `internal-docs/methodology-improvements/mock-category-fallback-analysis.md`), in the shape the paper cites it: "X% of mock-type classifications result from a positive keyword match, Y% from the fallback."

### Positive match vs. fallback

| Dataset | category='mock' rows | Positive match | Fallback (no keyword) | Positive % / Fallback % |
|---|---|---|---|---|
| Dataset A | 7,955 | 6,327 | 1,628 | 79.5% / 20.5% |
| Dataset C | 2,594 | 1,864 | 730 | 71.9% / 28.1% |

### Positive matches split further: framework API name vs. naming-only

"Framework API name" -- the matched call site itself (`mock_usages.raw_snippet`) contains "mock" (`MagicMock(`, `mock.patch(`, `jest.mock(`, ...). "Naming-only" -- the matched call is keyword-free (`jest.fn()`, `vi.fn()`, bare `patch()`, `monkeypatch.setattr()`, ...) but some other identifier in the same fixture body supplied "mock".

| Dataset | n | Framework API name | Naming-only | Fallback |
|---|---|---|---|---|
| Dataset A | 7,955 | 4,736 (59.5%) | 1,591 (20.0%) | 1,628 (20.5%) |
| Dataset C | 2,594 | 1,445 (55.7%) | 419 (16.2%) | 730 (28.1%) |

### Per language

The pooled split above can hide a language-specific reversal --
checking per language matters here specifically because it does:

**Dataset A**

| Language | n | Framework API name | Naming-only | Fallback |
|---|---|---|---|---|
| java | 239 | 239 (100.0%) | 0 (0.0%) | 0 (0.0%) |
| javascript | 344 | 193 (56.1%) | 128 (37.2%) | 23 (6.7%) |
| python | 4,244 | 2,802 (66.0%) | 164 (3.9%) | 1,278 (30.1%) |
| typescript | 3,128 | 1,502 (48.0%) | 1,299 (41.5%) | 327 (10.5%) |

**Dataset C**

| Language | n | Framework API name | Naming-only | Fallback |
|---|---|---|---|---|
| java | 76 | 76 (100.0%) | 0 (0.0%) | 0 (0.0%) |
| javascript | 294 | 94 (32.0%) | 61 (20.7%) | 139 (47.3%) |
| python | 1,073 | 933 (87.0%) | 73 (6.8%) | 67 (6.2%) |
| typescript | 1,151 | 342 (29.7%) | 285 (24.8%) | 524 (45.5%) |
