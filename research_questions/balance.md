# Control-Variable Balance Check

> Are the repo samples behind two datasets comparable on language, domain, and repo age -- before attributing an RQ1-3 fixture-metric difference to authorship or era? See this module's docstring for why this check didn't previously run against the current data.

Generated: 2026-08-19 15:56:59 UTC

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

### Dataset C (human-authored, pre-LLM) -- 3,005 fixture-yielding repos

**language distribution**

| Value | Count | % |
|---|---|---|
| python | 1,048 | 34.9% |
| typescript | 846 | 28.2% |
| java | 560 | 18.6% |
| javascript | 551 | 18.3% |

**domain distribution**

| Value | Count | % |
|---|---|---|
| other | 1,896 | 63.1% |
| web | 535 | 17.8% |
| ml | 210 | 7.0% |
| database | 114 | 3.8% |
| security | 93 | 3.1% |
| systems | 82 | 2.7% |
| devops | 75 | 2.5% |

## A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)

**p >= 0.05 means balanced** (no evidence of a difference); Cliff's delta/Cramer's V say how big any difference actually is, independent of sample size (thresholds: negligible/small/medium/large). BH-FDR corrects for running all 3 of these tests together.

| Variable | Test | statistic | p-value | balanced (p>=0.05) | effect size | BH-FDR adjusted p (sig?) |
|---|---|---|---|---|---|---|
| language | chi-square | 326.3 | 2.015e-70 | **no** | 0.274 (small) | 6.044e-70 (yes) |
| domain | chi-square | 291.1 | 6.625e-60 | **no** | 0.258 (small) | 9.938e-60 (yes) |
| repo_age_years | mann-whitney-u | 837690.5 | 2.165e-30 | **no** | -0.268 (small) | 2.165e-30 (yes) |
