# RQ2 -- Setup and Teardown Characterization

> How do agent-generated fixtures compare to human-written ones in setup and teardown provision?

Generated: 2026-08-31 20:52:47 UTC

See [docs/research-questions.md](../docs/research-questions.md) for the full RQ2 definition.

## Per-dataset summary

### Dataset A (agent-authored) -- 67,979 fixtures

**fixture_type kind distribution**

| Kind | Count | % |
|---|---|---|
| setup | 44,157 | 65.0% |
| teardown | 19,775 | 29.1% |
| setup_and_teardown | 3,858 | 5.7% |
| other | 189 | 0.3% |

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

5,043/67,979 fixtures (7.42%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 2,083 | 232 | 11.14% | typescript=145, python=86, javascript=1 |
| javascript | 3,873 | 1,173 | 30.29% | typescript=990, python=160, java=23 |
| python | 20,148 | 1,192 | 5.92% | typescript=907, javascript=152, java=133 |
| typescript | 41,875 | 2,446 | 5.84% | javascript=1,894, python=520, java=32 |

### Dataset C (human-authored, pre-LLM) -- 67,979 fixtures

**fixture_type kind distribution**

| Kind | Count | % |
|---|---|---|
| setup | 50,022 | 73.6% |
| teardown | 16,152 | 23.8% |
| setup_and_teardown | 1,236 | 1.8% |
| other | 569 | 0.8% |

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

6,214/67,979 fixtures (9.14%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 3,897 | 1,883 | 48.32% | typescript=985, python=819, javascript=79 |
| javascript | 5,467 | 2,067 | 37.81% | typescript=1,791, python=267, java=9 |
| python | 19,523 | 1,026 | 5.26% | typescript=841, javascript=172, java=13 |
| typescript | 39,092 | 1,238 | 3.17% | javascript=1,096, python=139, java=3 |

## A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)

### Table 1: Fixture Counts by Type (tab:rq2-counts)

Raw counts of setup-classified and teardown-classified fixtures ("other"-classified fixtures, e.g. a bare `@pytest.fixture`, are excluded from both columns; a fixture classified as providing both -- e.g. a pytest fixture with setup code before its `yield` -- is counted in both columns, so they are not mutually exclusive). Total is the dataset-wide sum across every language present, not just the four rows below. Purely descriptive -- no significance test.

| Language | Setup A | Setup C | Teardown A | Teardown C |
|---|---|---|---|---|
| Total | 48,015 | 51,258 | 23,633 | 17,388 |
| java | 1,270 | 987 | 609 | 499 |
| javascript | 2,782 | 3,344 | 1,965 | 1,403 |
| python | 18,619 | 16,142 | 4,932 | 4,800 |
| typescript | 25,344 | 30,785 | 16,127 | 10,686 |

### Table 2: Teardown Coverage by Repository (tab:rq2-coverage)

Per-repository binary coverage: 1 if a repo has >=1 teardown-classified fixture, else 0 (population: repos with >=1 setup/teardown/other-classified fixture). "Coverage A/C (%)" is the share of that population with the indicator at 1. "delta" is Cliff's delta from a Mann-Whitney U test on the indicator between datasets. Overall is a single pooled test (raw p, never BH-corrected); each language's p is BH-FDR-corrected against the other 3 languages' tests only.

| Language | n_A | n_C | Coverage A (%) | Coverage C (%) | delta | p (BH) |
|---|---|---|---|---|---|---|
| Overall | 1647 | 2472 | 77.6% | 62.4% | -0.152 (small) | <.001 |
| java | 122 | 315 | 63.9% | 47.0% | -0.170 (small) | 0.001 |
| javascript | 137 | 563 | 77.4% | 58.8% | -0.186 (small) | <.001 |
| python | 656 | 1045 | 67.4% | 58.4% | -0.090 (negligible) | <.001 |
| typescript | 928 | 749 | 84.6% | 71.7% | -0.129 (negligible) | <.001 |

## Supplementary Analyses

Analyses below are not part of either main paper table (tab:rq2-counts, tab:rq2-coverage) but are kept and computed since they may still be referenced in prose.

### Unimodality Check: Python Teardown Proportion (Dip Test)

Hartigan & Hartigan's dip test for unimodality [CITE: Hartigan & Hartigan 1985, The Dip Test of Unimodality], run on the per-repo Python `teardown_pct` distribution (each repo's teardown-classified fixtures divided by its total classified fixtures) -- separately per dataset, since this tests whether *one* distribution is unimodal, not whether two distributions differ. Not the same value as Table 2's binary coverage indicator. Null hypothesis: the distribution is unimodal; a low p-value is evidence of multimodality (e.g. a real "most repos provide none, a distinct minority provide all" split, rather than a smooth continuum from 0% to 100%).

| Dataset | n (Python repos) | Dip statistic | p-value |
|---|---|---|---|
| Dataset A | 656 | 0.0320 | <.001 |
| Dataset C | 1045 | 0.0297 | <.001 |

**Dataset A -- teardown_pct distribution across 656 Python repos**

```
 0.00- 0.10 | ######################################## (258)
 0.10- 0.20 | ########## (64)
 0.20- 0.30 | ############ (78)
 0.30- 0.40 | ########## (67)
 0.40- 0.50 | ####### (45)
 0.50- 0.60 | ######### (59)
 0.60- 0.70 | #### (27)
 0.70- 0.80 | ## (10)
 0.80- 0.90 | # (5)
 0.90- 1.00 | ####### (43)
```

**Dataset C -- teardown_pct distribution across 1045 Python repos**

```
 0.00- 0.10 | ######################################## (501)
 0.10- 0.20 | ######## (99)
 0.20- 0.30 | ######## (102)
 0.30- 0.40 | ###### (76)
 0.40- 0.50 | #### (52)
 0.50- 0.60 | ######## (97)
 0.60- 0.70 | ## (30)
 0.70- 0.80 | # (13)
 0.80- 0.90 | # (9)
 0.90- 1.00 | ##### (66)
```
