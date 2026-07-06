# Configuration Reference

This document describes configuration options for the phase-based collection
pipeline. See [Collection Architecture](./collection.md) for the Dataset
A/B/C build map, and [Reproducing Results](../usage/reproducing.md) for the
full phase sequence.

Per-run parameters (which repos, which language, output paths) are all via
command-line arguments — each phase script supports `--help` for its full
argument list. Fixed reference data (file-type filters, the testing-framework
registry, per-language search settings, and the agent-detection catalog) is
instead kept as YAML under `collection/config_data/` and
`collection/heuristics/` — see "Reference-Data Catalogs" below.

## Dataset B: `phase_2_extract_human.py`

```bash
python -m collection.phase_2_extract_human [OPTIONS]
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `--output-db` | PATH | data/fixturedb-human.db | SQLite database output path |
| `--repos-per-language` | INT | (all) | Target repos per language |
| `--repo-dir` | PATH | github-search-agent/agent_repositories | Directory with `*_agent_repo.csv` QC files |
| `--source-db` | PATH | data/corpus.db | Source corpus database |
| `--clones-dir` | PATH | clones/ | Directory with repository clones |
| `--language` | STR | (all) | Specific language: python, java, javascript, typescript |
| `--workers` | INT | 4 | Parallel worker threads |

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
python -m collection.phase_2_extract_human --repos-per-language 100 --language python
```

## Dataset C: `phase_2b_extract_dataset_c.py`

```bash
python -m collection.phase_2b_extract_dataset_c [OPTIONS]
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `--output-db` | PATH | data/fixturedb-human.db | SQLite database output path (shared with Dataset B) |
| `--clones-dir` | PATH | clones/ | Directory with repository clones |
| `--language` | STR | (all `dataset_c_*.csv` found) | Specific language; uses `dataset_c_{lang}.csv` |
| `--workers` | INT | 4 | Parallel worker threads |

Reads its repo sample from `fixtures-from-agents/dataset_c_*.csv` (produced
by `sample_proportional_repos.py`) rather than `corpus.db` — there is no
`--repo-dir` option.

### Example

```bash
python -m collection.phase_2b_extract_dataset_c --language python
```

## Dataset A: `phase_3_extract_agent.py`

```bash
python -m collection.phase_3_extract_agent [OPTIONS]
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `--output-db` | PATH | data/fixturedb-agent.db | SQLite database output path |
| `--repo-dir` | PATH | github-search-agent/agent_repositories | Directory with `*_agent_repo.csv` QC files |
| `--commit-dir` | PATH | github-search-agent/agent_repositories | Directory with `*_agent_commit_qc.csv` files |
| `--repos-per-language` | INT | (all) | Target repos per language |
| `--languages` | STR (multi) | (all) | Limit to one or more of: python, java, javascript, typescript |

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
python -m collection.phase_3_extract_agent --languages python javascript --repos-per-language 100
```

## Statistical Comparison

`collection/between_group_comparison.py` compares Dataset A vs Dataset B (the
within-repo pair) by querying a single database for both `commit_kind='agent'`
and `commit_kind='human'` rows. No phase script (1-8) currently calls it —
it's only wired up via the legacy `pipeline.py between-group-stats` command,
which expects one shared database (historically `data/between-group.db`).
Since the phase-based pipeline writes Dataset A and Dataset B to separate
databases (`fixturedb-agent.db` / `fixturedb-human.db`), running this command
against the phase-produced outputs requires first pointing `--db` at (or
merging into) a database containing both corpora's `fixtures` rows.

| Control | Test | Interpretation |
|---------|------|-----------------|
| language | Chi-square test | p ≥ 0.05 → balanced |
| domain | Chi-square test | p ≥ 0.05 → balanced |
| star_tier | Chi-square test | p ≥ 0.05 → balanced |
| repo_age_years | Mann-Whitney U | p ≥ 0.05 → balanced |

```bash
python pipeline.py between-group-stats --db data/between-group.db
```

## Temporal Boundaries

Fixed dates from `collection/config.py` (not configurable via CLI):

| Constant | Value | Used by | Rationale |
|----------|-------|---------|-----------|
| `AGENT_CORPUS_START_DATE` | 2025-01-01 | Dataset A, Dataset B | Agent availability window |
| `HUMAN_CORPUS_CUTOFF_DATE` | 2020-12-31 | Dataset C | Pre-AI-agent era cutoff |

These dates ensure Dataset C has no possible agent involvement (cutoff in
2020, agents available from 2025), while Datasets A and B are directly
comparable since they're drawn from the same repos and the same window.

## Database Configuration

Dataset A and Datasets B/C use **separate** databases:

```sql
-- Dataset A
-- (data/fixturedb-agent.db)
SELECT COUNT(*) FROM fixtures;

-- Dataset B vs Dataset C
-- (data/fixturedb-human.db) -- commit_kind distinguishes within-repo (human,
-- same 2025+ window as A) from the cross-repo baseline
SELECT commit_kind, COUNT(*) FROM fixtures GROUP BY commit_kind;
```

## Quality Filters

Shared thresholds from `collection/config.py`: `MIN_STARS = 500`,
`MIN_COMMITS = 100`, `MIN_TEST_FILES = 5`.

### Dataset A / Dataset B (same repos)
- Repositories with agent config files and agent commits in the 2025+ window
- At least `MIN_TEST_FILES` test files, at least 1 fixture extracted
- Tier 1 agent detection only (no heuristics)

### Dataset C
- Independent repo sample, stratified to match Dataset A's per-language/domain proportions
- Pinned pre-2021 cutoff commit per repo (no diff/purity gating — full snapshot extraction)

## Logging and Monitoring

Each phase produces a JSON summary in `output/`:

```
output/
├── phase_2_extraction_stats_YYYYMMDD_HHMMSS.json   # Dataset B
├── phase_2b_extraction_stats_YYYYMMDD_HHMMSS.json  # Dataset C
├── phase_4_distribution_analysis_YYYYMMDD_HHMMSS.json
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
| Agent detection: config-file patterns + commit signatures | `collection/heuristics/agent_heuristics.yaml` | `agent_patterns.AGENT_SIGNATURES` / `PAPER_AGENT_CONFIG_PATTERNS` / `LIGHTWEIGHT_AGENT_CONFIG_PATTERNS` |
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
| `GITHUB_TOKEN` | GitHub API auth (used by the legacy `pipeline.py agent-fixtures` convenience command) | github_pat_1A2B3C4D5E6F |
| `PYTHONPATH` | Module import path | `export PYTHONPATH=$PWD` |

## Advanced Options

### Database Optimization

```bash
# Rebuild indexes after collection
sqlite3 data/fixturedb-human.db "VACUUM; ANALYZE;"
sqlite3 data/fixturedb-agent.db "VACUUM; ANALYZE;"

# Check database health
sqlite3 data/fixturedb-human.db "PRAGMA integrity_check;"
```

## See Also

- [Reproducing Results](../usage/reproducing.md) — Step-by-step collection guide
- [Collection Architecture](./collection.md) — Dataset A/B/C build map
- [Database Schema](./database-schema.md) — Table structure and columns
- [Agent Detection](./agent-detection.md) — How agents are identified
