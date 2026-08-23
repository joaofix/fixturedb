# RQ3 -- Mocking

> How do agent-generated and human-written fixtures differ in mock usage -- coverage and intensity?

Generated: 2026-08-23 02:26:39 UTC

See [docs/research-questions.md](../docs/research-questions.md) for the full RQ3 definition.

## Per-dataset summary

### Dataset A (agent-authored) -- 47,208 fixtures, 10,510 mock usages

Mock prevalence: 3,924/47,208 fixtures (8.3%)

**Continuous metrics**

| Metric | n | median | mean | min | max | stdev |
|---|---|---|---|---|---|---|
| num_mocks | 47,208 | 0.00 | 0.22 | 0 | 45 | 1.21 |
| num_interactions_configured | 10,510 | 0.00 | 0.27 | 0 | 5 | 0.65 |

**has_mock distribution**

| Value | Count | % |
|---|---|---|
| no_mock | 43,284 | 91.7% |
| has_mock | 3,924 | 8.3% |

**framework distribution**

| Value | Count | % |
|---|---|---|
| unittest_mock | 3,137 | 29.8% |
| vitest | 2,868 | 27.3% |
| pytest_monkeypatch | 2,087 | 19.9% |
| jest | 1,891 | 18.0% |
| mockito | 262 | 2.5% |
| sinon | 152 | 1.4% |
| pytest_mock | 113 | 1.1% |

**category distribution**

| Value | Count | % |
|---|---|---|
| mock | 7,955 | 75.7% |
| stub | 1,032 | 9.8% |
| spy | 793 | 7.5% |
| fake | 679 | 6.5% |
| dummy | 51 | 0.5% |

**Mock prevalence by language**

| Language | Fixtures | With >=1 mock | Rate |
|---|---|---|---|
| java | 1,398 | 98 | 7.0% |
| javascript | 4,174 | 154 | 3.7% |
| python | 11,035 | 2,214 | 20.1% |
| typescript | 30,601 | 1,458 | 4.8% |

**Framework distribution by language**

| Language | Framework | Count |
|---|---|---|
| java | mockito | 262 |
| javascript | vitest | 275 |
| javascript | jest | 186 |
| javascript | sinon | 54 |
| python | unittest_mock | 3,136 |
| python | pytest_monkeypatch | 2,087 |
| python | pytest_mock | 113 |
| typescript | vitest | 2,593 |
| typescript | jest | 1,705 |
| typescript | sinon | 98 |
| typescript | unittest_mock | 1 |

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

3,561/47,208 fixtures (7.54%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 1,429 | 111 | 7.77% | typescript=83, python=27, javascript=1 |
| javascript | 3,385 | 962 | 28.42% | typescript=797, python=142, java=23 |
| python | 11,000 | 492 | 4.47% | typescript=323, javascript=144, java=25 |
| typescript | 31,394 | 1,996 | 6.36% | javascript=1,606, python=358, java=32 |

### Dataset C (human-authored, pre-LLM) -- 47,208 fixtures, 6,134 mock usages

Mock prevalence: 2,882/47,208 fixtures (6.1%)

**Continuous metrics**

| Metric | n | median | mean | min | max | stdev |
|---|---|---|---|---|---|---|
| num_mocks | 47,208 | 0.00 | 0.13 | 0 | 31 | 0.76 |
| num_interactions_configured | 6,134 | 0.00 | 0.13 | 0 | 5 | 0.47 |

**has_mock distribution**

| Value | Count | % |
|---|---|---|
| no_mock | 44,326 | 93.9% |
| has_mock | 2,882 | 6.1% |

**framework distribution**

| Value | Count | % |
|---|---|---|
| jest | 2,581 | 42.1% |
| sinon | 2,200 | 35.9% |
| unittest_mock | 993 | 16.2% |
| mockito | 137 | 2.2% |
| pytest_monkeypatch | 130 | 2.1% |
| pytest_mock | 93 | 1.5% |

**category distribution**

| Value | Count | % |
|---|---|---|
| mock | 2,594 | 42.3% |
| stub | 2,029 | 33.1% |
| spy | 1,282 | 20.9% |
| fake | 198 | 3.2% |
| dummy | 31 | 0.5% |

**Mock prevalence by language**

| Language | Fixtures | With >=1 mock | Rate |
|---|---|---|---|
| java | 1,398 | 43 | 3.1% |
| javascript | 4,174 | 281 | 6.7% |
| python | 11,035 | 586 | 5.3% |
| typescript | 30,601 | 1,972 | 6.4% |

**Framework distribution by language**

| Language | Framework | Count |
|---|---|---|
| java | mockito | 137 |
| javascript | jest | 368 |
| javascript | sinon | 241 |
| javascript | unittest_mock | 1 |
| python | unittest_mock | 990 |
| python | pytest_monkeypatch | 130 |
| python | pytest_mock | 93 |
| typescript | jest | 2,213 |
| typescript | sinon | 1,959 |
| typescript | unittest_mock | 2 |

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

4,318/47,208 fixtures (9.15%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 2,541 | 1,168 | 45.97% | typescript=684, python=428, javascript=56 |
| javascript | 4,454 | 1,385 | 31.10% | typescript=1,223, python=156, java=6 |
| python | 11,119 | 758 | 6.82% | typescript=607, javascript=135, java=16 |
| typescript | 29,094 | 1,007 | 3.46% | javascript=914, python=90, java=3 |

## A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)

**Continuous metrics (Mann-Whitney U, two-sided)** -- num_mocks/ num_interactions_configured have no per-language family (not one of the metrics the paper review named), so both render Overall-only, shown at both the fixture-level (every fixture/mock as an observation) and repo-level (one mean value per repo) basis. Effect size is Cliff's delta (thresholds: negligible <0.147, small <0.33, medium <0.474, else large).

### num_mocks

**Fixture-level**

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 47208 | 47208 | U=1089316348.0 | -0.022 | negligible | <.001 | -- |

**Repo-level** (one mean value per repo)

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 1354 | 2325 | U=1247171.5 | -0.208 | small | <.001 | -- |

### num_interactions_configured

**Fixture-level**

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 10510 | 6134 | U=29235790.5 | -0.093 | negligible | <.001 | -- |

**Repo-level** (one mean value per repo)

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 574 | 530 | U=137644.0 | -0.095 | negligible | <.001 | -- |

### Mocking Coverage and Intensity (paper table)

**Coverage** = % of repos with >=1 fixture containing a mock at all (population: every repo with >=1 fixture, of that language for the per-language rows). **Intensity** = median `num_mocks` across a repo's own mocking fixtures (`num_mocks > 0` only), then the median of those per-repo values across repos -- **computed only over repos where Coverage = 1**; non-mocking repos are excluded from Intensity entirely, not counted as 0. n_A/n_C is Coverage's population size for that row -- Intensity's true n can be smaller, since it's a strict subset (mocking repos only); this table has one n column pair per row, not one per metric. Both effect sizes are Cliff's delta from a Mann-Whitney U test on the underlying per-repo values (binary for coverage, the per-repo median for intensity). Overall is two single pooled tests (raw p, never BH-corrected). Each language's coverage AND intensity tests (8 tests: 4 languages x 2 metrics) are BH-FDR corrected together as one combined family, not two separate 4-test families -- both are RQ3 metrics reported in this same table.

| Language | n_A | n_C | Coverage A (%) | Coverage C (%) | δ_cov | p_cov | Intensity A | Intensity C | δ_int | p_int |
|---|---|---|---|---|---|---|---|---|---|---|
| Overall | 1354 | 2325 | 42.4% | 22.8% | -0.196 (small) | <.001 | 1.50 | 1.00 | -0.130 (negligible) | <.001 |
| java | 97 | 267 | 28.9% | 11.2% | -0.176 (small) | <.001 | 1.50 | 2.00 | 0.090 (negligible) | 0.623 |
| javascript | 115 | 557 | 21.7% | 20.8% | -0.009 (negligible) | 0.827 | 2.00 | 1.00 | -0.277 (small) | 0.026 |
| python | 531 | 944 | 56.3% | 18.2% | -0.381 (medium) | <.001 | 1.50 | 1.00 | -0.111 (negligible) | 0.047 |
| typescript | 749 | 735 | 33.1% | 31.2% | -0.020 (negligible) | 0.561 | 1.00 | 1.00 | -0.122 (negligible) | 0.026 |

## Legacy: Fixture-Level Mock Prevalence (Not Used in the Paper)

Kept for transparency/comparison only -- not one of RQ3's reported tables. Pooled + per-language fixture-level `has_mock` chi-square, already flagged as repo-level pseudo-replication (every fixture treated as an independent observation, though fixtures cluster within repos) before the table above existed -- see [Limitations § Categorical Pseudo-Replication](../docs/reference/limitations.md#categorical-pseudo-replication). The paper's actual mocking-coverage result is the Coverage column in the main table above, computed at the repo level directly.

### A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)

**has_mock (chi-square)** -- an "Overall" row (single pooled test, not BH-corrected) plus one BH-corrected row per language (one family, 4 languages -- see render_comparison_table()'s docstring in _shared.py). Effect size is Cramer's V (thresholds: negligible <0.1, small <0.3, medium <0.5, else large).

### has_mock

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 1354 | 2325 | chi2=171.6 (df=1) | 0.043 | negligible | <.001 | -- |
| java | 97 | 267 | chi2=21.8 (df=1) | 0.088 | negligible | <.001 | <.001 |
| javascript | 115 | 557 | chi2=38.5 (df=1) | 0.068 | negligible | <.001 | <.001 |
| python | 531 | 944 | chi2=1082.8 (df=1) | 0.221 | small | <.001 | <.001 |
| typescript | 749 | 735 | chi2=81.3 (df=1) | 0.036 | negligible | <.001 | <.001 |
