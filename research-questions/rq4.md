# RQ4 -- Mocking

> How do agent-generated and human-written fixtures differ in mock usage -- coverage?

Generated: 2026-10-27 03:29:23 UTC

See [docs/research-questions.md](../docs/research-questions.md) for the full RQ4 definition.

## Per-dataset summary

### Dataset A (agent-authored) -- 85,136 fixtures, 21,033 mock usages

Mock prevalence: 8,367/85,136 fixtures (9.8%)

**Continuous metrics**

| Metric | n | median | mean | min | max | stdev |
|---|---|---|---|---|---|---|
| num_mocks | 85,136 | 0.00 | 0.25 | 0 | 45 | 1.20 |

**has_mock distribution**

| Value | Count | % |
|---|---|---|
| no_mock | 76,769 | 90.2% |
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
| java | 3,203 | 204 | 6.4% |
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

6,762/85,136 fixtures (7.94%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 3,243 | 277 | 8.54% | typescript=179, python=94, javascript=4 |
| javascript | 5,566 | 1,953 | 35.09% | typescript=1,536, python=383, java=34 |
| python | 24,290 | 1,545 | 6.36% | typescript=1,182, javascript=202, java=161 |
| typescript | 52,037 | 2,987 | 5.74% | javascript=2,131, python=814, java=42 |

### Dataset C (human-authored, pre-LLM) -- 82,610 fixtures, 10,325 mock usages

Mock prevalence: 4,980/82,610 fixtures (6.0%)

**Continuous metrics**

| Metric | n | median | mean | min | max | stdev |
|---|---|---|---|---|---|---|
| num_mocks | 82,610 | 0.00 | 0.12 | 0 | 31 | 0.70 |

**has_mock distribution**

| Value | Count | % |
|---|---|---|
| no_mock | 77,630 | 94.0% |
| has_mock | 4,980 | 6.0% |

**framework distribution**

| Value | Count | % |
|---|---|---|
| jest | 3,948 | 38.2% |
| sinon | 3,669 | 35.5% |
| unittest_mock | 1,870 | 18.1% |
| mockito | 307 | 3.0% |
| pytest_monkeypatch | 301 | 2.9% |
| pytest_mock | 230 | 2.2% |

**category distribution**

| Value | Count | % |
|---|---|---|
| mock | 4,622 | 44.8% |
| stub | 3,307 | 32.0% |
| spy | 2,057 | 19.9% |
| fake | 265 | 2.6% |
| dummy | 74 | 0.7% |

**Mock prevalence by language**

| Language | Fixtures | With >=1 mock | Rate |
|---|---|---|---|
| java | 3,203 | 119 | 3.7% |
| javascript | 5,950 | 424 | 7.1% |
| python | 24,036 | 1,235 | 5.1% |
| typescript | 49,421 | 3,202 | 6.5% |

**Framework distribution by language**

| Language | Framework | Count |
|---|---|---|
| java | mockito | 307 |
| javascript | jest | 551 |
| javascript | sinon | 447 |
| javascript | unittest_mock | 1 |
| python | unittest_mock | 1,865 |
| python | pytest_monkeypatch | 301 |
| python | pytest_mock | 230 |
| typescript | jest | 3,397 |
| typescript | sinon | 3,222 |
| typescript | unittest_mock | 4 |

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

7,483/82,610 fixtures (9.06%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 5,374 | 2,225 | 41.40% | typescript=1,104, python=1,003, javascript=118 |
| javascript | 6,847 | 2,536 | 37.04% | typescript=2,176, python=336, java=24 |
| python | 23,729 | 1,223 | 5.15% | typescript=980, javascript=223, java=20 |
| typescript | 46,660 | 1,499 | 3.21% | javascript=1,298, python=191, java=10 |

## A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)

**Continuous metrics (Mann-Whitney U, two-sided)** -- num_mocks has no per-language family (not one of the metrics the paper review named), so it renders Overall-only, shown at both the fixture-level (every fixture as an observation) and repo-level (one mean value per repo) basis. Effect size is Cliff's delta (thresholds: negligible <0.147, small <0.33, medium <0.474, else large).

### num_mocks

**Fixture-level**

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 85136 | 82610 | U=3381739226.5 | -0.038 | negligible | <.001 | -- |

**Repo-level** (one mean value per repo)

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 2167 | 2572 | U=2218845.5 | -0.204 | small | <.001 | -- |

### Mocking Coverage (paper table)

**Coverage** = % of repos with >=1 fixture containing a mock at all (population: every repo with >=1 fixture, of that language for the per-language rows). Purely descriptive -- no statistical test.

| Language | n_A | n_C | Coverage A (%) | Coverage C (%) |
|---|---|---|---|---|
| Overall | 2167 | 2572 | 44.0% | 25.5% |
| java | 175 | 375 | 26.3% | 13.6% |
| javascript | 211 | 592 | 22.3% | 21.6% |
| python | 856 | 1062 | 59.5% | 22.7% |
| typescript | 1198 | 749 | 34.3% | 34.8% |

### Mock Fixture Counts by Language

Raw count of fixtures with >=1 mock (`has_mock`), per language, each also shown as a percentage of that language's total fixture count. Unlike RQ3's setup/teardown counts table, `has_mock` is a clean binary with no 'other' category and no double-counting concern, so the denominator here is simply the total fixture count for that language/dataset -- no exclusions. Total is the dataset-wide sum across every language present, not just the four rows below. Purely descriptive -- no significance test (see the Coverage table above for the paper's actual, repo-level mocking comparison).

| Language | Mock A (n) | Mock A (%) | Mock C (n) | Mock C (%) |
|---|---|---|---|---|
| Overall | 8,367 | 9.8% | 4,980 | 6.0% |
| java | 204 | 6.4% | 119 | 3.7% |
| javascript | 223 | 3.7% | 424 | 7.1% |
| python | 5,341 | 22.2% | 1,235 | 5.1% |
| typescript | 2,599 | 5.0% | 3,202 | 6.5% |
