# Control-Variable Balance Check

> Are the repo samples behind two datasets comparable on language, domain, and repo age -- before attributing an RQ2-4 fixture-metric difference to authorship or era? See this module's docstring for why this check was not run against the current data.

Generated: 2026-10-07 14:04:09 UTC

Repo-level (each fixture-yielding repo counted once), not fixture-weighted -- see this module's docstring for why.

## Per-dataset repo distributions

### Dataset A (agent-authored) -- 2,169 fixture-yielding repos

**language distribution**

| Value | Count | % |
|---|---|---|
| typescript | 1,076 | 49.6% |
| python | 778 | 35.9% |
| java | 163 | 7.5% |
| javascript | 152 | 7.0% |

**domain distribution**

| Value | Count | % |
|---|---|---|
| other | 1,235 | 56.9% |
| ml | 438 | 20.2% |
| web | 298 | 13.7% |
| systems | 57 | 2.6% |
| database | 54 | 2.5% |
| security | 52 | 2.4% |
| devops | 35 | 1.6% |

### Dataset C (human-authored, pre-LLM) -- 2,549 fixture-yielding repos

**language distribution**

| Value | Count | % |
|---|---|---|
| python | 993 | 39.0% |
| typescript | 784 | 30.8% |
| javascript | 420 | 16.5% |
| java | 352 | 13.8% |

**domain distribution**

| Value | Count | % |
|---|---|---|
| other | 1,596 | 62.6% |
| web | 464 | 18.2% |
| ml | 194 | 7.6% |
| database | 84 | 3.3% |
| security | 78 | 3.1% |
| systems | 67 | 2.6% |
| devops | 66 | 2.6% |

## A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)

**p >= 0.05 means balanced** (no evidence of a difference); Cliff's delta/Cramer's V say how big any difference actually is, independent of sample size (thresholds: negligible/small/medium/large). BH-FDR corrects for running all 3 of these tests together.

| Variable | Test | statistic | p-value | balanced (p>=0.05) | effect size | BH-FDR adjusted p (sig?) |
|---|---|---|---|---|---|---|
| language | chi-square | 237.8 | 2.838e-51 | **no** | 0.225 (small) | 4.256e-51 (yes) |
| domain | chi-square | 168.9 | 7.579e-34 | **no** | 0.189 (small) | 7.579e-34 (yes) |
| repo_age_years | mann-whitney-u | 1129503.0 | 6.842e-62 | **no** | -0.326 (small) | 2.052e-61 (yes) |
