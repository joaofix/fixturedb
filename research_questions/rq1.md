# RQ1 -- General Metrics Overview

> How do agent-generated and human-written fixtures compare across structural metrics?

Generated: 2026-08-19 15:56:56 UTC

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

### Dataset C (human-authored, pre-LLM) -- 191,883 fixtures

**Continuous metrics -- Paper** (repo-level: one mean per repo, not one value per fixture)

| Metric | n | median | mean | min | max | stdev |
|---|---|---|---|---|---|---|
| loc | 2,989 | 6.25 | 8.14 | 1 | 534 | 12.34 |
| cyclomatic_complexity | 2,989 | 1.02 | 1.19 | 1 | 14 | 0.50 |
| comment_density | 2,989 | 0.00 | 0.02 | 0 | 0 | 0.04 |

**Continuous metrics -- Other (not in the paper)** (repo-level: one mean per repo, not one value per fixture)

| Metric | n | median | mean | min | max | stdev |
|---|---|---|---|---|---|---|
| max_nesting_depth | 2,989 | 1.02 | 1.15 | 1 | 4 | 0.29 |
| num_parameters | 3,005 | 0.00 | 0.13 | 0 | 3 | 0.33 |

**scope distribution**

| Value | Count | % |
|---|---|---|
| per_test | 155,762 | 81.2% |
| per_class | 31,929 | 16.6% |
| per_module | 2,848 | 1.5% |
| global | 1,344 | 0.7% |

**fixture_type distribution**

| Value | Count | % |
|---|---|---|
| before_each | 49,158 | 25.6% |
| unittest_setup | 26,389 | 13.8% |
| after_each | 16,463 | 8.6% |
| pytest_decorator | 16,265 | 8.5% |
| junit4_before | 13,096 | 6.8% |
| mocha_before | 10,060 | 5.2% |
| testng_before_class | 7,951 | 4.1% |
| testng_data_provider | 7,674 | 4.0% |
| before_all | 7,614 | 4.0% |
| junit4_after | 5,346 | 2.8% |
| junit_rule | 5,119 | 2.7% |
| mocha_after | 4,934 | 2.6% |
| testng_after_class | 4,874 | 2.5% |
| after_all | 4,337 | 2.3% |
| junit5_before_each | 2,935 | 1.5% |
| junit_class_rule | 1,632 | 0.9% |
| testng_before_method | 1,438 | 0.7% |
| junit5_after_each | 1,232 | 0.6% |
| junit3_setup | 1,189 | 0.6% |
| junit5_before_all | 1,141 | 0.6% |
| pytest_class_method | 1,053 | 0.5% |
| junit5_after_all | 702 | 0.4% |
| testng_after_method | 643 | 0.3% |
| junit3_teardown | 638 | 0.3% |

**commit_type distribution**

| Value | Count | % |
|---|---|---|
| _(no data)_ | -- | -- |

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

19,090/191,883 fixtures (9.95%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 58,262 | 3,612 | 6.20% | python=1,677, typescript=1,147, javascript=788 |
| javascript | 33,157 | 3,058 | 9.22% | typescript=2,081, python=662, java=315 |
| python | 44,044 | 3,012 | 6.84% | javascript=1,557, typescript=1,008, java=447 |
| typescript | 56,420 | 9,408 | 16.67% | javascript=8,874, python=336, java=198 |

**agent_type distribution** (descriptive only, not compared against other datasets -- see load_dataset_metrics()'s docstring for why)

| Value | Count | % |
|---|---|---|
| human_pre2022 | 191,883 | 100.0% |

## A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)

**Paper Metrics -- Continuous** (Mann-Whitney U on repo-level values, two-sided) -- one mean value per repo (per language, for the per-language rows), not per fixture, so fixtures clustering within a repo can't inflate the result. Effect size is Cliff's delta (thresholds: negligible <0.147, small <0.33, medium <0.474, else large; positive means the comparison dataset tends to have larger values than A, negative means A tends to have larger values). The Overall row is a single pooled test, not BH-corrected; each metric's per-language rows are BH-FDR corrected against each other only (one family per metric, 4 languages). These three (`loc`, `cyclomatic_complexity`, `comment_density`) are the only continuous metrics reported in the paper -- see this module's docstring.

### loc

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 1354 | 2989 | U=2021803.5 | -0.001 | negligible | 0.964 | -- |
| java | 96 | 583 | U=27796.5 | -0.007 | negligible | 0.916 | 0.916 |
| javascript | 115 | 822 | U=44891.5 | -0.050 | negligible | 0.383 | 0.510 |
| python | 531 | 1120 | U=258929.5 | -0.129 | negligible | <.001 | <.001 |
| typescript | 749 | 762 | U=297824.0 | 0.044 | negligible | 0.142 | 0.284 |

### cyclomatic_complexity

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 1354 | 2989 | U=1946159.0 | -0.038 | negligible | 0.032 | -- |
| java | 96 | 583 | U=29524.5 | 0.055 | negligible | 0.365 | 0.365 |
| javascript | 115 | 822 | U=37864.5 | -0.199 | small | <.001 | <.001 |
| python | 531 | 1120 | U=322219.0 | 0.084 | negligible | 0.005 | 0.006 |
| typescript | 749 | 762 | U=228182.0 | -0.200 | small | <.001 | <.001 |

### comment_density

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 1354 | 2989 | U=1968781.0 | -0.027 | negligible | 0.135 | -- |
| java | 96 | 583 | U=26873.5 | -0.040 | negligible | 0.517 | 0.517 |
| javascript | 115 | 822 | U=39566.0 | -0.163 | small | 0.002 | 0.005 |
| python | 531 | 1120 | U=321044.5 | 0.080 | negligible | 0.007 | 0.009 |
| typescript | 749 | 762 | U=257376.0 | -0.098 | negligible | <.001 | 0.002 |

**Other Extracted Features (Not in the Paper) -- Continuous** (Mann-Whitney U on repo-level values, two-sided) -- one mean value per repo (per language, for the per-language rows), not per fixture, so fixtures clustering within a repo can't inflate the result. Effect size is Cliff's delta (thresholds: negligible <0.147, small <0.33, medium <0.474, else large; positive means the comparison dataset tends to have larger values than A, negative means A tends to have larger values). The Overall row is a single pooled test, not BH-corrected; each metric's per-language rows are BH-FDR corrected against each other only (one family per metric, 4 languages). Computed and tested with the same rigor as the paper metrics above -- `max_nesting_depth` gets an identical Mann-Whitney/per-language table, `num_parameters` gets a descriptive floor-percentage footnote instead (see below for why) -- just not part of the paper's reported RQ1 comparison.

**Floor-binding check (descriptive only -- not a comparative test)** -- `num_parameters` was dropped from Mann-Whitney testing (see this module's docstring) because it floors heavily in both datasets; this documents exactly how heavily, transparently, instead of silently omitting it.

| Metric | Floor value | Dataset A (agent-authored) at floor | Dataset C (human-authored, pre-LLM) at floor |
|---|---|---|---|
| num_parameters | 0 | 91.2% | 93.7% |

### max_nesting_depth

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 1354 | 2989 | U=1875258.5 | -0.073 | negligible | <.001 | -- |
| java | 96 | 583 | U=29429.0 | 0.052 | negligible | 0.395 | 0.527 |
| javascript | 115 | 822 | U=37641.0 | -0.204 | small | <.001 | <.001 |
| python | 531 | 1120 | U=297124.5 | -0.001 | negligible | 0.979 | 0.979 |
| typescript | 749 | 762 | U=219742.5 | -0.230 | small | <.001 | <.001 |

**Categorical metrics (chi-square)** -- Effect size is Cramer's V (thresholds: negligible <0.1, small <0.3, medium <0.5, else large). Same Overall-uncorrected / per-language-family-corrected convention as the continuous metrics above. `scope`/`fixture_type` each have a per-language family; `commit_type` doesn't (renders Overall-only).

### scope

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 1354 | 3005 | chi2=680.3 (df=3) | 0.053 | negligible | <.001 | -- |
| java | 97 | 608 | chi2=33.3 (df=1) | 0.024 | negligible | <.001 | <.001 |
| javascript | 115 | 822 | chi2=221.2 (df=1) | 0.070 | negligible | <.001 | <.001 |
| python | 531 | 1120 | chi2=504.6 (df=3) | 0.096 | negligible | <.001 | <.001 |
| typescript | 749 | 762 | chi2=236.3 (df=1) | 0.054 | negligible | <.001 | <.001 |

### fixture_type

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 1354 | 3005 | chi2=30317.8 (df=23) | 0.356 | medium | <.001 | -- |
| java | 97 | 608 | chi2=5457.0 (df=14) | 0.309 | medium | <.001 | <.001 |
| javascript | 115 | 822 | chi2=456.8 (df=5) | 0.100 | small | <.001 | <.001 |
| python | 531 | 1120 | chi2=6639.7 (df=2) | 0.348 | medium | <.001 | <.001 |
| typescript | 749 | 762 | chi2=6790.5 (df=5) | 0.288 | small | <.001 | <.001 |

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
| after_all | 0.0% | 3.1% | 0.0% | 2.5% | 1354 | 3005 | U=1920991.5 | -0.056 | negligible | <.001 | <.001 |
| after_each | 0.0% | 18.4% | 0.0% | 8.0% | 1354 | 3005 | U=1578630.5 | -0.224 | small | <.001 | <.001 |
| before_all | 0.0% | 4.9% | 0.0% | 4.9% | 1354 | 3005 | U=1944933.0 | -0.044 | negligible | <.001 | 0.001 |
| before_each | 8.3% | 28.0% | 0.0% | 23.5% | 1354 | 3005 | U=1836378.5 | -0.097 | negligible | <.001 | <.001 |
| junit3_setup | 0.0% | 0.0% | 0.0% | 0.4% | 1354 | 3005 | U=2060111.0 | 0.013 | negligible | <.001 | <.001 |
| junit3_teardown | 0.0% | 0.0% | 0.0% | 0.1% | 1354 | 3005 | U=2050633.0 | 0.008 | negligible | <.001 | 0.001 |
| junit4_after | 0.0% | 0.3% | 0.0% | 1.7% | 1354 | 3005 | U=2204061.0 | 0.083 | negligible | <.001 | <.001 |
| junit4_before | 0.0% | 0.9% | 0.0% | 6.8% | 1354 | 3005 | U=2280370.5 | 0.121 | negligible | <.001 | <.001 |
| junit5_after_all | 0.0% | 0.3% | 0.0% | 0.4% | 1354 | 3005 | U=2056775.0 | 0.011 | negligible | 0.025 | 0.028 |
| junit5_after_each | 0.0% | 1.0% | 0.0% | 0.6% | 1354 | 3005 | U=2037532.0 | 0.002 | negligible | 0.792 | 0.826 |
| junit5_before_all | 0.0% | 0.5% | 0.0% | 0.9% | 1354 | 3005 | U=2068329.5 | 0.017 | negligible | 0.003 | 0.004 |
| junit5_before_each | 0.0% | 2.8% | 0.0% | 2.1% | 1354 | 3005 | U=2032038.5 | -0.001 | negligible | 0.866 | 0.866 |
| junit_class_rule | 0.0% | 0.0% | 0.0% | 0.2% | 1354 | 3005 | U=2068622.0 | 0.017 | negligible | <.001 | <.001 |
| junit_rule | 0.0% | 0.1% | 0.0% | 2.3% | 1354 | 3005 | U=2197168.5 | 0.080 | negligible | <.001 | <.001 |
| mocha_after | 0.0% | 1.1% | 0.0% | 2.1% | 1354 | 3005 | U=2153487.5 | 0.059 | negligible | <.001 | <.001 |
| mocha_before | 0.0% | 1.4% | 0.0% | 4.6% | 1354 | 3005 | U=2205571.5 | 0.084 | negligible | <.001 | <.001 |
| pytest_class_method | 0.0% | 1.5% | 0.0% | 1.2% | 1354 | 3005 | U=1974019.0 | -0.030 | negligible | <.001 | <.001 |
| pytest_decorator | 0.0% | 29.0% | 0.0% | 15.9% | 1354 | 3005 | U=1738202.5 | -0.146 | negligible | <.001 | <.001 |
| testng_after_class | 0.0% | 0.1% | 0.0% | 0.7% | 1354 | 3005 | U=2141684.5 | 0.053 | negligible | <.001 | <.001 |
| testng_after_method | 0.0% | 0.1% | 0.0% | 0.1% | 1354 | 3005 | U=2046769.0 | 0.006 | negligible | 0.020 | 0.023 |
| testng_before_class | 0.0% | 0.2% | 0.0% | 1.9% | 1354 | 3005 | U=2182819.5 | 0.073 | negligible | <.001 | <.001 |
| testng_before_method | 0.0% | 0.1% | 0.0% | 0.2% | 1354 | 3005 | U=2052025.0 | 0.009 | negligible | 0.005 | 0.006 |
| testng_data_provider | 0.0% | 0.1% | 0.0% | 0.3% | 1354 | 3005 | U=2050337.0 | 0.008 | negligible | 0.004 | 0.005 |
| unittest_setup | 0.0% | 6.1% | 0.0% | 18.6% | 1354 | 3005 | U=2302994.0 | 0.132 | negligible | <.001 | <.001 |
