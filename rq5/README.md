# RQ5 review outputs

Written by `python -m collection.rq5_agent_file_scan`. Manual coding is done
in `rq5_repository_coding_sheet.csv`; `python -m collection.research_questions.rq5_coding`
reads it once every row is coded.

## Files

- `rq5_repositories.csv`: one row per analyzed repository.
- `rq5_fixture_matches.csv`: one row per fixture-keyword match, with two
  lines of context on each side. Not coded: it is the lookup for a snippet's
  context and for `evidence_row_id`. A match's **row id** is its 1-based
  position among the data rows (row id N is spreadsheet row N+1, below the
  header).
- `rq5_repository_coding_sheet.csv`: one row per repository with at least one fixture
  match. `fixture_snippets` lists all of the repository's matched lines, each
  prefixed with its row id, ordered by term (conftest, beforeEach, afterEach, beforeAll, afterAll, test setup, setup and teardown, fixture, fixtures),
  then file and line. The order is only a reading order, not a classification.
- `rq5_skipped_repositories.csv`: repositories that could not be analyzed.

## Coding columns of `rq5_repository_coding_sheet.csv`

- `code_fixture_guidance`: `yes` / `no` / `unsure`.
  Whether the repository's agent files give guidance about test fixtures as code.
- `evidence_row_id`: the match row id that confirmed `yes`. Required for `yes`.
- `category`: required for `yes`. One or more of the values below, separated by
  `;`. The values are the themes of Ardic et al. (SCAM 2026).
- `notes`: free text.

Allowed `category` values:

- `location_placement`
- `strategy`
- `tips`
- `avoidance`
- `example`
- `framework_environment`
- `other`
