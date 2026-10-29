# RQ3 -- Setup and Teardown Characterization

> How do agent-generated fixtures compare to human-written ones in setup and teardown provision?

Generated: 2026-10-27 04:02:47 UTC

See [docs/research-questions.md](../docs/research-questions.md) for the full RQ3 definition.

## Per-dataset summary

### Dataset A (agent-authored) -- 85,136 fixtures

**fixture_type kind distribution**

| Kind | Count | % |
|---|---|---|
| setup | 54,008 | 63.4% |
| teardown | 26,212 | 30.8% |
| setup_and_teardown | 4,706 | 5.5% |
| other | 210 | 0.2% |

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

6,762/85,136 fixtures (7.94%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 3,243 | 277 | 8.54% | typescript=179, python=94, javascript=4 |
| javascript | 5,566 | 1,953 | 35.09% | typescript=1,536, python=383, java=34 |
| python | 24,290 | 1,545 | 6.36% | typescript=1,182, javascript=202, java=161 |
| typescript | 52,037 | 2,987 | 5.74% | javascript=2,131, python=814, java=42 |

### Dataset C (human-authored, pre-LLM) -- 82,610 fixtures

**fixture_type kind distribution**

| Kind | Count | % |
|---|---|---|
| setup | 61,012 | 73.9% |
| teardown | 19,433 | 23.5% |
| setup_and_teardown | 1,607 | 1.9% |
| other | 558 | 0.7% |

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

7,483/82,610 fixtures (9.06%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 5,374 | 2,225 | 41.40% | typescript=1,104, python=1,003, javascript=118 |
| javascript | 6,847 | 2,536 | 37.04% | typescript=2,176, python=336, java=24 |
| python | 23,729 | 1,223 | 5.15% | typescript=980, javascript=223, java=20 |
| typescript | 46,660 | 1,499 | 3.21% | javascript=1,298, python=191, java=10 |

## A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)

### Table 1: Fixture Counts by Type (tab:rq3-counts)

Raw counts of setup-classified and teardown-classified fixtures, each also shown as a percentage of that language's *answerable* fixture count (setup + teardown + setup_and_teardown -- "other"-classified fixtures (a JUnit `@Rule`/`@ClassRule` field -- see the Fixture Kind Classification Coverage by Language table below) are excluded from both the counts themselves and this percentage denominator, since they were never a setup/teardown candidate in the first place; a fixture classified as providing both -- e.g. a pytest fixture with setup code before its `yield` -- is counted in both columns, so they are not mutually exclusive and the two percentages can sum past 100%). Total is the dataset-wide sum across every language present, not just the four rows below. Purely descriptive -- no significance test.

| Language | Setup A | Setup C | Teardown A | Teardown C |
|---|---|---|---|---|
| Total | 58,714 (69.1%) | 62,619 (76.3%) | 30,918 (36.4%) | 21,040 (25.6%) |
| java | 1,951 (64.5%) | 1,856 (69.5%) | 1,075 (35.5%) | 816 (30.5%) |
| javascript | 3,400 (57.1%) | 4,143 (69.6%) | 2,550 (42.9%) | 1,807 (30.4%) |
| python | 22,422 (93.4%) | 19,728 (82.2%) | 6,288 (26.2%) | 5,888 (24.5%) |
| typescript | 30,941 (59.6%) | 36,892 (74.6%) | 21,005 (40.4%) | 12,529 (25.4%) |

### Table 2: Teardown Coverage by Repository (tab:rq3-coverage)

Per-repository binary coverage: 1 if a repo has >=1 teardown-classified fixture, else 0 (population: repos with >=1 setup/teardown/other-classified fixture). "Coverage A/C (%)" is the share of that population with the indicator at 1. Purely descriptive -- no statistical test.

| Language | n_A | n_C | Coverage A (%) | Coverage C (%) |
|---|---|---|---|---|
| Overall | 2167 | 2572 | 78.8% | 63.9% |
| java | 175 | 375 | 67.4% | 48.5% |
| javascript | 211 | 592 | 81.5% | 59.3% |
| python | 856 | 1062 | 67.6% | 61.5% |
| typescript | 1198 | 749 | 86.2% | 72.5% |

## Supplementary Analyses

Analyses below are not part of either main paper table (tab:rq3-counts, tab:rq3-coverage) but are kept and computed since they may still be referenced in prose.

### Fixture Kind Classification Coverage by Language

Per-language, per-dataset breakdown of `fixture_role` (setup / teardown / setup_and_teardown / other) -- the same counts behind Table 1 above and the pooled dataset-wide `other` % in `Per-dataset summary`, just split out per language instead of pooled. Table 1 excludes `other` entirely from its own percentage denominator, so it never shows this slice; `other` fixtures (a JUnit `@Rule`/`@ClassRule` field -- not inherently setup or teardown) are not spread evenly across languages, so a language with a high `other` % has that much smaller a share of its fixtures represented in Table 1's counts at all. Worth re-checking whenever a new dataset is extracted -- a new language or framework can introduce its own unclassifiable fixture types.

| Dataset | Language | Total fixtures | setup | teardown | setup_and_teardown | other (count) | other (%) |
|---|---|---|---|---|---|---|---|
| A | java | 3,203 | 1,951 | 1,075 | 0 | 177 | 5.5% |
| A | javascript | 5,950 | 3,400 | 2,550 | 0 | 0 | 0.0% |
| A | python | 24,036 | 17,716 | 1,582 | 4,706 | 32 | 0.1% |
| A | typescript | 51,947 | 30,941 | 21,005 | 0 | 1 | 0.0% |
| C | java | 3,203 | 1,856 | 816 | 0 | 531 | 16.6% |
| C | javascript | 5,950 | 4,143 | 1,807 | 0 | 0 | 0.0% |
| C | python | 24,036 | 18,121 | 4,281 | 1,607 | 27 | 0.1% |
| C | typescript | 49,421 | 36,892 | 12,529 | 0 | 0 | 0.0% |
