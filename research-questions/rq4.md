# RQ4 -- Mocking

> How do agent-generated and human-written fixtures differ in mock usage -- coverage?

Generated: 2026-10-07 13:35:51 UTC

See [docs/research-questions.md](../docs/research-questions.md) for the full RQ4 definition.

## Per-dataset summary

### Dataset A (agent-authored) -- 85,206 fixtures, 21,033 mock usages

Mock prevalence: 8,367/85,206 fixtures (9.8%)

**Continuous metrics**

| Metric | n | median | mean | min | max | stdev |
|---|---|---|---|---|---|---|
| num_mocks | 85,206 | 0.00 | 0.25 | 0 | 45 | 1.20 |

**has_mock distribution**

| Value | Count | % |
|---|---|---|
| no_mock | 76,839 | 90.2% |
| has_mock | 8,367 | 9.8% |

**framework distribution**

| Value | Count | % |
|---|---|---|
| unittest_mock | 6,638 | 31.6% |
| pytest_monkeypatch | 6,126 | 29.1% |
| vitest | 4,060 | 19.3% |
| jest | 3,189 | 15.2% |
| mockito | 487 | 2.3% |
| sinon | 279 | 1.3% |
| pytest_mock | 254 | 1.2% |

**category distribution**

| Value | Count | % |
|---|---|---|
| mock | 15,418 | 73.3% |
| stub | 1,942 | 9.2% |
| fake | 1,853 | 8.8% |
| spy | 1,702 | 8.1% |
| dummy | 118 | 0.6% |

**Mock prevalence by language**

| Language | Fixtures | With >=1 mock | Rate |
|---|---|---|---|
| java | 3,273 | 204 | 6.2% |
| javascript | 5,950 | 223 | 3.7% |
| python | 24,036 | 5,341 | 22.2% |
| typescript | 51,947 | 2,599 | 5.0% |

**Framework distribution by language**

| Language | Framework | Count |
|---|---|---|
| java | mockito | 487 |
| javascript | vitest | 315 |
| javascript | jest | 252 |
| javascript | sinon | 102 |
| python | unittest_mock | 6,637 |
| python | pytest_monkeypatch | 6,126 |
| python | pytest_mock | 254 |
| typescript | vitest | 3,745 |
| typescript | jest | 2,937 |
| typescript | sinon | 177 |
| typescript | unittest_mock | 1 |

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

6,765/85,206 fixtures (7.94%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 3,310 | 277 | 8.37% | typescript=179, python=94, javascript=4 |
| javascript | 5,566 | 1,953 | 35.09% | typescript=1,536, python=383, java=34 |
| python | 24,293 | 1,548 | 6.37% | typescript=1,182, javascript=202, java=164 |
| typescript | 52,037 | 2,987 | 5.74% | javascript=2,131, python=814, java=42 |

### Dataset C (human-authored, pre-LLM) -- 82,680 fixtures, 10,263 mock usages

Mock prevalence: 4,970/82,680 fixtures (6.0%)

**Continuous metrics**

| Metric | n | median | mean | min | max | stdev |
|---|---|---|---|---|---|---|
| num_mocks | 82,680 | 0.00 | 0.12 | 0 | 31 | 0.70 |

**has_mock distribution**

| Value | Count | % |
|---|---|---|
| no_mock | 77,710 | 94.0% |
| has_mock | 4,970 | 6.0% |

**framework distribution**

| Value | Count | % |
|---|---|---|
| jest | 3,918 | 38.2% |
| sinon | 3,656 | 35.6% |
| unittest_mock | 1,923 | 18.7% |
| pytest_monkeypatch | 288 | 2.8% |
| pytest_mock | 245 | 2.4% |
| mockito | 233 | 2.3% |

**category distribution**

| Value | Count | % |
|---|---|---|
| mock | 4,580 | 44.6% |
| stub | 3,291 | 32.1% |
| spy | 2,039 | 19.9% |
| fake | 276 | 2.7% |
| dummy | 77 | 0.8% |

**Mock prevalence by language**

| Language | Fixtures | With >=1 mock | Rate |
|---|---|---|---|
| java | 3,273 | 97 | 3.0% |
| javascript | 5,950 | 413 | 6.9% |
| python | 24,036 | 1,258 | 5.2% |
| typescript | 49,421 | 3,202 | 6.5% |

**Framework distribution by language**

| Language | Framework | Count |
|---|---|---|
| java | mockito | 233 |
| javascript | jest | 521 |
| javascript | sinon | 434 |
| javascript | unittest_mock | 1 |
| python | unittest_mock | 1,918 |
| python | pytest_monkeypatch | 288 |
| python | pytest_mock | 245 |
| typescript | jest | 3,397 |
| typescript | sinon | 3,222 |
| typescript | unittest_mock | 4 |

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

7,480/82,680 fixtures (9.05%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 5,453 | 2,217 | 40.66% | typescript=1,104, python=1,003, javascript=110 |
| javascript | 6,820 | 2,523 | 36.99% | typescript=2,176, python=336, java=11 |
| python | 23,728 | 1,222 | 5.15% | typescript=980, javascript=226, java=16 |
| typescript | 46,679 | 1,518 | 3.25% | javascript=1,317, python=191, java=10 |

## A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)

**Continuous metrics (Mann-Whitney U, two-sided)** -- num_mocks has no per-language family (not one of the metrics the paper review named), so it renders Overall-only, shown at both the fixture-level (every fixture as an observation) and repo-level (one mean value per repo) basis. Effect size is Cliff's delta (thresholds: negligible <0.147, small <0.33, medium <0.474, else large).

### num_mocks

**Fixture-level**

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 85206 | 82680 | U=3387077225.0 | -0.038 | negligible | <.001 | -- |

**Repo-level** (one mean value per repo)

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 2169 | 2549 | U=2216877.5 | -0.198 | small | <.001 | -- |

### Mocking Coverage (paper table)

**Coverage** = % of repos with >=1 fixture containing a mock at all (population: every repo with >=1 fixture, of that language for the per-language rows). Purely descriptive -- no statistical test.

| Language | n_A | n_C | Coverage A (%) | Coverage C (%) |
|---|---|---|---|---|
| Overall | 2169 | 2549 | 44.0% | 26.2% |
| java | 177 | 358 | 26.0% | 13.4% |
| javascript | 211 | 589 | 22.3% | 22.4% |
| python | 856 | 1061 | 59.5% | 23.5% |
| typescript | 1198 | 749 | 34.3% | 34.8% |

### Mock Fixture Counts by Language

Raw count of fixtures with >=1 mock (`has_mock`), per language, each also shown as a percentage of that language's total fixture count. Unlike RQ3's setup/teardown counts table, `has_mock` is a clean binary with no 'other' category and no double-counting concern, so the denominator here is simply the total fixture count for that language/dataset -- no exclusions. Total is the dataset-wide sum across every language present, not just the four rows below. Purely descriptive -- no significance test (see the Coverage table above for the paper's actual, repo-level mocking comparison).

| Language | Mock A (n) | Mock A (%) | Mock C (n) | Mock C (%) |
|---|---|---|---|---|
| Overall | 8,367 | 9.8% | 4,970 | 6.0% |
| java | 204 | 6.2% | 97 | 3.0% |
| javascript | 223 | 3.7% | 413 | 6.9% |
| python | 5,341 | 22.2% | 1,258 | 5.2% |
| typescript | 2,599 | 5.0% | 3,202 | 6.5% |
