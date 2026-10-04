# Research Questions

FixtureDB addresses five research questions, comparing agent-authored fixtures
(Dataset A) against pre-LLM human-authored fixtures from an independent repository
pool (Dataset C) -- the RQ2-4 scripts' reported comparison is A vs C. A contemporary
human-authored baseline from the same repositories (Dataset B) is also collected, but
isn't part of these scripts' reported output. See
[Database Schema](architecture/database-schema.md) for the underlying tables and
[Dataset Card](data/dataset-card.md) for corpus composition.

---

## RQ1 — Fixture Prevalence (Quantitative)

> How common are tests, fixtures, setup, and teardown across the raw repo universe,
> independent of Dataset A/B/C's own filtering?

Unlike RQ2-4, this is not an A-vs-C comparison -- it characterizes the full raw
population (`github-search-raw/*.csv.gz`, ~24.7k repos minus known duplicates) that
A/B/C are each filtered subsets of. A dedicated collection stage,
`collection/rq1_prevalence_scan.py`, clones every repo (pinned to a fixed cutoff date
matching A/C's own collection date, not current HEAD) and persists per-repo counts to
`db/rq1_prevalence.db` -- deliberately not a 4th dataset, kept structurally separate
from `datasets/{a,b,c}/` and `db/{a,b,c}.db` (see that module's own docstring for the
full naming scheme and the production incidents its retry/timeout/auth logic exists
to handle).

`rq1.py` is the pure reader over that db, rendering two tables over every
successfully-scanned repo -- deliberately no `min_test_files` quality floor (or any
other filter) applied, unlike RQ2-4's Dataset A/C populations: RQ1's whole point is
to characterize the raw universe *before* any such filtering (a floored variant was
reported through 2026-10-04, as a robustness check showing the floor barely moved
the numbers, then dropped once that check had served its purpose -- see git history):

- **Table 1** (`tab:rq1-prevalence`): per language and "All" (pooled), repos with >=1
  test file, then three parallel percentages of that exact same population --
  Fixture (%), Setup (%), Teardown (%) -- self-explanatory by construction, no
  caption needed (2026-10-04 restructure: the table's previous `#`/`%` + Setup (%)/
  Teardown (%) shape had an absolute fixture-having count sitting between the
  population column and the percentages, visually inviting Setup/Teardown (%) to be
  read as dividing by *that* count instead -- which was also this table's actual old
  behavior, and pushed every language's numbers up near 95-99% regardless of how
  common setup/teardown actually is, an almost-tautological reading once you've
  already conditioned on "has a fixture." See `rq1.py`'s `render_table1()` docstring
  for the full account; the dropped raw fixture-having count is unchanged and still
  available in the report's own "Raw numbers" table).
- **Table 2** (`tab:rq1-prevalence-median`): per language and "All" (one pooled
  median, not an average of four per-language medians), the median fixture/setup/
  teardown count per repo among repos with >=1 fixture.

A repo whose clone failed, or that had no commit at or before the cutoff date, is
excluded from every count in both tables -- "unknown," never counted as "confirmed no
tests."

## RQ2 — General Metrics Overview (Quantitative)

> How do agent-generated and human-written fixtures compare across structural metrics?

What it covers: LOC, cyclomatic complexity, comment density, `fixture_type` distribution. **Three paper continuous metrics, final** (as of 2026-09-26): `PAPER_CONTINUOUS_METRICS` — exactly `loc`, `cyclomatic_complexity`, `comment_density` — is now also the exhaustive set this script computes and tests at all; `rq2.md` labels them "Paper Metrics." `num_parameters` is still shown descriptively (a floor-percentage footnote only — 0 params is the large majority in both datasets, which makes a distributional test uninformative) under a separate "Other Extracted Features (Not in the Paper)" heading. `cyclomatic_complexity` also floors heavily (CC=1 is the large majority) but stays in the comparative analysis, unlike `num_parameters`. `max_nesting_depth`, `num_objects_instantiated`, `num_external_calls`, `has_teardown_pair`, `scope`, `framework`, and `commit_type` were removed from the extracted metric set entirely (not part of any reported set, in this RQ or any other) — `scope`/`framework` were fully redundant with `fixture_type` (1:1 mapping verified across the collected data), `commit_type` (a Conventional Commits classification of the originating commit, along with the `conventional_commits.py` module that computed it) was never used in any reported RQ, and the other three simply aren't part of the paper's reported metrics.

The reported comparison: A vs C establishes the historical baseline — are agent-authored fixtures structurally different from a pre-LLM human baseline?

Generating the findings: `python -m collection.research_questions.rq2` computes per-dataset summary statistics for all of the above, plus an A vs C comparison (Mann-Whitney U for continuous metrics), directly from `db/a.db` and `db/c.db`, and writes the results to `research_questions/rq2.md` (regenerated on demand and committed — any dataset not yet collected is skipped rather than erroring). Every continuous-metric comparison table has the same shape: an "Overall" row (a single pooled test, reported as an exact p-value, not BH-corrected) plus, for `loc`/`cyclomatic_complexity`/`comment_density`, one BH-FDR-corrected row per language — each metric's 4 per-language tests are their own correction family, independent of every other metric's. Every row also reports `n_A`/`n_C`, the number of repos (not fixtures) that actually fed that specific test. Continuous metrics are repo-level throughout (one value per repo, per language for the per-language rows), not per-fixture: each repo contributes its own **mean** fixture value — the paper's actual methodology. `rq2.md` also renders a second, clearly-labeled "Diagnostic: median-per-repo aggregation (NOT used in the paper)" section (2026-09-28) with the same three metrics computed using each repo's **median** fixture value instead — an alternative aggregation that was briefly tried as the primary methodology and reverted the same day, since `cyclomatic_complexity`/`comment_density`'s heavy floor-binding collapses most repos' own median to the exact floor value, producing near-universal ties and starving Mann-Whitney of power. That section is kept only as a transparency record of how sensitive the comparison is to this choice, explicitly not a competing result — see `rq2.py`'s module docstring for the full account. `fixture_type` has no A vs C comparison of any kind — its fixture-level/per-language chi-square (which would have treated a repo's hundreds of correlated fixtures as that many independent observations, inflating both the chi-square statistic and Cramér's V) and its repo-level category-proportion test (Mann-Whitney U + Cliff's δ, formerly "Repo-level aggregates") were both never used in the paper and were removed entirely (2026-09-27), rather than kept unused. Only `fixture_type`'s per-dataset descriptive distribution remains, purely as a support column for `fixture_role` classification (see `rq3.py`'s module docstring). See [Limitations § Categorical Pseudo-Replication](reference/limitations.md#categorical-pseudo-replication).

## RQ3 — Setup and Teardown Characterization (Quantitative)

> How do agent-generated fixtures compare to human-written ones in setup and teardown
> provision?

What it covers: setup and teardown are detected as separate `fixture_type` values — `junit5_before_each` vs `junit5_after_each`, `before_each` vs `after_each` — and classified into a `fixture_role` (setup/teardown/other) via the same type/name lookup tables (see `rq3.py`'s module docstring). `has_teardown_pair`, a separate binary indicator that used to exist alongside `fixture_role`, was removed from the extracted metric set entirely.

Two reported tables (A vs C), replacing an earlier single median-proportion table:
- **Table 1 (fixture counts)**: purely descriptive, no statistics — the raw count of setup-classified and teardown-classified fixtures per language and Total ("other"-classified fixtures excluded from both columns).
- **Table 2 (teardown coverage)**: for each repo, a binary indicator — does it have at least one teardown-classified fixture at all? "Coverage A/C (%)" is the share of repos with the indicator at 1 (the mean of a 0/1 list *is* that percentage), with `n_A`/`n_C` repo counts per row. Purely descriptive — no statistical test (removed 2026-09-27, alongside RQ4's Coverage/Intensity test and Intensity metric entirely: RQ2 is now the only script in this package that performs BH-FDR correction — see [internal-docs/methodology-improvements/bh-fdr-correction-families.md](../internal-docs/methodology-improvements/bh-fdr-correction-families.md) for the full inventory).

Generating the findings: `python -m collection.research_questions.rq3` computes both tables directly from `db/a.db` and `db/c.db`, and writes the results to `research_questions/rq3.md` (regenerated on demand and committed — any dataset not yet collected is skipped rather than erroring).

A supplementary "Setup Coverage by Repository" table (the setup analogue of Table 2) and a Hartigan & Hartigan unimodality (dip test) check on Python's `teardown_pct` distribution were both computed here but never part of either paper table; both were removed entirely (2026-09-27) after review confirmed neither fed the paper -- see `rq3.py`'s module docstring for the one real finding the setup-coverage table had turned up (a significant per-language gap in Java) before removal. Removing the dip test also dropped the `diptest` package as a project dependency.

## RQ4 — Mocking (Quantitative)

> How do agent-generated and human-written fixtures differ in mock usage — coverage?

What it covers: `num_mocks` (mock calls per fixture), plus one paper table reporting a single repo-level metric derived from it: **mocking coverage** — does a repo have >=1 fixture with a mock at all? This RQ is purely quantitative — the old RQ4's qualitative `target_identifier`-based target-layer coding (boundary/internal/infrastructure) has been dropped rather than reduced to a keyword heuristic. `num_interactions_configured` (a separate `mock_usages` column estimating how many interactions were configured on a mock) was never one of the paper's reported metrics and was removed from the extracted metric set entirely (2026-09-26). **Mocking intensity** (among repos that do mock, the median mock-call count across that repo's own mocking fixtures) was reported alongside Coverage for a time, then removed entirely (2026-09-27) — no longer one of the paper's reported metrics.

The reported comparison asks whether repos mock at all more or less often since the pre-LLM era (Coverage, A vs C).

Generating the findings: `python -m collection.research_questions.rq4` computes Coverage directly from `db/a.db` and `db/c.db`, and writes the results to `research_questions/rq4.md` (regenerated on demand and committed — any dataset not yet collected is skipped rather than erroring). Coverage is repo-level: a per-repo binary has-any-mock indicator (population: every repo with >=1 fixture, of that language for the per-language rows), with "Coverage A/C (%)" the mean of that 0/1 indicator and `n_A`/`n_C` repo counts per row. Purely descriptive — no statistical test (removed 2026-09-27, alongside RQ3's Table 2 test and Intensity entirely: RQ2 is now the only script in this package that performs BH-FDR correction — see [internal-docs/methodology-improvements/bh-fdr-correction-families.md](../internal-docs/methodology-improvements/bh-fdr-correction-families.md) for the full inventory). This table replaced three previously-reported ones (fixture-level mock prevalence, framework distribution, test-double category distribution) — see rq4.py's module docstring for the full history. The fixture-level `has_mock` chi-square was kept for a time in a "Legacy" section (mock detection logic unchanged, but never used in the paper), then removed entirely (2026-09-27) — see [Limitations § Categorical Pseudo-Replication](reference/limitations.md#categorical-pseudo-replication). `framework`/`category` raw data (`mock_usages.framework`/`category`) is still fetched and available on `DatasetMetrics` for programmatic use, but no longer rendered as a report table — both are language-specific constructs (framework *names* can't overlap across languages; category *naming conventions* vary by ecosystem), so a pooled A-vs-C view was already confounded by each dataset's different language mix.

## RQ5 — Agent Configuration Files (Mixed — Qualitative + Quantitative)

> How often do root-level agent configuration files (AGENTS.md, CLAUDE.md) mention
> test-related and fixture-related guidance?

A keyword-based scan over the same raw ~24.7k-repo universe RQ1 measures
(`github-search-raw/*.csv.gz`), independent of Dataset A/B/C's own filtering, pinned
to the same snapshot date as RQ1 (`collection/rq5_agent_file_scan.py`'s
`RQ5_CUTOFF_DATE`, reused directly from `rq1_prevalence_scan.RQ1_CUTOFF_DATE`).
Unlike RQ1, this scan never clones anything — it reads entirely through GitHub's
REST API (the Git Database API specifically): one call finds the commit at or
before the snapshot date (`GET .../commits?until=<date>T23:59:59Z`), one lists the
repository root's tree entries non-recursively (`GET .../git/trees/<sha>`), and one
per matched entry fetches its raw blob content (`GET .../git/blobs/<sha>`) — the
same two or three calls regardless of repo size, which makes this scan immune to
the repo-size-driven failures (giant-monorepo clone timeouts, disk space,
`ENAMETOOLONG`) that RQ1's clone-based approach had to work around. A blob's
content is returned as-is regardless of what the file represents, so a symlinked
agent file (confirmed against a real example, `pnpm/pnpm`'s root `CLAUDE.md`) is
searched as its own literal target text with no special-casing needed. One accepted
methodology difference from RQ1: the cutoff-commit boundary is evaluated in UTC
(GitHub's API normalizes every commit timestamp to UTC, with no way to recover a
commit's original timezone offset), while RQ1's PyDriller-based walk compares each
commit's date in its own original offset — the two only disagree for a commit
landing within the \~14-hour window around UTC midnight on the exact cutoff date,
accepted as immaterial here since root config files change on the order of
weeks/months, not hours. Every occurrence of a catalog keyword is
keyword-matched (case-insensitive, word-boundary-respecting, multi-word terms
tolerant of a space/hyphen/no separator), tagged with its line, surrounding context,
and whether it falls inside a fenced code block, for later manual review. Test
keywords and fixture keywords are two separate, versioned lists in
`collection/heuristics/rq5_agent_file_keywords.yaml`, editable independently of the
scan's code. Statistics are computed at the **repository** level, not the file
level: a repo counts as having test (or fixture) guidance if ANY of its root
agent files matches >=1 test (or fixture) keyword, and the denominator throughout
is "repositories with >=1 root agent file" (not "repositories analyzed" — most
analyzed repos have none). Reported: overall, by repository language, and per
individual keyword (how many repositories contain it), plus the share of
test-guidance repos that also have fixture guidance. `agent_files.csv` (the
scan's own CSV) stays file-level raw data for manual review — no file-level
percentages are computed anywhere in the report.

**Fixture guidance is reported two ways, inclusive and unambiguous.** Unlike
every other keyword in the catalog, bare "fixture"/"fixtures" are a correct
lexical match with an ambiguous *sense*: manual sampling of real matches found
they're majority fixture-as-test-data-file (`tests/fixtures/*.json`), not
fixture-as-code (`@pytest.fixture`) — the sense this study is actually about.
They stay in the catalog (dropping them would also lose every real
fixture-as-code match, undercounting rather than fixing anything), but
`research_questions/rq5.py` additionally reports a stricter "unambiguous" count
restricted to repos with >=1 match from a keyword other than those two
(`conftest`, `beforeEach`/`afterEach`/`beforeAll`/`afterAll`, `test setup`,
`setup and teardown`) — a precision floor alongside the inclusive number, not a
replacement for it. The bare word "teardown" was removed from the catalog
entirely (v2 → v3) for the same reason "setup" was already excluded: it matches
generic resource/UI/infrastructure cleanup prose with no test relevance.

Collection: `python -m collection.rq5_agent_file_scan` writes `db/rq5_agent_files.db`
(three tables: `repo_scan`, `agent_files`, `agent_file_matches`) and
`rq5-agent-files/*.csv`. Reporting: `python -m collection.research_questions.rq5`
reads that db and writes `research_questions/rq5.md`.

---

## Summary

| RQ | Question | Type | Key Metrics | Datasets |
|----|----------|------|--------------|----------|
| RQ1 | How common are tests/fixtures/setup/teardown across the raw repo universe? | Quantitative | Repo counts with tests/fixtures/setup/teardown (%), median fixtures/setup/teardown per repo | Raw universe (not A/B/C) |
| RQ2 | How do agent and human fixtures compare on fundamental structural metrics? | Quantitative | Paper: `loc`, `cyclomatic_complexity`, `comment_density`. Also reported (not in paper): `num_parameters`, `fixture_type` | A vs C |
| RQ3 | How do agent and human fixtures compare in setup and teardown provision? | Quantitative | `fixture_role` (setup/teardown/other): absolute fixture counts by type, per-repo teardown coverage rate | A vs C |
| RQ4 | How do agent and human fixtures differ in mock usage? | Quantitative | Mocking coverage (% repos with any mock) | A vs C |
| RQ5 | How often do agent configuration files mention test/fixture guidance? | Mixed | % of repos (with >=1 root AGENTS.md/CLAUDE.md) with >=1 test keyword / >=1 fixture keyword, per keyword repo-count | Raw universe (not A/B/C) |

---

## Scripts

[collection/research_questions/](../collection/research_questions/) holds the scripts that
compute paper results directly from collected data and write a findings report to
`research_questions/` at the repo root (regenerated on demand and committed — a dataset
not yet collected is skipped rather than erroring). Each is standalone:
`python -m collection.research_questions.<module>`.

| Script | Answers | Reads | Writes |
|---|---|---|---|
| `rq1.py` | RQ1 — fixture/setup/teardown prevalence and per-repo medians, each in a no-floor and a `min_test_files`-floor variant | `db/rq1_prevalence.db` (written by `collection/rq1_prevalence_scan.py`, not `db/{a,b,c}.db`) | `research_questions/rq1.md` |
| `rq2.py` | RQ2 — per-dataset structural-metric summaries, plus an A vs C comparison (Mann-Whitney U / chi-square) | `db/a.db`, `db/c.db` | `research_questions/rq2.md` |
| `rq3.py` | RQ3 — per-dataset `fixture_type` kind (setup/teardown/other) distribution, plus two A vs C tables: absolute setup/teardown fixture counts by language, and per-repo teardown coverage rate by language (both purely descriptive) | `db/a.db`, `db/c.db` | `research_questions/rq3.md` |
| `rq4.py` | RQ4 — per-dataset mocking summary, plus one A vs C paper table (mocking coverage %, per language, purely descriptive) | `db/a.db`, `db/c.db` | `research_questions/rq4.md` |
| `rq5.py` | RQ5 — agent-config-file test/fixture keyword prevalence, repo-level (a repo counts if ANY of its root agent files matches): overall, by repo language, and per keyword | `db/rq5_agent_files.db` (written by `collection/rq5_agent_file_scan.py`, not `db/{a,b,c}.db`) | `research_questions/rq5.md` |
| `language_contamination.py` | Data-quality check (not tied to one RQ) — for each per-language fixture CSV, what fraction of rows carry a mismatched `language` value | `datasets/{a,c}/fixtures*/*.csv` | `research_questions/language_contamination.md` |

Dataset B (contemporary within-repo human baseline) is still collected (`db/b.db`, `paired_collection.py`) but is not part of any RQ2-4 script's reported output above.
