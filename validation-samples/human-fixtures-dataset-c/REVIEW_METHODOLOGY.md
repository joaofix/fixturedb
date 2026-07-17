# Manual review methodology: human-fixtures-dataset-c

Full 1,527-row sample (382 Python / 383 Java / 380 JavaScript / 382 TypeScript,
Cochran 95%/5%, seed=42), reviewed 2026-07-17.

## Method

Same four-tier methodology as `human-fixtures-dataset-b`'s review (see that
directory's `REVIEW_METHODOLOGY.md` for full rationale):

1. **Full-population structural check** (all 1,527 rows) against
   `fixture_definitions.yaml`'s documented ground truth. 1,525 passed; 2 were
   flagged (a Python `test_`-prefixed function name, and a false
   structural-sanity alarm on an unrelated string literal).
2. **Live GitHub verification of both flagged rows** — both confirmed true
   positives.
3. **Stratified personal read of 214 additional rows** that passed the
   structural check (up to 8 per (language, fixture_type) stratum, 29
   strata, `random.seed(42)`). Found **1 confirmed false positive** (below).
4. **The remaining 1,311 rows** passed the structural check but were not
   individually read — labeled TP on the strength of the mechanical check,
   consistent with its near-100% agreement rate on the 216-row read sample.

## Result: 1,526 / 1,527 TP — 99.93% precision, 1 confirmed FP

### False positive found

**`after()` in a vendored test262 file is a plain variable, not Mocha's
`afterEach`/`after` hook.** `endojs/endo`'s repo includes a full vendored
copy of the ECMAScript conformance suite (test262) under
`packages/test262-runner/test262/`. One such file
(`test/annexB/language/function-code/if-decl-else-decl-b-func-existing-var-update.js`)
declares `var after;`, later assigns it a function reference, and calls it as
`after()` to assert on Annex B function-hoisting semantics — nothing to do
with Mocha. The `mocha_after` pattern (`after(`) matched the call site
without any framework context. (`human-fixtures-dataset-c-0125` in
`javascript_fixtures_sample_*.csv`.)

This generalizes: `endojs/endo`'s vendored test262 files contribute 48
fixtures to Dataset C's javascript corpus (0.14% of the 33,454 total) — all
from a third-party spec-conformance suite the endo project ships, not code
the project's own developers wrote as tests. Not fixed as part of this
review; noted as a low-volume, contained instance of a more general
"vendored test suites get scanned like first-party tests" risk.

### Edge case documented, not counted as a false positive

One TypeScript file (`iTwin/itwinjs-core`,
`ui/components/src/test/toolbar/toolbarWitOverflow.test.tsx:35-38`) has an
`afterEach(cleanup)` call nested *inside* another `afterEach(() => {...})`'s
own callback body. The detector's recursive AST walk does not skip a
matched call's subtree, so both the outer and the inner `afterEach(...)`
are detected as separate fixtures. Both are genuine calls to Mocha's real
hook function (confirmed by direct inspection), just at an unusual nesting
position — not a detection error, so not labeled FP. Flagged here for
visibility since it means a single, unusually-written source location can
contribute more than one row to the corpus.

## A much larger finding, not a fixture-content issue: duplicate repos

Independent of the row-by-row TP/FP review above, aggregate analysis found
**16.2% of Dataset C's entire fixture corpus (34,653 of 214,436 fixtures
across all four languages) is duplicate content**: repos that are forks,
GitHub org transfers, or otherwise share byte-identical git history at the
Dataset C cutoff commit, counted once per repo name even though the
underlying commit — and therefore every fixture in it — is identical.

The largest single cluster: `jetbrains/jetbrainsruntime`, `openjdk/jdk`,
`openjdk/loom`, `openjdk/valhalla`, and one more OpenJDK-derived repo all
resolve to the exact same cutoff commit
(`f5ee356540d7aa4a7663c0d5d74f5fdb0726b426`), contributing 3,460 identical
fixtures each — 17,300 fixtures, 21.9% of Java's entire 79,168-fixture
corpus, from what is really one snapshot of one codebase.

Per-language duplicate-content rate: python 12.0%, java 25.6%, javascript
5.9%, typescript 12.4%. This is a data-quality issue in the underlying
`github-search-raw` source (confirmed present in the raw SEART export
itself, not introduced by this project's own selection code), not a
labeling error in the sampled fixtures — every duplicated fixture is
individually a correct detection, just not an independent observation.
Not fixed as part of this review; a decision on how (or whether) to
deduplicate before analysis is a separate methodology question.
