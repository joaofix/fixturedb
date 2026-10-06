# Research questions

The study asks five questions. RQ2 to RQ4 compare agent-written fixtures
(Dataset A) with pre-LLM human fixtures (Dataset C). RQ1 describes the raw
repository universe. RQ5 describes the repositories that contribute to Dataset A,
so neither compares the two datasets.

Each question has a script in `collection/research_questions/`. The script
writes its results to `research_questions/<rq>.md`.

## RQ1: How common are test fixtures?

Input: about 24.7k candidate repositories. The scan (`rq1_prevalence_scan.py`)
clones each repository at a fixed date and counts its test files, fixtures,
setups and teardowns.

- **Table 1:** of the repositories with tests, the share that contain at least
  one fixture, one setup, or one teardown.
- **Table 2:** the median number of fixtures, setups and teardowns per
  repository, counting only repositories with at least one fixture.

Repositories whose clone failed are left out of both tables.

## RQ2: What do fixtures look like?

Metrics per fixture: lines of code (non-blank lines in the body), cyclomatic
complexity, and comment density (single-line comments divided by lines of
code).

Each repository contributes the mean of its own fixtures. We compare the two
datasets with a Mann-Whitney U test. For the per-language rows, p-values are
corrected with Benjamini-Hochberg within each metric.

## RQ3: What types of fixtures do agents and humans write?

Each fixture is classified as setup, teardown, or other. The table shows the
counts of setups and teardowns per language.

It also reports teardown coverage: the share of repositories with at least one
teardown. No statistical test is applied.

## RQ4: Do fixtures mock?

A fixture counts as mocking when it contains at least one mock call.

The table reports mocking coverage: the share of repositories with at least one
mocking fixture. It is computed per language and overall. No statistical test is
applied.

## RQ5: What do agent configuration files say about tests?

Input: the root `AGENTS.md` and `CLAUDE.md` files of every repository that
contributes at least one fixture to Dataset A. Each file is read at the last
commit on or before a snapshot date. The snapshot date is a required argument of
the scan.

The scan (`rq5_agent_file_scan.py`) uses the GitHub GraphQL API, in batches of
25 repositories, and does not clone repositories. It searches for test-related and fixture-related terms. The keyword
catalog is `collection/heuristics/rq5_agent_file_keywords.yaml`.
A repository counts as matching if any of its root files matches.

The report (`research_questions/rq5.md`) gives numbers and definitions only. At
repository level: the share of repositories with a root agent file, and among
those the shares matching the test keywords, the keyword set of Ardic et al.
(SCAM 2026), and the fixture keywords, overall and per language, plus the number
of repositories containing each fixture term. Per match: how many fixture
matches fall inside fenced code blocks, overall and per term.

A fixture keyword match is not fixture guidance: many "fixture"/"fixtures"
matches refer to test-data files, which are out of scope. The final RQ5 number
comes from manual coding of `rq5/rq5_repository_coding_sheet.csv`, one row per
repository with a fixture match (coding values in `rq5/README.md`), read through
`rq5/rq5_snippets.md`, which shows each repository's matched lines with their
context and a GitHub link. A repository is coded `yes` when at least one match
refers to test fixtures as code; a description counts as guidance, because in
an agent configuration file it acts as an instruction to the agent. Once every
row is coded, `research_questions/rq5_coding.py` writes
`research_questions/rq5_coding.md`: the share of repositories with a root agent
file coded `yes` (overall and per language), the precision of the keyword search
(with `unsure` reported separately), and the repositories per category. It
refuses to run while any row is uncoded.

## Where the numbers come from

| Question | Reads | Writes |
|----------|-------|--------|
| RQ1 | `db/rq1_prevalence.db` | `research_questions/rq1.md` |
| RQ2 | `db/a.db`, `db/c.db` | `research_questions/rq2.md` |
| RQ3 | `db/a.db`, `db/c.db` | `research_questions/rq3.md` |
| RQ4 | `db/a.db`, `db/c.db` | `research_questions/rq4.md` |
| RQ5 | `db/rq5_agent_files.db` (Dataset A repositories) | `research_questions/rq5.md` |

See [Limitations](reference/limitations.md) before reading any comparison.
