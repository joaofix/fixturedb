# Control-Variable Balance Check

> Are the repo samples behind two datasets comparable on language, domain, and repo age -- before attributing an RQ1-3 fixture-metric difference to authorship or era? See this module's docstring for why this check didn't previously run against the current data.

Generated: 2026-09-08 01:16:31 UTC

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

### Dataset C (human-authored, pre-LLM) -- 2,494 fixture-yielding repos

**language distribution**

| Value | Count | % |
|---|---|---|
| python | 980 | 39.3% |
| typescript | 791 | 31.7% |
| javascript | 406 | 16.3% |
| java | 317 | 12.7% |

**domain distribution**

| Value | Count | % |
|---|---|---|
| other | 1,541 | 61.8% |
| web | 462 | 18.5% |
| ml | 192 | 7.7% |
| database | 91 | 3.6% |
| security | 72 | 2.9% |
| systems | 71 | 2.8% |
| devops | 65 | 2.6% |

## A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)

**p >= 0.05 means balanced** (no evidence of a difference); Cliff's delta/Cramer's V say how big any difference actually is, independent of sample size (thresholds: negligible/small/medium/large). BH-FDR corrects for running all 3 of these tests together.

| Variable | Test | statistic | p-value | balanced (p>=0.05) | effect size | BH-FDR adjusted p (sig?) |
|---|---|---|---|---|---|---|
| language | chi-square | 211.4 | 1.435e-45 | **no** | 0.225 (small) | 2.153e-45 (yes) |
| domain | chi-square | 249.4 | 5.604e-51 | **no** | 0.244 (small) | 1.681e-50 (yes) |
| repo_age_years | mann-whitney-u | 896412.0 | 9.821e-42 | **no** | -0.291 (small) | 9.821e-42 (yes) |
