# Configuration Reference

This document describes configuration options for the `python -m collection`
CLI. See [Collection Architecture](./collection.md) for the Dataset A/B/C
build map, and [Reproducing Results](../usage/reproducing.md) for the full
verb sequence.

Per-run parameters (which repos, which language, output paths) are all via
command-line arguments — every verb supports `--help` for its full argument
list, and every default input/output directory is resolved through
`collection/paths.py`. Fixed reference data (file-type filters, the
testing-framework registry, per-language search settings, and the
agent-detection catalog) is instead kept as YAML under
`collection/config_data/` and `collection/heuristics/` — see
"Reference-Data Catalogs" below.

## Dataset B: `extract-fixtures --dataset b`

```bash
python -m collection extract-fixtures --dataset b [OPTIONS]
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `--output-db` | PATH | db/b.db | SQLite database output path |
| `--repos-per-language` | INT | (all) | Target repos per language |
| `--repo-dir` | PATH | datasets/b/repos/ | Directory with `*_repo.csv` files (see `discover-repos --dataset b`) |
| `--commit-dir` | PATH | datasets/b/test-commits/ | Directory to also write discovered test-commit CSVs to |
| `--language` | STR | (all) | Specific language: python, java, javascript, typescript |
| `--workers` | INT | 4 | Parallel worker threads |
| `--force` | FLAG | off | Re-extract even if `--output-db` already has fixture rows |

### Control Variables (Fixed)

Computed automatically at the `AGENT_CORPUS_START_DATE` snapshot (same window as Dataset A, since Dataset B is the within-repo matched control):

| Variable | Description |
|----------|-------------|
| `language` | Programming language |
| `domain` | Repository domain (computed from topics/description) |
| `star_tier` | GitHub stars tier (core: ≥500, extended: 100-499) |
| `repo_age_years` | Repository age in years at the snapshot date |
| `agent_adoption_intensity` | Share of agent vs. human commits in the repo |

### Example

```bash
python -m collection discover-repos      --dataset b --language python
python -m collection extract-fixtures    --dataset b --repos-per-language 100 --language python
```

## Dataset C: `extract-fixtures --dataset c`

```bash
python -m collection extract-fixtures --dataset c [OPTIONS]
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `--output-db` | PATH | db/c.db | SQLite database output path |
| `--repo-dir` | PATH | datasets/c/repos/ | Directory containing `{lang}_repo.csv`/`all.csv` |
| `--language` | STR | (all, reads `all.csv`) | Specific language; reads `{lang}_repo.csv` instead |
| `--workers` | INT | 8 | Parallel worker threads |
| `--force` | FLAG | off | Re-extract even if `--output-db` already has fixture rows |

Reads its repo list from `datasets/c/repos/` (produced by
`discover-repos --dataset c`, which wraps `select_dataset_c_repos.py`)
rather than `corpus.db`.

### Example

```bash
python -m collection discover-repos   --dataset c
python -m collection extract-fixtures --dataset c --language python
```

## Dataset A: `extract-fixtures --dataset a`

```bash
python -m collection extract-fixtures --dataset a [OPTIONS]
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `--output-db` | PATH | db/a.db | SQLite database output path |
| `--repo-dir` | PATH | datasets/a/repos/ | Directory with `*_repo.csv` files |
| `--commit-dir` | PATH | datasets/a/test-commits/ | Directory with `*_test_commit.csv`/`*_commit.csv` files |
| `--repos-per-language` | INT | (all) | Target repos per language |
| `--languages` | STR (multi) | (all) | Limit to one or more of: python, java, javascript, typescript |
| `--force` | FLAG | off | Re-extract even if `--output-db` already has fixture rows |

### Control Variables (Fixed)

Computed automatically at the `AGENT_CORPUS_START_DATE` snapshot:

| Variable | Description |
|----------|-------------|
| `language` | Programming language |
| `domain` | Repository domain |
| `star_tier` | GitHub stars tier at snapshot |
| `repo_age_years` | Repository age in years at snapshot |
| `agent_type` | Agent classifier: claude, copilot, cursor, aider, or unknown |
| `commit_kind` | Always `'agent'` |

### Agent Detection

Agents detected via **Tier 1 (author metadata + co-authored-by trailers)**:

```
Agent patterns recognized:
- co-authored-by: Claude <claude@anthropic.com>
- co-authored-by: GitHub Copilot <copilot@github.com>
- co-authored-by: Cursor <cursor@anysoftware.io>
- co-authored-by: Aider <aider@paul.pub>
```

### Example

```bash
python -m collection discover-repos      --dataset a
python -m collection discover-commits    --dataset a
python -m collection filter-test-commits --dataset a
python -m collection extract-fixtures    --dataset a --languages python javascript --repos-per-language 100
```

## Statistical Comparison

`collection/between_group_comparison.py` compares two datasets' `fixtures`
tables. Since each dataset now has its own database (`db/a.db`, `db/b.db`,
`db/c.db`), comparing two of them means pointing it at both DB paths
directly rather than filtering one shared database by `commit_kind`.
`python -m collection analyze-distribution --dataset a --against b` covers
the same "are these two corpora comparable in size" question at the fixture-
count level; `between_group_comparison.py` goes deeper with per-control
statistical tests.

| Control | Test | Interpretation |
|---------|------|-----------------|
| language | Chi-square test | p ≥ 0.05 → balanced |
| domain | Chi-square test | p ≥ 0.05 → balanced |
| star_tier | Chi-square test | p ≥ 0.05 → balanced |
| repo_age_years | Mann-Whitney U | p ≥ 0.05 → balanced |

## Temporal Boundaries

Fixed dates from `collection/config.py` (not configurable via CLI):

| Constant | Value | Used by | Rationale |
|----------|-------|---------|-----------|
| `AGENT_CORPUS_START_DATE` | 2025-01-01 | Dataset A, Dataset B | Agent availability window |
| `HUMAN_CORPUS_CUTOFF_DATE` | 2020-12-31 | Dataset C | Pre-AI-agent era cutoff, and upper bound of the repo creation-date window |
| `DATASET_C_MIN_CREATED_DATE` | 2016-01-01 | Dataset C | Lower bound of the repo creation-date window |

These dates ensure Dataset C has no possible agent involvement (cutoff in
2020, agents available from 2025), while Datasets A and B are directly
comparable since they're drawn from the same repos and the same window.
`DATASET_C_MIN_CREATED_DATE`/`HUMAN_CORPUS_CUTOFF_DATE` together bound a
Dataset C repo's age at snapshot time to a fixed ~5-year window, the same
value for every language — see
[internal-docs/methodology-improvements/dataset-c-repo-selection.md](../../internal-docs/methodology-improvements/dataset-c-repo-selection.md)
for why.

## Database Configuration

Each dataset has its own, fully separate database:

```sql
-- Dataset A (db/a.db)
SELECT COUNT(*) FROM fixtures;

-- Dataset B (db/b.db) -- within-repo, same 2025+ window as A
SELECT COUNT(*) FROM fixtures;

-- Dataset C (db/c.db) -- cross-repo pre-2021 baseline
SELECT COUNT(*) FROM fixtures;
```

## Quality Filters

Shared thresholds from `collection/config.py`: `MIN_STARS = 500`,
`MIN_COMMITS = 100`, `MIN_TEST_FILES = 5`.

### Dataset A / Dataset B (same repos)
- Repositories with agent config files and agent commits in the 2025+ window
- At least `MIN_TEST_FILES` test files, at least 1 fixture extracted
- Tier 1 agent detection only (no heuristics)

### Dataset C
- Independent repo set, created within `[DATASET_C_MIN_CREATED_DATE, HUMAN_CORPUS_CUTOFF_DATE]` — no
  domain/category stratification, no per-language cap (see `select_dataset_c_repos.py`)
- **No `MIN_STARS` filter.** GitHub's live star count only reflects today's popularity, not the repo's
  standing at the pre-2021 snapshot — see the methodology doc linked above for why this would bias the
  sample toward repos that happened to succeed later.
- `MIN_COMMITS`/`MIN_TEST_FILES` are still enforced, but measured from the repo's real git history as of
  its own cutoff commit (`dataset_c.py::count_commits_up_to()`), not from GitHub's live metadata
- Pinned pre-2021 cutoff commit per repo (no diff/purity gating — full snapshot extraction)

## Logging and Monitoring

Extraction and sampling produce JSON summaries in `output/`:

```
output/
├── human_corpus_summary_*.json    # Dataset B extraction run summary
├── agent_corpus_summary_*.json    # Dataset A extraction run summary
├── sample_a.json, sample_b.json, sample_c.json   # per-dataset sample results
└── ...
```

## Reference-Data Catalogs

Fixed, non-per-run configuration lives as YAML data files, not hardcoded
Python — editing a catalog is a data change, not a code change, and
reviewers can scan the exact list without reading Python. `collection/config.py`
loads all of these at import time and derives the module-level constants
(`NON_CODE_EXTENSIONS`, `EXCLUSION_KEYWORDS`, `FRAMEWORK_REGISTRY`,
`LANGUAGE_CONFIGS`) that the rest of the codebase already imports — no
production call site reads the YAML directly.

| Catalog | File | Loaded by |
|---|---|---|
| Non-code file extensions to skip during test-file scanning | `collection/config_data/non_code_extensions.yaml` | `config.NON_CODE_EXTENSIONS` |
| Repo name/description keywords for boilerplate/toy repos | `collection/config_data/exclusion_keywords.yaml` | `config.EXCLUSION_KEYWORDS` |
| Known testing frameworks per language | `collection/config_data/framework_registry.yaml` | `config.FRAMEWORK_REGISTRY` |
| Per-language search/test-detection settings | `collection/config_data/language_configs.yaml` | `config.LANGUAGE_CONFIGS` |
| Agent detection: config-file patterns | `collection/heuristics/agent_files.csv` (mirrors [labri-progress/agent-mining](https://github.com/labri-progress/agent-mining)'s `files.csv` schema+content) | `agent_patterns.PAPER_AGENT_CONFIG_PATTERNS` / `LIGHTWEIGHT_AGENT_CONFIG_PATTERNS` |
| Agent detection: paper's strict-scope agent subset | `collection/heuristics/agent_heuristics.yaml` (`paper_scope`) | `agent_patterns.PAPER_AGENT_CONFIG_PATTERNS` |
| Agent detection: commit author/trailer signatures | `collection/heuristics/agent_authors.csv` (mirrors [labri-progress/agent-mining](https://github.com/labri-progress/agent-mining)'s `authors.csv` schema+content) | `agent_patterns.AGENT_SIGNATURES` |
| Bot-account detection: CI/automation bot patterns | `collection/heuristics/bots.csv` (mirrors [labri-progress/agent-mining](https://github.com/labri-progress/agent-mining)'s `bots.csv` schema+content) | `agent_patterns.BOT_PATTERNS` / `is_bot_author()` |
| Operational definition of "fixture" per language (patterns + documented exclusions) | `collection/config_data/fixture_definitions.yaml` | `detector_python.py` / `detector_java.py` / `detector_javascript.py` pattern tables |
| Mock-framework, external-call, object-instantiation regex tables + setup/teardown pairing rules | `collection/config_data/feature_extraction_patterns.yaml` | `detector_shared.py` (`MOCK_PATTERNS`, `EXTERNAL_CALL_PATTERNS`, teardown pairing) / `complexity_provider.py` (`_count_object_instantiations`) |

The fixture-definitions catalog is also a reviewer-facing audit artifact, not
just data: each language section has an `excluded` list documenting known
boundary cases the detector deliberately does not (or cannot) catch, so a
missing pattern is a documented decision rather than an oversight — see
[Fixture Detection Logic](detection.md),
[Fixture Patterns Reference](../usage/fixture-patterns-reference.md#known-exclusions--boundary-cases),
and [Limitations](../reference/limitations.md#fixture-detection-recall) for
how this feeds into the paper's recall discussion.

Building exhaustive, catalog-driven test coverage for `fixture_definitions.yaml`
(parametrized directly over every entry, not a hand-picked subset —
`tests/collection/test_fixture_definitions_catalog_coverage.py`) surfaced
real detection bugs in `detector_java.py`'s JUnit3 fallback: no check for
class inheritance at all (despite the YAML's own comment restricting it
to a TestCase subclass), and an "already annotated" guard narrow enough
that a `@Given`-annotated method could be double-detected. See
[Fixture Detection Logic](detection.md) for the full writeup.

The feature-extraction-patterns catalog covers the metrics computed *after*
a fixture is already detected (`num_mocks`, `num_external_calls`,
`num_objects_instantiated`, `has_teardown_pair`): what regex signals a
mock/I-O-call/constructor, and which setup fixture_types pair with which
teardown fixture_types. Migrating this out of Python also fixed a real gap
found while auditing it — the previous hardcoded teardown-pairing table
referenced fixture types no detector in this codebase ever produces
(`nunit_setup`, `xunit_fact`, `xunit_theory` — .NET frameworks, out of
scope) while missing several pairs it should have had (TestNG, Mocha, AVA,
`before_all`/`after_all`, JUnit3), so those fixture types never got credit
for having a teardown even when one was present in the source.

A follow-up audit of `mock_patterns` specifically (prompted by "what do we
actually detect as a mock?") found and fixed three more real blind spots,
not just relocated data: `mock.patch.object(...)`/`mocker.patch.object(...)`
(a distinct call shape from `.patch('dotted.path')` that the original regex
structurally couldn't match), bare `patch(...)`/`patch.object(...)` (the
`from unittest.mock import patch` form, used without a `mock.`/`mocker.`
prefix), and several missing Sinon/Jest entry points
(`sinon.fake/replace/createStubInstance`, `jest.mocked/createMockFromModule`).
pytest's built-in `monkeypatch` fixture was also added as a new
`pytest_monkeypatch` framework. `mock_patterns_excluded` documents what's
still deliberately out of scope (PowerMock, assertion-only Chai/sinon-chai
usage, and the structural fact that anything mocked outside a fixture's own
body — most notably Jest's conventional top-level `jest.mock(...)` — is
invisible to this detector).

Each `mock_patterns` entry also carries a `category`, classifying the
detected construct into the classic test-double taxonomy (dummy/stub/spy/
mock/fake, per Meszaros). This is a new `mock_usages.category` column, not
just a documentation addition — see [Fixture Detection Logic](detection.md)
for the classification methodology (keyword match first, then a small,
individually-justified manual-override list for the handful of constructs
whose name contains no category keyword) and why `dummy` is deliberately
never assigned.

Building exhaustive, catalog-driven test coverage for `mock_patterns`
(30 patterns total) surfaced two real precision bugs, not just gaps in
what was tested: the bare `Mock()`/`MagicMock()`/`AsyncMock()` pattern had
no word boundary, so it also matched inside `EasyMock.createMock(...)`
(a Java false positive), and MockK's `mock(X.class)` pattern had no
qualifier exclusion, so it also matched inside `Mockito.mock(X.class)`
(double-counting one call under two frameworks). Both were fixed in the
YAML (word boundary, negative lookbehind) rather than in
`detector_shared.py`, since the patterns — not the detection code — were
the source of the bug. `Mockito.spy(...)` was also added as a new pattern:
it previously had no coverage at all, meaning Java had zero `spy`-category
representation despite `spy` being a distinct, common Mockito API from
`mock()`.

Temporal boundaries (`AGENT_CORPUS_START_DATE`, `HUMAN_CORPUS_CUTOFF_DATE`)
and quality thresholds (`MIN_STARS`, `MIN_COMMITS`, `MIN_TEST_FILES`) remain
plain constants directly in `collection/config.py` — they're single values
tuned for this study's design, not open-ended catalogs expected to grow.

## Environment Variables

| Variable | Usage | Example |
|----------|-------|---------|
| `GITHUB_TOKEN` | GitHub API auth (rate-limit relief for repo-discovery pre-checks) | github_pat_1A2B3C4D5E6F |
| `PYTHONPATH` | Module import path | `export PYTHONPATH=$PWD` |

## Advanced Options

### Database Optimization

```bash
# Rebuild indexes after collection
sqlite3 db/b.db "VACUUM; ANALYZE;"
sqlite3 db/a.db "VACUUM; ANALYZE;"

# Check database health
sqlite3 db/b.db "PRAGMA integrity_check;"
```

## See Also

- [Reproducing Results](../usage/reproducing.md) — Step-by-step collection guide
- [Collection Architecture](./collection.md) — Dataset A/B/C build map
- [Database Schema](./database-schema.md) — Table structure and columns
- [Agent Detection](./agent-detection.md) — How agents are identified
