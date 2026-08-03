# RQ1 -- General Metrics Overview

> How do agent-generated and human-written fixtures compare across structural metrics?

Generated: 2026-08-03 21:07:51 UTC

See [docs/research-questions.md](../docs/research-questions.md) for the full RQ1 definition.

## Per-dataset summary

### Dataset A (agent-authored) -- 50,498 fixtures

**Continuous metrics**

| Metric | n | mean | median | min | max | stdev |
|---|---|---|---|---|---|---|
| loc | 50,498 | 7.61 | 4.00 | 1 | 358 | 10.17 |
| cyclomatic_complexity | 50,498 | 1.20 | 1.00 | 1 | 25 | 0.69 |
| max_nesting_depth | 50,498 | 1.19 | 1.00 | 1 | 6 | 0.47 |
| num_parameters | 50,498 | 0.15 | 0.00 | 0 | 12 | 0.52 |
| num_objects_instantiated | 50,498 | 0.41 | 0.00 | 0 | 38 | 1.08 |
| num_external_calls | 50,498 | 0.06 | 0.00 | 0 | 16 | 0.42 |

**scope distribution**

| Value | Count | % |
|---|---|---|
| per_test | 44,030 | 87.2% |
| per_class | 5,468 | 10.8% |
| per_module | 738 | 1.5% |
| global | 262 | 0.5% |

**fixture_type distribution**

| Value | Count | % |
|---|---|---|
| before_each | 18,354 | 36.3% |
| pytest_decorator | 10,923 | 21.6% |
| after_each | 10,876 | 21.5% |
| before_all | 2,655 | 5.3% |
| after_all | 2,232 | 4.4% |
| unittest_setup | 1,996 | 4.0% |
| pytest_class_method | 935 | 1.9% |
| mocha_before | 683 | 1.4% |
| mocha_after | 521 | 1.0% |
| junit5_before_each | 466 | 0.9% |
| junit5_after_each | 205 | 0.4% |
| junit5_before_all | 168 | 0.3% |
| junit4_before | 132 | 0.3% |
| junit5_after_all | 104 | 0.2% |
| junit_rule | 89 | 0.2% |
| junit4_after | 50 | 0.1% |
| testng_before_method | 36 | 0.1% |
| testng_before_class | 25 | 0.0% |
| testng_after_method | 15 | 0.0% |
| testng_after_class | 13 | 0.0% |
| junit_class_rule | 12 | 0.0% |
| testng_data_provider | 7 | 0.0% |
| junit3_setup | 1 | 0.0% |

**commit_type distribution**

| Value | Count | % |
|---|---|---|
| feat | 23,190 | 45.9% |
| none | 12,927 | 25.6% |
| fix | 7,182 | 14.2% |
| test | 5,030 | 10.0% |
| refactor | 1,019 | 2.0% |
| chore | 694 | 1.4% |
| other | 357 | 0.7% |
| docs | 99 | 0.2% |

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

4,061/50,498 fixtures (8.04%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 1,412 | 233 | 16.50% | typescript=124, python=108, javascript=1 |
| javascript | 3,422 | 969 | 28.32% | typescript=840, python=106, java=23 |
| python | 13,681 | 753 | 5.50% | typescript=471, javascript=208, java=74 |
| typescript | 31,983 | 2,106 | 6.58% | javascript=1,347, python=712, java=47 |

**agent_type distribution** (descriptive only, not compared against other datasets -- see load_dataset_metrics()'s docstring for why)

| Value | Count | % |
|---|---|---|
| claude | 43,226 | 85.6% |
| copilot | 3,612 | 7.2% |
| cursor | 2,032 | 4.0% |
| devin | 366 | 0.7% |
| codex | 290 | 0.6% |
| paperclip | 288 | 0.6% |
| gemini | 216 | 0.4% |
| qwen_coder | 147 | 0.3% |
| letta_code | 125 | 0.2% |
| amp | 55 | 0.1% |
| jules | 35 | 0.1% |
| gru | 23 | 0.0% |
| sourcery | 19 | 0.0% |
| langchain_open_swe | 18 | 0.0% |
| coderabbit | 13 | 0.0% |
| aider | 9 | 0.0% |
| openhands | 6 | 0.0% |
| crush | 4 | 0.0% |
| codegen | 3 | 0.0% |
| factory_droid | 3 | 0.0% |
| sentry_seer | 3 | 0.0% |
| windsurf | 3 | 0.0% |
| ona | 1 | 0.0% |
| opencode | 1 | 0.0% |

### Dataset B (human-authored, contemporary) -- 68,346 fixtures

**Continuous metrics**

| Metric | n | mean | median | min | max | stdev |
|---|---|---|---|---|---|---|
| loc | 68,346 | 9.27 | 5.00 | 1 | 960 | 13.53 |
| cyclomatic_complexity | 68,346 | 1.24 | 1.00 | 1 | 44 | 0.87 |
| max_nesting_depth | 68,346 | 1.23 | 1.00 | 1 | 11 | 0.54 |
| num_parameters | 68,346 | 0.28 | 0.00 | 0 | 16 | 0.65 |
| num_objects_instantiated | 68,346 | 0.81 | 0.00 | 0 | 127 | 1.76 |
| num_external_calls | 68,346 | 0.14 | 0.00 | 0 | 20 | 0.66 |

**scope distribution**

| Value | Count | % |
|---|---|---|
| per_test | 56,736 | 83.0% |
| per_class | 7,947 | 11.6% |
| per_module | 2,515 | 3.7% |
| global | 1,148 | 1.7% |

**fixture_type distribution**

| Value | Count | % |
|---|---|---|
| pytest_decorator | 32,780 | 48.0% |
| unittest_setup | 7,425 | 10.9% |
| before_each | 6,474 | 9.5% |
| junit5_before_each | 4,335 | 6.3% |
| after_each | 4,066 | 5.9% |
| junit5_after_each | 1,913 | 2.8% |
| pytest_class_method | 1,910 | 2.8% |
| testng_before_class | 1,275 | 1.9% |
| junit5_before_all | 1,121 | 1.6% |
| testng_after_class | 1,093 | 1.6% |
| before_all | 1,063 | 1.6% |
| testng_data_provider | 784 | 1.1% |
| junit4_before | 770 | 1.1% |
| junit5_after_all | 567 | 0.8% |
| mocha_before | 553 | 0.8% |
| after_all | 518 | 0.8% |
| junit4_after | 416 | 0.6% |
| mocha_after | 383 | 0.6% |
| junit_rule | 356 | 0.5% |
| testng_before_method | 259 | 0.4% |
| testng_after_method | 109 | 0.2% |
| junit_class_rule | 104 | 0.2% |
| junit3_setup | 69 | 0.1% |
| junit3_teardown | 3 | 0.0% |

**commit_type distribution**

| Value | Count | % |
|---|---|---|
| none | 38,559 | 56.4% |
| feat | 17,912 | 26.2% |
| fix | 5,156 | 7.5% |
| test | 4,143 | 6.1% |
| chore | 1,364 | 2.0% |
| refactor | 613 | 0.9% |
| other | 469 | 0.7% |
| docs | 129 | 0.2% |
| style | 1 | 0.0% |

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

8,302/68,346 fixtures (12.15%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 14,571 | 1,752 | 12.02% | typescript=837, python=530, javascript=385 |
| javascript | 7,704 | 1,876 | 24.35% | typescript=1,618, python=188, java=70 |
| python | 46,071 | 4,674 | 10.15% | typescript=3,930, javascript=459, java=285 |

**agent_type distribution** (descriptive only, not compared against other datasets -- see load_dataset_metrics()'s docstring for why)

| Value | Count | % |
|---|---|---|
| human | 68,346 | 100.0% |

### Dataset C (human-authored, pre-LLM) -- 166,070 fixtures

**Continuous metrics**

| Metric | n | mean | median | min | max | stdev |
|---|---|---|---|---|---|---|
| loc | 166,070 | 7.94 | 5.00 | 1 | 2405 | 16.57 |
| cyclomatic_complexity | 166,070 | 1.14 | 1.00 | 1 | 40 | 0.63 |
| max_nesting_depth | 166,070 | 1.11 | 1.00 | 1 | 12 | 0.39 |
| num_parameters | 166,070 | 0.11 | 0.00 | 0 | 29 | 0.50 |
| num_objects_instantiated | 166,070 | 0.54 | 0.00 | 0 | 123 | 1.66 |
| num_external_calls | 166,070 | 0.07 | 0.00 | 0 | 164 | 0.70 |

**scope distribution**

| Value | Count | % |
|---|---|---|
| per_test | 137,639 | 82.9% |
| per_class | 24,439 | 14.7% |
| per_module | 2,803 | 1.7% |
| global | 1,189 | 0.7% |

**fixture_type distribution**

| Value | Count | % |
|---|---|---|
| before_each | 41,712 | 25.1% |
| unittest_setup | 24,238 | 14.6% |
| pytest_decorator | 15,964 | 9.6% |
| after_each | 14,159 | 8.5% |
| junit4_before | 13,080 | 7.9% |
| mocha_before | 8,989 | 5.4% |
| testng_before_class | 6,628 | 4.0% |
| junit_rule | 5,616 | 3.4% |
| before_all | 4,987 | 3.0% |
| junit4_after | 4,951 | 3.0% |
| mocha_after | 4,691 | 2.8% |
| testng_after_class | 3,318 | 2.0% |
| testng_data_provider | 3,196 | 1.9% |
| junit5_before_each | 2,880 | 1.7% |
| after_all | 2,829 | 1.7% |
| junit_class_rule | 1,343 | 0.8% |
| junit5_after_each | 1,262 | 0.8% |
| testng_before_method | 1,172 | 0.7% |
| junit5_before_all | 1,168 | 0.7% |
| pytest_class_method | 1,049 | 0.6% |
| junit3_setup | 1,005 | 0.6% |
| junit5_after_all | 685 | 0.4% |
| junit3_teardown | 581 | 0.3% |
| testng_after_method | 567 | 0.3% |

**commit_type distribution**

| Value | Count | % |
|---|---|---|
| _(no data)_ | -- | -- |

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

0/166,070 fixtures (0.00%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 47,452 | 0 | 0.00% | -- |
| javascript | 30,032 | 0 | 0.00% | -- |
| python | 41,251 | 0 | 0.00% | -- |
| typescript | 47,335 | 0 | 0.00% | -- |

**agent_type distribution** (descriptive only, not compared against other datasets -- see load_dataset_metrics()'s docstring for why)

| Value | Count | % |
|---|---|---|
| human_pre2022 | 166,070 | 100.0% |

## A vs B: Dataset A (agent-authored) vs Dataset B (human-authored, contemporary)

**Continuous metrics (Mann-Whitney U, two-sided)** -- p-values shrink with sample size alone; Cliff's delta is what says how big the difference actually is (thresholds: negligible <0.147, small <0.33, medium <0.474, else large; positive means the comparison dataset tends to have larger values than A, negative means A tends to have larger values). BH-FDR corrects for running all 6 of these tests together (see apply_fdr_correction()'s docstring).

| Metric | A mean | A median | B mean | B median | U | p-value | significant (p<0.05) | Cliff's delta (effect size) | BH-FDR adjusted p (sig?) |
|---|---|---|---|---|---|---|---|---|---|
| loc | 7.61 | 4.00 | 9.27 | 5.00 | 1943468464.0 | 7.466e-308 | yes | 0.126 (negligible) | 1.493e-307 (yes) |
| cyclomatic_complexity | 1.20 | 1.00 | 1.24 | 1.00 | 1744116620.0 | 7.259e-08 | yes | 0.011 (negligible) | 7.259e-08 (yes) |
| max_nesting_depth | 1.19 | 1.00 | 1.23 | 1.00 | 1772814502.5 | 1.894e-34 | yes | 0.027 (negligible) | 2.273e-34 (yes) |
| num_parameters | 0.15 | 0.00 | 0.28 | 0.00 | 1902016545.5 | 0 | yes | 0.102 (negligible) | 0 (yes) |
| num_objects_instantiated | 0.41 | 0.00 | 0.81 | 0.00 | 2025536218.0 | 0 | yes | 0.174 (small) | 0 (yes) |
| num_external_calls | 0.06 | 0.00 | 0.14 | 0.00 | 1800891947.5 | 4.878e-198 | yes | 0.044 (negligible) | 7.317e-198 (yes) |

**Categorical metrics (chi-square)** -- Cramer's V thresholds: negligible <0.1, small <0.3, medium <0.5, else large. BH-FDR corrects for running all 3 of these tests together.

| Metric | chi2 | dof | p-value | significant (p<0.05) | Cramer's V (effect size) | BH-FDR adjusted p (sig?) |
|---|---|---|---|---|---|---|
| scope | 928.2 | 3 | 6.686e-201 | yes | 0.088 (negligible) | 6.686e-201 (yes) |
| fixture_type | 32847.2 | 23 | 0 | yes | 0.526 (large) | 0 (yes) |
| commit_type | 11781.5 | 8 | 0 | yes | 0.315 (medium) | 0 (yes) |

**fixture_type, stratified by language (chi-square per language)** -- the pooled fixture_type comparison above can look significant purely because Dataset A (agent-authored) and Dataset B (human-authored, contemporary) have different language mixes (see this module's docstring); this checks whether the mechanism difference holds within each shared language.

| Language | chi2 | dof | p-value | significant (p<0.05) | Cramer's V (effect size) | BH-FDR adjusted p (sig?) |
|---|---|---|---|---|---|---|
| java | 397.8 | 14 | 3.649e-76 | yes | 0.166 (small) | 1.46e-75 (yes) |
| javascript | 216.1 | 5 | 1.004e-44 | yes | 0.142 (small) | 2.008e-44 (yes) |
| python | 166.2 | 2 | 8.154e-37 | yes | 0.054 (negligible) | 1.087e-36 (yes) |
| typescript | 64.0 | 5 | 1.788e-12 | yes | 0.041 (negligible) | 1.788e-12 (yes) |

## A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)

**Continuous metrics (Mann-Whitney U, two-sided)** -- p-values shrink with sample size alone; Cliff's delta is what says how big the difference actually is (thresholds: negligible <0.147, small <0.33, medium <0.474, else large; positive means the comparison dataset tends to have larger values than A, negative means A tends to have larger values). BH-FDR corrects for running all 6 of these tests together (see apply_fdr_correction()'s docstring).

| Metric | A mean | A median | C mean | C median | U | p-value | significant (p<0.05) | Cliff's delta (effect size) | BH-FDR adjusted p (sig?) |
|---|---|---|---|---|---|---|---|---|---|
| loc | 7.61 | 4.00 | 7.94 | 5.00 | 4235688665.0 | 0.0004896 | yes | 0.010 (negligible) | 0.0004896 (yes) |
| cyclomatic_complexity | 1.20 | 1.00 | 1.14 | 1.00 | 4018148227.5 | 8.23e-175 | yes | -0.042 (negligible) | 2.469e-174 (yes) |
| max_nesting_depth | 1.19 | 1.00 | 1.11 | 1.00 | 3918640041.0 | 0 | yes | -0.065 (negligible) | 0 (yes) |
| num_parameters | 0.15 | 0.00 | 0.11 | 0.00 | 4033503905.5 | 2.307e-173 | yes | -0.038 (negligible) | 4.614e-173 (yes) |
| num_objects_instantiated | 0.41 | 0.00 | 0.54 | 0.00 | 4337626946.5 | 3.179e-52 | yes | 0.034 (negligible) | 4.769e-52 (yes) |
| num_external_calls | 0.06 | 0.00 | 0.07 | 0.00 | 4214645378.5 | 9.3e-07 | yes | 0.005 (negligible) | 1.116e-06 (yes) |

**Categorical metrics (chi-square)** -- Cramer's V thresholds: negligible <0.1, small <0.3, medium <0.5, else large. BH-FDR corrects for running all 3 of these tests together.

| Metric | chi2 | dof | p-value | significant (p<0.05) | Cramer's V (effect size) | BH-FDR adjusted p (sig?) |
|---|---|---|---|---|---|---|
| scope | 544.3 | 3 | 1.21e-117 | yes | 0.050 (negligible) | 1.21e-117 (yes) |
| fixture_type | 32039.6 | 23 | 0 | yes | 0.385 (medium) | 0 (yes) |
| commit_type | -- | -- | -- | _insufficient data_ | -- | -- |

**fixture_type, stratified by language (chi-square per language)** -- the pooled fixture_type comparison above can look significant purely because Dataset A (agent-authored) and Dataset C (human-authored, pre-LLM) have different language mixes (see this module's docstring); this checks whether the mechanism difference holds within each shared language.

| Language | chi2 | dof | p-value | significant (p<0.05) | Cramer's V (effect size) | BH-FDR adjusted p (sig?) |
|---|---|---|---|---|---|---|
| java | 3692.1 | 14 | 0 | yes | 0.275 (small) | 0 (yes) |
| javascript | 265.1 | 5 | 3.088e-55 | yes | 0.088 (negligible) | 3.088e-55 (yes) |
| python | 8219.8 | 2 | 0 | yes | 0.386 (medium) | 0 (yes) |
| typescript | 6884.0 | 5 | 0 | yes | 0.296 (small) | 0 (yes) |

## Repo-level aggregates

The comparisons above treat every fixture as an independent observation, but fixtures cluster within repos (shared authorship conventions, framework choices, project style) -- a handful of unusually prolific repos can dominate a fixture-level result. This section re-runs the continuous metrics with one *mean-per-repo* value per repo instead, so each repo counts once regardless of how many fixtures it contributed. A finding that holds in both views is on firmer ground than one that only shows up fixture-level.

### A vs B: Dataset A (agent-authored) vs Dataset B (human-authored, contemporary)

| Metric | A mean | A median | B mean | B median | U | p-value | significant (p<0.05) | Cliff's delta (effect size) | BH-FDR adjusted p (sig?) |
|---|---|---|---|---|---|---|---|---|---|
| loc | 7.83 | 6.37 | 9.01 | 7.80 | 979110.0 | 4.528e-17 | yes | 0.192 (small) | 5.433e-17 (yes) |
| cyclomatic_complexity | 1.22 | 1.03 | 1.28 | 1.14 | 965260.0 | 2.253e-15 | yes | 0.175 (small) | 2.253e-15 (yes) |
| max_nesting_depth | 1.20 | 1.06 | 1.26 | 1.19 | 985449.5 | 3.477e-19 | yes | 0.200 (small) | 5.216e-19 (yes) |
| num_parameters | 0.17 | 0.00 | 0.29 | 0.12 | 1037199.0 | 5.353e-36 | yes | 0.263 (small) | 1.071e-35 (yes) |
| num_objects_instantiated | 0.53 | 0.20 | 0.80 | 0.67 | 1073326.5 | 9.161e-42 | yes | 0.307 (small) | 2.748e-41 (yes) |
| num_external_calls | 0.09 | 0.00 | 0.17 | 0.01 | 1045216.5 | 5.386e-43 | yes | 0.272 (small) | 3.231e-42 (yes) |

### A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)

| Metric | A mean | A median | C mean | C median | U | p-value | significant (p<0.05) | Cliff's delta (effect size) | BH-FDR adjusted p (sig?) |
|---|---|---|---|---|---|---|---|---|---|
| loc | 7.83 | 6.37 | 8.04 | 6.09 | 1994963.0 | 0.02116 | yes | -0.043 (negligible) | 0.02116 (yes) |
| cyclomatic_complexity | 1.22 | 1.03 | 1.19 | 1.00 | 1968357.0 | 0.001445 | yes | -0.056 (negligible) | 0.001734 (yes) |
| max_nesting_depth | 1.20 | 1.06 | 1.15 | 1.01 | 1895499.0 | 2.907e-07 | yes | -0.091 (negligible) | 1.744e-06 (yes) |
| num_parameters | 0.17 | 0.00 | 0.14 | 0.00 | 1972343.0 | 0.0004522 | yes | -0.054 (negligible) | 0.0006783 (yes) |
| num_objects_instantiated | 0.53 | 0.20 | 0.62 | 0.30 | 2231295.5 | 0.0001421 | yes | 0.070 (negligible) | 0.0002841 (yes) |
| num_external_calls | 0.09 | 0.00 | 0.12 | 0.00 | 2211749.5 | 5.014e-05 | yes | 0.061 (negligible) | 0.0001504 (yes) |
