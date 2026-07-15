# Dataset Card - FixtureDB

## Dataset Overview

FixtureDB is a cross-language dataset of test fixture definitions extracted from GitHub
repositories, comparing agent-authored and human-authored fixtures across three
independent corpora: agent-authored fixtures (Dataset A), contemporary human-authored
fixtures from the same repositories (Dataset B), and pre-LLM human-authored fixtures
from an independent repository pool (Dataset C).

### Dataset Summary

| Property | Value |
|----------|-------|
| **Name** | FixtureDB |
| **Languages** | Python, Java, JavaScript, TypeScript |
| **Licenses** | Code: MIT, Dataset: CC BY 4.0 |
| **Venue** | ICPC 2027 — Research Track |

---

## Dataset Composition

### What the Dataset Contains

The dataset consists of:

1. **Three independent SQLite databases** (`db/a.db`, `db/b.db`, `db/c.db` — see
   [Database Schema](../architecture/database-schema.md) for the full, authoritative
   schema), each with:
   - `repositories` — Repository metadata and control variables
   - `test_files` — Test file inventory with file-level metrics
   - `fixtures` — Individual fixture definitions with structural metrics
   - `mock_usages` — Mock framework usage per fixture

   Dataset A's fixtures are tagged `commit_kind='agent'` plus `agent_type`; Dataset B's
   are tagged `commit_kind='human'`; Dataset C has no commit-level tagging (its fixtures
   come from a single repository snapshot, not a commit-by-commit scan — see
   [Database Schema](../architecture/database-schema.md) for why).

2. **CSV stage outputs** under `datasets/{a,b,c}/{repos,commits,test-commits,fixtures}/`
   (git-tracked; per-language files) — the intermediate artifacts of each collection
   stage, not just the final database.

3. **Per-dataset export bundles** (`export/{a,b,c}.zip`, via
   `python -m collection export --dataset {a,b,c}`) — see
   [CSV Export Guide](csv-export-guide.md). Each bundle is self-contained (raw CSV dumps
   of `repositories`/`test_files`/`fixtures`/`mock_usages`, filtered to a manual-review
   sample, plus a generated README/SCHEMA).

4. **Collection summaries** (`datasets/{dataset}/summary.yaml`, via
   `python -m collection summarize --dataset {a,b,c}`) with repository/fixture counts,
   extraction rates, and (for A/B) purity-gate acceptance rate.

### Unit of Analysis

The unit of analysis is the **fixture** (individual test setup/teardown definition).
Each fixture record includes:

- **Identity**: repository, file, line range, fixture name
- **Type**: detected pattern (e.g., `pytest_decorator`, `pytest_class_method`,
  `unittest_setup`, `junit5_before_each`, JS/TS lifecycle hooks — see
  [Fixture Detection](../architecture/detection.md) for the full, per-language,
  YAML-defined catalog)
- **Framework**: testing framework (e.g., `pytest`, `unittest`, `junit`, `testng`,
  ambiguous for JS/TS hooks shared across Jest/Mocha/Vitest)
- **Scope**: execution scope (`per_test`, `per_class`, `per_module`, `global`)
- **Complexity**: LOC, cyclomatic complexity, max nesting depth
- **Structure**: number of parameters, object instantiations, external calls
- **Behavior**: teardown pair presence, fixture dependencies, mock usages
- **Provenance**: commit SHA (A/B only), commit kind (`agent`/`human`), agent type (A only)

---

## Research Objectives

We address the following research questions:

1. **RQ1 — Structural metrics:** How do fixture definitions differ in structural
   complexity, parameter counts, object instantiations, and external calls?
2. **RQ2 — Setup/teardown provision:** How do fixtures differ in cleanup completeness
   (teardown pairs) and scope granularity?
3. **RQ3 — Mocking practices:** How do fixtures differ in mocking behavior (framework
   choice, test-double category, usage counts)?
4. **RQ4 — Operational categories:** How do fixture types/purposes differ in
   distribution across authorship groups?
5. **RQ5 — Control variable effects:** How do language, domain, and repository age
   mediate any differences?

---

## Variables

### Independent Variable

- **Dataset membership (A/B/C):** which corpus a fixture belongs to, operationalized via
  the collection pipeline that produced it (agent-attributed commit for A, non-agent
  commit in the same repo pool for B, pre-LLM-era repository snapshot for C) rather than
  a single shared `commit_role` column — see
  [Agent Detection](../architecture/agent-detection.md).
  - Operationalization: Tier 1 detection (co-authored-by/assisted-by/generated-by
    trailers, then author identity; bot accounts excluded first).
  - Justification: precision-prioritized design — a false positive (human code labeled
    agent) threatens validity more than a false negative (an unattributed agent commit
    just reduces statistical power).

### Dependent Variables (Metrics)

All metrics are collected only from test files.

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

### Control Variables

Computed at each dataset's own temporal reference point (2025-01-01 for A/B,
2020-12-31 for C).

| Variable | Operationalization |
|----------|-------------------|
| `language` | Repository primary language (Python, Java, JavaScript, TypeScript) |
| `domain` | Heuristic keyword classification (`web`, `systems`, `ml`, `security`, `database`, `devops`, `other`) |
| `repo_age_years` | `(reference_date - created_at) / 365.25` |

Star count is **not** a control variable: every repository is drawn from
`github-search-raw/`, itself seeded with a hard ≥500-star filter at the source (SEART
GHS query time — see `github-search-raw/details.txt`), so no repository in the corpus
can fall below that floor.

---

## Methodology

### Study Design

**Three-corpus between-group comparison** — see
[Agent Detection](../architecture/agent-detection.md) for the full detection
methodology and `internal-docs/methodology-improvements/dataset-c-repo-selection.md`
for Dataset C's repo-selection rationale.

1. **Repository seeding**: All candidate repositories are seeded from SEART GHS
   (`github-search-raw/`), a hard ≥500-star / ≥100-commit / ≥5k-LOC / non-fork query
   filter applied at source.
2. **Dataset A repo qualification**: candidates whose working tree contains a
   Claude/Cursor/Copilot config file (a strict subset of the ~60-agent detection
   catalog, chosen for unambiguous, high-adoption qualification signal).
3. **Dataset A commit scanning**: within qualified repos, commits since 2025-01-01 are
   checked against the full agent-signature catalog (Tier 1: bot exclusion, then
   trailer, then author identity).
4. **Dataset B repo resolution**: Dataset B's repo pool is resolved *directly* from
   Dataset A's already-qualified repos (not independently searched) — the within-repo
   control by construction.
5. **Dataset C repo selection**: independent of A/B, filtered only by repo-creation date
   (2016-01-01–2020-12-31), no agent-related filter (predates agent tooling entirely).
6. **Fixture extraction**: `detector.extract_fixtures()` (Section on Fixture Detection)
   applied identically across all three datasets.
7. **Purity gating (A/B only)**: commit-level (reject the whole commit if any touched
   test file has a deletion/rename) and fixture-level (each fixture's own line span must
   be 100% newly added) — see [Agent Detection § Pure-Addition Filter](../architecture/agent-detection.md).

### Temporal Windows

- **Datasets A/B**: commits dated 2025-01-01 onwards (same window for both — this is
  what makes B a valid within-repo, same-era control for A).
- **Dataset C**: repositories created 2016-01-01–2020-12-31, snapshotted at each
  repository's own last commit on or before 2020-12-31. Fixture age is bounded to
  roughly this ~5-year window but not known exactly (Dataset C is a single snapshot, not
  a commit-by-commit scan) — contrast with A/B, where every fixture is dated to its
  exact authoring commit.

### Agent Detection

**Tier 1: trailer + author-identity detection**, checked in order, first match wins:
1. Bot status (excludes CI/automation accounts outright)
2. `Co-authored-by`/`Assisted-by`/`Generated-by` commit trailers
3. Author name/email against the agent-signature catalog

Word-boundary matching, case-insensitive. Free-text commit message scanning is
deliberately not used (see [Agent Detection § Known Limitations](../architecture/agent-detection.md)
for the false positives this would introduce). Full agent catalog (~60 tools):
`collection/heuristics/agent-mining/`.

### Pure-Addition Filter (Datasets A/B)

To ensure fixtures are **100% newly added** by their attributed author (not a
modification of pre-existing code):
- **Commit-level gate**: Reject commits where any test file contains deletions,
  renames, or copies.
- **Fixture-level gate**: Accept only fixtures whose own line span is exclusively added
  lines (AST-node-precise, falling back to a line-range check).

---

## Statistical Analysis Plan

### Balance Tests (Pre-comparison)

Before comparing fixture distributions between any two datasets:

1. **Language distribution:** chi-square.
2. **Domain distribution:** chi-square.
3. **Repository age:** Mann-Whitney U (skewed distributions).

Goal: confirm the two corpora being compared are comparable on control variables before
attributing a metric difference to authorship; see
[Limitations § Control Variable Balance](../reference/limitations.md#control-variable-balance).

### Group Comparison Tests

A/B/C are three separate databases, not paired observations within one table — unpaired
tests throughout:

| Variable type | Test |
|----------|--------------|
| Continuous (`loc`, `cyclomatic_complexity`, `max_nesting_depth`, `num_parameters`, `num_objects_instantiated`, `num_external_calls`) | Mann-Whitney U |
| Categorical (`framework`, `scope`, `has_teardown_pair`, `fixture_type`, mock `category`) | Chi-square |

See [Analyzing the Datasets](../usage/usage.md) for the concrete query/test pattern
(load each dataset separately, tag with a `dataset` column, concatenate).

---

## Sampling

- **Datasets A/B/C (full collection):** every fixture meeting the pipeline's criteria is
  collected — no fixture-level sampling at collection time.
- **Manual-validation sample:** `python -m collection sample --dataset {a,b,c}` draws a
  Cochran-sized (95% confidence, ±5% margin) stratified sample per language for manual
  precision/recall review — see [Manual-Validation Sampling](../usage/validation-sampling.md).
  This is the sample `export/{dataset}.zip`'s `fixtures.csv`/`mock_usages.csv` are
  filtered to.

---

## Threats to Validity

See [Limitations and Threats to Validity](../reference/limitations.md) for the full,
current, authoritative treatment. Summary:

### Internal Validity

1. **Agent misclassification:** Tier 1 detection under-reports agent contributions
   (conservative by design — precision over recall). Commits without agent trailers/
   identity signals are classified as human.
2. **Differential false-negative risk, Dataset B vs. C:** Dataset B's repos are, by
   construction, agent-adopting — an untrailed, informally-agent-assisted commit is more
   likely there than in Dataset C's repo pool. B and C are not interchangeable "human"
   baselines; treat A-vs-B and A-vs-C as related but distinct comparisons.
3. **Differential recall across authorship groups:** the same AST detector is applied to
   both agent and human code, but recall could still differ by authorship group if agent
   code follows canonical framework idioms more consistently than human code. Not yet
   measured — documented as an open threat.
4. **Metric heuristics:** `num_external_calls` is regex-based and may miss indirect I/O;
   `has_teardown_pair` may miss implicit cleanup (e.g., connection pooling).

### Construct Validity

1. **What "fixture" means:** the study targets automatically detectable fixture
   patterns per `collection/heuristics/fixture_definitions.yaml`'s per-language,
   documented catalog. Custom/implicit setup without a recognizable declaration is
   missed by design.
2. **Domain labels:** heuristic keyword classifier; accuracy depends on repository
   topics/description quality. Treat as a coarse grouping, not precise categorization.

### External Validity

1. **Language coverage:** Python, Java, JavaScript, TypeScript only.
2. **Star-based sampling:** every repository has ≥500 GitHub stars (a hard filter at the
   SEART seeding stage, not a tunable threshold) — popular OSS projects may not reflect
   typical developer practices. A known tradeoff in empirical SE studies drawing on
   star-based sampling for test-coverage assurance (see the Hamster study, Pan et al.,
   2025).
3. **Temporal confounding for A-vs-C:** Dataset C's window (2016–2020) predates
   Dataset A/B's (2025+); framework/practice changes across that gap are a threat to
   validity for the cross-repo comparison specifically (not for A-vs-B, which shares a
   window).

### Conclusion Validity

1. **Sample size:** final per-language fixture counts depend on repository availability
   and the pipeline's quality floor — report count tables from
   `datasets/{dataset}/summary.yaml` when presenting results, not estimates.
2. **Multiple comparisons:** many metrics tested jointly increases family-wise error
   rate; consider Bonferroni/FDR correction when reporting.

---

## Data Quality

### Known Limitations

1. **Agent detection precision vs. recall**: Tier 1 prioritizes precision over recall.
   No completed manual validation study exists yet (infrastructure — `validation_sampling.py`
   — is implemented and ready; see [Limitations § Validation Status](../reference/limitations.md#validation-status)).
2. **Fixture detection recall** (informed estimate, not yet a measured result — see
   [Limitations § Fixture Detection Recall](../reference/limitations.md#fixture-detection-recall)):
   - Python: >95%, Java: >95%, JavaScript: >90%, TypeScript: >90%
3. **Metric limitations**: see Advanced Metrics Limitations in
   [Limitations](../reference/limitations.md).
4. **Language coverage**: Python, Java, JavaScript, TypeScript only.
5. **Domain classification**: heuristic keyword-based; accuracy depends on topics/
   description quality.
6. **Sampling bias**: all repositories have ≥500 stars.

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

### CSV Stage Outputs

```
datasets/a/{repos,commits,test-commits,fixtures}/
datasets/b/{repos,test-commits,fixtures}/
datasets/c/{repos,fixtures}/
```

### Export Bundles

```
export/a.zip   # repositories.csv, test_files.csv, fixtures.csv, mock_usages.csv, README.md, SCHEMA.md, AGENTS.md
export/b.zip   # same, no AGENTS.md
export/c.zip   # same, no AGENTS.md
```

See [CSV Export Guide](csv-export-guide.md) for the exact contents and how the sampled
subset is drawn.

### Collection Summaries

```
datasets/a/summary.yaml
datasets/b/summary.yaml
datasets/c/summary.yaml
```

---

## Citation

If you use FixtureDB in your research, please cite the paper once published (ICPC 2027
Research Track submission — citation details to follow acceptance).

---

## Dataset Maintenance

- **Versioning:** No formal versioning yet. Dataset is time-stamped via collection run
  timestamps in output filenames.
- **Updates:** Dataset may be updated for future paper revisions or language additions.
- **Errata:** Check the repository issues page for known data quality issues and
  corrections.
