# Control-Variable Balance Check

> Are the repo samples behind two datasets comparable on language, domain, and repo age -- before attributing an RQ1-3 fixture-metric difference to authorship or era? See this module's docstring for why this check didn't previously run against the current data.

Generated: 2026-08-21 00:06:40 UTC

Repo-level (each fixture-yielding repo counted once), not fixture-weighted -- see this module's docstring for why.

## Per-dataset repo distributions

### Dataset A (agent-authored) -- 1,354 fixture-yielding repos

**language distribution**

| Value | Count | % |
|---|---|---|
| typescript | 695 | 51.3% |
| python | 485 | 35.8% |
| java | 89 | 6.6% |
| javascript | 85 | 6.3% |

**domain distribution**

| Value | Count | % |
|---|---|---|
| other | 677 | 50.0% |
| ml | 343 | 25.3% |
| web | 214 | 15.8% |
| systems | 39 | 2.9% |
| database | 29 | 2.1% |
| devops | 27 | 2.0% |
| security | 25 | 1.8% |

### Dataset C (human-authored, pre-LLM) -- 2,325 fixture-yielding repos

**language distribution**

| Value | Count | % |
|---|---|---|
| python | 893 | 38.4% |
| typescript | 767 | 33.0% |
| javascript | 398 | 17.1% |
| java | 267 | 11.5% |

**domain distribution**

| Value | Count | % |
|---|---|---|
| other | 1,432 | 61.6% |
| web | 443 | 19.1% |
| ml | 174 | 7.5% |
| database | 77 | 3.3% |
| security | 70 | 3.0% |
| systems | 66 | 2.8% |
| devops | 63 | 2.7% |

## A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)

**p >= 0.05 means balanced** (no evidence of a difference); Cliff's delta/Cramer's V say how big any difference actually is, independent of sample size (thresholds: negligible/small/medium/large). BH-FDR corrects for running all 3 of these tests together.

| Variable | Test | statistic | p-value | balanced (p>=0.05) | effect size | BH-FDR adjusted p (sig?) |
|---|---|---|---|---|---|---|
| language | chi-square | 171.9 | 5.003e-37 | **no** | 0.216 (small) | 7.505e-37 (yes) |
| domain | chi-square | 229.4 | 1.005e-46 | **no** | 0.250 (small) | 3.016e-46 (yes) |
| repo_age_years | mann-whitney-u | 643321.0 | 6.81e-30 | **no** | -0.274 (small) | 6.81e-30 (yes) |
