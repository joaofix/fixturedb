# RQ1 -- General Metrics Overview

> How do agent-generated and human-written fixtures compare across structural metrics?

Generated: 2026-08-31 20:52:41 UTC

See [docs/research-questions.md](../docs/research-questions.md) for the full RQ1 definition.

## Per-dataset summary

### Dataset A (agent-authored) -- 67,979 fixtures

**Continuous metrics -- Paper** (repo-level: one mean per repo, not one value per fixture)

| Metric | n | median | mean | min | max | stdev |
|---|---|---|---|---|---|---|
| loc | 1,647 | 6.33 | 7.64 | 1 | 82 | 5.49 |
| cyclomatic_complexity | 1,647 | 1.05 | 1.22 | 1 | 6 | 0.46 |
| comment_density | 1,647 | 0.01 | 0.02 | 0 | 0 | 0.04 |

**Continuous metrics -- Other (not in the paper)** (repo-level: one mean per repo, not one value per fixture)

| Metric | n | median | mean | min | max | stdev |
|---|---|---|---|---|---|---|
| max_nesting_depth | 1,647 | 1.07 | 1.19 | 1 | 4 | 0.31 |
| num_parameters | 1,647 | 0.00 | 0.18 | 0 | 4 | 0.39 |

**scope distribution**

| Value | Count | % |
|---|---|---|
| per_test | 59,244 | 87.2% |
| per_class | 7,259 | 10.7% |
| per_module | 1,051 | 1.5% |
| global | 425 | 0.6% |

**fixture_type distribution**

| Value | Count | % |
|---|---|---|
| before_each | 23,937 | 35.2% |
| pytest_decorator | 15,955 | 23.5% |
| after_each | 14,618 | 21.5% |
| before_all | 3,474 | 5.1% |
| after_all | 2,886 | 4.2% |
| unittest_setup | 2,757 | 4.1% |
| pytest_class_method | 1,010 | 1.5% |
| mocha_before | 715 | 1.1% |
| junit5_before_each | 713 | 1.0% |
| mocha_after | 588 | 0.9% |
| junit5_after_each | 333 | 0.5% |
| junit5_before_all | 253 | 0.4% |
| junit4_before | 190 | 0.3% |
| junit5_after_all | 141 | 0.2% |
| junit_rule | 131 | 0.2% |
| junit4_after | 93 | 0.1% |
| testng_before_class | 62 | 0.1% |
| testng_before_method | 51 | 0.1% |
| testng_after_class | 25 | 0.0% |
| junit_class_rule | 22 | 0.0% |
| testng_after_method | 17 | 0.0% |
| testng_data_provider | 7 | 0.0% |
| junit3_setup | 1 | 0.0% |

**commit_type distribution**

| Value | Count | % |
|---|---|---|
| feat | 29,628 | 43.6% |
| none | 17,044 | 25.1% |
| fix | 10,684 | 15.7% |
| test | 7,651 | 11.3% |
| refactor | 1,182 | 1.7% |
| chore | 1,026 | 1.5% |
| other | 623 | 0.9% |
| docs | 139 | 0.2% |
| style | 2 | 0.0% |

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

5,043/67,979 fixtures (7.42%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 2,083 | 232 | 11.14% | typescript=145, python=86, javascript=1 |
| javascript | 3,873 | 1,173 | 30.29% | typescript=990, python=160, java=23 |
| python | 20,148 | 1,192 | 5.92% | typescript=907, javascript=152, java=133 |
| typescript | 41,875 | 2,446 | 5.84% | javascript=1,894, python=520, java=32 |

**agent_type distribution** (descriptive only, not compared against other datasets -- see load_dataset_metrics()'s docstring for why)

| Value | Count | % |
|---|---|---|
| claude | 57,975 | 85.3% |
| copilot | 4,647 | 6.8% |
| cursor | 2,905 | 4.3% |
| devin | 629 | 0.9% |
| codex | 408 | 0.6% |
| paperclip | 351 | 0.5% |
| gemini | 238 | 0.4% |
| qwen_coder | 224 | 0.3% |
| letta_code | 161 | 0.2% |
| gru | 145 | 0.2% |
| jules | 109 | 0.2% |
| amp | 79 | 0.1% |
| langchain_open_swe | 29 | 0.0% |
| sourcery | 19 | 0.0% |
| coderabbit | 14 | 0.0% |
| crush | 12 | 0.0% |
| aider | 9 | 0.0% |
| openhands | 6 | 0.0% |
| mistral_vibe | 4 | 0.0% |
| codegen | 3 | 0.0% |
| factory_droid | 3 | 0.0% |
| sentry_seer | 3 | 0.0% |
| windsurf | 3 | 0.0% |
| generic | 1 | 0.0% |
| ona | 1 | 0.0% |
| opencode | 1 | 0.0% |

### Dataset C (human-authored, pre-LLM) -- 67,979 fixtures

**Continuous metrics -- Paper** (repo-level: one mean per repo, not one value per fixture)

| Metric | n | median | mean | min | max | stdev |
|---|---|---|---|---|---|---|
| loc | 2,450 | 5.86 | 7.91 | 1 | 161 | 9.69 |
| cyclomatic_complexity | 2,450 | 1.00 | 1.17 | 1 | 9 | 0.46 |
| comment_density | 2,450 | 0.00 | 0.02 | 0 | 1 | 0.05 |

**Continuous metrics -- Other (not in the paper)** (repo-level: one mean per repo, not one value per fixture)

| Metric | n | median | mean | min | max | stdev |
|---|---|---|---|---|---|---|
| max_nesting_depth | 2,450 | 1.00 | 1.14 | 1 | 4 | 0.29 |
| num_parameters | 2,472 | 0.00 | 0.15 | 0 | 4 | 0.37 |

**scope distribution**

| Value | Count | % |
|---|---|---|
| per_test | 58,281 | 85.7% |
| per_class | 7,821 | 11.5% |
| per_module | 1,269 | 1.9% |
| global | 608 | 0.9% |

**fixture_type distribution**

| Value | Count | % |
|---|---|---|
| before_each | 25,401 | 37.4% |
| unittest_setup | 11,920 | 17.5% |
| after_each | 7,434 | 10.9% |
| pytest_decorator | 7,324 | 10.8% |
| mocha_before | 5,157 | 7.6% |
| before_all | 3,571 | 5.3% |
| mocha_after | 2,678 | 3.9% |
| after_all | 1,977 | 2.9% |
| junit4_before | 489 | 0.7% |
| pytest_class_method | 478 | 0.7% |
| testng_before_class | 275 | 0.4% |
| testng_data_provider | 274 | 0.4% |
| junit_rule | 218 | 0.3% |
| junit4_after | 198 | 0.3% |
| testng_after_class | 177 | 0.3% |
| junit5_before_each | 91 | 0.1% |
| junit_class_rule | 61 | 0.1% |
| testng_before_method | 56 | 0.1% |
| junit5_after_each | 50 | 0.1% |
| junit5_before_all | 44 | 0.1% |
| junit3_setup | 32 | 0.0% |
| testng_after_method | 30 | 0.0% |
| junit5_after_all | 24 | 0.0% |
| junit3_teardown | 20 | 0.0% |

**commit_type distribution**

| Value | Count | % |
|---|---|---|
| _(no data)_ | -- | -- |

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

6,214/67,979 fixtures (9.14%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 3,897 | 1,883 | 48.32% | typescript=985, python=819, javascript=79 |
| javascript | 5,467 | 2,067 | 37.81% | typescript=1,791, python=267, java=9 |
| python | 19,523 | 1,026 | 5.26% | typescript=841, javascript=172, java=13 |
| typescript | 39,092 | 1,238 | 3.17% | javascript=1,096, python=139, java=3 |

**agent_type distribution** (descriptive only, not compared against other datasets -- see load_dataset_metrics()'s docstring for why)

| Value | Count | % |
|---|---|---|
| human_pre2022 | 67,979 | 100.0% |

## A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)

**Paper Metrics -- Continuous** (Mann-Whitney U on repo-level values, two-sided) -- one mean value per repo (per language, for the per-language rows), not per fixture, so fixtures clustering within a repo can't inflate the result. Effect size is Cliff's delta (thresholds: negligible <0.147, small <0.33, medium <0.474, else large; positive means the comparison dataset tends to have larger values than A, negative means A tends to have larger values). The Overall row is a single pooled test, not BH-corrected; each metric's per-language rows are BH-FDR corrected against each other only (one family per metric, 4 languages). These three (`loc`, `cyclomatic_complexity`, `comment_density`) are the only continuous metrics reported in the paper -- see this module's docstring.

### loc

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 1647 | 2450 | U=1867489.5 | -0.074 | negligible | <.001 | -- |
| java | 121 | 288 | U=15396.0 | -0.116 | negligible | 0.063 | 0.125 |
| javascript | 137 | 563 | U=35982.0 | -0.067 | negligible | 0.223 | 0.265 |
| python | 656 | 1045 | U=276792.0 | -0.192 | small | <.001 | <.001 |
| typescript | 928 | 749 | U=358531.5 | 0.032 | negligible | 0.265 | 0.265 |

### cyclomatic_complexity

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 1647 | 2450 | U=1714968.0 | -0.150 | small | <.001 | -- |
| java | 121 | 288 | U=14285.0 | -0.180 | small | <.001 | <.001 |
| javascript | 137 | 563 | U=27241.0 | -0.294 | small | <.001 | <.001 |
| python | 656 | 1045 | U=339636.0 | -0.009 | negligible | 0.739 | 0.739 |
| typescript | 928 | 749 | U=272240.0 | -0.217 | small | <.001 | <.001 |

### comment_density

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 1647 | 2450 | U=1764204.0 | -0.126 | negligible | <.001 | -- |
| java | 121 | 288 | U=13345.0 | -0.234 | small | <.001 | <.001 |
| javascript | 137 | 563 | U=28601.5 | -0.258 | small | <.001 | <.001 |
| python | 656 | 1045 | U=337513.0 | -0.015 | negligible | 0.575 | 0.575 |
| typescript | 928 | 749 | U=307268.0 | -0.116 | negligible | <.001 | <.001 |

**Other Extracted Features (Not in the Paper) -- Continuous** (Mann-Whitney U on repo-level values, two-sided) -- one mean value per repo (per language, for the per-language rows), not per fixture, so fixtures clustering within a repo can't inflate the result. Effect size is Cliff's delta (thresholds: negligible <0.147, small <0.33, medium <0.474, else large; positive means the comparison dataset tends to have larger values than A, negative means A tends to have larger values). The Overall row is a single pooled test, not BH-corrected; each metric's per-language rows are BH-FDR corrected against each other only (one family per metric, 4 languages). Computed and tested with the same rigor as the paper metrics above -- `max_nesting_depth` gets an identical Mann-Whitney/per-language table, `num_parameters` gets a descriptive floor-percentage footnote instead (see below for why) -- just not part of the paper's reported RQ1 comparison.

**Floor-binding check (descriptive only -- not a comparative test)** -- `num_parameters` was dropped from Mann-Whitney testing (see this module's docstring) because it floors heavily in both datasets; this documents exactly how heavily, transparently, instead of silently omitting it.

| Metric | Floor value | Dataset A (agent-authored) at floor | Dataset C (human-authored, pre-LLM) at floor |
|---|---|---|---|
| num_parameters | 0 | 88.6% | 92.9% |

### max_nesting_depth

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 1647 | 2450 | U=1673979.0 | -0.170 | small | <.001 | -- |
| java | 121 | 288 | U=14785.5 | -0.151 | small | 0.004 | 0.004 |
| javascript | 137 | 563 | U=26440.0 | -0.314 | small | <.001 | <.001 |
| python | 656 | 1045 | U=312840.0 | -0.087 | negligible | 0.002 | 0.002 |
| typescript | 928 | 749 | U=260856.5 | -0.249 | small | <.001 | <.001 |

**Categorical metrics (chi-square)** -- Effect size is Cramer's V (thresholds: negligible <0.1, small <0.3, medium <0.5, else large). Same Overall-uncorrected / per-language-family-corrected convention as the continuous metrics above. `scope`/`fixture_type` each have a per-language family; `commit_type` doesn't (renders Overall-only).

### scope

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 1647 | 2472 | chi2=81.7 (df=3) | 0.025 | negligible | <.001 | -- |
| java | 122 | 315 | chi2=7.4 (df=1) | 0.043 | negligible | 0.006 | 0.006 |
| javascript | 137 | 563 | chi2=80.8 (df=1) | 0.092 | negligible | <.001 | <.001 |
| python | 656 | 1045 | chi2=942.0 (df=3) | 0.155 | small | <.001 | <.001 |
| typescript | 928 | 749 | chi2=118.5 (df=1) | 0.038 | negligible | <.001 | <.001 |

### fixture_type

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 1647 | 2472 | chi2=18049.1 (df=23) | 0.364 | medium | <.001 | -- |
| java | 122 | 315 | chi2=1685.6 (df=14) | 0.643 | large | <.001 | <.001 |
| javascript | 137 | 563 | chi2=237.9 (df=5) | 0.158 | small | <.001 | <.001 |
| python | 656 | 1045 | chi2=9110.8 (df=2) | 0.481 | medium | <.001 | <.001 |
| typescript | 928 | 749 | chi2=8105.0 (df=5) | 0.313 | medium | <.001 | <.001 |

> **`fixture_type`'s result above is not used in the paper.** It's a pooled/per-language fixture-level chi-square, which treats fixtures clustered within a repo as independent observations and inflates both chi2 and Cramer's V (see [Limitations § Categorical Pseudo-Replication](../docs/reference/limitations.md#categorical-pseudo-replication)). The paper reports the repo-level `fixture_type` proportion test in "Repo-level aggregates" below instead. `scope`/`commit_type` above are unaffected and are used as-is.

### commit_type

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 1647 | 0 | -- | -- | _insufficient data_ | -- | -- |

## Repo-level aggregates

fixture_type re-tested with one *proportion-per-repo* value per category instead of pooled/per-language fixture-level chi-square, so each repo counts once regardless of how many fixtures it contributed -- see compare_categorical_repo_level()'s docstring in _shared.py. (The continuous metrics above are already repo-level throughout, including their per-language rows, so they don't need a separate view here.)

### A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)

**fixture_type, repo-level (Mann-Whitney U on per-repo category proportions, two-sided)** -- the fixture_type chi-square table above treats every fixture as an independent observation, but fixtures cluster within repos (shared framework choice, project convention), which inflates chi2 and partially corrupts Cramer's V. This instead compares, per repo, what fraction of its fixtures are each fixture_type -- so each repo counts once regardless of how many fixtures it contributed. **This is the `fixture_type` result reported in the paper.**

| Category | A median | A mean | C median | C mean | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|---|---|---|
| after_all | 0.0% | 3.0% | 0.0% | 2.7% | 1647 | 2472 | U=1874244.0 | -0.079 | negligible | <.001 | <.001 |
| after_each | 0.0% | 18.4% | 0.0% | 8.5% | 1647 | 2472 | U=1544625.5 | -0.241 | small | <.001 | <.001 |
| before_all | 0.0% | 4.7% | 0.0% | 5.0% | 1647 | 2472 | U=1890507.5 | -0.071 | negligible | <.001 | <.001 |
| before_each | 12.5% | 28.4% | 0.0% | 24.7% | 1647 | 2472 | U=1831199.5 | -0.100 | negligible | <.001 | <.001 |
| junit3_setup | 0.0% | 0.1% | 0.0% | 0.2% | 1647 | 2472 | U=2041865.0 | 0.003 | negligible | 0.053 | 0.060 |
| junit3_teardown | 0.0% | 0.0% | 0.0% | 0.1% | 1647 | 2472 | U=2039809.5 | 0.002 | negligible | 0.068 | 0.074 |
| junit4_after | 0.0% | 0.3% | 0.0% | 1.2% | 1647 | 2472 | U=2079002.0 | 0.021 | negligible | <.001 | <.001 |
| junit4_before | 0.0% | 0.9% | 0.0% | 3.9% | 1647 | 2472 | U=2136238.0 | 0.049 | negligible | <.001 | <.001 |
| junit5_after_all | 0.0% | 0.3% | 0.0% | 0.2% | 1647 | 2472 | U=2016806.5 | -0.009 | negligible | 0.004 | 0.005 |
| junit5_after_each | 0.0% | 1.0% | 0.0% | 0.4% | 1647 | 2472 | U=1986423.5 | -0.024 | negligible | <.001 | <.001 |
| junit5_before_all | 0.0% | 0.5% | 0.0% | 0.6% | 1647 | 2472 | U=2017826.5 | -0.009 | negligible | 0.025 | 0.030 |
| junit5_before_each | 0.0% | 2.9% | 0.0% | 1.0% | 1647 | 2472 | U=1968141.5 | -0.033 | negligible | <.001 | <.001 |
| junit_class_rule | 0.0% | 0.0% | 0.0% | 0.2% | 1647 | 2472 | U=2050116.5 | 0.007 | negligible | 0.004 | 0.006 |
| junit_rule | 0.0% | 0.1% | 0.0% | 1.6% | 1647 | 2472 | U=2084950.5 | 0.024 | negligible | <.001 | <.001 |
| mocha_after | 0.0% | 1.1% | 0.0% | 2.1% | 1647 | 2472 | U=2112659.0 | 0.038 | negligible | <.001 | <.001 |
| mocha_before | 0.0% | 1.3% | 0.0% | 4.4% | 1647 | 2472 | U=2171058.5 | 0.066 | negligible | <.001 | <.001 |
| pytest_class_method | 0.0% | 1.4% | 0.0% | 1.4% | 1647 | 2472 | U=1966298.0 | -0.034 | negligible | <.001 | <.001 |
| pytest_decorator | 0.0% | 28.9% | 0.0% | 18.5% | 1647 | 2472 | U=1791942.0 | -0.120 | negligible | <.001 | <.001 |
| testng_after_class | 0.0% | 0.1% | 0.0% | 0.7% | 1647 | 2472 | U=2074471.5 | 0.019 | negligible | <.001 | <.001 |
| testng_after_method | 0.0% | 0.1% | 0.0% | 0.1% | 1647 | 2472 | U=2042259.0 | 0.003 | negligible | 0.124 | 0.130 |
| testng_before_class | 0.0% | 0.2% | 0.0% | 1.0% | 1647 | 2472 | U=2074958.5 | 0.019 | negligible | <.001 | <.001 |
| testng_before_method | 0.0% | 0.2% | 0.0% | 0.1% | 1647 | 2472 | U=2041425.5 | 0.003 | negligible | 0.225 | 0.225 |
| testng_data_provider | 0.0% | 0.1% | 0.0% | 0.3% | 1647 | 2472 | U=2047643.5 | 0.006 | negligible | 0.011 | 0.014 |
| unittest_setup | 0.0% | 6.2% | 0.0% | 21.0% | 1647 | 2472 | U=2340428.5 | 0.150 | small | <.001 | <.001 |
