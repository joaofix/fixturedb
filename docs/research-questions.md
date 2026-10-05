# Research questions

The study asks five questions. RQ2 to RQ4 compare agent-written fixtures
(Dataset A) with pre-LLM human fixtures (Dataset C). RQ1 and RQ5 describe the
raw repository universe, so they do not compare the two datasets.

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

Input: the root `AGENTS.md` and `CLAUDE.md` files of the same repositories as
RQ1. The scan (`rq5_agent_file_scan.py`) uses the GitHub API and does not clone
repositories.

The scan counts keyword matches for test-related and fixture-related terms. The
catalog of keywords is in `collection/heuristics/rq5_agent_file_keywords.yaml`.
The report gives the share of repositories that mention testing and the share
that mention fixtures.

## Where the numbers come from

| Question | Reads | Writes |
|----------|-------|--------|
| RQ1 | `db/rq1_prevalence.db` | `research_questions/rq1.md` |
| RQ2 | `db/a.db`, `db/c.db` | `research_questions/rq2.md` |
| RQ3 | `db/a.db`, `db/c.db` | `research_questions/rq3.md` |
| RQ4 | `db/a.db`, `db/c.db` | `research_questions/rq4.md` |
| RQ5 | `db/rq5_agent_files.db` | `research_questions/rq5.md` |

See [Limitations](reference/limitations.md) before reading any comparison.
