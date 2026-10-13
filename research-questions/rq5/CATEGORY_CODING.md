# RQ5 category coding: what does the fixture guidance say?

The first coding step decided which repositories have guidance about test
fixtures in their agent files (`yes` in `rq5_repository_coding_sheet.csv`; see
`DECISION_CODING.md`). This second step looks at *what* that guidance says:
where fixtures live, how to clean them up, what to keep out of them, and so on.
We sort it into categories that we built ourselves from the data.

We do not categorize all 556 repositories. We categorize a random sample, large
enough to describe the whole group with a known margin of error.

## The files

| File | What it is |
|---|---|
| `rq5_category_sample.csv` | The sheet you code: the repositories coded `yes`, in random order, with their fixture lines |
| `rq5_category_codebook.yaml` | The list of categories: a code, a name and a definition for each |
| `rq5_snippets.md` | The full matched lines with more context, for when the sheet is not enough |
| `rq5_agreement_sheet.csv` | 20 repositories for a second coder (only when the agreement check is done) |
| `../rq5_coding.md` | The results, regenerated from the sheets |

This step never changes the decisions in `rq5_repository_coding_sheet.csv`.

## How the sample works

All the 556 repositories coded `yes` were shuffled once, at random, with a
fixed seed (**20261012**) so that anyone can reproduce the same order. Because
the order is random, the first *n* rows are a random sample of size *n*. So we
simply code from the top, and wherever we stop, what we have coded is a valid
random sample.

There are two good places to stop, marked in the `checkpoint` column:

| Stop after | Margin of error | `checkpoint` column |
|---|---|---|
| **83** rows | ±10% | `83` on rows 1–83 |
| **228** rows | ±5% | `228` on rows 84–228 |

"±10%" means that if 30% of the coded repositories have a category, the true
share among all 556 is, with 95% confidence, between 20% and 40%.

<details>
<summary>Where 83 and 228 come from</summary>

Cochran's formula at 95% confidence (z = 1.96), with p = 0.5 (the most
cautious choice) and the finite population correction for N = 556, rounded up:

- n0 = z² · p · (1 − p) / e²
- n = n0 / (1 + (n0 − 1) / N)

For e = 0.10 this gives 82.02, so 83; for e = 0.05 it gives 227.43, so 228. The
margin reported for the size actually reached is
z · √(p (1 − p) / n · (N − n) / (N − 1)): 9.9% at 83 and 5.0% at 228.
</details>

## Coding a row

Each row of `rq5_category_sample.csv` is one repository. The `snippets` cell
shows every fixture line found in it: a row id and the file it comes from, then
the line before, the matched line (marked `>`) and the line after. If a
repository has so much text that it does not fit in one cell, the cell ends
with a note pointing to its section in `rq5_snippets.md`.

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
- **Use only what you see**, as in the first step: the lines in the sheet (or in
  `rq5_snippets.md`), without looking elsewhere in the repository.
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
| Location (`location`) | Where fixtures live or must be placed. | "Fixtures (sample PDF, docx, xlsx, archive, etc.) live in `test/fixtures/`." |
| Reuse (`reuse`) | Use or reuse existing fixtures, or names the ones available. | "Use the shared `context` pytest fixture from `test/config/conftest.py`" |
| Framework features (`framework`) | How to use the framework's fixture features: which mechanism, at what scope. | "Prefer fixtures over setup/teardown methods" |
| Test doubles (`test_doubles`) | Mocks, stubs or fakes provided by fixtures or reset in hooks. | "Unit test conftest provides `driver` fixture as MagicMock" |
| Fixture creation (`creation`) | When to add a fixture, or which tool or procedure creates it. | "Add fixture in `tests/fixtures/<tool_name>_output.(json\|xml\|txt)`" |
| Fixture design (`design`) | Qualities a fixture should have: minimal, deterministic, synthetic, typed. | "Use the smallest synthetic fixture that crosses the required boundary" |
| Fixture maintenance (`maintenance`) | Updating, regenerating, versioning or not editing fixtures. | "All binary fixtures under `tests/fixtures/` MUST be tracked via git-lfs." |
| Cleanup (`cleanup`) | Removing what fixtures or tests create. | "Cleanup runs from `afterAll` even when an assertion fails" |
| Test isolation (`isolation`) | Keeping fixture state from leaking between tests. | "Every PG/MySQL container suite MUST own its fixture database." |
| Sensitive information (`sensitive`) | No real credentials, personal or customer data in fixtures. | "Never commit secrets, credentials, or raw sensitive payloads in logs or fixtures." |
| Other (`other`) | Mentions fixtures without saying how to use them, such as a pointer to another document. | "Test conventions, fixtures: HACKING.rst / TESTING.rst" |

## Changing the categories

The categories can still change while coding. To add, rename, split or merge
one:

1. Edit `rq5_category_codebook.yaml`. Each entry has a `code` (one word in
   snake_case, used in the sheet), a `name` (shown in the results) and a
   `definition` (written so that someone else could apply it without asking).
2. Go back over the rows already coded and update their `categories` to match.

A code used in the sheet but missing from the codebook stops the analysis with
an error, so the two cannot drift apart silently.

## Checking agreement with a second coder

To show that the categories are clear enough for someone else to apply:

1. Once at least 20 rows are coded, run
   `python -m collection.rq5_category_sample agreement-sheet`. It picks 20
   repositories at random from the coded rows (seed **20261013**) and writes
   `rq5_agreement_sheet.csv` with their snippets and an empty `categories`
   column.
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

The sample command refuses to overwrite a sheet that already has coding.

## What the results show

The "Categories" section of `rq5_coding.md` reports:

- the sample: size reached, checkpoint, confidence and margin of error;
- each category with its definition, number of repositories and share of the
  sample (a repository can have several categories, so the shares add up to
  more than 100%);
- how many categories a repository has (median, minimum, maximum);
- the languages of the sample next to those of all 556 repositories;
- the agreement with the second coder, once available.

## Things that break the sample

- Regenerating the sample after coding has started (the command refuses).
- Reordering, deleting or skipping rows.
- Changing decisions in `rq5_repository_coding_sheet.csv` after sampling: the
  sample no longer matches the repositories coded `yes`, and the analysis stops.
- Writing a code in `categories` before adding it to the codebook.
