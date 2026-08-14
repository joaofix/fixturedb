# Control-Variable Balance Check

> Are the repo samples behind two datasets comparable on language, domain, and repo age -- before attributing an RQ1-3 fixture-metric difference to authorship or era? See this module's docstring for why this check didn't previously run against the current data.

Generated: 2026-08-14 19:20:37 UTC

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

### Dataset C (human-authored, pre-LLM) -- 851 fixture-yielding repos

**language distribution**

| Value | Count | % |
|---|---|---|
| python | 547 | 64.3% |
| typescript | 212 | 24.9% |
| javascript | 62 | 7.3% |
| java | 30 | 3.5% |

**domain distribution**

| Value | Count | % |
|---|---|---|
| other | 535 | 62.9% |
| web | 118 | 13.9% |
| ml | 99 | 11.6% |
| database | 28 | 3.3% |
| devops | 27 | 3.2% |
| security | 22 | 2.6% |
| systems | 22 | 2.6% |

## A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)

**p >= 0.05 means balanced** (no evidence of a difference); Cliff's delta/Cramer's V say how big any difference actually is, independent of sample size (thresholds: negligible/small/medium/large). BH-FDR corrects for running all 3 of these tests together.

| Variable | Test | statistic | p-value | balanced (p>=0.05) | effect size | BH-FDR adjusted p (sig?) |
|---|---|---|---|---|---|---|
| language | chi-square | 91.9 | 8.586e-20 | **no** | 0.220 (small) | 2.576e-19 (yes) |
| domain | chi-square | 91.0 | 1.871e-17 | **no** | 0.219 (small) | 2.807e-17 (yes) |
| repo_age_years | mann-whitney-u | 149295.0 | 2.784e-12 | **no** | -0.234 (small) | 2.784e-12 (yes) |
