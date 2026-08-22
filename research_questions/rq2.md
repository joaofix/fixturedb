# RQ2 -- Setup and Teardown Characterization

> How do agent-generated fixtures compare to human-written ones in setup and teardown provision?

Generated: 2026-08-22 18:49:49 UTC

See [docs/research-questions.md](../docs/research-questions.md) for the full RQ2 definition.

## Per-dataset summary

### Dataset A (agent-authored) -- 47,208 fixtures

**fixture_type kind distribution**

| Kind | Count | % |
|---|---|---|
| setup | 23,759 | 50.3% |
| teardown | 14,942 | 31.7% |
| other | 8,507 | 18.0% |

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

3,561/47,208 fixtures (7.54%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 1,429 | 111 | 7.77% | typescript=83, python=27, javascript=1 |
| javascript | 3,385 | 962 | 28.42% | typescript=797, python=142, java=23 |
| python | 11,000 | 492 | 4.47% | typescript=323, javascript=144, java=25 |
| typescript | 31,394 | 1,996 | 6.36% | javascript=1,606, python=358, java=32 |

### Dataset C (human-authored, pre-LLM) -- 47,208 fixtures

**fixture_type kind distribution**

| Kind | Count | % |
|---|---|---|
| setup | 31,339 | 66.4% |
| teardown | 11,372 | 24.1% |
| other | 4,497 | 9.5% |

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

4,318/47,208 fixtures (9.15%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 2,541 | 1,168 | 45.97% | typescript=684, python=428, javascript=56 |
| javascript | 4,454 | 1,385 | 31.10% | typescript=1,223, python=156, java=6 |
| python | 11,119 | 758 | 6.82% | typescript=607, javascript=135, java=16 |
| typescript | 29,094 | 1,007 | 3.46% | javascript=914, python=90, java=3 |

## A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)

### Table 1: Fixture Counts by Type (tab:rq2-counts)

Raw counts of setup-classified and teardown-classified fixtures ("other"-classified fixtures, e.g. a bare `@pytest.fixture`, are excluded from both columns). Total is the dataset-wide sum across every language present, not just the four rows below. Purely descriptive -- no significance test.

| Language | Setup A | Setup C | Teardown A | Teardown C |
|---|---|---|---|---|
| Total | 23,759 | 31,339 | 14,942 | 11,372 |
| java | 894 | 708 | 422 | 355 |
| javascript | 2,471 | 2,892 | 1,703 | 1,282 |
| python | 1,890 | 4,951 | 720 | 1,922 |
| typescript | 18,504 | 22,788 | 12,097 | 7,813 |

### Table 2: Teardown Coverage by Repository (tab:rq2-coverage)

Per-repository binary coverage: 1 if a repo has >=1 teardown-classified fixture, else 0 (population: repos with >=1 setup/teardown/other-classified fixture). "Coverage A/C (%)" is the share of that population with the indicator at 1. "delta" is Cliff's delta from a Mann-Whitney U test on the indicator between datasets. Overall is a single pooled test (raw p, never BH-corrected); each language's p is BH-FDR-corrected against the other 3 languages' tests only.

| Language | n_A | n_C | Coverage A (%) | Coverage C (%) | delta | p (BH) |
|---|---|---|---|---|---|---|
| Overall | 1354 | 2325 | 61.4% | 50.3% | -0.111 (negligible) | <.001 |
| java | 97 | 267 | 66.0% | 47.2% | -0.188 (small) | 0.002 |
| javascript | 115 | 557 | 77.4% | 55.5% | -0.219 (small) | <.001 |
| python | 531 | 944 | 19.4% | 32.0% | 0.126 (negligible) | <.001 |
| typescript | 749 | 735 | 84.8% | 68.0% | -0.168 (small) | <.001 |

## Supplementary Analyses

Analyses below are not part of either main paper table (tab:rq2-counts, tab:rq2-coverage) but are kept and computed since they may still be referenced in prose.

### Unimodality Check: Python Teardown Proportion (Dip Test)

Hartigan & Hartigan's dip test for unimodality [CITE: Hartigan & Hartigan 1985, The Dip Test of Unimodality], run on the per-repo Python `teardown_pct` distribution (each repo's teardown-classified fixtures divided by its total classified fixtures) -- separately per dataset, since this tests whether *one* distribution is unimodal, not whether two distributions differ. Not the same value as Table 2's binary coverage indicator. Null hypothesis: the distribution is unimodal; a low p-value is evidence of multimodality (e.g. a real "most repos provide none, a distinct minority provide all" split, rather than a smooth continuum from 0% to 100%).

| Dataset | n (Python repos) | Dip statistic | p-value |
|---|---|---|---|
| Dataset A | 531 | 0.0141 | 0.723 |
| Dataset C | 944 | 0.0228 | 0.002 |

**Dataset A -- teardown_pct distribution across 531 Python repos**

```
 0.00- 0.10 | ######################################## (449)
 0.10- 0.20 | ## (27)
 0.20- 0.30 | # (16)
 0.30- 0.40 | # (10)
 0.40- 0.50 | # (9)
 0.50- 0.60 | # (16)
 0.60- 0.70 |  (1)
 0.70- 0.80 |  (1)
 0.80- 0.90 |  (0)
 0.90- 1.00 |  (2)
```

**Dataset C -- teardown_pct distribution across 944 Python repos**

```
 0.00- 0.10 | ######################################## (665)
 0.10- 0.20 | ### (50)
 0.20- 0.30 | ### (57)
 0.30- 0.40 | ### (46)
 0.40- 0.50 | ## (26)
 0.50- 0.60 | ### (56)
 0.60- 0.70 | # (16)
 0.70- 0.80 |  (3)
 0.80- 0.90 |  (3)
 0.90- 1.00 | # (22)
```
