# Control-Variable Balance Check

> Are the repo samples behind two datasets comparable on language, domain, and repo age -- before attributing an RQ1-3 fixture-metric difference to authorship or era? See this module's docstring for why this check didn't previously run against the current data.

Generated: 2026-08-16 01:51:20 UTC

Repo-level (each fixture-yielding repo counted once), not fixture-weighted -- see this module's docstring for why.

## Per-dataset repo distributions

### Dataset A (agent-authored) -- 1,044 fixture-yielding repos

**language distribution**

| Value | Count | % |
|---|---|---|
| python | 457 | 43.8% |
| typescript | 441 | 42.2% |
| java | 79 | 7.6% |
| javascript | 67 | 6.4% |

**domain distribution**

| Value | Count | % |
|---|---|---|
| other | 534 | 51.1% |
| ml | 307 | 29.4% |
| web | 124 | 11.9% |
| systems | 21 | 2.0% |
| devops | 20 | 1.9% |
| database | 19 | 1.8% |
| security | 19 | 1.8% |

### Dataset C (human-authored, pre-LLM) -- 3,244 fixture-yielding repos

**language distribution**

| Value | Count | % |
|---|---|---|
| python | 1,087 | 33.5% |
| typescript | 946 | 29.2% |
| java | 662 | 20.4% |
| javascript | 549 | 16.9% |

**domain distribution**

| Value | Count | % |
|---|---|---|
| other | 2,104 | 64.9% |
| web | 554 | 17.1% |
| ml | 209 | 6.4% |
| database | 122 | 3.8% |
| security | 98 | 3.0% |
| systems | 81 | 2.5% |
| devops | 76 | 2.3% |

## A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)

**p >= 0.05 means balanced** (no evidence of a difference); Cliff's delta/Cramer's V say how big any difference actually is, independent of sample size (thresholds: negligible/small/medium/large). BH-FDR corrects for running all 3 of these tests together.

| Variable | Test | statistic | p-value | balanced (p>=0.05) | effect size | BH-FDR adjusted p (sig?) |
|---|---|---|---|---|---|---|
| language | chi-square | 200.9 | 2.663e-43 | **no** | 0.216 (small) | 3.994e-43 (yes) |
| domain | chi-square | 398.4 | 6.207e-83 | **no** | 0.305 (medium) | 1.862e-82 (yes) |
| repo_age_years | mann-whitney-u | 580188.5 | 3.01e-14 | **no** | -0.219 (small) | 3.01e-14 (yes) |
