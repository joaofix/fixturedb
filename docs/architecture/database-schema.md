# Database schema

There is one SQLite database per dataset: `db/a.db` and `db/c.db`. Both use the
same schema, defined in `collection/db_schema.py`. Both run in WAL mode.

Each row in `fixtures` is one fixture. Each row in `mock_usages` is one mock
call inside a fixture.

## repositories

| Column | Type | Meaning |
|--------|------|---------|
| `id` | INTEGER | Primary key |
| `github_id` | INTEGER | GitHub numeric id |
| `full_name` | TEXT | `owner/name` |
| `language` | TEXT | Repository language tag |
| `stars`, `forks` | INTEGER | Counts at collection time |
| `description`, `topics` | TEXT | From GitHub. `topics` is a JSON list. |
| `created_at`, `pushed_at` | TEXT | ISO 8601 dates |
| `clone_url`, `pinned_commit` | TEXT | Clone address and the commit that was read |
| `status`, `error_message`, `skip_reason` | TEXT | Collection state |
| `num_test_files`, `num_fixtures`, `num_mock_usages` | INTEGER | Counts |
| `num_contributors` | INTEGER | From GitHub |
| `domain` | TEXT | `web`, `systems`, `ml`, `security`, `database`, `devops` or `other` |
| `repo_age_years` | REAL | Age at the dataset's reference date. NULL if created after it. |
| `repo_age_at_collection_years` | REAL | Age when collection ran |
| `collected_at` | TEXT | Insert time |

## test_files

| Column | Type | Meaning |
|--------|------|---------|
| `id` | INTEGER | Primary key |
| `repo_id` | INTEGER | Links to `repositories.id` |
| `relative_path` | TEXT | Path in the repository |
| `language` | TEXT | Language of the file |
| `file_loc` | INTEGER | Non-blank lines |
| `num_test_funcs`, `num_fixtures` | INTEGER | Counts in the file |
| `total_fixture_loc` | INTEGER | Sum of fixture lines in the file |

## fixtures

| Column | Type | Meaning |
|--------|------|---------|
| `id`, `file_id`, `repo_id` | INTEGER | Keys |
| `name` | TEXT | Fixture name |
| `fixture_type` | TEXT | Matched pattern, for example `pytest_decorator` |
| `start_line`, `end_line` | INTEGER | 1-based location |
| `loc` | INTEGER | Non-blank lines |
| `cyclomatic_complexity` | INTEGER | Lizard |
| `num_parameters` | INTEGER | Lizard |
| `num_comment_lines`, `comment_density` | INTEGER, REAL | Single-line comments, and that count divided by `loc` |
| `fixture_role` | TEXT | `setup`, `teardown`, `setup_and_teardown` or `other` |
| `raw_source` | TEXT | Exact fixture text |
| `num_mocks` | INTEGER | Number of mock calls in the fixture |
| `commit_sha` | TEXT | Dataset A: the commit that added the fixture. Dataset C: the repository's cutoff commit. |
| `commit_date` | TEXT | Date of `commit_sha` |
| `commit_kind` | TEXT | `agent` in `db/a.db`. Not set in `db/c.db`. |
| `agent_type` | TEXT | Agent family, if the commit is agent work |
| `is_complete_addition` | INTEGER | 1 if the fixture was only added in its commit |
| `repo_age_at_commit_years` | REAL | Repository age at `commit_date` |

## mock_usages

| Column | Type | Meaning |
|--------|------|---------|
| `id`, `fixture_id`, `repo_id` | INTEGER | Keys |
| `framework` | TEXT | Mock library, for example `unittest_mock` or `mockito` |
| `category` | TEXT | `dummy`, `stub`, `spy`, `mock` or `fake` |
| `target_identifier` | TEXT | The mocked name, if it can be read |
| `num_interactions_configured` | INTEGER | Mock setup calls |
| `raw_snippet` | TEXT | Exact mock text |

## Columns the paper does not use

These columns are still stored. The paper does not analyse them, and the code
does not report them:

- `fixtures.scope`, `fixtures.framework`
- `fixtures.max_nesting_depth`, `fixtures.num_objects_instantiated`,
  `fixtures.num_external_calls`
- `fixtures.has_teardown_pair`, `fixtures.commit_type`

They will be removed when the schema is changed after the collection run.

## Queries

Analysis examples are on the [analysis page](../usage/analysis.md).

From the shell:

```bash
sqlite3 db/a.db "SELECT COUNT(*) FROM fixtures;"
sqlite3 db/a.db "SELECT agent_type, COUNT(*) FROM fixtures WHERE agent_type IS NOT NULL GROUP BY agent_type;"
```

The databases are written by the pipeline. Do not edit them by hand.
