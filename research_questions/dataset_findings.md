# Dataset Findings (outside RQ1-3)

> Descriptive statistics about the datasets themselves -- collection process, composition -- that support paper claims but don't belong to any single RQ1-3 comparison. See this module's docstring for what each section below covers and why it lives here instead of its own script.

Generated: 2026-09-08 01:16:33 UTC

## Diff-Purity Gate (Dataset A)

Of Dataset A's agent commits that touched >=1 test file, how many were rejected for mixing test-file additions with edits/deletions, vs accepted as pure additions?

### Overall

2,729/4,417 repos had >=1 agent commit touching a test file.

| Touching tests | Accepted (pure addition) | Rejected (mixed diff) | Unclassified (extraction error) | Rejection rate |
|---|---|---|---|---|
| 218,678 | 104,611 | 112,181 | 1,886 | 51.30% |

### By language

**Rejection rate by repo language**

| Group | Repos | Touching tests | Rejected | Rejection rate |
|---|---|---|---|---|
| typescript | 2,233 | 119,615 | 63,654 | 53.22% |
| python | 1,394 | 77,528 | 38,656 | 49.86% |
| java | 371 | 11,536 | 5,196 | 45.04% |
| javascript | 419 | 9,999 | 4,675 | 46.75% |

### By agent adoption intensity

**Rejection rate by agent_adoption_intensity**

| Group | Repos | Touching tests | Rejected | Rejection rate |
|---|---|---|---|---|
| consistent | 709 | 105,729 | 54,563 | 51.61% |
| pervasive | 201 | 67,921 | 34,346 | 50.57% |
| limited | 962 | 39,723 | 20,568 | 51.78% |
| experimental | 857 | 5,305 | 2,704 | 50.97% |
| no_commits | 1,688 | 0 | 0 | -- |

### Per-repo distribution

**Per-repo rejection-rate distribution** (one rate per repo with >=1 test-touching commit -- each repo counted once, not weighted by its commit volume)

| N repos | Median | Mean | Stdev | Min | Max | Repos at 0% rejected | Repos at 100% rejected |
|---|---|---|---|---|---|---|---|
| 2,729 | 0.500 | 0.493 | 0.273 | 0.000 | 1.000 | 292 | 248 |

## Agent Adoption Intensity (Dataset A repo pool)

How Dataset A's whole repo pool splits across agent_adoption_intensity buckets -- bucket *membership*, not the rejection-rate-by-bucket view above. See this module's docstring for the known limitation (bucket label only, no underlying numeric ratio persisted).

### Overall

| Bucket | Repos | % of Dataset A repos |
|---|---|---|
| no_commits | 1,688 | 38.22% |
| experimental | 857 | 19.40% |
| limited | 962 | 21.78% |
| consistent | 709 | 16.05% |
| pervasive | 201 | 4.55% |

### Funnel and adoption intensity by language

Config -> No commits -> adoption tiers, per language -- the exact shape used for the paper's funnel/adoption table. See this function's docstring for exactly what Config/Total mean and how the percentages are computed.

| Language | Agent Configuration Present | No commits | Experimental | Limited | Consistent | Pervasive | Agent Active Total |
|---|---|---|---|---|---|---|---|
| Java | 371 | 163 (43.94%) | 85 (22.91%) | 71 (19.14%) | 44 (11.86%) | 8 (2.16%) | 208 |
| JavaScript | 419 | 211 (50.36%) | 50 (11.93%) | 85 (20.29%) | 58 (13.84%) | 15 (3.58%) | 208 |
| Python | 1,394 | 439 (31.49%) | 245 (17.58%) | 345 (24.75%) | 274 (19.66%) | 91 (6.53%) | 955 |
| TypeScript | 2,233 | 875 (39.18%) | 477 (21.36%) | 461 (20.64%) | 333 (14.91%) | 87 (3.90%) | 1,358 |
| **Total (All Languages)** | 4,417 | 1,688 (38.22%) | 857 (19.40%) | 962 (21.78%) | 709 (16.05%) | 201 (4.55%) | 2,729 |

## Dataset A: Commits and Repositories Summary

"All commits" counts non-merge commits (agent, human, and bot alike) since AGENT_CORPUS_START_DATE -- not full repository lifetime history -- among repos with an agent config file present; the same window and repo population as the rows below it, not an independent measure.

### Commits

| Commits | Java | JavaScript | Python | TypeScript | Total |
|---|---|---|---|---|---|
| All commits | 624,143 | 441,308 | 1,817,374 | 3,266,876 | 6,149,701 |
| Agent commits | 24,989 | 32,713 | 190,178 | 307,686 | 555,566 |
| Test commits | 11,536 | 9,999 | 77,528 | 119,615 | 218,678 |
| Mock commits | 109 | 101 | 2,384 | 1,389 | 3,983 |

### Repositories

| Repositories | Java | JavaScript | Python | TypeScript | Total |
|---|---|---|---|---|---|
| Candidate repos | 3,786 | 5,448 | 8,622 | 6,893 | 24,749 |
| With agent files or directories | 371 | 419 | 1,394 | 2,233 | 4,417 |
| With agent commits | 258 | 303 | 1,089 | 1,661 | 3,311 |
| With test commits | 208 | 208 | 955 | 1,358 | 2,729 |
| With mock commits | 33 | 31 | 376 | 312 | 752 |

## Dataset C: Repository Summary

| Repositories | Java | JavaScript | Python | TypeScript | Total |
|---|---|---|---|---|---|
| Candidate repos | 3,786 | 5,448 | 8,622 | 6,893 | 24,749 |
| Created within 2016-2020 | 1,398 | 1,916 | 2,738 | 2,107 | 8,159 |
| With any fixtures | 317 | 406 | 980 | 791 | 2,494 |
| With any mocks | 37 | 73 | 219 | 265 | 594 |

## Fixture Counts by Language

Total extracted fixtures per language, per dataset, counted by each fixture's own detected language -- not its repo's tagged language. This is a different grouping than the "Cross-language fixture leakage" table in rq1.md's per-dataset summaries, which groups by repo language instead, so a repo's language bucket there includes any fixtures written in a different language that were found inside it. The numbers here are the clean per-language totals -- a leaked fixture counts under the language it's actually written in, not its repo's tag.

| Dataset | Java | JavaScript | Python | TypeScript | Total |
|---|---|---|---|---|---|
| Dataset A (agent-authored) | 2,261 | 4,858 | 20,684 | 42,820 | 70,623 |
| Dataset C (human-authored, pre-LLM) | 2,261 | 4,858 | 20,684 | 42,820 | 70,623 |

## Dataset C: Sampling-Down Summary

Matched against Dataset a: 70,623/70,623 fixtures, 2,494 repos, seed=42.

A language whose "Repos sampled" hits its full available count took everything Dataset C had for it and still fell short of the target mix -- the shortfall was redistributed to the other languages, not discarded (see `_allocate_quotas_with_shortfall_reallocation()` in `dataset_sampler.py`).

| Language | Dataset C's own mix | Target (a's mix) | Sampled mix | Repos sampled | Fixtures sampled |
|---|---|---|---|---|---|
| Java | 31.3% | 3.2% | 3.2% | 325/629 | 2,261/62,084 |
| JavaScript | 20.7% | 6.9% | 6.9% | 563/812 | 4,858/40,968 |
| Python | 22.1% | 29.3% | 29.3% | 1,040/1,125 | 20,684/43,852 |
| TypeScript | 25.9% | 60.6% | 60.6% | 758/766 | 42,820/51,203 |

## JUnit 3 Fallback Detection (Java)

Side note, not a comparison: raw counts of `junit3_setup`/`junit3_teardown`, Java's only fixture_types identified without an annotation -- by method name plus a substring check on the enclosing class's superclass, which is not an exact-name or recursive type-resolution check. See `internal-docs/methodology-improvements/junit3-fallback-detection.md` for the full investigation (manual review of every instance found in both datasets at time of writing; all genuine, one only via substring coincidence). Tracked here so a re-collection that picks up a materially different count is easy to notice.

| Dataset | junit3_setup | junit3_teardown | Total |
|---|---|---|---|
| Dataset A | 1 | 0 | 1 |
| Dataset C | 37 | 30 | 67 |

## JS/TS Hook Fixture Complexity (Lizard `function_list` Selection)

Side note, not a comparison: exact re-check, not a sample, of whether each `before_each`/`after_each` fixture's recorded `cyclomatic_complexity` matches the true outer hook function's own complexity. Lizard orders `function_list` by parse-completion, not source position -- a nested closure (a `.catch(() => {})`, a mock callback) that finishes parsing before the outer hook does can land at `function_list[0]`, which `analyze_function_complexity()` unconditionally reads, silently displacing the outer hook's own complexity. Only fixtures whose `raw_source` contains a likely nested construct are re-checked ("Nested construct" column) -- that's the precondition for the issue at all. See `internal-docs/methodology-improvements/js-ts-hook-fixture-complexity.md` for the full investigation.

| Dataset | before_each/after_each | Nested construct | Re-checked | Mismatched | Mismatch rate |
|---|---|---|---|---|---|
| Dataset A | 39,767 | 4,021 | 3,325 | 676 | 20.33% |
| Dataset C | 34,087 | 4,015 | 3,039 | 304 | 10.00% |

## Mocha Bare `before()`/`after()` Detection (Regression Guard)

Side note, not a comparison, and not a live risk estimate -- count of `mocha_before`/`mocha_after` fixtures whose `raw_source` does not start with a bare `before(`/`after(` call, i.e. would indicate the `page.after()`/`browser.before()` false-positive shape investigated in `internal-docs/methodology-improvements/mocha-before-after-detection.md`. That investigation found this is structurally impossible given the detector's exact full-text-equality matching (confirmed 0/80 in a manual sample) -- this should always read 0; a nonzero value would mean the detector's matching logic regressed, not that a real edge case was found.

| Dataset | mocha_before/mocha_after | Non-bare-call shape |
|---|---|---|
| Dataset A | 1,343 | 0 |
| Dataset C | 7,857 | 0 |

## Aliased Mock Import Detection (Python)

Side note, not a comparison, and a lower bound, not a live risk estimate -- count of Python fixtures whose `raw_source` contains a direct class/function-level mock alias (`from unittest.mock import patch as p`, etc.), the one pattern that actually breaks mock detection. This DB-only check can only catch an alias declared *inside* a fixture body -- the far more common top-of-file form is invisible to it by construction (`raw_source` is function-body-only). See `internal-docs/methodology-improvements/aliased-mock-import-prevalence.md` for the real-file sampling that actually calibrates the true rate (found ~0% there too, via a different, network-dependent method this script deliberately doesn't replicate).

| Dataset | Python fixtures | Class/function-level alias in body |
|---|---|---|
| Dataset A | 20,684 | 0 |
| Dataset C | 20,684 | 0 |

## Mock-Category Fallback Rate

Side note, not a comparison: `category='mock'` (`mock_usages.category`) is both a real, specific test-double category (the literal word "mock" found in the fixture body) *and* the classifier's catch-all fallback when none of the 5 category terms (dummy/stub/spy/fake/mock) appear anywhere at all -- nothing in the schema distinguishes which happened for a given row. This reconstructs that split exactly (not an estimate -- see `internal-docs/methodology-improvements/mock-category-fallback-analysis.md`), in the shape the paper cites it: "X% of mock-type classifications result from a positive keyword match, Y% from the fallback."

### Positive match vs. fallback

| Dataset | category='mock' rows | Positive match | Fallback (no keyword) | Positive % / Fallback % |
|---|---|---|---|---|
| Dataset A | 13,733 | 11,235 | 2,498 | 81.8% / 18.2% |
| Dataset C | 3,818 | 2,922 | 896 | 76.5% / 23.5% |

### Positive matches split further: framework API name vs. naming-only

"Framework API name" -- the matched call site itself (`mock_usages.raw_snippet`) contains "mock" (`MagicMock(`, `mock.patch(`, `jest.mock(`, ...). "Naming-only" -- the matched call is keyword-free (`jest.fn()`, `vi.fn()`, bare `patch()`, `monkeypatch.setattr()`, ...) but some other identifier in the same fixture body supplied "mock".

| Dataset | n | Framework API name | Naming-only | Fallback |
|---|---|---|---|---|
| Dataset A | 13,733 | 8,930 (65.0%) | 2,305 (16.8%) | 2,498 (18.2%) |
| Dataset C | 3,818 | 2,304 (60.3%) | 618 (16.2%) | 896 (23.5%) |

### Per language

The pooled split above can hide a language-specific reversal --
checking per language matters here specifically because it does:

**Dataset A**

| Language | n | Framework API name | Naming-only | Fallback |
|---|---|---|---|---|
| java | 386 | 386 (100.0%) | 0 (0.0%) | 0 (0.0%) |
| javascript | 374 | 213 (57.0%) | 135 (36.1%) | 26 (7.0%) |
| python | 9,014 | 6,368 (70.6%) | 562 (6.2%) | 2,084 (23.1%) |
| typescript | 3,959 | 1,963 (49.6%) | 1,608 (40.6%) | 388 (9.8%) |

**Dataset C**

| Language | n | Framework API name | Naming-only | Fallback |
|---|---|---|---|---|
| java | 123 | 123 (100.0%) | 0 (0.0%) | 0 (0.0%) |
| javascript | 277 | 90 (32.5%) | 68 (24.5%) | 119 (43.0%) |
| python | 1,943 | 1,663 (85.6%) | 155 (8.0%) | 125 (6.4%) |
| typescript | 1,475 | 428 (29.0%) | 395 (26.8%) | 652 (44.2%) |
