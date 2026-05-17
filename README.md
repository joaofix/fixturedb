# FixtureDB — Corpus Collection Pipeline

[![Tests & Coverage](https://github.com/joao-almeida/icsme-nier-2026/actions/workflows/coverage.yml/badge.svg)](https://github.com/joao-almeida/icsme-nier-2026/actions/workflows/coverage.yml)
![Coverage](./.github/coverage.svg)

Replication package for the paper:

> **FixtureDB: A Multi-Language Dataset of Test Fixture Definitions**
> João Almeida, Andre Hora  
> *ICSME 2026 — Tool Demonstration and Data Showcase Track*  
> TODO: add DOI once published

This repository contains the extraction pipeline that builds FixtureDB.
The dataset itself (SQLite database + CSV exports) is archived separately
on Zenodo at **TODO: Zenodo DOI**.

---

## Dataset at a Glance

The toy dataset contains fixture definitions extracted from 200 GitHub repositories across 4 programming languages:

| Metric | Toy Dataset |
|--------|-------------|
| **Total Repositories** | 200 (50 per language) |
| **Total Test Files** | 257,764 |
| **Total Fixtures** | 35,169 |
| **Languages** | Python, Java, JavaScript, TypeScript |
| **Size (SQLite + CSVs)** | ~175 MB (uncompressed) / 26 MB (compressed) |
| **Export Format** | SQLite database + 5 CSV files:<br>- repositories.csv (metadata)<br>- repository_statistics.csv (aggregated metrics per repo)<br>- test_files.csv (file metadata)<br>- test_file_statistics.csv (aggregated metrics per file)<br>- fixtures.csv (individual fixtures) |
| **Reproducibility** | Pinned GitHub commits for all repositories |

**Download:** [Latest Zenodo Release](TODO: add Zenodo DOI) — includes full SQLite database and CSV exports for analysis.

### Data Collection Details

| Property | Value |
|----------|-------|
| **SEART GitHub Search Extraction** | April 1–2, 2026 |
| **Repository Selection** | Quality filters: ≥5 test files, ≥50 commits, ≥500 stars |
| **Languages** | Python, Java, JavaScript, TypeScript |
| **GitHub API Version** | v3 REST API |
| **Required Tools** | See [requirements.txt](requirements.txt) for exact versions |
| **Tree-sitter** | Grammar support for all 4 languages |
| **Complexity Analysis** | Lizard + language-specific cognitive complexity |
| **Python Environment** | 3.8+ |

### Human vs Agent Fixture Analysis

Building on the FixtureDB corpus, the `collection/` pipeline implements a **two-tier methodology** to compare human-created (pre-2021) vs AGENT-generated (2022+) fixtures:

- **Tier 1 (Within-Repo)**: Search existing corpus repos for agent commits → eliminates confounders (same project, domain, team)
- **Tier 2 (Between-Repo)**: If Tier 1 insufficient, discover matched repos via SEART → reach statistical power with transparency

**Phases:**
1. Scan corpus for agent commits (Tier 1)
2. Verify Co-authored-by trailers
3. Assess Tier 1 yield, recommend Tier 2 if needed
4. Discover matched repos (Tier 2, conditional)
5. Extract pre-2021 human fixtures (snapshot-based)
6. Extract AGENT fixtures (with tier labels + commit SHA)
7. Analyze distributions, stratified sampling
8. Export and final validation

**Output:** Two balanced datasets: `fixturedb-human.db` vs `fixturedb-agent.db` with explicit methodology tracking.

For a fast validation run, use `python -m collection.toy` to build a 20-repo-per-language toy dataset.

See [collection/README.md](collection/README.md) for detailed documentation and quick start.

---

## Documentation

Complete documentation has been organized into dedicated files in the [docs/](docs/) folder:

### Quick Navigation

| Document | Purpose |
|----------|---------|
| [docs/INDEX.md](docs/INDEX.md) | **Start here** — overview and quick navigation |
| [collection/README.md](collection/README.md) | Command-line entrypoint for the new dataset |

### Getting Started

| Document | Purpose |
|----------|---------|
| [docs/getting-started/intro.md](docs/getting-started/intro.md) | What is FixtureDB and why it matters |
| [docs/getting-started/repository-structure.md](docs/getting-started/repository-structure.md) | Project layout and organization |
| [docs/getting-started/setup.md](docs/getting-started/setup.md) | Installation and dependencies |
| [collection/README.md](collection/README.md) | Command reference for the new dataset |

### Dataset & Data Collection

| Document | Purpose |
|----------|---------|
| [docs/data/data-collection.md](docs/data/data-collection.md) | Five-phase pipeline walkthrough |
| [docs/data/storage.md](docs/data/storage.md) | Disk usage and database growth |
| [docs/data/csv-export-guide.md](docs/data/csv-export-guide.md) | CSV export format and columns |
| [docs/data/csv-user-guide.md](docs/data/csv-user-guide.md) | CSV exports for non-SQL users |

### Architecture & Technical Reference

| Document | Purpose |
|----------|---------|
| [docs/architecture/database-schema.md](docs/architecture/database-schema.md) | Complete ERD and table specifications |
| [docs/architecture/configuration.md](docs/architecture/configuration.md) | All tunable parameters |
| [docs/architecture/detection.md](docs/architecture/detection.md) | Tree-sitter AST and mock detection |
| [docs/architecture/data-pipeline-overview.md](docs/architecture/data-pipeline-overview.md) | Detailed pipeline architecture |
| [docs/architecture/metrics-reference.md](docs/architecture/metrics-reference.md) | Metrics definitions and computation |

### Usage & Analysis

| Document | Purpose |
|----------|---------|
| [docs/usage/reproducing.md](docs/usage/reproducing.md) | Exact corpus replication with pinned commits |
| [docs/usage/usage.md](docs/usage/usage.md) | SQL query examples and data access |
| [docs/usage/fixture-patterns-reference.md](docs/usage/fixture-patterns-reference.md) | Fixture types and classification patterns |

### Reference

| Document | Purpose |
|----------|---------|
| [docs/reference/limitations.md](docs/reference/limitations.md) | Known constraints and validation status |
| [docs/reference/license.md](docs/reference/license.md) | MIT (code) and CC BY 4.0 (dataset) |
| [docs/reference/testing.md](docs/reference/testing.md) | Test suite and validation |
| [docs/reference/references.md](docs/reference/references.md) | Academic citations and sources |

## Quick start

```bash
# Install dependencies
pip install -r requirements.txt

# Set up your GitHub token
cp .env.example .env
# Edit .env and add your GITHUB_TOKEN

# Build a quick validation dataset
python -m collection toy
```

For detailed setup, see [docs/getting-started/setup.md](docs/getting-started/setup.md).

## Running Tests

The test suite is organized to match the project structure:

```bash
# Run all tests
pytest tests/

# Run collection module tests
pytest tests/collection/

# Run human_vs_agent pipeline tests
pytest tests/human_vs_agent/

# Run with coverage report
pytest tests/ --cov=collection --cov=human_vs_agent --cov-report=html
```

For detailed test organization, see [tests/TEST_ORGANIZATION.md](tests/TEST_ORGANIZATION.md).

## What is FixtureDB?

FixtureDB is a structured dataset of **test fixture definitions** extracted from
open-source software repositories on GitHub across **Python, Java, JavaScript,
and TypeScript**.

A *test fixture* is any code that prepares or tears down state before or after a test runs.
For each fixture, the dataset records structural metadata (size, complexity, scope, type)
and mock framework usage.

**Why it matters:** Prior empirical work on fixtures is exclusively Java-based. FixtureDB is the
first cross-language resource treating the fixture as its primary unit of analysis.

See [docs/getting-started/intro.md](docs/getting-started/intro.md) for the full overview.

### Data Quality & Testing

FixtureDB focuses exclusively on **quantitative, objective aspects** of test fixtures:

- **Framework Detection**: Syntactically unambiguous markers only (decorators, annotations, attributes)
  - Python: `@pytest.fixture`, `setUp()`/`tearDown()` methods
  - Java: `@Before`/`@After` annotations
  - JavaScript/TypeScript: Mocha/Jest `beforeEach()`/`afterEach()` and related patterns

- **Structural Metrics**: Lines of code, cyclomatic complexity, parameter counts, fixture type/scope
- **Mock Framework Usage**: Detection of mock object patterns within fixture code

**CSV exports** contain quantitative metrics. The SQLite database includes additional internal infrastructure for reproducibility and future research.

All fixture detectors include **comprehensive unit tests** ([tests/test_framework_detection.py](tests/test_framework_detection.py)) verifying:
- Correct framework identification across supported languages
- AST-based detection accuracy
- Cross-language consistency

See [docs/architecture/detection.md](docs/architecture/detection.md) for technical details on detection algorithms.

---

## Exploratory Data Analysis (EDA)

The following visualizations provide an overview of the FixtureDB corpus:

### Corpus Composition

**Repository Distribution and Pipeline Status**

![Repositories by Tier](docs/plots/01a_corpus_by_tier.png)

![Pipeline Status](docs/plots/01b_pipeline_status.png)

### Repository Timeline & Activity

**Creation Timeline and Activity Patterns**

![Repository Creation Timeline](docs/plots/02a_creation_timeline.png)

![Repository Recent Activity](docs/plots/02b_activity_recency.png)

### Fixture Overview

**Fixture Distribution and Scope Patterns**

![Fixture Distribution per Repository](docs/plots/03a_fixtures_per_repo.png)

![Fixture Scope Distribution](docs/plots/03b_fixture_scope.png)

### Mocking Practices

**Mock Usage and Framework Diversity**

![Mock Adoption Rate](docs/plots/04a_mock_adoption.png)

![Mocking Framework Usage](docs/plots/04b_framework_diversity.png)

### Fixture Type & Scope Distribution

**Detection Patterns and Execution Scopes**

![Fixture Types by Language](docs/plots/03c_fixture_types.png)

![Fixture Scopes Stacked Distribution](docs/plots/03d_fixture_scopes.png)

### Fixture Size & Complexity Analysis

**Lines of Code and Complexity Metrics**

![Lines of Code Distribution](docs/plots/04c_lines_of_code.png)

![Complexity Metrics Comparison](docs/plots/04d_complexity_metrics.png)

### Framework & Execution Patterns

**Framework-Specific Scope Adoption**

![Framework by Execution Scope](docs/plots/04e_framework_by_scope.png)

### Fixture Complexity Analysis

**Nesting, Reuse, and Complexity Patterns**

![Fixture Nesting Depth Distribution](docs/plots/05a_nesting_depth.png)

![Nesting vs Complexity Correlation](docs/plots/05b_nesting_complexity_correlation.png)

![Fixture Reuse Patterns](docs/plots/05c_fixture_reuse_distribution.png)

![Reuse vs Complexity Correlation](docs/plots/05d_reuse_complexity_correlation.png)

![Teardown Adoption Rate](docs/plots/05e_teardown_adoption.png)

### Test File Organization & Design Patterns

**File Characteristics and Fixture Design**

![Test File Characteristics](docs/plots/05g_test_file_characteristics.png)

![Fixture Design Patterns](docs/plots/05h_design_patterns.png)

### Repository Quality & Maturity

**Project Popularity vs Fixture Quality**

![Repository Maturity vs Fixture Quality](docs/plots/05i_repo_maturity.png)

## EDA Guides & Data Insights

Comprehensive exploratory data analysis documentation is available in the following guides:

| Guide | Purpose |
|-------|---------|
| [EDA_INDEX.md](EDA_INDEX.md) | Navigation guide for all EDA resources |
| [EDA_COMPLETE_SUMMARY.md](EDA_COMPLETE_SUMMARY.md) | Master reference: all improvements, integrations, and next steps |
| [EDA_IMPROVEMENTS_2026.md](EDA_IMPROVEMENTS_2026.md) | Detailed descriptions of all 8 new plots and their design rationale |
| [EDA_QUICK_REFERENCE.md](EDA_QUICK_REFERENCE.md) | Research workflows, CSV column mapping, and which plot to use for what question |
| [EDA_KEY_INSIGHTS.md](EDA_KEY_INSIGHTS.md) | Data-driven findings: language comparisons, fixture patterns, teardown adoption analysis |

**Quick Start:** Begin with [EDA_INDEX.md](EDA_INDEX.md) for overview and navigation to specific analysis goals.