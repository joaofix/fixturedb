# BH-FDR correction: complete family inventory

**Date**: 2026-09-27
**Context**: reference documentation, written after a session-long pass
removing every RQ1-3 table/computation confirmed unused in the paper,
ending in a drastic, explicit simplification: **RQ1 is now the only
script in this package that performs BH-FDR correction at all.** RQ2 and
RQ3 were simplified in the paper to report plain descriptive percentages
for their coverage tables, with no statistical test backing them, so
there is nothing left to correct there. This documents the complete,
final state of every Benjamini-Hochberg correction family this pipeline
computes. No code changes here -- descriptive only.

Earlier in the same session, before this final simplification, RQ2's
Table 2 and RQ3's Coverage/Intensity table each still ran their own
Mann-Whitney U + BH-FDR per-language family (and, before that, an even
larger set of now-removed tables -- `num_interactions_configured`,
`category_by_language`/`category_by_repo_and_language`, RQ2's Setup
Coverage table, RQ2's Hartigan dip test, `commit_type`, `fixture_type`'s
fixture-level chi-square, RQ3's Legacy `has_mock` chi-square -- also had
their own families). All of that is gone now, along with RQ3's Intensity
metric entirely (removed, not just its test).

---

## What problem BH-FDR solves

Every RQ script runs many hypothesis tests per report. At an uncorrected
alpha=0.05, the more tests you run, the more "significant" results
you'd expect to see purely by chance. Benjamini-Hochberg controls the
*false discovery rate* -- the expected proportion of false positives
among the tests flagged significant -- which is why this project uses
it instead of Bonferroni (family-wise error control): Bonferroni is
needlessly conservative for many related, non-independent tests like
these (the same metric across 4 languages is not 4 independent
experiments).

## Mechanism

One function, `apply_fdr_correction()` in
`collection/research_questions/_shared.py`:

- Wraps scipy's `false_discovery_control(p_values, method="bh")`.
- Takes a `dict[str, BalanceTest]` -- that dict *is* the family.
  Whatever keys are passed in together get corrected together; nothing
  outside that dict is touched.
- Returns new `BalanceTest`s with `adjusted_p_value`/
  `significant_after_correction` added to `details`, alongside the
  untouched raw `p_value`/`is_balanced` -- both raw and corrected
  verdicts stay visible in every rendered table.
- **Exclusion rule**: a test with `reason == "insufficient_data"` or
  `"error" in details` is left out of the correction entirely (passes
  through unchanged, no `adjusted_p_value`) -- it was never really
  "tested," so there's nothing to correct.
- **One deliberate non-exclusion**: `reason == "identical_distributions"`
  (both sides collapse to one equal value) *is* still corrected -- it's
  a real computed result (p=1.0 via a shortcut past Mann-Whitney, not a
  placeholder), so it stays in the family.

As of this simplification, `apply_fdr_correction()` has exactly two
callers left in the whole package: RQ1's per-language continuous-metric
families (via the shared `render_comparison_table()`) and `balance.py`'s
3-variable control check. Nothing in rq2.py or rq3.py calls it anymore.

## Universal convention: the Overall row is never corrected

Every comparison table has one pooled "Overall" row (all repos/fixtures
regardless of language) plus, where a per-language breakdown exists,
several more rows. Overall's raw p-value is reported as-is -- a single
pooled test needs no multiple-comparison correction. Only the breakdown
rows form a "family."

## Every family currently computed

| Script | Table | Family members | Size |
|---|---|---|---|
| RQ1 | `loc` | 4 languages | 4 |
| RQ1 | `cyclomatic_complexity` | 4 languages | 4 |
| RQ1 | `comment_density` | 4 languages | 4 |
| RQ1 | `fixture_type` (Repo-level aggregates -- the paper's actual result) | fixture_type categories (union observed in `db/a.db`+`db/c.db`) | 35 |
| `balance.py` | Control-variable balance (A vs C) | `language`, `domain`, `repo_age_years` | 3 |

That's it -- 5 families total, all in RQ1 or the non-RQ `balance.py`
validity check. RQ2 and RQ3 compute zero BH-FDR families.

## RQ1's `fixture_type` family is a different *kind*, not just a different size

The three continuous metrics above are **by-language** families: the
same statistical question asked once per language, always exactly 4
members, via the shared `render_comparison_table()`.

`fixture_type`'s repo-level test is a **by-category** family instead:
the same question asked once per *value* of the variable itself --
`pytest_decorator` vs `unittest_setup` vs `junit5_before_each`, etc. --
via a different function, `compare_categorical_repo_level()`/
`render_categorical_repo_level_table()`. Its family size is **not
fixed** -- it's the union of distinct `fixture_type` values observed on
either side, confirmed against the real data to currently be **35**,
not 4. A 35-test family behaves very differently under BH-FDR than a
4-test one (the correction is much less punishing per-test as the
family grows), worth being explicit about if this number ever gets
cited in the paper's methodology.

## RQ2 and RQ3's coverage tables: plain percentages, no test

Both tables render `n_A`/`n_C` plus a coverage percentage per side
(the mean of a per-repo 0/1 indicator -- does this repo have >=1
qualifying fixture at all?), per language and Overall. No statistic, no
effect size, no p-value, no correction of any kind:

- **RQ2 Table 2** (`tab:rq2-coverage`, teardown coverage).
- **RQ3's paper table** (`Mocking Coverage`) -- Intensity (median mock
  count among mocking repos) was removed entirely alongside the test,
  not just de-tested.

## What's not corrected at all

- Every Overall row, everywhere (single pooled test, by design).
- RQ2 and RQ3's coverage percentages (no test to begin with).
- `balance.py`'s comparison is A-vs-C only (Dataset B dropped from its
  reported output) -- its 3-test family doesn't grow with a third
  dataset.
- Anything purely descriptive (per-dataset distribution tables, RQ2's
  Table 1, RQ3's Mock Fixture Counts table, the Fixture Kind
  Classification Coverage table) -- no test, so no correction question
  even arises.
