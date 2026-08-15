# Dataset Findings (outside RQ1-3)

> Descriptive statistics about the datasets themselves -- collection process, composition -- that support paper claims but don't belong to any single RQ1-3 comparison. See this module's docstring for what each section below covers and why it lives here instead of its own script.

Generated: 2026-08-15 16:44:35 UTC

## Diff-Purity Gate (Dataset A)

Of Dataset A's agent commits that touched >=1 test file, how many were rejected for mixing test-file additions with edits/deletions, vs accepted as pure additions?

### Overall

1,709/3,224 repos had >=1 agent commit touching a test file.

| Touching tests | Accepted (pure addition) | Rejected (mixed diff) | Unclassified (extraction error) | Rejection rate |
|---|---|---|---|---|
| 109,862 | 53,569 | 54,701 | 1,592 | 49.79% |

### By language

**Rejection rate by repo language**

| Group | Repos | Touching tests | Rejected | Rejection rate |
|---|---|---|---|---|
| typescript | 1,599 | 55,744 | 28,896 | 51.84% |
| python | 1,101 | 42,953 | 21,001 | 48.89% |
| java | 245 | 6,686 | 2,816 | 42.12% |
| javascript | 279 | 4,479 | 1,988 | 44.38% |

### By agent adoption intensity

**Rejection rate by agent_adoption_intensity**

| Group | Repos | Touching tests | Rejected | Rejection rate |
|---|---|---|---|---|
| pervasive | 151 | 45,474 | 22,951 | 50.47% |
| consistent | 443 | 43,680 | 21,449 | 49.10% |
| limited | 593 | 17,778 | 8,843 | 49.74% |
| experimental | 522 | 2,930 | 1,458 | 49.76% |
| no_commits | 1,515 | 0 | 0 | -- |

### Per-repo distribution

**Per-repo rejection-rate distribution** (one rate per repo with >=1 test-touching commit -- each repo counted once, not weighted by its commit volume)

| N repos | Median | Mean | Stdev | Min | Max | Repos at 0% rejected | Repos at 100% rejected |
|---|---|---|---|---|---|---|---|
| 1,709 | 0.500 | 0.484 | 0.272 | 0.000 | 1.000 | 177 | 157 |

## Agent Adoption Intensity (Dataset A repo pool)

How Dataset A's whole repo pool splits across agent_adoption_intensity buckets -- bucket *membership*, not the rejection-rate-by-bucket view above. See this module's docstring for the known limitation (bucket label only, no underlying numeric ratio persisted).

### Overall

| Bucket | Repos | % of Dataset A repos |
|---|---|---|
| no_commits | 1,515 | 46.99% |
| experimental | 522 | 16.19% |
| limited | 593 | 18.39% |
| consistent | 443 | 13.74% |
| pervasive | 151 | 4.68% |

### Funnel and adoption intensity by language

Config -> No commits -> adoption tiers, per language -- the exact shape used for the paper's funnel/adoption table. See this function's docstring for exactly what Config/Total mean and how the percentages are computed.

| Language | Agent Configuration Present | No commits | Experimental | Limited | Consistent | Pervasive | Agent Active Total |
|---|---|---|---|---|---|---|---|
| Java | 245 | 115 (46.94%) | 54 (22.04%) | 47 (19.18%) | 23 (9.39%) | 6 (2.45%) | 130 |
| JavaScript | 279 | 131 (46.95%) | 38 (13.62%) | 61 (21.86%) | 40 (14.34%) | 9 (3.23%) | 148 |
| Python | 1,101 | 350 (31.79%) | 201 (18.26%) | 261 (23.71%) | 216 (19.62%) | 73 (6.63%) | 751 |
| TypeScript | 1,599 | 919 (57.47%) | 229 (14.32%) | 224 (14.01%) | 164 (10.26%) | 63 (3.94%) | 680 |
| **Total (All Languages)** | 3,224 | 1,515 (46.99%) | 522 (16.19%) | 593 (18.39%) | 443 (13.74%) | 151 (4.68%) | 1,709 |

## Dataset A: Commits and Repositories Summary

"All commits" counts non-merge commits (agent, human, and bot alike) since AGENT_CORPUS_START_DATE -- not full repository lifetime history -- among repos with an agent config file present; the same window and repo population as the rows below it, not an independent measure.

### Commits

| Commits | Java | JavaScript | Python | TypeScript | Total |
|---|---|---|---|---|---|
| All commits | 391,004 | 188,892 | 1,062,569 | 1,661,364 | 3,303,829 |
| Agent commits | 16,189 | 15,690 | 110,995 | 179,059 | 321,933 |
| Test commits | 6,686 | 4,479 | 42,953 | 55,744 | 109,862 |
| Mock commits | 68 | 48 | 1,302 | 600 | 2,018 |

### Repositories

| Repositories | Java | JavaScript | Python | TypeScript | Total |
|---|---|---|---|---|---|
| Candidate repos | 3,786 | 5,448 | 8,622 | 6,893 | 24,749 |
| With agent files or directories | 245 | 279 | 1,101 | 1,599 | 3,224 |
| With agent commits | 159 | 216 | 877 | 927 | 2,179 |
| With test commits | 130 | 148 | 751 | 680 | 1,709 |
| With mock commits | 25 | 21 | 272 | 148 | 466 |

## Dataset C: Repository Summary

| Repositories | Java | JavaScript | Python | TypeScript | Total |
|---|---|---|---|---|---|
| Candidate repos | 3,786 | 5,448 | 8,622 | 6,893 | 24,749 |
| Created within 2016-2020 | 1,544 | 2,068 | 3,003 | 2,355 | 8,970 |
| With any fixtures | 30 | 62 | 547 | 212 | 851 |
| With any mocks | 11 | 25 | 149 | 82 | 267 |

## Dataset C: Sampling-Down Summary

Matched against Dataset a: 39,377/39,088 fixtures, 851 repos, seed=42.

A language whose "Repos sampled" hits its full available count took everything Dataset C had for it and still fell short of the target mix -- the shortfall was redistributed to the other languages, not discarded (see `_allocate_quotas_with_shortfall_reallocation()` in `dataset_sampler.py`).

| Language | Dataset C's own mix | Target (a's mix) | Sampled mix | Repos sampled | Fixtures sampled |
|---|---|---|---|---|---|
| Java | 37.7% | 7.6% | 8.2% | 30/662 | 3,233/79,738 |
| JavaScript | 14.6% | 6.4% | 6.4% | 62/549 | 2,528/30,836 |
| Python | 18.4% | 43.8% | 43.5% | 547/1,087 | 17,111/38,962 |
| TypeScript | 29.3% | 42.2% | 41.9% | 212/946 | 16,505/61,848 |

## JUnit 3 Fallback Detection (Java)

Side note, not a comparison: raw counts of `junit3_setup`/`junit3_teardown`, Java's only fixture_types identified without an annotation -- by method name plus a substring check on the enclosing class's superclass, which is not an exact-name or recursive type-resolution check. See `internal-docs/methodology-improvements/junit3-fallback-detection.md` for the full investigation (manual review of every instance found in both datasets at time of writing; all genuine, one only via substring coincidence). Tracked here so a re-collection that picks up a materially different count is easy to notice.

| Dataset | junit3_setup | junit3_teardown | Total |
|---|---|---|---|
| Dataset A | 1 | 0 | 1 |
| Dataset C (sampled) | 12 | 2 | 14 |
| Dataset C (full, pre-sampling) | 1,218 | 653 | 1,871 |

## JS/TS Hook Fixture Complexity (Lizard `function_list` Selection)

Side note, not a comparison: exact re-check, not a sample, of whether each `before_each`/`after_each` fixture's recorded `cyclomatic_complexity` matches the true outer hook function's own complexity. Lizard orders `function_list` by parse-completion, not source position -- a nested closure (a `.catch(() => {})`, a mock callback) that finishes parsing before the outer hook does can land at `function_list[0]`, which `analyze_function_complexity()` unconditionally reads, silently displacing the outer hook's own complexity. Only fixtures whose `raw_source` contains a likely nested construct are re-checked ("Nested construct" column) -- that's the precondition for the issue at all. See `internal-docs/methodology-improvements/js-ts-hook-fixture-complexity.md` for the full investigation.

| Dataset | before_each/after_each | Nested construct | Re-checked | Mismatched | Mismatch rate |
|---|---|---|---|---|---|
| Dataset A | 21,703 | 2,031 | 1,669 | 349 | 20.91% |
| Dataset C (sampled) | 12,327 | 1,511 | 884 | 68 | 7.69% |
| Dataset C (full, pre-sampling) | 67,947 | 8,135 | 6,503 | 797 | 12.26% |

## Mocha Bare `before()`/`after()` Detection (Regression Guard)

Side note, not a comparison, and not a live risk estimate -- count of `mocha_before`/`mocha_after` fixtures whose `raw_source` does not start with a bare `before(`/`after(` call, i.e. would indicate the `page.after()`/`browser.before()` false-positive shape investigated in `internal-docs/methodology-improvements/mocha-before-after-detection.md`. That investigation found this is structurally impossible given the detector's exact full-text-equality matching (confirmed 0/80 in a manual sample) -- this should always read 0; a nonzero value would mean the detector's matching logic regressed, not that a real edge case was found.

| Dataset | mocha_before/mocha_after | Non-bare-call shape |
|---|---|---|
| Dataset A | 791 | 0 |
| Dataset C (sampled) | 4,415 | 0 |

## Aliased Mock Import Detection (Python)

Side note, not a comparison, and a lower bound, not a live risk estimate -- count of Python fixtures whose `raw_source` contains a direct class/function-level mock alias (`from unittest.mock import patch as p`, etc.), the one pattern that actually breaks mock detection. This DB-only check can only catch an alias declared *inside* a fixture body -- the far more common top-of-file form is invisible to it by construction (`raw_source` is function-body-only). See `internal-docs/methodology-improvements/aliased-mock-import-prevalence.md` for the real-file sampling that actually calibrates the true rate (found ~0% there too, via a different, network-dependent method this script deliberately doesn't replicate).

| Dataset | Python fixtures | Class/function-level alias in body |
|---|---|---|
| Dataset A | 11,712 | 0 |
| Dataset C (sampled) | 16,745 | 0 |

## Mock-Category Fallback Rate

Side note, not a comparison: `category='mock'` (`mock_usages.category`) is both a real, specific test-double category (the literal word "mock" found in the fixture body) *and* the classifier's catch-all fallback when none of the 5 category terms (dummy/stub/spy/fake/mock) appear anywhere at all -- nothing in the schema distinguishes which happened for a given row. This reconstructs that split exactly (not an estimate -- see `internal-docs/methodology-improvements/mock-category-fallback-analysis.md`), in the shape the paper cites it: "X% of mock-type classifications result from a positive keyword match, Y% from the fallback."

### Positive match vs. fallback

| Dataset | category='mock' rows | Positive match | Fallback (no keyword) | Positive % / Fallback % |
|---|---|---|---|---|
| Dataset A | 10,963 | 7,898 | 3,065 | 72.0% / 28.0% |
| Dataset C (sampled) | 3,369 | 2,782 | 587 | 82.6% / 17.4% |

### Positive matches split further: framework API name vs. naming-only

"Framework API name" -- the matched call site itself (`mock_usages.raw_snippet`) contains "mock" (`MagicMock(`, `mock.patch(`, `jest.mock(`, ...). "Naming-only" -- the matched call is keyword-free (`jest.fn()`, `vi.fn()`, bare `patch()`, `monkeypatch.setattr()`, ...) but some other identifier in the same fixture body supplied "mock".

| Dataset | n | Framework API name | Naming-only | Fallback |
|---|---|---|---|---|
| Dataset A | 10,963 | 6,593 (60.1%) | 1,305 (11.9%) | 3,065 (28.0%) |
| Dataset C (sampled) | 3,369 | 2,335 (69.3%) | 447 (13.3%) | 587 (17.4%) |

### Per language

The pooled split above can hide a language-specific reversal --
checking per language matters here specifically because it does:

**Dataset A**

| Language | n | Framework API name | Naming-only | Fallback |
|---|---|---|---|---|
| java | 245 | 245 (100.0%) | 0 (0.0%) | 0 (0.0%) |
| javascript | 181 | 95 (52.5%) | 68 (37.6%) | 18 (9.9%) |
| python | 8,495 | 5,223 (61.5%) | 402 (4.7%) | 2,870 (33.8%) |
| typescript | 2,042 | 1,030 (50.4%) | 835 (40.9%) | 177 (8.7%) |

**Dataset C (sampled)**

| Language | n | Framework API name | Naming-only | Fallback |
|---|---|---|---|---|
| java | 125 | 125 (100.0%) | 0 (0.0%) | 0 (0.0%) |
| javascript | 768 | 401 (52.2%) | 115 (15.0%) | 252 (32.8%) |
| python | 2,023 | 1,687 (83.4%) | 186 (9.2%) | 150 (7.4%) |
| typescript | 453 | 122 (26.9%) | 146 (32.2%) | 185 (40.8%) |
