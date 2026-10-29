# Cross-Language Contamination Check

> For each dataset, what fraction of fixtures have their own detected language (from the fixture's own file) differ from their repo's tagged language?

Dataset C is checked against its fixture-level sample-down (`db/c_sampled.db`), not the full `db/c.db` -- see this module's docstring.

Generated: 2026-10-27 03:29:43 UTC

### Dataset A (agent-authored)

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

6,762/85,136 fixtures (7.94%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 3,243 | 277 | 8.54% | typescript=179, python=94, javascript=4 |
| javascript | 5,566 | 1,953 | 35.09% | typescript=1,536, python=383, java=34 |
| python | 24,290 | 1,545 | 6.36% | typescript=1,182, javascript=202, java=161 |
| typescript | 52,037 | 2,987 | 5.74% | javascript=2,131, python=814, java=42 |

### Dataset C (human-authored, pre-LLM)

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

7,483/82,610 fixtures (9.06%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 5,374 | 2,225 | 41.40% | typescript=1,104, python=1,003, javascript=118 |
| javascript | 6,847 | 2,536 | 37.04% | typescript=2,176, python=336, java=24 |
| python | 23,729 | 1,223 | 5.15% | typescript=980, javascript=223, java=20 |
| typescript | 46,660 | 1,499 | 3.21% | javascript=1,298, python=191, java=10 |
