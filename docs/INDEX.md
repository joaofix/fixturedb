# FixtureDB Documentation Index

Start here for the between-group study comparing human and agent-authored test fixtures.

## Quick links

| What do you want? | Start here |
|-------------------|-----------|
| Overview | [What is FixtureDB?](getting-started/intro.md) |
| Install and configure | [Setup & Requirements](getting-started/setup.md) |
| Understand the repository layout | [Repository Structure](getting-started/repository-structure.md) |
| Read the research questions | [Research Questions](research-questions.md) |
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

- [What is FixtureDB?](getting-started/intro.md)
- [Setup & Requirements](getting-started/setup.md)
- [Repository Structure](getting-started/repository-structure.md)
- [Research Questions](research-questions.md)

### Architecture

- [Database Schema](architecture/database-schema.md)
- [Agent Detection Methodology](architecture/agent-detection.md)
- [Fixture Detection Logic](architecture/detection.md)
- [Metrics Reference](architecture/metrics-reference.md)
- [Configuration Reference](architecture/configuration.md)

### Data and usage

- [Using the Dataset](usage/usage.md)
- [Reproducing Results](usage/reproducing.md)
- [Fixture Patterns Reference](usage/fixture-patterns-reference.md)
- [Manual-Validation Sampling](usage/validation-sampling.md)
- [CSV User Guide](data/csv-user-guide.md)
- [Storage & Scale](data/storage.md)

### Reference

- [Limitations & Threats to Validity](reference/limitations.md)
- [Test Suite & Validation](reference/testing.md)
- [Academic References](reference/references.md)
- [License](reference/license.md)

## Study Design

FixtureDB compares three independent datasets: Dataset A (agent-authored fixtures, 2025+), Dataset B (human-authored fixtures, a within-repo control using the same repos and window as A), and Dataset C (human-authored fixtures, a cross-repo pre-2021 baseline). Agent identification uses Tier 1 detection (co-authored-by trailers, author signatures). Comparisons are unpaired (Mann-Whitney U / chi-square), since each dataset is its own database rather than matched pairs in one table.

See the [introduction](getting-started/intro.md) for the full methodology.

## Citation

FixtureDB: A Multi-Language Dataset of Test Fixture Definitions from Open-Source Software
João Almeida, Andre Hora
ICPC 2027 — Research Track

## License

- Code: MIT License. See [LICENSE](../LICENSE) or [reference/license.md](reference/license.md).
- Dataset: CC BY 4.0. See [reference/license.md](reference/license.md).
