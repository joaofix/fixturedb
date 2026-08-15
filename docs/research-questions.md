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

What it covers: LOC, cyclomatic complexity, nesting depth, scope distribution, `fixture_type` distribution. `num_parameters` is still collected and shown descriptively per dataset, but is dropped from the comparative (Mann-Whitney) analysis — 0 params is the large majority in both datasets, which makes a distributional test uninformative; a floor-percentage footnote documents exactly how heavily instead. `cyclomatic_complexity` also floors heavily (CC=1 is the large majority) but stays in the comparative analysis, unlike `num_parameters`. (`num_objects_instantiated`/`num_external_calls` are still collected but not part of the paper's reported RQ1 metrics.)

The reported comparison: A vs C establishes the historical baseline — are agent-authored fixtures structurally different from a pre-LLM human baseline?

Generating the findings: `python -m collection.research_questions.rq1` computes per-dataset summary statistics for all of the above, plus an A vs C comparison (Mann-Whitney U for continuous metrics, chi-square for categorical ones), directly from `db/a.db` and `db/c_sampled.db`, and writes the results to `research_questions/rq1.md` (regenerated on demand and committed — any dataset not yet collected is skipped rather than erroring). Every comparison table has the same shape: an "Overall" row (a single pooled test, reported as an exact p-value, not BH-corrected) plus, for `loc`/`cyclomatic_complexity`/`max_nesting_depth`/`scope`/`fixture_type` (not `commit_type`), one BH-FDR-corrected row per language — each metric's 4 per-language tests are their own correction family, independent of every other metric's. Every row also reports `n_A`/`n_C`, the number of repos (not fixtures) that actually fed that specific test. Continuous metrics are repo-level throughout (one value per repo, per language for the per-language rows), not per-fixture. `fixture_type` is additionally re-tested with per-repo category proportions (Mann-Whitney U + Cliff's δ, in "Repo-level aggregates") to correct for fixtures clustering within repos — the fixture-level/per-language chi-square above treats a repo's hundreds of correlated fixtures as that many independent observations, which inflates both the chi-square statistic and Cramér's V, and isn't used in the paper. See [Limitations § Categorical Pseudo-Replication](reference/limitations.md#categorical-pseudo-replication).

## RQ2 — Setup and Teardown Characterization (Quantitative)

> How do agent-generated fixtures compare to human-written ones in setup and teardown
> provision?

What it covers: setup and teardown are detected as separate `fixture_type` values — `junit5_before_each` vs `junit5_after_each`, `before_each` vs `after_each` — and classified into a "kind" (setup/teardown/other) reusing the same type/name lookup tables `fixtures.has_teardown_pair` itself is computed from (see `rq2.py`'s module docstring). For each repo, this gives three per-repo proportions — `setup_pct`/`teardown_pct`/`other_pct` — summing to 100%.

The reported comparison (A vs C) is one table: median per-repo `setup_pct`/`teardown_pct` per language and Overall, plus one repo-level effect size and BH-FDR-corrected p-value per language. The test reuses the same repo-level-proportion approach as RQ1's `fixture_type`/RQ3's `has_mock` (Mann-Whitney U + Cliff's δ on per-repo category proportions, `compare_categorical_repo_level()` in `_shared.py`) — see [Limitations § Categorical Pseudo-Replication](reference/limitations.md#categorical-pseudo-replication). The table's single effect-size/p-value pair per row is the `setup` category's own test (`setup_pct`/`teardown_pct` aren't independent, so one test represents the row); the column is labeled "V" for consistency with the paper's other effect-size columns, but the number is Cliff's delta, not literally Cramér's V — see `rq2.py`'s module docstring for why. Overall is a single pooled test (raw p, uncorrected); each language's p is BH-FDR-corrected against the other 3 languages' `setup` tests only, with `n_A`/`n_C` repo counts per row.

A second, separate metric follows the same table: Hartigan & Hartigan's dip test for unimodality (`run_dip_test()` in `_shared.py`, the `diptest` package), run on the per-repo Python `teardown_pct` distribution — separately per dataset, since it tests whether *one* distribution is unimodal, not whether two differ. Reported with a text histogram of each distribution (`render_ascii_histogram()`; this package's reports are plain markdown with no image pipeline). Exists specifically to check whether Python's near-zero median `teardown_pct` (driven by `pytest_decorator`'s `"other"` classification — a `yield`-based fixture's real teardown is invisible to the setup/teardown/other split above even though `has_teardown_pair` does detect it, see [internal-docs/methodology-improvements/pytest-yield-teardown-vs-fixture-kind.md](../internal-docs/methodology-improvements/pytest-yield-teardown-vs-fixture-kind.md)) reflects a genuinely bimodal repo population or a smooth continuum the median alone can't reveal.

## RQ3 — Mocking (Quantitative)

> How do agent-generated and human-written fixtures differ in mock usage — prevalence,
> framework selection, and interaction depth?

What it covers: mock prevalence per fixture and per language, framework distribution, test-double `category` (dummy/stub/spy/mock/fake), and `num_interactions_configured`. This RQ is purely quantitative — the old RQ3's qualitative `target_identifier`-based target-layer coding (boundary/internal/infrastructure) has been dropped rather than reduced to a keyword heuristic.

The reported comparison asks whether mock prevalence inside fixtures has changed since the pre-LLM era (A vs C), and whether framework choice differs by author type — do agents default to the dominant framework per language, or show more diversity?

Generating the findings: `python -m collection.research_questions.rq3` computes per-dataset mock prevalence (overall and per language), framework distribution, category distribution, and interaction-depth statistics, plus an A vs C comparison, directly from `db/a.db` and `db/c_sampled.db`, and writes the results to `research_questions/rq3.md` (regenerated on demand and committed — any dataset not yet collected is skipped rather than erroring). `has_mock` reports an Overall row plus a per-language BH-FDR family (4 languages) with `n_A`/`n_C` repo counts per row (chi-square; same convention as RQ1, see its "Generating the findings" paragraph) and is additionally re-tested with per-repo proportions (Mann-Whitney U + Cliff's δ, in "Repo-level aggregates") to correct for fixtures clustering within repos — that repo-level version is what's reported in the paper, see [Limitations § Categorical Pseudo-Replication](reference/limitations.md#categorical-pseudo-replication). `num_mocks`/`num_interactions_configured` have no per-language family and render Overall-only, at both the fixture-level and repo-level basis. `framework` and `category` (test-double type) get neither a pooled nor a fixture-level per-language test at all — both are language-specific constructs (framework *names* can't overlap across languages; category *naming conventions* vary by ecosystem), so pooling either across Dataset A's TypeScript-heavy and Dataset C's Python/JavaScript-heavy mix would reflect language composition, not an authorship-era effect. `framework` is reported as a purely descriptive per-language top-3 table (no test); `category` is compared per language using the same repo-level-proportion approach (Mann-Whitney U + Cliff's δ), with each language's own 5-category family BH-FDR-corrected independently of every other language's — see rq3.py's module docstring for the full rationale.

## RQ4 — Usage Categories (Mixed — Qualitative + Quantitative)

> What categories of operations do fixtures perform, and do agent-generated fixtures
> cover the full range of fixture responsibilities that human developers produce?

What it covers: an open-coding taxonomy, positioned last so it synthesizes the picture built by RQ1–3. After establishing that agent fixtures are structurally simpler (RQ1), produce fewer teardowns (RQ2), and mock differently (RQ3), RQ4 asks whether the operational taxonomy explains those differences — are agents concentrating in certain easy categories (object factories, simple environment setup) and avoiding harder ones (stateful I/O setup, lifecycle wrappers, composite fixtures)?

---

## Summary

| RQ | Question | Type | Key Metrics | Datasets |
|----|----------|------|--------------|----------|
| RQ1 | How do agent and human fixtures compare on fundamental structural metrics? | Quantitative | `loc`, `cyclomatic_complexity`, `nesting_depth`, `scope`, `commit_type` | A vs C |
| RQ2 | How do agent and human fixtures compare in setup and teardown provision? | Quantitative | `fixture_type` kind (setup/teardown/other), per-repo setup_pct/teardown_pct | A vs C |
| RQ3 | How do agent and human fixtures differ in mock usage, framework selection, and interaction depth? | Quantitative | `num_mocks`, `framework`, `category`, `num_interactions_configured` | A vs C |
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
| `rq1.py` | RQ1 — per-dataset structural-metric summaries, plus an A vs C comparison (Mann-Whitney U / chi-square) | `db/a.db`, `db/c_sampled.db` | `research_questions/rq1.md` |
| `rq2.py` | RQ2 — per-dataset `fixture_type` kind (setup/teardown/other) distribution, plus an A vs C comparison of per-repo setup_pct/teardown_pct medians and a repo-level effect size/p-value per language | `db/a.db`, `db/c_sampled.db` | `research_questions/rq2.md` |
| `rq3.py` | RQ3 — per-dataset mock prevalence (overall and per language), framework distribution, category distribution, interaction-depth stats, plus an A vs C comparison | `db/a.db`, `db/c_sampled.db` | `research_questions/rq3.md` |
| `language_contamination.py` | Data-quality check (not tied to one RQ) — for each per-language fixture CSV, what fraction of rows carry a mismatched `language` value | `datasets/{a,c}/fixtures*/*.csv` | `research_questions/language_contamination.md` |

RQ4 has no script yet — its section above describes the intended operationalization, not yet implemented.

Dataset B (contemporary within-repo human baseline) is still collected (`db/b.db`, `paired_collection.py`) but is not part of any RQ1-3 script's reported output above.
