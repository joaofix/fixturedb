# RQ4 -- Mocking

> How do agent-generated and human-written fixtures differ in mock usage -- coverage?

Generated: 2026-10-03 21:15:07 UTC

See [docs/research-questions.md](../docs/research-questions.md) for the full RQ4 definition.

## Per-dataset summary

### Dataset A (agent-authored) -- 70,623 fixtures, 17,725 mock usages

Mock prevalence: 7,032/70,623 fixtures (10.0%)

**Continuous metrics**

| Metric | n | median | mean | min | max | stdev |
|---|---|---|---|---|---|---|
| num_mocks | 70,623 | 0.00 | 0.25 | 0 | 45 | 1.22 |

**has_mock distribution**

| Value | Count | % |
|---|---|---|
| no_mock | 63,591 | 90.0% |
| has_mock | 7,032 | 10.0% |

**framework distribution**

| Value | Count | % |
|---|---|---|
| unittest_mock | 7,368 | 41.6% |
| vitest | 3,475 | 19.6% |
| pytest_monkeypatch | 3,474 | 19.6% |
| jest | 2,611 | 14.7% |
| mockito | 441 | 2.5% |
| sinon | 179 | 1.0% |
| pytest_mock | 177 | 1.0% |

**category distribution**

| Value | Count | % |
|---|---|---|
| mock | 13,733 | 77.5% |
| stub | 1,573 | 8.9% |
| fake | 1,197 | 6.8% |
| spy | 1,119 | 6.3% |
| dummy | 103 | 0.6% |

**Mock prevalence by language**

| Language | Fixtures | With >=1 mock | Rate |
|---|---|---|---|
| java | 2,261 | 180 | 8.0% |
| javascript | 4,858 | 189 | 3.9% |
| python | 20,684 | 4,630 | 22.4% |
| typescript | 42,820 | 2,033 | 4.7% |

**Framework distribution by language**

| Language | Framework | Count |
|---|---|---|
| java | mockito | 441 |
| javascript | vitest | 277 |
| javascript | jest | 231 |
| javascript | sinon | 68 |
| python | unittest_mock | 7,366 |
| python | pytest_monkeypatch | 3,474 |
| python | pytest_mock | 177 |
| typescript | vitest | 3,198 |
| typescript | jest | 2,380 |
| typescript | sinon | 111 |
| typescript | unittest_mock | 2 |

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

5,352/70,623 fixtures (7.58%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 2,265 | 262 | 11.57% | typescript=175, python=86, javascript=1 |
| javascript | 3,975 | 1,210 | 30.44% | typescript=1,017, python=170, java=23 |
| python | 21,078 | 1,253 | 5.94% | typescript=950, javascript=160, java=143 |
| typescript | 43,305 | 2,627 | 6.07% | javascript=1,932, python=603, java=92 |

### Dataset C (human-authored, pre-LLM) -- 70,623 fixtures, 8,590 mock usages

Mock prevalence: 4,215/70,623 fixtures (6.0%)

**Continuous metrics**

| Metric | n | median | mean | min | max | stdev |
|---|---|---|---|---|---|---|
| num_mocks | 70,623 | 0.00 | 0.12 | 0 | 31 | 0.69 |

**has_mock distribution**

| Value | Count | % |
|---|---|---|
| no_mock | 66,408 | 94.0% |
| has_mock | 4,215 | 6.0% |

**framework distribution**

| Value | Count | % |
|---|---|---|
| jest | 3,225 | 37.5% |
| sinon | 3,002 | 34.9% |
| unittest_mock | 1,795 | 20.9% |
| pytest_monkeypatch | 252 | 2.9% |
| pytest_mock | 173 | 2.0% |
| mockito | 143 | 1.7% |

**category distribution**

| Value | Count | % |
|---|---|---|
| mock | 3,855 | 44.9% |
| stub | 2,773 | 32.3% |
| spy | 1,669 | 19.4% |
| fake | 233 | 2.7% |
| dummy | 60 | 0.7% |

**Mock prevalence by language**

| Language | Fixtures | With >=1 mock | Rate |
|---|---|---|---|
| java | 2,261 | 62 | 2.7% |
| javascript | 4,858 | 319 | 6.6% |
| python | 20,684 | 1,098 | 5.3% |
| typescript | 42,820 | 2,736 | 6.4% |

**Framework distribution by language**

| Language | Framework | Count |
|---|---|---|
| java | mockito | 143 |
| javascript | jest | 377 |
| javascript | sinon | 262 |
| javascript | unittest_mock | 1 |
| python | unittest_mock | 1,790 |
| python | pytest_monkeypatch | 252 |
| python | pytest_mock | 173 |
| typescript | jest | 2,848 |
| typescript | sinon | 2,740 |
| typescript | unittest_mock | 4 |

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

6,376/70,623 fixtures (9.03%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 4,157 | 1,936 | 46.57% | typescript=990, python=866, javascript=80 |
| javascript | 5,610 | 2,126 | 37.90% | typescript=1,797, python=314, java=15 |
| python | 20,359 | 1,013 | 4.98% | typescript=837, javascript=162, java=14 |
| typescript | 40,497 | 1,301 | 3.21% | javascript=1,132, python=158, java=11 |

## A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)

**Continuous metrics (Mann-Whitney U, two-sided)** -- num_mocks has no per-language family (not one of the metrics the paper review named), so it renders Overall-only, shown at both the fixture-level (every fixture as an observation) and repo-level (one mean value per repo) basis. Effect size is Cliff's delta (thresholds: negligible <0.147, small <0.33, medium <0.474, else large).

### num_mocks

**Fixture-level**

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 70623 | 70623 | U=2393479441.5 | -0.040 | negligible | <.001 | -- |

**Repo-level** (one mean value per repo)

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 1687 | 2506 | U=1632601.0 | -0.228 | small | <.001 | -- |

### Mocking Coverage (paper table)

**Coverage** = % of repos with >=1 fixture containing a mock at all (population: every repo with >=1 fixture, of that language for the per-language rows). Purely descriptive -- no statistical test.

| Language | n_A | n_C | Coverage A (%) | Coverage C (%) |
|---|---|---|---|---|
| Overall | 1687 | 2506 | 44.6% | 23.6% |
| java | 127 | 325 | 29.9% | 10.2% |
| javascript | 143 | 563 | 22.4% | 18.1% |
| python | 678 | 1059 | 59.3% | 21.7% |
| typescript | 948 | 753 | 34.5% | 33.2% |

### Mock Fixture Counts by Language

Raw count of fixtures with >=1 mock (`has_mock`), per language, each also shown as a percentage of that language's total fixture count. Unlike RQ3's setup/teardown counts table, `has_mock` is a clean binary with no 'other' category and no double-counting concern, so the denominator here is simply the total fixture count for that language/dataset -- no exclusions. Total is the dataset-wide sum across every language present, not just the four rows below. Purely descriptive -- no significance test (see the Coverage table above for the paper's actual, repo-level mocking comparison).

| Language | Mock A (n) | Mock A (%) | Mock C (n) | Mock C (%) |
|---|---|---|---|---|
| Overall | 7,032 | 10.0% | 4,215 | 6.0% |
| java | 180 | 8.0% | 62 | 2.7% |
| javascript | 189 | 3.9% | 319 | 6.6% |
| python | 4,630 | 22.4% | 1,098 | 5.3% |
| typescript | 2,033 | 4.7% | 2,736 | 6.4% |
