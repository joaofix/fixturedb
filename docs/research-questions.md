# Research Questions

FixtureDB addresses four research questions, each comparing fixtures across the three
independent corpora: agent-authored fixtures (Dataset A), contemporary human-authored
fixtures from the same repositories (Dataset B), and pre-LLM human-authored fixtures
from an independent repository pool (Dataset C). See
[Database Schema](architecture/database-schema.md) for the underlying tables and
[Dataset Card](data/dataset-card.md) for corpus composition.

---

## RQ1 — General Metrics Overview (Quantitative)

> How do agent-generated and human-written fixtures compare across structural metrics?

**What it covers**: LOC, cyclomatic complexity, nesting depth, `num_parameters`, scope
distribution, `fixture_type` distribution, `num_external_calls`, `num_objects_instantiated`.
This is the baseline characterization that grounds everything else. It answers: are
agent fixtures bigger or smaller, simpler or more complex, more or less parameterized
than human ones?

**Three-dataset comparison**: A vs B establishes the pure authorship effect. A vs C
establishes the historical baseline. B vs C adds a secondary finding — has human
fixture writing itself changed in the agent era?

**Generating the findings**: `python -m collection.research_questions.rq1` computes
per-dataset summary statistics for all of the above plus A vs B and A vs C
comparisons (Mann-Whitney U for continuous metrics, chi-square for categorical ones)
directly from `db/{a,b,c}.db`, and writes the results to `research_questions/rq1.md`
(gitignored, regenerated on demand — any dataset not yet collected is skipped rather
than erroring).

## RQ2 — Setup and Teardown Characterization (Quantitative)

> How do agent-generated fixtures compare to human-written ones in setup and teardown
> provision?

**What it covers**: This is the cleanest new angle and it is already measurable from
the existing schema. Setup and teardown are detected as separate `fixture_type` values
— `junit5_before_each` vs `junit5_after_each`, `before_each` vs `after_each` — and
`fixtures.has_teardown_pair` flags whether a setup-side fixture has matching cleanup
logic, computed per language via `_calculate_teardown_pairs()`
([detector_shared.py](../collection/detector_shared.py)): a yield statement (pytest), a
same-type setup/teardown name pair (unittest, including `addCleanup`/`enterContext`
self-registered cleanup), a different-type setup/teardown pair by scope (JUnit/TestNG/
JS), or an always-true case for mechanisms that guarantee teardown by construction
(JUnit `@Rule`/`@ClassRule`, Vitest `aroundEach`/`aroundAll`). Per repo, the ratio of
setup fixtures to teardown fixtures can be computed: a balanced ratio approaching 1:1
suggests disciplined lifecycle management, while a heavily setup-skewed ratio (many
befores, few afters) suggests teardown is being neglected.

This operationalization requires no new AST work — `fixture_type` and
`has_teardown_pair` already capture it completely. Note: pairing is intra-file only
(a setup fixture's teardown counterpart in a different file, e.g. inherited from a
Java base test class, is not detected).

**Three-dataset comparison**: Do agents write fewer teardown fixtures than humans in
the same repos (A vs B)? Is teardown discipline better or worse today than in the
pre-LLM era (A vs C, B vs C)?

**Key metrics**: `fixture_type` (setup vs teardown variants), `has_teardown_pair`,
setup-to-teardown ratio per repo, per language.

## RQ3 — Mocking (Quantitative)

> How do agent-generated and human-written fixtures differ in mock usage — prevalence,
> framework selection, and interaction depth?

**What it covers**: Mock prevalence per fixture and per language, framework
distribution, `num_interactions_configured`, and `target_identifier` patterns.

**Three-dataset comparison**: Do agents mock more or less than humans (A vs B)? Has
mock prevalence inside fixtures changed since the pre-LLM era (A vs C)? Does framework
choice differ by author type — do agents default to the dominant framework per
language or show more diversity?

## RQ4 — Usage Categories (Mixed — Qualitative + Quantitative)

> What categories of operations do fixtures perform, and do agent-generated fixtures
> cover the full range of fixture responsibilities that human developers produce?

**What it covers**: An open-coding taxonomy, positioned last so it synthesizes the
picture built by RQ1–3. After establishing that agent fixtures are structurally
simpler (RQ1), produce fewer teardowns (RQ2), and mock differently (RQ3), RQ4 asks
whether the operational taxonomy explains those differences — are agents concentrating
in certain easy categories (object factories, simple environment setup) and avoiding
harder ones (stateful I/O setup, lifecycle wrappers, composite fixtures)?

---

## Summary

| RQ | Question | Type | Key Metrics | Datasets |
|----|----------|------|--------------|----------|
| RQ1 | How do agent and human fixtures compare on fundamental structural metrics? | Quantitative | `loc`, `cyclomatic_complexity`, `nesting_depth`, `num_parameters`, `scope`, `num_external_calls`, `commit_type` | A vs B vs C |
| RQ2 | How do agent and human fixtures compare in setup and teardown provision? | Quantitative | `fixture_type` (setup vs teardown variants), `has_teardown_pair`, setup-to-teardown ratio | A vs B vs C |
| RQ3 | How do agent and human fixtures differ in mock usage, framework selection, and interaction depth? | Quantitative | `mock_usages`, `framework`, `num_interactions_configured` | A vs B vs C |
| RQ4 | What operations do fixtures perform, and do agents cover the full range of human fixture responsibilities? | Mixed | `category` (manual label), `fixture_type`, `scope` | A vs B vs C |

---

## Scripts

[collection/research_questions/](../collection/research_questions/) holds the scripts that
compute paper results directly from collected data and write a findings report to
`research_questions/` at the repo root (gitignored, regenerated on demand — a dataset
not yet collected is skipped rather than erroring). Each is standalone:
`python -m collection.research_questions.<module>`.

| Script | Answers | Reads | Writes |
|---|---|---|---|
| `rq1.py` | RQ1 — per-dataset structural-metric summaries, plus A vs B / A vs C comparisons (Mann-Whitney U / chi-square) | `db/{a,b,c}.db` | `research_questions/rq1.md` |
| `language_contamination.py` | Data-quality check (not tied to one RQ) — for each per-language fixture CSV, what fraction of rows carry a mismatched `language` value | `datasets/{a,b,c}/fixtures/*.csv` | `research_questions/language_contamination.md` |

RQ2–RQ4 have no script yet — their sections above describe the intended operationalization, not yet implemented.
