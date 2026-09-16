# setUpModule/tearDownModule matched regardless of class nesting

**Status: Fixed and corrected in `db/c.db`, 2026-09-15.**

## 1. Found during manual validation of the unittest name-based heuristic

The Cochran-sized manual validation sample for Python's unittest
name-based lifecycle heuristic (`validation-samples/unittest-heuristic/`)
flagged 2 of its 4 sampled `setUpModule`/`tearDownModule` rows as false
positives: both were methods nested inside `class Module(object):` in
CPython's own `Lib/unittest/test/test_setups.py` -- a file that tests
unittest's *own* setUpModule/tearDownModule mechanism by defining local
classes with same-named methods, never invoked by unittest as real hooks.

## 2. Root cause

`detector_python.py`'s `_detect_python()` matched every name in
`UNITTEST_SETUP_NAMES` (`setUp`/`tearDown`/`setUpClass`/`tearDownClass`/
`setUpModule`/`tearDownModule`) by name alone, with no nesting check.
That's correct for the first four (real class methods), but
`setUpModule`/`tearDownModule` are only ever meaningful as plain
module-level functions -- unittest never calls a same-named method
nested inside a class.

## 3. Fix

`detector_python.py` gained `_is_nested_in_class()`, walking the
tree-sitter parent chain from a candidate `setUpModule`/`tearDownModule`
node; a class-definition ancestor now excludes the match. Regression
tests added directly (`tests/collection/test_extractor_unit/test_python_fixtures.py::TestUnittestModuleLevelHooks`)
and via the catalog-coverage test's per-`per_module`-scope code
generation (`tests/collection/test_fixture_definitions_catalog_coverage.py`).

## 4. Scale investigation and correction

A full scoping pass (not just the 380-row sample) re-fetched and
re-parsed all 446 `setUpModule`/`tearDownModule` candidates across
`db/a.db` + `db/c.db` to check real nesting:

| | Dataset A | Dataset C |
|---|---|---|
| candidates | 16 | 430 |
| nested-in-class (confirmed bug) | 0 | 158 |
| % of dataset's Python fixtures | 0% | 0.36% |

Combined: 158 / 64,536 Python fixtures = 0.245% of the corpus; 0.539% of
the unittest-heuristic population specifically. All 158 came from exactly
7 repositories, all vendoring the same CPython `Lib/unittest/test/
{test_setups,test_runner,test_result,test_suite}.py` files: `python/cpython`
itself, `jython/jython`, `ironlanguages/ironpython2`, `oracle/graalpython`,
`google/google-ctf`, `oils-for-unix/oils`, `cedricguillemet/imogen`. Split
evenly 79 `setup` / 79 `teardown` by `fixture_type_kind`.

Sanity-checked the fix against one of these files directly (re-fetched,
re-parsed with the fixed detector): 0 matches, down from 14 stored rows
for that file pre-fix.

**Correction applied:** rather than a full recollection (considered and
rejected -- see below), the 158 confirmed-bug rows were deleted directly
from `db/c.db` by exact fixture id (`DELETE FROM fixtures WHERE id IN
(...)`, verified 0 `mock_usages` references first). `db/a.db` needed no
change (0 affected rows). A pre-deletion backup of `db/c.db` was taken
before the delete. Post-deletion, all 288 remaining setUpModule/
tearDownModule fixtures in both databases were re-verified as genuine
module-level hooks (0 remaining nested cases).

### Why a surgical delete instead of recollection

Considered re-cloning and re-extracting just the 7 affected repos, but:
content is pinned by `commit_sha` (deterministic, no re-discovery
uncertainty), `collect_dataset_c_fixtures()`'s stratified-sampling step
is inactive for the real Dataset C pipeline (no `commit_kind='agent'`
rows or `fixtures-from-agents/` CSVs to derive targets from, so it always
takes every extracted candidate unfiltered) -- so a scoped recollection
of exactly these 7 repos would be mechanically safe from a sampling
standpoint, but would also silently apply every *other* detector fix
shipped since these repos were first collected (e.g. the mock-detection
comment-exclusion fix, `79e4ec7`), making these 7 repos detector-fresher
than the rest of Dataset C -- a new, asymmetric inconsistency that
doesn't exist today. Since the setUpModule/tearDownModule fix only ever
*removes* false-positive rows (never reclassifies or adds any), a
targeted delete of the exact, fully-enumerated set of affected rows
produces an identical result to a scoped recollection for this bug
specifically, without that side effect and without any cloning.

The unittest-heuristic validation sample CSV was updated separately
(2 of its 380 rows -- the ones that surfaced this bug -- removed rather
than kept as stale FPs against fixed code); see
`validation-samples/README_detection_validation.md`.
