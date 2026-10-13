# RQ5 -- Manual coding of fixture guidance

Generated: 2026-10-13 04:00:00 UTC

Source: `research-questions/rq5/rq5_repository_coding_sheet.csv`, one row per repository with a fixture keyword match in its guidance files.

## Code fixture guidance

| Statistic | Count | Percentage | Denominator |
|---|---|---|---|
| Coded `yes` | 556 | 28.1% | 1,978 repositories with a guidance file |
| Coded `yes` or `unsure` (every `unsure` counted as `yes`) | 620 | 31.3% | 1,978 repositories with a guidance file |

## By primary language

| Language | With guidance file | Coded `yes` | Percentage |
|---|---|---|---|
| Python | 724 | 222 | 30.7% |
| Java | 159 | 40 | 25.2% |
| JavaScript | 193 | 52 | 26.9% |
| TypeScript | 902 | 242 | 26.8% |

## Keyword search precision

| Coding | Repositories | Percentage of repositories with a fixture match |
|---|---|---|
| `yes` | 556 | 81.9% |
| `no` | 59 | 8.7% |
| `unsure` | 64 | 9.4% |
| Total | 679 | -- |

Precision: 556 of 679 (81.9%); 64 coded `unsure`.

## Categories

### Sampling

Population: the 556 repositories coded `yes`, in one random permutation (seed 20261012, not stratified), coded from the top; checkpoint 83 reached. Sample size: 83. Confidence: 95%. Margin of error: 9.9% (p = 0.5, with the finite population correction).

### Categories of fixture guidance

| Category | Definition | Repositories | % of sample |
|---|---|---|---|
| Location | Where fixtures live or must be placed. | 25 | 30.1% |
| Reuse | Use or reuse existing fixtures, or names the ones available. | 16 | 19.3% |
| Framework features | How to use the test framework's fixture features, such as which mechanism (fixtures, setUp, hooks, wrappers) and at what scope (per test, module, session). | 13 | 15.7% |
| Test doubles | Mocks, stubs or fakes provided by fixtures or reset in hooks. | 13 | 15.7% |
| Fixture creation | When to add a fixture, or which tool or procedure creates it. | 12 | 14.5% |
| Fixture design | Qualities a fixture should have, such as minimal, deterministic, synthetic or typed. | 12 | 14.5% |
| Fixture maintenance | Updating, regenerating, versioning or not editing fixtures. | 12 | 14.5% |
| Cleanup | Removing what fixtures or tests create. | 11 | 13.3% |
| Test isolation | Keeping fixture state from leaking between tests (no shared mutation, read-only, parallel-safe), including per-test resources such as temporary directories or private databases. | 9 | 10.8% |
| Non-actionable mention | Mentions fixtures without telling the agent what to do, such as a fixture path in a command, a passing tip, or a pointer to another document. | 8 | 9.6% |
| Sensitive information | No real credentials, personal or customer data in fixtures. | 5 | 6.0% |

A repository can belong to several categories, so percentages do not add up to 100%.

Categories per repository: median 2, minimum 1, maximum 3.

### Languages

| Language | Coded sample (n = 83) | % | All `yes` repositories (N = 556) | % |
|---|---|---|---|---|
| Python | 31 | 37.3% | 222 | 39.9% |
| Java | 5 | 6.0% | 40 | 7.2% |
| JavaScript | 8 | 9.6% | 52 | 9.4% |
| TypeScript | 39 | 47.0% | 242 | 43.5% |

### Agreement

No second coding yet.
