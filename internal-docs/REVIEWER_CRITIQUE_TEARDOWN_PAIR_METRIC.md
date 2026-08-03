# Reviewer Critique: `has_teardown_pair`

Academic-reviewer-style critique of the `has_teardown_pair` metric (RQ2 — Setup and
Teardown Characterization), produced by reading the actual implementation
(`collection/detector_shared.py::_calculate_teardown_pairs()`, the `teardown_detection`
table in `collection/heuristics/feature_extraction_patterns.yaml`, and its call site in
`collection/detector.py`) rather than the docs alone. See
`docs/architecture/metrics-reference.md` (`### has_teardown_pair`) and
`docs/reference/limitations.md` (`has_teardown_pair` row, "Validation Status") for the
published disclosures this critique builds on top of. Companion to
`REVIEWER_CRITIQUE_DETECTION_METHODOLOGY.md` (agent/fixture detection generally) —
this one is scoped to the teardown-pairing metric specifically.

## Status

| # | Gap | Status |
|---|-----|--------|
| 1 | Type-based pairing has no block/class locality — can false-pair hooks across independent `describe()` blocks or `@Nested` classes in the same file | **Resolved** — `FixtureResult.container_id` (the AST byte-offset of the nearest enclosing `describe()`/`class_declaration` node) added to `collection/detector_shared.py`, populated by `detector_javascript.py::_enclosing_describe_id()` and `detector_java.py::_enclosing_class_id()`, and required to match in `_calculate_teardown_pairs`'s type-based branch. Internal pairing signal only — not written to `fixtures.csv`/DB. Covered by 5 new tests in `tests/collection/test_extractor_metadata/test_new_metrics.py::TestTeardownDetection` (2 JS, 3 Java, including the `@Nested`-class repro). |
| 2 | Metric measures presence of cleanup, not correctness | Disclosed (`docs/architecture/metrics-reference.md`, "Known limitations"). Defensible scope choice; flag explicitly if the paper's framing ever drifts toward "agents provide teardown as reliably as humans." |
| 3 | No inter-rater reliability / manual validation specific to this metric | Disclosed (`docs/reference/limitations.md`, "Validation Status" — no Cohen's kappa available generally). RQ2's per-type `has_teardown_pair` rate additionally is "descriptive only, not run through a significance test" (`collection/research_questions/rq2.py:40-46`) — only the setup-to-teardown *ratio* and *kind distribution* get Mann-Whitney U / chi-square treatment. |
| 4 | Two mechanisms (`always_has_teardown_fixture_types`) set the flag with zero source-level check, by construction | **Resolved** — not a bug (the language semantics genuinely guarantee it: JUnit `@Rule`/`@ClassRule`, Vitest `aroundEach`/`aroundAll`), but the "these rows carry no agent-vs-human signal" caveat is now written down: `docs/architecture/metrics-reference.md`'s `has_teardown_pair` section, "Reporting caveat." |

## What already holds up

- Five detection mechanisms (`always_has_teardown`, `yield_based`, `name_based`,
  `self_registered_cleanup`, `type_based`), each with a concrete, real-pattern
  motivation on record (`self_registered_cleanup` exists specifically because a modern
  `setUp()` using only `addCleanup()` would otherwise silently read as 0).
- RQ2 reuses the *exact same* `TYPE_BASED_TEARDOWN_PAIRS`/`NAME_BASED_TEARDOWN_PAIRS`
  tables that `has_teardown_pair` itself is computed from
  (`collection/research_questions/rq2.py:95-105`), rather than a second, independently
  drifting definition of "setup" vs. "teardown."
- Types with no clean setup/teardown split (`testng_data_provider`, always-true types)
  are bucketed as "other" in RQ2's kind classification instead of forced into a fake
  split.
- Pairing is genuinely file-scoped, not corpus-scoped: `_calculate_teardown_pairs` is
  called inside `extract_fixtures_from_file` (`collection/detector.py:235`), once per
  file, on that file's own fixture list only — no risk of matching setup in one repo
  against teardown in an unrelated one.
- Only the setup-side fixture is flagged (matches the column's documented semantics);
  the teardown fixture itself is never separately flagged, so there's no double-count
  risk in aggregate rates.

## Resolved item — #1: type-based pairing has no block/class locality

Fixed — see "Fix (implemented)" below. Kept the original gap writeup as-is (describes
the pre-fix state) since it's what a reviewer independently rediscovering this would
find by reading the code as it stood before the fix.

**The gap (pre-fix).** `FixtureResult.scope` (`collection/detector_shared.py:108`) is a flat enum
(`per_test`/`per_class`/`per_module`/`global`) assigned purely from a static lookup
table keyed by hook name — `JS_FIXTURE_CALLS` in `detector_javascript.py`,
`JUNIT_FIXTURE_ANNOTATIONS`/`JUNIT_TESTNG_AMBIGUOUS` in `detector_java.py`. It does not
encode *which* enclosing `describe()` block or `@Nested` class a hook lives in. The
type-based pairing check —

```python
# detector_shared.py:763-768
elif fixture.fixture_type in TYPE_BASED_TEARDOWN_PAIRS:
    expected_type = TYPE_BASED_TEARDOWN_PAIRS[fixture.fixture_type]
    has_teardown = any(
        other.fixture_type == expected_type and other.scope == fixture.scope
        for other in fixtures
    )
```

— will pair *any* same-scope hook of the matching type anywhere in the file. Concrete
failure case (JS/TS, `before_each`/`after_each` — the generic type-based pair used for
Jest/Mocha/Jasmine-style `beforeEach`/`afterEach`):

```js
describe('UserService', () => {
  beforeEach(() => setupUser());   // <-- flagged has_teardown_pair=1
  test(...);
});

describe('OrderService', () => {
  afterEach(() => cleanupOrder()); // <-- unrelated, but satisfies the check above
  test(...);
});
```

`UserService`'s `beforeEach` has no teardown of its own but reads as
`has_teardown_pair=1`, satisfied purely by an unrelated `afterEach` elsewhere in the
same file. The same gap applies to JUnit5 `@Nested` inner classes (`detector_java.py`
does not track class boundaries either — `scope` there is likewise assigned straight
from the annotation lookup table with no class-node identity attached).

This is the overcounting mirror image of the limitation `metrics-reference.md` already
discloses ("pairing is intra-file only" — which is about *undercounting*, missing
legitimate cross-file pairs, e.g. inherited Java base-class teardown). The
within-file, cross-block overcounting direction isn't written down anywhere yet.
Magnitude in the actual corpus is unmeasured — this was found by code reading, not by
querying `db/{a,b,c}.db` for suspiciously high type-based pairing rates, which would be
the natural next step before deciding how urgent this is.

### Fix (implemented)

Implemented as designed below (no deviations). Verified against the exact
`UserService`/`OrderService` example above: pre-fix, `UserService`'s `beforeEach` read
`has_teardown_pair=1`; post-fix, `0` (checked directly by running the real
`extract_fixtures()` against both the pre-fix and post-fix code via `git stash`).

**Root fix — track enclosing-container identity, require it to match.**

1. Add a field to `FixtureResult` (`detector_shared.py:102-122`), e.g.
   `container_id: Optional[str] = None` — a stable identifier for the innermost
   enclosing test-suite container. It doesn't need semantic meaning, just needs to
   distinguish blocks: the enclosing `describe(...)` call node's start byte/line
   (JS/TS), or the enclosing class node's start byte/line (Java, so both top-level
   classes and `@Nested` inner classes get distinct ids). `None`/a file-level sentinel
   when a hook has no enclosing block (e.g. a top-level Jest `beforeEach` with no
   wrapping `describe`).
2. Populate it during AST traversal in `detector_javascript.py` (walk up from the hook
   call node to the nearest enclosing `describe(...)` call) and `detector_java.py`
   (walk up to the nearest enclosing class declaration node). **Python is unaffected**
   — `pytest_class_method`/`unittest_setup` pairing is name-based, not type-based
   (`type_based_pairs` in the YAML has no Python entries), so this fix only touches the
   JS and Java detectors.
3. Update the type-based branch in `_calculate_teardown_pairs` to additionally require
   `other.container_id == fixture.container_id`.
4. Treat `container_id` as transient/internal to the pairing computation, not part of
   the exported schema — verify the CSV/DB row-serialization path doesn't dump
   `FixtureResult` fields wholesale (if it does, explicitly exclude this one; no need
   to add a DB column or bump the schema version for a field nothing downstream
   consumes).
5. Regression tests: a synthetic two-`describe()`-block JS file (one block with only
   `beforeEach`, the other with only `afterEach`, same scope) asserting **no**
   false pairing; a same-file, same-block case asserting pairing still works; a JUnit5
   `@Nested`-class analog of both.

(The cheaper line-proximity fallback originally sketched here wasn't needed — the root
fix, above, was implemented directly.)

**Corpus impact:** if Datasets A/B were already extracted with the buggy detector
before this fix landed, the historical `has_teardown_pair` rate for
`before_each`/`after_each`/`junit5_*` types in `db/{a,b}.db` may have been inflated by
an unknown amount. Not investigated separately — the user is redoing fixture
extraction for all datasets soon regardless, which picks up this fix automatically in
the next version of the corpus.
