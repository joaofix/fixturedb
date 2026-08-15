# `mock`-category concentration: mostly real API-name matches, not a naming-convention artifact -- with one real, language-specific asymmetry (`monkeypatch`)

**Date**: 2026-08-15
**Context**: RQ3 reports `mock` as by far the largest test-double category
in both datasets (A: 10,963/14,405 = 76.1% of all mock_usages rows; C
sampled: 3,369/5,993 = 56.2%). This investigates how much of that
concentration is a real signal vs. an artifact of "mock" being the
classifier's catch-all/fallback category, and whether agent-era code's
naming habits inflate it. Investigation only, no code changes.

---

## 1. The fallback logic, and a premise correction

`_classify_mock_category()` (`detector_shared.py`) scans the fixture's
*whole body* text (not just the matched call site) against
`MOCK_CATEGORY_KEYWORDS` in priority order --
`dummy/dummies -> stub -> spy/spies -> fake -> mock` -- and returns the
first category whose term appears (case-insensitive substring), falling
back to `"mock"` if none match at all.

**Premise correction**: the request's framing ("when no keyword from
{dummy, stub, spy, fake, mock} is found ... labeled mock") conflates two
structurally different things. `mock` is not only the fallback value --
it is *also* the 5th, least-specific real category in the same priority
list (`feature_extraction_patterns.yaml`'s own comment: *""mock" ... is
listed last and doubles as the fallback when no more specific term is
found nearby -- not a special case, just the least specific term."*). So
a `category='mock'` row means one of two genuinely different things:

- **(a) Positive match**: the substring `"mock"` appears somewhere in the
  fixture body (and `dummy`/`stub`/`spy`/`fake` don't -- else it would be
  categorized as one of those instead).
- **(b) True fallback**: *none* of the 5 terms -- not even "mock" --
  appear anywhere in the body, and `_classify_mock_category()` falls
  through the whole loop to its bare `return "mock"`.

**No flag or column distinguishes these** -- `mock_usages` stores
`category`/`framework`/`raw_snippet` but nothing recording which path
produced the category. Approximated from data instead, per the request,
but exactly rather than approximately: for `category='mock'` rows
specifically, checking whether the fixture's `raw_source` contains
`"mock"` (case-insensitive) is *exact*, not approximate -- by
construction, a `category='mock'` row already ruled out
dummy/stub/spy/fake, so "does `raw_source` contain 'mock'?" fully
separates (a) from (b) with no ambiguity.

## 2. Fallback rate

| Dataset | `category='mock'` rows | Positive (contains "mock") | Fallback (contains nothing) | Fallback rate |
|---|---|---|---|---|
| A | 10,963 | 7,898 | 3,065 | **27.96%** |
| C sampled | 3,369 | 2,782 | 587 | **17.42%** |

(Distinct-fixture view, since a fixture can contribute several
`mock_usages` rows sharing one category: A -- 2,596 fixtures, 34.48%
fallback; C sampled -- 1,461 fixtures, 22.38% fallback. Same direction
either way.)

**Most of the "mock" category is a real positive match, in both
datasets** -- 72-83% depending on framing, not primarily fallback. But
the fallback share is real (17-34%), not negligible, and **the request's
predicted direction is backwards**: Dataset A's fallback rate is
*higher* than Dataset C's, not lower. §5 explains why.

## 3. Positive matches: framework API name vs. naming-only

Split using `mock_usages.raw_snippet` (the actual matched call-site text,
captured at detection time) vs. the fixture's full `raw_source`:

- **API name carries "mock"**: the matched snippet itself contains
  "mock" (`MagicMock(`, `mock.patch(`, `jest.mock(`, `vi.mock(`,
  `Mockito.mock(`, etc.) -- classification is mechanical, driven by
  which library function was called.
- **Naming-only**: "mock" is absent from the matched snippet but present
  elsewhere in the fixture body -- the call itself was something
  keyword-free (`jest.fn()`, `vi.fn()`, bare `patch()`), and only a
  *variable name* nearby (`mockClient`, `vi.mocked(...)`,
  `jest.clearAllMocks()`) supplied the term. This is the "naming
  preference" the request's critique describes.

| Dataset | n (category='mock') | API name | Naming-only | True fallback |
|---|---|---|---|---|
| A | 10,963 | 6,593 (60.14%) | 1,305 (11.90%) | 3,065 (27.96%) |
| C sampled | 3,369 | 2,335 (69.31%) | 447 (13.27%) | 587 (17.42%) |

Naming-only is a modest, fairly stable ~12-13% share in both datasets --
not the dominant driver of the concentration in either. The datasets'
real difference is almost entirely in the fallback share, not the
naming-only share.

## 4. Per-language breakdown

| Dataset | Language | n | API name | Naming-only | Fallback |
|---|---|---|---|---|---|
| A | java | 245 | 100.00% | 0.00% | 0.00% |
| A | javascript | 181 | 52.49% | 37.57% | 9.94% |
| A | python | 8,495 | 61.48% | 4.73% | **33.78%** |
| A | typescript | 2,042 | 50.44% | 40.89% | 8.67% |
| C sampled | java | 125 | 100.00% | 0.00% | 0.00% |
| C sampled | javascript | 768 | 52.21% | 14.97% | 32.81% |
| C sampled | python | 2,023 | 83.39% | 9.19% | **7.41%** |
| C sampled | typescript | 453 | 26.93% | 32.23% | **40.84%** |

Java is 100% API-name-driven in both datasets -- Mockito/EasyMock's own
call syntax always contains "Mock" literally, so there's no ambiguity to
resolve for Java at all.

**The pooled A-vs-C fallback comparison in §2 is Python-driven and
reverses for JS/TS.** Python's fallback rate is dramatically higher in A
(33.78%) than C (7.41%) -- but TypeScript's fallback rate is dramatically
*lower* in A (8.67%) than C (40.84%), and JavaScript's too (9.94% vs
32.81%). Naming-only, specifically, is *higher* in A for both JS (37.57%
vs 14.97%) and TS (40.89% vs 32.23%) -- i.e., for JS/TS specifically, the
request's original hypothesis (agent-era code names mock variables more
explicitly, producing fewer fallbacks) **is what the data shows** -- it's
just fully masked in the pooled numbers by Python moving in the opposite
direction for a different, structural reason.

## 5. Why Python's fallback rate is so much higher in Dataset A: `monkeypatch`, not naming

Broke fallback rows down by `framework`:

| Dataset | Fallback rows by framework |
|---|---|
| A | `pytest_monkeypatch`: 2,631, `unittest_mock`: 239, `vitest`: 126, `jest`: 69 |
| C sampled | `jest`: 437, `pytest_monkeypatch`: 116, `unittest_mock`: 34 |

**`pytest_monkeypatch` alone is 85.8% of Dataset A's entire fallback
bucket** (2,631/3,065), and Dataset A uses `monkeypatch` far more overall
than Dataset C does (2,977 total monkeypatch mock_usages rows in A vs.
246 in C sampled -- roughly 12x). Inspected a sample of these directly:
every one is a genuine `monkeypatch.setattr(...)`/`monkeypatch.delenv(
...)` call inside an ordinarily-named fixture (`disable_llm`,
`_ensure_clean_env`) -- real, correctly-detected patching behavior, with
no dummy/stub/spy/fake/mock-flavored identifier anywhere nearby to give
it a more specific category. This isn't a naming-style gap -- it's
**structural**: `monkeypatch`'s own API (`setattr`/`delattr`/`setenv`/
`delenv`/`setitem`/`delitem`) never contains any of the 5 category terms,
so a `monkeypatch`-only fixture can *only* avoid the fallback if some
unrelated part of its body happens to use a keyword-bearing name --
independent of how "mock-y" the naming convention is. (The same
structural gap exists for a handful of other real APIs -- `jest.fn(`,
`vi.fn(`, bare `patch(`/`patch.object(`, `sinon.replace(`,
`create_autospec(` -- none of which contain a category keyword in their
own call text either; `monkeypatch` just dominates by volume here.)

Net: **Dataset A's higher pooled fallback rate is a framework-adoption
story (agent-authored Python test setup uses `monkeypatch` much more
than Dataset C's pre-2021 corpus does), not a naming-convention story.**
The naming-convention effect the request hypothesized is real, but it's
localized to JS/TS (§4), smaller in magnitude, and runs in the opposite
direction from what drives the pooled Python number.

## 6. Assessment

- **Mechanical vs. semantic**: mostly semantic/mechanical-by-design, not
  an artifact. 60-69% of `mock`-category rows in both datasets are driven
  directly by an unambiguous framework API name (`MagicMock(`,
  `mock.patch(`, `Mockito.mock(`, etc.) -- exactly what the category
  taxonomy is meant to capture. True catch-all fallback (zero keyword
  evidence anywhere in the fixture) is real but a minority: 17-34%
  depending on dataset/framing, concentrated almost entirely in one
  Python idiom (`monkeypatch`) that the current 5-term taxonomy has no
  vocabulary for, structurally, regardless of naming style.
- **Naming-convention effect**: real but small and language-specific --
  ~12-13% of the `mock` category in both datasets is naming-only, and
  JS/TS (not Python) is where an agent-vs-human naming difference
  actually shows up in the hypothesized direction (Dataset A: fewer
  fallbacks, more naming-only positives, for JS and TS specifically).
- **Recommendation for the paper**: don't describe the `mock` category's
  size as evidence of naming-convention bias, pooled -- the pooled number
  is dominated by a Python/`monkeypatch` adoption difference between
  datasets that has nothing to do with naming. If a naming-style
  observation is worth including, scope it to JS/TS specifically, where
  it's real and in the expected direction. Separately worth noting as its
  own, distinct limitation: `monkeypatch`/`jest.fn`/`vi.fn`/bare
  `patch`/`sinon.replace`/`create_autospec` are real test-double APIs the
  5-term category taxonomy structurally can't distinguish from "no
  keyword evidence at all" -- a taxonomy gap, not a detection error (all
  of these are still correctly *detected* as mocks; only their *category*
  defaults to the least-specific term).
