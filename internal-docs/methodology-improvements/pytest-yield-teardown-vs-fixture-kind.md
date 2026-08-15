# Yield-based pytest fixtures: `has_teardown_pair` sees the yield; `fixture_type_kind` structurally can't

**Date**: 2026-08-15
**Context**: resolving a suspected contradiction in RQ2's planned Python
narrative -- does a `@pytest.fixture` with `yield` get correctly credited
with teardown, or does it fall through both classification mechanisms and
inflate a "Python agents don't provide teardown" claim that isn't true?
Investigation only, no code changes.

---

## 1. `fixture_type_kind`: not in `detector_shared.py`/`detector_python.py` at all

**Premise correction**: `fixture_type_kind` isn't computed or persisted
anywhere in the detection/extraction pipeline -- there's no DB column for
it. It's a derived, RQ2-analysis-time-only classification: `_kind()` in
`collection/research_questions/rq2.py`:

```python
def _kind(fixture_type: str, name: str | None = None) -> str:
    if fixture_type in TYPE_BASED_SETUP_TYPES:
        return "setup"
    if fixture_type in TYPE_BASED_TEARDOWN_TYPES:
        return "teardown"
    if fixture_type in NAME_BASED_TEARDOWN_PAIRS and name is not None:
        if name in NAME_BASED_SETUP_NAMES[fixture_type]:
            return "setup"
        if name in NAME_BASED_TEARDOWN_NAMES[fixture_type]:
            return "teardown"
    return "other"
```

`pytest_decorator` is in neither `TYPE_BASED_TEARDOWN_PAIRS` (setup/
teardown as different fixture_types -- Python has no such pair) nor
`NAME_BASED_TEARDOWN_PAIRS` (setup/teardown sharing one fixture_type,
split by name -- Python's `unittest_setup`/`pytest_class_method` do this,
`pytest_decorator` doesn't: every pytest fixture, `yield` or not, is just
named whatever the developer called it). So **every `pytest_decorator`
fixture is classified `"other"`, unconditionally, `yield` or no `yield`**
-- this is not a bug or an oversight, it's already stated explicitly in
`rq2.py`'s own module docstring: *"pytest_decorator -- setup with an
*optional* teardown via `yield`, not captured by type or name ...
buckets as 'other' instead of forcing a fake split."*

## 2. `has_teardown_pair`: correctly reads the `yield`, option (b)

`_calculate_teardown_pairs()` (`detector_shared.py:712-784`) has five
mechanisms, keyed by `feature_extraction_patterns.yaml`'s
`teardown_detection` table. The relevant one:

```yaml
yield_based_fixture_types: [pytest_decorator]
```

```python
elif fixture.fixture_type in YIELD_BASED_TEARDOWN_TYPES:
    has_teardown = "yield" in fixture.raw_source
```

**Option (b), exactly**: no separate complementary fixture is needed --
`has_teardown_pair` for a `pytest_decorator` fixture is a direct,
same-fixture check for a `yield` statement in its own body. This is a
genuinely different, independent mechanism from `_kind()` in §1 -- one
reads the source text for `yield`, the other only ever looks at
`fixture_type`/`name`.

## 3. Quantified: yield vs. `has_teardown_pair`, exact agreement

Python `pytest_decorator` fixtures, both DBs:

| Dataset | has_teardown_pair=1 | has_teardown_pair=0 | Total |
|---|---|---|---|
| A | 2,119 | 6,782 | 8,901 |
| C sampled | 1,217 | 6,286 | 7,503 |

Cross-checked against `raw_source`'s actual `yield` content:

- **100% of `has_teardown_pair=1` fixtures contain `yield`** in both
  datasets (2,119/2,119 in A, 1,217/1,217 in C) -- no false positives.
- **`has_teardown_pair=0` fixtures**: a case-insensitive `LIKE '%yield%'`
  SQL scan initially flagged 7 (A) / 2 (C) as suspicious ("has_teardown_
  pair=0 but body contains 'yield'??"). Investigated each directly:
  **all 9 are docstring prose** -- "Yields a dict...", "Yield each test
  combo..." -- capitalized `Yield`/`Yields` describing what a `return`-
  based fixture hands back, in plain English, not an actual Python
  `yield` keyword anywhere in the code. Re-ran with the exact case-
  *sensitive* check the real code uses (`"yield" in raw_source`, lowercase
  literal): **0/6,782 (A) and 0/7,503 (C) mismatches** -- `has_teardown_
  pair` is in perfect, deterministic agreement with the literal lowercase
  `yield` keyword's presence, with no exceptions in either dataset. (This
  was a false alarm in my own verification query, not a code bug --
  `LIKE` is case-insensitive by default in SQLite; the actual Python `in`
  check is not.)

## 4. Does this explain a high Python "no-teardown" rate?

Computed the literal question -- Python-A repos where *every* Python
fixture is `pytest_decorator` (i.e. 100% `"other"` under `_kind()`), and
separately, where every one of those also has `has_teardown_pair=0`:

| Dataset | Python repos | 100% `pytest_decorator` ("other") | ...*and* `has_teardown_pair=0` for all |
|---|---|---|---|
| A | 490 | 320 (**65.3%**) | 132 (**26.9%**) |
| C sampled | 558 | 205 (**36.7%**) | 82 (**14.7%**) |

**This is the actual mechanism, and it's a real, substantial gap.**
65.3% of Dataset A's Python repos have *every* fixture landing in
`_kind()`'s `"other"` bucket -- which is exactly why the current, live
`research_questions/rq2.md` already shows Python's median `setup_pct`/
`teardown_pct` at **0.0%/0.0%** for Dataset A (0.0%/0.0% also for the
Overall-repo-level medians; C sampled shows 50.0%/0.0%) -- more than half
the repos contribute a literal 0% to that per-repo proportion, dragging
the median itself to 0. But only 26.9% of A's Python repos actually have
*zero detectable teardown by any measure* (`has_teardown_pair`, which
does see `yield`) -- **the other 38.4 percentage points of repos (65.3%
- 26.9%) are repos that DO provide real, detected teardown via `yield`,
just invisible to the `_kind()`-based table because `pytest_decorator`
can never be `"teardown"` kind, full stop.** Same fixture-level pattern:
23.8% of A's `pytest_decorator` fixtures (2,119/8,901) have a real,
detected `yield`-based teardown -- entirely uncounted in the
`fixture_type_kind` distribution table.

**Net**: yes, `fixture_type_kind`'s `"other"` bucket is what drives an
apparent near-zero Python teardown signal in that specific table -- but
it is not evidence that Python fixtures lack teardown; it's evidence that
this one classification scheme can't see it. `has_teardown_pair` is the
metric that actually answers "does this fixture provide teardown," and
by that metric Python's real rate (23.8% fixture-level in A) is
materially higher than what `_kind()`'s `"other"`-heavy table would
suggest on its own.

## 5. The specific "45.4%" / "21.5% vs 24.1%" / "V=0.469" figures

**Searched the full `paper-draft/` tree (all 5 sections) for `45.4`,
`21.5`, `24.1`, and `0.469` -- none currently appear anywhere.**
`3-results.md` (113 lines) has no RQ2 content filled in yet at all (still
placeholder `N/A` tables for most metrics). `2-study-design.md`'s
methodology paragraph already describes teardown pairing correctly
("a setup fixture is flagged paired if it yields (pytest), shares a
naming convention with a teardown fixture ..., or has a same-scope
counterpart hook") -- consistent with §2 above, no correction needed
there.

So: **no current text conflates these two metrics** -- there is nothing
to fix in the paper draft as it stands today. This reads as a
pre-emptive check before that section gets written, not a fix for an
existing error, and it's worth keeping this doc around specifically so
whoever writes the Python RQ2 narrative next doesn't reach for
`fixture_type_kind`'s `"other"`/teardown numbers as if they were a
teardown-*detection* result -- they aren't; `has_teardown_pair` is (§2-4
above). For reference, the actual current live numbers (`research_questions/rq2.md`,
regenerated on demand): Python's repo-level median setup/teardown split
is 0.0%/0.0% (A) vs. 50.0%/0.0% (C), Cliff's delta V=0.371 (medium,
p<.001) -- not 0.469, and not from a chi-square/Cramer's V (RQ2 no longer
computes a pooled fixture-type_kind chi-square at all, per this file's
own rewrite -- only the repo-level Mann-Whitney/Cliff's-delta test
described in rq2.py's docstring).
