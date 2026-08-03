# RQ3 -- Mocking

> How do agent-generated and human-written fixtures differ in mock usage -- prevalence, framework selection, and interaction depth?

Generated: 2026-08-03 21:07:55 UTC

See [docs/research-questions.md](../docs/research-questions.md) for the full RQ3 definition.

## Per-dataset summary

### Dataset A (agent-authored) -- 50,498 fixtures, 11,353 mock usages

Mock prevalence: 4,407/50,498 fixtures (8.7%)

**Continuous metrics**

| Metric | n | mean | median | min | max | stdev |
|---|---|---|---|---|---|---|
| num_mocks | 50,498 | 0.22 | 0.00 | 0 | 45 | 1.17 |
| num_interactions_configured | 11,353 | 0.31 | 0.00 | 0 | 5 | 0.71 |

**has_mock distribution**

| Value | Count | % |
|---|---|---|
| no_mock | 46,091 | 91.3% |
| has_mock | 4,407 | 8.7% |

**framework distribution**

| Value | Count | % |
|---|---|---|
| unittest_mock | 4,322 | 38.1% |
| vitest | 2,965 | 26.1% |
| pytest_monkeypatch | 1,878 | 16.5% |
| jest | 1,746 | 15.4% |
| mockito | 244 | 2.1% |
| sinon | 111 | 1.0% |
| pytest_mock | 87 | 0.8% |

**category distribution**

| Value | Count | % |
|---|---|---|
| mock | 8,743 | 77.0% |
| stub | 938 | 8.3% |
| spy | 869 | 7.7% |
| fake | 722 | 6.4% |
| dummy | 81 | 0.7% |

**Mock prevalence by language**

| Language | Fixtures | With >=1 mock | Rate |
|---|---|---|---|
| java | 1,323 | 97 | 7.3% |
| javascript | 4,009 | 150 | 3.7% |
| python | 13,854 | 2,651 | 19.1% |
| typescript | 31,312 | 1,509 | 4.8% |

**Framework distribution by language**

| Language | Framework | Count |
|---|---|---|
| java | mockito | 244 |
| javascript | vitest | 276 |
| javascript | jest | 176 |
| javascript | sinon | 61 |
| python | unittest_mock | 4,321 |
| python | pytest_monkeypatch | 1,878 |
| python | pytest_mock | 87 |
| typescript | vitest | 2,689 |
| typescript | jest | 1,570 |
| typescript | sinon | 50 |
| typescript | unittest_mock | 1 |

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

4,061/50,498 fixtures (8.04%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 1,412 | 233 | 16.50% | typescript=124, python=108, javascript=1 |
| javascript | 3,422 | 969 | 28.32% | typescript=840, python=106, java=23 |
| python | 13,681 | 753 | 5.50% | typescript=471, javascript=208, java=74 |
| typescript | 31,983 | 2,106 | 6.58% | javascript=1,347, python=712, java=47 |

### Dataset B (human-authored, contemporary) -- 68,346 fixtures, 25,994 mock usages

Mock prevalence: 10,166/68,346 fixtures (14.9%)

**Continuous metrics**

| Metric | n | mean | median | min | max | stdev |
|---|---|---|---|---|---|---|
| num_mocks | 68,346 | 0.38 | 0.00 | 0 | 75 | 1.45 |
| num_interactions_configured | 25,994 | 0.49 | 0.00 | 0 | 7 | 0.83 |

**has_mock distribution**

| Value | Count | % |
|---|---|---|
| no_mock | 58,180 | 85.1% |
| has_mock | 10,166 | 14.9% |

**framework distribution**

| Value | Count | % |
|---|---|---|
| unittest_mock | 14,741 | 56.7% |
| pytest_monkeypatch | 5,359 | 20.6% |
| mockito | 2,314 | 8.9% |
| sinon | 1,588 | 6.1% |
| jest | 1,034 | 4.0% |
| vitest | 697 | 2.7% |
| pytest_mock | 261 | 1.0% |

**category distribution**

| Value | Count | % |
|---|---|---|
| mock | 20,878 | 80.3% |
| stub | 2,536 | 9.8% |
| fake | 1,653 | 6.4% |
| dummy | 511 | 2.0% |
| spy | 416 | 1.6% |

**Mock prevalence by language**

| Language | Fixtures | With >=1 mock | Rate |
|---|---|---|---|
| java | 13,174 | 968 | 7.3% |
| javascript | 6,672 | 538 | 8.1% |
| python | 42,115 | 8,296 | 19.7% |
| typescript | 6,385 | 364 | 5.7% |

**Framework distribution by language**

| Language | Framework | Count |
|---|---|---|
| java | mockito | 2,314 |
| java | unittest_mock | 1 |
| javascript | jest | 736 |
| javascript | sinon | 726 |
| javascript | vitest | 230 |
| python | unittest_mock | 14,739 |
| python | pytest_monkeypatch | 5,359 |
| python | pytest_mock | 261 |
| typescript | sinon | 862 |
| typescript | vitest | 467 |
| typescript | jest | 298 |
| typescript | unittest_mock | 1 |

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

8,302/68,346 fixtures (12.15%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 14,571 | 1,752 | 12.02% | typescript=837, python=530, javascript=385 |
| javascript | 7,704 | 1,876 | 24.35% | typescript=1,618, python=188, java=70 |
| python | 46,071 | 4,674 | 10.15% | typescript=3,930, javascript=459, java=285 |

### Dataset C (human-authored, pre-LLM) -- 166,070 fixtures, 19,325 mock usages

Mock prevalence: 9,079/166,070 fixtures (5.5%)

**Continuous metrics**

| Metric | n | mean | median | min | max | stdev |
|---|---|---|---|---|---|---|
| num_mocks | 166,070 | 0.12 | 0.00 | 0 | 32 | 0.70 |
| num_interactions_configured | 19,325 | 0.21 | 0.00 | 0 | 5 | 0.58 |

**has_mock distribution**

| Value | Count | % |
|---|---|---|
| no_mock | 156,991 | 94.5% |
| has_mock | 9,079 | 5.5% |

**framework distribution**

| Value | Count | % |
|---|---|---|
| jest | 5,532 | 28.6% |
| sinon | 5,307 | 27.5% |
| mockito | 4,167 | 21.6% |
| unittest_mock | 3,491 | 18.1% |
| pytest_monkeypatch | 475 | 2.5% |
| pytest_mock | 349 | 1.8% |
| easymock | 4 | 0.0% |

**category distribution**

| Value | Count | % |
|---|---|---|
| mock | 10,515 | 54.4% |
| stub | 4,845 | 25.1% |
| spy | 3,222 | 16.7% |
| fake | 586 | 3.0% |
| dummy | 157 | 0.8% |

**Mock prevalence by language**

| Language | Fixtures | With >=1 mock | Rate |
|---|---|---|---|
| java | 47,452 | 1,755 | 3.7% |
| javascript | 30,032 | 2,075 | 6.9% |
| python | 41,251 | 2,221 | 5.4% |
| typescript | 47,335 | 3,028 | 6.4% |

**Framework distribution by language**

| Language | Framework | Count |
|---|---|---|
| java | mockito | 4,167 |
| java | easymock | 4 |
| javascript | sinon | 2,505 |
| javascript | jest | 2,298 |
| javascript | unittest_mock | 3 |
| python | unittest_mock | 3,480 |
| python | pytest_monkeypatch | 475 |
| python | pytest_mock | 349 |
| typescript | jest | 3,234 |
| typescript | sinon | 2,802 |
| typescript | unittest_mock | 8 |

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

0/166,070 fixtures (0.00%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 47,452 | 0 | 0.00% | -- |
| javascript | 30,032 | 0 | 0.00% | -- |
| python | 41,251 | 0 | 0.00% | -- |
| typescript | 47,335 | 0 | 0.00% | -- |

## A vs B: Dataset A (agent-authored) vs Dataset B (human-authored, contemporary)

**Continuous metrics (Mann-Whitney U, two-sided)** -- p-values shrink with sample size alone; Cliff's delta is what says how big the difference actually is (thresholds: negligible <0.147, small <0.33, medium <0.474, else large; positive means the comparison dataset tends to have larger values than A, negative means A tends to have larger values). BH-FDR corrects for running both of these tests together.

| Metric | A mean | A median | B mean | B median | U | p-value | significant (p<0.05) | Cliff's delta (effect size) | BH-FDR adjusted p (sig?) |
|---|---|---|---|---|---|---|---|---|---|
| num_mocks | 0.22 | 0.00 | 0.38 | 0.00 | 1832271608.0 | 6.601e-225 | yes | 0.062 (negligible) | 1.32e-224 (yes) |
| num_interactions_configured | 0.31 | 0.00 | 0.49 | 0.00 | 165115743.5 | 4.279e-117 | yes | 0.119 (negligible) | 4.279e-117 (yes) |

**Categorical metrics (chi-square)** -- Cramer's V thresholds: negligible <0.1, small <0.3, medium <0.5, else large. BH-FDR corrects for running all 3 of these tests together.

| Metric | chi2 | dof | p-value | significant (p<0.05) | Cramer's V (effect size) | BH-FDR adjusted p (sig?) |
|---|---|---|---|---|---|---|
| has_mock | 1019.5 | 1 | 1.06e-223 | yes | 0.093 (negligible) | 1.589e-223 (yes) |
| framework | 7399.6 | 6 | 0 | yes | 0.445 (medium) | 0 (yes) |
| category | 949.8 | 4 | 2.749e-204 | yes | 0.159 (small) | 2.749e-204 (yes) |

**has_mock, stratified by language (chi-square per language)** -- the aggregate comparison above can look significant purely because Dataset A (agent-authored) and Dataset B (human-authored, contemporary) have different language mixes; this checks whether the difference holds within each shared language.

| Language | chi2 | dof | p-value | significant (p<0.05) | Cramer's V (effect size) | BH-FDR adjusted p (sig?) |
|---|---|---|---|---|---|---|
| java | 0.0 | 1 | 1 | no | 0.000 (negligible) | 1 (no) |
| javascript | 76.9 | 1 | 1.793e-18 | yes | 0.085 (negligible) | 7.171e-18 (yes) |
| python | 2.1 | 1 | 0.1506 | no | 0.006 (negligible) | 0.2008 (no) |
| typescript | 8.5 | 1 | 0.003465 | yes | 0.015 (negligible) | 0.006931 (yes) |

## A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)

**Continuous metrics (Mann-Whitney U, two-sided)** -- p-values shrink with sample size alone; Cliff's delta is what says how big the difference actually is (thresholds: negligible <0.147, small <0.33, medium <0.474, else large; positive means the comparison dataset tends to have larger values than A, negative means A tends to have larger values). BH-FDR corrects for running both of these tests together.

| Metric | A mean | A median | C mean | C median | U | p-value | significant (p<0.05) | Cliff's delta (effect size) | BH-FDR adjusted p (sig?) |
|---|---|---|---|---|---|---|---|---|---|
| num_mocks | 0.22 | 0.00 | 0.12 | 0.00 | 4055280589.0 | 1.221e-157 | yes | -0.033 (negligible) | 2.443e-157 (yes) |
| num_interactions_configured | 0.31 | 0.00 | 0.21 | 0.00 | 102907762.0 | 2.923e-44 | yes | -0.062 (negligible) | 2.923e-44 (yes) |

**Categorical metrics (chi-square)** -- Cramer's V thresholds: negligible <0.1, small <0.3, medium <0.5, else large. BH-FDR corrects for running all 3 of these tests together.

| Metric | chi2 | dof | p-value | significant (p<0.05) | Cramer's V (effect size) | BH-FDR adjusted p (sig?) |
|---|---|---|---|---|---|---|
| has_mock | 704.2 | 1 | 3.567e-155 | yes | 0.057 (negligible) | 3.567e-155 (yes) |
| framework | 13320.8 | 7 | 0 | yes | 0.659 (large) | 0 (yes) |
| category | 2276.5 | 4 | 0 | yes | 0.272 (small) | 0 (yes) |

**has_mock, stratified by language (chi-square per language)** -- the aggregate comparison above can look significant purely because Dataset A (agent-authored) and Dataset C (human-authored, pre-LLM) have different language mixes; this checks whether the difference holds within each shared language.

| Language | chi2 | dof | p-value | significant (p<0.05) | Cramer's V (effect size) | BH-FDR adjusted p (sig?) |
|---|---|---|---|---|---|---|
| java | 45.5 | 1 | 1.506e-11 | yes | 0.031 (negligible) | 1.506e-11 (yes) |
| javascript | 57.6 | 1 | 3.249e-14 | yes | 0.041 (negligible) | 4.332e-14 (yes) |
| python | 2431.5 | 1 | 0 | yes | 0.210 (small) | 0 (yes) |
| typescript | 86.0 | 1 | 1.794e-20 | yes | 0.033 (negligible) | 3.588e-20 (yes) |

## Repo-level aggregates

The comparisons above treat every fixture/mock as an independent observation, but they cluster within repos (shared authorship conventions, framework choices, project style) -- a handful of unusually prolific repos can dominate a fixture-level result. This section re-runs the continuous metrics with one *mean-per-repo* value per repo instead, so each repo counts once regardless of how many fixtures/mocks it contributed.

### A vs B: Dataset A (agent-authored) vs Dataset B (human-authored, contemporary)

| Metric | A mean | A median | B mean | B median | U | p-value | significant (p<0.05) | Cliff's delta (effect size) | BH-FDR adjusted p (sig?) |
|---|---|---|---|---|---|---|---|---|---|
| num_mocks | 0.29 | 0.00 | 0.33 | 0.10 | 939168.5 | 1.792e-11 | yes | 0.143 (negligible) | 1.792e-11 (yes) |
| num_interactions_configured | 0.23 | 0.00 | 0.43 | 0.32 | 262763.5 | 7.628e-25 | yes | 0.309 (small) | 1.526e-24 (yes) |

### A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)

| Metric | A mean | A median | C mean | C median | U | p-value | significant (p<0.05) | Cliff's delta (effect size) | BH-FDR adjusted p (sig?) |
|---|---|---|---|---|---|---|---|---|---|
| num_mocks | 0.29 | 0.00 | 0.12 | 0.00 | 1735864.5 | 4.096e-26 | yes | -0.167 (small) | 8.192e-26 (yes) |
| num_interactions_configured | 0.23 | 0.00 | 0.22 | 0.00 | 269109.0 | 0.8588 | no | -0.004 (negligible) | 0.8588 (no) |
