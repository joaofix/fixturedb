# RQ5 review outputs

Written by `python -m collection.rq5_agent_file_scan`. Manual coding is done
in `rq5_repository_coding_sheet.csv`; `python -m collection.research_questions.rq5_coding`
reads it once every row is coded.

Files searched: every guidance file of each repository, a file named
AGENTS.md, CLAUDE.md, GEMINI.md (case-insensitive) at the root or in any
subdirectory, outside dependency, build and cache directories. References
between files are not followed. Both lists are in
`collection/heuristics/rq5_agent_guidance_files.yaml`.

## Files

- `rq5_repositories.csv`: one row per analyzed repository, with its guidance
  files and whether the fixture match is in root or nested files.
- `rq5_fixture_matches.csv`: one row per fixture-keyword match, with the file
  path, its location (`root` or `nested`) and two lines of context on each side.
  Not coded: it is the lookup for a snippet's context. A match's **row id** is
  its 1-based position among the data rows (row id N is spreadsheet row N+1,
  below the header).
- `rq5_repository_coding_sheet.csv`: the coding sheet, one row per repository with at
  least one fixture match. `fixture_location` says whether the matches are in
  root files, nested files or both. The matched lines are not in the sheet;
  read them in `rq5_snippets.md`.
- `rq5_snippets.md`: the matched lines, for reading while coding.
  Repository N is data row N of the sheet; each matched line has its row id(s)
  in `rq5_fixture_matches.csv`, its location, a GitHub link and two lines of
  context on each side, ordered by term (conftest, beforeEach, afterEach, beforeAll, afterAll, test setup, setup and teardown, fixture, fixtures), then
  location, path and line. The order is only a reading order, not a
  classification.
- `rq5_skipped_repositories.csv`: repositories that could not be analyzed,
  with the reason; written only when there is at least one.

A new scan keeps the coding already in the sheet: see `carry_over_coding()` in
`collection/rq5_agent_file_scan.py`.

## Coding columns of `rq5_repository_coding_sheet.csv`

- `decision`: `yes` / `no` / `unsure`. One verdict per
  repository, over all of its guidance files.
  - `yes`: at least one match is about test fixtures: fixture code
    (pytest fixtures, `conftest.py`, `beforeEach`/`afterEach`, setUp/tearDown,
    ...) or fixtures used by tests (fixture files, test data). It may be
    inferred from the terms near the match instead of stated explicitly; do
    not be pedantic. Description counts as guidance: in an agent configuration
    file, a statement about how fixtures are done is an instruction to the
    agent. One such match is enough.
  - `no`: no match is about testing, e.g. a product or domain term named
    "fixture", a contract, a changelog entry, or a link to a setup document.
  - `unsure`: a match might be about test fixtures but its surrounding lines
    do not settle it.

  Decide from the matched lines and the lines around them only, as an average
  developer reading many unfamiliar projects: do not look elsewhere in the
  repository, and do not rely on specialist knowledge of the project, its
  language or its frameworks. The full rules, with examples, are in
  `DECISION_CODING.md`.
- `notes`: free text.

## Category coding

The fixture guidance of the repositories coded `yes` is categorized on a random
sample, with this study's own categories: see `rq5_category_sample.csv`,
`rq5_category_codebook.yaml` and `rq5_agreement_sheet.csv`, written by
`python -m collection.rq5_category_sample`. The instructions are in
`CATEGORY_CODING.md`.
