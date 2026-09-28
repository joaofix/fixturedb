# RQ1 -- General Metrics Overview

> How do agent-generated and human-written fixtures compare across structural metrics?

Generated: 2026-09-28 04:52:46 UTC

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
| num_parameters | 1,687 | 0.00 | 0.18 | 0 | 4 | 0.38 |

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
| loc | 2,495 | 5.87 | 7.95 | 1 | 180 | 9.19 |
| cyclomatic_complexity | 2,495 | 1.00 | 1.19 | 1 | 14 | 0.54 |
| comment_density | 2,495 | 0.00 | 0.02 | 0 | 1 | 0.05 |

**Continuous metrics -- Other (not in the paper)** (repo-level: one mean per repo, not one value per fixture)

| Metric | n | median | mean | min | max | stdev |
|---|---|---|---|---|---|---|
| num_parameters | 2,506 | 0.00 | 0.15 | 0 | 3 | 0.36 |

**fixture_type distribution**

| Value | Count | % |
|---|---|---|
| before_each | 26,343 | 37.3% |
| unittest_setup | 12,450 | 17.6% |
| after_each | 7,732 | 10.9% |
| pytest_decorator | 7,732 | 10.9% |
| mocha_before | 5,198 | 7.4% |
| before_all | 3,633 | 5.1% |
| mocha_after | 2,670 | 3.8% |
| after_all | 2,102 | 3.0% |
| pytest_class_method | 502 | 0.7% |
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

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

6,376/70,623 fixtures (9.03%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 4,157 | 1,936 | 46.57% | typescript=990, python=866, javascript=80 |
| javascript | 5,610 | 2,126 | 37.90% | typescript=1,797, python=314, java=15 |
| python | 20,359 | 1,013 | 4.98% | typescript=837, javascript=162, java=14 |
| typescript | 40,497 | 1,301 | 3.21% | javascript=1,132, python=158, java=11 |

**agent_type distribution** (descriptive only, not compared against other datasets -- see load_dataset_metrics()'s docstring for why)

| Value | Count | % |
|---|---|---|
| human_pre2022 | 70,623 | 100.0% |

## A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)

**Paper Metrics -- Continuous** (Mann-Whitney U on repo-level values, two-sided) -- one mean value per repo (per language, for the per-language rows), not per fixture, so fixtures clustering within a repo can't inflate the result. Effect size is Cliff's delta (thresholds: negligible <0.147, small <0.33, medium <0.474, else large; positive means the comparison dataset tends to have larger values than A, negative means A tends to have larger values). The Overall row is a single pooled test, not BH-corrected; each metric's per-language rows are BH-FDR corrected against each other only (one family per metric, 4 languages). These three (`loc`, `cyclomatic_complexity`, `comment_density`) are the only continuous metrics reported in the paper -- see this module's docstring. Each per-language row also reports `A median`/`C median`, `A Q3`/`C Q3` (75th percentile), and `A P90`/`C P90` (90th percentile) -- the median/Q3/P90 of the same per-repo mean values the Mann-Whitney test itself runs on, alongside (not a replacement for) the effect size and p-value. Q3/P90 exist to explain an effect that reaches significance despite identical medians -- a real difference concentrated in the upper tail, invisible to the median alone.

### loc

| Language | n_A | n_C | A median | C median | A Q3 | C Q3 | A P90 | C P90 | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Overall | 1687 | 2495 | -- | -- | -- | -- | -- | -- | U=1971070.0 | -0.063 | negligible | <.001 | -- |
| java | 125 | 312 | 8.00 | 6.50 | 10.25 | 9.40 | 13.80 | 15.00 | U=16227.0 | -0.168 | small | 0.006 | 0.012 |
| javascript | 143 | 563 | 5.13 | 4.80 | 8.00 | 7.96 | 12.93 | 12.96 | U=37493.5 | -0.069 | negligible | 0.204 | 0.204 |
| python | 678 | 1059 | 8.00 | 6.39 | 11.20 | 9.79 | 16.00 | 16.04 | U=299669.0 | -0.165 | small | <.001 | <.001 |
| typescript | 948 | 753 | 5.33 | 5.67 | 7.24 | 7.83 | 10.33 | 11.43 | U=374407.0 | 0.049 | negligible | 0.082 | 0.110 |

### cyclomatic_complexity

| Language | n_A | n_C | A median | C median | A Q3 | C Q3 | A P90 | C P90 | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Overall | 1687 | 2495 | -- | -- | -- | -- | -- | -- | U=1806030.0 | -0.142 | negligible | <.001 | -- |
| java | 125 | 312 | 1.07 | 1.00 | 1.33 | 1.13 | 1.72 | 1.50 | U=14963.5 | -0.233 | small | <.001 | <.001 |
| javascript | 143 | 563 | 1.00 | 1.00 | 1.33 | 1.00 | 1.67 | 1.21 | U=29511.0 | -0.267 | small | <.001 | <.001 |
| python | 678 | 1059 | 1.08 | 1.08 | 1.34 | 1.38 | 1.75 | 1.89 | U=359194.5 | 0.001 | negligible | 0.984 | 0.984 |
| typescript | 948 | 753 | 1.02 | 1.00 | 1.20 | 1.04 | 1.43 | 1.20 | U=280652.5 | -0.214 | small | <.001 | <.001 |

### comment_density

| Language | n_A | n_C | A median | C median | A Q3 | C Q3 | A P90 | C P90 | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Overall | 1687 | 2495 | -- | -- | -- | -- | -- | -- | U=1826610.0 | -0.132 | negligible | <.001 | -- |
| java | 125 | 312 | 0.00 | 0.00 | 0.04 | 0.00 | 0.08 | 0.05 | U=14481.0 | -0.257 | small | <.001 | <.001 |
| javascript | 143 | 563 | 0.00 | 0.00 | 0.03 | 0.00 | 0.10 | 0.04 | U=30357.0 | -0.246 | small | <.001 | <.001 |
| python | 678 | 1059 | 0.01 | 0.00 | 0.03 | 0.03 | 0.06 | 0.08 | U=351310.0 | -0.021 | negligible | 0.427 | 0.427 |
| typescript | 948 | 753 | 0.01 | 0.00 | 0.02 | 0.01 | 0.05 | 0.04 | U=314766.5 | -0.118 | negligible | <.001 | <.001 |

**Other Extracted Features (Not in the Paper)** -- `num_parameters` is still collected but dropped from Mann-Whitney testing entirely (see this module's docstring for why); shown here only as a descriptive floor-percentage footnote, not a comparative test.

**Floor-binding check (descriptive only -- not a comparative test)** -- `num_parameters` was dropped from Mann-Whitney testing (see this module's docstring) because it floors heavily in both datasets; this documents exactly how heavily, transparently, instead of silently omitting it.

| Metric | Floor value | Dataset A (agent-authored) at floor | Dataset C (human-authored, pre-LLM) at floor |
|---|---|---|---|
| num_parameters | 0 | 88.4% | 92.9% |

## Diagnostic: median-per-repo aggregation (NOT used in the paper)

**This section is presented for transparency only -- these are not results, do not cite them.** The paper's own methodology (above) takes each repo's *mean* fixture value, then reports the median across repos. This section instead takes each repo's own *median* fixture value first. That interacts badly with `cyclomatic_complexity`/`comment_density`'s heavy floor-binding (CC=1, comment_density=0 for most fixtures -- see this module's docstring): most repos' own median collapses to that exact floor value, producing near-universal ties across repos and starving Mann-Whitney of power. The per-language pattern below can and does diverge substantially from the paper's actual table above -- that divergence is the point of keeping this section, as a record of how sensitive the comparison is to this choice, not a competing result.

### loc

| Language | n_A | n_C | A median | C median | A Q3 | C Q3 | A P90 | C P90 | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Overall | 1687 | 2495 | -- | -- | -- | -- | -- | -- | U=2018087.0 | -0.041 | negligible | 0.023 | -- |
| java | 125 | 312 | 6.00 | 5.50 | 8.00 | 8.00 | 13.00 | 12.45 | U=17026.5 | -0.127 | negligible | 0.036 | 0.049 |
| javascript | 143 | 563 | 4.00 | 4.00 | 7.00 | 6.00 | 11.00 | 10.50 | U=37602.5 | -0.066 | negligible | 0.216 | 0.216 |
| python | 678 | 1059 | 6.00 | 5.00 | 8.50 | 7.00 | 13.00 | 12.00 | U=291072.0 | -0.189 | small | <.001 | <.001 |
| typescript | 948 | 753 | 4.00 | 4.00 | 5.00 | 6.00 | 7.00 | 8.00 | U=378603.5 | 0.061 | negligible | 0.028 | 0.049 |

### cyclomatic_complexity

| Language | n_A | n_C | A median | C median | A Q3 | C Q3 | A P90 | C P90 | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Overall | 1687 | 2495 | -- | -- | -- | -- | -- | -- | U=2116082.5 | 0.005 | negligible | 0.514 | -- |
| java | 125 | 312 | 1.00 | 1.00 | 1.00 | 1.00 | 1.50 | 1.50 | U=19162.0 | -0.017 | negligible | 0.602 | 0.602 |
| javascript | 143 | 563 | 1.00 | 1.00 | 1.00 | 1.00 | 1.50 | 1.00 | U=37173.0 | -0.077 | negligible | <.001 | 0.002 |
| python | 678 | 1059 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.50 | U=370789.5 | 0.033 | negligible | 0.039 | 0.051 |
| typescript | 948 | 753 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | U=346496.0 | -0.029 | negligible | 0.003 | 0.006 |

### comment_density

| Language | n_A | n_C | A median | C median | A Q3 | C Q3 | A P90 | C P90 | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Overall | 1687 | 2495 | -- | -- | -- | -- | -- | -- | U=2117002.0 | 0.006 | negligible | 0.462 | -- |
| java | 125 | 312 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | U=19475.5 | -0.001 | negligible | 0.967 | 0.967 |
| javascript | 143 | 563 | 0.00 | 0.00 | 0.00 | 0.00 | 0.08 | 0.00 | U=36429.0 | -0.095 | negligible | <.001 | 0.001 |
| python | 678 | 1059 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.02 | U=367795.5 | 0.024 | negligible | 0.086 | 0.173 |
| typescript | 948 | 753 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | U=351975.5 | -0.014 | negligible | 0.195 | 0.261 |
