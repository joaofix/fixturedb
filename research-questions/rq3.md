# RQ3 -- Setup and Teardown Characterization

> How do agent-generated fixtures compare to human-written ones in setup and teardown provision?

Generated: 2026-10-07 13:35:48 UTC

See [docs/research-questions.md](../docs/research-questions.md) for the full RQ3 definition.

## Per-dataset summary

### Dataset A (agent-authored) -- 85,206 fixtures

**fixture_type kind distribution**

| Kind | Count | % |
|---|---|---|
| setup | 54,008 | 63.4% |
| teardown | 26,212 | 30.8% |
| setup_and_teardown | 4,706 | 5.5% |
| other | 280 | 0.3% |

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

6,765/85,206 fixtures (7.94%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 3,310 | 277 | 8.37% | typescript=179, python=94, javascript=4 |
| javascript | 5,566 | 1,953 | 35.09% | typescript=1,536, python=383, java=34 |
| python | 24,293 | 1,548 | 6.37% | typescript=1,182, javascript=202, java=164 |
| typescript | 52,037 | 2,987 | 5.74% | javascript=2,131, python=814, java=42 |

### Dataset C (human-authored, pre-LLM) -- 82,680 fixtures

**fixture_type kind distribution**

| Kind | Count | % |
|---|---|---|
| setup | 60,823 | 73.6% |
| teardown | 19,441 | 23.5% |
| setup_and_teardown | 1,602 | 1.9% |
| other | 814 | 1.0% |

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

7,480/82,680 fixtures (9.05%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 5,453 | 2,217 | 40.66% | typescript=1,104, python=1,003, javascript=110 |
| javascript | 6,820 | 2,523 | 36.99% | typescript=2,176, python=336, java=11 |
| python | 23,728 | 1,222 | 5.15% | typescript=980, javascript=226, java=16 |
| typescript | 46,679 | 1,518 | 3.25% | javascript=1,317, python=191, java=10 |

## A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)

### Table 1: Fixture Counts by Type (tab:rq3-counts)

Raw counts of setup-classified and teardown-classified fixtures, each also shown as a percentage of that language's *answerable* fixture count (setup + teardown + setup_and_teardown -- "other"-classified fixtures, e.g. a JUnit `@Rule` or a TestNG `@DataProvider` (see the Fixture Kind Classification Coverage by Language table below), are excluded from both the counts themselves and this percentage denominator, since they were never a setup/teardown candidate in the first place; a fixture classified as providing both -- e.g. a pytest fixture with setup code before its `yield` -- is counted in both columns, so they are not mutually exclusive and the two percentages can sum past 100%). Total is the dataset-wide sum across every language present, not just the four rows below. Purely descriptive -- no significance test.

| Language | Setup A | Setup C | Teardown A | Teardown C |
|---|---|---|---|---|
| Total | 58,714 (69.1%) | 62,425 (76.3%) | 30,918 (36.4%) | 21,043 (25.7%) |
| java | 1,951 (64.5%) | 1,665 (66.9%) | 1,075 (35.5%) | 823 (33.1%) |
| javascript | 3,400 (57.1%) | 4,157 (69.9%) | 2,550 (42.9%) | 1,793 (30.1%) |
| python | 22,422 (93.4%) | 19,711 (82.1%) | 6,288 (26.2%) | 5,898 (24.6%) |
| typescript | 30,941 (59.6%) | 36,892 (74.6%) | 21,005 (40.4%) | 12,529 (25.4%) |

### Table 2: Teardown Coverage by Repository (tab:rq3-coverage)

Per-repository binary coverage: 1 if a repo has >=1 teardown-classified fixture, else 0 (population: repos with >=1 setup/teardown/other-classified fixture). "Coverage A/C (%)" is the share of that population with the indicator at 1. Purely descriptive -- no statistical test.

| Language | n_A | n_C | Coverage A (%) | Coverage C (%) |
|---|---|---|---|---|
| Overall | 2169 | 2549 | 78.7% | 64.7% |
| java | 177 | 358 | 66.7% | 51.7% |
| javascript | 211 | 589 | 81.5% | 58.2% |
| python | 856 | 1061 | 67.6% | 62.3% |
| typescript | 1198 | 749 | 86.2% | 72.5% |

## Supplementary Analyses

Analyses below are not part of either main paper table (tab:rq3-counts, tab:rq3-coverage) but are kept and computed since they may still be referenced in prose.

### Fixture Kind Classification Coverage by Language

Per-language, per-dataset breakdown of `fixture_role` (setup / teardown / setup_and_teardown / other) -- the same counts behind Table 1 above and the pooled dataset-wide `other` % in `Per-dataset summary`, just split out per language instead of pooled. Table 1 excludes `other` entirely from its own percentage denominator, so it never shows this slice; `other` fixtures (e.g. a JUnit `@Rule`/`@ClassRule` field, or a TestNG `@DataProvider` -- neither is inherently setup or teardown) are not spread evenly across languages, so a language with a high `other` % has that much smaller a share of its fixtures represented in Table 1's counts at all. Worth re-checking whenever a new dataset is extracted -- a new language or framework can introduce its own unclassifiable fixture types.

| Dataset | Language | Total fixtures | setup | teardown | setup_and_teardown | other (count) | other (%) |
|---|---|---|---|---|---|---|---|
| A | java | 3,273 | 1,951 | 1,075 | 0 | 247 | 7.5% |
| A | javascript | 5,950 | 3,400 | 2,550 | 0 | 0 | 0.0% |
| A | python | 24,036 | 17,716 | 1,582 | 4,706 | 32 | 0.1% |
| A | typescript | 51,947 | 30,941 | 21,005 | 0 | 1 | 0.0% |
| C | java | 3,273 | 1,665 | 823 | 0 | 785 | 24.0% |
| C | javascript | 5,950 | 4,157 | 1,793 | 0 | 0 | 0.0% |
| C | python | 24,036 | 18,109 | 4,296 | 1,602 | 29 | 0.1% |
| C | typescript | 49,421 | 36,892 | 12,529 | 0 | 0 | 0.0% |
