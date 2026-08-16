# RQ2 -- Setup and Teardown Characterization

> How do agent-generated fixtures compare to human-written ones in setup and teardown provision?

Generated: 2026-08-16 01:51:14 UTC

See [docs/research-questions.md](../docs/research-questions.md) for the full RQ2 definition.

## Per-dataset summary

### Dataset A (agent-authored) -- 39,088 fixtures

**fixture_type kind distribution**

| Kind | Count | % |
|---|---|---|
| setup | 18,613 | 47.6% |
| teardown | 11,429 | 29.2% |
| other | 9,046 | 23.1% |

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

2,559/39,088 fixtures (6.55%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 1,320 | 198 | 15.00% | typescript=122, python=75, javascript=1 |
| javascript | 1,684 | 332 | 19.71% | typescript=190, python=119, java=23 |
| python | 11,798 | 614 | 5.20% | typescript=409, javascript=149, java=56 |
| typescript | 24,286 | 1,415 | 5.83% | javascript=1,073, python=334, java=8 |

### Dataset C (human-authored, pre-LLM) -- 211,384 fixtures

**fixture_type kind distribution**

| Kind | Count | % |
|---|---|---|
| setup | 121,519 | 57.5% |
| teardown | 48,446 | 22.9% |
| other | 41,419 | 19.6% |

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

18,660/211,384 fixtures (8.83%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 79,738 | 4,044 | 5.07% | python=1,818, typescript=1,164, javascript=1,062 |
| javascript | 30,836 | 2,862 | 9.28% | typescript=2,150, python=388, java=324 |
| python | 38,962 | 1,895 | 4.86% | typescript=865, javascript=689, java=341 |
| typescript | 61,848 | 9,859 | 15.94% | javascript=9,272, python=389, java=198 |

## A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)

Per-repository proportions: for each repo, `setup_pct`/`teardown_pct`/`other_pct` = that repo's setup/teardown/other-classified fixtures divided by its total classified fixtures (the three sum to 100% per repo; `other_pct` isn't shown below). Median is taken over those per-repo proportions, not a single pooled fixture-level percentage. "V (A↔C)"/"p (BH)" are the `setup` category's own repo-level Mann-Whitney U + Cliff's delta test (`setup`/`teardown` aren't independent -- together with `other` they sum to 100% per repo -- so this one test represents the row). The column is labeled "V" for consistency with the paper's other effect-size columns, but the number is Cliff's delta, not literally Cramer's V. Overall is a single pooled test (raw p, never BH-corrected); each language's p is BH-FDR-corrected against the other 3 languages' `setup` tests only.

| Language | n_A | n_C | Setup A (%) | Setup C (%) | Teardown A (%) | Teardown C (%) | V (A↔C) | p (BH) |
|---|---|---|---|---|---|---|---|---|
| Overall | 1044 | 3244 | 50.0% | 66.2% | 16.7% | 13.0% | 0.312 (small) | <.001 |
| java | 84 | 702 | 68.1% | 64.8% | 19.4% | 15.7% | -0.105 (negligible) | 0.114 |
| javascript | 88 | 834 | 57.5% | 73.0% | 42.5% | 27.0% | 0.169 (small) | 0.011 |
| python | 490 | 1155 | 0.0% | 50.0% | 0.0% | 0.0% | 0.343 (medium) | <.001 |
| typescript | 502 | 859 | 56.4% | 75.6% | 43.6% | 24.4% | 0.313 (small) | <.001 |

## Unimodality Check: Python Teardown Proportion (Dip Test)

Hartigan & Hartigan's dip test for unimodality [CITE: Hartigan & Hartigan 1985, The Dip Test of Unimodality], run on the same per-repo Python `teardown_pct` values the table above summarizes as a single median -- separately per dataset, since this tests whether *one* distribution is unimodal, not whether two distributions differ. Null hypothesis: the distribution is unimodal; a low p-value is evidence of multimodality (e.g. a real "most repos provide none, a distinct minority provide all" split, rather than a smooth continuum from 0% to 100%).

| Dataset | n (Python repos) | Dip statistic | p-value |
|---|---|---|---|
| Dataset A | 490 | 0.0174 | 0.415 |
| Dataset C | 1155 | 0.0247 | <.001 |

**Dataset A -- teardown_pct distribution across 490 Python repos**

```
 0.00- 0.10 | ######################################## (416)
 0.10- 0.20 | ## (24)
 0.20- 0.30 | # (12)
 0.30- 0.40 | # (10)
 0.40- 0.50 | # (7)
 0.50- 0.60 | ## (18)
 0.60- 0.70 |  (0)
 0.70- 0.80 |  (1)
 0.80- 0.90 |  (0)
 0.90- 1.00 |  (2)
```

**Dataset C -- teardown_pct distribution across 1155 Python repos**

```
 0.00- 0.10 | ######################################## (771)
 0.10- 0.20 | #### (79)
 0.20- 0.30 | ##### (87)
 0.30- 0.40 | #### (79)
 0.40- 0.50 | ### (58)
 0.50- 0.60 | ### (67)
 0.60- 0.70 |  (6)
 0.70- 0.80 |  (1)
 0.80- 0.90 |  (0)
 0.90- 1.00 |  (7)
```
