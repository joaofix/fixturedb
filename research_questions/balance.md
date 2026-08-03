# Control-Variable Balance Check

> Are the repo samples behind two datasets comparable on language, domain, and repo age -- before attributing an RQ1-3 fixture-metric difference to authorship or era? See this module's docstring for why this check didn't previously run against the current data.

Generated: 2026-08-03 21:07:56 UTC

Repo-level (each fixture-yielding repo counted once), not fixture-weighted -- see this module's docstring for why.

## Per-dataset repo distributions

### Dataset A (agent-authored) -- 1,390 fixture-yielding repos

**language distribution**

| Value | Count | % |
|---|---|---|
| typescript | 714 | 51.4% |
| python | 496 | 35.7% |
| java | 98 | 7.1% |
| javascript | 82 | 5.9% |

**domain distribution**

| Value | Count | % |
|---|---|---|
| other | 684 | 49.2% |
| ml | 367 | 26.4% |
| web | 212 | 15.3% |
| devops | 35 | 2.5% |
| systems | 34 | 2.4% |
| database | 33 | 2.4% |
| security | 25 | 1.8% |

### Dataset B (human-authored, contemporary) -- 1,182 fixture-yielding repos

**language distribution**

| Value | Count | % |
|---|---|---|
| python | 807 | 68.3% |
| java | 193 | 16.3% |
| javascript | 182 | 15.4% |

**domain distribution**

| Value | Count | % |
|---|---|---|
| other | 641 | 54.2% |
| ml | 305 | 25.8% |
| web | 113 | 9.6% |
| database | 40 | 3.4% |
| systems | 31 | 2.6% |
| devops | 30 | 2.5% |
| security | 22 | 1.9% |

### Dataset C (human-authored, pre-LLM) -- 3,000 fixture-yielding repos

**language distribution**

| Value | Count | % |
|---|---|---|
| python | 1,133 | 37.8% |
| typescript | 737 | 24.6% |
| java | 578 | 19.3% |
| javascript | 552 | 18.4% |

**domain distribution**

| Value | Count | % |
|---|---|---|
| other | 1,945 | 64.8% |
| web | 472 | 15.7% |
| ml | 212 | 7.1% |
| database | 116 | 3.9% |
| security | 99 | 3.3% |
| systems | 80 | 2.7% |
| devops | 76 | 2.5% |

## A vs B: Dataset A (agent-authored) vs Dataset B (human-authored, contemporary)

**p >= 0.05 means balanced** (no evidence of a difference); Cliff's delta/Cramer's V say how big any difference actually is, independent of sample size (thresholds: negligible/small/medium/large). BH-FDR corrects for running all 3 of these tests together.

| Variable | Test | statistic | p-value | balanced (p>=0.05) | effect size | BH-FDR adjusted p (sig?) |
|---|---|---|---|---|---|---|
| language | chi-square | 845.8 | 4.964e-183 | **no** | 0.573 (large) | 1.489e-182 (yes) |
| domain | chi-square | 22.0 | 0.00122 | **no** | 0.092 (negligible) | 0.00122 (yes) |
| repo_age_years | mann-whitney-u | 367595.0 | 0.0003839 | **no** | 0.101 (negligible) | 0.0005759 (yes) |

## A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)

**p >= 0.05 means balanced** (no evidence of a difference); Cliff's delta/Cramer's V say how big any difference actually is, independent of sample size (thresholds: negligible/small/medium/large). BH-FDR corrects for running all 3 of these tests together.

| Variable | Test | statistic | p-value | balanced (p>=0.05) | effect size | BH-FDR adjusted p (sig?) |
|---|---|---|---|---|---|---|
| language | chi-square | 402.4 | 6.79e-87 | **no** | 0.303 (medium) | 2.037e-86 (yes) |
| domain | chi-square | 322.1 | 1.47e-66 | **no** | 0.271 (small) | 2.205e-66 (yes) |
| repo_age_years | mann-whitney-u | 909325.5 | 1.33e-28 | **no** | -0.253 (small) | 1.33e-28 (yes) |
