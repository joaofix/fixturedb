# RQ2 -- General Metrics Overview

> How do agent-generated and human-written fixtures compare across structural metrics?

Generated: 2026-10-27 03:29:14 UTC

See [docs/research-questions.md](../docs/research-questions.md) for the full RQ2 definition.

## Per-dataset summary

### Dataset A (agent-authored) -- 85,136 fixtures

**Continuous metrics -- Paper** (repo-level: one mean per repo, not one value per fixture)

| Metric | n | median | mean | min | max | stdev |
|---|---|---|---|---|---|---|
| loc | 2,166 | 6.40 | 7.56 | 1 | 82 | 5.15 |
| cyclomatic_complexity | 2,166 | 1.06 | 1.22 | 1 | 7 | 0.43 |
| comment_density | 2,166 | 0.01 | 0.02 | 0 | 0 | 0.04 |

**Continuous metrics -- Other (not in the paper)** (repo-level: one mean per repo, not one value per fixture)

| Metric | n | median | mean | min | max | stdev |
|---|---|---|---|---|---|---|
| num_parameters | 2,167 | 0.00 | 0.18 | 0 | 4 | 0.37 |

**fixture_type distribution**

| Value | Count | % |
|---|---|---|
| before_each | 28,876 | 33.9% |
| after_each | 19,164 | 22.5% |
| pytest_decorator | 18,651 | 21.9% |
| before_all | 4,514 | 5.3% |
| unittest_setup | 4,253 | 5.0% |
| after_all | 3,540 | 4.2% |
| pytest_class_method | 1,132 | 1.3% |
| junit5_before_each | 1,131 | 1.3% |
| mocha_before | 951 | 1.1% |
| mocha_after | 851 | 1.0% |
| junit5_after_each | 687 | 0.8% |
| junit5_before_all | 455 | 0.5% |
| junit4_before | 248 | 0.3% |
| junit5_after_all | 219 | 0.3% |
| junit_rule | 151 | 0.2% |
| junit4_after | 126 | 0.1% |
| testng_before_method | 56 | 0.1% |
| junit4_before_class | 39 | 0.0% |
| junit_class_rule | 26 | 0.0% |
| testng_after_method | 20 | 0.0% |
| testng_before_class | 19 | 0.0% |
| testng_after_class | 14 | 0.0% |
| junit4_after_class | 9 | 0.0% |
| testng_before_test | 2 | 0.0% |
| junit3_setup | 1 | 0.0% |
| vitest_around_each | 1 | 0.0% |

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

6,762/85,136 fixtures (7.94%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 3,243 | 277 | 8.54% | typescript=179, python=94, javascript=4 |
| javascript | 5,566 | 1,953 | 35.09% | typescript=1,536, python=383, java=34 |
| python | 24,290 | 1,545 | 6.36% | typescript=1,182, javascript=202, java=161 |
| typescript | 52,037 | 2,987 | 5.74% | javascript=2,131, python=814, java=42 |

**agent_type distribution** (descriptive only, not compared against other datasets -- see load_dataset_metrics()'s docstring for why)

| Value | Count | % |
|---|---|---|
| claude | 71,471 | 83.9% |
| copilot | 5,452 | 6.4% |
| cursor | 3,999 | 4.7% |
| codex | 993 | 1.2% |
| openhands | 801 | 0.9% |
| devin | 699 | 0.8% |
| paperclip | 422 | 0.5% |
| gemini | 281 | 0.3% |
| letta_code | 252 | 0.3% |
| qwen_coder | 199 | 0.2% |
| jules | 148 | 0.2% |
| amp | 133 | 0.2% |
| langchain_open_swe | 96 | 0.1% |
| roo_code | 38 | 0.0% |
| gru | 29 | 0.0% |
| opencode | 27 | 0.0% |
| coderabbit | 19 | 0.0% |
| sourcery | 19 | 0.0% |
| aider | 17 | 0.0% |
| factory_droid | 8 | 0.0% |
| crush | 6 | 0.0% |
| chatgpt | 5 | 0.0% |
| deepsource | 4 | 0.0% |
| mistral_vibe | 4 | 0.0% |
| codegen | 3 | 0.0% |
| junie | 3 | 0.0% |
| sentry_seer | 3 | 0.0% |
| windsurf | 3 | 0.0% |
| generic | 1 | 0.0% |
| ona | 1 | 0.0% |

### Dataset C (human-authored, pre-LLM) -- 82,610 fixtures

**Continuous metrics -- Paper** (repo-level: one mean per repo, not one value per fixture)

| Metric | n | median | mean | min | max | stdev |
|---|---|---|---|---|---|---|
| loc | 2,550 | 6.00 | 8.03 | 1 | 195 | 9.11 |
| cyclomatic_complexity | 2,550 | 1.00 | 1.19 | 1 | 14 | 0.54 |
| comment_density | 2,550 | 0.00 | 0.02 | 0 | 0 | 0.05 |

**Continuous metrics -- Other (not in the paper)** (repo-level: one mean per repo, not one value per fixture)

| Metric | n | median | mean | min | max | stdev |
|---|---|---|---|---|---|---|
| num_parameters | 2,572 | 0.00 | 0.14 | 0 | 3 | 0.36 |

**fixture_type distribution**

| Value | Count | % |
|---|---|---|
| before_each | 30,560 | 37.0% |
| unittest_setup | 14,372 | 17.4% |
| pytest_decorator | 9,066 | 11.0% |
| after_each | 8,724 | 10.6% |
| mocha_before | 6,194 | 7.5% |
| before_all | 4,281 | 5.2% |
| mocha_after | 3,182 | 3.9% |
| after_all | 2,430 | 2.9% |
| junit4_before | 893 | 1.1% |
| pytest_class_method | 598 | 0.7% |
| junit_rule | 415 | 0.5% |
| junit4_before_class | 376 | 0.5% |
| junit4_after | 332 | 0.4% |
| junit4_after_class | 209 | 0.3% |
| junit5_before_each | 168 | 0.2% |
| junit_class_rule | 116 | 0.1% |
| testng_before_class | 102 | 0.1% |
| junit3_setup | 80 | 0.1% |
| testng_before_method | 80 | 0.1% |
| junit5_before_all | 75 | 0.1% |
| junit5_after_each | 71 | 0.1% |
| testng_after_class | 68 | 0.1% |
| testng_after_method | 36 | 0.0% |
| testng_before_suite | 32 | 0.0% |
| junit5_after_all | 31 | 0.0% |
| junit3_teardown | 30 | 0.0% |
| testng_before_test | 29 | 0.0% |
| after_class_ambiguous | 22 | 0.0% |
| before_class_ambiguous | 19 | 0.0% |
| testng_after_test | 12 | 0.0% |
| testng_after_suite | 5 | 0.0% |
| testng_before_groups | 2 | 0.0% |

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

7,483/82,610 fixtures (9.06%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 5,374 | 2,225 | 41.40% | typescript=1,104, python=1,003, javascript=118 |
| javascript | 6,847 | 2,536 | 37.04% | typescript=2,176, python=336, java=24 |
| python | 23,729 | 1,223 | 5.15% | typescript=980, javascript=223, java=20 |
| typescript | 46,660 | 1,499 | 3.21% | javascript=1,298, python=191, java=10 |

**agent_type distribution** (descriptive only, not compared against other datasets -- see load_dataset_metrics()'s docstring for why)

| Value | Count | % |
|---|---|---|
| human_pre2022 | 82,610 | 100.0% |

## A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)

**Paper Metrics -- Continuous** (Mann-Whitney U on repo-level values, two-sided) -- one mean value per repo (per language, for the per-language rows), not per fixture, so fixtures clustering within a repo can't inflate the result. Effect size is Cliff's delta (thresholds: negligible <0.147, small <0.33, medium <0.474, else large; positive means the comparison dataset tends to have larger values than A, negative means A tends to have larger values). The Overall row is a single pooled test, not BH-corrected; each metric's per-language rows are BH-FDR corrected against each other only (one family per metric, 4 languages). These three (`loc`, `cyclomatic_complexity`, `comment_density`) are the only continuous metrics reported in the paper -- see this module's docstring. Each per-language row also reports `A median`/`C median`, `A Q3`/`C Q3` (75th percentile), and `A P90`/`C P90` (90th percentile) -- the median/Q3/P90 of the same per-repo mean values the Mann-Whitney test itself runs on, alongside (not a replacement for) the effect size and p-value. Q3/P90 exist to explain an effect that reaches significance despite identical medians -- a real difference concentrated in the upper tail, invisible to the median alone.

### loc

| Language | n_A | n_C | A median | C median | A Q3 | C Q3 | A P90 | C P90 | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Overall | 2166 | 2550 | -- | -- | -- | -- | -- | -- | U=2629711.0 | -0.048 | negligible | 0.005 | -- |
| java | 173 | 353 | 8.00 | 7.00 | 10.50 | 10.00 | 13.98 | 14.19 | U=26594.5 | -0.129 | negligible | 0.016 | 0.032 |
| javascript | 211 | 592 | 5.02 | 5.00 | 8.51 | 8.00 | 12.64 | 13.00 | U=61833.5 | -0.010 | negligible | 0.830 | 0.830 |
| python | 856 | 1062 | 8.00 | 6.42 | 11.26 | 10.00 | 15.33 | 16.00 | U=386885.0 | -0.149 | small | <.001 | <.001 |
| typescript | 1198 | 749 | 5.41 | 5.65 | 7.33 | 7.79 | 10.24 | 11.34 | U=466150.0 | 0.039 | negligible | 0.147 | 0.196 |

### cyclomatic_complexity

| Language | n_A | n_C | A median | C median | A Q3 | C Q3 | A P90 | C P90 | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Overall | 2166 | 2550 | -- | -- | -- | -- | -- | -- | U=2374211.0 | -0.140 | negligible | <.001 | -- |
| java | 173 | 353 | 1.07 | 1.00 | 1.36 | 1.15 | 1.79 | 1.58 | U=23844.5 | -0.219 | small | <.001 | <.001 |
| javascript | 211 | 592 | 1.00 | 1.00 | 1.33 | 1.00 | 1.80 | 1.22 | U=45561.0 | -0.271 | small | <.001 | <.001 |
| python | 856 | 1062 | 1.11 | 1.09 | 1.41 | 1.40 | 1.89 | 1.90 | U=445792.0 | -0.019 | negligible | 0.451 | 0.451 |
| typescript | 1198 | 749 | 1.02 | 1.00 | 1.19 | 1.04 | 1.41 | 1.20 | U=354804.5 | -0.209 | small | <.001 | <.001 |

### comment_density

| Language | n_A | n_C | A median | C median | A Q3 | C Q3 | A P90 | C P90 | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Overall | 2166 | 2550 | -- | -- | -- | -- | -- | -- | U=2489470.0 | -0.099 | negligible | <.001 | -- |
| java | 173 | 353 | 0.00 | 0.00 | 0.03 | 0.01 | 0.06 | 0.06 | U=24901.0 | -0.184 | small | <.001 | <.001 |
| javascript | 211 | 592 | 0.00 | 0.00 | 0.03 | 0.01 | 0.09 | 0.05 | U=49865.0 | -0.202 | small | <.001 | <.001 |
| python | 856 | 1062 | 0.01 | 0.01 | 0.03 | 0.03 | 0.06 | 0.08 | U=455785.5 | 0.003 | negligible | 0.914 | 0.914 |
| typescript | 1198 | 749 | 0.00 | 0.00 | 0.02 | 0.01 | 0.05 | 0.04 | U=412202.5 | -0.081 | negligible | 0.001 | 0.002 |

**Other Extracted Features (Not in the Paper)** -- `num_parameters` is still collected but dropped from Mann-Whitney testing entirely (see this module's docstring for why); shown here only as a descriptive floor-percentage footnote, not a comparative test.

**Floor-binding check (descriptive only -- not a comparative test)** -- `num_parameters` was dropped from Mann-Whitney testing (see this module's docstring) because it floors heavily in both datasets; this documents exactly how heavily, transparently, instead of silently omitting it.

| Metric | Floor value | Dataset A (agent-authored) at floor | Dataset C (human-authored, pre-LLM) at floor |
|---|---|---|---|
| num_parameters | 0 | 88.1% | 92.9% |

## Diagnostic: median-per-repo aggregation (NOT used in the paper)

**This section is presented for transparency only -- these are not results, do not cite them.** The paper's own methodology (above) takes each repo's *mean* fixture value, then reports the median across repos. This section instead takes each repo's own *median* fixture value first. That interacts badly with `cyclomatic_complexity`/`comment_density`'s heavy floor-binding (CC=1, comment_density=0 for most fixtures -- see this module's docstring): most repos' own median collapses to that exact floor value, producing near-universal ties across repos and starving Mann-Whitney of power. The per-language pattern below can and does diverge substantially from the paper's actual table above -- that divergence is the point of keeping this section, as a record of how sensitive the comparison is to this choice, not a competing result.

### loc

| Language | n_A | n_C | A median | C median | A Q3 | C Q3 | A P90 | C P90 | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Overall | 2166 | 2550 | -- | -- | -- | -- | -- | -- | U=2665039.0 | -0.035 | negligible | 0.037 | -- |
| java | 173 | 353 | 6.00 | 6.00 | 8.50 | 8.00 | 13.00 | 13.00 | U=26928.5 | -0.118 | negligible | 0.026 | 0.037 |
| javascript | 211 | 592 | 4.00 | 4.00 | 6.50 | 6.00 | 11.00 | 11.00 | U=62797.0 | 0.005 | negligible | 0.905 | 0.905 |
| python | 856 | 1062 | 6.00 | 4.50 | 8.50 | 7.00 | 12.75 | 12.00 | U=364278.0 | -0.199 | small | <.001 | <.001 |
| typescript | 1198 | 749 | 4.00 | 4.00 | 5.00 | 6.00 | 7.00 | 9.00 | U=474664.5 | 0.058 | negligible | 0.028 | 0.037 |

### cyclomatic_complexity

| Language | n_A | n_C | A median | C median | A Q3 | C Q3 | A P90 | C P90 | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Overall | 2166 | 2550 | -- | -- | -- | -- | -- | -- | U=2735994.5 | -0.009 | negligible | 0.225 | -- |
| java | 173 | 353 | 1.00 | 1.00 | 1.00 | 1.00 | 1.50 | 1.00 | U=29282.0 | -0.041 | negligible | 0.143 | 0.191 |
| javascript | 211 | 592 | 1.00 | 1.00 | 1.00 | 1.00 | 1.50 | 1.00 | U=57812.5 | -0.074 | negligible | <.001 | <.001 |
| python | 856 | 1062 | 1.00 | 1.00 | 1.00 | 1.00 | 1.50 | 1.50 | U=453711.0 | -0.002 | negligible | 0.902 | 0.902 |
| typescript | 1198 | 749 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | U=435443.5 | -0.029 | negligible | 0.001 | 0.002 |

### comment_density

| Language | n_A | n_C | A median | C median | A Q3 | C Q3 | A P90 | C P90 | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Overall | 2166 | 2550 | -- | -- | -- | -- | -- | -- | U=2769011.5 | 0.003 | negligible | 0.718 | -- |
| java | 173 | 353 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | U=31127.0 | 0.019 | negligible | 0.465 | 0.465 |
| javascript | 211 | 592 | 0.00 | 0.00 | 0.00 | 0.00 | 0.08 | 0.00 | U=57802.0 | -0.075 | negligible | 0.002 | 0.006 |
| python | 856 | 1062 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | U=460501.5 | 0.013 | negligible | 0.308 | 0.465 |
| typescript | 1198 | 749 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | U=444444.0 | -0.009 | negligible | 0.350 | 0.465 |
