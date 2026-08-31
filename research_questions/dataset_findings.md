# Dataset Findings (outside RQ1-3)

> Descriptive statistics about the datasets themselves -- collection process, composition -- that support paper claims but don't belong to any single RQ1-3 comparison. See this module's docstring for what each section below covers and why it lives here instead of its own script.

Generated: 2026-08-31 20:52:56 UTC

## Diff-Purity Gate (Dataset A)

Of Dataset A's agent commits that touched >=1 test file, how many were rejected for mixing test-file additions with edits/deletions, vs accepted as pure additions?

### Overall

2,691/4,393 repos had >=1 agent commit touching a test file.

| Touching tests | Accepted (pure addition) | Rejected (mixed diff) | Unclassified (extraction error) | Rejection rate |
|---|---|---|---|---|
| 203,145 | 96,917 | 103,685 | 2,543 | 51.04% |

### By language

**Rejection rate by repo language**

| Group | Repos | Touching tests | Rejected | Rejection rate |
|---|---|---|---|---|
| typescript | 2,222 | 113,896 | 59,819 | 52.52% |
| python | 1,388 | 69,179 | 34,655 | 50.09% |
| java | 370 | 10,650 | 4,841 | 45.46% |
| javascript | 413 | 9,420 | 4,370 | 46.39% |

### By agent adoption intensity

**Rejection rate by agent_adoption_intensity**

| Group | Repos | Touching tests | Rejected | Rejection rate |
|---|---|---|---|---|
| consistent | 693 | 98,530 | 50,518 | 51.27% |
| pervasive | 192 | 61,370 | 30,857 | 50.28% |
| limited | 950 | 37,782 | 19,558 | 51.77% |
| experimental | 856 | 5,463 | 2,752 | 50.38% |
| no_commits | 1,702 | 0 | 0 | -- |

### Per-repo distribution

**Per-repo rejection-rate distribution** (one rate per repo with >=1 test-touching commit -- each repo counted once, not weighted by its commit volume)

| N repos | Median | Mean | Stdev | Min | Max | Repos at 0% rejected | Repos at 100% rejected |
|---|---|---|---|---|---|---|---|
| 2,691 | 0.500 | 0.490 | 0.276 | 0.000 | 1.000 | 301 | 254 |

## Agent Adoption Intensity (Dataset A repo pool)

How Dataset A's whole repo pool splits across agent_adoption_intensity buckets -- bucket *membership*, not the rejection-rate-by-bucket view above. See this module's docstring for the known limitation (bucket label only, no underlying numeric ratio persisted).

### Overall

| Bucket | Repos | % of Dataset A repos |
|---|---|---|
| no_commits | 1,702 | 38.74% |
| experimental | 856 | 19.49% |
| limited | 950 | 21.63% |
| consistent | 693 | 15.78% |
| pervasive | 192 | 4.37% |

### Funnel and adoption intensity by language

Config -> No commits -> adoption tiers, per language -- the exact shape used for the paper's funnel/adoption table. See this function's docstring for exactly what Config/Total mean and how the percentages are computed.

| Language | Agent Configuration Present | No commits | Experimental | Limited | Consistent | Pervasive | Agent Active Total |
|---|---|---|---|---|---|---|---|
| Java | 370 | 164 (44.32%) | 85 (22.97%) | 70 (18.92%) | 44 (11.89%) | 7 (1.89%) | 206 |
| JavaScript | 413 | 210 (50.85%) | 47 (11.38%) | 83 (20.10%) | 58 (14.04%) | 15 (3.63%) | 203 |
| Python | 1,388 | 441 (31.77%) | 247 (17.80%) | 347 (25.00%) | 268 (19.31%) | 85 (6.12%) | 947 |
| TypeScript | 2,222 | 887 (39.92%) | 477 (21.47%) | 450 (20.25%) | 323 (14.54%) | 85 (3.83%) | 1,335 |
| **Total (All Languages)** | 4,393 | 1,702 (38.74%) | 856 (19.49%) | 950 (21.63%) | 693 (15.78%) | 192 (4.37%) | 2,691 |

## Dataset A: Commits and Repositories Summary

"All commits" counts non-merge commits (agent, human, and bot alike) since AGENT_CORPUS_START_DATE -- not full repository lifetime history -- among repos with an agent config file present; the same window and repo population as the rows below it, not an independent measure.

### Commits

| Commits | Java | JavaScript | Python | TypeScript | Total |
|---|---|---|---|---|---|
| All commits | 602,067 | 416,330 | 1,749,796 | 3,203,736 | 5,971,929 |
| Agent commits | 23,416 | 31,282 | 171,489 | 298,221 | 524,408 |
| Test commits | 10,650 | 9,420 | 69,179 | 113,896 | 203,145 |
| Mock commits | 100 | 99 | 2,202 | 1,336 | 3,737 |

### Repositories

| Repositories | Java | JavaScript | Python | TypeScript | Total |
|---|---|---|---|---|---|
| Candidate repos | 3,786 | 5,448 | 8,622 | 6,893 | 24,749 |
| With agent files or directories | 370 | 413 | 1,388 | 2,222 | 4,393 |
| With agent commits | 256 | 300 | 1,081 | 1,649 | 3,286 |
| With test commits | 206 | 203 | 947 | 1,335 | 2,691 |
| With mock commits | 32 | 31 | 356 | 304 | 723 |

## Dataset C: Repository Summary

| Repositories | Java | JavaScript | Python | TypeScript | Total |
|---|---|---|---|---|---|
| Candidate repos | 3,786 | 5,448 | 8,622 | 6,893 | 24,749 |
| Created within 2016-2020 | 1,398 | 1,916 | 2,734 | 2,107 | 8,155 |
| With any fixtures | 311 | 403 | 983 | 775 | 2,472 |
| With any mocks | 47 | 84 | 219 | 260 | 610 |

## Fixture Counts by Language

Total extracted fixtures per language, per dataset, counted by each fixture's own detected language -- not its repo's tagged language. This is a different grouping than the "Cross-language fixture leakage" table in rq1.md's per-dataset summaries, which groups by repo language instead, so a repo's language bucket there includes any fixtures written in a different language that were found inside it. The numbers here are the clean per-language totals -- a leaked fixture counts under the language it's actually written in, not its repo's tag.

| Dataset | Java | JavaScript | Python | TypeScript | Total |
|---|---|---|---|---|---|
| Dataset A (agent-authored) | 2,039 | 4,747 | 19,722 | 41,471 | 67,979 |
| Dataset C (human-authored, pre-LLM) | 2,039 | 4,747 | 19,722 | 41,471 | 67,979 |

## Dataset C: Sampling-Down Summary

Matched against Dataset a: 67,979/67,979 fixtures, 2,472 repos, seed=42.

A language whose "Repos sampled" hits its full available count took everything Dataset C had for it and still fell short of the target mix -- the shortfall was redistributed to the other languages, not discarded (see `_allocate_quotas_with_shortfall_reallocation()` in `dataset_sampler.py`).

| Language | Dataset C's own mix | Target (a's mix) | Sampled mix | Repos sampled | Fixtures sampled |
|---|---|---|---|---|---|
| Java | 31.3% | 3.0% | 3.0% | 315/629 | 2,039/60,404 |
| JavaScript | 20.2% | 7.0% | 7.0% | 563/800 | 4,747/39,029 |
| Python | 22.7% | 29.0% | 29.0% | 1,045/1,122 | 19,722/43,785 |
| TypeScript | 25.8% | 61.0% | 61.0% | 749/754 | 41,471/49,894 |

## JUnit 3 Fallback Detection (Java)

Side note, not a comparison: raw counts of `junit3_setup`/`junit3_teardown`, Java's only fixture_types identified without an annotation -- by method name plus a substring check on the enclosing class's superclass, which is not an exact-name or recursive type-resolution check. See `internal-docs/methodology-improvements/junit3-fallback-detection.md` for the full investigation (manual review of every instance found in both datasets at time of writing; all genuine, one only via substring coincidence). Tracked here so a re-collection that picks up a materially different count is easy to notice.

| Dataset | junit3_setup | junit3_teardown | Total |
|---|---|---|---|
| Dataset A | 1 | 0 | 1 |
| Dataset C | 32 | 20 | 52 |

## JS/TS Hook Fixture Complexity (Lizard `function_list` Selection)

Side note, not a comparison: exact re-check, not a sample, of whether each `before_each`/`after_each` fixture's recorded `cyclomatic_complexity` matches the true outer hook function's own complexity. Lizard orders `function_list` by parse-completion, not source position -- a nested closure (a `.catch(() => {})`, a mock callback) that finishes parsing before the outer hook does can land at `function_list[0]`, which `analyze_function_complexity()` unconditionally reads, silently displacing the outer hook's own complexity. Only fixtures whose `raw_source` contains a likely nested construct are re-checked ("Nested construct" column) -- that's the precondition for the issue at all. See `internal-docs/methodology-improvements/js-ts-hook-fixture-complexity.md` for the full investigation.

| Dataset | before_each/after_each | Nested construct | Re-checked | Mismatched | Mismatch rate |
|---|---|---|---|---|---|
| Dataset A | 38,555 | 3,857 | 3,185 | 675 | 21.19% |
| Dataset C | 32,835 | 3,838 | 2,912 | 246 | 8.45% |

## Mocha Bare `before()`/`after()` Detection (Regression Guard)

Side note, not a comparison, and not a live risk estimate -- count of `mocha_before`/`mocha_after` fixtures whose `raw_source` does not start with a bare `before(`/`after(` call, i.e. would indicate the `page.after()`/`browser.before()` false-positive shape investigated in `internal-docs/methodology-improvements/mocha-before-after-detection.md`. That investigation found this is structurally impossible given the detector's exact full-text-equality matching (confirmed 0/80 in a manual sample) -- this should always read 0; a nonzero value would mean the detector's matching logic regressed, not that a real edge case was found.

| Dataset | mocha_before/mocha_after | Non-bare-call shape |
|---|---|---|
| Dataset A | 1,303 | 0 |
| Dataset C | 7,835 | 0 |

## Aliased Mock Import Detection (Python)

Side note, not a comparison, and a lower bound, not a live risk estimate -- count of Python fixtures whose `raw_source` contains a direct class/function-level mock alias (`from unittest.mock import patch as p`, etc.), the one pattern that actually breaks mock detection. This DB-only check can only catch an alias declared *inside* a fixture body -- the far more common top-of-file form is invisible to it by construction (`raw_source` is function-body-only). See `internal-docs/methodology-improvements/aliased-mock-import-prevalence.md` for the real-file sampling that actually calibrates the true rate (found ~0% there too, via a different, network-dependent method this script deliberately doesn't replicate).

| Dataset | Python fixtures | Class/function-level alias in body |
|---|---|---|
| Dataset A | 19,722 | 0 |
| Dataset C | 19,722 | 0 |

## Mock-Category Fallback Rate

Side note, not a comparison: `category='mock'` (`mock_usages.category`) is both a real, specific test-double category (the literal word "mock" found in the fixture body) *and* the classifier's catch-all fallback when none of the 5 category terms (dummy/stub/spy/fake/mock) appear anywhere at all -- nothing in the schema distinguishes which happened for a given row. This reconstructs that split exactly (not an estimate -- see `internal-docs/methodology-improvements/mock-category-fallback-analysis.md`), in the shape the paper cites it: "X% of mock-type classifications result from a positive keyword match, Y% from the fallback."

### Positive match vs. fallback

| Dataset | category='mock' rows | Positive match | Fallback (no keyword) | Positive % / Fallback % |
|---|---|---|---|---|
| Dataset A | 13,122 | 10,880 | 2,242 | 82.9% / 17.1% |
| Dataset C | 3,640 | 2,735 | 905 | 75.1% / 24.9% |

### Positive matches split further: framework API name vs. naming-only

"Framework API name" -- the matched call site itself (`mock_usages.raw_snippet`) contains "mock" (`MagicMock(`, `mock.patch(`, `jest.mock(`, ...). "Naming-only" -- the matched call is keyword-free (`jest.fn()`, `vi.fn()`, bare `patch()`, `monkeypatch.setattr()`, ...) but some other identifier in the same fixture body supplied "mock".

| Dataset | n | Framework API name | Naming-only | Fallback |
|---|---|---|---|---|
| Dataset A | 13,122 | 8,655 (66.0%) | 2,225 (17.0%) | 2,242 (17.1%) |
| Dataset C | 3,640 | 2,151 (59.1%) | 584 (16.0%) | 905 (24.9%) |

### Per language

The pooled split above can hide a language-specific reversal --
checking per language matters here specifically because it does:

**Dataset A**

| Language | n | Framework API name | Naming-only | Fallback |
|---|---|---|---|---|
| java | 335 | 335 (100.0%) | 0 (0.0%) | 0 (0.0%) |
| javascript | 370 | 210 (56.8%) | 134 (36.2%) | 26 (7.0%) |
| python | 8,494 | 6,159 (72.5%) | 496 (5.8%) | 1,839 (21.7%) |
| typescript | 3,923 | 1,951 (49.7%) | 1,595 (40.7%) | 377 (9.6%) |

**Dataset C**

| Language | n | Framework API name | Naming-only | Fallback |
|---|---|---|---|---|
| java | 126 | 126 (100.0%) | 0 (0.0%) | 0 (0.0%) |
| javascript | 284 | 91 (32.0%) | 46 (16.2%) | 147 (51.8%) |
| python | 1,747 | 1,501 (85.9%) | 118 (6.8%) | 128 (7.3%) |
| typescript | 1,483 | 433 (29.2%) | 420 (28.3%) | 630 (42.5%) |
