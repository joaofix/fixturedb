# Manual review methodology: human-fixtures-dataset-b

Full 1,513-row sample (382 Python / 377 Java / 371 JavaScript / 383 TypeScript,
Cochran 95%/5%, seed=42), reviewed 2026-07-16.

## Method

1. **Full-population structural check** (all 1,513 rows). An independent
   verifier -- not a call into the production detector, a fresh
   reimplementation from `collection/heuristics/fixture_definitions.yaml`'s
   own documented ground truth -- confirmed each row's claimed
   `fixture_type` had its required marker (decorator/annotation/hook-call
   text, or method name) present in `raw_source`, plus basic structural
   sanity (non-empty, balanced brackets). 1,498 rows passed; 15 were flagged.

   One systematic false-flag surfaced and was corrected before counting:
   Python's `pytest_decorator` type scopes `raw_source` to the function node
   only (by design -- see `docs/architecture/metrics-reference.md`), so the
   `@pytest.fixture` decorator itself is never in `raw_source`. Confirmed via
   live GitHub source for 3 sampled rows before adjusting the checker to a
   plausibility check (real `def`, not test-shaped) for this type instead.

2. **Live GitHub verification of all 15 flagged rows.** Fetched each row's
   actual source file at the commit URL and read the real surrounding code
   (not just the CSV's `raw_source` field). Found:
   - 10 true positives: `test_`-prefixed function names (confusing but legal
     pytest convention) genuinely decorated `@pytest.fixture`.
   - 5 confirmed false positives (see below).

3. **Stratified personal read of 207 additional rows** that passed the
   structural check (up to 8 per (language, fixture_type) stratum, 28 strata,
   `random.seed(42)`) -- catches what marker-presence alone can't (a
   correctly-decorated function whose body doesn't actually behave like a
   fixture). Zero further issues found; 100% agreement with the mechanical
   pass.

4. **The remaining 1,291 rows** passed the structural check but were not
   individually read by a human/LLM reviewer -- labeled TP on the strength of
   the mechanical check alone, consistent with its 100% agreement rate on the
   207-row read sample. `reviewer_notes` on every row states which of these
   four tiers produced its label.

## Result: 1,508 / 1,513 TP -- 99.67% precision, 5 confirmed FP

### False positives found

1. **`@pytest.mark.usefixtures(...)` / `@pytest.mark.parametrize(...,
   lazy_fixture(...))` collide with the `pytest_decorator` substring rule.**
   `fixture_definitions.yaml`'s `pytest_decorator` pattern is `match_substrings:
   [pytest, fixture]` -- any decorator text containing both substrings
   matches. `@pytest.mark.usefixtures("x")` contains "pytest" (from
   `pytest.mark`) and "fixture" (from "usefixtures"); `@pytest.mark.parametrize(...,
   lazy_fixture(...))` contains "pytest" and "fixture" (from "lazy_fixture"
   inside the argument list). Both are real *test* functions carrying an
   unrelated pytest mark, not fixture definitions. 4 of 5 confirmed FPs
   (`human-fixtures-dataset-b-0089`, `-0177`, `-0216` in
   `python_fixtures_sample_*.csv`; `-0317` also python).

2. **A TypeScript `before_each` row's `raw_source` extraction ran past the
   hook's own closing brace**, capturing an unrelated trailing `it.skip(...)`
   test block and the enclosing `describe(...)`'s closing brace instead of
   stopping at the hook's own end. Confirmed against live GitHub source
   (react-spring `parallax.spec.tsx`): the real `beforeEach` is 4 lines
   (L167-170); the claimed range was L167-186.
   (`human-fixtures-dataset-b-0102` in `typescript_fixtures_sample_*.csv`.)

Neither finding was fixed in `collection/detector_python.py` /
`collection/detector_javascript.py` as part of this review -- flagged for a
follow-up fix, not addressed here.
