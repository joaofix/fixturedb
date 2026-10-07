# Cross-Language Contamination Check

> For each dataset, what fraction of fixtures have their own detected language (from the fixture's own file) differ from their repo's tagged language?

Dataset C is checked against its fixture-level sample-down (`db/c_sampled.db`), not the full `db/c.db` -- see this module's docstring.

Generated: 2026-10-07 14:04:10 UTC

### Dataset A (agent-authored)

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

6,765/85,206 fixtures (7.94%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 3,310 | 277 | 8.37% | typescript=179, python=94, javascript=4 |
| javascript | 5,566 | 1,953 | 35.09% | typescript=1,536, python=383, java=34 |
| python | 24,293 | 1,548 | 6.37% | typescript=1,182, javascript=202, java=164 |
| typescript | 52,037 | 2,987 | 5.74% | javascript=2,131, python=814, java=42 |

### Dataset C (human-authored, pre-LLM)

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

7,480/82,680 fixtures (9.05%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 5,453 | 2,217 | 40.66% | typescript=1,104, python=1,003, javascript=110 |
| javascript | 6,820 | 2,523 | 36.99% | typescript=2,176, python=336, java=11 |
| python | 23,728 | 1,222 | 5.15% | typescript=980, javascript=226, java=16 |
| typescript | 46,679 | 1,518 | 3.25% | javascript=1,317, python=191, java=10 |
