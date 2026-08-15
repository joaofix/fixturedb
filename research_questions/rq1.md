# RQ1 -- General Metrics Overview

> How do agent-generated and human-written fixtures compare across structural metrics?

Generated: 2026-08-14 22:42:15 UTC

See [docs/research-questions.md](../docs/research-questions.md) for the full RQ1 definition.

## Per-dataset summary

### Dataset A (agent-authored) -- 39,088 fixtures

**Continuous metrics** (repo-level: one mean per repo, not one value per fixture)

| Metric | n | median | mean | min | max | stdev |
|---|---|---|---|---|---|---|
| loc | 1,044 | 6.50 | 7.82 | 1 | 82 | 5.91 |
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

### Dataset C (human-authored, pre-LLM) -- 39,377 fixtures

**Continuous metrics** (repo-level: one mean per repo, not one value per fixture)

| Metric | n | median | mean | min | max | stdev |
|---|---|---|---|---|---|---|
| loc | 851 | 6.28 | 8.22 | 1 | 161 | 8.59 |
| cyclomatic_complexity | 851 | 1.04 | 1.24 | 1 | 9 | 0.61 |
| max_nesting_depth | 851 | 1.06 | 1.19 | 1 | 3 | 0.31 |
| num_parameters | 851 | 0.00 | 0.19 | 0 | 3 | 0.39 |

**scope distribution**

| Value | Count | % |
|---|---|---|
| per_test | 33,229 | 84.4% |
| per_class | 4,537 | 11.5% |
| per_module | 1,123 | 2.9% |
| global | 488 | 1.2% |

**fixture_type distribution**

| Value | Count | % |
|---|---|---|
| before_each | 9,166 | 23.3% |
| unittest_setup | 8,843 | 22.5% |
| pytest_decorator | 7,503 | 19.1% |
| after_each | 3,161 | 8.0% |
| mocha_before | 3,099 | 7.9% |
| before_all | 1,569 | 4.0% |
| junit4_before | 1,568 | 4.0% |
| mocha_after | 1,316 | 3.3% |
| after_all | 829 | 2.1% |
| junit4_after | 626 | 1.6% |
| testng_before_class | 534 | 1.4% |
| junit_rule | 430 | 1.1% |
| pytest_class_method | 399 | 1.0% |
| testng_after_class | 167 | 0.4% |
| testng_data_provider | 51 | 0.1% |
| junit5_before_all | 37 | 0.1% |
| junit_class_rule | 22 | 0.1% |
| junit5_after_all | 19 | 0.0% |
| junit3_setup | 12 | 0.0% |
| testng_before_method | 9 | 0.0% |
| junit5_before_each | 8 | 0.0% |
| junit5_after_each | 5 | 0.0% |
| junit3_teardown | 2 | 0.0% |
| testng_after_method | 2 | 0.0% |

**commit_type distribution**

| Value | Count | % |
|---|---|---|
| _(no data)_ | -- | -- |

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

3,900/39,377 fixtures (9.90%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 3,233 | 20 | 0.62% | python=16, javascript=4 |
| javascript | 2,528 | 297 | 11.75% | typescript=125, python=119, java=53 |
| python | 17,111 | 615 | 3.59% | typescript=294, java=188, javascript=133 |
| typescript | 16,505 | 2,968 | 17.98% | javascript=2,816, python=114, java=38 |

**agent_type distribution** (descriptive only, not compared against other datasets -- see load_dataset_metrics()'s docstring for why)

| Value | Count | % |
|---|---|---|
| human_pre2022 | 39,377 | 100.0% |

## A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)

**Continuous metrics (Mann-Whitney U on repo-level values, two-sided)** -- one mean value per repo (per language, for the per-language rows), not per fixture, so fixtures clustering within a repo can't inflate the result. Effect size is Cliff's delta (thresholds: negligible <0.147, small <0.33, medium <0.474, else large; positive means the comparison dataset tends to have larger values than A, negative means A tends to have larger values). The Overall row is a single pooled test, not BH-corrected; each metric's per-language rows are BH-FDR corrected against each other only (one family per metric, 4 languages).

**Floor-binding check (descriptive only -- not a comparative test)** -- `num_parameters` was dropped from Mann-Whitney testing (see this module's docstring) because it floors heavily in both datasets; this documents exactly how heavily, transparently, instead of silently omitting it.

| Metric | Floor value | Dataset A (agent-authored) at floor | Dataset C (human-authored, pre-LLM) at floor |
|---|---|---|---|
| num_parameters | 0 | 89.0% | 88.9% |

### loc

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 1044 | 851 | U=432366.5 | -0.027 | negligible | 0.317 | -- |
| java | 84 | 40 | U=1597.5 | -0.049 | negligible | 0.661 | 0.661 |
| javascript | 88 | 144 | U=6058.0 | -0.044 | negligible | 0.576 | 0.661 |
| python | 490 | 558 | U=117963.5 | -0.137 | negligible | <.001 | <.001 |
| typescript | 502 | 177 | U=48230.0 | 0.086 | negligible | 0.090 | 0.180 |

### cyclomatic_complexity

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 1044 | 851 | U=436087.5 | -0.018 | negligible | 0.473 | -- |
| java | 84 | 40 | U=1514.0 | -0.099 | negligible | 0.337 | 0.337 |
| javascript | 88 | 144 | U=5095.5 | -0.196 | small | 0.006 | 0.011 |
| python | 490 | 558 | U=147613.0 | 0.080 | negligible | 0.021 | 0.028 |
| typescript | 502 | 177 | U=34936.0 | -0.214 | small | <.001 | <.001 |

### max_nesting_depth

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 1044 | 851 | U=422450.0 | -0.049 | negligible | 0.057 | -- |
| java | 84 | 40 | U=1506.5 | -0.103 | negligible | 0.314 | 0.418 |
| javascript | 88 | 144 | U=4938.5 | -0.221 | small | 0.002 | 0.004 |
| python | 490 | 558 | U=135243.0 | -0.011 | negligible | 0.759 | 0.759 |
| typescript | 502 | 177 | U=33345.5 | -0.249 | small | <.001 | <.001 |

**Categorical metrics (chi-square)** -- Effect size is Cramer's V (thresholds: negligible <0.1, small <0.3, medium <0.5, else large). Same Overall-uncorrected / per-language-family-corrected convention as the continuous metrics above. `scope`/`fixture_type` each have a per-language family; `commit_type` doesn't (renders Overall-only).

### scope

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 1044 | 851 | chi2=250.5 (df=3) | 0.057 | negligible | <.001 | -- |
| java | 84 | 40 | chi2=1.9 (df=1) | 0.020 | negligible | 0.163 | 0.163 |
| javascript | 88 | 144 | chi2=337.8 (df=1) | 0.209 | small | <.001 | <.001 |
| python | 490 | 558 | chi2=650.8 (df=3) | 0.151 | small | <.001 | <.001 |
| typescript | 502 | 177 | chi2=256.8 (df=1) | 0.083 | negligible | <.001 | <.001 |

### fixture_type

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 1044 | 851 | chi2=13645.3 (df=23) | 0.417 | medium | <.001 | -- |
| java | 84 | 40 | chi2=2901.2 (df=14) | 0.786 | large | <.001 | <.001 |
| javascript | 88 | 144 | chi2=538.0 (df=5) | 0.263 | small | <.001 | <.001 |
| python | 490 | 558 | chi2=3528.0 (df=2) | 0.352 | medium | <.001 | <.001 |
| typescript | 502 | 177 | chi2=5281.8 (df=5) | 0.375 | medium | <.001 | <.001 |

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
| after_all | 0.0% | 2.3% | 0.0% | 1.8% | 1044 | 851 | U=413934.5 | -0.068 | negligible | <.001 | <.001 |
| after_each | 0.0% | 16.2% | 0.0% | 5.1% | 1044 | 851 | U=330981.0 | -0.255 | small | <.001 | <.001 |
| before_all | 0.0% | 3.6% | 0.0% | 3.8% | 1044 | 851 | U=415280.5 | -0.065 | negligible | <.001 | <.001 |
| before_each | 0.0% | 24.5% | 0.0% | 16.5% | 1044 | 851 | U=371470.0 | -0.164 | small | <.001 | <.001 |
| junit3_setup | 0.0% | 0.1% | 0.0% | 0.1% | 1044 | 851 | U=446404.0 | 0.005 | negligible | 0.058 | 0.100 |
| junit3_teardown | 0.0% | 0.0% | 0.0% | 0.0% | 1044 | 851 | U=444744.0 | 0.001 | negligible | 0.268 | 0.322 |
| junit4_after | 0.0% | 0.3% | 0.0% | 0.3% | 1044 | 851 | U=448542.5 | 0.010 | negligible | 0.102 | 0.153 |
| junit4_before | 0.0% | 1.1% | 0.0% | 1.7% | 1044 | 851 | U=449481.0 | 0.012 | negligible | 0.110 | 0.155 |
| junit5_after_all | 0.0% | 0.3% | 0.0% | 0.1% | 1044 | 851 | U=440528.5 | -0.008 | negligible | 0.093 | 0.149 |
| junit5_after_each | 0.0% | 1.0% | 0.0% | 0.0% | 1044 | 851 | U=431871.0 | -0.028 | negligible | <.001 | <.001 |
| junit5_before_all | 0.0% | 0.5% | 0.0% | 0.4% | 1044 | 851 | U=438534.0 | -0.013 | negligible | 0.024 | 0.044 |
| junit5_before_each | 0.0% | 3.0% | 0.0% | 0.0% | 1044 | 851 | U=424942.0 | -0.043 | negligible | <.001 | <.001 |
| junit_class_rule | 0.0% | 0.0% | 0.0% | 0.0% | 1044 | 851 | U=444511.0 | 0.001 | negligible | 0.802 | 0.802 |
| junit_rule | 0.0% | 0.2% | 0.0% | 0.4% | 1044 | 851 | U=450633.5 | 0.014 | negligible | 0.006 | 0.013 |
| mocha_after | 0.0% | 1.0% | 0.0% | 1.5% | 1044 | 851 | U=463184.5 | 0.043 | negligible | <.001 | <.001 |
| mocha_before | 0.0% | 1.3% | 0.0% | 3.1% | 1044 | 851 | U=468426.0 | 0.054 | negligible | <.001 | <.001 |
| pytest_class_method | 0.0% | 1.8% | 0.0% | 2.0% | 1044 | 851 | U=431584.0 | -0.028 | negligible | 0.009 | 0.018 |
| pytest_decorator | 0.0% | 34.9% | 0.0% | 27.7% | 1044 | 851 | U=411098.5 | -0.075 | negligible | 0.001 | 0.003 |
| testng_after_class | 0.0% | 0.1% | 0.0% | 0.1% | 1044 | 851 | U=446785.0 | 0.006 | negligible | 0.145 | 0.193 |
| testng_after_method | 0.0% | 0.1% | 0.0% | 0.0% | 1044 | 851 | U=443466.0 | -0.002 | negligible | 0.422 | 0.483 |
| testng_before_class | 0.0% | 0.3% | 0.0% | 0.4% | 1044 | 851 | U=447457.5 | 0.007 | negligible | 0.191 | 0.242 |
| testng_before_method | 0.0% | 0.1% | 0.0% | 0.1% | 1044 | 851 | U=445030.5 | 0.002 | negligible | 0.516 | 0.539 |
| testng_data_provider | 0.0% | 0.1% | 0.0% | 0.2% | 1044 | 851 | U=445034.5 | 0.002 | negligible | 0.514 | 0.539 |
| unittest_setup | 0.0% | 7.3% | 0.0% | 34.5% | 1044 | 851 | U=576537.5 | 0.298 | small | <.001 | <.001 |
