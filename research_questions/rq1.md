# RQ1 -- General Metrics Overview

> How do agent-generated and human-written fixtures compare across structural metrics?

Generated: 2026-08-21 00:06:37 UTC

See [docs/research-questions.md](../docs/research-questions.md) for the full RQ1 definition.

## Per-dataset summary

### Dataset A (agent-authored) -- 47,208 fixtures

**Continuous metrics -- Paper** (repo-level: one mean per repo, not one value per fixture)

| Metric | n | median | mean | min | max | stdev |
|---|---|---|---|---|---|---|
| loc | 1,354 | 6.28 | 7.67 | 1 | 82 | 5.74 |
| cyclomatic_complexity | 1,354 | 1.04 | 1.22 | 1 | 6 | 0.47 |
| comment_density | 1,354 | 0.01 | 0.02 | 0 | 0 | 0.04 |

**Continuous metrics -- Other (not in the paper)** (repo-level: one mean per repo, not one value per fixture)

| Metric | n | median | mean | min | max | stdev |
|---|---|---|---|---|---|---|
| max_nesting_depth | 1,354 | 1.06 | 1.20 | 1 | 4 | 0.33 |
| num_parameters | 1,354 | 0.00 | 0.18 | 0 | 3 | 0.39 |

**scope distribution**

| Value | Count | % |
|---|---|---|
| per_test | 40,671 | 86.2% |
| per_class | 5,633 | 11.9% |
| per_module | 683 | 1.4% |
| global | 221 | 0.5% |

**fixture_type distribution**

| Value | Count | % |
|---|---|---|
| before_each | 17,519 | 37.1% |
| after_each | 11,104 | 23.5% |
| pytest_decorator | 8,406 | 17.8% |
| before_all | 2,837 | 6.0% |
| after_all | 2,200 | 4.7% |
| unittest_setup | 1,894 | 4.0% |
| pytest_class_method | 735 | 1.6% |
| mocha_before | 619 | 1.3% |
| junit5_before_each | 570 | 1.2% |
| mocha_after | 496 | 1.1% |
| junit5_after_each | 241 | 0.5% |
| junit5_before_all | 150 | 0.3% |
| junit4_before | 123 | 0.3% |
| junit5_after_all | 98 | 0.2% |
| junit_rule | 61 | 0.1% |
| junit4_after | 56 | 0.1% |
| testng_before_class | 31 | 0.1% |
| testng_before_method | 20 | 0.0% |
| junit_class_rule | 16 | 0.0% |
| testng_after_class | 15 | 0.0% |
| testng_after_method | 12 | 0.0% |
| testng_data_provider | 5 | 0.0% |

**commit_type distribution**

| Value | Count | % |
|---|---|---|
| feat | 20,989 | 44.5% |
| none | 11,984 | 25.4% |
| fix | 7,426 | 15.7% |
| test | 4,813 | 10.2% |
| chore | 756 | 1.6% |
| refactor | 739 | 1.6% |
| other | 428 | 0.9% |
| docs | 71 | 0.2% |
| style | 2 | 0.0% |

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

3,561/47,208 fixtures (7.54%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 1,429 | 111 | 7.77% | typescript=83, python=27, javascript=1 |
| javascript | 3,385 | 962 | 28.42% | typescript=797, python=142, java=23 |
| python | 11,000 | 492 | 4.47% | typescript=323, javascript=144, java=25 |
| typescript | 31,394 | 1,996 | 6.36% | javascript=1,606, python=358, java=32 |

**agent_type distribution** (descriptive only, not compared against other datasets -- see load_dataset_metrics()'s docstring for why)

| Value | Count | % |
|---|---|---|
| claude | 40,388 | 85.6% |
| copilot | 3,074 | 6.5% |
| cursor | 1,981 | 4.2% |
| devin | 359 | 0.8% |
| paperclip | 346 | 0.7% |
| codex | 310 | 0.7% |
| qwen_coder | 198 | 0.4% |
| gemini | 192 | 0.4% |
| letta_code | 150 | 0.3% |
| amp | 59 | 0.1% |
| jules | 47 | 0.1% |
| gru | 23 | 0.0% |
| langchain_open_swe | 23 | 0.0% |
| sourcery | 19 | 0.0% |
| coderabbit | 10 | 0.0% |
| aider | 9 | 0.0% |
| openhands | 6 | 0.0% |
| crush | 4 | 0.0% |
| codegen | 3 | 0.0% |
| factory_droid | 3 | 0.0% |
| windsurf | 3 | 0.0% |
| generic | 1 | 0.0% |

### Dataset C (human-authored, pre-LLM) -- 47,208 fixtures

**Continuous metrics -- Paper** (repo-level: one mean per repo, not one value per fixture)

| Metric | n | median | mean | min | max | stdev |
|---|---|---|---|---|---|---|
| loc | 2,309 | 5.67 | 7.96 | 1 | 157 | 8.91 |
| cyclomatic_complexity | 2,309 | 1.00 | 1.17 | 1 | 8 | 0.48 |
| comment_density | 2,309 | 0.00 | 0.02 | 0 | 0 | 0.05 |

**Continuous metrics -- Other (not in the paper)** (repo-level: one mean per repo, not one value per fixture)

| Metric | n | median | mean | min | max | stdev |
|---|---|---|---|---|---|---|
| max_nesting_depth | 2,309 | 1.00 | 1.15 | 1 | 4 | 0.31 |
| num_parameters | 2,325 | 0.00 | 0.15 | 0 | 4 | 0.40 |

**scope distribution**

| Value | Count | % |
|---|---|---|
| per_test | 40,561 | 85.9% |
| per_class | 5,525 | 11.7% |
| per_module | 754 | 1.6% |
| global | 368 | 0.8% |

**fixture_type distribution**

| Value | Count | % |
|---|---|---|
| before_each | 19,151 | 40.6% |
| unittest_setup | 6,591 | 14.0% |
| after_each | 5,647 | 12.0% |
| pytest_decorator | 4,155 | 8.8% |
| mocha_before | 3,828 | 8.1% |
| before_all | 2,701 | 5.7% |
| mocha_after | 1,944 | 4.1% |
| after_all | 1,504 | 3.2% |
| junit4_before | 335 | 0.7% |
| pytest_class_method | 289 | 0.6% |
| testng_before_class | 194 | 0.4% |
| testng_data_provider | 183 | 0.4% |
| junit4_after | 158 | 0.3% |
| testng_after_class | 113 | 0.2% |
| junit_rule | 112 | 0.2% |
| junit5_before_each | 82 | 0.2% |
| junit5_after_each | 44 | 0.1% |
| junit_class_rule | 40 | 0.1% |
| testng_before_method | 36 | 0.1% |
| junit3_setup | 34 | 0.1% |
| junit5_before_all | 27 | 0.1% |
| testng_after_method | 15 | 0.0% |
| junit5_after_all | 14 | 0.0% |
| junit3_teardown | 11 | 0.0% |

**commit_type distribution**

| Value | Count | % |
|---|---|---|
| _(no data)_ | -- | -- |

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

4,318/47,208 fixtures (9.15%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 2,541 | 1,168 | 45.97% | typescript=684, python=428, javascript=56 |
| javascript | 4,454 | 1,385 | 31.10% | typescript=1,223, python=156, java=6 |
| python | 11,119 | 758 | 6.82% | typescript=607, javascript=135, java=16 |
| typescript | 29,094 | 1,007 | 3.46% | javascript=914, python=90, java=3 |

**agent_type distribution** (descriptive only, not compared against other datasets -- see load_dataset_metrics()'s docstring for why)

| Value | Count | % |
|---|---|---|
| human_pre2022 | 47,208 | 100.0% |

## A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)

**Paper Metrics -- Continuous** (Mann-Whitney U on repo-level values, two-sided) -- one mean value per repo (per language, for the per-language rows), not per fixture, so fixtures clustering within a repo can't inflate the result. Effect size is Cliff's delta (thresholds: negligible <0.147, small <0.33, medium <0.474, else large; positive means the comparison dataset tends to have larger values than A, negative means A tends to have larger values). The Overall row is a single pooled test, not BH-corrected; each metric's per-language rows are BH-FDR corrected against each other only (one family per metric, 4 languages). These three (`loc`, `cyclomatic_complexity`, `comment_density`) are the only continuous metrics reported in the paper -- see this module's docstring.

### loc

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 1354 | 2309 | U=1448622.5 | -0.073 | negligible | <.001 | -- |
| java | 96 | 251 | U=10541.0 | -0.125 | negligible | 0.071 | 0.094 |
| javascript | 115 | 557 | U=28017.0 | -0.125 | negligible | 0.034 | 0.068 |
| python | 531 | 944 | U=205119.0 | -0.182 | small | <.001 | <.001 |
| typescript | 749 | 735 | U=286941.5 | 0.042 | negligible | 0.157 | 0.157 |

### cyclomatic_complexity

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 1354 | 2309 | U=1317504.5 | -0.157 | small | <.001 | -- |
| java | 96 | 251 | U=10287.0 | -0.146 | negligible | 0.012 | 0.016 |
| javascript | 115 | 557 | U=22022.0 | -0.312 | small | <.001 | <.001 |
| python | 531 | 944 | U=241538.5 | -0.036 | negligible | 0.213 | 0.213 |
| typescript | 749 | 735 | U=211549.5 | -0.231 | small | <.001 | <.001 |

### comment_density

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 1354 | 2309 | U=1307906.5 | -0.163 | small | <.001 | -- |
| java | 96 | 251 | U=8126.0 | -0.326 | small | <.001 | <.001 |
| javascript | 115 | 557 | U=22235.5 | -0.306 | small | <.001 | <.001 |
| python | 531 | 944 | U=232886.0 | -0.071 | negligible | 0.015 | 0.015 |
| typescript | 749 | 735 | U=234865.5 | -0.147 | negligible | <.001 | <.001 |

**Other Extracted Features (Not in the Paper) -- Continuous** (Mann-Whitney U on repo-level values, two-sided) -- one mean value per repo (per language, for the per-language rows), not per fixture, so fixtures clustering within a repo can't inflate the result. Effect size is Cliff's delta (thresholds: negligible <0.147, small <0.33, medium <0.474, else large; positive means the comparison dataset tends to have larger values than A, negative means A tends to have larger values). The Overall row is a single pooled test, not BH-corrected; each metric's per-language rows are BH-FDR corrected against each other only (one family per metric, 4 languages). Computed and tested with the same rigor as the paper metrics above -- `max_nesting_depth` gets an identical Mann-Whitney/per-language table, `num_parameters` gets a descriptive floor-percentage footnote instead (see below for why) -- just not part of the paper's reported RQ1 comparison.

**Floor-binding check (descriptive only -- not a comparative test)** -- `num_parameters` was dropped from Mann-Whitney testing (see this module's docstring) because it floors heavily in both datasets; this documents exactly how heavily, transparently, instead of silently omitting it.

| Metric | Floor value | Dataset A (agent-authored) at floor | Dataset C (human-authored, pre-LLM) at floor |
|---|---|---|---|
| num_parameters | 0 | 91.2% | 94.0% |

### max_nesting_depth

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 1354 | 2309 | U=1291165.5 | -0.174 | small | <.001 | -- |
| java | 96 | 251 | U=10449.0 | -0.133 | negligible | 0.023 | 0.023 |
| javascript | 115 | 557 | U=21504.0 | -0.329 | small | <.001 | <.001 |
| python | 531 | 944 | U=229789.0 | -0.083 | negligible | 0.005 | 0.007 |
| typescript | 749 | 735 | U=204026.5 | -0.259 | small | <.001 | <.001 |

**Categorical metrics (chi-square)** -- Effect size is Cramer's V (thresholds: negligible <0.1, small <0.3, medium <0.5, else large). Same Overall-uncorrected / per-language-family-corrected convention as the continuous metrics above. `scope`/`fixture_type` each have a per-language family; `commit_type` doesn't (renders Overall-only).

### scope

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 1354 | 2325 | chi2=41.4 (df=3) | 0.021 | negligible | <.001 | -- |
| java | 97 | 267 | chi2=11.3 (df=1) | 0.064 | negligible | <.001 | <.001 |
| javascript | 115 | 557 | chi2=177.0 (df=1) | 0.146 | small | <.001 | <.001 |
| python | 531 | 944 | chi2=422.5 (df=3) | 0.138 | small | <.001 | <.001 |
| typescript | 749 | 735 | chi2=200.2 (df=1) | 0.057 | negligible | <.001 | <.001 |

### fixture_type

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 1354 | 2325 | chi2=10626.0 (df=23) | 0.335 | medium | <.001 | -- |
| java | 97 | 267 | chi2=1233.5 (df=14) | 0.664 | large | <.001 | <.001 |
| javascript | 115 | 557 | chi2=279.5 (df=5) | 0.183 | small | <.001 | <.001 |
| python | 531 | 944 | chi2=4233.0 (df=2) | 0.438 | medium | <.001 | <.001 |
| typescript | 749 | 735 | chi2=5951.3 (df=5) | 0.312 | medium | <.001 | <.001 |

> **`fixture_type`'s result above is not used in the paper.** It's a pooled/per-language fixture-level chi-square, which treats fixtures clustered within a repo as independent observations and inflates both chi2 and Cramer's V (see [Limitations § Categorical Pseudo-Replication](../docs/reference/limitations.md#categorical-pseudo-replication)). The paper reports the repo-level `fixture_type` proportion test in "Repo-level aggregates" below instead. `scope`/`commit_type` above are unaffected and are used as-is.

### commit_type

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 1354 | 0 | -- | -- | _insufficient data_ | -- | -- |

## Repo-level aggregates

fixture_type re-tested with one *proportion-per-repo* value per category instead of pooled/per-language fixture-level chi-square, so each repo counts once regardless of how many fixtures it contributed -- see compare_categorical_repo_level()'s docstring in _shared.py. (The continuous metrics above are already repo-level throughout, including their per-language rows, so they don't need a separate view here.)

### A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)

**fixture_type, repo-level (Mann-Whitney U on per-repo category proportions, two-sided)** -- the fixture_type chi-square table above treats every fixture as an independent observation, but fixtures cluster within repos (shared framework choice, project convention), which inflates chi2 and partially corrupts Cramer's V. This instead compares, per repo, what fraction of its fixtures are each fixture_type -- so each repo counts once regardless of how many fixtures it contributed. **This is the `fixture_type` result reported in the paper.**

| Category | A median | A mean | C median | C mean | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|---|---|---|
| after_all | 0.0% | 3.1% | 0.0% | 2.8% | 1354 | 2325 | U=1458577.0 | -0.073 | negligible | <.001 | <.001 |
| after_each | 0.0% | 18.4% | 0.0% | 8.8% | 1354 | 2325 | U=1207114.0 | -0.233 | small | <.001 | <.001 |
| before_all | 0.0% | 4.9% | 0.0% | 5.4% | 1354 | 2325 | U=1480997.0 | -0.059 | negligible | <.001 | <.001 |
| before_each | 8.3% | 28.0% | 0.0% | 26.0% | 1354 | 2325 | U=1462962.5 | -0.071 | negligible | <.001 | <.001 |
| junit3_setup | 0.0% | 0.0% | 0.0% | 0.1% | 1354 | 2325 | U=1579441.0 | 0.003 | negligible | 0.031 | 0.036 |
| junit3_teardown | 0.0% | 0.0% | 0.0% | 0.1% | 1354 | 2325 | U=1576733.0 | 0.002 | negligible | 0.127 | 0.138 |
| junit4_after | 0.0% | 0.3% | 0.0% | 1.3% | 1354 | 2325 | U=1602091.5 | 0.018 | negligible | <.001 | <.001 |
| junit4_before | 0.0% | 0.9% | 0.0% | 3.6% | 1354 | 2325 | U=1639972.5 | 0.042 | negligible | <.001 | <.001 |
| junit5_after_all | 0.0% | 0.3% | 0.0% | 0.2% | 1354 | 2325 | U=1556449.0 | -0.011 | negligible | <.001 | <.001 |
| junit5_after_each | 0.0% | 1.0% | 0.0% | 0.5% | 1354 | 2325 | U=1541762.0 | -0.020 | negligible | <.001 | <.001 |
| junit5_before_all | 0.0% | 0.5% | 0.0% | 0.3% | 1354 | 2325 | U=1554053.0 | -0.013 | negligible | <.001 | <.001 |
| junit5_before_each | 0.0% | 2.8% | 0.0% | 1.0% | 1354 | 2325 | U=1526435.0 | -0.030 | negligible | <.001 | <.001 |
| junit_class_rule | 0.0% | 0.0% | 0.0% | 0.3% | 1354 | 2325 | U=1581869.0 | 0.005 | negligible | 0.032 | 0.036 |
| junit_rule | 0.0% | 0.1% | 0.0% | 1.1% | 1354 | 2325 | U=1604349.5 | 0.019 | negligible | <.001 | <.001 |
| mocha_after | 0.0% | 1.1% | 0.0% | 2.2% | 1354 | 2325 | U=1626596.5 | 0.033 | negligible | <.001 | <.001 |
| mocha_before | 0.0% | 1.4% | 0.0% | 4.9% | 1354 | 2325 | U=1677283.5 | 0.066 | negligible | <.001 | <.001 |
| pytest_class_method | 0.0% | 1.5% | 0.0% | 1.2% | 1354 | 2325 | U=1524659.0 | -0.031 | negligible | <.001 | <.001 |
| pytest_decorator | 0.0% | 29.0% | 0.0% | 17.6% | 1354 | 2325 | U=1369430.5 | -0.130 | negligible | <.001 | <.001 |
| testng_after_class | 0.0% | 0.1% | 0.0% | 0.5% | 1354 | 2325 | U=1592138.5 | 0.012 | negligible | 0.002 | 0.002 |
| testng_after_method | 0.0% | 0.1% | 0.0% | 0.0% | 1354 | 2325 | U=1577292.5 | 0.002 | negligible | 0.306 | 0.320 |
| testng_before_class | 0.0% | 0.2% | 0.0% | 1.0% | 1354 | 2325 | U=1599465.0 | 0.016 | negligible | <.001 | <.001 |
| testng_before_method | 0.0% | 0.1% | 0.0% | 0.1% | 1354 | 2325 | U=1577483.5 | 0.002 | negligible | 0.329 | 0.329 |
| testng_data_provider | 0.0% | 0.1% | 0.0% | 0.4% | 1354 | 2325 | U=1581865.0 | 0.005 | negligible | 0.032 | 0.036 |
| unittest_setup | 0.0% | 6.1% | 0.0% | 20.5% | 1354 | 2325 | U=1805287.5 | 0.147 | negligible | <.001 | <.001 |
