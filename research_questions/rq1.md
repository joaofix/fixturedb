# RQ1 -- General Metrics Overview

> How do agent-generated and human-written fixtures compare across structural metrics?

Generated: 2026-08-16 01:51:12 UTC

See [docs/research-questions.md](../docs/research-questions.md) for the full RQ1 definition.

## Per-dataset summary

### Dataset A (agent-authored) -- 39,088 fixtures

**Continuous metrics** (repo-level: one mean per repo, not one value per fixture)

| Metric | n | median | mean | min | max | stdev |
|---|---|---|---|---|---|---|
| loc | 1,044 | 6.50 | 7.84 | 1 | 82 | 5.91 |
| cyclomatic_complexity | 1,044 | 1.06 | 1.24 | 1 | 6 | 0.48 |
| max_nesting_depth | 1,044 | 1.09 | 1.22 | 1 | 4 | 0.34 |
| num_parameters | 1,044 | 0.00 | 0.21 | 0 | 3 | 0.40 |

**scope distribution**

| Value | Count | % |
|---|---|---|
| per_test | 34,062 | 87.1% |
| per_class | 4,150 | 10.6% |
| per_module | 656 | 1.7% |
| global | 220 | 0.6% |

**fixture_type distribution**

| Value | Count | % |
|---|---|---|
| before_each | 13,415 | 34.3% |
| pytest_decorator | 8,901 | 22.8% |
| after_each | 8,288 | 21.2% |
| unittest_setup | 2,126 | 5.4% |
| before_all | 1,941 | 5.0% |
| after_all | 1,732 | 4.4% |
| pytest_class_method | 685 | 1.8% |
| mocha_before | 435 | 1.1% |
| junit5_before_each | 432 | 1.1% |
| mocha_after | 356 | 0.9% |
| junit5_after_each | 173 | 0.4% |
| junit5_before_all | 145 | 0.4% |
| junit4_before | 115 | 0.3% |
| junit_rule | 98 | 0.3% |
| junit5_after_all | 89 | 0.2% |
| testng_before_method | 40 | 0.1% |
| junit4_after | 34 | 0.1% |
| testng_before_class | 30 | 0.1% |
| junit_class_rule | 16 | 0.0% |
| testng_after_method | 15 | 0.0% |
| testng_after_class | 14 | 0.0% |
| testng_data_provider | 7 | 0.0% |
| junit3_setup | 1 | 0.0% |

**commit_type distribution**

| Value | Count | % |
|---|---|---|
| feat | 17,813 | 45.6% |
| none | 10,318 | 26.4% |
| fix | 5,278 | 13.5% |
| test | 4,087 | 10.5% |
| chore | 671 | 1.7% |
| refactor | 603 | 1.5% |
| other | 244 | 0.6% |
| docs | 74 | 0.2% |

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

2,559/39,088 fixtures (6.55%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 1,320 | 198 | 15.00% | typescript=122, python=75, javascript=1 |
| javascript | 1,684 | 332 | 19.71% | typescript=190, python=119, java=23 |
| python | 11,798 | 614 | 5.20% | typescript=409, javascript=149, java=56 |
| typescript | 24,286 | 1,415 | 5.83% | javascript=1,073, python=334, java=8 |

**agent_type distribution** (descriptive only, not compared against other datasets -- see load_dataset_metrics()'s docstring for why)

| Value | Count | % |
|---|---|---|
| claude | 33,473 | 85.6% |
| copilot | 2,496 | 6.4% |
| cursor | 1,576 | 4.0% |
| paperclip | 318 | 0.8% |
| devin | 317 | 0.8% |
| codex | 271 | 0.7% |
| qwen_coder | 198 | 0.5% |
| gemini | 185 | 0.5% |
| letta_code | 144 | 0.4% |
| jules | 33 | 0.1% |
| amp | 28 | 0.1% |
| langchain_open_swe | 17 | 0.0% |
| coderabbit | 6 | 0.0% |
| openhands | 6 | 0.0% |
| aider | 5 | 0.0% |
| sourcery | 5 | 0.0% |
| crush | 4 | 0.0% |
| codegen | 3 | 0.0% |
| factory_droid | 3 | 0.0% |

### Dataset C (human-authored, pre-LLM) -- 211,384 fixtures

**Continuous metrics** (repo-level: one mean per repo, not one value per fixture)

| Metric | n | median | mean | min | max | stdev |
|---|---|---|---|---|---|---|
| loc | 3,228 | 6.25 | 8.09 | 1 | 534 | 11.98 |
| cyclomatic_complexity | 3,228 | 1.02 | 1.19 | 1 | 14 | 0.51 |
| max_nesting_depth | 3,228 | 1.02 | 1.15 | 1 | 4 | 0.28 |
| num_parameters | 3,244 | 0.00 | 0.13 | 0 | 3 | 0.32 |

**scope distribution**

| Value | Count | % |
|---|---|---|
| per_test | 172,667 | 81.7% |
| per_class | 34,581 | 16.4% |
| per_module | 2,929 | 1.4% |
| global | 1,207 | 0.6% |

**fixture_type distribution**

| Value | Count | % |
|---|---|---|
| before_each | 51,170 | 24.2% |
| unittest_setup | 22,971 | 10.9% |
| testng_data_provider | 17,041 | 8.1% |
| after_each | 16,777 | 7.9% |
| junit4_before | 16,137 | 7.6% |
| pytest_decorator | 15,665 | 7.4% |
| mocha_before | 10,702 | 5.1% |
| testng_before_class | 10,361 | 4.9% |
| before_all | 7,345 | 3.5% |
| junit_rule | 6,982 | 3.3% |
| junit4_after | 6,221 | 2.9% |
| testng_after_class | 5,876 | 2.8% |
| mocha_after | 5,288 | 2.5% |
| after_all | 3,883 | 1.8% |
| junit5_before_each | 3,503 | 1.7% |
| testng_before_method | 2,031 | 1.0% |
| junit_class_rule | 1,706 | 0.8% |
| junit5_before_all | 1,644 | 0.8% |
| junit5_after_each | 1,424 | 0.7% |
| junit3_setup | 1,218 | 0.6% |
| pytest_class_method | 1,026 | 0.5% |
| junit5_after_all | 883 | 0.4% |
| testng_after_method | 877 | 0.4% |
| junit3_teardown | 653 | 0.3% |

**commit_type distribution**

| Value | Count | % |
|---|---|---|
| _(no data)_ | -- | -- |

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

18,660/211,384 fixtures (8.83%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 79,738 | 4,044 | 5.07% | python=1,818, typescript=1,164, javascript=1,062 |
| javascript | 30,836 | 2,862 | 9.28% | typescript=2,150, python=388, java=324 |
| python | 38,962 | 1,895 | 4.86% | typescript=865, javascript=689, java=341 |
| typescript | 61,848 | 9,859 | 15.94% | javascript=9,272, python=389, java=198 |

**agent_type distribution** (descriptive only, not compared against other datasets -- see load_dataset_metrics()'s docstring for why)

| Value | Count | % |
|---|---|---|
| human_pre2022 | 211,384 | 100.0% |

## A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)

**Continuous metrics (Mann-Whitney U on repo-level values, two-sided)** -- one mean value per repo (per language, for the per-language rows), not per fixture, so fixtures clustering within a repo can't inflate the result. Effect size is Cliff's delta (thresholds: negligible <0.147, small <0.33, medium <0.474, else large; positive means the comparison dataset tends to have larger values than A, negative means A tends to have larger values). The Overall row is a single pooled test, not BH-corrected; each metric's per-language rows are BH-FDR corrected against each other only (one family per metric, 4 languages).

**Floor-binding check (descriptive only -- not a comparative test)** -- `num_parameters` was dropped from Mann-Whitney testing (see this module's docstring) because it floors heavily in both datasets; this documents exactly how heavily, transparently, instead of silently omitting it.

| Metric | Floor value | Dataset A (agent-authored) at floor | Dataset C (human-authored, pre-LLM) at floor |
|---|---|---|---|
| num_parameters | 0 | 89.0% | 94.2% |

### loc

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 1044 | 3228 | U=1626625.5 | -0.035 | negligible | 0.092 | -- |
| java | 83 | 676 | U=28126.5 | 0.003 | negligible | 0.970 | 0.970 |
| javascript | 88 | 834 | U=34450.5 | -0.061 | negligible | 0.345 | 0.459 |
| python | 490 | 1155 | U=244615.5 | -0.136 | negligible | <.001 | <.001 |
| typescript | 502 | 859 | U=223217.0 | 0.035 | negligible | 0.277 | 0.459 |

### cyclomatic_complexity

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 1044 | 3228 | U=1537406.5 | -0.088 | negligible | <.001 | -- |
| java | 83 | 676 | U=28824.0 | 0.027 | negligible | 0.671 | 0.671 |
| javascript | 88 | 834 | U=29070.0 | -0.208 | small | <.001 | <.001 |
| python | 490 | 1155 | U=305770.5 | 0.081 | negligible | 0.008 | 0.010 |
| typescript | 502 | 859 | U=160497.5 | -0.256 | small | <.001 | <.001 |

### max_nesting_depth

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 1044 | 3228 | U=1459357.0 | -0.134 | negligible | <.001 | -- |
| java | 83 | 676 | U=29189.5 | 0.040 | negligible | 0.531 | 0.677 |
| javascript | 88 | 834 | U=28564.0 | -0.222 | small | <.001 | <.001 |
| python | 490 | 1155 | U=279388.5 | -0.013 | negligible | 0.677 | 0.677 |
| typescript | 502 | 859 | U=153737.0 | -0.287 | small | <.001 | <.001 |

**Categorical metrics (chi-square)** -- Effect size is Cramer's V (thresholds: negligible <0.1, small <0.3, medium <0.5, else large). Same Overall-uncorrected / per-language-family-corrected convention as the continuous metrics above. `scope`/`fixture_type` each have a per-language family; `commit_type` doesn't (renders Overall-only).

### scope

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 1044 | 3244 | chi2=842.3 (df=3) | 0.058 | negligible | <.001 | -- |
| java | 84 | 702 | chi2=3.4 (df=1) | 0.007 | negligible | 0.064 | 0.064 |
| javascript | 88 | 834 | chi2=100.0 (df=1) | 0.049 | negligible | <.001 | <.001 |
| python | 490 | 1155 | chi2=659.1 (df=3) | 0.113 | small | <.001 | <.001 |
| typescript | 502 | 859 | chi2=130.6 (df=1) | 0.040 | negligible | <.001 | <.001 |

### fixture_type

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 1044 | 3244 | chi2=31704.2 (df=23) | 0.356 | medium | <.001 | -- |
| java | 84 | 702 | chi2=4634.1 (df=14) | 0.244 | small | <.001 | <.001 |
| javascript | 88 | 834 | chi2=251.0 (df=5) | 0.078 | negligible | <.001 | <.001 |
| python | 490 | 1155 | chi2=5735.1 (df=2) | 0.334 | medium | <.001 | <.001 |
| typescript | 502 | 859 | chi2=5568.5 (df=5) | 0.264 | small | <.001 | <.001 |

> **`fixture_type`'s result above is not used in the paper.** It's a pooled/per-language fixture-level chi-square, which treats fixtures clustered within a repo as independent observations and inflates both chi2 and Cramer's V (see [Limitations § Categorical Pseudo-Replication](../docs/reference/limitations.md#categorical-pseudo-replication)). The paper reports the repo-level `fixture_type` proportion test in "Repo-level aggregates" below instead. `scope`/`commit_type` above are unaffected and are used as-is.

### commit_type

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 1044 | 0 | -- | -- | _insufficient data_ | -- | -- |

## Repo-level aggregates

fixture_type re-tested with one *proportion-per-repo* value per category instead of pooled/per-language fixture-level chi-square, so each repo counts once regardless of how many fixtures it contributed -- see compare_categorical_repo_level()'s docstring in _shared.py. (The continuous metrics above are already repo-level throughout, including their per-language rows, so they don't need a separate view here.)

### A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)

**fixture_type, repo-level (Mann-Whitney U on per-repo category proportions, two-sided)** -- the fixture_type chi-square table above treats every fixture as an independent observation, but fixtures cluster within repos (shared framework choice, project convention), which inflates chi2 and partially corrupts Cramer's V. This instead compares, per repo, what fraction of its fixtures are each fixture_type -- so each repo counts once regardless of how many fixtures it contributed. **This is the `fixture_type` result reported in the paper.**

| Category | A median | A mean | C median | C mean | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|---|---|---|
| after_all | 0.0% | 2.3% | 0.0% | 2.4% | 1044 | 3244 | U=1645745.0 | -0.028 | negligible | 0.021 | 0.026 |
| after_each | 0.0% | 16.2% | 0.0% | 8.1% | 1044 | 3244 | U=1400258.5 | -0.173 | small | <.001 | <.001 |
| before_all | 0.0% | 3.6% | 0.0% | 4.9% | 1044 | 3244 | U=1677977.5 | -0.009 | negligible | 0.505 | 0.551 |
| before_each | 0.0% | 24.5% | 0.0% | 23.4% | 1044 | 3244 | U=1621170.0 | -0.043 | negligible | 0.020 | 0.026 |
| junit3_setup | 0.0% | 0.1% | 0.0% | 0.4% | 1044 | 3244 | U=1715736.5 | 0.013 | negligible | <.001 | <.001 |
| junit3_teardown | 0.0% | 0.0% | 0.0% | 0.1% | 1044 | 3244 | U=1708506.0 | 0.009 | negligible | 0.002 | 0.003 |
| junit4_after | 0.0% | 0.3% | 0.0% | 1.9% | 1044 | 3244 | U=1846459.0 | 0.090 | negligible | <.001 | <.001 |
| junit4_before | 0.0% | 1.1% | 0.0% | 7.3% | 1044 | 3244 | U=1907574.0 | 0.126 | negligible | <.001 | <.001 |
| junit5_after_all | 0.0% | 0.3% | 0.0% | 0.4% | 1044 | 3244 | U=1715267.0 | 0.013 | negligible | 0.020 | 0.026 |
| junit5_after_each | 0.0% | 1.0% | 0.0% | 0.6% | 1044 | 3244 | U=1700085.0 | 0.004 | negligible | 0.554 | 0.578 |
| junit5_before_all | 0.0% | 0.5% | 0.0% | 1.1% | 1044 | 3244 | U=1726650.5 | 0.020 | negligible | 0.003 | 0.005 |
| junit5_before_each | 0.0% | 3.0% | 0.0% | 2.2% | 1044 | 3244 | U=1697061.0 | 0.002 | negligible | 0.779 | 0.779 |
| junit_class_rule | 0.0% | 0.0% | 0.0% | 0.2% | 1044 | 3244 | U=1721898.0 | 0.017 | negligible | <.001 | <.001 |
| junit_rule | 0.0% | 0.2% | 0.0% | 2.3% | 1044 | 3244 | U=1834904.0 | 0.084 | negligible | <.001 | <.001 |
| mocha_after | 0.0% | 1.0% | 0.0% | 2.1% | 1044 | 3244 | U=1795608.5 | 0.060 | negligible | <.001 | <.001 |
| mocha_before | 0.0% | 1.3% | 0.0% | 4.6% | 1044 | 3244 | U=1835857.5 | 0.084 | negligible | <.001 | <.001 |
| pytest_class_method | 0.0% | 1.8% | 0.0% | 1.1% | 1044 | 3244 | U=1610337.5 | -0.049 | negligible | <.001 | <.001 |
| pytest_decorator | 0.0% | 34.9% | 0.0% | 15.6% | 1044 | 3244 | U=1332664.5 | -0.213 | small | <.001 | <.001 |
| testng_after_class | 0.0% | 0.1% | 0.0% | 0.8% | 1044 | 3244 | U=1795392.5 | 0.060 | negligible | <.001 | <.001 |
| testng_after_method | 0.0% | 0.1% | 0.0% | 0.1% | 1044 | 3244 | U=1704650.5 | 0.007 | negligible | 0.035 | 0.040 |
| testng_before_class | 0.0% | 0.3% | 0.0% | 2.1% | 1044 | 3244 | U=1827318.5 | 0.079 | negligible | <.001 | <.001 |
| testng_before_method | 0.0% | 0.1% | 0.0% | 0.2% | 1044 | 3244 | U=1714027.5 | 0.012 | negligible | 0.002 | 0.003 |
| testng_data_provider | 0.0% | 0.1% | 0.0% | 0.5% | 1044 | 3244 | U=1709403.0 | 0.009 | negligible | 0.008 | 0.011 |
| unittest_setup | 0.0% | 7.3% | 0.0% | 17.4% | 1044 | 3244 | U=1866541.0 | 0.102 | negligible | <.001 | <.001 |
