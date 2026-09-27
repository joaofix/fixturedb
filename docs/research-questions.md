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

What it covers: LOC, cyclomatic complexity, comment density, `fixture_type` distribution. **Three paper continuous metrics, final** (as of 2026-09-26): `PAPER_CONTINUOUS_METRICS` — exactly `loc`, `cyclomatic_complexity`, `comment_density` — is now also the exhaustive set this script computes and tests at all; `rq1.md` labels them "Paper Metrics." `num_parameters` is still shown descriptively (a floor-percentage footnote only — 0 params is the large majority in both datasets, which makes a distributional test uninformative) under a separate "Other Extracted Features (Not in the Paper)" heading. `cyclomatic_complexity` also floors heavily (CC=1 is the large majority) but stays in the comparative analysis, unlike `num_parameters`. `max_nesting_depth`, `num_objects_instantiated`, `num_external_calls`, `has_teardown_pair`, `scope`, `framework`, and `commit_type` were removed from the extracted metric set entirely (not part of any reported set, in this RQ or any other) — `scope`/`framework` were fully redundant with `fixture_type` (1:1 mapping verified across the collected data), `commit_type` (a Conventional Commits classification of the originating commit, along with the `conventional_commits.py` module that computed it) was never used in any reported RQ, and the other three simply aren't part of the paper's reported metrics.

The reported comparison: A vs C establishes the historical baseline — are agent-authored fixtures structurally different from a pre-LLM human baseline?

Generating the findings: `python -m collection.research_questions.rq1` computes per-dataset summary statistics for all of the above, plus an A vs C comparison (Mann-Whitney U for continuous metrics), directly from `db/a.db` and `db/c.db`, and writes the results to `research_questions/rq1.md` (regenerated on demand and committed — any dataset not yet collected is skipped rather than erroring). Every continuous-metric comparison table has the same shape: an "Overall" row (a single pooled test, reported as an exact p-value, not BH-corrected) plus, for `loc`/`cyclomatic_complexity`/`comment_density`, one BH-FDR-corrected row per language — each metric's 4 per-language tests are their own correction family, independent of every other metric's. Every row also reports `n_A`/`n_C`, the number of repos (not fixtures) that actually fed that specific test. Continuous metrics are repo-level throughout (one value per repo, per language for the per-language rows), not per-fixture. `fixture_type` has no A vs C comparison of any kind — its fixture-level/per-language chi-square (which would have treated a repo's hundreds of correlated fixtures as that many independent observations, inflating both the chi-square statistic and Cramér's V) and its repo-level category-proportion test (Mann-Whitney U + Cliff's δ, formerly "Repo-level aggregates") were both never used in the paper and were removed entirely (2026-09-27), rather than kept unused. Only `fixture_type`'s per-dataset descriptive distribution remains, purely as a support column for `fixture_role` classification (see `rq2.py`'s module docstring). See [Limitations § Categorical Pseudo-Replication](reference/limitations.md#categorical-pseudo-replication).

## RQ2 — Setup and Teardown Characterization (Quantitative)

> How do agent-generated fixtures compare to human-written ones in setup and teardown
> provision?

What it covers: setup and teardown are detected as separate `fixture_type` values — `junit5_before_each` vs `junit5_after_each`, `before_each` vs `after_each` — and classified into a `fixture_role` (setup/teardown/other) via the same type/name lookup tables (see `rq2.py`'s module docstring). `has_teardown_pair`, a separate binary indicator that used to exist alongside `fixture_role`, was removed from the extracted metric set entirely.

Two reported tables (A vs C), replacing an earlier single median-proportion table:
- **Table 1 (fixture counts)**: purely descriptive, no statistics — the raw count of setup-classified and teardown-classified fixtures per language and Total ("other"-classified fixtures excluded from both columns).
- **Table 2 (teardown coverage)**: for each repo, a binary indicator — does it have at least one teardown-classified fixture at all? "Coverage A/C (%)" is the share of repos with the indicator at 1 (the mean of a 0/1 list *is* that percentage), with `n_A`/`n_C` repo counts per row. Purely descriptive — no statistical test (removed 2026-09-27, alongside RQ3's Coverage/Intensity test and Intensity metric entirely: RQ1 is now the only script in this package that performs BH-FDR correction — see [internal-docs/methodology-improvements/bh-fdr-correction-families.md](../internal-docs/methodology-improvements/bh-fdr-correction-families.md) for the full inventory).

Generating the findings: `python -m collection.research_questions.rq2` computes both tables directly from `db/a.db` and `db/c.db`, and writes the results to `research_questions/rq2.md` (regenerated on demand and committed — any dataset not yet collected is skipped rather than erroring).

A supplementary "Setup Coverage by Repository" table (the setup analogue of Table 2) and a Hartigan & Hartigan unimodality (dip test) check on Python's `teardown_pct` distribution were both computed here but never part of either paper table; both were removed entirely (2026-09-27) after review confirmed neither fed the paper -- see `rq2.py`'s module docstring for the one real finding the setup-coverage table had turned up (a significant per-language gap in Java) before removal. Removing the dip test also dropped the `diptest` package as a project dependency.

## RQ3 — Mocking (Quantitative)

> How do agent-generated and human-written fixtures differ in mock usage — coverage?

What it covers: `num_mocks` (mock calls per fixture), plus one paper table reporting a single repo-level metric derived from it: **mocking coverage** — does a repo have >=1 fixture with a mock at all? This RQ is purely quantitative — the old RQ3's qualitative `target_identifier`-based target-layer coding (boundary/internal/infrastructure) has been dropped rather than reduced to a keyword heuristic. `num_interactions_configured` (a separate `mock_usages` column estimating how many interactions were configured on a mock) was never one of the paper's reported metrics and was removed from the extracted metric set entirely (2026-09-26). **Mocking intensity** (among repos that do mock, the median mock-call count across that repo's own mocking fixtures) was reported alongside Coverage for a time, then removed entirely (2026-09-27) — no longer one of the paper's reported metrics.

The reported comparison asks whether repos mock at all more or less often since the pre-LLM era (Coverage, A vs C).

Generating the findings: `python -m collection.research_questions.rq3` computes Coverage directly from `db/a.db` and `db/c.db`, and writes the results to `research_questions/rq3.md` (regenerated on demand and committed — any dataset not yet collected is skipped rather than erroring). Coverage is repo-level: a per-repo binary has-any-mock indicator (population: every repo with >=1 fixture, of that language for the per-language rows), with "Coverage A/C (%)" the mean of that 0/1 indicator and `n_A`/`n_C` repo counts per row. Purely descriptive — no statistical test (removed 2026-09-27, alongside RQ2's Table 2 test and Intensity entirely: RQ1 is now the only script in this package that performs BH-FDR correction — see [internal-docs/methodology-improvements/bh-fdr-correction-families.md](../internal-docs/methodology-improvements/bh-fdr-correction-families.md) for the full inventory). This table replaced three previously-reported ones (fixture-level mock prevalence, framework distribution, test-double category distribution) — see rq3.py's module docstring for the full history. The fixture-level `has_mock` chi-square was kept for a time in a "Legacy" section (mock detection logic unchanged, but never used in the paper), then removed entirely (2026-09-27) — see [Limitations § Categorical Pseudo-Replication](reference/limitations.md#categorical-pseudo-replication). `framework`/`category` raw data (`mock_usages.framework`/`category`) is still fetched and available on `DatasetMetrics` for programmatic use, but no longer rendered as a report table — both are language-specific constructs (framework *names* can't overlap across languages; category *naming conventions* vary by ecosystem), so a pooled A-vs-C view was already confounded by each dataset's different language mix.

## RQ4 — Usage Categories (Mixed — Qualitative + Quantitative)

> What categories of operations do fixtures perform, and do agent-generated fixtures
> cover the full range of fixture responsibilities that human developers produce?

What it covers: an open-coding taxonomy, positioned last so it synthesizes the picture built by RQ1–3. After establishing that agent fixtures are structurally simpler (RQ1), produce fewer teardowns (RQ2), and mock differently (RQ3), RQ4 asks whether the operational taxonomy explains those differences — are agents concentrating in certain easy categories (object factories, simple environment setup) and avoiding harder ones (stateful I/O setup, lifecycle wrappers, composite fixtures)?

---

## Summary

| RQ | Question | Type | Key Metrics | Datasets |
|----|----------|------|--------------|----------|
| RQ1 | How do agent and human fixtures compare on fundamental structural metrics? | Quantitative | Paper: `loc`, `cyclomatic_complexity`, `comment_density`. Also reported (not in paper): `num_parameters`, `fixture_type` | A vs C |
| RQ2 | How do agent and human fixtures compare in setup and teardown provision? | Quantitative | `fixture_role` (setup/teardown/other): absolute fixture counts by type, per-repo teardown coverage rate | A vs C |
| RQ3 | How do agent and human fixtures differ in mock usage? | Quantitative | Mocking coverage (% repos with any mock) | A vs C |
| RQ4 | What operations do fixtures perform, and do agents cover the full range of human fixture responsibilities? | Mixed | `category` (manual label), `fixture_type` | A vs C |

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
| `rq2.py` | RQ2 — per-dataset `fixture_type` kind (setup/teardown/other) distribution, plus two A vs C tables: absolute setup/teardown fixture counts by language, and per-repo teardown coverage rate by language (both purely descriptive) | `db/a.db`, `db/c.db` | `research_questions/rq2.md` |
| `rq3.py` | RQ3 — per-dataset mocking summary, plus one A vs C paper table (mocking coverage %, per language, purely descriptive) | `db/a.db`, `db/c.db` | `research_questions/rq3.md` |
| `language_contamination.py` | Data-quality check (not tied to one RQ) — for each per-language fixture CSV, what fraction of rows carry a mismatched `language` value | `datasets/{a,c}/fixtures*/*.csv` | `research_questions/language_contamination.md` |

RQ4 has no script yet — its section above describes the intended operationalization, not yet implemented.

Dataset B (contemporary within-repo human baseline) is still collected (`db/b.db`, `paired_collection.py`) but is not part of any RQ1-3 script's reported output above.
