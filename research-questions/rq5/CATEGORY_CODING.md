# RQ5 category coding: what does the fixture guidance say?

The first coding step decided which repositories have guidance about test
fixtures in their agent files (`yes` in `rq5_repository_coding_sheet.csv`; see
`DECISION_CODING.md`). This second step looks at *what* that guidance says:
where fixtures live, how to clean them up, what to keep out of them, and so on.
We sort it into categories that we built ourselves from the data.

We do not categorize all 586 repositories. We categorize a random sample, large
enough to describe the whole group with a known margin of error.

## The files

| File | What it is |
|---|---|
| `rq5_category_sample.csv` | The sheet you code: the repositories coded `yes`, in random order |
| `rq5_category_codebook.yaml` | The list of categories: a code, a name and a definition for each |
| `rq5_snippets.md` | Where you read each repository's fixture lines, with context and GitHub links |
| `rq5_agreement_sheet.csv` | 20 repositories for a second coder (only when the agreement check is done) |
| `../rq5_coding.md` | The results, regenerated from the sheets |

This step never changes the decisions in `rq5_repository_coding_sheet.csv`.

## How the sample works

The rows are in random order, so the first *n* rows are a random sample of
size *n*. So we simply code from the top, and at a checkpoint what we have
coded is a valid random sample.

The order was made in two steps:

1. **First pass.** All the 556 repositories coded `yes` in the first pass were
   shuffled once, at random, with a fixed seed (**20261012**) so that anyone
   can reproduce the same order. The first 83 rows (the ±10% checkpoint for
   N = 556: **83** rows, and **228** for ±5%) were coded.
2. **Decision review (2026-10-13).** A second review of the decisions changed
   the population to **586**: 8 repositories left `yes` and 38 joined. One of
   the 8 had been coded, so 82 coded rows remained, out of the 548 repositories
   of the first pass that are still `yes`. The sample was rebuilt once as a
   **proportional stratified sample**: the 548 keep their order and coding, the
   38 new ones were shuffled with seed **20261014**, and the two are
   interleaved at the same rate. Rows 1–82 are the coded rows of the first
   pass, rows 83–88 the first 6 of the 38 (82/548 of 38 = 5.7, rounded to 6),
   and after that each row comes from the group further below its share.
   Because both groups are sampled at the same rate, the coded rows are again
   a random sample of all 586, with no weighting.

There are two good places to stop, marked in the `checkpoint` column:

| Stop after | Margin of error | `checkpoint` column |
|---|---|---|
| **88** rows | ±9.6% | `88` on rows 1–88 |
| **233** rows | ±5% | `233` on rows 89–233 |

"±10%" means that if 30% of the coded repositories have a category, the true
share among all 586 is, with 95% confidence, between 20% and 40%.

<details>
<summary>Where 88 and 233 come from</summary>

Cochran's formula at 95% confidence (z = 1.96), with p = 0.5 (the most
cautious choice) and the finite population correction, rounded up:

- n0 = z² · p · (1 − p) / e²
- n = n0 / (1 + (n0 − 1) / N)

For N = 586, e = 0.10 gives 82.64, so 83; e = 0.05 gives 232.28, so 233. The
first checkpoint is 88 rather than 83 because 88 is where both groups are at
the same rate (82 of 548 and 6 of 38); at 233 there are 218 and 15. The margin
reported for the size actually reached is
z · √(p (1 − p) / n · (N − n) / (N − 1)): 9.6% at 88 and 5.0% at 233.
</details>

## Coding a row

Each row of `rq5_category_sample.csv` is one repository. Read its fixture lines
in `rq5_snippets.md`: search for the repository's name to find its section,
which shows every matched line with two lines of context and a GitHub link.

You fill three columns:

| Column | What to write |
|---|---|
| `open_code` | In your own words, what the fixture guidance says. |
| `categories` | The codes of every category that applies, separated by `;` (for example `location; cleanup`). |
| `notes` | Anything worth remembering. Optional. |

A few rules keep the coding consistent:

- **Judge the repository, not the file.** A repository gets every category that
  any of its fixture lines supports, whether those lines are in several files,
  in one file, or even in one sentence. Example: "Shared durable test or
  local-development fixtures must be created through the owning module's …
  `seed()` hook and treated as read-only by tests" gives both *Fixture
  creation* and *Test isolation*.
- **Only fixture lines count.** A line next to a fixture match that talks about
  something else adds no category.
- **Repeated text counts once.** The same guidance in `AGENTS.md` and
  `CLAUDE.md` is one piece of guidance.
- **Use only what you see**, as in the first step: the lines in
  `rq5_snippets.md`, without looking elsewhere in the repository.
- **Every row gets at least one category.** If a repository looks like it
  should not have been `yes`, say so in `notes` and give it the closest
  category; do not change the decision sheet from here.
- **Code from the top, without skipping.** Results use the rows from row 1 down
  to the first row without categories. A filled row after an empty one stops
  the analysis with an error ("coding out of order"), because skipping rows
  would break the randomness of the sample.

## The categories

These came out of open coding the first 83 rows. The codebook
(`rq5_category_codebook.yaml`) is the official list; this table only adds an
example for each.

| Category (code) | What the guidance says | Example |
|---|---|---|
| Location (`location`) | Where fixtures live or should be placed. | "Fixtures (sample PDF, docx, xlsx, archive, etc.) live in `test/fixtures/`." |
| Reuse (`reuse`) | Using existing fixtures. | "Use the shared `context` pytest fixture from `test/config/conftest.py`" |
| Framework features (`framework`) | Which fixture mechanism and scope to use. | "Prefer fixtures over setup/teardown methods" |
| Test doubles (`test_doubles`) | Mocks and stubs handled by fixtures. | "Unit test conftest provides `driver` fixture as MagicMock" |
| Fixture creation (`creation`) | When and how to create fixtures. | "Add fixture in `tests/fixtures/<tool_name>_output.(json\|xml\|txt)`" |
| Fixture design (`design`) | Qualities that fixtures should have. | "Use the smallest synthetic fixture that crosses the required boundary" |
| Fixture maintenance (`maintenance`) | Keeping fixtures up to date. | "All binary fixtures under `tests/fixtures/` MUST be tracked via git-lfs." |
| Cleanup (`cleanup`) | Removing what fixtures or tests create. | "Cleanup runs from `afterAll` even when an assertion fails" |
| Test isolation (`isolation`) | Avoiding state leaks between tests. | "Every PG/MySQL container suite MUST own its fixture database." |
| Sensitive information (`sensitive`) | No real or private data in fixtures. | "Never commit secrets, credentials, or raw sensitive payloads in logs or fixtures." |
| Non-actionable mention (`non_actionable`) | Mentions fixtures without instructions. | "Test conventions, fixtures: HACKING.rst / TESTING.rst" |

Two boundaries need care (they are also `note`s in the codebook):

- **Reuse** also covers guidance that only lists or names the fixtures
  available, such as a table of the fixtures in `conftest.py`.
- **Fixture creation** is about the tool or procedure that creates a fixture
  ("Build fixtures with `@verdaccio/test-helper`"); what the fixture should be
  like ("deterministic", "synthetic") is **Fixture design**.

## Changing the categories

The categories can still change while coding. To add, rename, split or merge
one:

1. Edit `rq5_category_codebook.yaml`. Each entry has a `code` (one word in
   snake_case, used in the sheet), a `name` (shown in the results) and a
   `definition` (written so that someone else could apply it without asking).
   An entry can also have a `note`: a hint for coders on a boundary case, which
   is not shown in the results.
2. Go back over the rows already coded and update their `categories` to match.

A code used in the sheet but missing from the codebook stops the analysis with
an error, so the two cannot drift apart silently.

## Checking agreement with a second coder

To show that the categories are clear enough for someone else to apply:

1. Once at least 20 rows are coded, run
   `python -m collection.rq5_category_sample agreement-sheet`. It picks 20
   repositories at random from the coded rows (seed **20261013**) and writes
   `rq5_agreement_sheet.csv` with an empty `categories` column. The second
   coder reads the lines in `rq5_snippets.md`, like the first.
2. The second coder fills `categories` for all 20 repositories, using only the
   codebook and without looking at the first coding.
3. Run `python -m collection.rq5_category_sample agreement`, or regenerate the
   results: once all 20 rows are filled, `rq5_coding.md` shows the agreement.

For each category, each repository is either in it or not, for each coder. The
report gives, per category, how often the two coders agree and Cohen's kappa
(agreement corrected for chance). Kappa cannot be computed for a category that
both coders gave to every repository, or to none; it then shows `n/a`.

## Commands

```bash
# Once, before coding: shuffle the sample and create an empty codebook
python -m collection.rq5_category_sample sample

# Any time: regenerate the results (decisions and categories)
python -m collection.research_questions.rq5_coding

# Agreement check
python -m collection.rq5_category_sample agreement-sheet
python -m collection.rq5_category_sample agreement
```

The sample command refuses to overwrite a sheet that already has coding. It
wrote the first-pass order; the rebuild after the decision review was done
once, by hand, and the command is not run again.

## What the results show

The "Categories" section of `rq5_coding.md` reports:

- the sample: size reached, checkpoint, confidence and margin of error;
- each category with its definition, number of repositories and share of the
  sample (a repository can have several categories, so the shares add up to
  more than 100%);
- how many categories a repository has (median, minimum, maximum);
- the languages of the sample next to those of all 586 repositories;
- the agreement with the second coder, once available.

## Things that break the sample

- Regenerating the sample after coding has started (the command refuses).
- Reordering, deleting or skipping rows.
- Changing decisions in `rq5_repository_coding_sheet.csv` after sampling: the
  sample no longer matches the repositories coded `yes`, and the analysis stops.
- Writing a code in `categories` before adding it to the codebook.
