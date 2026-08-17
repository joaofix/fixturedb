# `num_objects_instantiated`: false-positive rate, corpus-wide -- RESOLVED

**Date**: 2026-08-16 (investigated); fixed same day -- see "Resolution" at
the bottom.
**Context**: manual spot-check of one fixture (`db/a.db` fixture #46, a
`setUp` with `num_objects_instantiated=4`) found the 4th "instantiation"
was actually `VALUES (` inside a SQL string literal embedded in the
fixture body -- not real Python code. This investigates how common that
kind of false positive is across the whole corpus, not just SQL, and
whether it's the only mechanism. Started as investigation-only; the
finding was significant enough that a fix was implemented the same day
(see "Resolution").
Run against `past-datasets/16-aug-2026/db/{a,c}.db` (the just-archived
snapshot -- see `git log`'s "Archive datasets/..." commit).

---

## Method

`_count_object_instantiations()` (`complexity_provider.py`) is two regex
patterns from `feature_extraction_patterns.yaml`'s
`object_instantiation_patterns`, run against a fixture's raw, un-parsed
source text:

- **Java/JS/TS**: `` \bnew\s+[\w.]+\s*(?:<.+?>)?\s*\( `` -- anchored on the
  `new` keyword.
- **Python**: `` \b[A-Z][A-Za-z0-9_]*\s*\( `` -- "capitalized identifier
  immediately followed by `(`", a heuristic with no `new`-style anchor at
  all (the YAML's own comment already flags this: *"Not restricted to
  Python's actual class names, so it can overcount"*).

Neither pattern is AST-aware -- both are plain text/regex scans over the
fixture's full `raw_source`, with no notion of "this byte range is inside
a string literal" or "this is the function's own signature, not its
body". Two independent checks were run against every fixture in both
datasets with `num_objects_instantiated > 0` (62,271 fixtures, 123,632
regex matches total):

1. **Structural**: re-parse each fixture's `raw_source` with the same
   tree-sitter grammar the real pipeline already uses (`_get_parser()` in
   `detector_shared.py` -- no new parsing logic), and check whether each
   regex match's byte position falls inside a `string`/`comment`-type
   node (Python: `string`/`comment`; Java: `string_literal`/
   `character_literal`/`line_comment`/`block_comment`; JS/TS: `string`/
   `template_string`/`comment`). This is exact and covers the *entire*
   corpus, not a sample -- it generalizes the SQL-string case found
   manually to every language and every kind of embedded text (comments,
   commented-out code, generated-source string literals, docstrings).
2. **Self-match** (found during this investigation, Python-only): a
   fixture whose own name is capitalized (PascalCase or
   `SCREAMING_SNAKE_CASE` -- both valid, if unconventional, Python
   identifiers) can match the heuristic against its **own `def NAME(`
   signature line**, with zero relation to anything the fixture's body
   actually does.
3. **Manual semantic review**: a random sample of 46 matches that pass
   both checks above (20 Python, 10 Java, 8 JS, 8 TS) was read by hand for
   any further false-positive pattern (e.g. a capitalized helper/BDD
   function -- `Given(...)`/`When(...)`/`Then(...)` -- that isn't a
   constructor at all). None found -- every one was a genuine constructor
   or factory call once the two mechanisms above are accounted for.

---

## Finding 1: structural (string/comment) false positives -- corpus-wide

| Dataset/language | Fixtures (count>0) | Matches | Struct. FP matches | % of matches | Fixtures w/ ≥1 FP | % of fixtures |
|---|---|---|---|---|---|---|
| A / python | 5,821 | 10,112 | 339 | 3.4% | 218 | 3.7% |
| A / java | 520 | 958 | 0 | 0.0% | 0 | 0.0% |
| A / javascript | 348 | 517 | 0 | 0.0% | 0 | 0.0% |
| A / typescript | 2,933 | 3,934 | 56 | 1.4% | 46 | 1.6% |
| C / python | 15,152 | 31,655 | 582 | 1.8% | 254 | 1.7% |
| C / java | 24,208 | 55,489 | 531 | 1.0% | 213 | 0.9% |
| C / javascript | 4,855 | 7,160 | 58 | 0.8% | 33 | 0.7% |
| C / typescript | 8,434 | 13,807 | 51 | 0.4% | 48 | 0.6% |
| **TOTAL** | **62,271** | **123,632** | **1,617** | **1.3%** | **812** | **1.3%** |

Python is consistently the highest (1.8-3.4% of matches) because its
pattern has no keyword anchor -- any capitalized-identifier-then-`(`
sequence matches, which a SQL/text string is fairly likely to
accidentally contain (`VALUES (`, `INSERT (`, doc-comment prose). Java/
JS/TS's `new`-anchored pattern is far more specific -- Dataset A has
*zero* Java/JS structural false positives at all -- but not immune:
Java's biggest source turned out to be **generated-source string
literals** (JShell/compiler-style test fixtures that build a whole Java
class as a string to feed into a `Compiler`, e.g. `"public static MyList
list() { return new MyList(); }\n"` -- `new MyList(` is real Java
*syntax*, just not running Java *code*) and **commented-out code blocks**
(a `/* ... */` block containing several old `new X()` calls, `//`-prefixed
disabled lines). See the doc's own investigation script output for direct
examples of both.

## Finding 2: Python self-match false positives (new, not in the original request)

190 of 20,973 Python fixtures with `num_objects_instantiated > 0`
(0.91%) have a capitalized own name whose `def NAME(`/`async def NAME(`
signature line itself matches the heuristic -- e.g. fixtures literally
named `Popen`, `Model`, `A`, `B`, `G`, `H`, `N`, `X_blobs`,
`HyperParameters`, `NaCl`, `TEST_ADDRESS`. **157 of those 190 (82.6%)
have this self-match as their *only* counted instantiation** -- meaning
their true `num_objects_instantiated` is **0**, not the stored positive
value. Concretely: `TEST_ADDRESS` (`db/c.db` #22248) is stored as
`num_objects_instantiated=1`; its entire body is
`return address_conversion_func("0x...")` -- zero real instantiations.

**Sharp A vs C asymmetry** (a real, dataset-level finding, not noise):

| Dataset | Python fixtures (count>0) | Self-match | Self-match-only (true count = 0) |
|---|---|---|---|
| A | 5,821 | 3 (0.05%) | 1 (0.02%) |
| C | 15,152 | 187 (1.23%) | 156 (1.03%) |

Dataset C's rate is ~25x Dataset A's. Consistent with agent output
following PEP8 `snake_case` fixture-naming near-universally, while
pre-2021 human code has more naming-convention drift (constant-styled
`SCREAMING_SNAKE_CASE` fixtures, single-letter fixture names, PascalCase).
This is a naming-convention artifact of the *fixture's own name*, not of
anything the fixture body does -- unrelated to (and not overlapping much
with) Finding 1's string/comment mechanism (Python union of "struct FP or
self-match": A 3.80%, C 2.86% of fixtures -- close to the two mechanisms'
simple sum, confirming they're largely independent).

## Finding 3: no further false-positive pattern found in code context

The 46-match manual sample (Python/Java/JS/TS, all in real code, past
both checks above) turned up zero additional false positives -- every
match was a genuine `Mock()`/`AsyncMock()`/`DataFrame()`/`new
ApiClient()`/`new Vue({...})`-style real constructor or factory call. A
frequency scan of all 40,846 in-code Python matches' identifiers (9,307
distinct names) surfaced no systematic non-constructor naming pattern
either (checked explicitly for BDD-style `Given`/`When`/`Then`/`Scenario`/
`Step` names -- the ones found, e.g. `Scenario`/`Feature`/
`ExpectationSuite`, are real classes, e.g. Great Expectations' own
`ExpectationSuite`/`ExpectationConfiguration` types).

---

## Assessment

Combining both mechanisms, the false-positive rate is small in aggregate
(~1.3% of all matches structurally, plus an extra ~0.9% of Python
fixtures via self-match) but **not uniform** -- it concentrates almost
entirely in Python, and within Python, concentrates in Dataset C. For any
analysis that treats a fixture's exact `num_objects_instantiated` value as
meaningful (rather than just "zero vs. non-zero"), roughly 1 in 25
Dataset-C Python fixtures with a positive count should be treated with
caution, and about 1 in 100 should be treated as **wrong** (true value 0).

This is not currently a live risk to the paper's reported numbers:
`num_objects_instantiated` is collected and exported but **not** one of
RQ1's reported comparative metrics (see `rq1.py`'s module docstring --
`num_objects_instantiated`/`num_external_calls` are "still collected but
not part of the paper's reported RQ1 metrics"). It matters if/when this
metric is ever promoted to a reported comparison, or used descriptively
in the paper text.

No code change is proposed here (investigation only, per instructions).
If this metric is ever reported, two independent, low-cost mitigations
exist and could be implemented later: (a) skip matches whose byte range
falls inside a string/comment node (the same tree-sitter walk this
investigation already does, reusable almost verbatim), and (b) skip a
match that starts at byte 0 of `raw_source` (the fixture's own
`def`/`async def` line can never itself be an instantiation happening
*inside* the fixture).

---

## Resolution (2026-08-16, same day)

Rejected as "unacceptable to leave as-is" -- implemented mitigation (a)
above, generalized: rather than filtering regex matches after the fact,
`num_objects_instantiated` was rewritten to walk the fixture's own
already-parsed tree-sitter node directly and count real AST node types --
`object_creation_expression` (Java), `new_expression` (JS/TS), and a
capitalized-target `call` node (Python, which has no dedicated
"constructor" node at all). See `detector_shared.py::
_count_object_instantiations()`.

This fixes both false-positive mechanisms **structurally**, not just in
the cases this investigation happened to check: a string literal's or
comment's contents are never parsed as nested code, so neither can ever
produce a matching node; a fixture's own `def NAME(...):` line is a
`function_definition` node, never a `call` node, so the self-match
mechanism (Finding 2) can't occur either. `complexity_provider.py`'s
regex-based `_count_object_instantiations()` and
`feature_extraction_patterns.yaml`'s `object_instantiation_patterns`
section were both removed rather than kept as unused code.

New regression tests reproduce every case this investigation found by
hand (SQL-in-string, Java line/block comments, JS template-string,
self-named `TEST_ADDRESS`-style fixture, plus a bonus case found while
re-verifying -- a nested `class Foo(Bar):` definition also matched the
old regex and no longer does) --
`tests/collection/test_extractor_metadata/test_object_instantiations.py::TestObjectInstantiationsFalsePositiveFixes`.

No DB migration was needed (this changes values, not schema -- the
column already existed). Landed while `datasets/`/`db/` were already
empty ahead of the next full collection run (see the "Archive
datasets/..." commit), so the fix applies cleanly to fresh data with no
backfill question to resolve.
