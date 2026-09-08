# RQ1 -- General Metrics Overview

> How do agent-generated and human-written fixtures compare across structural metrics?

Generated: 2026-09-08 01:16:48 UTC

See [docs/research-questions.md](../docs/research-questions.md) for the full RQ1 definition.

## Per-dataset summary

### Dataset A (agent-authored) -- 70,623 fixtures

**Continuous metrics -- Paper** (repo-level: one mean per repo, not one value per fixture)

| Metric | n | median | mean | min | max | stdev |
|---|---|---|---|---|---|---|
| loc | 1,687 | 6.32 | 7.62 | 1 | 82 | 5.47 |
| cyclomatic_complexity | 1,687 | 1.05 | 1.22 | 1 | 6 | 0.42 |
| comment_density | 1,687 | 0.01 | 0.02 | 0 | 0 | 0.04 |

**Continuous metrics -- Other (not in the paper)** (repo-level: one mean per repo, not one value per fixture)

| Metric | n | median | mean | min | max | stdev |
|---|---|---|---|---|---|---|
| max_nesting_depth | 1,687 | 1.07 | 1.19 | 1 | 4 | 0.31 |
| num_parameters | 1,687 | 0.00 | 0.18 | 0 | 4 | 0.38 |

**scope distribution**

| Value | Count | % |
|---|---|---|
| per_test | 61,439 | 87.0% |
| per_class | 7,557 | 10.7% |
| per_module | 1,169 | 1.7% |
| global | 458 | 0.6% |

**fixture_type distribution**

| Value | Count | % |
|---|---|---|
| before_each | 24,573 | 34.8% |
| pytest_decorator | 16,706 | 23.7% |
| after_each | 15,194 | 21.5% |
| before_all | 3,599 | 5.1% |
| after_all | 2,969 | 4.2% |
| unittest_setup | 2,900 | 4.1% |
| pytest_class_method | 1,078 | 1.5% |
| junit5_before_each | 788 | 1.1% |
| mocha_before | 736 | 1.0% |
| mocha_after | 607 | 0.9% |
| junit5_after_each | 383 | 0.5% |
| junit5_before_all | 286 | 0.4% |
| junit4_before | 204 | 0.3% |
| junit5_after_all | 154 | 0.2% |
| junit_rule | 135 | 0.2% |
| junit4_after | 106 | 0.2% |
| testng_before_method | 56 | 0.1% |
| junit4_before_class | 52 | 0.1% |
| junit_class_rule | 22 | 0.0% |
| testng_after_method | 21 | 0.0% |
| testng_before_class | 16 | 0.0% |
| junit4_after_class | 14 | 0.0% |
| testng_after_class | 12 | 0.0% |
| testng_data_provider | 9 | 0.0% |
| testng_before_test | 2 | 0.0% |
| junit3_setup | 1 | 0.0% |

**commit_type distribution**

| Value | Count | % |
|---|---|---|
| feat | 30,566 | 43.3% |
| none | 17,780 | 25.2% |
| fix | 11,398 | 16.1% |
| test | 7,853 | 11.1% |
| refactor | 1,186 | 1.7% |
| chore | 1,034 | 1.5% |
| other | 656 | 0.9% |
| docs | 148 | 0.2% |
| style | 2 | 0.0% |

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

5,352/70,623 fixtures (7.58%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 2,265 | 262 | 11.57% | typescript=175, python=86, javascript=1 |
| javascript | 3,975 | 1,210 | 30.44% | typescript=1,017, python=170, java=23 |
| python | 21,078 | 1,253 | 5.94% | typescript=950, javascript=160, java=143 |
| typescript | 43,305 | 2,627 | 6.07% | javascript=1,932, python=603, java=92 |

**agent_type distribution** (descriptive only, not compared against other datasets -- see load_dataset_metrics()'s docstring for why)

| Value | Count | % |
|---|---|---|
| claude | 60,338 | 85.4% |
| copilot | 4,709 | 6.7% |
| cursor | 3,046 | 4.3% |
| devin | 648 | 0.9% |
| codex | 448 | 0.6% |
| paperclip | 356 | 0.5% |
| gemini | 238 | 0.3% |
| qwen_coder | 225 | 0.3% |
| letta_code | 169 | 0.2% |
| gru | 145 | 0.2% |
| jules | 97 | 0.1% |
| amp | 91 | 0.1% |
| langchain_open_swe | 29 | 0.0% |
| sourcery | 19 | 0.0% |
| coderabbit | 14 | 0.0% |
| crush | 12 | 0.0% |
| aider | 9 | 0.0% |
| openhands | 8 | 0.0% |
| mistral_vibe | 4 | 0.0% |
| codegen | 3 | 0.0% |
| factory_droid | 3 | 0.0% |
| junie | 3 | 0.0% |
| sentry_seer | 3 | 0.0% |
| windsurf | 3 | 0.0% |
| generic | 1 | 0.0% |
| ona | 1 | 0.0% |
| opencode | 1 | 0.0% |

### Dataset C (human-authored, pre-LLM) -- 70,623 fixtures

**Continuous metrics -- Paper** (repo-level: one mean per repo, not one value per fixture)

| Metric | n | median | mean | min | max | stdev |
|---|---|---|---|---|---|---|
| loc | 2,483 | 5.88 | 7.87 | 1 | 230 | 9.48 |
| cyclomatic_complexity | 2,483 | 1.00 | 1.19 | 1 | 17 | 0.57 |
| comment_density | 2,483 | 0.00 | 0.02 | 0 | 1 | 0.05 |

**Continuous metrics -- Other (not in the paper)** (repo-level: one mean per repo, not one value per fixture)

| Metric | n | median | mean | min | max | stdev |
|---|---|---|---|---|---|---|
| max_nesting_depth | 2,483 | 1.00 | 1.15 | 1 | 5 | 0.31 |
| num_parameters | 2,494 | 0.00 | 0.14 | 0 | 3 | 0.36 |

**scope distribution**

| Value | Count | % |
|---|---|---|
| per_test | 60,427 | 85.6% |
| per_class | 8,125 | 11.5% |
| per_module | 1,388 | 2.0% |
| global | 683 | 1.0% |

**fixture_type distribution**

| Value | Count | % |
|---|---|---|
| before_each | 26,363 | 37.3% |
| unittest_setup | 12,465 | 17.7% |
| pytest_decorator | 7,747 | 11.0% |
| after_each | 7,724 | 10.9% |
| mocha_before | 5,185 | 7.3% |
| before_all | 3,642 | 5.2% |
| mocha_after | 2,672 | 3.8% |
| after_all | 2,092 | 3.0% |
| pytest_class_method | 472 | 0.7% |
| junit4_before | 457 | 0.6% |
| testng_data_provider | 275 | 0.4% |
| junit_rule | 249 | 0.4% |
| junit4_after | 239 | 0.3% |
| junit4_before_class | 219 | 0.3% |
| junit4_after_class | 126 | 0.2% |
| junit5_before_each | 120 | 0.2% |
| testng_before_class | 96 | 0.1% |
| testng_after_class | 61 | 0.1% |
| testng_before_method | 61 | 0.1% |
| junit_class_rule | 59 | 0.1% |
| junit5_after_each | 57 | 0.1% |
| junit3_setup | 37 | 0.1% |
| junit5_before_all | 35 | 0.0% |
| junit3_teardown | 30 | 0.0% |
| junit5_after_all | 27 | 0.0% |
| testng_after_method | 24 | 0.0% |
| testng_before_test | 21 | 0.0% |
| before_class_ambiguous | 16 | 0.0% |
| after_class_ambiguous | 15 | 0.0% |
| testng_after_test | 15 | 0.0% |
| testng_before_suite | 15 | 0.0% |
| testng_factory | 4 | 0.0% |
| testng_after_suite | 2 | 0.0% |
| testng_after_groups | 1 | 0.0% |

**commit_type distribution**

| Value | Count | % |
|---|---|---|
| _(no data)_ | -- | -- |

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

6,355/70,623 fixtures (9.00%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 4,156 | 1,935 | 46.56% | typescript=990, python=865, javascript=80 |
| javascript | 5,602 | 2,118 | 37.81% | typescript=1,797, python=306, java=15 |
| python | 20,380 | 1,013 | 4.97% | typescript=837, javascript=162, java=14 |
| typescript | 40,485 | 1,289 | 3.18% | javascript=1,132, python=146, java=11 |

**agent_type distribution** (descriptive only, not compared against other datasets -- see load_dataset_metrics()'s docstring for why)

| Value | Count | % |
|---|---|---|
| human_pre2022 | 70,623 | 100.0% |

## A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)

**Paper Metrics -- Continuous** (Mann-Whitney U on repo-level values, two-sided) -- one mean value per repo (per language, for the per-language rows), not per fixture, so fixtures clustering within a repo can't inflate the result. Effect size is Cliff's delta (thresholds: negligible <0.147, small <0.33, medium <0.474, else large; positive means the comparison dataset tends to have larger values than A, negative means A tends to have larger values). The Overall row is a single pooled test, not BH-corrected; each metric's per-language rows are BH-FDR corrected against each other only (one family per metric, 4 languages). These three (`loc`, `cyclomatic_complexity`, `comment_density`) are the only continuous metrics reported in the paper -- see this module's docstring. Each per-language row also reports `A median`/`C median`, `A Q3`/`C Q3` (75th percentile), and `A P90`/`C P90` (90th percentile) -- the same per-repo mean values the Mann-Whitney test itself runs on, alongside (not a replacement for) the effect size and p-value. Q3/P90 exist to explain an effect that reaches significance despite identical medians -- a real difference concentrated in the upper tail, invisible to the median alone.

### loc

| Language | n_A | n_C | A median | C median | A Q3 | C Q3 | A P90 | C P90 | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Overall | 1687 | 2483 | -- | -- | -- | -- | -- | -- | U=1944283.0 | -0.072 | negligible | <.001 | -- |
| java | 125 | 312 | 8.00 | 6.50 | 10.25 | 9.40 | 13.80 | 15.00 | U=16227.0 | -0.168 | small | 0.006 | 0.012 |
| javascript | 143 | 563 | 5.13 | 4.80 | 8.00 | 7.96 | 12.93 | 12.96 | U=37493.5 | -0.069 | negligible | 0.204 | 0.204 |
| python | 678 | 1040 | 8.00 | 6.31 | 11.20 | 9.61 | 16.00 | 15.28 | U=287867.5 | -0.183 | small | <.001 | <.001 |
| typescript | 948 | 758 | 5.33 | 5.65 | 7.24 | 7.81 | 10.33 | 11.42 | U=375687.5 | 0.046 | negligible | 0.105 | 0.140 |

### cyclomatic_complexity

| Language | n_A | n_C | A median | C median | A Q3 | C Q3 | A P90 | C P90 | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Overall | 1687 | 2483 | -- | -- | -- | -- | -- | -- | U=1792069.5 | -0.144 | negligible | <.001 | -- |
| java | 125 | 312 | 1.07 | 1.00 | 1.33 | 1.13 | 1.72 | 1.50 | U=14963.5 | -0.233 | small | <.001 | <.001 |
| javascript | 143 | 563 | 1.00 | 1.00 | 1.33 | 1.00 | 1.67 | 1.21 | U=29511.0 | -0.267 | small | <.001 | <.001 |
| python | 678 | 1040 | 1.08 | 1.08 | 1.34 | 1.36 | 1.75 | 1.89 | U=352334.0 | -0.001 | negligible | 0.981 | 0.981 |
| typescript | 948 | 758 | 1.02 | 1.00 | 1.20 | 1.04 | 1.43 | 1.20 | U=282545.5 | -0.214 | small | <.001 | <.001 |

### comment_density

| Language | n_A | n_C | A median | C median | A Q3 | C Q3 | A P90 | C P90 | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Overall | 1687 | 2483 | -- | -- | -- | -- | -- | -- | U=1833084.0 | -0.125 | negligible | <.001 | -- |
| java | 125 | 312 | 0.00 | 0.00 | 0.04 | 0.00 | 0.08 | 0.05 | U=14481.0 | -0.257 | small | <.001 | <.001 |
| javascript | 143 | 563 | 0.00 | 0.00 | 0.03 | 0.00 | 0.10 | 0.04 | U=30357.0 | -0.246 | small | <.001 | <.001 |
| python | 678 | 1040 | 0.01 | 0.00 | 0.03 | 0.03 | 0.06 | 0.09 | U=349337.5 | -0.009 | negligible | 0.736 | 0.736 |
| typescript | 948 | 758 | 0.01 | 0.00 | 0.02 | 0.01 | 0.05 | 0.05 | U=319504.5 | -0.111 | negligible | <.001 | <.001 |

**Other Extracted Features (Not in the Paper) -- Continuous** (Mann-Whitney U on repo-level values, two-sided) -- one mean value per repo (per language, for the per-language rows), not per fixture, so fixtures clustering within a repo can't inflate the result. Effect size is Cliff's delta (thresholds: negligible <0.147, small <0.33, medium <0.474, else large; positive means the comparison dataset tends to have larger values than A, negative means A tends to have larger values). The Overall row is a single pooled test, not BH-corrected; each metric's per-language rows are BH-FDR corrected against each other only (one family per metric, 4 languages). Computed and tested with the same rigor as the paper metrics above -- `max_nesting_depth` gets an identical Mann-Whitney/per-language table, `num_parameters` gets a descriptive floor-percentage footnote instead (see below for why) -- just not part of the paper's reported RQ1 comparison.

**Floor-binding check (descriptive only -- not a comparative test)** -- `num_parameters` was dropped from Mann-Whitney testing (see this module's docstring) because it floors heavily in both datasets; this documents exactly how heavily, transparently, instead of silently omitting it.

| Metric | Floor value | Dataset A (agent-authored) at floor | Dataset C (human-authored, pre-LLM) at floor |
|---|---|---|---|
| num_parameters | 0 | 88.4% | 92.7% |

### max_nesting_depth

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 1687 | 2483 | U=1749273.0 | -0.165 | small | <.001 | -- |
| java | 125 | 312 | U=15429.5 | -0.209 | small | <.001 | <.001 |
| javascript | 143 | 563 | U=28794.5 | -0.285 | small | <.001 | <.001 |
| python | 678 | 1040 | U=325881.5 | -0.076 | negligible | 0.006 | 0.006 |
| typescript | 948 | 758 | U=271615.5 | -0.244 | small | <.001 | <.001 |

**Categorical metrics (chi-square)** -- Effect size is Cramer's V (thresholds: negligible <0.1, small <0.3, medium <0.5, else large). Same Overall-uncorrected / per-language-family-corrected convention as the continuous metrics above. `scope`/`fixture_type` each have a per-language family; `commit_type` doesn't (renders Overall-only).

### scope

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 1687 | 2494 | chi2=92.1 (df=3) | 0.026 | negligible | <.001 | -- |
| java | 127 | 325 | chi2=63.1 (df=2) | 0.118 | small | <.001 | <.001 |
| javascript | 143 | 563 | chi2=143.0 (df=1) | 0.121 | small | <.001 | <.001 |
| python | 678 | 1040 | chi2=910.8 (df=3) | 0.148 | small | <.001 | <.001 |
| typescript | 948 | 758 | chi2=144.8 (df=1) | 0.041 | negligible | <.001 | <.001 |

### fixture_type

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 1687 | 2494 | chi2=18664.1 (df=33) | 0.364 | medium | <.001 | -- |
| java | 127 | 325 | chi2=1897.1 (df=24) | 0.648 | large | <.001 | <.001 |
| javascript | 143 | 563 | chi2=275.7 (df=5) | 0.168 | small | <.001 | <.001 |
| python | 678 | 1040 | chi2=9473.7 (df=2) | 0.479 | medium | <.001 | <.001 |
| typescript | 948 | 758 | chi2=8279.8 (df=5) | 0.311 | medium | <.001 | <.001 |

> **`fixture_type`'s result above is not used in the paper.** It's a pooled/per-language fixture-level chi-square, which treats fixtures clustered within a repo as independent observations and inflates both chi2 and Cramer's V (see [Limitations § Categorical Pseudo-Replication](../docs/reference/limitations.md#categorical-pseudo-replication)). The paper reports the repo-level `fixture_type` proportion test in "Repo-level aggregates" below instead. `scope`/`commit_type` above are unaffected and are used as-is.

### commit_type

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 1687 | 0 | -- | -- | _insufficient data_ | -- | -- |

## Repo-level aggregates

fixture_type re-tested with one *proportion-per-repo* value per category instead of pooled/per-language fixture-level chi-square, so each repo counts once regardless of how many fixtures it contributed -- see compare_categorical_repo_level()'s docstring in _shared.py. (The continuous metrics above are already repo-level throughout, including their per-language rows, so they don't need a separate view here.)

### A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)

**fixture_type, repo-level (Mann-Whitney U on per-repo category proportions, two-sided)** -- the fixture_type chi-square table above treats every fixture as an independent observation, but fixtures cluster within repos (shared framework choice, project convention), which inflates chi2 and partially corrupts Cramer's V. This instead compares, per repo, what fraction of its fixtures are each fixture_type -- so each repo counts once regardless of how many fixtures it contributed. **This is the `fixture_type` result reported in the paper.**

| Category | A median | A mean | C median | C mean | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|---|---|---|
| after_all | 0.0% | 3.0% | 0.0% | 2.7% | 1687 | 2494 | U=1930063.0 | -0.083 | negligible | <.001 | <.001 |
| after_class_ambiguous | 0.0% | 0.0% | 0.0% | 0.0% | 1687 | 2494 | U=2104532.5 | 0.000 | negligible | 0.411 | 0.418 |
| after_each | 0.0% | 18.4% | 0.0% | 8.6% | 1687 | 2494 | U=1587247.0 | -0.245 | small | <.001 | <.001 |
| before_all | 0.0% | 4.8% | 0.0% | 5.2% | 1687 | 2494 | U=1955760.5 | -0.070 | negligible | <.001 | <.001 |
| before_class_ambiguous | 0.0% | 0.0% | 0.0% | 0.0% | 1687 | 2494 | U=2104532.5 | 0.000 | negligible | 0.411 | 0.418 |
| before_each | 12.5% | 28.1% | 0.0% | 24.7% | 1687 | 2494 | U=1898619.5 | -0.097 | negligible | <.001 | <.001 |
| junit3_setup | 0.0% | 0.1% | 0.0% | 0.1% | 1687 | 2494 | U=2107500.5 | 0.002 | negligible | 0.160 | 0.201 |
| junit3_teardown | 0.0% | 0.0% | 0.0% | 0.2% | 1687 | 2494 | U=2110437.0 | 0.003 | negligible | 0.020 | 0.036 |
| junit4_after | 0.0% | 0.3% | 0.0% | 1.6% | 1687 | 2494 | U=2158692.5 | 0.026 | negligible | <.001 | <.001 |
| junit4_after_class | 0.0% | 0.0% | 0.0% | 0.4% | 1687 | 2494 | U=2137089.0 | 0.016 | negligible | <.001 | <.001 |
| junit4_before | 0.0% | 0.8% | 0.0% | 3.9% | 1687 | 2494 | U=2208954.0 | 0.050 | negligible | <.001 | <.001 |
| junit4_before_class | 0.0% | 0.2% | 0.0% | 1.1% | 1687 | 2494 | U=2143574.5 | 0.019 | negligible | <.001 | <.001 |
| junit5_after_all | 0.0% | 0.3% | 0.0% | 0.2% | 1687 | 2494 | U=2079889.0 | -0.011 | negligible | <.001 | 0.001 |
| junit5_after_each | 0.0% | 1.0% | 0.0% | 0.6% | 1687 | 2494 | U=2059118.5 | -0.021 | negligible | <.001 | <.001 |
| junit5_before_all | 0.0% | 0.5% | 0.0% | 0.5% | 1687 | 2494 | U=2078405.5 | -0.012 | negligible | 0.002 | 0.004 |
| junit5_before_each | 0.0% | 2.8% | 0.0% | 1.2% | 1687 | 2494 | U=2042873.0 | -0.029 | negligible | <.001 | <.001 |
| junit_class_rule | 0.0% | 0.0% | 0.0% | 0.1% | 1687 | 2494 | U=2111771.5 | 0.004 | negligible | 0.056 | 0.090 |
| junit_rule | 0.0% | 0.1% | 0.0% | 1.3% | 1687 | 2494 | U=2151019.5 | 0.022 | negligible | <.001 | <.001 |
| mocha_after | 0.0% | 1.1% | 0.0% | 2.1% | 1687 | 2494 | U=2187373.0 | 0.040 | negligible | <.001 | <.001 |
| mocha_before | 0.0% | 1.3% | 0.0% | 4.4% | 1687 | 2494 | U=2242290.0 | 0.066 | negligible | <.001 | <.001 |
| pytest_class_method | 0.0% | 1.4% | 0.0% | 1.3% | 1687 | 2494 | U=2024475.5 | -0.038 | negligible | <.001 | <.001 |
| pytest_decorator | 0.0% | 29.0% | 0.0% | 18.2% | 1687 | 2494 | U=1843786.5 | -0.124 | negligible | <.001 | <.001 |
| testng_after_class | 0.0% | 0.0% | 0.0% | 0.1% | 1687 | 2494 | U=2112636.5 | 0.004 | negligible | 0.068 | 0.105 |
| testng_after_groups | 0.0% | 0.0% | 0.0% | 0.0% | 1687 | 2494 | U=2104532.5 | 0.000 | negligible | 0.411 | 0.418 |
| testng_after_method | 0.0% | 0.1% | 0.0% | 0.0% | 1687 | 2494 | U=2109645.5 | 0.003 | negligible | 0.158 | 0.201 |
| testng_after_suite | 0.0% | 0.0% | 0.0% | 0.0% | 1687 | 2494 | U=2105376.0 | 0.001 | negligible | 0.245 | 0.297 |
| testng_after_test | 0.0% | 0.0% | 0.0% | 0.0% | 1687 | 2494 | U=2107063.0 | 0.002 | negligible | 0.100 | 0.148 |
| testng_before_class | 0.0% | 0.1% | 0.0% | 0.2% | 1687 | 2494 | U=2108863.0 | 0.002 | negligible | 0.270 | 0.316 |
| testng_before_method | 0.0% | 0.2% | 0.0% | 0.1% | 1687 | 2494 | U=2107577.5 | 0.002 | negligible | 0.418 | 0.418 |
| testng_before_suite | 0.0% | 0.0% | 0.0% | 0.0% | 1687 | 2494 | U=2104532.5 | 0.000 | negligible | 0.411 | 0.418 |
| testng_before_test | 0.0% | 0.0% | 0.0% | 0.1% | 1687 | 2494 | U=2108791.0 | 0.002 | negligible | 0.133 | 0.189 |
| testng_data_provider | 0.0% | 0.1% | 0.0% | 0.3% | 1687 | 2494 | U=2113042.5 | 0.004 | negligible | 0.046 | 0.078 |
| testng_factory | 0.0% | 0.0% | 0.0% | 0.0% | 1687 | 2494 | U=2106219.5 | 0.001 | negligible | 0.154 | 0.201 |
| unittest_setup | 0.0% | 6.4% | 0.0% | 20.9% | 1687 | 2494 | U=2412608.0 | 0.147 | negligible | <.001 | <.001 |
