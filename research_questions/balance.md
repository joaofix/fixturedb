# Control-Variable Balance Check

> Are the repo samples behind two datasets comparable on language, domain, and repo age -- before attributing an RQ1-3 fixture-metric difference to authorship or era? See this module's docstring for why this check didn't previously run against the current data.

Generated: 2026-09-16 02:21:44 UTC

Repo-level (each fixture-yielding repo counted once), not fixture-weighted -- see this module's docstring for why.

## Per-dataset repo distributions

### Dataset A (agent-authored) -- 1,687 fixture-yielding repos

**language distribution**

| Value | Count | % |
|---|---|---|
| typescript | 855 | 50.7% |
| python | 612 | 36.3% |
| java | 115 | 6.8% |
| javascript | 105 | 6.2% |

**domain distribution**

| Value | Count | % |
|---|---|---|
| other | 828 | 49.1% |
| ml | 426 | 25.3% |
| web | 276 | 16.4% |
| systems | 45 | 2.7% |
| database | 41 | 2.4% |
| security | 36 | 2.1% |
| devops | 35 | 2.1% |

### Dataset C (human-authored, pre-LLM) -- 2,506 fixture-yielding repos

**language distribution**

| Value | Count | % |
|---|---|---|
| python | 993 | 39.6% |
| typescript | 788 | 31.4% |
| javascript | 408 | 16.3% |
| java | 317 | 12.6% |

**domain distribution**

| Value | Count | % |
|---|---|---|
| other | 1,544 | 61.6% |
| web | 463 | 18.5% |
| ml | 196 | 7.8% |
| database | 92 | 3.7% |
| security | 76 | 3.0% |
| devops | 68 | 2.7% |
| systems | 67 | 2.7% |

## A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)

**p >= 0.05 means balanced** (no evidence of a difference); Cliff's delta/Cramer's V say how big any difference actually is, independent of sample size (thresholds: negligible/small/medium/large). BH-FDR corrects for running all 3 of these tests together.

| Variable | Test | statistic | p-value | balanced (p>=0.05) | effect size | BH-FDR adjusted p (sig?) |
|---|---|---|---|---|---|---|
| language | chi-square | 214.8 | 2.648e-46 | **no** | 0.226 (small) | 3.971e-46 (yes) |
| domain | chi-square | 246.7 | 2.109e-50 | **no** | 0.243 (small) | 6.328e-50 (yes) |
| repo_age_years | mann-whitney-u | 899372.0 | 4.397e-42 | **no** | -0.292 (small) | 4.397e-42 (yes) |
