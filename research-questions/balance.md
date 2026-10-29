# Control-Variable Balance Check

> Are the repo samples behind two datasets comparable on language, domain, and repo age -- before attributing an RQ2-4 fixture-metric difference to authorship or era? See this module's docstring for why this check was not run against the current data.

Generated: 2026-10-27 03:29:25 UTC

Repo-level (each fixture-yielding repo counted once), not fixture-weighted -- see this module's docstring for why.

## Per-dataset repo distributions

### Dataset A (agent-authored) -- 2,167 fixture-yielding repos

**language distribution**

| Value | Count | % |
|---|---|---|
| typescript | 1,076 | 49.7% |
| python | 778 | 35.9% |
| java | 161 | 7.4% |
| javascript | 152 | 7.0% |

**domain distribution**

| Value | Count | % |
|---|---|---|
| other | 1,234 | 56.9% |
| ml | 438 | 20.2% |
| web | 298 | 13.8% |
| systems | 56 | 2.6% |
| database | 54 | 2.5% |
| security | 52 | 2.4% |
| devops | 35 | 1.6% |

### Dataset C (human-authored, pre-LLM) -- 2,572 fixture-yielding repos

**language distribution**

| Value | Count | % |
|---|---|---|
| python | 995 | 38.7% |
| typescript | 785 | 30.5% |
| javascript | 424 | 16.5% |
| java | 368 | 14.3% |

**domain distribution**

| Value | Count | % |
|---|---|---|
| other | 1,608 | 62.5% |
| web | 466 | 18.1% |
| ml | 194 | 7.5% |
| database | 89 | 3.5% |
| security | 77 | 3.0% |
| systems | 70 | 2.7% |
| devops | 68 | 2.6% |

## A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)

**p >= 0.05 means balanced** (no evidence of a difference); Cliff's delta/Cramer's V say how big any difference actually is, independent of sample size (thresholds: negligible/small/medium/large). BH-FDR corrects for running all 3 of these tests together.

| Variable | Test | statistic | p-value | balanced (p>=0.05) | effect size | BH-FDR adjusted p (sig?) |
|---|---|---|---|---|---|---|
| language | chi-square | 248.7 | 1.243e-53 | **no** | 0.229 (small) | 1.865e-53 (yes) |
| domain | chi-square | 172.6 | 1.294e-34 | **no** | 0.191 (small) | 1.294e-34 (yes) |
| repo_age_years | mann-whitney-u | 1142340.0 | 4.662e-61 | **no** | -0.323 (small) | 1.399e-60 (yes) |
