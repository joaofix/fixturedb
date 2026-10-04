# Cross-Language Contamination Check

> For each dataset, what fraction of fixtures have their own detected language (from the fixture's own file) differ from their repo's tagged language?

Dataset C is checked against its fixture-level sample-down (`db/c_sampled.db`), not the full `db/c.db` -- see this module's docstring.

Generated: 2026-10-04 15:59:22 UTC

### Dataset A (agent-authored)

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

5,352/70,623 fixtures (7.58%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 2,265 | 262 | 11.57% | typescript=175, python=86, javascript=1 |
| javascript | 3,975 | 1,210 | 30.44% | typescript=1,017, python=170, java=23 |
| python | 21,078 | 1,253 | 5.94% | typescript=950, javascript=160, java=143 |
| typescript | 43,305 | 2,627 | 6.07% | javascript=1,932, python=603, java=92 |

### Dataset C (human-authored, pre-LLM)

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

6,376/70,623 fixtures (9.03%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 4,157 | 1,936 | 46.57% | typescript=990, python=866, javascript=80 |
| javascript | 5,610 | 2,126 | 37.90% | typescript=1,797, python=314, java=15 |
| python | 20,359 | 1,013 | 4.98% | typescript=837, javascript=162, java=14 |
| typescript | 40,497 | 1,301 | 3.21% | javascript=1,132, python=158, java=11 |
