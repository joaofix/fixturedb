# RQ5 category coding: what does the fixture guidance say?

The first coding step decided which repositories have guidance about test
fixtures in their agent files (`yes` in `rq5_repository_coding_sheet.csv`; see
`DECISION_CODING.md`). This second step looks at *what* that guidance says:
where fixtures live, how to clean them up, what to keep out of them, and so on.
We sort it into categories that we built ourselves from the data.

We do not categorize all 586 repositories. We categorize an exploratory random
sample of 100 of them.

## The files

| File | What it is |
|---|---|
| `rq5_category_sample.csv` | The sheet you code: the repositories coded `yes`, in random order |
| `rq5_category_codebook.yaml` | The list of categories: a code, a name, a short description and a definition for each |
| `rq5_category_mapping.csv` | How the categories before the revision of 2026-10-15 map to the current ones |
| `rq5_snippets.md` | Where you read each repository's fixture lines, with context and GitHub links |
| `rq5_agreement_sheet.csv` | 20 repositories for a second coder (only when the agreement check is done) |
| `../rq5_coding.md` | The results, regenerated from the sheets |

This step never changes the decisions in `rq5_repository_coding_sheet.csv`.

## How the sample works

The 586 repositories coded `yes` are in a fixed random order, and the sample is
the first **100** rows of that order: an exploratory random sample (no margin
of error is computed). We code from the top; the `checkpoint` column is `100`
on rows 1–100.

The order was made in two steps, and both seeds are kept so that anyone can
reproduce it:

1. **First pass.** All the 556 repositories coded `yes` in the first pass were
   shuffled once, at random, with a fixed seed (**20261012**). The first 83
   rows were coded.
2. **Decision review (2026-10-13).** A second review of the decisions changed
   the population to **586**: 8 repositories left `yes` and 38 joined. One of
   the 8 had been coded, so 82 coded rows remained, out of the 548 repositories
   of the first pass that are still `yes`. The order was rebuilt once: the 548
   keep their order and coding, the 38 new ones were shuffled with seed
   **20261014**, and the two are interleaved at the same rate. Rows 1–82 are
   the coded rows of the first pass, rows 83–88 the first 6 of the 38, and
   after that each row comes from the group further below its share, so any
   first *n* rows hold both groups at the same rate.

Rows 1–88 were coded before the sample was set at 100; rows 89–100 are the ones
still to be coded.

## Coding a row

Each row of `rq5_category_sample.csv` is one repository. Read its fixture lines
in `rq5_snippets.md`: search for the repository's name to find its section,
which shows every matched line with two lines of context and a GitHub link.

You fill three columns:

| Column | What to write |
|---|---|
| `open_code` | In your own words, what the fixture guidance says. |
| `categories` | The codes of every category that applies, separated by `;` (for example `location; quality`). |
| `notes` | Anything worth remembering. Optional. |

A few rules keep the coding consistent:

- **Judge the repository, not the file.** A repository gets every category that
  any of its fixture lines supports, whether those lines are in several files,
  in one file, or even in one sentence. Example: "Shared durable test or
  local-development fixtures must be created through the owning module's …
  `seed()` hook and treated as read-only by tests" gives both *Creation* and
  *Quality*.
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

The codebook (`rq5_category_codebook.yaml`) is the official list; this table
only adds an example for each. The `definition` of each category is still to
be written.

| Category (code) | What the guidance says | Example |
|---|---|---|
| Location (`location`) | Where fixtures live or should be placed. | "Fixtures (sample PDF, docx, xlsx, archive, etc.) live in `test/fixtures/`." |
| Creation (`creation`) | When to create fixtures or reuse existing ones. | "Add fixture in `tests/fixtures/<tool_name>_output.(json\|xml\|txt)`" |
| Quality (`quality`) | Qualities fixtures should have and keep. | "Use the smallest synthetic fixture that crosses the required boundary" |
| Conventions (`conventions`) | Which fixture mechanism and scope to use. | "Prefer fixtures over setup/teardown methods" |
| Test doubles (`test_doubles`) | Mocks and stubs handled by fixtures. | "Unit test conftest provides `driver` fixture as MagicMock" |
| Security (`security`) | No real or private data in fixtures. | "Never commit secrets, credentials, or raw sensitive payloads in logs or fixtures." |
| Miscellaneous (`miscellaneous`) | Guidance that fits no other category. | (none coded yet) |
| Non-actionable mention (`non_actionable`) | Mentions fixtures without instructions. Kept in the sheet, but not in the results (`in_results: false`). | "Test conventions, fixtures: HACKING.rst / TESTING.rst" |

A repository coded `non_actionable` stays in the coded sample and in the
denominator of every share, but the category is left out of the category table
and the per-repository counts. The report lists the repositories that have it
as their only category.

### The category revision (2026-10-15)

The first categories came out of open coding the first 83 rows. On
2026-10-15 they were revised: several were merged or renamed, and one was
taken out of the results. `rq5_category_mapping.csv` gives the old-to-new
mapping:

| Before | Now |
|---|---|
| Location | Location |
| Fixture creation, Reuse | Creation |
| Fixture design, Fixture maintenance, Test isolation, Cleanup | Quality |
| Framework features | Conventions |
| Test doubles | Test doubles |
| Sensitive information | Security |
| Non-actionable mention | Non-actionable mention, kept in the sheet but not in the results |

The mapping was applied to the coded rows automatically, removing duplicates
(a repository coded with both Fixture design and Cleanup gets `quality` once);
nothing else was recoded. The state before the revision is the git tag
`rq5-categories-before-revision`.

## Changing the categories

The categories can still change while coding. To add, rename, split or merge
one:

1. Edit `rq5_category_codebook.yaml`. Each entry has a `code` (one word in
   snake_case, used in the sheet), a `name` and a `description` (one line,
   shown in the results and the paper), and a `definition` (written so that
   someone else could apply it without asking; it may be left empty). An
   entry with `in_results: false` stays usable in the sheet but is left out
   of the results.
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

- the sample: how many of the 100 are coded, and the seeds of the order;
- each category with its description, number of repositories and share of the
  sample (a repository can have several categories, so the shares add up to
  more than 100%);
- how many categories a repository has (median, minimum, maximum);
- for each category with `in_results: false` (Non-actionable mention), the
  repositories that have it as their only category, and how many have it
  together with other categories;
- the languages of the sample next to those of all 586 repositories;
- the agreement with the second coder, once available.

## Things that break the sample

- Regenerating the sample after coding has started (the command refuses).
- Reordering, deleting or skipping rows.
- Changing decisions in `rq5_repository_coding_sheet.csv` after sampling: the
  sample no longer matches the repositories coded `yes`, and the analysis stops.
- Writing a code in `categories` before adding it to the codebook.
