# JUnit 3 fallback detection: how "extends TestCase" is actually checked

**Date**: 2026-08-14
**Context**: documentation-only investigation, requested to get the paper's
description of JUnit 3 (`junit3_setup`/`junit3_teardown`) detection exactly
right. No code changes. The two fixture_types are rare enough (15 fixtures
across the two databases RQ1 actually compares, `db/a.db` + `db/c_sampled.db`)
that no rerun is warranted regardless of what this turned up.

---

## 1. Where it lives

`collection/detector_java.py`:

- `_enclosing_class_extends_test_case()` (lines 58-72) -- the check itself.
- Its call site, inside `_detect_java()`'s `method_declaration` visitor
  (lines 129-149) -- the JUnit3 fallback only fires for a method named
  `setUp`/`tearDown` (`JUNIT3_FALLBACK_NAMES`, from
  `fixture_definitions.yaml`'s `junit3_fallback.names`) that has **no
  annotations at all** and whose enclosing class passes the check below.

## 2. What the check actually does

```python
def _enclosing_class_extends_test_case(node, src_bytes: bytes) -> bool:
    current = node.parent
    while current is not None:
        if current.type == "class_declaration":
            for child in current.children:
                if child.type == "superclass":
                    return "TestCase" in _source(child, src_bytes)
            return False
        current = current.parent
    return False
```

Confirmed directly against `tree-sitter-java` (fed synthetic class
declarations and inspected the `superclass` node's text):

- It walks up from the `setUp`/`tearDown` method to its **immediate**
  enclosing `class_declaration` only -- the first one found, not every
  ancestor class.
- That class's `superclass` clause's source text is exactly `extends
  <Name>`, where `<Name>` may be simple (`TestCase`) or fully qualified
  (`junit.framework.TestCase`) -- whatever the source actually wrote.
- The test is `"TestCase" in text` -- a **plain substring containment
  check**, not an equality/exact-name check and not a type-resolution
  check. It matches `extends TestCase` and `extends junit.framework.TestCase`
  as intended, but it would equally match any superclass name that merely
  *contains* the substring `TestCase` (e.g. `AbstractMojoTestCase`,
  `MyTestCaseBase`), regardless of whether that class has anything to do
  with JUnit.
- It is **not recursive**: it does not resolve `<Name>` to a class and walk
  *its* superclass in turn. If a repo's own base class extends
  `junit.framework.TestCase` two levels up but the base class's own name
  doesn't contain the substring "TestCase", the fallback will not fire
  (false negative, silently). Conversely a totally unrelated class merely
  named `...TestCase...` would false-positive (see below for the one real
  instance found).

## 3. Fixture counts

Both DBs RQ1's Java comparison actually reads (`db/a.db`,
`db/c_sampled.db` -- the sampled Dataset C used throughout `research_questions/`):

| Dataset | `junit3_setup` | `junit3_teardown` |
|---|---|---|
| A (`db/a.db`) | 1 | 0 |
| C sampled (`db/c_sampled.db`) | 12 | 2 |

(For reference only, not what RQ1 compares: the full, pre-sampling
`db/c.db` has 1,218 `junit3_setup` / 653 `junit3_teardown` -- Dataset C's
sampling draws a subset of repos, not a subset of fixtures, so this larger
number isn't inconsistent with the 12/2 above, just a different repo set.)

## 4. Manual check of all 15 -- real TestCase, or a substring coincidence?

Checked every one of the 15 fixtures' enclosing class against the actual
source at (or immediately before, for since-deleted files) each repo's
real commit history:

| Repo | Files | Superclass text | Verdict |
|---|---|---|---|
| `bcgit/bc-java` (A) | `HaetaeTest.java` | `extends TestCase` | genuine JUnit 3 |
| `apache/doris` | `TestFileSystemManager.java`, `TestHDFSBrokerService.java` | `extends TestCase` | genuine (files later deleted in 2025; content confirmed at the commit right before deletion) |
| `apache/incubator-doris` | same 2 files | `extends TestCase` | genuine -- pre-graduation duplicate of the `apache/doris` files above (same content, different repo; not flagged in `duplicate_repos_by_current_commit.csv`, which keys on current-HEAD SHA equality and these repos have long since diverged there) |
| `apple/coremltools` | `UnknownFieldSetTest.java` | `extends TestCase` | genuine, but the fixture is from **vendored code**: `deps/protobuf/.../com/google/protobuf/test/...` -- Google's own protobuf test suite, bundled inside coremltools's repo, not authored by coremltools |
| `datavane/tis` | `AddSolrDocument.java`, `InOptimizeClientAgentTest.java`, `OptimizeClient2AgentTest.java` | `extends TestCase` | genuine and active at Dataset C's own pre-2021 cutoff commit (`ec9b61b`, 2020-09-26) -- these files were later entirely wrapped in `//` comments by the repo's own authors in a 2021-12 refactor and finally deleted in 2022-10, well after the cutoff Dataset C actually pins to, so none of that affects what was extracted |
| `theotherp/nzbhydra2` | `ChangelogGeneratorMojoTest.java`, `ReleaseMojoTest.java`, `SetReleaseFinalMojoTest.java` | `extends AbstractMojoTestCase` | **substring match, not literal `TestCase`** -- see below |

**The one interesting case**: `nzbhydra2`'s three fixtures extend
`AbstractMojoTestCase` (from `maven-plugin-testing-harness`), which the
substring check accepts because "TestCase" appears inside that name. This
is *not* a false positive in outcome -- `AbstractMojoTestCase` genuinely
extends `PlexusTestCase`, which genuinely extends `junit.framework.TestCase`,
so `setUp()`/`tearDown()` here are real JUnit 3 lifecycle methods -- but the
detector doesn't know that chain exists. It got the right answer by
coincidence of naming, the same way it would get the wrong answer for a
hypothetical unrelated class merely named e.g. `MyTestCaseWrapper`. No such
wrong case exists in either database today; this is a characterization of
the check's precision, not a data quality bug to fix.

## 5. How to describe this in the paper

Accurate language: *"JUnit 3's `setUp()`/`tearDown()` fixtures (unlike
every other Java fixture_type in this study) carry no annotation, so
they're identified by method name plus a check that the immediately
enclosing class's `extends` clause contains the substring `TestCase` --
matching the literal and fully-qualified JUnit 3 base class as intended,
but not verifying the match through type resolution or the full
inheritance chain."* Given the check's low incidence (15/~78,000+ fixtures
combined) and that manual review found the only substring-driven match
(`AbstractMojoTestCase`) to still be semantically correct, this is a
documented, narrow imprecision rather than a validity threat -- consistent
with how `fixture_definitions.yaml`'s existing `known_imprecisions` list
already documents the analogous `@BeforeClass`/`@AfterClass`
JUnit4-vs-TestNG ambiguity. Not added there in this pass since the task
was scoped to investigation/write-up only; worth a one-line addition
there if/when someone next touches that file.
