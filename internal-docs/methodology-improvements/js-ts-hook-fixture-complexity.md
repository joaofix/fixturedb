# JS/TS `beforeEach`/`afterEach`: Lizard handles the arrow callback correctly, but `function_list[0]` can pick the wrong function

**Date**: 2026-08-15
**Context**: documentation-only investigation into whether Lizard reliably
computes LOC/CC for JS/TS hook fixtures, whose bodies are anonymous
callbacks (`beforeEach(() => {...})`), parallel to the JUnit3/`@Rule`/
`unittest` investigations in this directory. No code changes, no reruns
of collection.

---

## 1. The call mechanics (`complexity_provider.py`)

`_detect_js()` (`detector_javascript.py`) passes the **whole call
expression** as `func_node` -- `beforeEach(() => {...})`, not just the
arrow function argument. `_build_result()` (`detector_shared.py`) takes
that node's own source text (`src_text = _source(func_node, src_bytes)`)
and passes it, unmodified, to `analyze_function_complexity(src_text,
language)`. So Lizard is handed exactly the snippet the request's example
shows -- a standalone statement, not a bare function body.

`analyze_function_complexity()` (`complexity_provider.py:75-172`) writes
that text to a temp file (extension from `_get_extension()`: `.js`/`.ts`)
and calls `lizard.analyze_file()` on it. It then reads
`result.function_list[0]` -- **always index 0, unconditionally, no name
matching** (the `function_name` parameter exists but is never read in the
body). If `function_list` is empty, the pre-seeded defaults
(`cyclomatic_complexity: 1, num_parameters: 0, num_external_calls: 0`)
are returned untouched -- this is the (b) failure mode the request
described, and it's real, but (per the empirical tests below) it doesn't
happen for arrow-callback hooks. LOC is computed separately, not from
Lizard (`_count_loc(src_text)` in `_build_result`, a non-blank line count
over the same `src_text` -- see this directory's other writeups for why).

## 2. Empirical test: does Lizard find the arrow callback?

Ran the three requested snippets directly through `lizard.analyze_file()`
with a `.js` extension:

| Test | function_list length | name | nloc | cc |
|---|---|---|---|---|
| 1. Simple arrow callback | 1 | `(anonymous)` | 3 | **1** |
| 2. Arrow callback, if/else | 1 | `(anonymous)` | 7 | **2** |
| 3. Named function, if/else (control) | 1 | `setup` | 7 | **2** |

**Answer to the core question: (a).** Lizard identifies the anonymous
arrow callback as its own function unit and computes CC correctly --
Test 2 and Test 3 (identical bodies, one arrow/one named) produce
byte-identical `nloc`/`cc`. Anonymity is not the problem; `(anonymous)`
just means Lizard couldn't find a name token, which `_build_result()`
already handles separately (`name = ... else f"<anonymous>_{line}"`, not
used for the metrics themselves).

## 3. CC distribution: before_each/after_each vs unittest_setup

| Dataset | Group | n | min | p25 | median | p75 | max | mean | % at CC=1 |
|---|---|---|---|---|---|---|---|---|---|
| A | before_each + after_each (JS/TS) | 21,703 | 1 | 1.00 | 1.00 | 1.00 | 11 | 1.165 | 88.7% |
| A | unittest_setup (Python) | 2,126 | 1 | 1.00 | 1.00 | 1.00 | 13 | 1.352 | -- |
| C sampled | before_each + after_each (JS/TS) | 12,327 | 1 | 1.00 | 1.00 | 1.00 | 8 | 1.040 | 96.9% |
| C sampled | unittest_setup (Python) | 8,843 | 1 | 1.00 | 1.00 | 1.00 | 11 | 1.206 | -- |

p25/median/p75 all land on 1 for **every** group here, JS/TS and Python
alike -- this floor is not a JS/TS-specific artifact of Lizard mishandling
anonymous callbacks; it's the same shape Python's own Lizard-derived CC
has (Python's CC also comes from Lizard, just with `num_parameters`
separately overridden -- see `_build_result()`). The genuine signal is in
the tail: real variance exists (max 8-13, mean consistently >1), and
Dataset A's hooks skew mildly more complex than Dataset C's (88.7% vs
96.9% at floor) -- plausibly real (agent-authored setup doing more
per-hook work), not something this investigation can fully separate from
the mechanism issue in §5 below.

## 4. Manual inspection: 5 CC>1, 5 CC=1 (Dataset A `before_each`)

**CC>1 (5/5 genuine)**: every sample has real, visible branching Lizard
correctly counted -- `if (existsSync(...))` guards before a directory
reset (3 instances, independently, in different repos -- a common
idiom), a `for` loop unrolling two write ranges (`bfirsh/jsnes`, cc=3),
and a `mockApiFetch.mockImplementation((path) => { if...; if...; if...
})` (`zts212653/clowder-ai`, cc=4 -- see §5, this one turned out to be
instructive for a different reason).

**CC=1 (5/5 genuine)**: every sample is a real straight-line callback --
object construction, `mockReset()`/`stubGlobal()` calls, `await
adapter.initialize()`. No missed branching in this particular sample.

## 5. A real mechanism issue found along the way: `function_list[0]` isn't always the outer hook

The `zts212653/clowder-ai` CC=4 sample above has a nested closure
(`mockApiFetch.mockImplementation((path) => { if...if...if... })`) inside
the outer `beforeEach` body. Feeding that exact snippet to Lizard directly
shows **two** function entries, not one:

```
name='(anonymous)' nloc=8 cc=4 start=7 end=14   <- function_list[0]: the INNER mockImplementation callback
name='(anonymous)' nloc=8 cc=1 start=1 end=15   <- function_list[1]: the OUTER beforeEach callback itself
```

Lizard appends functions to `function_list` in the order their closing
brace is reached during parsing, not by source position -- a nested
callback that closes before its enclosing function does comes first.
Since `analyze_function_complexity()` unconditionally reads
`function_list[0]`, **it picked the inner callback's CC (4), not the
outer hook's own CC (1)**, in this instance. Here that's a lucky
coincidence -- the reported number happens to still describe real
complexity that genuinely lives inside the fixture -- but it's not
"the beforeEach callback's own complexity," and the opposite failure is
just as easy to construct:

```js
beforeEach(() => {
    mockApiFetch.mockImplementation((path) => {
      return jsonOk({});
    });
    if (config.auth) {
      client.setAuth();
    } else {
      client.reset();
    }
  })
```

Lizard here again returns the inner callback first (cc=1, no branching)
and the true outer hook second (cc=2, the real if/else) --
`function_list[0]` reports **cc=1**, silently missing the outer
function's own real branch entirely.

**How often does this bite in practice?** Originally estimated from an
80-fixture manual sample (see the git history of this file for that
first pass); **since superseded by an exact, full-population check**,
now live in `dataset_findings.py`'s "JS/TS Hook Fixture Complexity"
section (`_fetch_js_hook_complexity_mismatch()`) -- it re-runs Lizard
directly against every already-stored `raw_source` containing a likely
nested construct (cheap: no network, ~0.5ms/fixture) and compares against
the true outer function (the one starting at `raw_source`'s own line 1),
rather than sampling. Numbers as of this writing (also visible live in
`research_questions/dataset_findings.md`, regenerated on demand):

| Dataset | before_each/after_each | Nested construct | Re-checked | Mismatched | Mismatch rate |
|---|---|---|---|---|---|
| A | 21,703 | 2,031 (9.4%) | 1,669 | 349 | **20.91%** |
| C sampled | 12,327 | 1,511 (12.3%) | 884 | 68 | **7.69%** |
| C full (pre-sampling) | 67,947 | 8,135 (12.0%) | 6,503 | 797 | **12.26%** |

The exact check is unrestricted (checks every nested-construct fixture,
not just ones already reporting CC=1 the way the original manual sample
was scoped), which is why C sampled's rate here (7.69%) is nonzero
despite the original 80-fixture sample finding 0/51 in its (narrower,
CC=1-only) slice -- that sample wasn't wrong, just too small against a
true rate low enough (an exact 26/1,456 ≈ 1.8% within that same CC=1-only
slice) that a 51-fixture sample missing it entirely is unsurprising, not
contradictory.

The mismatch also isn't one-directional -- splitting by which way the
true outer's CC differs from what got recorded:

| Dataset | Under-counted (true > recorded) | Over-counted (true < recorded) |
|---|---|---|
| A | 221 | 128 |
| C sampled | 26 | 42 |
| C full | 257 | 540 |

Dataset A skews toward under-counting (the `await x().catch(() => {})`-
before-real-branching shape described above); Dataset C skews the other
way -- over-counting, i.e. `function_list[0]` picks an inner closure
that itself has real branching (a `.forEach()`/`.map()` callback, an
IIFE) while the outer hook body is actually simple. Both directions are
the same underlying mechanism (parse-completion ordering, not source
position); which direction dominates depends on what kind of nested
construct a codebase's hooks tend to contain, not on anything specific
to agent- vs. human-authored code.

## 6. Assessment

- **The request's core question**: Lizard genuinely parses and measures
  the anonymous arrow callback (option (a)), not (b)/empty-result. The
  floor (~89-97% at CC=1) is a real property of the fixtures themselves
  (confirmed by manual review and by Python's own unittest_setup showing
  an identical floor) -- not evidence of a broken parse.
- **A real, narrower issue exists**, independent of the anonymous-callback
  question the request focused on: `function_list[0]` is not guaranteed
  to be the fixture's own outer function whenever the fixture body
  contains any nested function/arrow (a mock callback, a `.catch()`/
  `.then()` handler, an object-literal method, a `.forEach()`/`.map()`
  callback) that Lizard finishes parsing first. The exact check (§5
  above) puts this at **349/21,703 (1.61%) of Dataset A's, 68/12,327
  (0.55%) of Dataset C sampled's, and 797/67,947 (1.17%) of Dataset C
  full's** before_each/after_each population overall -- i.e. a small
  single-digit share of the whole population, but a real 8-21% mismatch
  rate *within* the narrower "has a nested construct" subset each
  fixture would need to fall into first. Not large enough to move any
  RQ1 conclusion (effect sizes there are already "negligible"/small), but
  a real, previously-undocumented mechanism worth stating precisely in
  the paper's limitations rather than folding into a generic "Lizard
  handles callbacks fine" claim -- and, unlike the original sample-based
  estimate, no longer just an estimate: `dataset_findings.py` computes
  this exactly on every re-collection now (see
  `research_questions/dataset_findings.md`'s "JS/TS Hook Fixture
  Complexity" section), so this number won't silently drift stale the
  way a one-off manual sample would. This is a distinct issue from the
  `@Rule`/`@ClassRule` Lizard-empty-function-list case documented in
  [junit-rule-fixtures.md](junit-rule-fixtures.md) -- there Lizard finds
  *nothing*; here it finds *the wrong one of several*.
