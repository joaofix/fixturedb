# FixtureDB Documentation Index

Start here for the between-group study comparing human and agent-authored test fixtures.

## Quick links

| What do you want? | Start here |
|-------------------|-----------|
| Overview | [What is FixtureDB?](getting-started/intro.md) |
| Install and configure | [Setup & Requirements](getting-started/setup.md) |
| Understand the repository layout | [Repository Structure](getting-started/repository-structure.md) |
| Run the collection pipeline | [Using the Pipeline](usage/reproducing.md) |
| Inspect the database schema | [Database Schema](architecture/database-schema.md) |
| Understand agent detection | [Agent Detection Methodology](architecture/agent-detection.md) |
| Read metric definitions | [Metrics Reference](architecture/metrics-reference.md) |
| Understand fixture patterns | [Fixture Patterns Reference](usage/fixture-patterns-reference.md) |
| Work with CSV exports | [CSV User Guide](data/csv-user-guide.md) |
| Analyze the dataset | [Analysis Guide](usage/usage.md) |
| Draw a manual-validation sample | [Manual-Validation Sampling](usage/validation-sampling.md) |
| Review limitations | [Limitations & Threats to Validity](reference/limitations.md) |
| Check tests and validation | [Test Suite & Validation](reference/testing.md)

## Core sections

### Getting started

- [What is FixtureDB?](getting-started/intro.md) — Between-group study design and data
- [Setup & Requirements](getting-started/setup.md) — Installation and configuration
- [Repository Structure](getting-started/repository-structure.md) — Project layout and organization

### Architecture

- [Database Schema](architecture/database-schema.md) — Between-group database structure
- [Agent Detection Methodology](architecture/agent-detection.md) — How agents are identified
- [Fixture Detection Logic](architecture/detection.md) — How fixtures are extracted
- [Metrics Reference](architecture/metrics-reference.md) — Metric definitions and calculations
- [Configuration Reference](architecture/configuration.md) — Configuration options

### Data and usage

- [Using the Dataset](usage/usage.md) — Analysis examples and SQL queries
- [Reproducing Results](usage/reproducing.md) — Three-stage collection pipeline
- [Fixture Patterns Reference](usage/fixture-patterns-reference.md) — Complete fixture catalog
- [Manual-Validation Sampling](usage/validation-sampling.md) — Cochran-formula sampling for human review
- [CSV User Guide](data/csv-user-guide.md) — CSV export documentation
- [Storage & Scale](data/storage.md) — Database sizes and storage requirements

### Reference

- [Limitations & Threats to Validity](reference/limitations.md) — Study limitations
- [Test Suite & Validation](reference/testing.md) — Testing documentation
- [Academic References](reference/references.md) — Citations and references
- [License](reference/license.md) — Licensing information

## Study Design

FixtureDB is a **between-group comparison across three independent datasets**:
Dataset A (agent-authored fixtures, 2025+), Dataset B (human-authored fixtures,
within-repo control, same repos and window as A), and Dataset C (human-authored
fixtures, cross-repo pre-2021 baseline). Agent identification uses Tier 1
detection (co-authored-by trailers, author signatures); comparisons are unpaired
(Mann-Whitney U / chi-square), since each dataset is its own database rather than
matched pairs in one table.

See [introduction](getting-started/intro.md) for the full methodology.

## Citation

FixtureDB: A Multi-Language Dataset of Test Fixture Definitions from Open-Source Software
João Almeida, Andre Hora
ICSME 2026 — Tool Demonstration and Data Showcase Track

## License

- Code: MIT License. See [LICENSE](../LICENSE) or [reference/license.md](reference/license.md).
- Dataset: CC BY 4.0. See [reference/license.md](reference/license.md).
