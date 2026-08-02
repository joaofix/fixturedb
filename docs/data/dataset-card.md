# Dataset Card — FixtureDB

## Overview

FixtureDB is a cross-language dataset of test fixture definitions extracted from GitHub repositories. It compares agent-authored and human-authored fixtures across three corpora: agent-authored fixtures (Dataset A), contemporary human-authored fixtures from the same repositories (Dataset B), and pre-LLM human-authored fixtures from an independent repository pool (Dataset C).

| Property | Value |
|----------|-------|
| **Name** | FixtureDB |
| **Languages** | Python, Java, JavaScript, TypeScript |
| **Licenses** | Code: MIT, Dataset: CC BY 4.0 |
| **Venue** | ICPC 2027 — Research Track |

---

## Dataset Composition

### What the dataset contains

Each dataset is a SQLite database (`db/{a,b,c}.db`, schema in [Database Schema](../architecture/database-schema.md)) with four tables: `repositories`, `test_files`, `fixtures`, and `mock_usages`. Dataset A's fixtures carry `commit_kind='agent'` and an `agent_type`; Dataset B's carry `commit_kind='human'`. Dataset C has no commit-level tagging — its fixtures come from a single repository snapshot rather than a commit-by-commit scan.

Alongside the databases:

- **CSV stage outputs**, git-tracked, under `datasets/{a,b,c}/{repos,commits,test-commits,fixtures}/` — the intermediate artifacts of each collection stage, not just the final database.
- **Per-dataset export bundles** (`export/{a,b,c}.zip`, via `python -m collection export --dataset {a,b,c}`) — self-contained CSV dumps of the four tables, filtered to the manual-review sample, with a generated README and schema. See [CSV Export Guide](csv-export-guide.md).
- **Collection summaries** (`datasets/{dataset}/summary.yaml`, via `python -m collection summarize --dataset {a,b,c}`) — repository/fixture counts, extraction rates, and (for A/B) purity-gate acceptance rate.

### Unit of analysis

The unit of analysis is the **fixture**: an individual test setup/teardown definition. Each record includes:

- **Identity** — repository, file, line range, fixture name
- **Type** — detected pattern (`pytest_decorator`, `unittest_setup`, `junit5_before_each`, JS/TS lifecycle hooks, etc. — full catalog in [Fixture Detection](../architecture/detection.md))
- **Framework** — pytest, unittest, junit, testng, etc. (ambiguous for JS/TS hooks shared across Jest/Mocha/Vitest)
- **Scope** — `per_test`, `per_class`, `per_module`, `global`
- **Complexity** — LOC, cyclomatic complexity, max nesting depth
- **Structure** — parameter count, object instantiations, external calls
- **Behavior** — teardown pair presence, fixture dependencies, mock usages
- **Provenance** — commit SHA (A/B only), commit kind, agent type (A only)

---

## Research Objectives

See [Research Questions](../research-questions.md) for the full RQ1–RQ4 definitions and how the three-dataset comparison applies to each.

---

## Variables

### Independent variable

**Dataset membership (A/B/C)** — which corpus a fixture belongs to, determined by the collection pipeline that produced it (agent-attributed commit for A, non-agent commit in the same repo pool for B, pre-LLM-era repository snapshot for C), not a single shared `commit_role` column. See [Agent Detection](../architecture/agent-detection.md).

Membership is operationalized via Tier 1 detection: co-authored-by/assisted-by/generated-by trailers, then author identity, with bot accounts excluded first. The design prioritizes precision over recall — a false positive (human code labeled agent) threatens validity more than a false negative, which only costs statistical power.

### Dependent variables (metrics)

All metrics are collected from test files only.

| Variable | Definition | Tool |
|----------|------------|------|
| `loc` | Non-blank lines of code | Tree-sitter |
| `cyclomatic_complexity` | McCabe complexity | Lizard |
| `max_nesting_depth` | Maximum control-flow nesting | Tree-sitter |
| `num_parameters` | Formal parameter count from AST | Tree-sitter / Lizard |
| `num_objects_instantiated` | Constructor-like expressions | AST + regex |
| `num_external_calls` | I/O and external operation calls | Regex |
| `framework` | Testing framework family | AST traversal |
| `scope` | Execution scope (per_test, per_class, per_module, global) | AST traversal |
| `fixture_dependencies` | Other fixtures this fixture depends on (pytest only) | AST traversal |
| `has_teardown_pair` | Presence of associated cleanup | AST + heuristic pairing rules |
| `num_mocks` / `mock_framework` / `category` | Mock usage, test-double taxonomy | Regex |

### Control variables

Computed at each dataset's own temporal reference point: 2025-01-01 for A/B, 2020-12-31 for C.

| Variable | Operationalization |
|----------|-------------------|
| `language` | Repository primary language (Python, Java, JavaScript, TypeScript) |
| `domain` | Heuristic keyword classification (`web`, `systems`, `ml`, `security`, `database`, `devops`, `other`) |
| `repo_age_years` | `(reference_date - created_at) / 365.25` |

Star count is not a control variable: every repository comes from `github-search-raw/`, which is already seeded with a hard ≥500-star filter at the source (SEART GHS query time — see `github-search-raw/details.txt`), so no repository in the corpus can fall below that floor.

---

## Methodology

### Study design

Three-corpus between-group comparison. See [Agent Detection](../architecture/agent-detection.md) for the full detection methodology and `internal-docs/methodology-improvements/dataset-c-repo-selection.md` for Dataset C's repo-selection rationale.

1. **Repository seeding.** All candidate repositories come from SEART GHS (`github-search-raw/`), filtered at source to ≥500 stars, ≥100 commits, ≥5k LOC, non-fork. This filter doesn't catch org transfers or independently-created "shadow copies" (repos with identical git history but no GitHub-native fork relationship) — see [Repository-Level Duplication](#repository-level-duplication) below and [Limitations](../reference/limitations.md#repository-level-duplication-forks-org-transfers-shadow-copies).
2. **Dataset A repo qualification.** Candidates whose working tree contains a Claude/Cursor/Copilot config file — a strict subset of the ~60-agent detection catalog, chosen as an unambiguous, high-adoption qualification signal.
3. **Dataset A commit scanning.** Within qualified repos, commits since 2025-01-01 are checked against the full agent-signature catalog (bot exclusion, then trailer, then author identity).
4. **Dataset B repo resolution.** Resolved directly from Dataset A's already-qualified repos, not independently searched — this is what makes B a within-repo control by construction.
5. **Dataset C repo selection.** Independent of A/B, filtered only by repo-creation date (2016-01-01 to 2020-12-31); no agent-related filter, since this window predates agent tooling entirely.
6. **Fixture extraction.** `detector.extract_fixtures()` applied identically across all three datasets.
7. **Purity gating (A/B only).** Commit-level: reject the whole commit if any touched test file has a deletion or rename. Fixture-level: each fixture's own line span must be 100% newly added.

### Temporal windows

Datasets A and B use the same window — commits dated 2025-01-01 onward — which is what makes B a valid within-repo, same-era control for A. Dataset C uses repositories created 2016-01-01 through 2020-12-31, snapshotted at each repository's own last commit on or before 2020-12-31. Because C is a single snapshot rather than a commit-by-commit scan, its fixture age is bounded to roughly this five-year window but not known exactly — contrast with A/B, where every fixture is dated to its exact authoring commit.

### Agent detection

Tier 1 detection checks, in order, until the first match:

1. Bot status (excludes CI/automation accounts outright)
2. `Co-authored-by`/`Assisted-by`/`Generated-by` commit trailers
3. Author name/email against the agent-signature catalog

Matching is word-boundary, case-insensitive. Free-text commit message scanning is deliberately not used — see [Agent Detection § Known Limitations](../architecture/agent-detection.md) for the false positives it would introduce. The full agent catalog (~60 tools) lives in `collection/heuristics/agent-mining/`.

### Pure-addition filter (Datasets A/B)

To ensure fixtures are 100% newly added by their attributed author, not a modification of pre-existing code, two gates apply: a commit-level gate rejects commits where any test file contains deletions, renames, or copies, and a fixture-level gate accepts only fixtures whose own line span is exclusively added lines (AST-node-precise, falling back to a line-range check).

### Repository-level duplication

Two different `repo_name`s can share partly or fully identical git history — org transfers, mirrors, shadow copies — invisible to the non-fork filter in step 1, since GitHub's own fork bookkeeping doesn't track this. A shared commit SHA is a cryptographic guarantee of identical content and is never a false positive, so every mechanism below uses it directly as the dedup key.

Two repo-level pre-filters run before selection. Dataset C checks each candidate's commit at the fixed cutoff date against every other candidate (`collection/dedupe_dataset_c_repos.py`). Dataset A drops repos currently sharing a HEAD commit before cloning — but this only catches repos still byte-identical *today*, not a pair that has since diverged.

A third, commit-level mechanism (`collection/dedupe_commits_by_sha.py`) closes most of that gap by working on already-collected commit data instead of a live pre-check: any commit whose exact SHA was collected under more than one `repo_name` is removed, keeping one canonical `repo_name`'s copy. This is fully preventive for Dataset A, since `extract-fixtures --dataset a` reads its commits from the exact file this step cleans — but it has no effect on Dataset B, because `extract-fixtures --dataset b` independently re-clones and re-scans every repo's history rather than reading the deduped file, so it silently rediscovers the same duplicate commits regardless. A fourth mechanism, `collection/dedupe_fixtures_by_sha.py`, closes that gap for B specifically by running the same detection logic against the already-extracted fixture CSVs and database, after (not before) `extract-fixtures --dataset b` — and unlike the other three, it's a recurring cleanup that must be re-run after every extraction, not a one-time fix.

See [Limitations § Repository-Level Duplication](../reference/limitations.md#repository-level-duplication-forks-org-transfers-shadow-copies) and `internal-docs/methodology-improvements/repo-deduplication.md` for the full investigation and measured duplication rates.

---

## Statistical Analysis Plan

### Balance tests (pre-comparison)

Before comparing fixture distributions between any two datasets, we check whether the underlying repo samples are themselves comparable on control variables — repo-level (each fixture-yielding repo counted once), not fixture-weighted:

1. **Language distribution** — chi-square
2. **Domain distribution** — chi-square
3. **Repository age** — Mann-Whitney U (skewed distributions)

The goal is to confirm two corpora are comparable on control variables before attributing a metric difference to authorship. Implemented in `collection/research_questions/balance.py` (`python -m collection.research_questions.balance`, output `research_questions/balance.md`); see [Limitations § Control Variable Balance](../reference/limitations.md#control-variable-balance) for the current result and why this wasn't wired up until 2026-07-31.

### Group comparison tests

A/B/C are three separate databases, not paired observations within one table, so all tests are unpaired:

| Variable type | Test |
|----------|--------------|
| Continuous (`loc`, `cyclomatic_complexity`, `max_nesting_depth`, `num_parameters`, `num_objects_instantiated`, `num_external_calls`) | Mann-Whitney U |
| Categorical (`framework`, `scope`, `has_teardown_pair`, `fixture_type`, mock `category`) | Chi-square |

Every test also reports an effect size — Cliff's delta for Mann-Whitney, Cramér's V for chi-square — since p-values alone conflate statistical significance with sample size; at this corpus's scale (tens of thousands of fixtures), p-values are near-zero for almost any nonzero difference, meaningful or not. Continuous metrics are additionally re-tested at repo level (one mean-per-repo value instead of one value per fixture — see RQ1/RQ3's "Repo-level aggregates" section) to guard against pseudo-replication, since fixtures cluster within repos and testing raw fixture values as independent observations can inflate apparent significance.

See [Analyzing the Datasets](../usage/usage.md) for the concrete query/test pattern: load each dataset separately, tag with a `dataset` column, concatenate.

---

## Sampling

Every fixture meeting the pipeline's criteria is collected for Datasets A, B, and C — there's no fixture-level sampling at collection time.

For manual precision/recall review, `python -m collection sample --dataset {a,b,c}` draws a Cochran-sized (95% confidence, ±5% margin) stratified sample per language. See [Manual-Validation Sampling](../usage/validation-sampling.md). This is the same sample that `export/{dataset}.zip`'s `fixtures.csv`/`mock_usages.csv` are filtered to.

---

## Threats to Validity

See [Limitations and Threats to Validity](../reference/limitations.md) for the full, current treatment. Summary:

### Internal validity

Tier 1 agent detection under-reports agent contributions by design (precision over recall) — commits without agent trailers or identity signals are classified as human. This creates a differential false-negative risk between Datasets B and C: Dataset B's repos are agent-adopting by construction, so an untrailed, informally-agent-assisted commit is more likely there than in Dataset C's pool. B and C are not interchangeable human baselines; treat A-vs-B and A-vs-C as related but distinct comparisons. A further, unmeasured threat is differential recall across authorship groups — the same AST detector is applied to agent and human code alike, but recall could differ if agent code follows canonical framework idioms more consistently than human code. Finally, some metrics are heuristic: `num_external_calls` is regex-based and may miss indirect I/O, and `has_teardown_pair` may miss implicit cleanup such as connection pooling.

### Construct validity

The study targets automatically detectable fixture patterns, per `collection/heuristics/fixture_definitions.yaml`'s per-language catalog — custom or implicit setup without a recognizable declaration is missed by design. Domain labels come from a heuristic keyword classifier, whose accuracy depends on repository topic/description quality; treat them as a coarse grouping, not a precise categorization.

### External validity

Language coverage is limited to Python, Java, JavaScript, and TypeScript. Every repository has ≥500 GitHub stars — a hard filter at the SEART seeding stage, not a tunable threshold — so popular OSS projects may not reflect typical developer practices, a known tradeoff in empirical SE studies that draw on star-based sampling (see the Hamster study, Pan et al., 2025). Finally, Dataset C's window (2016–2020) predates A/B's (2025+), so framework and practice changes across that gap are a threat to the cross-repo comparison specifically — not to A-vs-B, which shares a window.

### Conclusion validity

Final per-language fixture counts depend on repository availability and the pipeline's quality floor — report count tables from `datasets/{dataset}/summary.yaml` when presenting results, not estimates. Because many metrics are tested jointly, family-wise error rate increases; consider Bonferroni or FDR correction when reporting.

---

## Data Quality

### Known limitations

1. **Agent detection precision vs. recall.** Tier 1 prioritizes precision over recall. No manual validation study has been completed yet — the infrastructure (`validation_sampling.py`) is implemented and ready. See [Limitations § Validation Status](../reference/limitations.md#validation-status).
2. **Fixture detection recall** (an informed estimate, not yet a measured result): Python >95%, Java >95%, JavaScript >90%, TypeScript >90%. See [Limitations § Fixture Detection Recall](../reference/limitations.md#fixture-detection-recall).
3. **Metric limitations** — see Advanced Metrics Limitations in [Limitations](../reference/limitations.md).
4. **Language coverage** — Python, Java, JavaScript, TypeScript only.
5. **Domain classification** — heuristic keyword-based; accuracy depends on topic/description quality.
6. **Sampling bias** — all repositories have ≥500 stars.
7. **Repository-level duplication** — not caught by the source query's non-fork filter (org transfers, shadow copies). Forward-looking detection is now in place for future collections but hasn't been applied retroactively. See [Limitations § Repository-Level Duplication](../reference/limitations.md#repository-level-duplication-forks-org-transfers-shadow-copies).
8. **Cross-language fixture leakage** — a repo's single language tag doesn't mean every extracted fixture is in that language; multi-language repos contribute a measurable minority of fixtures in other languages (Dataset B 12.15%, Dataset A 8.04% as of 2026-07-31; Dataset C's rate requires a fresh extraction run to measure). This is a corpus property to report, not an error to fix. See [Limitations § Cross-Language Fixture Leakage](../reference/limitations.md#cross-language-fixture-leakage).

---

## Dataset Splits

| Dataset | Repositories | Commits/Snapshot | Fixtures | Description |
|---------|-------------|-------------------|----------|-------------|
| `a` | Agent-enabled (Claude/Cursor/Copilot config) | Agent-attributed, 2025-01-01+ | Agent-authored | Primary agent corpus |
| `b` | Same repos as `a` | Non-agent, 2025-01-01+ | Human-authored | Within-repo control |
| `c` | Independent pool, created 2016–2020 | Snapshot at each repo's last commit ≤2020-12-31 | Human-authored | Cross-repo, pre-agent-era baseline |

---

## Accessing the Dataset

### Databases

```bash
# Path
db/a.db   # Dataset A (agent)
db/b.db   # Dataset B (contemporary human)
db/c.db   # Dataset C (pre-LLM human)

# Tables
.tables
```

### CSV stage outputs

```
datasets/a/{repos,commits,test-commits,fixtures}/
datasets/b/{repos,test-commits,fixtures}/
datasets/c/{repos,fixtures}/
```

### Export bundles

```
export/a.zip   # repositories.csv, test_files.csv, fixtures.csv, mock_usages.csv, README.md, SCHEMA.md, AGENTS.md
export/b.zip   # same, no AGENTS.md
export/c.zip   # same, no AGENTS.md
```

See [CSV Export Guide](csv-export-guide.md) for the exact contents and how the sampled subset is drawn.

### Collection summaries

```
datasets/a/summary.yaml
datasets/b/summary.yaml
datasets/c/summary.yaml
```

---

## Citation

If you use FixtureDB in your research, please cite the paper once published (ICPC 2027 Research Track submission — citation details to follow acceptance).

---

## Dataset Maintenance

There's no formal versioning yet; the dataset is time-stamped via collection run timestamps in output filenames. It may be updated for future paper revisions or language additions. Check the repository's issues page for known data quality issues and corrections.
