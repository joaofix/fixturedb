# RQ3 -- Mocking

> How do agent-generated and human-written fixtures differ in mock usage -- coverage and intensity?

Generated: 2026-08-31 20:52:51 UTC

See [docs/research-questions.md](../docs/research-questions.md) for the full RQ3 definition.

## Per-dataset summary

### Dataset A (agent-authored) -- 67,979 fixtures, 16,820 mock usages

Mock prevalence: 6,688/67,979 fixtures (9.8%)

**Continuous metrics**

| Metric | n | median | mean | min | max | stdev |
|---|---|---|---|---|---|---|
| num_mocks | 67,979 | 0.00 | 0.25 | 0 | 45 | 1.22 |
| num_interactions_configured | 16,820 | 0.00 | 0.36 | 0 | 8 | 0.75 |

**has_mock distribution**

| Value | Count | % |
|---|---|---|
| no_mock | 61,291 | 90.2% |
| has_mock | 6,688 | 9.8% |

**framework distribution**

| Value | Count | % |
|---|---|---|
| unittest_mock | 7,055 | 41.9% |
| vitest | 3,421 | 20.3% |
| pytest_monkeypatch | 3,041 | 18.1% |
| jest | 2,587 | 15.4% |
| mockito | 377 | 2.2% |
| sinon | 174 | 1.0% |
| pytest_mock | 165 | 1.0% |

**category distribution**

| Value | Count | % |
|---|---|---|
| mock | 13,122 | 78.0% |
| stub | 1,386 | 8.2% |
| fake | 1,121 | 6.7% |
| spy | 1,105 | 6.6% |
| dummy | 86 | 0.5% |

**Mock prevalence by language**

| Language | Fixtures | With >=1 mock | Rate |
|---|---|---|---|
| java | 2,039 | 154 | 7.6% |
| javascript | 4,747 | 183 | 3.9% |
| python | 19,722 | 4,350 | 22.1% |
| typescript | 41,471 | 2,001 | 4.8% |

**Framework distribution by language**

| Language | Framework | Count |
|---|---|---|
| java | mockito | 377 |
| javascript | vitest | 276 |
| javascript | jest | 227 |
| javascript | sinon | 67 |
| python | unittest_mock | 7,053 |
| python | pytest_monkeypatch | 3,041 |
| python | pytest_mock | 165 |
| typescript | vitest | 3,145 |
| typescript | jest | 2,360 |
| typescript | sinon | 107 |
| typescript | unittest_mock | 2 |

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

5,043/67,979 fixtures (7.42%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 2,083 | 232 | 11.14% | typescript=145, python=86, javascript=1 |
| javascript | 3,873 | 1,173 | 30.29% | typescript=990, python=160, java=23 |
| python | 20,148 | 1,192 | 5.92% | typescript=907, javascript=152, java=133 |
| typescript | 41,875 | 2,446 | 5.84% | javascript=1,894, python=520, java=32 |

### Dataset C (human-authored, pre-LLM) -- 67,979 fixtures, 8,154 mock usages

Mock prevalence: 3,960/67,979 fixtures (5.8%)

**Continuous metrics**

| Metric | n | median | mean | min | max | stdev |
|---|---|---|---|---|---|---|
| num_mocks | 67,979 | 0.00 | 0.12 | 0 | 31 | 0.69 |
| num_interactions_configured | 8,154 | 0.00 | 0.12 | 0 | 5 | 0.44 |

**has_mock distribution**

| Value | Count | % |
|---|---|---|
| no_mock | 64,019 | 94.2% |
| has_mock | 3,960 | 5.8% |

**framework distribution**

| Value | Count | % |
|---|---|---|
| jest | 3,193 | 39.2% |
| sinon | 2,873 | 35.2% |
| unittest_mock | 1,566 | 19.2% |
| pytest_monkeypatch | 212 | 2.6% |
| pytest_mock | 160 | 2.0% |
| mockito | 150 | 1.8% |

**category distribution**

| Value | Count | % |
|---|---|---|
| mock | 3,640 | 44.6% |
| stub | 2,662 | 32.6% |
| spy | 1,597 | 19.6% |
| fake | 206 | 2.5% |
| dummy | 49 | 0.6% |

**Mock prevalence by language**

| Language | Fixtures | With >=1 mock | Rate |
|---|---|---|---|
| java | 2,039 | 61 | 3.0% |
| javascript | 4,747 | 341 | 7.2% |
| python | 19,722 | 992 | 5.0% |
| typescript | 41,471 | 2,566 | 6.2% |

**Framework distribution by language**

| Language | Framework | Count |
|---|---|---|
| java | mockito | 150 |
| javascript | jest | 432 |
| javascript | sinon | 299 |
| javascript | unittest_mock | 1 |
| python | unittest_mock | 1,561 |
| python | pytest_monkeypatch | 212 |
| python | pytest_mock | 160 |
| typescript | jest | 2,761 |
| typescript | sinon | 2,574 |
| typescript | unittest_mock | 4 |

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

6,214/67,979 fixtures (9.14%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 3,897 | 1,883 | 48.32% | typescript=985, python=819, javascript=79 |
| javascript | 5,467 | 2,067 | 37.81% | typescript=1,791, python=267, java=9 |
| python | 19,523 | 1,026 | 5.26% | typescript=841, javascript=172, java=13 |
| typescript | 39,092 | 1,238 | 3.17% | javascript=1,096, python=139, java=3 |

## A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)

**Continuous metrics (Mann-Whitney U, two-sided)** -- num_mocks/ num_interactions_configured have no per-language family (not one of the metrics the paper review named), so both render Overall-only, shown at both the fixture-level (every fixture/mock as an observation) and repo-level (one mean value per repo) basis. Effect size is Cliff's delta (thresholds: negligible <0.147, small <0.33, medium <0.474, else large).

### num_mocks

**Fixture-level**

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 67979 | 67979 | U=2217237509.0 | -0.040 | negligible | <.001 | -- |

**Repo-level** (one mean value per repo)

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 1647 | 2472 | U=1607994.5 | -0.210 | small | <.001 | -- |

### num_interactions_configured

**Fixture-level**

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 16820 | 8154 | U=58018585.0 | -0.154 | small | <.001 | -- |

**Repo-level** (one mean value per repo)

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 723 | 610 | U=203753.0 | -0.076 | negligible | 0.002 | -- |

### Mocking Coverage and Intensity (paper table)

**Coverage** = % of repos with >=1 fixture containing a mock at all (population: every repo with >=1 fixture, of that language for the per-language rows). **Intensity** = median `num_mocks` across a repo's own mocking fixtures (`num_mocks > 0` only), then the median of those per-repo values across repos -- **computed only over repos where Coverage = 1**; non-mocking repos are excluded from Intensity entirely, not counted as 0. n_A/n_C is Coverage's population size for that row -- Intensity's true n can be smaller, since it's a strict subset (mocking repos only); this table has one n column pair per row, not one per metric. Both effect sizes are Cliff's delta from a Mann-Whitney U test on the underlying per-repo values (binary for coverage, the per-repo median for intensity). Overall is two single pooled tests (raw p, never BH-corrected). Each language's coverage AND intensity tests (8 tests: 4 languages x 2 metrics) are BH-FDR corrected together as one combined family, not two separate 4-test families -- both are RQ3 metrics reported in this same table.

| Language | n_A | n_C | Coverage A (%) | Coverage C (%) | δ_cov | p_cov | Intensity A | Intensity C | δ_int | p_int |
|---|---|---|---|---|---|---|---|---|---|---|
| Overall | 1647 | 2472 | 43.9% | 24.7% | -0.192 (small) | <.001 | 1.00 | 1.00 | -0.113 (negligible) | <.001 |
| java | 122 | 315 | 28.7% | 13.0% | -0.157 (small) | <.001 | 1.50 | 1.00 | -0.029 (negligible) | 0.824 |
| javascript | 137 | 563 | 22.6% | 21.7% | -0.010 (negligible) | 0.824 | 2.00 | 1.00 | -0.176 (small) | 0.161 |
| python | 656 | 1045 | 58.1% | 21.6% | -0.365 (medium) | <.001 | 1.50 | 1.00 | -0.089 (negligible) | 0.090 |
| typescript | 928 | 749 | 34.2% | 32.8% | -0.013 (negligible) | 0.761 | 1.00 | 1.00 | -0.133 (negligible) | 0.007 |

## Legacy: Fixture-Level Mock Prevalence (Not Used in the Paper)

Kept for transparency/comparison only -- not one of RQ3's reported tables. Pooled + per-language fixture-level `has_mock` chi-square, already flagged as repo-level pseudo-replication (every fixture treated as an independent observation, though fixtures cluster within repos) before the table above existed -- see [Limitations § Categorical Pseudo-Replication](../docs/reference/limitations.md#categorical-pseudo-replication). The paper's actual mocking-coverage result is the Coverage column in the main table above, computed at the repo level directly.

### A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)

**has_mock (chi-square)** -- an "Overall" row (single pooled test, not BH-corrected) plus one BH-corrected row per language (one family, 4 languages -- see render_comparison_table()'s docstring in _shared.py). Effect size is Cramer's V (thresholds: negligible <0.1, small <0.3, medium <0.5, else large).

### has_mock

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 1647 | 2472 | chi2=757.7 (df=1) | 0.075 | negligible | <.001 | -- |
| java | 122 | 315 | chi2=41.6 (df=1) | 0.101 | small | <.001 | <.001 |
| javascript | 137 | 563 | chi2=49.8 (df=1) | 0.072 | negligible | <.001 | <.001 |
| python | 656 | 1045 | chi2=2440.1 (df=1) | 0.249 | small | <.001 | <.001 |
| typescript | 928 | 749 | chi2=73.7 (df=1) | 0.030 | negligible | <.001 | <.001 |
