# Dataset C sample-down: switched from whole-repo to fixture-level sampling

**Status: Implemented, 2026-08-20.**

## 1. Request

Replace `sample-c-repos --match-dataset a`'s sampling algorithm: instead
of sampling whole Dataset C repos (stratified by language, targeting the
match dataset's per-language *repo-count* mix, landing only
*approximately* on its fixture count), sample individual fixtures
directly so each language hits the match dataset's real fixture count
*exactly*. Each language sampled fully independently: get the target
fixture count for that language from the match dataset, draw exactly
that many fixtures from Dataset C's pool for that language without
replacement, and if Dataset C has fewer than the target, take everything
available and log a warning rather than failing or silently
under-filling. Fixtures from the same repo can now land on opposite
sides of the sample -- explicitly intentional, maximizing the number of
distinct repos represented over keeping any one sampled repo "whole".

Dataset A was not to be touched, and no `research_questions/*.py` script
was to be modified.

## 2. What changed

- `collection/dataset_sampler.py`: `sample_repos_by_language()`,
  `RepoSamplingResult`, and `_allocate_quotas_with_shortfall_reallocation()`
  (the whole-repo, cross-language-shortfall-redistributing algorithm) are
  removed -- fully dead after this change, no other caller existed.
  Replaced with `sample_fixtures_by_language()` / `FixtureSamplingResult`:
  samples fixture rows directly, one language at a time, in sorted order
  for seed-reproducibility regardless of dict ordering. `StratifiedSampler`
  (used by the unrelated `sample --dataset a/b` command) is untouched.

- `collection/dataset_pipeline.py`: `sample_dataset_c_repos()`'s body is
  rewritten around the new algorithm (name kept, per the constraint
  below), reading `db/{match_dataset}.db`'s per-language fixture counts
  --grouped by each fixture's own detected language
  (`test_files.language`), not its repo's tagged language -- as the exact
  target, using a new `_fetch_fixture_language_counts()` (same grouping
  `dataset_findings.md`'s "Fixture Counts by Language" table uses, added
  the same day). `_fetch_dataset_c_repo_fixture_counts()`,
  `_fetch_repo_language_counts_with_fixtures()`, and `_build_sampled_db()`
  (all whole-repo-specific) are removed; replaced by
  `_fetch_dataset_c_fixtures_by_own_language()` (the sampling pool) and
  `_build_sampled_db_from_fixtures()` (a new DB builder that copies only
  the selected fixtures plus their FK dependencies, *recomputing* each
  touched repo's/test_file's aggregate counts from what was actually
  copied rather than carrying the source's counts over unchanged -- a
  repo/file can now be partially represented, which the old builder's
  "never partially included" assumption didn't need to handle).

- `internal-docs/RUN_COMMANDS.md`: the `sample-c-repos` section's
  description rewritten to match (not a `research_questions/` script, so
  in scope for this change).

## 3. Constraint: `research_questions/dataset_findings.py` was not touched

`_render_dataset_c_sampling_summary()` reads `output/sample_c_repos.json`
and subscripts several `distribution_check[language]` keys directly
(`original_ratio`, `target_ratio`, `sampled_ratio`,
`dataset_c_available_repo_count`, `sampled_repo_count`,
`sampled_fixture_count`, `dataset_c_available_fixture_count`) -- all
whole-repo-sampling concepts. Rather than touch that file,
`sample_dataset_c_repos()` still computes and writes every one of those
exact keys, now derived as descriptive statistics from the fixture-level
result (e.g. `sampled_repo_count` per language is "how many distinct
repos ended up with >=1 sampled fixture of this language", not a quota --
a repo is no longer a sampling unit). The report keeps rendering without
any change to the renderer; confirmed by regenerating
`dataset_findings.md` end-to-end against the real `db/a.db`/`db/c.db`.

**One known, accepted staleness**: that render function's hardcoded intro
sentence ("A language whose 'Repos sampled' hits its full available count
... the shortfall was redistributed to the other languages, not
discarded") describes the *old* algorithm's cross-language shortfall
redistribution, which no longer happens (each language is now sampled
fully independently -- see point 4 below). Since `dataset_findings.py` is
off-limits, this sentence is now inaccurate and was left as-is rather
than worked around from `dataset_pipeline.py`'s side.

## 4. Behavior differences from the old algorithm

- **Exact vs. approximate**: real run against `db/a.db`/`db/c.db`
  (2026-08-20): old algorithm sampled 47,582/47,208 target (repos are
  indivisible chunks, so it could only land close); new algorithm samples
  exactly 47,208/47,208, and every language hits its target exactly
  (java 1,398, javascript 4,174, python 11,035, typescript 30,601 --
  matching Dataset A's real per-language fixture counts exactly).
- **No cross-language shortfall redistribution**: the old algorithm, when
  one language couldn't reach its target share, redistributed the
  shortfall proportionally across the other languages
  (`_allocate_quotas_with_shortfall_reallocation()`). The new algorithm
  samples each language fully independently -- a shortfall in one
  language never changes another's target or sampled count.
- **Repos can appear partially**: a sampled repo's fixture count in
  `db/c_sampled.db` can now be smaller than its real count in `db/c.db`.
  `repositories.num_fixtures`/`num_test_files`/`num_mock_usages` and
  `test_files.num_fixtures`/`total_fixture_loc` reflect only what was
  actually sampled for that repo/file, not the source's real totals.
- **Do not compute repo-level statistics against `db/c_sampled.db`** --
  e.g. RQ2's setup/teardown pairing assumes a repo's fixtures are either
  fully present or fully absent; a fixture-level sample breaks that
  assumption by construction. This was never a live concern in practice
  since Dataset C sampling is deactivated for `research_questions/`
  scripts already (they read the full, unsampled `db/c.db` -- see
  `_shared.py::require_db_or_none()`'s docstring), but it's worth stating
  explicitly for any future use of `db/c_sampled.db`.

## 5. Tests

`tests/test_dataset_sampler.py`: `TestSampleReposByLanguage`,
`TestAllocateQuotasWithShortfallReallocation`,
`TestSampleReposByLanguageWithTargetProportions` (whole-repo-specific)
replaced with `TestSampleFixturesByLanguage` -- reproducibility,
exact-count matching (not "close to"), same-repo fixtures landing on
opposite sides of the sample, shortfall takes everything available and
flags it without affecting other languages, absent-language handling in
both directions, empty-population error.

`tests/collection/test_sample_dataset_c_repos.py`: fully rewritten
around the new fetch/build functions, including new leakage-specific
tests (a single repo with test files in two languages, proving both the
fixture pool and the sampling target grouping follow each fixture's own
language, not its repo's tag) and a partial-repo-copy test (fewer
fixtures copied than the source repo has, with recomputed aggregate
counts).

Full suite: 1,676 passed after this change.
