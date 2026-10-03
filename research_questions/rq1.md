# RQ1 -- Fixture Prevalence

> How common are tests, fixtures, setup, and teardown across the raw repo universe, independent of Dataset A/B/C's own filtering?

Generated: 2026-10-03 02:54:09 UTC

See [docs/research-questions.md](../docs/research-questions.md) for the full RQ1 definition.

Population: 24,461 successfully-scanned repos (`clone_ok=1`), every repo pinned to the same commit-at-or-before cutoff date -- see `collection/rq1_prevalence_scan.py`'s module docstring. A repo whose clone failed, or that had no commit at or before that date, is excluded entirely from every count below ("unknown", never counted as "confirmed no tests").

## No additional quality floor

Every successfully-scanned repo counts here, regardless of how many test files it has.

### Table 1: Prevalence of test fixtures in repositories (tab:rq1-prevalence)

| Language | Repositories with Tests | # | % | Setup (%) | Teardown (%) |
|---|---|---|---|---|---|
| All | 20,437 | 14,675 | 71.8% | 98.1% | 81.2% |
| Python | 7,320 | 5,814 | 79.4% | 99.6% | 77.5% |
| Java | 3,273 | 2,421 | 74.0% | 97.9% | 78.2% |
| JavaScript | 4,011 | 1,990 | 49.6% | 97.3% | 80.1% |
| TypeScript | 5,833 | 4,450 | 76.3% | 96.7% | 88.0% |

### Table 2: Distribution of test fixtures by repository, median (tab:rq1-prevalence-median)

| Language | Fixture | Setup | Teardown |
|---|---|---|---|
| All | 26.0 | 19.0 | 5.0 |
| Python | 22.0 | 19.0 | 4.0 |
| Java | 30.0 | 19.0 | 5.0 |
| JavaScript | 19.5 | 13.0 | 4.0 |
| TypeScript | 35.0 | 21.5 | 11.0 |

At the median, each repository contains 26.0 test fixtures, including 19.0 setups and 5.0 teardowns.

### Raw numbers

| Language | n (tests) | n (fixtures) | n (setup) | n (teardown) | sum fixtures | sum setup | sum teardown |
|---|---|---|---|---|---|---|---|
| All | 20,437 | 14,675 | 14,399 | 11,910 | 1,807,601 | 1,260,003 | 554,418 |
| Python | 7,320 | 5,814 | 5,788 | 4,504 | 470,702 | 427,525 | 115,106 |
| Java | 3,273 | 2,421 | 2,370 | 1,894 | 423,264 | 245,541 | 112,636 |
| JavaScript | 4,011 | 1,990 | 1,937 | 1,594 | 183,803 | 128,063 | 55,740 |
| TypeScript | 5,833 | 4,450 | 4,304 | 3,918 | 729,832 | 458,874 | 270,936 |

## Quality floor applied (>= 5 test files)

Restricted to repos with >= 5 test files -- matching `study_parameters.yaml`'s `min_test_files`, the same floor Dataset A/B/C's own collection applies. No second scan was needed for this variant -- see `collection/rq1_prevalence_scan.py`'s module docstring for why.

### Table 1: Prevalence of test fixtures in repositories (tab:rq1-prevalence)

| Language | Repositories with Tests | # | % | Setup (%) | Teardown (%) |
|---|---|---|---|---|---|
| All | 18,025 | 14,191 | 78.7% | 98.2% | 82.2% |
| Python | 6,559 | 5,649 | 86.1% | 99.6% | 78.4% |
| Java | 2,873 | 2,364 | 82.3% | 98.1% | 78.9% |
| JavaScript | 3,304 | 1,853 | 56.1% | 97.5% | 81.6% |
| TypeScript | 5,289 | 4,325 | 81.8% | 96.9% | 89.2% |

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
| All | 18,025 | 14,191 | 13,939 | 11,668 | 1,805,233 | 1,258,358 | 553,680 |
| Python | 6,559 | 5,649 | 5,625 | 4,430 | 469,989 | 426,949 | 114,935 |
| Java | 2,873 | 2,364 | 2,319 | 1,866 | 423,123 | 245,459 | 112,596 |
| JavaScript | 3,304 | 1,853 | 1,806 | 1,512 | 182,654 | 127,332 | 55,322 |
| TypeScript | 5,289 | 4,325 | 4,189 | 3,860 | 729,467 | 458,618 | 270,827 |
