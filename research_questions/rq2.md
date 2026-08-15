# RQ2 -- Setup and Teardown Characterization

> How do agent-generated fixtures compare to human-written ones in setup and teardown provision?

Generated: 2026-08-15 17:34:38 UTC

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

### Dataset C (human-authored, pre-LLM) -- 39,377 fixtures

**fixture_type kind distribution**

| Kind | Count | % |
|---|---|---|
| setup | 22,952 | 58.3% |
| teardown | 8,400 | 21.3% |
| other | 8,025 | 20.4% |

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

3,900/39,377 fixtures (9.90%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 3,233 | 20 | 0.62% | python=16, javascript=4 |
| javascript | 2,528 | 297 | 11.75% | typescript=125, python=119, java=53 |
| python | 17,111 | 615 | 3.59% | typescript=294, java=188, javascript=133 |
| typescript | 16,505 | 2,968 | 17.98% | javascript=2,816, python=114, java=38 |

## A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)

Per-repository proportions: for each repo, `setup_pct`/`teardown_pct`/`other_pct` = that repo's setup/teardown/other-classified fixtures divided by its total classified fixtures (the three sum to 100% per repo; `other_pct` isn't shown below). Median is taken over those per-repo proportions, not a single pooled fixture-level percentage. "V (A↔C)"/"p (BH)" are the `setup` category's own repo-level Mann-Whitney U + Cliff's delta test (`setup`/`teardown` aren't independent -- together with `other` they sum to 100% per repo -- so this one test represents the row). The column is labeled "V" for consistency with the paper's other effect-size columns, but the number is Cliff's delta, not literally Cramer's V. Overall is a single pooled test (raw p, never BH-corrected); each language's p is BH-FDR-corrected against the other 3 languages' `setup` tests only.

| Language | n_A | n_C | Setup A (%) | Setup C (%) | Teardown A (%) | Teardown C (%) | V (A↔C) | p (BH) |
|---|---|---|---|---|---|---|---|---|
| Overall | 1044 | 851 | 50.0% | 62.3% | 16.7% | 4.5% | 0.212 (small) | <.001 |
| java | 84 | 40 | 68.1% | 68.3% | 19.4% | 7.9% | -0.018 (negligible) | 0.873 |
| javascript | 88 | 144 | 57.5% | 69.7% | 42.5% | 30.3% | 0.140 (negligible) | 0.094 |
| python | 490 | 558 | 0.0% | 50.0% | 0.0% | 0.0% | 0.371 (medium) | <.001 |
| typescript | 502 | 177 | 56.4% | 80.3% | 43.6% | 19.7% | 0.352 (medium) | <.001 |

## Unimodality Check: Python Teardown Proportion (Dip Test)

Hartigan & Hartigan's dip test for unimodality [CITE: Hartigan & Hartigan 1985, The Dip Test of Unimodality], run on the same per-repo Python `teardown_pct` values the table above summarizes as a single median -- separately per dataset, since this tests whether *one* distribution is unimodal, not whether two distributions differ. Null hypothesis: the distribution is unimodal; a low p-value is evidence of multimodality (e.g. a real "most repos provide none, a distinct minority provide all" split, rather than a smooth continuum from 0% to 100%).

| Dataset | n (Python repos) | Dip statistic | p-value |
|---|---|---|---|
| Dataset A | 490 | 0.0174 | 0.415 |
| Dataset C | 558 | 0.0260 | 0.010 |

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

**Dataset C -- teardown_pct distribution across 558 Python repos**

```
 0.00- 0.10 | ######################################## (370)
 0.10- 0.20 | #### (38)
 0.20- 0.30 | ##### (47)
 0.30- 0.40 | #### (35)
 0.40- 0.50 | ### (27)
 0.50- 0.60 | ### (32)
 0.60- 0.70 |  (2)
 0.70- 0.80 |  (1)
 0.80- 0.90 |  (0)
 0.90- 1.00 | # (6)
```
