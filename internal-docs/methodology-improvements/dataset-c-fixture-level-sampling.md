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
- **Repo-level statistics computed against `db/c_sampled.db` carry
  per-repo sampling noise** -- e.g. RQ2's setup/teardown proportions
  assume a repo's fixtures are either fully present or fully absent; a
  fixture-level sample breaks that assumption by construction. At the
  time this was written, this was not a live concern -- see
  section 6 below for why it now is, and for the update.

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

## 6. `research_questions/` switched back to reading `db/c_sampled.db` (2026-08-20)

**Status: Implemented, 2026-08-20 (same day as section 1-5 above).**

### Request

Point every `research_questions/*.py` script (not just the sampling
machinery itself) at Dataset C's fixture-level sample-down instead of the
full, ~3.3x-larger `db/c.db` -- global, including `dataset_findings.py`'s
descriptive/data-quality sections (repo-purity/adoption-intensity report,
the "Fixture Counts by Language" table, and the JUnit3-fallback/JS-hook-
complexity/mocha-bare-hook/aliased-mock-import/mock-category-fallback side
notes), not scoped to just the A-vs-C statistical comparison scripts. This
reverses the "deactivated" decision `require_db_or_none()`'s docstring
used to describe (see git history for that version) -- the team's
reasoning this time: with the sampling algorithm now exact-per-language
(section 1-4 above), there's no longer an approximation-quality objection
to routing everything through it.

### What changed

- `collection/research_questions/_shared.py::require_db_or_none()`:
  dataset `"c"` now resolves to `db_root / "c_sampled.db"` instead of
  `db_path("c", root=db_root)` (`db_root / "c.db"`). Still returns `None`
  with a logged warning if that file doesn't exist yet -- same "skip,
  don't error" convention as every other dataset, so a Dataset C
  re-collection without a matching `sample-c-repos` re-run degrades
  gracefully rather than silently reading stale/full data.
- `collection/research_questions/language_contamination.py::check_dataset()`:
  dataset `"c"` now reads `datasets_root / "c" / "fixtures-sampled"`
  instead of `paths.stage_dir("c", "fixtures", root=datasets_root)`
  (`datasets/c/fixtures/`) -- matches the DB-side redirect above.
- Every docstring/comment across `dataset_pipeline.py`,
  `dataset_findings.py`, `RUN_COMMANDS.md`, and the affected test files
  that described dataset C sampling as "deactivated" was updated to
  describe the new reality (`sample-c-repos` is now a required step
  before regenerating RQ reports, not an inert, never-read side capability).

### Known limitation accepted, not worked around

Every comparison in `rq1.py`/`rq2.py`/`rq3.py`/`balance.py` works by
aggregating one proportion/mean per repo (the repo-de-clustering
methodology used throughout this package, to avoid treating a repo's
correlated fixtures as independent observations). `db/c_sampled.db` can
now represent a Dataset C repo only partially (section 4's "Repos can
appear partially" point) -- average fixtures/repo dropped from ~63.9 in
the full corpus to ~20.3 in the sample (2026-08-20 collection: 191,883
fixtures / 3,005 repos vs. 47,208 fixtures / 2,325 repos touched). So a
Dataset C repo's per-repo proportion/mean computed against the sample can
now differ from its true value in the full corpus.

This was evaluated and accepted as a **known limitation, not a blocker**:
`sample_fixtures_by_language()` samples uniformly at random per language,
with no consideration of `fixture_type`, repo, or any other fixture
attribute -- so a repo's sampled subset is a fair (if smaller) random
draw from its own true fixture set, not a systematically skewed one. This
adds *estimation noise* to a repo's per-repo statistic (worse for repos
that end up with very few sampled fixtures of a given language), not a
*directional bias* -- it should not manufacture a false A-vs-C
difference, though it can reduce statistical power to detect a real one
relative to comparing against the full corpus. Documented here, in
`_shared.py::require_db_or_none()`'s docstring, and in
`dataset_pipeline.py::sample_dataset_c_repos()`'s docstring rather than
worked around, since there is no way to route around it without either
reverting to whole-repo sampling (rejected in section 1-4 above) or
scoping the redirect down to non-repo-level sections only (considered and
explicitly rejected for this change).

### Tests

`tests/collection/test_research_questions_shared.py::TestRequireDbOrNone`,
`tests/collection/test_language_contamination.py::TestCheckDataset`,
and every `_make_db*`-style helper in `test_rq1.py`/`test_rq2.py`/
`test_rq3.py`/`test_balance.py`/`test_dataset_findings.py` that writes
synthetic dataset-C data updated to write to `c_sampled.db`/
`fixtures-sampled/` (mirroring the new redirect) instead of `c.db`/
`fixtures/`, with the corresponding "must NOT read the other path" cases
inverted to match.
