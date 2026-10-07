# RQ1 -- Fixture Prevalence

> How common are tests, fixtures, setup, and teardown across the raw repo universe, independent of Dataset A/C's own filtering?

Generated: 2026-10-07 13:35:38 UTC

See [docs/research-questions.md](../docs/research-questions.md) for the full RQ1 definition.

Population: 24,432 successfully-scanned repos (`clone_ok=1`), every repo pinned to the same commit-at-or-before cutoff date -- see `collection/rq1_prevalence_scan.py`'s module docstring. A repo whose clone failed, or that had no commit at or before that date, is excluded entirely from every count below ("unknown", never counted as "confirmed no tests"). No `min_test_files` quality floor is applied -- every successfully-scanned repo counts here regardless of how many test files it has, by design (see this module's own docstring).

### Table 1: Prevalence of test fixtures in repositories (tab:rq1-prevalence)

| Language | Repositories with Tests | Fixture (%) | Setup (%) | Teardown (%) |
|---|---|---|---|---|
| All | 20,415 | 71.8% | 70.5% | 58.3% |
| Python | 7,314 | 79.5% | 79.1% | 61.6% |
| Java | 3,259 | 74.0% | 72.5% | 57.9% |
| JavaScript | 4,002 | 49.6% | 48.3% | 39.7% |
| TypeScript | 5,840 | 76.3% | 73.8% | 67.2% |

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

## Legacy: Fixture-Conditioned Table 1 (Not Used in the Paper)

Kept for transparency/comparison only -- this is Table 1's original Setup (%)/Teardown (%) definition (share of the fixture-having subset, `#`/`%` below, rather than of all repos with >=1 test file). Near-universal regardless of language (95-99%) since clearing "has >=1 fixture" is a much easier bar than clearing "has >=1 test file" -- not the paper's table, which is the Table 1 above.

| Language | Repositories with Tests | # | % | Setup (%) | Teardown (%) |
|---|---|---|---|---|---|
| All | 20,415 | 14,665 | 71.8% | 98.1% | 81.2% |
| Python | 7,314 | 5,811 | 79.5% | 99.6% | 77.5% |
| Java | 3,259 | 2,413 | 74.0% | 97.9% | 78.2% |
| JavaScript | 4,002 | 1,984 | 49.6% | 97.3% | 80.1% |
| TypeScript | 5,840 | 4,457 | 76.3% | 96.7% | 88.1% |
