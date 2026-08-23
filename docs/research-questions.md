# Research Questions

FixtureDB addresses four research questions, comparing agent-authored fixtures
(Dataset A) against pre-LLM human-authored fixtures from an independent repository
pool (Dataset C) -- the RQ1-3 scripts' reported comparison is A vs C. A contemporary
human-authored baseline from the same repositories (Dataset B) is also collected, but
isn't part of these scripts' reported output. See
[Database Schema](architecture/database-schema.md) for the underlying tables and
[Dataset Card](data/dataset-card.md) for corpus composition.

---

## RQ1 — General Metrics Overview (Quantitative)

> How do agent-generated and human-written fixtures compare across structural metrics?

What it covers: LOC, cyclomatic complexity, comment density, nesting depth, scope distribution, `fixture_type` distribution. **Two tiers, continuous metrics only** (since 2026-08-17): `PAPER_CONTINUOUS_METRICS` — exactly `loc`, `cyclomatic_complexity`, `comment_density` — is the exhaustive set of continuous metrics reported in the paper, and `rq1.md` labels them explicitly as "Paper Metrics." Every other continuous metric this script computes (`max_nesting_depth`, `num_parameters`) is still shown — `max_nesting_depth` gets the identical Mann-Whitney/per-language treatment as the paper metrics, `num_parameters` gets only a descriptive floor-percentage footnote (0 params is the large majority in both datasets, which makes a distributional test uninformative) — but renders under a separate "Other Extracted Features (Not in the Paper)" heading so a reader can't mistake "this script reports it" for "the paper reports it." `cyclomatic_complexity` also floors heavily (CC=1 is the large majority) but stays in the comparative analysis, unlike `num_parameters`. This tiering is continuous-metrics-only — `scope`/`fixture_type`/`commit_type` (categorical) already have their own separate paper/non-paper framing below, and `num_objects_instantiated`/`num_external_calls` are still collected but excluded from RQ1 entirely (not even in the "Other" tier), not part of any reported set.

The reported comparison: A vs C establishes the historical baseline — are agent-authored fixtures structurally different from a pre-LLM human baseline?

Generating the findings: `python -m collection.research_questions.rq1` computes per-dataset summary statistics for all of the above, plus an A vs C comparison (Mann-Whitney U for continuous metrics, chi-square for categorical ones), directly from `db/a.db` and `db/c.db`, and writes the results to `research_questions/rq1.md` (regenerated on demand and committed — any dataset not yet collected is skipped rather than erroring). Every comparison table has the same shape: an "Overall" row (a single pooled test, reported as an exact p-value, not BH-corrected) plus, for `loc`/`cyclomatic_complexity`/`comment_density`/`max_nesting_depth`/`scope`/`fixture_type` (not `commit_type`), one BH-FDR-corrected row per language — each metric's 4 per-language tests are their own correction family, independent of every other metric's. Every row also reports `n_A`/`n_C`, the number of repos (not fixtures) that actually fed that specific test. Continuous metrics are repo-level throughout (one value per repo, per language for the per-language rows), not per-fixture. `fixture_type` is additionally re-tested with per-repo category proportions (Mann-Whitney U + Cliff's δ, in "Repo-level aggregates") to correct for fixtures clustering within repos — the fixture-level/per-language chi-square above treats a repo's hundreds of correlated fixtures as that many independent observations, which inflates both the chi-square statistic and Cramér's V, and isn't used in the paper. See [Limitations § Categorical Pseudo-Replication](reference/limitations.md#categorical-pseudo-replication).

## RQ2 — Setup and Teardown Characterization (Quantitative)

> How do agent-generated fixtures compare to human-written ones in setup and teardown
> provision?

What it covers: setup and teardown are detected as separate `fixture_type` values — `junit5_before_each` vs `junit5_after_each`, `before_each` vs `after_each` — and classified into a "kind" (setup/teardown/other) reusing the same type/name lookup tables `fixtures.has_teardown_pair` itself is computed from (see `rq2.py`'s module docstring).

Two reported tables (A vs C), replacing an earlier single median-proportion table:
- **Table 1 (fixture counts)**: purely descriptive, no statistics — the raw count of setup-classified and teardown-classified fixtures per language and Total ("other"-classified fixtures excluded from both columns).
- **Table 2 (teardown coverage)**: the inferential table. For each repo, a binary indicator — does it have at least one teardown-classified fixture at all? — compared between datasets with Mann-Whitney U + Cliff's δ on that 0/1 indicator (the same repo-level-proportion machinery RQ1's `fixture_type`/RQ3's `has_mock` use, `compute_continuous_balance()` in `between_group_comparison.py` — see [Limitations § Categorical Pseudo-Replication](reference/limitations.md#categorical-pseudo-replication)). "Coverage A/C (%)" is the share of repos with the indicator at 1 (the mean of a 0/1 list *is* that percentage). Overall is a single pooled test (raw p, uncorrected); each language's p is BH-FDR-corrected against the other 3 languages' tests only, with `n_A`/`n_C` repo counts per row.

Generating the findings: `python -m collection.research_questions.rq2` computes both tables directly from `db/a.db` and `db/c.db`, and writes the results to `research_questions/rq2.md` (regenerated on demand and committed — any dataset not yet collected is skipped rather than erroring).

Supplementary (not part of either table, rendered in its own "Supplementary Analyses" section since it may still be cited in prose): Hartigan & Hartigan's dip test for unimodality (`run_dip_test()` in `_shared.py`, the `diptest` package), run on the per-repo Python `teardown_pct` *proportion* distribution (continuous, distinct from Table 2's binary coverage indicator) — separately per dataset, since it tests whether *one* distribution is unimodal, not whether two differ. Reported with a text histogram of each distribution (`render_ascii_histogram()`; this package's reports are plain markdown with no image pipeline). Exists specifically to check whether Python's near-zero median `teardown_pct` (driven by `pytest_decorator`'s `"other"` classification — a `yield`-based fixture's real teardown is invisible to the setup/teardown/other split above even though `has_teardown_pair` does detect it, see [internal-docs/methodology-improvements/pytest-yield-teardown-vs-fixture-kind.md](../internal-docs/methodology-improvements/pytest-yield-teardown-vs-fixture-kind.md)) reflects a genuinely bimodal repo population or a smooth continuum the median alone can't reveal.

## RQ3 — Mocking (Quantitative)

> How do agent-generated and human-written fixtures differ in mock usage — coverage
> and intensity?

What it covers: `num_mocks` (mock calls per fixture) and `num_interactions_configured` (continuous, unchanged), plus one paper table combining two repo-level metrics derived from `num_mocks`: **mocking coverage** (does a repo have >=1 fixture with a mock at all?) and **mocking intensity** (among repos that do mock, the median mock-call count across that repo's own mocking fixtures). This RQ is purely quantitative — the old RQ3's qualitative `target_identifier`-based target-layer coding (boundary/internal/infrastructure) has been dropped rather than reduced to a keyword heuristic.

The reported comparison asks whether repos mock at all more or less often since the pre-LLM era (Coverage, A vs C), and, among repos that do mock, how heavily (Intensity, A vs C).

Generating the findings: `python -m collection.research_questions.rq3` computes both metrics directly from `db/a.db` and `db/c.db`, and writes the results to `research_questions/rq3.md` (regenerated on demand and committed — any dataset not yet collected is skipped rather than erroring). Both are repo-level, Mann-Whitney U + Cliff's δ, per language and Overall — Coverage on a per-repo binary has-any-mock indicator (population: every repo with >=1 fixture, of that language for the per-language rows; "Coverage A/C (%)" is the mean of that 0/1 indicator), Intensity on the per-repo median mock-call count among only that repo's mocking fixtures (population: repos where Coverage = 1 — a strict subset of Coverage's own population, so the table's single `n_A`/`n_C` per row reflects Coverage's population, not Intensity's smaller true n). Overall is two single pooled tests (raw p, uncorrected); each language's coverage AND intensity tests (8 tests: 4 languages × 2 metrics) are BH-FDR-corrected together as **one combined family**, not two separate 4-test families, since both are RQ3 metrics reported in the same table — see rq3.py's module docstring for the full rationale, including why this table replaced three previously-reported ones (fixture-level mock prevalence, framework distribution, test-double category distribution). The fixture-level `has_mock` chi-square is kept (mock detection logic unchanged) but moved to a "Legacy" section, not used in the paper — see [Limitations § Categorical Pseudo-Replication](reference/limitations.md#categorical-pseudo-replication). `framework`/`category` raw data (`mock_usages.framework`/`category`) is still fetched and available on `DatasetMetrics` for programmatic use, but no longer rendered as a report table — both are language-specific constructs (framework *names* can't overlap across languages; category *naming conventions* vary by ecosystem), so a pooled A-vs-C view was already confounded by each dataset's different language mix.

## RQ4 — Usage Categories (Mixed — Qualitative + Quantitative)

> What categories of operations do fixtures perform, and do agent-generated fixtures
> cover the full range of fixture responsibilities that human developers produce?

What it covers: an open-coding taxonomy, positioned last so it synthesizes the picture built by RQ1–3. After establishing that agent fixtures are structurally simpler (RQ1), produce fewer teardowns (RQ2), and mock differently (RQ3), RQ4 asks whether the operational taxonomy explains those differences — are agents concentrating in certain easy categories (object factories, simple environment setup) and avoiding harder ones (stateful I/O setup, lifecycle wrappers, composite fixtures)?

---

## Summary

| RQ | Question | Type | Key Metrics | Datasets |
|----|----------|------|--------------|----------|
| RQ1 | How do agent and human fixtures compare on fundamental structural metrics? | Quantitative | Paper: `loc`, `cyclomatic_complexity`, `comment_density`. Also reported (not in paper): `max_nesting_depth`, `num_parameters`, `scope`, `commit_type` | A vs C |
| RQ2 | How do agent and human fixtures compare in setup and teardown provision? | Quantitative | `fixture_type` kind (setup/teardown/other): absolute fixture counts by type, per-repo teardown coverage rate | A vs C |
| RQ3 | How do agent and human fixtures differ in mock usage? | Quantitative | Mocking coverage (% repos with any mock) and intensity (median mock calls per mocking fixture), `num_interactions_configured` | A vs C |
| RQ4 | What operations do fixtures perform, and do agents cover the full range of human fixture responsibilities? | Mixed | `category` (manual label), `fixture_type`, `scope` | A vs C |

---

## Scripts

[collection/research_questions/](../collection/research_questions/) holds the scripts that
compute paper results directly from collected data and write a findings report to
`research_questions/` at the repo root (regenerated on demand and committed — a dataset
not yet collected is skipped rather than erroring). Each is standalone:
`python -m collection.research_questions.<module>`.

| Script | Answers | Reads | Writes |
|---|---|---|---|
| `rq1.py` | RQ1 — per-dataset structural-metric summaries, plus an A vs C comparison (Mann-Whitney U / chi-square) | `db/a.db`, `db/c.db` | `research_questions/rq1.md` |
| `rq2.py` | RQ2 — per-dataset `fixture_type` kind (setup/teardown/other) distribution, plus two A vs C tables: absolute setup/teardown fixture counts by language, and per-repo teardown coverage rate with a repo-level effect size/p-value per language | `db/a.db`, `db/c.db` | `research_questions/rq2.md` |
| `rq3.py` | RQ3 — per-dataset mocking summary, plus one A vs C paper table (mocking coverage % and intensity, per language) and a legacy fixture-level mock-prevalence section | `db/a.db`, `db/c.db` | `research_questions/rq3.md` |
| `language_contamination.py` | Data-quality check (not tied to one RQ) — for each per-language fixture CSV, what fraction of rows carry a mismatched `language` value | `datasets/{a,c}/fixtures*/*.csv` | `research_questions/language_contamination.md` |

RQ4 has no script yet — its section above describes the intended operationalization, not yet implemented.

Dataset B (contemporary within-repo human baseline) is still collected (`db/b.db`, `paired_collection.py`) but is not part of any RQ1-3 script's reported output above.
