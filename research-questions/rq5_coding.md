# RQ5 -- Manual coding of fixture guidance

Generated: 2026-10-13 20:55:21 UTC

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

Population: the 586 repositories coded `yes`, ordered as a proportional stratified random sample: the 548 repositories coded `yes` in the first pass and still `yes`, in their random order (seed 20261012), and the 38 coded `yes` in the decision review, in a random order (seed 20261014), interleaved so that every checkpoint holds both at the same rate; coded from the top; no checkpoint reached (88 and 233): the coded prefix stops at 82. Sample size: 82. Confidence: 95%. Margin of error: 10.0% (p = 0.5, with the finite population correction).

### Categories of fixture guidance

| Category | Definition | Repositories | % of sample |
|---|---|---|---|
| Location | Where fixtures live or should be placed | 24 | 29.3% |
| Reuse | Using existing fixtures | 16 | 19.5% |
| Framework features | Which fixture mechanism and scope to use | 13 | 15.9% |
| Test doubles | Mocks and stubs handled by fixtures | 13 | 15.9% |
| Fixture creation | When and how to create fixtures | 12 | 14.6% |
| Fixture design | Qualities that fixtures should have | 12 | 14.6% |
| Fixture maintenance | Keeping fixtures up to date | 12 | 14.6% |
| Cleanup | Removing what fixtures or tests create | 11 | 13.4% |
| Test isolation | Avoiding state leaks between tests | 9 | 11.0% |
| Non-actionable mention | Mentions fixtures without instructions | 8 | 9.8% |
| Sensitive information | No real or private data in fixtures | 5 | 6.1% |

A repository can belong to several categories, so percentages do not add up to 100%.

Categories per repository: median 2, minimum 1, maximum 3.

### Languages

| Language | Coded sample (n = 82) | % | All `yes` repositories (N = 586) | % |
|---|---|---|---|---|
| Python | 30 | 36.6% | 227 | 38.7% |
| Java | 5 | 6.1% | 43 | 7.3% |
| JavaScript | 8 | 9.8% | 56 | 9.6% |
| TypeScript | 39 | 47.6% | 260 | 44.4% |

### Agreement

No second coding yet.
