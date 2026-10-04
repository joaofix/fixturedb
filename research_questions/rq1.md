# RQ1 -- Fixture Prevalence

> How common are tests, fixtures, setup, and teardown across the raw repo universe, independent of Dataset A/B/C's own filtering?

Generated: 2026-10-04 15:51:16 UTC

See [docs/research-questions.md](../docs/research-questions.md) for the full RQ1 definition.

Population: 24,432 successfully-scanned repos (`clone_ok=1`), every repo pinned to the same commit-at-or-before cutoff date -- see `collection/rq1_prevalence_scan.py`'s module docstring. A repo whose clone failed, or that had no commit at or before that date, is excluded entirely from every count below ("unknown", never counted as "confirmed no tests").

## No additional quality floor

Every successfully-scanned repo counts here, regardless of how many test files it has.

### Table 1: Prevalence of test fixtures in repositories (tab:rq1-prevalence)

| Language | Repositories with Tests | # | % | Setup (%) | Teardown (%) |
|---|---|---|---|---|---|
| All | 20,415 | 14,665 | 71.8% | 98.1% | 81.2% |
| Python | 7,314 | 5,811 | 79.5% | 99.6% | 77.5% |
| Java | 3,259 | 2,413 | 74.0% | 97.9% | 78.2% |
| JavaScript | 4,002 | 1,984 | 49.6% | 97.3% | 80.1% |
| TypeScript | 5,840 | 4,457 | 76.3% | 96.7% | 88.1% |

### Table 2: Distribution of test fixtures by repository, median (tab:rq1-prevalence-median)

| Language | Fixture | Setup | Teardown |
|---|---|---|---|
| All | 26.0 | 19.0 | 5.0 |
| Python | 22.0 | 19.0 | 4.0 |
| Java | 30.0 | 19.0 | 5.0 |
| JavaScript | 19.5 | 13.0 | 4.0 |
| TypeScript | 35.0 | 22.0 | 11.0 |

At the median, each repository contains 26.0 test fixtures, including 19.0 setups and 5.0 teardowns.

### Raw numbers

| Language | n (tests) | n (fixtures) | n (setup) | n (teardown) | sum fixtures | sum setup | sum teardown |
|---|---|---|---|---|---|---|---|
| All | 20,415 | 14,665 | 14,388 | 11,902 | 1,814,530 | 1,262,109 | 559,316 |
| Python | 7,314 | 5,811 | 5,785 | 4,502 | 469,229 | 426,678 | 114,467 |
| Java | 3,259 | 2,413 | 2,362 | 1,886 | 421,784 | 244,220 | 112,565 |
| JavaScript | 4,002 | 1,984 | 1,931 | 1,589 | 183,237 | 127,732 | 55,505 |
| TypeScript | 5,840 | 4,457 | 4,310 | 3,925 | 740,280 | 463,479 | 276,779 |

## Quality floor applied (>= 5 test files)

Restricted to repos with >= 5 test files -- matching `study_parameters.yaml`'s `min_test_files`, the same floor Dataset A/B/C's own collection applies. No second scan was needed for this variant -- see `collection/rq1_prevalence_scan.py`'s module docstring for why.

### Table 1: Prevalence of test fixtures in repositories (tab:rq1-prevalence)

| Language | Repositories with Tests | # | % | Setup (%) | Teardown (%) |
|---|---|---|---|---|---|
| All | 18,010 | 14,181 | 78.7% | 98.2% | 82.2% |
| Python | 6,555 | 5,646 | 86.1% | 99.6% | 78.4% |
| Java | 2,862 | 2,357 | 82.4% | 98.1% | 78.9% |
| JavaScript | 3,297 | 1,847 | 56.0% | 97.5% | 81.6% |
| TypeScript | 5,296 | 4,331 | 81.8% | 96.8% | 89.3% |

### Table 2: Distribution of test fixtures by repository, median (tab:rq1-prevalence-median)

| Language | Fixture | Setup | Teardown |
|---|---|---|---|
| All | 28.0 | 20.0 | 6.0 |
| Python | 23.0 | 20.0 | 4.0 |
| Java | 32.0 | 20.0 | 6.0 |
| JavaScript | 23.0 | 15.0 | 5.0 |
| TypeScript | 38.0 | 23.0 | 12.0 |

At the median, each repository contains 28.0 test fixtures, including 20.0 setups and 6.0 teardowns.

### Raw numbers

| Language | n (tests) | n (fixtures) | n (setup) | n (teardown) | sum fixtures | sum setup | sum teardown |
|---|---|---|---|---|---|---|---|
| All | 18,010 | 14,181 | 13,928 | 11,660 | 1,812,158 | 1,260,461 | 558,577 |
| Python | 6,555 | 5,646 | 5,622 | 4,428 | 468,516 | 426,102 | 114,296 |
| Java | 2,862 | 2,357 | 2,312 | 1,859 | 421,645 | 244,139 | 112,526 |
| JavaScript | 3,297 | 1,847 | 1,800 | 1,507 | 182,088 | 127,001 | 55,087 |
| TypeScript | 5,296 | 4,331 | 4,194 | 3,866 | 739,909 | 463,219 | 276,668 |
