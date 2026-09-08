# RQ2 -- Setup and Teardown Characterization

> How do agent-generated fixtures compare to human-written ones in setup and teardown provision?

Generated: 2026-09-08 01:16:49 UTC

See [docs/research-questions.md](../docs/research-questions.md) for the full RQ2 definition.

## Per-dataset summary

### Dataset A (agent-authored) -- 70,623 fixtures

**fixture_type kind distribution**

| Kind | Count | % |
|---|---|---|
| setup | 45,767 | 64.8% |
| teardown | 20,587 | 29.2% |
| setup_and_teardown | 4,072 | 5.8% |
| other | 197 | 0.3% |

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

5,352/70,623 fixtures (7.58%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 2,265 | 262 | 11.57% | typescript=175, python=86, javascript=1 |
| javascript | 3,975 | 1,210 | 30.44% | typescript=1,017, python=170, java=23 |
| python | 21,078 | 1,253 | 5.94% | typescript=950, javascript=160, java=143 |
| typescript | 43,305 | 2,627 | 6.07% | javascript=1,932, python=603, java=92 |

### Dataset C (human-authored, pre-LLM) -- 70,623 fixtures

**fixture_type kind distribution**

| Kind | Count | % |
|---|---|---|
| setup | 51,928 | 73.5% |
| teardown | 16,806 | 23.8% |
| setup_and_teardown | 1,286 | 1.8% |
| other | 603 | 0.9% |

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

6,355/70,623 fixtures (9.00%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 4,156 | 1,935 | 46.56% | typescript=990, python=865, javascript=80 |
| javascript | 5,602 | 2,118 | 37.81% | typescript=1,797, python=306, java=15 |
| python | 20,380 | 1,013 | 4.97% | typescript=837, javascript=162, java=14 |
| typescript | 40,485 | 1,289 | 3.18% | javascript=1,132, python=146, java=11 |

## A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)

### Table 1: Fixture Counts by Type (tab:rq2-counts)

Raw counts of setup-classified and teardown-classified fixtures, each also shown as a percentage of that language's *answerable* fixture count (setup + teardown + setup_and_teardown -- "other"-classified fixtures, e.g. a JUnit `@Rule` or a TestNG `@DataProvider` (see the Fixture Kind Classification Coverage by Language table below), are excluded from both the counts themselves and this percentage denominator, since they were never a setup/teardown candidate in the first place; a fixture classified as providing both -- e.g. a pytest fixture with setup code before its `yield` -- is counted in both columns, so they are not mutually exclusive and the two percentages can sum past 100%). Total is the dataset-wide sum across every language present, not just the four rows below. Purely descriptive -- no significance test.

| Language | Setup A | Setup C | Teardown A | Teardown C |
|---|---|---|---|---|
| Total | 49,839 (70.8%) | 53,214 (76.0%) | 24,659 (35.0%) | 18,092 (25.8%) |
| java | 1,405 (67.1%) | 1,077 (64.3%) | 690 (32.9%) | 597 (35.7%) |
| javascript | 2,842 (58.5%) | 3,353 (69.0%) | 2,016 (41.5%) | 1,505 (31.0%) |
| python | 19,526 (94.5%) | 16,947 (82.0%) | 5,199 (25.2%) | 5,007 (24.2%) |
| typescript | 26,066 (60.9%) | 31,837 (74.4%) | 16,754 (39.1%) | 10,983 (25.6%) |

### Table 2: Teardown Coverage by Repository (tab:rq2-coverage)

Per-repository binary coverage: 1 if a repo has >=1 teardown-classified fixture, else 0 (population: repos with >=1 setup/teardown/other-classified fixture). "Coverage A/C (%)" is the share of that population with the indicator at 1. "delta" is Cliff's delta from a Mann-Whitney U test on the indicator between datasets. Overall is a single pooled test (raw p, never BH-corrected); each language's p is BH-FDR-corrected against the other 3 languages' tests only.

| Language | n_A | n_C | Coverage A (%) | Coverage C (%) | delta | p (BH) |
|---|---|---|---|---|---|---|
| Overall | 1687 | 2494 | 78.0% | 63.0% | -0.150 (small) | <.001 |
| java | 127 | 325 | 66.1% | 49.5% | -0.166 (small) | 0.001 |
| javascript | 143 | 563 | 76.2% | 57.5% | -0.187 (small) | <.001 |
| python | 678 | 1040 | 67.8% | 60.0% | -0.078 (negligible) | 0.001 |
| typescript | 948 | 758 | 85.2% | 72.0% | -0.132 (negligible) | <.001 |

## Supplementary Analyses

Analyses below are not part of either main paper table (tab:rq2-counts, tab:rq2-coverage) but are kept and computed since they may still be referenced in prose.

### Fixture Kind Classification Coverage by Language

Per-language, per-dataset breakdown of `fixture_type_kind` (setup / teardown / setup_and_teardown / other) -- the same counts behind Table 1 above and the pooled dataset-wide `other` % in `Per-dataset summary`, just split out per language instead of pooled. Table 1 excludes `other` entirely from its own percentage denominator, so it never shows this slice; `other` fixtures (e.g. a JUnit `@Rule`/`@ClassRule` field, or a TestNG `@DataProvider` -- neither is inherently setup or teardown) are not spread evenly across languages, so a language with a high `other` % has that much smaller a share of its fixtures represented in Table 1's counts at all. Worth re-checking whenever a new dataset is extracted -- a new language or framework can introduce its own unclassifiable fixture types.

| Dataset | Language | Total fixtures | setup | teardown | setup_and_teardown | other (count) | other (%) |
|---|---|---|---|---|---|---|---|
| A | java | 2,261 | 1,405 | 690 | 0 | 166 | 7.3% |
| A | javascript | 4,858 | 2,842 | 2,016 | 0 | 0 | 0.0% |
| A | python | 20,684 | 15,454 | 1,127 | 4,072 | 31 | 0.1% |
| A | typescript | 42,820 | 26,066 | 16,754 | 0 | 0 | 0.0% |
| C | java | 2,261 | 1,077 | 597 | 0 | 587 | 26.0% |
| C | javascript | 4,858 | 3,353 | 1,505 | 0 | 0 | 0.0% |
| C | python | 20,684 | 15,661 | 3,721 | 1,286 | 16 | 0.1% |
| C | typescript | 42,820 | 31,837 | 10,983 | 0 | 0 | 0.0% |

### Unimodality Check: Python Teardown Proportion (Dip Test)

Hartigan & Hartigan's dip test for unimodality [CITE: Hartigan & Hartigan 1985, The Dip Test of Unimodality], run on the per-repo Python `teardown_pct` distribution (each repo's teardown-classified fixtures divided by its total classified fixtures) -- separately per dataset, since this tests whether *one* distribution is unimodal, not whether two distributions differ. Not the same value as Table 2's binary coverage indicator. Null hypothesis: the distribution is unimodal; a low p-value is evidence of multimodality (e.g. a real "most repos provide none, a distinct minority provide all" split, rather than a smooth continuum from 0% to 100%).

| Dataset | n (Python repos) | Dip statistic | p-value |
|---|---|---|---|
| Dataset A | 678 | 0.0324 | <.001 |
| Dataset C | 1040 | 0.0303 | <.001 |

**Dataset A -- teardown_pct distribution across 678 Python repos**

```
 0.00- 0.10 | ######################################## (262)
 0.10- 0.20 | ########## (67)
 0.20- 0.30 | ############# (83)
 0.30- 0.40 | ########### (70)
 0.40- 0.50 | ####### (45)
 0.50- 0.60 | ########## (65)
 0.60- 0.70 | #### (26)
 0.70- 0.80 | ## (10)
 0.80- 0.90 | # (5)
 0.90- 1.00 | ####### (45)
```

**Dataset C -- teardown_pct distribution across 1040 Python repos**

```
 0.00- 0.10 | ######################################## (494)
 0.10- 0.20 | ######## (95)
 0.20- 0.30 | ######## (101)
 0.30- 0.40 | ####### (89)
 0.40- 0.50 | ##### (58)
 0.50- 0.60 | ####### (92)
 0.60- 0.70 | ## (30)
 0.70- 0.80 | # (12)
 0.80- 0.90 | # (8)
 0.90- 1.00 | ##### (61)
```
