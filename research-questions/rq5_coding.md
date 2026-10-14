# RQ5 -- Manual coding of fixture guidance

Generated: 2026-10-14 01:00:02 UTC

Source: `research-questions/rq5/rq5_repository_coding_sheet.csv`, one row per repository with a fixture keyword match in its guidance files.

## Code fixture guidance

| Statistic | Count | Percentage | Denominator |
|---|---|---|---|
| Coded `yes` | 586 | 29.6% | 1,978 repositories with a guidance file |

## By primary language

| Language | With guidance file | Coded `yes` | Percentage |
|---|---|---|---|
| Python | 724 | 227 | 31.4% |
| Java | 159 | 43 | 27.0% |
| JavaScript | 193 | 56 | 29.0% |
| TypeScript | 902 | 260 | 28.8% |

## Keyword search precision

| Coding | Repositories | Percentage of repositories with a fixture match |
|---|---|---|
| `yes` | 586 | 86.3% |
| `no` | 93 | 13.7% |
| Total | 679 | -- |

Precision: 586 of 679 (86.3%).

## Categories

### Sampling

Population: the 586 repositories coded `yes`, ordered as a proportional stratified random sample: the 548 repositories coded `yes` in the first pass and still `yes`, in their random order (seed 20261012), and the 38 coded `yes` in the decision review, in a random order (seed 20261014), interleaved so that every checkpoint holds both at the same rate; coded from the top; checkpoint 88 reached. Sample size: 88. Confidence: 95%. Margin of error: 9.6% (p = 0.5, with the finite population correction).

### Categories of fixture guidance

| Category | Definition | Repositories | % of sample |
|---|---|---|---|
| Location | Where fixtures live or should be placed | 24 | 27.3% |
| Reuse | Using existing fixtures | 18 | 20.5% |
| Fixture creation | When and how to create fixtures | 17 | 19.3% |
| Fixture design | Qualities that fixtures should have | 14 | 15.9% |
| Test doubles | Mocks and stubs handled by fixtures | 13 | 14.8% |
| Framework features | Which fixture mechanism and scope to use | 12 | 13.6% |
| Cleanup | Removing what fixtures or tests create | 11 | 12.5% |
| Test isolation | Avoiding state leaks between tests | 10 | 11.4% |
| Fixture maintenance | Keeping fixtures up to date | 9 | 10.2% |
| Non-actionable mention | Mentions fixtures without instructions | 8 | 9.1% |
| Sensitive information | No real or private data in fixtures | 6 | 6.8% |

A repository can belong to several categories, so percentages do not add up to 100%.

Categories per repository: median 2, minimum 1, maximum 3.

### Languages

| Language | Coded sample (n = 88) | % | All `yes` repositories (N = 586) | % |
|---|---|---|---|---|
| Python | 33 | 37.5% | 227 | 38.7% |
| Java | 5 | 5.7% | 43 | 7.3% |
| JavaScript | 9 | 10.2% | 56 | 9.6% |
| TypeScript | 41 | 46.6% | 260 | 44.4% |

### Agreement

No second coding yet.
