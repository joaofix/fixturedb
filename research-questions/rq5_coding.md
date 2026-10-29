# RQ5 -- Manual coding of fixture guidance

Generated: 2026-10-27 03:45:23 UTC

Source: `research-questions/rq5/rq5_repository_coding_sheet.csv`, one row per repository with a fixture keyword match in its guidance files.

## Code fixture guidance

| Statistic | Count | Percentage | Denominator |
|---|---|---|---|
| Coded `yes` | 586 | 29.7% | 1,976 repositories with a guidance file |

## By primary language

| Language | With guidance file | Coded `yes` | Percentage |
|---|---|---|---|
| Python | 724 | 227 | 31.4% |
| Java | 157 | 43 | 27.4% |
| JavaScript | 193 | 56 | 29.0% |
| TypeScript | 902 | 260 | 28.8% |

## Keyword search precision

| Coding | Repositories | Percentage of repositories with a fixture match |
|---|---|---|
| `yes` | 586 | 86.4% |
| `no` | 92 | 13.6% |
| Total | 678 | -- |

Precision: 586 of 678 (86.4%).

## Categories

### Sampling

Population: the 586 repositories coded `yes`. Sample: an exploratory random sample of the first 100 of them, in the existing random order (seed 20261012 for the 548 repositories coded `yes` in the first pass, seed 20261014 for the 38 coded `yes` in the decision review, interleaved at the same rate), coded from the top; all 100 coded. Sample size: 100.

### Categories of fixture guidance

| Category | Description | Repositories | % of sample |
|---|---|---|---|
| Quality | Keeping fixtures reliable and independent | 43 | 43.0% |
| Creation | Creating or reusing fixtures | 39 | 39.0% |
| Location | Placing and organizing fixtures | 28 | 28.0% |
| Test doubles | Handling mocks within fixtures | 15 | 15.0% |
| Mechanisms | Choosing decorators, annotations or functions | 13 | 13.0% |
| Sensitive data | Avoid private or production data | 7 | 7.0% |
| Miscellaneous | Guidance that fits no other category | 0 | 0.0% |

A repository can belong to several categories, so percentages do not add up to 100%.

Categories per repository: median 1, minimum 0, maximum 3.

Not in the table: Non-actionable mention (mentions fixtures without instructions). 8 repositories have it as their only category: silvertakana/worldwideview, invoicerr-app/invoicerr, umijs/qiankun, steipete/oracle, Osmantic/ODS, yagop/node-telegram-bot-api, openstack/neutron, tractorjuice/arc-kit. 0 have it together with other categories.

### Languages

| Language | Coded sample (n = 100) | % | All `yes` repositories (N = 586) | % |
|---|---|---|---|---|
| Python | 36 | 36.0% | 227 | 38.7% |
| Java | 7 | 7.0% | 43 | 7.3% |
| JavaScript | 11 | 11.0% | 56 | 9.6% |
| TypeScript | 46 | 46.0% | 260 | 44.4% |

### Agreement

No second coding yet.
