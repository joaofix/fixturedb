# Java `@Rule`/`@ClassRule`: excluded from LOC/CC/nesting comparisons

**Date**: 2026-08-14
**Context**: `@Rule`/`@ClassRule` (`detector_java.py`) are the only fixture_types in
any language this project extracts from that are detected on a
`field_declaration`, not a method/function. This document records the
investigation into whether that breaks their structural metrics, and the fix.

---

## 1. Problem

Every metric on a `FixtureResult` (`loc`, `cyclomatic_complexity`,
`max_nesting_depth`, `num_parameters`) is defined in terms of "the fixture's
function body." `@Rule`/`@ClassRule` have no function body — a typical
instance is a one-line field:

```java
@Rule
public ExpectedException thrown = ExpectedException.none();
```

The question: what do Lizard (which drives `cyclomatic_complexity`/
`num_parameters`) and the custom AST nesting-depth traversal actually return
for a node like this, and does it distort RQ1's Java LOC/CC/nesting
comparison?

## 2. What Lizard actually does

Tested directly against `lizard.analyze_file()` with four representative
snippets (plain `@Rule`, `@ClassRule`, and one with a ternary in the
initializer, to check whether *any* branching gets picked up): **`function_list`
came back empty in all four cases.** A field declaration has no
function/method syntax for Lizard to find — this is structural, not
occasional. `analyze_function_complexity()` (`complexity_provider.py`) only
overwrites its defaults inside `if result.function_list:`; for these
fixtures that block never runs, so `cyclomatic_complexity`/`num_parameters`
are always its hardcoded defaults (1 and 0) — never a real measurement.

`loc` is unaffected (computed independently via non-blank line count of the
real source text, not via Lizard) and `num_objects_instantiated` is
unaffected too -- as of 2026-08-16 it's an independent tree-sitter AST
walk directly on the fixture's own already-parsed node
(`detector_shared.py::_count_object_instantiations()`), not routed
through Lizard at all (previously: an independent regex pass, not gated
on Lizard's function count -- same conclusion, different mechanism; see
internal-docs/methodology-improvements/
num-objects-instantiated-false-positive-rate.md).

## 3. What the nesting-depth traversal does

`_compute_nesting_depth()` starts at `max_depth = 1` and only increments on
control-flow node types found anywhere in the subtree. A plain field
declaration has none, so it correctly floors at 1 -- the same floor any
simple, branch-free *method* fixture also gets. Not a special case, not
broken.

## 4. A second, rarer failure mode

Querying `db/c.db`, 38 of 8,688 `@Rule`/`@ClassRule` fixtures (0.4%) have
`cyclomatic_complexity != 1`. Inspecting them: real JUnit code sometimes puts
an **anonymous inner class** in the initializer, overriding `before()`/
`after()`-style methods with genuine branching (e.g. a `TestWatcher`
subclass). Lizard *does* find functions there, but picks up
`result.function_list[0]` — whichever inner method happens first — and
reports only *that one method's* complexity as the whole fixture's,
ignoring any sibling overridden methods, and inconsistent with `loc`, which
correctly spans the entire multi-method block. Left as-is: too rare (0.4% of
one fixture_type, 0/114 in Dataset A) to justify its own fix given the
exclusion below already removes these fixtures from the comparisons where it
would matter.

## 5. Scale

| | Dataset A | Dataset C |
|---|---|---|
| `@Rule`/`@ClassRule` share of Java fixtures | 114/1,209 (9.4%) | 8,688/76,557 (11.3%) |
| their `loc` median vs other Java fixtures | 2.00 vs 6.00 | 2.00 vs 7.00 |
| their `cyclomatic_complexity == 1` rate vs other Java fixtures | 100.0% vs 84.0% | 99.6% vs 88.4% |

Median CC is unaffected either way (1.00 in every group -- already the
majority value everywhere). `loc` is where it actually matters: a real
~3x pull on Java's pooled LOC distribution, not from measurement error but
because a field declaration and a method body aren't the same kind of unit.

## 6. Fix chosen

Excluded `{"junit_rule", "junit_class_rule"}` from RQ1's `loc`/
`cyclomatic_complexity`/`max_nesting_depth` comparisons (repo-level and
per-language), both datasets, while keeping them in `fixture_type`/`scope`
categorical distributions -- "this repo declared N JUnit Rules" is still a
meaningful, correctly-measured fact.

Two options were considered:

- **(a)** Filter directly in `rq1.py` before computing stats.
- **(b)** Add a `has_no_body` column to the `fixtures` table, set at
  extraction time, so any script filters consistently without knowing the
  specific fixture_type strings.

Went with a hybrid: (a)'s no-schema-change, no-re-collection approach, but
the fixture_type set lives as one named constant
(`_shared.py::NO_BODY_FIXTURE_TYPES`) instead of inline in `rq1.py`, so a
future script gets (b)'s actual goal -- consistent downstream filtering --
without a migration + backfill across every already-collected DB. If a
DB-level marker (discoverable outside these scripts, e.g. by someone
querying the DB directly) is ever worth the migration cost, `has_no_body`
is the fallback design, already scoped above.
