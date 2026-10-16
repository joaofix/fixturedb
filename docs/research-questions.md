# Research questions

The study asks five questions. RQ2 to RQ4 compare agent-written fixtures
(Dataset A) with pre-LLM human fixtures (Dataset C). RQ1 describes the raw
repository universe. RQ5 describes the repositories that contribute to Dataset A,
so neither compares the two datasets.

Each question has a script in `collection/research_questions/`. The script
writes its results to `research-questions/<rq>.md`.

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

Input: the guidance files of every repository that contributes at least one
fixture to Dataset A: every file named `AGENTS.md`, `CLAUDE.md` or `GEMINI.md`
(case-insensitive) in the repository's tree, at the root or in any
subdirectory (for example `packages/api/AGENTS.md`). References between files
are not followed: a file is read because of its name, wherever it is. Files
under dependency, build and cache directories (`node_modules`, `vendor`,
`build`, `dist`, `target`, ...; the same list as the Dataset A agent-config
detector) are not read, since they can ship another project's guidance file.
Both lists are in `collection/heuristics/rq5_agent_guidance_files.yaml`.

Every file is read at the last commit on or before a snapshot date, a required
argument of the scan. A guidance file that is a symbolic link is read through
its target, followed within the repository (at most 5 links). Each real file
is read once: a link to a guidance file already read (`CLAUDE.md` linking to
`AGENTS.md`) is not read again, and a link that leaves the repository or
points at nothing is not read. Git submodules are not entered, since their
content lives in another repository.

An earlier version of RQ5 followed Ardic et al. (SCAM 2026): 18 root file names
plus the Markdown files they reference, one hop away (`CONTRIBUTING.md`,
`TESTING.md`, `SKILL.md`, ...). The three names at any depth replace both lists.

The scan (`rq5_agent_file_scan.py`) uses the GitHub API and does not clone
repositories. Per batch of 25 repositories, one GraphQL query finds each
repository's snapshot commit, one REST request per repository lists its whole
tree (recursive Git Trees endpoint), and batched GraphQL queries read the
files. When GitHub truncates the listing of a very large tree, the tree is
fetched in parts: its direct children, then each subdirectory's own recursive
listing (split again where still truncated), skipping the excluded
directories. Root and
nested files are searched for test-related and fixture-related terms with the
same rules. The keyword catalog is
`collection/heuristics/rq5_agent_file_keywords.yaml`. A repository counts as
matching if any of its guidance files matches.

The report (`research-questions/rq5.md`) gives numbers and definitions only. At
repository level: the share of repositories with a guidance file (and with one
at the root), and among those the shares matching the test keywords (the
keyword set of Ardic et al., SCAM 2026: test, tests, testing, tested) and the
fixture keywords, overall and per language, plus the number of repositories
containing each fixture term. Per match: how many fixture matches fall inside
fenced code blocks, overall and per term. It also reports where the guidance
files are: per file name (files, repositories, at the root, nested), the
repositories with nested files only, the repositories whose fixture match comes
only from nested files, the files read through a symbolic link, and the
repositories whose file list was fetched in parts.

A fixture keyword match is not fixture guidance: many "fixture"/"fixtures"
matches refer to test-data files, which are out of scope. The final RQ5 number
comes from manual coding of `research-questions/rq5/rq5_repository_coding_sheet.csv`, one row per
repository with a fixture match in its guidance files (the rules, with examples,
are in `research-questions/rq5/DECISION_CODING.md`). The matched lines are read in
`research-questions/rq5/rq5_snippets.md`, one section per sheet row, with their
file path, whether they come from a root or a nested file, their context and
a GitHub link. A repository is coded `yes` when at least one match, in any of
its guidance files, is about test fixtures, either fixture code or fixtures
used by tests (fixture files, test data), including when this is inferred from
the terms near the match rather than stated; a description counts as guidance,
because in an agent configuration file it acts as an instruction to the agent.
Every other repository is coded `no`, including one whose matches might be about
test fixtures but whose text does not settle it: an unclear case is never
counted as fixture guidance. Decisions use only the matched lines and the lines around them, read as an
average developer would, without looking elsewhere in the repository or relying
on specialist knowledge of the project. Once every
row is coded, `collection/research_questions/rq5_coding.py` writes
`research-questions/rq5_coding.md`: the share of repositories with a guidance
file coded `yes` (overall and per language), the precision of the keyword search,
and the categories of the coded category sample (below). It refuses to
run while any row is uncoded.

A rescan never discards coding. When the coding sheet already holds coding,
the scan copies it and its `rq5_fixture_matches.csv` into `db/` (timestamped)
and writes the new sheet with the coding carried over: a repository still in
the sheet keeps its decision and notes exactly as they were, even if
its matches changed; a repository that no longer has a fixture match is
dropped; a new repository is added uncoded. The outcome per coded repository
(`unchanged`, `matches_changed`, `removed`) is written next to the backup.

### RQ5 categories

The coders' instructions are in `research-questions/rq5/CATEGORY_CODING.md`.
The fixture guidance of the repositories coded `yes` is categorized by open
coding a random sample, with this study's own categories (not Ardic et al.'s).
`python -m collection.rq5_category_sample sample` writes
`research-questions/rq5/rq5_category_sample.csv`: all repositories coded `yes`
(556), in one simple random permutation of the coding sheet's order (seed
20261012, not stratified), with empty `open_code`, `categories` and `notes`
columns; the matched lines are read in `rq5_snippets.md`, and the languages
reported for the sample come from the scan database. Rows are coded from the top, so the coded sample
is always the prefix of rows with `categories` filled. The sample is the first
100 rows (`SAMPLE_SIZE`), marked `100` in the `checkpoint` column: an
exploratory random sample, for which no margin of error is computed. It also
writes an empty `rq5_category_codebook.yaml`, where each category gets a
`code` (one snake_case word, used in `categories`), a `name`, a one-line
`description` (shown in the report and the paper), a `definition` (may be
left empty) and, optionally, `in_results: false` to keep a category in the
sheet but out of the results.

That command made the order of the first coding pass, whose first 83 rows were
coded. A review of the decisions (2026-10-13) then changed the population to
586 repositories coded `yes`: 8 left (one of them coded) and 38 joined. The
order was rebuilt once, by hand, keeping the coding already done: the 548
first-pass repositories still coded `yes` keep their order (and the 82 coded
rows their coding), the 38 new ones are shuffled with seed 20261014, and the
two are interleaved so that any first rows hold both at the same rate (rows
83–88 are the first 6 of the 38). The sample was then set to the first 100 rows
of this order, without reshuffling (rows 1–88 were already coded). The
constants are in `collection/rq5_category_sample.py` (`SAMPLE_SIZE`,
`TOP_UP_SEED`, `ORIGINAL_STRATUM`, `ADDED_STRATUM`).

The categories were revised once (2026-10-15), after the first 88 rows were
coded: several were merged or renamed, and one, Non-actionable mention, was
taken out of the results (`in_results: false`): its repositories keep it in
the sheet and stay in the sample and in the denominator of every share, but it
is not in the category table or the per-repository counts.
`research-questions/rq5/rq5_category_mapping.csv` maps each old category code
to its new one. The mapping was applied to the coded rows automatically, with
duplicates removed; nothing else was recoded. The state before the revision is
the git tag `rq5-categories-before-revision`.

The `rq5_coding` report then gives how many of the 100 are coded and the seeds
of the order, each category's repositories and share of the coded sample (a
repository can have several categories), the number of categories per
repository, the repositories whose only category is out of the results
(Non-actionable mention) and how many have it with other categories, and the
languages of
the coded sample next to those of all 586. It fails if a row after the coded
prefix has categories (coding out of order), if
a code is not in the codebook, or if the sample no longer matches the
repositories coded `yes`; if the coded prefix is not exactly the 100 rows of the
sample, it warns and reports the actual size.

For inter-coder agreement, `python -m collection.rq5_category_sample
agreement-sheet` draws 20 repositories from the coded prefix (seed 20261013)
into `rq5_agreement_sheet.csv` for a second coder, and
`python -m collection.rq5_category_sample agreement` compares the two codings:
per category, each repository is yes or no for that category, with percent
agreement and Cohen's kappa (undefined, and left out of the average, when both
coders gave every repository the same value). Once the second sheet is fully
coded, the `rq5_coding` report includes the agreement table.

## Where the numbers come from

| Question | Reads | Writes |
|----------|-------|--------|
| RQ1 | `db/rq1_prevalence.db` | `research-questions/rq1.md` |
| RQ2 | `db/a.db`, `db/c.db` | `research-questions/rq2.md` |
| RQ3 | `db/a.db`, `db/c.db` | `research-questions/rq3.md` |
| RQ4 | `db/a.db`, `db/c.db` | `research-questions/rq4.md` |
| RQ5 | `db/rq5_agent_files.db` (Dataset A repositories) | `research-questions/rq5.md` |

See [Limitations](reference/limitations.md) before reading any comparison.
