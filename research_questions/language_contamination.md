# Cross-Language Contamination Check

> For each dataset's per-language fixture CSV, what fraction of rows carry a `language` value that doesn't match the file's own nominal (filename) language?

Dataset C is checked against its fixture-level sample-down (`datasets/c/fixtures-sampled/`), not the full corpus (`datasets/c/fixtures/`) -- see this module's docstring.

Generated: 2026-09-08 01:16:31 UTC

### Dataset A (agent-authored) -- 0/70,623 fixtures mismatched (0.00%)

| CSV file | nominal language | total | mismatched | mismatched % | mismatched languages found |
|---|---|---|---|---|---|
| java_fixtures.csv | java | 2,261 | 0 | 0.00% | -- |
| javascript_fixtures.csv | javascript | 4,858 | 0 | 0.00% | -- |
| python_fixtures.csv | python | 20,684 | 0 | 0.00% | -- |
| typescript_fixtures.csv | typescript | 42,820 | 0 | 0.00% | -- |

### Dataset C (human-authored, pre-LLM) -- 0/70,623 fixtures mismatched (0.00%)

_Checked against `datasets/c/fixtures-sampled/` -- the fixture-level sample-down (`sample-c-repos --match-dataset a`), not the full `datasets/c/fixtures/` corpus. Same source every other `research_questions/` script uses for Dataset C (`db/c_sampled.db`)._

| CSV file | nominal language | total | mismatched | mismatched % | mismatched languages found |
|---|---|---|---|---|---|
| java_fixtures.csv | java | 2,261 | 0 | 0.00% | -- |
| javascript_fixtures.csv | javascript | 4,858 | 0 | 0.00% | -- |
| python_fixtures.csv | python | 20,684 | 0 | 0.00% | -- |
| typescript_fixtures.csv | typescript | 42,820 | 0 | 0.00% | -- |
