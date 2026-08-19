# Dataset Findings (outside RQ1-3)

> Descriptive statistics about the datasets themselves -- collection process, composition -- that support paper claims but don't belong to any single RQ1-3 comparison. See this module's docstring for what each section below covers and why it lives here instead of its own script.

Generated: 2026-08-19 15:57:00 UTC

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
| With any fixtures | 560 | 551 | 1,048 | 846 | 3,005 |
| With any mocks | 168 | 171 | 286 | 323 | 948 |

## Dataset C: Sampling-Down Summary

_Not available -- run `python -m collection sample-c-repos --match-dataset a` first._

## JUnit 3 Fallback Detection (Java)

Side note, not a comparison: raw counts of `junit3_setup`/`junit3_teardown`, Java's only fixture_types identified without an annotation -- by method name plus a substring check on the enclosing class's superclass, which is not an exact-name or recursive type-resolution check. See `internal-docs/methodology-improvements/junit3-fallback-detection.md` for the full investigation (manual review of every instance found in both datasets at time of writing; all genuine, one only via substring coincidence). Tracked here so a re-collection that picks up a materially different count is easy to notice.

| Dataset | junit3_setup | junit3_teardown | Total |
|---|---|---|---|
| Dataset A | 0 | 0 | 0 |
| Dataset C | 1,189 | 638 | 1,827 |

## JS/TS Hook Fixture Complexity (Lizard `function_list` Selection)

Side note, not a comparison: exact re-check, not a sample, of whether each `before_each`/`after_each` fixture's recorded `cyclomatic_complexity` matches the true outer hook function's own complexity. Lizard orders `function_list` by parse-completion, not source position -- a nested closure (a `.catch(() => {})`, a mock callback) that finishes parsing before the outer hook does can land at `function_list[0]`, which `analyze_function_complexity()` unconditionally reads, silently displacing the outer hook's own complexity. Only fixtures whose `raw_source` contains a likely nested construct are re-checked ("Nested construct" column) -- that's the precondition for the issue at all. See `internal-docs/methodology-improvements/js-ts-hook-fixture-complexity.md` for the full investigation.

| Dataset | before_each/after_each | Nested construct | Re-checked | Mismatched | Mismatch rate |
|---|---|---|---|---|---|
| Dataset A | 28,623 | 2,811 | 2,330 | 517 | 22.19% |
| Dataset C | 65,621 | 8,098 | 6,486 | 828 | 12.77% |

## Mocha Bare `before()`/`after()` Detection (Regression Guard)

Side note, not a comparison, and not a live risk estimate -- count of `mocha_before`/`mocha_after` fixtures whose `raw_source` does not start with a bare `before(`/`after(` call, i.e. would indicate the `page.after()`/`browser.before()` false-positive shape investigated in `internal-docs/methodology-improvements/mocha-before-after-detection.md`. That investigation found this is structurally impossible given the detector's exact full-text-equality matching (confirmed 0/80 in a manual sample) -- this should always read 0; a nonzero value would mean the detector's matching logic regressed, not that a real edge case was found.

| Dataset | mocha_before/mocha_after | Non-bare-call shape |
|---|---|---|
| Dataset A | 1,115 | 0 |
| Dataset C | 14,994 | 0 |

## Aliased Mock Import Detection (Python)

Side note, not a comparison, and a lower bound, not a live risk estimate -- count of Python fixtures whose `raw_source` contains a direct class/function-level mock alias (`from unittest.mock import patch as p`, etc.), the one pattern that actually breaks mock detection. This DB-only check can only catch an alias declared *inside* a fixture body -- the far more common top-of-file form is invisible to it by construction (`raw_source` is function-body-only). See `internal-docs/methodology-improvements/aliased-mock-import-prevalence.md` for the real-file sampling that actually calibrates the true rate (found ~0% there too, via a different, network-dependent method this script deliberately doesn't replicate).

| Dataset | Python fixtures | Class/function-level alias in body |
|---|---|---|
| Dataset A | 11,035 | 0 |
| Dataset C | 43,707 | 0 |

## Mock-Category Fallback Rate

Side note, not a comparison: `category='mock'` (`mock_usages.category`) is both a real, specific test-double category (the literal word "mock" found in the fixture body) *and* the classifier's catch-all fallback when none of the 5 category terms (dummy/stub/spy/fake/mock) appear anywhere at all -- nothing in the schema distinguishes which happened for a given row. This reconstructs that split exactly (not an estimate -- see `internal-docs/methodology-improvements/mock-category-fallback-analysis.md`), in the shape the paper cites it: "X% of mock-type classifications result from a positive keyword match, Y% from the fallback."

### Positive match vs. fallback

| Dataset | category='mock' rows | Positive match | Fallback (no keyword) | Positive % / Fallback % |
|---|---|---|---|---|
| Dataset A | 7,955 | 6,327 | 1,628 | 79.5% / 20.5% |
| Dataset C | 11,979 | 9,580 | 2,399 | 80.0% / 20.0% |

### Positive matches split further: framework API name vs. naming-only

"Framework API name" -- the matched call site itself (`mock_usages.raw_snippet`) contains "mock" (`MagicMock(`, `mock.patch(`, `jest.mock(`, ...). "Naming-only" -- the matched call is keyword-free (`jest.fn()`, `vi.fn()`, bare `patch()`, `monkeypatch.setattr()`, ...) but some other identifier in the same fixture body supplied "mock".

| Dataset | n | Framework API name | Naming-only | Fallback |
|---|---|---|---|---|
| Dataset A | 7,955 | 4,736 (59.5%) | 1,591 (20.0%) | 1,628 (20.5%) |
| Dataset C | 11,979 | 8,202 (68.5%) | 1,378 (11.5%) | 2,399 (20.0%) |

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
| java | 3,225 | 3,225 (100.0%) | 0 (0.0%) | 0 (0.0%) |
| javascript | 2,859 | 970 (33.9%) | 609 (21.3%) | 1,280 (44.8%) |
| python | 4,055 | 3,477 (85.7%) | 286 (7.1%) | 292 (7.2%) |
| typescript | 1,840 | 530 (28.8%) | 483 (26.2%) | 827 (44.9%) |
