# FixtureDB — Fixture Collection Pipeline

[![Tests & Coverage](https://github.com/joao-almeida/icsme-nier-2026/actions/workflows/coverage.yml/badge.svg)](https://github.com/joao-almeida/icsme-nier-2026/actions/workflows/coverage.yml)
![Coverage](./.github/coverage.svg)

Replication package for the paper:

> **An empirical study on test fixture usage by coding agents on open source software**
> João Almeida, Andre Hora

FixtureDB is a between-group study of test fixtures extracted from agent-enabled GitHub repositories. It is the companion code for a master's degree thesis in Software Engineering. The collection pipeline detects agent commits, extracts fixtures, and compares agent-authored and human-authored test code within the same repositories. It also includes a separate human-only dataset collected from pre-agent repositories for inter-repository baseline comparison.

## Datasets

The repository contains three main datasets. The fixture collections will be regenerated during the next collection cycle.

- **fixtures-from-agents (Dataset A)** — Agent-authored test fixtures extracted from commits identified as agent-generated. This is the agent corpus for the within-repository comparison. The directory also includes stratified repository sample CSVs (e.g. `dataset_c_sample.csv`) for Dataset C.

- **fixtures-from-humans (Dataset B)** — Human-authored test fixtures extracted from the same repositories as Dataset A. This is the matched human control sample for the within-repository comparison.

- **Pre-agent Baseline (Dataset C)** — Human-authored test fixtures collected from pre-2022 software repositories that are independent from the agent-enabled corpus. This dataset serves as an inter-repository baseline. The repository sample files are stored under `fixtures-from-agents/` as `dataset_c_*.csv`.

## Methodology

FixtureDB covers **Python, Java, JavaScript, and TypeScript**. For each fixture it extracts structural, semantic, and usage metrics through tree-sitter AST analysis, Lizard complexity measurement, and framework-specific pattern matching.

| Metric | Description |
|--------|-------------|
| `loc` | Non-blank lines of code in the fixture body |
| `cyclomatic_complexity` | McCabe cyclomatic complexity of the fixture |
| `max_nesting_depth` | Maximum block nesting depth in the fixture body |
| `num_parameters` | Number of fixture parameters |
| `num_objects_instantiated` | Estimated object creations inside the fixture |
| `num_external_calls` | Estimated I/O or external library calls inside the fixture |
| `fixture_type` | Detected pattern (e.g. `pytest_decorator`, `unittest_setUp`) |
| `scope` | Execution scope (`per_test`, `per_class`, `per_module`, `global`) |
| `framework` | Detected testing framework (`pytest`, `unittest`, `junit`, `jest`, `mocha`, etc.) |
| `reuse_count` | Number of test functions that use this fixture |
| `has_teardown_pair` | Whether the fixture has a teardown or cleanup counterpart |
| `fixture_dependencies` | Other fixtures or setup functions this fixture depends on |
| `mock_usages` | Mock framework usages associated with the fixture |

## Documentation

| Topic | Document |
|-------|----------|
| Overview and methodology | [What is FixtureDB?](docs/getting-started/intro.md) |
| Installation and setup | [Setup & Requirements](docs/getting-started/setup.md) |
| Repository layout | [Repository Structure](docs/getting-started/repository-structure.md) |
| Running the pipeline | [Reproducing Results](docs/usage/reproducing.md) |
| Database schema | [Database Schema](docs/architecture/database-schema.md) |
| Agent detection | [Agent Detection](docs/architecture/agent-detection.md) |
| Fixture detection | [Fixture Detection](docs/architecture/detection.md) |
| Metric definitions | [Metrics Reference](docs/architecture/metrics-reference.md) |
| Fixture patterns | [Fixture Patterns Reference](docs/usage/fixture-patterns-reference.md) |
| CSV exports | [CSV User Guide](docs/data/csv-user-guide.md) |
| Analysis examples | [Analysis Guide](docs/usage/usage.md) |
| Limitations | [Limitations & Threats to Validity](docs/reference/limitations.md) |
| Tests | [Test Suite & Validation](docs/reference/testing.md) |

See the [full documentation index](docs/INDEX.md) for the complete set of guides.
