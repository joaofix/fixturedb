# RQ5 decision coding: is this guidance about test fixtures?

The keyword search finds every line in a repository's agent guidance files
that mentions a fixture term such as `fixture`, `conftest`, `beforeEach` or `test setup`. Many of those lines are not about test fixtures at all. This step decides, for each repository, whether its
guidance really is about test fixtures.

The decision goes in the `decision` column of `rq5_repository_coding_sheet.csv`.
The matched lines are read in `rq5_snippets.md` (section N is row N of the
sheet). The repositories coded `yes` are later categorized; see
`CATEGORY_CODING.md`.

## The two answers

| Decision | Meaning |
|---|---|
| `yes` | At least one match is about test fixtures. |
| `no` | No match is about test fixtures, or none clearly is. |

One decision per repository, over all of its matches in all of its guidance
files. **One good match is enough for `yes`.**

## How to read a match

- **Use only what you see:** the matched line and the lines around it. Do not
  open other files of the repository and do not rely on knowing the project.
  Read it as an average developer going through many unfamiliar projects would.
- **Be lenient.** The text does not have to say "test fixture". If the nearby
  words make the test context clear, that is enough. "Use synthetic fixtures
  and redact prompts" under a data-safety rule is clearly about fixtures that
  simulate data in tests: `yes`.
- **Describing counts as guidance.** In a file written for an agent, a statement
  of how things are done works as an instruction. "Tests use pytest fixtures
  defined in `conftest.py`" is `yes`, even though it gives no order.
- **Unhelpful still counts.** A match can be about test fixtures and still tell
  the agent little (a path pattern in a table, a one-line tip). It is `yes`; how
  useful it is is a separate question.

## What counts as a test fixture

### Fixture code and setup/teardown hooks: `yes`

Pytest fixtures, `conftest.py` fixtures, and setup/teardown hooks
(`beforeEach`, `afterEach`, `beforeAll`, `afterAll`, `@BeforeEach`,
`@AfterEach`, `setUp`/`tearDown`) in a test context are fixtures, **whatever
they do inside**: a hook that only resets mocks is still a fixture.

> "Reset store state in `beforeEach` via `store.setState({...})`" → `yes`

Guidance *against* a hook is still guidance about fixtures:

> "Set up and tear down inside the test case rather than `beforeEach`" → `yes`

### Fixture files and test data: `yes`

Files or data that tests load (a `tests/fixtures/` folder, recorded responses,
golden files a test compares against, small projects an end-to-end test runs
on) are fixtures. Saying where they live is enough.

> "Fixtures (sample PDF, docx, xlsx, archive, etc.) live in `test/fixtures/`.
> Reuse them rather than generating new files on the fly." → `yes`

A guidance file that is itself part of a test fixture counts too, when its
body speaks to the reader about the fixture. When "fixture" appears only in
the file's title, the file is test data, not guidance:

> "Guidance for coding agents working in this fixture project." (in
> `…/fixtures/clean/CLAUDE.md`) → `yes`
>
> "# Git streaming fixture agent" (in `tests/runner-e2e/fixtures/…/AGENTS.md`) → `no`

### Pointers and "don't" rules: `yes`

A pointer to a document that covers test fixtures, and a rule *not* to do
something with fixtures, are both fixture guidance.

> "Test conventions, fixtures: HACKING.rst / TESTING.rst" → `yes`
>
> "…do not include test fixtures unless explicitly requested" → `yes`

## What does not count

### Mocks on their own: `no`

A mock is not a fixture. A mock mentioned without any fixture around it is
`no`. A mock *inside* a fixture or hook is fine: the hook makes it `yes`.

> A `MockFastMCP` class kept in `tests/conftest.py`, with no fixture mentioned → `no`
>
> "Mock `NetworkManager.getClient` in `beforeAll` to return mock client" → `yes` (the hook)

### Test configuration and generic setup: `no`

A `conftest.py` that only configures the test run (collection rules, warning
filters, `sys.path`, markers), a setup file or folder with no fixture in it,
and the configuration needed to run tests (runner settings, environment
variables, an emulator) are not fixtures.

> "`tests/conftest.py` puts `src/` on the path" → `no`
>
> "`src/setupTests.ts`", "e2e/ — End-to-end test setup" → `no`

A shared setup file *is* a fixture when the text says what it sets up for the
tests, such as mocks for every test or a temporary home directory:

> "Shared test mocks belong in `src/test-setup.ts` and are wired through
> `test.setupFiles`" → `yes`

### Fixtures that are not for tests: `no`

The word "fixture" also names demo inputs, screenshots, seed data for running
the app, benchmark inputs, prompt examples, and sample data in documentation.
None of these are test fixtures.

> "`bun run seed:dev` — manual reseed path; … seeds local fixtures plus the
> public corpus" → `no`
>
> "`benchmarks/`: benchmark runners and fixtures" → `no`

### The same word with another meaning: `no`

> Vue Router's `beforeEach` navigation guard → `no`
>
> A tool named `fixture_search` → `no`

### Guidance that is not the repository's own: `no`

- **Vendored code.** A guidance file inside a copied third-party repository
  (for example under `.repos/<other-project>/`) is not this repository's
  guidance, however clear it is.
- **Example prompts.** A user guide showing a sample command such as
  `jarvis ask --agent claude_code "Refactor the tests to use pytest fixtures"`
  is an example, not a
  rule for the repository.

A **skill file** in the repository (for example under `.agents/skills/`) does
count: the agent reads it when it looks for guidance, even if it only holds
examples.

## When the text does not settle it: `no`

If a match could be about test fixtures but nothing in the text makes it
clear, the answer is `no`: an unclear case is never counted as fixture
guidance. Typical cases:

- **The test context is only implied by a vague phrase.** "`pnpm fixtures:check`
  — use this rather than ad-hoc emit-and-diff", or "the geometry is the fixture".
- **"Fixture" appears in passing**, with a hint of tests nearby but nothing
  that ties it to them ("Wave-2 with full fixtures + tests" in a status list).

Check the rules above first: golden or conformance cases that implementations
must pass, and fixture files under `tests/fixtures/`, are `yes` even when the
word "test" is missing.

## Quick reference

| The match says… | Decision |
|---|---|
| A pytest/`conftest.py` fixture, or a setup/teardown hook in tests | `yes` |
| Where test fixture files live, or what test data to use | `yes` |
| A pointer to a doc about test fixtures, or a "don't" rule about them | `yes` |
| A guidance file that is itself a test fixture and says so, or a skill file in the repo | `yes` |
| A fixture file where "fixture" appears only in its title | `no` |
| A mock with no fixture or hook around it | `no` |
| A shared setup file described by what it sets up (mocks, temp home) | `yes` |
| Test configuration, a setup file only named, runner settings | `no` |
| Demo, seed, benchmark, screenshot or documentation "fixtures" | `no` |
| The word with another meaning (router guard, tool name) | `no` |
| Vendored third-party guidance, or an example prompt | `no` |
| Might be a test fixture, but the text does not settle it | `no` |
