# Control-Variable Balance Check

> Are the repo samples behind two datasets comparable on language, domain, and repo age -- before attributing an RQ1-3 fixture-metric difference to authorship or era? See this module's docstring for why this check didn't previously run against the current data.

Generated: 2026-08-31 20:53:09 UTC

Repo-level (each fixture-yielding repo counted once), not fixture-weighted -- see this module's docstring for why.

## Per-dataset repo distributions

### Dataset A (agent-authored) -- 1,647 fixture-yielding repos

**language distribution**

| Value | Count | % |
|---|---|---|
| typescript | 842 | 51.1% |
| python | 593 | 36.0% |
| java | 112 | 6.8% |
| javascript | 100 | 6.1% |

**domain distribution**

| Value | Count | % |
|---|---|---|
| other | 803 | 48.8% |
| ml | 419 | 25.4% |
| web | 271 | 16.5% |
| systems | 45 | 2.7% |
| database | 38 | 2.3% |
| security | 36 | 2.2% |
| devops | 35 | 2.1% |

### Dataset C (human-authored, pre-LLM) -- 2,472 fixture-yielding repos

**language distribution**

| Value | Count | % |
|---|---|---|
| python | 983 | 39.8% |
| typescript | 775 | 31.4% |
| javascript | 403 | 16.3% |
| java | 311 | 12.6% |

**domain distribution**

| Value | Count | % |
|---|---|---|
| other | 1,528 | 61.8% |
| web | 452 | 18.3% |
| ml | 196 | 7.9% |
| database | 86 | 3.5% |
| security | 75 | 3.0% |
| devops | 68 | 2.8% |
| systems | 67 | 2.7% |

## A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)

**p >= 0.05 means balanced** (no evidence of a difference); Cliff's delta/Cramer's V say how big any difference actually is, independent of sample size (thresholds: negligible/small/medium/large). BH-FDR corrects for running all 3 of these tests together.

| Variable | Test | statistic | p-value | balanced (p>=0.05) | effect size | BH-FDR adjusted p (sig?) |
|---|---|---|---|---|---|---|
| language | chi-square | 219.0 | 3.348e-47 | **no** | 0.231 (small) | 5.022e-47 (yes) |
| domain | chi-square | 243.4 | 1.072e-49 | **no** | 0.243 (small) | 3.216e-49 (yes) |
| repo_age_years | mann-whitney-u | 860725.5 | 3.112e-42 | **no** | -0.296 (small) | 3.112e-42 (yes) |
