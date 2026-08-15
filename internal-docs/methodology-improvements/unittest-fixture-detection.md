# Python `unittest` setUp/tearDown: matched on method name alone, no class check

**Date**: 2026-08-15
**Context**: documentation-only investigation into whether Python's
`unittest_setup` detection verifies the enclosing class actually derives
from `unittest.TestCase`, parallel to the JUnit3 investigation (see
[junit3-fallback-detection.md](junit3-fallback-detection.md)). No code
changes.

---

## 1. Where it lives

`collection/detector_python.py`, the `elif node.type == "function_definition"`
branch (lines 84-113) inside `_detect_python()`'s `visit()`.

## 2. What the check actually does

```python
elif node.type == "function_definition" and id(node) not in decorator_matched_funcs:
    name_node = node.child_by_field_name("name")
    if name_node:
        name = _source(name_node, src_bytes)
        if name in UNITTEST_SETUP_NAMES:
            results.append(_build_result(..., fixture_type="unittest_setup", ...))
```

**There is no enclosing-class check at all** -- unlike Java's JUnit3
fallback (`_enclosing_class_extends_test_case()`, a real if imprecise
substring check), Python's `unittest_setup` detector fires for *any*
function/method anywhere in the file named one of `UNITTEST_SETUP_NAMES`
(`fixture_definitions.yaml`'s `python.unittest_setup.names`: `setUp`,
`tearDown`, `setUpClass`, `tearDownClass`, `setUpModule`,
`tearDownModule`, `asyncSetUp`, `asyncTearDown`), regardless of whether
it's a method on a class at all, and if it is, regardless of what that
class extends. So:

- No, it does not check for `unittest.TestCase`/`TestCase` in any form.
- The substring/exact/qualified-name questions don't apply -- there's
  nothing to match against, since no class lookup happens.
- Indirect inheritance (`class MyBase(unittest.TestCase): pass` /
  `class MyTest(MyBase): pass`) is trivially "handled": `setUp` in
  `MyTest` is detected, but only because *every* `setUp`/`tearDown` is
  detected, indirect-inheriting or not, TestCase-related or not.

This is a real difference in design between the two languages'
detectors, not an oversight specific to this investigation -- but it does
mean Python's `unittest_setup` fixture_type is method-name matching, full
stop, and its accuracy rests entirely on how reliably real-world code
uses these six/eight names only inside genuine `TestCase` hierarchies.

**Side note on fixture_type granularity**: the request's queries assumed
separate `unittest_setup`/`unittest_teardown`/`unittest_setup_class`/
`unittest_teardown_class` fixture_types. Only one exists:
`"unittest_setup"` is the fixture_type for *all* of `setUp`/`tearDown`/
`setUpClass`/`tearDownClass`/`setUpModule`/`tearDownModule`/`asyncSetUp`/
`asyncTearDown` alike (`_build_result(fixture_type="unittest_setup", ...)`
is hardcoded on line 95, regardless of which of the six/eight names
matched) -- they're distinguished only by `scope` (`per_test`/`per_class`/
`per_module`), confirmed directly against both DBs (`SELECT DISTINCT
fixture_type FROM fixtures WHERE fixture_type LIKE 'unittest%'` returns
exactly one value in each). Also, `fixtures` has no `dataset` column --
Dataset A/B/C are separate `.db` files, not a column to filter on.

## 3. Scale

Query against both DBs actually used elsewhere in `research_questions/`:

| Dataset | `unittest_setup` (all scopes) | per_test | per_class | per_module |
|---|---|---|---|---|
| A (`db/a.db`) | 2,126 | 1,973 | 143 | 10 |
| C sampled (`db/c_sampled.db`) | 8,843 | 7,631 | 1,139 | 73 |

Matches `rq1.md`'s existing published counts exactly.

## 4. Manual review: 20 random `unittest_setup` fixtures per dataset

For each of 40 sampled fixtures (`ORDER BY RANDOM() LIMIT 20` against each
DB), fetched the real file at the fixture's own recorded `commit_sha`
(populated on every fixture row in both datasets, not just Dataset A) and
located the nearest enclosing `class ... :` declaration above the
fixture's `start_line`.

**Dataset A: 20/20 genuine.** Every sampled fixture's enclosing class is
`unittest.TestCase`/`TestCase` directly, or through a resolved indirect
chain -- e.g. `jsv4/opencontracts`'s `_BaseGeoMutationTestCase(TestCase)`,
and `talebook/talebook`'s `TestScanDuplicateDetection(TestWithUserLogin)`,
traced three levels (`TestWithUserLogin(TestApp)` ->
`TestApp(testing.AsyncHTTPTestCase)` -> Tornado's `AsyncHTTPTestCase`,
itself a `unittest.TestCase` subclass) and confirmed genuine throughout.

**Dataset C sampled: 19/20 genuine, 1/20 a real non-TestCase mixin.**
Confirmed multiple indirect chains as real (`aiidateam/aiida-core`'s
`AiidaTestCase(unittest.TestCase)`; `pypr/pysph`'s
`DictBoxSortNNPSTestCase(NNPSTestCase)` where `NNPSTestCase(unittest.
TestCase)`; `facebookresearch/crypten`'s `TestTFP(MultiProcessTestCase,
TestOptim)`, where the *first* base, `MultiProcessTestCase`, is
`unittest.TestCase` and the *second*, `TestOptim(object)`, is not --
Python's MRO puts `unittest.TestCase` in scope regardless, and the
sampled `tearDown()` correctly calls `super().tearDown()`).

The one exception: **`garethdmm/gryphon`**, file
`gryphon/tests/environment/exchange_wrappers/coinbase_auth.py`:

```python
from gryphon.tests.environment.exchange_wrappers.auth_methods import ExchangeAuthMethodsTests

class TestCoinbaseBTCUSDAuthMethods(ExchangeAuthMethodsTests):
    def setUp(self):
        self.exchange = CoinbaseBTCUSDExchange()
```

`ExchangeAuthMethodsTests` (`auth_methods.py`) is `class
ExchangeAuthMethodsTests(object):` -- a plain mixin, not a
`unittest.TestCase` subclass anywhere in its chain. Under standard
`unittest`/`pytest` semantics, `setUp()` on a non-`TestCase` class is not
a recognized lifecycle hook and would not run automatically -- this looks
like a genuinely mis-detected fixture, not a data artifact.

**Followed up beyond the one sampled instance**: this is not an isolated
one-off inside `gryphon` -- the same mixin pattern (a shared
`ExchangePublicMethodsTests(object)`/`ExchangeAuthMethodsTests(object)`
base, combined per-exchange under `environment/exchange_wrappers/`,
`environment/exchange_coordinator/`, and `logic/exchange_wrappers/`)
recurs across that repo. Of `gryphon`'s 53 `unittest_setup` fixtures in
`db/c_sampled.db`, roughly 23 (43%) sit in this non-`TestCase` mixin
pattern (verified a sample of these files directly); the other ~30 (the
`logic/libraries/`, `logic/models/`, `logic/strategies/` test files) are
genuine `unittest.TestCase` subclasses, confirmed directly (e.g.
`order_sliding_test.py`'s `TestOrderSliding(unittest.TestCase)`).

## 5. Assessment

**Is a class check missing that matters?** In principle yes -- Python's
detector has no equivalent of Java's (imprecise but present) superclass
check, so it will over-detect in any repo that reuses `setUp`/`tearDown`
as plain method names outside a `TestCase` hierarchy (mixins meant to be
combined with a `TestCase` elsewhere but occasionally left standalone,
helper classes, or genuinely unrelated code). In practice, across 40
independently-sampled instances, this only materialized in **one repo**
(`gryphon`), contributing an estimated 23/8,843 (~0.26%) of Dataset C
sampled's `unittest_setup` fixtures, and 0/2,126 (0%) of Dataset A's in
this sample. Every one of the other 12 distinct repos sampled (7 in A, 6
in C, `gryphon` the only exception) used the six/eight lifecycle names
exactly as `unittest` intends, including several genuine multi-level
indirect-inheritance chains resolving correctly to `unittest.TestCase`.

**Net read**: not a systemic validity threat at the scale sampled --
the false-positive rate observed (1/20 fixtures, but concentrated in a
single small-to-mid repo rather than spread evenly) is low and doesn't
change any RQ1-3 conclusion at this sample's precision. It is a real,
concrete, non-hypothetical example of what "name-only matching" can miss,
worth stating plainly in the paper's limitations rather than asserting
Python's `unittest_setup` fixtures are class-verified (they are not).
Given the 1/20 (5%) hit rate in a random sample of just 20, a full-corpus
audit would very plausibly turn up more mixin-pattern repos like
`gryphon` -- this single-sample estimate should be treated as a lower
bound on the true rate, not a precise measurement.
