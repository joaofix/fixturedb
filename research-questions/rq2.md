# RQ2 -- General Metrics Overview

> How do agent-generated and human-written fixtures compare across structural metrics?

Generated: 2026-10-07 13:35:44 UTC

See [docs/research-questions.md](../docs/research-questions.md) for the full RQ2 definition.

## Per-dataset summary

### Dataset A (agent-authored) -- 85,206 fixtures

**Continuous metrics -- Paper** (repo-level: one mean per repo, not one value per fixture)

| Metric | n | median | mean | min | max | stdev |
|---|---|---|---|---|---|---|
| loc | 2,168 | 6.41 | 7.56 | 1 | 82 | 5.14 |
| cyclomatic_complexity | 2,168 | 1.06 | 1.22 | 1 | 7 | 0.42 |
| comment_density | 2,168 | 0.01 | 0.02 | 0 | 0 | 0.04 |

**Continuous metrics -- Other (not in the paper)** (repo-level: one mean per repo, not one value per fixture)

| Metric | n | median | mean | min | max | stdev |
|---|---|---|---|---|---|---|
| num_parameters | 2,169 | 0.00 | 0.18 | 0 | 4 | 0.37 |

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
| testng_data_provider | 70 | 0.1% |
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

6,765/85,206 fixtures (7.94%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 3,310 | 277 | 8.37% | typescript=179, python=94, javascript=4 |
| javascript | 5,566 | 1,953 | 35.09% | typescript=1,536, python=383, java=34 |
| python | 24,293 | 1,548 | 6.37% | typescript=1,182, javascript=202, java=164 |
| typescript | 52,037 | 2,987 | 5.74% | javascript=2,131, python=814, java=42 |

**agent_type distribution** (descriptive only, not compared against other datasets -- see load_dataset_metrics()'s docstring for why)

| Value | Count | % |
|---|---|---|
| claude | 71,530 | 83.9% |
| copilot | 5,462 | 6.4% |
| cursor | 4,000 | 4.7% |
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

### Dataset C (human-authored, pre-LLM) -- 82,680 fixtures

**Continuous metrics -- Paper** (repo-level: one mean per repo, not one value per fixture)

| Metric | n | median | mean | min | max | stdev |
|---|---|---|---|---|---|---|
| loc | 2,537 | 6.00 | 7.94 | 1 | 199 | 8.70 |
| cyclomatic_complexity | 2,537 | 1.00 | 1.19 | 1 | 14 | 0.53 |
| comment_density | 2,537 | 0.00 | 0.02 | 0 | 0 | 0.04 |

**Continuous metrics -- Other (not in the paper)** (repo-level: one mean per repo, not one value per fixture)

| Metric | n | median | mean | min | max | stdev |
|---|---|---|---|---|---|---|
| num_parameters | 2,549 | 0.00 | 0.14 | 0 | 3 | 0.36 |

**fixture_type distribution**

| Value | Count | % |
|---|---|---|
| before_each | 30,565 | 37.0% |
| unittest_setup | 14,359 | 17.4% |
| pytest_decorator | 9,080 | 11.0% |
| after_each | 8,721 | 10.5% |
| mocha_before | 6,204 | 7.5% |
| before_all | 4,280 | 5.2% |
| mocha_after | 3,176 | 3.8% |
| after_all | 2,425 | 2.9% |
| junit4_before | 764 | 0.9% |
| pytest_class_method | 597 | 0.7% |
| junit_rule | 417 | 0.5% |
| junit4_before_class | 356 | 0.4% |
| junit4_after | 328 | 0.4% |
| testng_data_provider | 282 | 0.3% |
| junit4_after_class | 213 | 0.3% |
| junit5_before_each | 184 | 0.2% |
| testng_before_class | 91 | 0.1% |
| junit_class_rule | 83 | 0.1% |
| testng_before_method | 75 | 0.1% |
| junit5_after_each | 72 | 0.1% |
| testng_after_class | 66 | 0.1% |
| junit5_before_all | 57 | 0.1% |
| junit3_setup | 55 | 0.1% |
| junit5_after_all | 41 | 0.0% |
| junit3_teardown | 38 | 0.0% |
| testng_before_suite | 30 | 0.0% |
| testng_before_test | 30 | 0.0% |
| testng_after_method | 29 | 0.0% |
| before_class_ambiguous | 22 | 0.0% |
| after_class_ambiguous | 21 | 0.0% |
| testng_after_test | 12 | 0.0% |
| testng_after_suite | 3 | 0.0% |
| testng_factory | 3 | 0.0% |
| testng_before_groups | 1 | 0.0% |

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

7,480/82,680 fixtures (9.05%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 5,453 | 2,217 | 40.66% | typescript=1,104, python=1,003, javascript=110 |
| javascript | 6,820 | 2,523 | 36.99% | typescript=2,176, python=336, java=11 |
| python | 23,728 | 1,222 | 5.15% | typescript=980, javascript=226, java=16 |
| typescript | 46,679 | 1,518 | 3.25% | javascript=1,317, python=191, java=10 |

**agent_type distribution** (descriptive only, not compared against other datasets -- see load_dataset_metrics()'s docstring for why)

| Value | Count | % |
|---|---|---|
| human_pre2022 | 82,680 | 100.0% |

## A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)

**Paper Metrics -- Continuous** (Mann-Whitney U on repo-level values, two-sided) -- one mean value per repo (per language, for the per-language rows), not per fixture, so fixtures clustering within a repo can't inflate the result. Effect size is Cliff's delta (thresholds: negligible <0.147, small <0.33, medium <0.474, else large; positive means the comparison dataset tends to have larger values than A, negative means A tends to have larger values). The Overall row is a single pooled test, not BH-corrected; each metric's per-language rows are BH-FDR corrected against each other only (one family per metric, 4 languages). These three (`loc`, `cyclomatic_complexity`, `comment_density`) are the only continuous metrics reported in the paper -- see this module's docstring. Each per-language row also reports `A median`/`C median`, `A Q3`/`C Q3` (75th percentile), and `A P90`/`C P90` (90th percentile) -- the median/Q3/P90 of the same per-repo mean values the Mann-Whitney test itself runs on, alongside (not a replacement for) the effect size and p-value. Q3/P90 exist to explain an effect that reaches significance despite identical medians -- a real difference concentrated in the upper tail, invisible to the median alone.

### loc

| Language | n_A | n_C | A median | C median | A Q3 | C Q3 | A P90 | C P90 | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Overall | 2168 | 2537 | -- | -- | -- | -- | -- | -- | U=2616902.0 | -0.048 | negligible | 0.004 | -- |
| java | 175 | 342 | 8.00 | 7.00 | 10.62 | 10.50 | 14.00 | 15.12 | U=26376.0 | -0.119 | negligible | 0.027 | 0.054 |
| javascript | 211 | 589 | 5.02 | 5.00 | 8.51 | 8.09 | 12.64 | 13.00 | U=61212.5 | -0.015 | negligible | 0.747 | 0.747 |
| python | 856 | 1061 | 8.00 | 6.43 | 11.26 | 10.00 | 15.33 | 16.00 | U=387292.0 | -0.147 | small | <.001 | <.001 |
| typescript | 1198 | 749 | 5.41 | 5.65 | 7.33 | 7.79 | 10.24 | 11.34 | U=466150.0 | 0.039 | negligible | 0.147 | 0.196 |

### cyclomatic_complexity

| Language | n_A | n_C | A median | C median | A Q3 | C Q3 | A P90 | C P90 | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Overall | 2168 | 2537 | -- | -- | -- | -- | -- | -- | U=2367552.0 | -0.139 | negligible | <.001 | -- |
| java | 175 | 342 | 1.08 | 1.00 | 1.36 | 1.17 | 1.78 | 1.67 | U=23481.5 | -0.215 | small | <.001 | <.001 |
| javascript | 211 | 589 | 1.00 | 1.00 | 1.33 | 1.00 | 1.80 | 1.18 | U=44981.0 | -0.276 | small | <.001 | <.001 |
| python | 856 | 1061 | 1.11 | 1.10 | 1.41 | 1.40 | 1.89 | 1.89 | U=447696.0 | -0.014 | negligible | 0.581 | 0.581 |
| typescript | 1198 | 749 | 1.02 | 1.00 | 1.19 | 1.04 | 1.41 | 1.20 | U=354804.5 | -0.209 | small | <.001 | <.001 |

### comment_density

| Language | n_A | n_C | A median | C median | A Q3 | C Q3 | A P90 | C P90 | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Overall | 2168 | 2537 | -- | -- | -- | -- | -- | -- | U=2478668.0 | -0.099 | negligible | <.001 | -- |
| java | 175 | 342 | 0.00 | 0.00 | 0.03 | 0.01 | 0.07 | 0.05 | U=24069.0 | -0.196 | small | <.001 | <.001 |
| javascript | 211 | 589 | 0.00 | 0.00 | 0.03 | 0.01 | 0.09 | 0.05 | U=49211.5 | -0.208 | small | <.001 | <.001 |
| python | 856 | 1061 | 0.01 | 0.01 | 0.03 | 0.03 | 0.06 | 0.08 | U=455503.0 | 0.003 | negligible | 0.904 | 0.904 |
| typescript | 1198 | 749 | 0.00 | 0.00 | 0.02 | 0.01 | 0.05 | 0.04 | U=412202.5 | -0.081 | negligible | 0.001 | 0.002 |

**Other Extracted Features (Not in the Paper)** -- `num_parameters` is still collected but dropped from Mann-Whitney testing entirely (see this module's docstring for why); shown here only as a descriptive floor-percentage footnote, not a comparative test.

**Floor-binding check (descriptive only -- not a comparative test)** -- `num_parameters` was dropped from Mann-Whitney testing (see this module's docstring) because it floors heavily in both datasets; this documents exactly how heavily, transparently, instead of silently omitting it.

| Metric | Floor value | Dataset A (agent-authored) at floor | Dataset C (human-authored, pre-LLM) at floor |
|---|---|---|---|
| num_parameters | 0 | 88.1% | 92.8% |

## Diagnostic: median-per-repo aggregation (NOT used in the paper)

**This section is presented for transparency only -- these are not results, do not cite them.** The paper's own methodology (above) takes each repo's *mean* fixture value, then reports the median across repos. This section instead takes each repo's own *median* fixture value first. That interacts badly with `cyclomatic_complexity`/`comment_density`'s heavy floor-binding (CC=1, comment_density=0 for most fixtures -- see this module's docstring): most repos' own median collapses to that exact floor value, producing near-universal ties across repos and starving Mann-Whitney of power. The per-language pattern below can and does diverge substantially from the paper's actual table above -- that divergence is the point of keeping this section, as a record of how sensitive the comparison is to this choice, not a competing result.

### loc

| Language | n_A | n_C | A median | C median | A Q3 | C Q3 | A P90 | C P90 | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Overall | 2168 | 2537 | -- | -- | -- | -- | -- | -- | U=2654203.0 | -0.035 | negligible | 0.037 | -- |
| java | 175 | 342 | 6.00 | 6.00 | 8.50 | 8.50 | 12.00 | 13.00 | U=27307.5 | -0.087 | negligible | 0.100 | 0.134 |
| javascript | 211 | 589 | 4.00 | 4.00 | 6.50 | 6.00 | 11.00 | 10.60 | U=61781.5 | -0.006 | negligible | 0.900 | 0.900 |
| python | 856 | 1061 | 6.00 | 4.50 | 8.50 | 7.00 | 12.75 | 12.00 | U=362094.0 | -0.203 | small | <.001 | <.001 |
| typescript | 1198 | 749 | 4.00 | 4.00 | 5.00 | 6.00 | 7.00 | 9.00 | U=474664.5 | 0.058 | negligible | 0.028 | 0.056 |

### cyclomatic_complexity

| Language | n_A | n_C | A median | C median | A Q3 | C Q3 | A P90 | C P90 | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Overall | 2168 | 2537 | -- | -- | -- | -- | -- | -- | U=2735665.5 | -0.005 | negligible | 0.499 | -- |
| java | 175 | 342 | 1.00 | 1.00 | 1.00 | 1.00 | 1.50 | 1.50 | U=29205.0 | -0.024 | negligible | 0.414 | 0.552 |
| javascript | 211 | 589 | 1.00 | 1.00 | 1.00 | 1.00 | 1.50 | 1.00 | U=57605.5 | -0.073 | negligible | <.001 | 0.001 |
| python | 856 | 1061 | 1.00 | 1.00 | 1.00 | 1.00 | 1.50 | 1.50 | U=455323.5 | 0.003 | negligible | 0.856 | 0.856 |
| typescript | 1198 | 749 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | U=435443.5 | -0.029 | negligible | 0.001 | 0.002 |

### comment_density

| Language | n_A | n_C | A median | C median | A Q3 | C Q3 | A P90 | C P90 | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Overall | 2168 | 2537 | -- | -- | -- | -- | -- | -- | U=2754163.5 | 0.001 | negligible | 0.841 | -- |
| java | 175 | 342 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | U=30117.0 | 0.006 | negligible | 0.806 | 0.806 |
| javascript | 211 | 589 | 0.00 | 0.00 | 0.00 | 0.00 | 0.08 | 0.00 | U=57480.5 | -0.075 | negligible | 0.001 | 0.006 |
| python | 856 | 1061 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | U=460253.0 | 0.014 | negligible | 0.293 | 0.467 |
| typescript | 1198 | 749 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | U=444444.0 | -0.009 | negligible | 0.350 | 0.467 |
