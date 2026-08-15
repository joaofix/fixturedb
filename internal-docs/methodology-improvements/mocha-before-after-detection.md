# Mocha bare `before()`/`after()`: member-expression calls (`page.after()`) structurally can't match

**Date**: 2026-08-15
**Context**: documentation-only investigation into whether the
`mocha_before`/`mocha_after` detector can false-positive on method calls
like `page.after(...)`/`browser.before(...)`. No code changes.

---

## 1. Where it lives, and a premise correction

`collection/detector_javascript.py::_detect_js()`. One correction to the
request's framing: **there is no Tree-sitter query object/string
anywhere in this codebase** -- no call site uses `tree_sitter.Query`
(the S-expression query language). Detection is a hand-written recursive
visitor (`visit()`) walking every AST node and using
`child_by_field_name("function")`/`_source()` directly -- the same
mechanism as every other detector in this project (Python, Java). So
"show the exact Tree-sitter query string" doesn't apply; what follows is
the exact matching logic instead.

```python
if node.type in ("call_expression", "await_expression"):
    target = node  # (or the inner call_expression, if await-wrapped)
    func_node = target.child_by_field_name("function")
    if func_node:
        name = _source(func_node, src_bytes).strip()
        if name in JS_FIXTURE_CALLS:   # {"before": ..., "after": ..., "beforeEach": ..., ...}
            ...
```

`JS_FIXTURE_CALLS`'s keys are exactly `beforeEach`/`beforeAll`/
`afterEach`/`afterAll`/`before`/`after`/`aroundEach`/`aroundAll`
(`fixture_definitions.yaml`'s `javascript_typescript.hooks`).

## 2. Why this is (a), not (b) -- by construction, not by design intent alone

For `page.after(() => {...})`, tree-sitter-javascript's grammar makes the
call_expression's `function` field a **`member_expression`** node whose
own source text is `"page.after"` -- confirmed directly:

```
call_expression ['page.after(() => { page.close(); })']
  member_expression ['page.after']
    identifier ['page']
    . ['.']
    property_identifier ['after']
  arguments [...]
```

`name = "page.after"`, and `"page.after" in JS_FIXTURE_CALLS` is `False`
-- not because the code special-cases member expressions, but because a
member expression's full rendered text always contains a `.` (or `?.`,
or bracket-subscript syntax) and can therefore never *equal* the bare
4-6 character hook name it's being compared against. Exact full-text
string equality against a short literal, not a substring/regex check (as
in Java's JUnit3 fallback -- see
[junit3-fallback-detection.md](junit3-fallback-detection.md), which
*does* have this kind of exposure via substring matching), is what
rules this out structurally, for any receiver name and any of the four
member-access syntaxes JS has.

## 3. Empirical test (ran the actual detector, not a reimplementation)

```js
before(() => { client = setup(); });
after(() => { client.close(); });
page.after(() => { page.close(); });
browser.before(() => { browser.reset(); });
el.insertBefore(node, ref);
```

Fed directly to `_detect_js()`:

```
2 fixture(s) detected:
  fixture_type='mocha_before' raw_source='before(() => { client = setup(); })'
  fixture_type='mocha_after'  raw_source='after(() => { client.close(); })'
```

Exactly the 2 genuine bare calls; `page.after(...)`, `browser.before(...)`,
and `el.insertBefore(...)` are all correctly excluded. Matches §2's
prediction exactly.

## 4. Scale

| Dataset | `mocha_before` | `mocha_after` | Combined | % of all fixtures |
|---|---|---|---|---|
| A (`db/a.db`) | 435 | 356 | 791 | 2.0% (791/39,088) |
| C sampled (`db/c_sampled.db`) | 3,099 | 1,316 | 4,415 | 11.2% (4,415/39,377) |

## 5. Manual sample: 20 `mocha_before` + 20 `mocha_after`, both datasets (80 total)

Classified each sampled `raw_source` by whether the captured text itself
starts with a bare `before(`/`after(` call (a false positive from a
member-expression call would necessarily start with
`<receiver>.before(`/`<receiver>.after(`, since `raw_source` is exactly
the matched `call_expression`'s own source text):

| Sample | n | Genuine bare `before()`/`after()` | Non-bare (method call etc.) |
|---|---|---|---|
| Dataset C `mocha_before` | 20 | 20 | 0 |
| Dataset C `mocha_after` | 20 | 20 | 0 |
| Dataset A `mocha_before` | 20 | 20 | 0 |
| Dataset A `mocha_after` | 20 | 20 | 0 |
| **Total** | **80** | **80 (100%)** | **0 (0%)** |

Spot-checked the actual content beyond the prefix check, too: every
sample is unambiguous real test scaffolding -- sinon stubs, server
setup/teardown, temp-dir cleanup, `app.stop()` -- not, e.g., some
unrelated top-level function that happens to be named `before`/`after`
for a non-Mocha purpose (a theoretically distinct false-positive
category from the one asked about, and also not observed here).

## 6. Assessment

**Zero exposure, and not by luck.** Unlike Java's `@Rule`/`@ClassRule`
(Lizard structural gap) or JUnit3's `TestCase` substring check or
Python's unannotated `unittest_setup` (no class check at all), this
detector's exact full-text-equality-against-a-short-literal design
makes the specific false-positive shape asked about
(`page.after()`/`browser.before()`) **structurally impossible**, for any
receiver name or member-access syntax -- confirmed both by reading the
match logic and by two independent tests (a direct run of the actual
detector against adversarial input, and a 100%-clean 80-fixture manual
sample across both datasets). No effect on any reported metric; no
follow-up needed.

**Now tracked live**: `dataset_findings.py`'s "Mocha Bare `before()`/
`after()` Detection (Regression Guard)" section
(`_fetch_mocha_bare_hook_non_bare_count()`) re-runs this exact
non-bare-call-shape check against every `mocha_before`/`mocha_after`
fixture on every re-collection (0/791 in Dataset A, 0/4,415 in Dataset C
sampled, as of this writing) -- not a live risk estimate (the guarantee
is structural, per above), but a regression guard: a future nonzero
value there would mean the detector's own matching logic changed.
