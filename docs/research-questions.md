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

What it covers: LOC, cyclomatic complexity, nesting depth, `num_parameters`, scope distribution, `fixture_type` distribution. This is the baseline characterization that grounds everything else — it answers whether agent fixtures are bigger or smaller, simpler or more complex, more or less parameterized than human ones. (`num_objects_instantiated`/`num_external_calls` are still collected but not part of the paper's reported RQ1 metrics.)

The reported comparison: A vs C establishes the historical baseline — are agent-authored fixtures structurally different from a pre-LLM human baseline?

Generating the findings: `python -m collection.research_questions.rq1` computes per-dataset summary statistics for all of the above, plus an A vs C comparison (Mann-Whitney U for continuous metrics, chi-square for categorical ones), directly from `db/a.db` and `db/c_sampled.db`, and writes the results to `research_questions/rq1.md` (gitignored, regenerated on demand — any dataset not yet collected is skipped rather than erroring). Every comparison table has the same shape: an "Overall" row (a single pooled test, reported as an exact p-value, not BH-corrected) plus, for `loc`/`cyclomatic_complexity`/`max_nesting_depth`/`num_parameters`/`scope`/`fixture_type` (not `commit_type`), one BH-FDR-corrected row per language — each metric's 4 per-language tests are their own correction family, independent of every other metric's. Every row also reports `n_A`/`n_C`, the number of repos (not fixtures) that actually fed that specific test. Continuous metrics are repo-level throughout (one value per repo, per language for the per-language rows), not per-fixture. `fixture_type` is additionally re-tested with per-repo category proportions (Mann-Whitney U + Cliff's δ, in "Repo-level aggregates") to correct for fixtures clustering within repos — the fixture-level/per-language chi-square above treats a repo's hundreds of correlated fixtures as that many independent observations, which inflates both the chi-square statistic and Cramér's V, and isn't used in the paper. See [Limitations § Categorical Pseudo-Replication](reference/limitations.md#categorical-pseudo-replication).

## RQ2 — Setup and Teardown Characterization (Quantitative)

> How do agent-generated fixtures compare to human-written ones in setup and teardown
> provision?

What it covers: this is the cleanest new angle, and it's already measurable from the existing schema. Setup and teardown are detected as separate `fixture_type` values — `junit5_before_each` vs `junit5_after_each`, `before_each` vs `after_each` — and `fixtures.has_teardown_pair` flags whether a setup-side fixture has matching cleanup logic, computed per language via `_calculate_teardown_pairs()` ([detector_shared.py](../collection/detector_shared.py)): a yield statement (pytest), a same-type setup/teardown name pair (unittest, including `addCleanup`/`enterContext` self-registered cleanup), a different-type setup/teardown pair by scope (JUnit/TestNG/JS), or an always-true case for mechanisms that guarantee teardown by construction (JUnit `@Rule`/`@ClassRule`, Vitest `aroundEach`/`aroundAll`). Per repo, the ratio of setup fixtures to teardown fixtures can be computed: a balanced ratio approaching 1:1 suggests disciplined lifecycle management, while a heavily setup-skewed ratio (many befores, few afters) suggests teardown is being neglected.

This operationalization requires no new AST work — `fixture_type` and `has_teardown_pair` already capture it completely. Pairing is intra-file only: a setup fixture's teardown counterpart in a different file, e.g. inherited from a Java base test class, isn't detected.

The reported comparison asks whether teardown discipline is better or worse in agent-authored fixtures than in the pre-LLM human baseline (A vs C). Key metrics: `fixture_type` (setup vs teardown variants), `has_teardown_pair`, and the setup-to-teardown ratio per repo and per language. `fixture_type_kind` (setup/teardown/other), the setup-to-teardown ratio, and the no-teardown-repo rate each report an Overall row plus a per-language BH-FDR family (4 languages, corrected independently per metric), with `n_A`/`n_C` repo counts per row — same convention as RQ1, see its "Generating the findings" paragraph. The setup/teardown/other kind distribution is additionally re-tested with per-repo category proportions (Mann-Whitney U + Cliff's δ, in "Repo-level aggregates") for the same repo-clustering reason as RQ1's `fixture_type` — see [Limitations § Categorical Pseudo-Replication](reference/limitations.md#categorical-pseudo-replication).

## RQ3 — Mocking (Quantitative)

> How do agent-generated and human-written fixtures differ in mock usage — prevalence,
> framework selection, and interaction depth?

What it covers: mock prevalence per fixture and per language, framework distribution, test-double `category` (dummy/stub/spy/mock/fake), and `num_interactions_configured`. This RQ is purely quantitative — the old RQ3's qualitative `target_identifier`-based target-layer coding (boundary/internal/infrastructure) has been dropped rather than reduced to a keyword heuristic.

The reported comparison asks whether mock prevalence inside fixtures has changed since the pre-LLM era (A vs C), and whether framework choice differs by author type — do agents default to the dominant framework per language, or show more diversity?

Generating the findings: `python -m collection.research_questions.rq3` computes per-dataset mock prevalence (overall and per language), framework distribution, category distribution, and interaction-depth statistics, plus an A vs C comparison (Mann-Whitney U for `num_mocks`/`num_interactions_configured`, chi-square for `has_mock`/`framework`/`category`), directly from `db/a.db` and `db/c_sampled.db`, and writes the results to `research_questions/rq3.md` (gitignored, regenerated on demand — any dataset not yet collected is skipped rather than erroring). `has_mock`/`framework`/`category` each report an Overall row plus a per-language BH-FDR family (4 languages, corrected independently per metric) with `n_A`/`n_C` repo counts per row — same convention as RQ1, see its "Generating the findings" paragraph; `num_mocks`/`num_interactions_configured` have no per-language family and render Overall-only, at both the fixture-level and repo-level basis. `has_mock`/`framework`/`category` are additionally re-tested with per-repo category proportions (Mann-Whitney U + Cliff's δ, in "Repo-level aggregates") to correct for fixtures/mocks clustering within repos — see [Limitations § Categorical Pseudo-Replication](reference/limitations.md#categorical-pseudo-replication).

## RQ4 — Usage Categories (Mixed — Qualitative + Quantitative)

> What categories of operations do fixtures perform, and do agent-generated fixtures
> cover the full range of fixture responsibilities that human developers produce?

What it covers: an open-coding taxonomy, positioned last so it synthesizes the picture built by RQ1–3. After establishing that agent fixtures are structurally simpler (RQ1), produce fewer teardowns (RQ2), and mock differently (RQ3), RQ4 asks whether the operational taxonomy explains those differences — are agents concentrating in certain easy categories (object factories, simple environment setup) and avoiding harder ones (stateful I/O setup, lifecycle wrappers, composite fixtures)?

---

## Summary

| RQ | Question | Type | Key Metrics | Datasets |
|----|----------|------|--------------|----------|
| RQ1 | How do agent and human fixtures compare on fundamental structural metrics? | Quantitative | `loc`, `cyclomatic_complexity`, `nesting_depth`, `num_parameters`, `scope`, `commit_type` | A vs C |
| RQ2 | How do agent and human fixtures compare in setup and teardown provision? | Quantitative | `fixture_type` (setup vs teardown variants), `has_teardown_pair`, setup-to-teardown ratio | A vs C |
| RQ3 | How do agent and human fixtures differ in mock usage, framework selection, and interaction depth? | Quantitative | `num_mocks`, `framework`, `category`, `num_interactions_configured` | A vs C |
| RQ4 | What operations do fixtures perform, and do agents cover the full range of human fixture responsibilities? | Mixed | `category` (manual label), `fixture_type`, `scope` | A vs C |

---

## Scripts

[collection/research_questions/](../collection/research_questions/) holds the scripts that
compute paper results directly from collected data and write a findings report to
`research_questions/` at the repo root (gitignored, regenerated on demand — a dataset
not yet collected is skipped rather than erroring). Each is standalone:
`python -m collection.research_questions.<module>`.

| Script | Answers | Reads | Writes |
|---|---|---|---|
| `rq1.py` | RQ1 — per-dataset structural-metric summaries, plus an A vs C comparison (Mann-Whitney U / chi-square) | `db/a.db`, `db/c_sampled.db` | `research_questions/rq1.md` |
| `rq2.py` | RQ2 — per-dataset `fixture_type` kind (setup/teardown/other) distribution, per-repo setup-to-teardown ratio, `has_teardown_pair` rate by fixture_type, plus an A vs C comparison | `db/a.db`, `db/c_sampled.db` | `research_questions/rq2.md` |
| `rq3.py` | RQ3 — per-dataset mock prevalence (overall and per language), framework distribution, category distribution, interaction-depth stats, plus an A vs C comparison | `db/a.db`, `db/c_sampled.db` | `research_questions/rq3.md` |
| `language_contamination.py` | Data-quality check (not tied to one RQ) — for each per-language fixture CSV, what fraction of rows carry a mismatched `language` value | `datasets/{a,c}/fixtures*/*.csv` | `research_questions/language_contamination.md` |

RQ4 has no script yet — its section above describes the intended operationalization, not yet implemented.

Dataset B (contemporary within-repo human baseline) is still collected (`db/b.db`, `paired_collection.py`) but is not part of any RQ1-3 script's reported output above.
