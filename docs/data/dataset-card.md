# Dataset card: FixtureDB

## Summary

FixtureDB contains test fixtures from open-source repositories in four
languages: Python, Java, JavaScript and TypeScript. A fixture is code that sets up
or tears down the state of a test.

The dataset has two parts:

| Part | Written by | Source | Time window |
|------|-----------|--------|-------------|
| **Dataset A** | Coding agents | Repositories with an agent configuration file and at least one agent commit | Commits from 2025-01-01 |
| **Dataset C** | Humans | Repositories created 2016 to 2020 | Snapshot at 2020-12-31 |

| Property | Value |
|----------|-------|
| Languages | Python, Java, JavaScript, TypeScript |
| Unit | One fixture |
| Code licence | MIT |
| Data licence | CC BY 4.0 |

## What is in the release

Each dataset has one SQLite database with four tables: `repositories`,
`test_files`, `fixtures` and `mock_usages`. The schema is described in
[Database schema](../architecture/database-schema.md).

The release also includes:

- **Export bundles** (`export/a.zip`, `export/c.zip`). Each bundle contains CSV
  files for the four tables, the manual-review sample, a README and a schema
  file. See [Exports and storage](exports.md).
- **Stage CSVs** (`datasets/a/`, `datasets/c/`). These are the intermediate
  outputs of each collection step. They are the easiest files to review.
- **Collection summaries** (`datasets/a/summary.yaml`, `datasets/c/summary.yaml`).
  These give repository and fixture counts for each dataset.

## Variables used in the paper

Metrics are computed on test files only.

| Variable | Meaning |
|----------|---------|
| `fixture_type` | The matched pattern, for example `pytest_decorator` or `junit5_before_each` |
| `fixture_role` | `setup`, `teardown`, `setup_and_teardown` or `other` |
| `loc` | Non-blank lines in the fixture body |
| `cyclomatic_complexity` | Decision points in the fixture body |
| `comment_density` | Single-line comments divided by `loc` |
| `num_mocks` | Number of mock calls in the fixture body |
| `mock_usages.category` | Test double type: `dummy`, `stub`, `spy`, `mock` or `fake` |

The schema has other columns. The paper does not use them, so this page does not
describe them. See the database schema page.

## Control variables

Each dataset has its own reference date. A repository's control values are taken
at that date.

| Variable | How it is computed |
|----------|--------------------|
| `language` | The repository's language tag |
| `domain` | Keyword match on topics and description: `web`, `systems`, `ml`, `security`, `database`, `devops`, or `other` |
| `repo_age_years` | Years from repository creation to the reference date |

Domain labels are rough. They depend on the quality of the topics and descriptions.

## How the data was collected

1. **Repository list.** Candidate repositories come from SEART (`github-search-raw/`).
   The search keeps repositories with at least 500 stars, 100 commits, 5,000 lines
   of code, and no fork relationship.
2. **Dataset A repositories.** A repository is kept if its tree has an agent
   configuration file from the catalog in `collection/heuristics/agent-mining/`.
3. **Dataset A commits.** Commits since 2025-01-01 are classified. A commit is an
   agent commit if its trailers or author name match the agent catalog. Bot accounts
   are excluded first.
4. **Dataset C repositories.** Repositories created 2016 to 2020 are kept. Each is
   checked out at its own commit on or before 2020-12-31.
5. **Fixtures.** The same parser and pattern list are used for both datasets. See
   [Fixture detection](../architecture/detection.md).
6. **Purity filter (Dataset A only).** A commit is kept only if it deletes no lines
   in test files. A fixture is kept only if all its lines are new.

Duplicate repositories are removed where the collection can detect them. The
rules and what they miss are in the [limitations page](../reference/limitations.md).

## Known problems

- Agent detection favours precision. Agent commits without a trace are counted as
  human.
- Fixture detection covers the common patterns only. Custom fixtures are missed.
- Repositories have at least 500 stars. Results may not apply to smaller projects.
- Some fixtures are in a different language from their repository's tag. In
  Dataset A this is 8.04% of fixtures, measured on 2026-07-31.

The full list with mitigations is in the [limitations page](../reference/limitations.md).

## Access

```sql
-- Dataset A
SELECT COUNT(*) FROM fixtures;   -- in db/a.db
-- Dataset C
SELECT COUNT(*) FROM fixtures;   -- in db/c.db
```

## Citation

Cite the paper once it is published. Details will be added on acceptance.

## Versions

There is no formal versioning yet. Each collection run is dated in its output
file names. Check the repository's issue tracker for known problems and corrections.
