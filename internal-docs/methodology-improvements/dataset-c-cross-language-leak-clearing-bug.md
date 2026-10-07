# Dataset C: a later language's first run cleared an earlier language's leaked rows

**Date**: 2026-10-07
**Context**: Thorough post-collection review of the real four-language Dataset C
extraction run (per-language CSVs vs. `db/c.db`) found 176 repositories / 6,706
fixture rows present in the database but missing from three of the four CSVs.

---

## 1. Problem

`find_test_files_with_language()` discovers test files of *any* of the four
collected languages inside a repository, independent of that repository's own
tagged language (`docs/architecture/collection.md`'s "Repository deduplication"
section already documents this as expected cross-language leakage, not a bug:
a java-tagged repo can legitimately contain javascript test files, and those
fixtures get written into `javascript_fixtures.csv`).

`collect_dataset_c_fixtures()` clears its own language's output CSV on a fresh
attempt:

```python
fresh_start = not checkpoint_path.exists()
```

This correctly protects a language's *own* run from clearing *another*
language's file (each language only ever unlinks its own CSV). But it does not
account for the reverse: an **earlier** language's run can leak real rows into a
**later** language's CSV before that later language has ever run itself — and
that later language's own first-ever invocation then destroys those rows,
purely because its own checkpoint happens to be empty. The destruction has
nothing to do with the later language's own candidates; it is pure collateral
damage against another language's already-correct output.

Reconstructed execution order from the leak pattern: java ran first (never
damaged — nothing had leaked into it yet), then javascript, then python, then
typescript, each one's first run wiping out whatever the previous ones had
already leaked into it.

One affected repository, `bridata/dbus` (tagged `java`), had **zero** fixtures
in its own tagged language — every one of its 20 fixtures came from leaked
javascript/python test files. For that repository, the leaked copy was its
*only* copy; there was no safe "own-language" fallback to recover metadata
from, which is why the repair (§3) reads directly off the database instead of
copying a sibling CSV row.

## 2. Fix

```python
sibling_checkpoint_exists = any(
    p.name != checkpoint_path.name
    for p in checkpoint_path.parent.glob("dataset_c_checkpoint_*.json")
)
fresh_start = not checkpoint_path.exists() and not sibling_checkpoint_exists
```

If any other language's checkpoint already exists, this attempt is not a
genuinely fresh one — some other language has already run and may have left
real, correct leaked rows in this language's CSV — so clearing is skipped.

This preserves the pre-existing, already-tested invariant that a language's own
first run must never clear a *different* language's file due to its own
candidates (`test_collect_dataset_c_fresh_start_does_not_clear_other_languages_csv`
in `tests/collection/test_dataset_c.py`, unchanged and still passing), while
fixing the new one.

**Known residual gap**, documented in the code comment at the fix site: a
non-first language's first run in a fresh attempt gets no automatic protection
against its *own* stale leftovers from an unrelated, older collection attempt
(e.g. re-running python after wiping only `db/c.db` and python's own checkpoint,
while java/javascript/typescript checkpoints from that old attempt still exist
on disk). A genuine from-scratch rebuild must manually clear
`datasets/c/fixtures/`, `db/c.db`, and all `dataset_c_checkpoint_*.json` first.

Tests: `test_a_later_languages_first_run_does_not_clear_an_earlier_runs_leaked_rows`
and `test_the_very_first_invocation_of_a_fresh_attempt_still_clears_its_own_stale_csv`
in `tests/collection/test_dataset_c_failure_handling.py`.

## 3. Data repair (applied retroactively)

The already-damaged CSVs (`datasets/c/fixtures/{javascript,python,typescript}_fixtures.csv`)
were repaired directly from `db/c.db`, which was never affected by this bug
(the CSV write and the DB write happen independently; only the CSV's `unlink()`
was destructive). Every field a CSV row needs is a direct column on the
`fixtures` table (`commit_sha`, `commit_date`, `agent_type`, `commit_kind`,
`is_complete_addition`, `repo_age_at_commit_years`, `num_mocks`), so the repair
reads `fixtures` joined to `test_files`/`repositories` for exactly the
`(repo, language)` pairs present in the database but absent from that
language's CSV, and appends the reconstructed rows.

791 (javascript) + 2,635 (python) + 3,280 (typescript) = 6,706 rows across 176
repositories appended. Verified after repair: database and CSV per-language
totals match exactly (188,026 rows each), and every one of this project's
`analyze_c_fixtures.py`-style integrity checks (schema, value ranges, cutoff
commit consistency, github_url correctness, pool membership) passes.

While investigating, also found and fixed 91 pre-existing exact-duplicate rows
(88 in javascript, 3 in typescript) unrelated to this bug — the `fixtures`
table's `UNIQUE(file_id, name, start_line, commit_sha)` constraint rules out a
real database-level duplicate, so these were a separate CSV-only double-append
affecting 7 repositories, removed by keeping one copy of each
`(repo_name, commit_sha, file_path, fixture_name, start_line)` key.

## 4. Status

Closed. Code fix in `collection/dataset_c.py`, tests passing, full suite green.
Data repair applied to the real `datasets/c/fixtures/*.csv`. One pre-existing,
unrelated, low-priority issue remains: a single java fixture with
`comment_density` slightly above 1.0 (a tree-sitter comment-counting edge
case), not fixed here.
