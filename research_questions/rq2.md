# RQ2 -- Setup and Teardown Characterization

> How do agent-generated fixtures compare to human-written ones in setup and teardown provision?

Generated: 2026-08-21 00:06:38 UTC

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

Per-repository proportions: for each repo, `setup_pct`/`teardown_pct`/`other_pct` = that repo's setup/teardown/other-classified fixtures divided by its total classified fixtures (the three sum to 100% per repo; `other_pct` isn't shown below). Median is taken over those per-repo proportions, not a single pooled fixture-level percentage. "V (A↔C)"/"p (BH)" are the `setup` category's own repo-level Mann-Whitney U + Cliff's delta test (`setup`/`teardown` aren't independent -- together with `other` they sum to 100% per repo -- so this one test represents the row). The column is labeled "V" for consistency with the paper's other effect-size columns, but the number is Cliff's delta, not literally Cramer's V. Overall is a single pooled test (raw p, never BH-corrected); each language's p is BH-FDR-corrected against the other 3 languages' `setup` tests only.

| Language | n_A | n_C | Setup A (%) | Setup C (%) | Teardown A (%) | Teardown C (%) | V (A↔C) | p (BH) |
|---|---|---|---|---|---|---|---|---|
| Overall | 1354 | 2325 | 50.0% | 66.7% | 22.2% | 2.3% | 0.235 (small) | <.001 |
| java | 97 | 267 | 66.7% | 66.7% | 25.0% | 0.0% | -0.130 (negligible) | 0.051 |
| javascript | 115 | 557 | 55.6% | 81.0% | 44.4% | 19.0% | 0.217 (small) | <.001 |
| python | 531 | 944 | 0.0% | 37.8% | 0.0% | 0.0% | 0.328 (small) | <.001 |
| typescript | 749 | 735 | 57.1% | 78.6% | 42.9% | 21.4% | 0.315 (small) | <.001 |

## Unimodality Check: Python Teardown Proportion (Dip Test)

Hartigan & Hartigan's dip test for unimodality [CITE: Hartigan & Hartigan 1985, The Dip Test of Unimodality], run on the same per-repo Python `teardown_pct` values the table above summarizes as a single median -- separately per dataset, since this tests whether *one* distribution is unimodal, not whether two distributions differ. Null hypothesis: the distribution is unimodal; a low p-value is evidence of multimodality (e.g. a real "most repos provide none, a distinct minority provide all" split, rather than a smooth continuum from 0% to 100%).

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
