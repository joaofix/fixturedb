# RQ2 -- Setup and Teardown Characterization

> How do agent-generated fixtures compare to human-written ones in setup and teardown provision?

Generated: 2026-08-06 16:14:47 UTC

See [docs/research-questions.md](../docs/research-questions.md) for the full RQ2 definition.

## Per-dataset summary

### Dataset A (agent-authored) -- 50,498 fixtures

**fixture_type kind distribution**

| Kind | Count | % |
|---|---|---|
| setup | 24,664 | 48.8% |
| teardown | 14,786 | 29.3% |
| other | 11,048 | 21.9% |

**Per-repo setup-to-teardown ratio** (repos with >=1 setup fixture)

- Repos with >=1 setup fixture: 1,035
- Of those, with zero teardown fixtures (ratio undefined): 236 (22.8%)
- Ratio distribution over the remaining 799 repos: mean=2.30, median=1.25, min=0.2, max=122.0

**Per-repo setup-to-teardown ratio, by language** (each fixture's own language, not its repo's tag -- see compute_language_leakage()'s docstring; a repo with setup fixtures in more than one language contributes one ratio value to each)

| Language | Repos with at least one setup fixture | No-teardown repos (ratio undefined) | No-teardown rate | n (ratio computed) | mean | median | min | max |
|---|---|---|---|---|---|---|---|---|
| java | 101 | 38 | 37.6% | 63 | 2.49 | 1.66 | 0.5 | 16.0 |
| javascript | 99 | 25 | 25.3% | 74 | 1.62 | 1.00 | 0.2 | 10.0 |
| python | 194 | 88 | 45.4% | 106 | 2.96 | 1.01 | 0.3 | 55.0 |
| typescript | 731 | 123 | 16.8% | 608 | 2.24 | 1.25 | 0.2 | 122.0 |

**has_teardown_pair rate by fixture_type**

| fixture_type | n | n with teardown pair | rate |
|---|---|---|---|
| before_each | 18,354 | 9,688 | 52.8% |
| pytest_decorator | 10,923 | 2,635 | 24.1% |
| after_each | 10,876 | 0 | 0.0% |
| before_all | 2,655 | 1,874 | 70.6% |
| after_all | 2,232 | 0 | 0.0% |
| unittest_setup | 1,996 | 578 | 29.0% |
| pytest_class_method | 935 | 244 | 26.1% |
| mocha_before | 683 | 518 | 75.8% |
| mocha_after | 521 | 0 | 0.0% |
| junit5_before_each | 466 | 148 | 31.8% |
| junit5_after_each | 205 | 0 | 0.0% |
| junit5_before_all | 168 | 97 | 57.7% |
| junit4_before | 132 | 42 | 31.8% |
| junit5_after_all | 104 | 0 | 0.0% |
| junit_rule | 89 | 0 | 0.0% |
| junit4_after | 50 | 0 | 0.0% |
| testng_before_method | 36 | 10 | 27.8% |
| testng_before_class | 25 | 12 | 48.0% |
| testng_after_method | 15 | 0 | 0.0% |
| testng_after_class | 13 | 0 | 0.0% |
| junit_class_rule | 12 | 0 | 0.0% |
| testng_data_provider | 7 | 0 | 0.0% |
| junit3_setup | 1 | 0 | 0.0% |

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

4,061/50,498 fixtures (8.04%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 1,412 | 233 | 16.50% | typescript=124, python=108, javascript=1 |
| javascript | 3,422 | 969 | 28.32% | typescript=840, python=106, java=23 |
| python | 13,681 | 753 | 5.50% | typescript=471, javascript=208, java=74 |
| typescript | 31,983 | 2,106 | 6.58% | javascript=1,347, python=712, java=47 |

### Dataset B (human-authored, contemporary) -- 68,346 fixtures

**fixture_type kind distribution**

| Kind | Count | % |
|---|---|---|
| setup | 22,603 | 33.1% |
| teardown | 11,411 | 16.7% |
| other | 34,332 | 50.2% |

**Per-repo setup-to-teardown ratio** (repos with >=1 setup fixture)

- Repos with >=1 setup fixture: 772
- Of those, with zero teardown fixtures (ratio undefined): 191 (24.7%)
- Ratio distribution over the remaining 581 repos: mean=2.90, median=1.77, min=0.2, max=26.0

**Per-repo setup-to-teardown ratio, by language** (each fixture's own language, not its repo's tag -- see compute_language_leakage()'s docstring; a repo with setup fixtures in more than one language contributes one ratio value to each)

| Language | Repos with at least one setup fixture | No-teardown repos (ratio undefined) | No-teardown rate | n (ratio computed) | mean | median | min | max |
|---|---|---|---|---|---|---|---|---|
| java | 194 | 37 | 19.1% | 157 | 3.17 | 2.20 | 0.5 | 26.0 |
| javascript | 165 | 21 | 12.7% | 144 | 2.44 | 1.23 | 0.1 | 25.0 |
| python | 391 | 160 | 40.9% | 231 | 3.49 | 1.91 | 0.3 | 28.5 |
| typescript | 172 | 27 | 15.7% | 145 | 2.23 | 1.50 | 0.2 | 15.3 |

**has_teardown_pair rate by fixture_type**

| fixture_type | n | n with teardown pair | rate |
|---|---|---|---|
| pytest_decorator | 32,780 | 8,053 | 24.6% |
| unittest_setup | 7,425 | 2,112 | 28.4% |
| before_each | 6,474 | 3,637 | 56.2% |
| junit5_before_each | 4,335 | 1,528 | 35.2% |
| after_each | 4,066 | 0 | 0.0% |
| junit5_after_each | 1,913 | 0 | 0.0% |
| pytest_class_method | 1,910 | 463 | 24.2% |
| testng_before_class | 1,275 | 1,057 | 82.9% |
| junit5_before_all | 1,121 | 540 | 48.2% |
| testng_after_class | 1,093 | 0 | 0.0% |
| before_all | 1,063 | 506 | 47.6% |
| testng_data_provider | 784 | 0 | 0.0% |
| junit4_before | 770 | 317 | 41.2% |
| junit5_after_all | 567 | 0 | 0.0% |
| mocha_before | 553 | 413 | 74.7% |
| after_all | 518 | 0 | 0.0% |
| junit4_after | 416 | 0 | 0.0% |
| mocha_after | 383 | 0 | 0.0% |
| junit_rule | 356 | 356 | 100.0% |
| testng_before_method | 259 | 75 | 29.0% |
| testng_after_method | 109 | 0 | 0.0% |
| junit_class_rule | 104 | 104 | 100.0% |
| junit3_setup | 69 | 2 | 2.9% |
| junit3_teardown | 3 | 0 | 0.0% |

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

8,302/68,346 fixtures (12.15%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 14,571 | 1,752 | 12.02% | typescript=837, python=530, javascript=385 |
| javascript | 7,704 | 1,876 | 24.35% | typescript=1,618, python=188, java=70 |
| python | 46,071 | 4,674 | 10.15% | typescript=3,930, javascript=459, java=285 |

### Dataset C (human-authored, pre-LLM) -- 166,070 fixtures

**fixture_type kind distribution**

| Kind | Count | % |
|---|---|---|
| setup | 99,870 | 60.1% |
| teardown | 40,031 | 24.1% |
| other | 26,169 | 15.8% |

**Per-repo setup-to-teardown ratio** (repos with >=1 setup fixture)

- Repos with >=1 setup fixture: 2,473
- Of those, with zero teardown fixtures (ratio undefined): 706 (28.5%)
- Ratio distribution over the remaining 1,767 repos: mean=4.84, median=2.00, min=0.0, max=121.0

**Per-repo setup-to-teardown ratio, by language** (each fixture's own language, not its repo's tag -- see compute_language_leakage()'s docstring; a repo with setup fixtures in more than one language contributes one ratio value to each)

| Language | Repos with at least one setup fixture | No-teardown repos (ratio undefined) | No-teardown rate | n (ratio computed) | mean | median | min | max |
|---|---|---|---|---|---|---|---|---|
| java | 559 | 157 | 28.1% | 402 | 4.34 | 2.08 | 0.1 | 85.0 |
| javascript | 534 | 132 | 24.7% | 402 | 4.75 | 1.75 | 0.0 | 121.0 |
| python | 668 | 227 | 34.0% | 441 | 5.04 | 2.00 | 0.3 | 86.0 |
| typescript | 712 | 190 | 26.7% | 522 | 5.13 | 2.00 | 0.0 | 78.2 |

**has_teardown_pair rate by fixture_type**

| fixture_type | n | n with teardown pair | rate |
|---|---|---|---|
| before_each | 41,712 | 15,756 | 37.8% |
| unittest_setup | 24,238 | 7,673 | 31.7% |
| pytest_decorator | 15,964 | 2,715 | 17.0% |
| after_each | 14,159 | 0 | 0.0% |
| junit4_before | 13,080 | 4,292 | 32.8% |
| mocha_before | 8,989 | 5,092 | 56.6% |
| testng_before_class | 6,628 | 2,866 | 43.2% |
| junit_rule | 5,616 | 5,616 | 100.0% |
| before_all | 4,987 | 2,541 | 51.0% |
| junit4_after | 4,951 | 0 | 0.0% |
| mocha_after | 4,691 | 0 | 0.0% |
| testng_after_class | 3,318 | 0 | 0.0% |
| testng_data_provider | 3,196 | 0 | 0.0% |
| junit5_before_each | 2,880 | 955 | 33.2% |
| after_all | 2,829 | 0 | 0.0% |
| junit_class_rule | 1,343 | 1,343 | 100.0% |
| junit5_after_each | 1,262 | 0 | 0.0% |
| testng_before_method | 1,172 | 478 | 40.8% |
| junit5_before_all | 1,168 | 558 | 47.8% |
| pytest_class_method | 1,049 | 248 | 23.6% |
| junit3_setup | 1,005 | 547 | 54.4% |
| junit5_after_all | 685 | 0 | 0.0% |
| junit3_teardown | 581 | 0 | 0.0% |
| testng_after_method | 567 | 0 | 0.0% |

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

0/166,070 fixtures (0.00%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 47,452 | 0 | 0.00% | -- |
| javascript | 30,032 | 0 | 0.00% | -- |
| python | 41,251 | 0 | 0.00% | -- |
| typescript | 47,335 | 0 | 0.00% | -- |

## A vs B: Dataset A (agent-authored) vs Dataset B (human-authored, contemporary)

**Per-repo setup-to-teardown ratio (Mann-Whitney U, two-sided)** -- Cliff's delta thresholds: negligible <0.147, small <0.33, medium <0.474, else large; positive means the comparison dataset tends to have a larger ratio than A, negative means A tends to have a larger ratio.

A mean=2.30, median=1.25 | B mean=2.90, median=1.77 | U=281015.0 | p=1.736e-11 | significant (p<0.05): yes | Cliff's delta (effect size): 0.211 (small)

**Categorical comparisons (chi-square)** -- Cramer's V thresholds: negligible <0.1, small <0.3, medium <0.5, else large. BH-FDR corrects for running both of these tests together.

| Metric | chi2 | dof | p-value | significant (p<0.05) | Cramer's V (effect size) | BH-FDR adjusted p (sig?) |
|---|---|---|---|---|---|---|
| fixture_type_kind | 10017.0 | 2 | 0 | yes | 0.290 (small) | 0 (yes) |
| repo_zero_teardown_rate | 0.8 | 1 | 0.3661 | no | 0.021 (negligible) | 0.3661 (no) |

**fixture_type_kind, stratified by language (chi-square per language)** -- the aggregate comparison above can look significant purely because Dataset A (agent-authored) and Dataset B (human-authored, contemporary) have different language mixes; this checks whether the difference holds within each shared language.

| Language | chi2 | dof | p-value | significant (p<0.05) | Cramer's V (effect size) | BH-FDR adjusted p (sig?) |
|---|---|---|---|---|---|---|
| java | 5.5 | 2 | 0.06434 | no | 0.019 (negligible) | 0.08579 (no) |
| javascript | 30.9 | 1 | 2.686e-08 | yes | 0.054 (negligible) | 1.074e-07 (yes) |
| python | 1.2 | 2 | 0.5366 | no | 0.005 (negligible) | 0.5366 (no) |
| typescript | 6.8 | 1 | 0.008916 | yes | 0.013 (negligible) | 0.01783 (yes) |

## A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)

**Per-repo setup-to-teardown ratio (Mann-Whitney U, two-sided)** -- Cliff's delta thresholds: negligible <0.147, small <0.33, medium <0.474, else large; positive means the comparison dataset tends to have a larger ratio than A, negative means A tends to have a larger ratio.

A mean=2.30, median=1.25 | C mean=4.84, median=2.00 | U=897623.5 | p=1.895e-28 | significant (p<0.05): yes | Cliff's delta (effect size): 0.272 (small)

**Categorical comparisons (chi-square)** -- Cramer's V thresholds: negligible <0.1, small <0.3, medium <0.5, else large. BH-FDR corrects for running both of these tests together.

| Metric | chi2 | dof | p-value | significant (p<0.05) | Cramer's V (effect size) | BH-FDR adjusted p (sig?) |
|---|---|---|---|---|---|---|
| fixture_type_kind | 2113.1 | 2 | 0 | yes | 0.099 (negligible) | 0 (yes) |
| repo_zero_teardown_rate | 12.0 | 1 | 0.0005391 | yes | 0.058 (negligible) | 0.0005391 (yes) |

**fixture_type_kind, stratified by language (chi-square per language)** -- the aggregate comparison above can look significant purely because Dataset A (agent-authored) and Dataset C (human-authored, pre-LLM) have different language mixes; this checks whether the difference holds within each shared language.

| Language | chi2 | dof | p-value | significant (p<0.05) | Cramer's V (effect size) | BH-FDR adjusted p (sig?) |
|---|---|---|---|---|---|---|
| java | 137.0 | 2 | 1.8e-30 | yes | 0.053 (negligible) | 1.8e-30 (yes) |
| javascript | 177.2 | 1 | 1.974e-40 | yes | 0.072 (negligible) | 2.632e-40 (yes) |
| python | 6690.0 | 2 | 0 | yes | 0.348 (medium) | 0 (yes) |
| typescript | 1304.2 | 1 | 1.381e-285 | yes | 0.129 (small) | 2.763e-285 (yes) |
