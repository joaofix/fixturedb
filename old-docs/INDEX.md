# FixtureDB Documentation Index

Start here for navigation and use-case-specific guides.

## Quick Links (5 min)

| What do you want? | Start here |
|-------------------|-----------|
| **Overview** | [What is FixtureDB?](getting-started/intro.md) |
| **Get the data** | [Setup & Requirements](getting-started/setup.md) |
| **Run the pipeline** | [Running the Pipeline](getting-started/running.md) |
| **Analyze CSVs** | [Using the Dataset — CSV Analysis](usage/usage.md#use-case-2-analyzing-csv-exports) |
| **Query SQLite** | [Using the Dataset — SQLite Queries](usage/usage.md#use-case-1-querying-the-sqlite-database) |
| **Reproduce the corpus** | [Reproducing Results](usage/reproducing.md) |
| **Verify limitations** | [Limitations & Threats to Validity](reference/limitations.md) |
| **Understand metrics** | [Metrics Reference](architecture/metrics-reference.md) |

---

## By Use Case

### I want to analyze the data

- **CSV Exports:** [Using the Dataset for Analysis](usage/usage.md#use-case-2-analyzing-csv-exports)
- **Database Schema:** [Schema Reference](architecture/database-schema.md)
- **Metric Definitions:** [Metrics & Calculations](architecture/metrics-reference.md)

### I want to query SQL

- **SQLite Guide:** [Using the Dataset — SQL Queries](usage/usage.md#use-case-1-querying-the-sqlite-database)
- **Schema & Relationships:** [Database Schema](architecture/database-schema.md)

### I want to reproduce the paper

- **How-To:** [Reproducing the Corpus](usage/reproducing.md)
- **Configuration:** [Configuration Reference](architecture/configuration.md)
- **Detection Details:** [Fixture Detection Logic](architecture/detection.md)

### I want to understand limitations

- **Known Constraints:** [Limitations & Threats to Validity](reference/limitations.md)
- **Testing:** [Test Suite & Validation](reference/testing.md)

---

## All Documentation

**Getting Started**
- [What is FixtureDB?](getting-started/intro.md) — Overview & significance
- [Repository Structure](getting-started/repository-structure.md) — Project layout
- [Setup & Requirements](getting-started/setup.md) — Installation
- [Running the Pipeline](getting-started/running.md) — Command reference

**Architecture & Technical**
- [Database Schema](architecture/database-schema.md) — Tables, columns, relationships
- [Configuration Reference](architecture/configuration.md) — Tunable parameters
- [Fixture Detection Logic](architecture/detection.md) — AST parsing & metric computation
- [Metrics Reference](architecture/metrics-reference.md) — Tool usage & methodology
- [Data Pipeline Overview](architecture/data-pipeline-overview.md) — Extraction phases

**Data Collection & Export**
- [Data Collection Process](data/data-collection.md) — 5-phase pipeline
- [Storage & Scale](data/storage.md) — Disk usage estimates
- [CSV Export Guide](data/csv-export-guide.md) — Export formats
- [Language-Specific CSV Export](data/language-specific-csv-export.md) — Per-language extracts

**Usage & Analysis**
- [Using the Dataset](usage/usage.md) — SQL/CSV examples
- [Reproducing Results](usage/reproducing.md) — Corpus replication
- [Fixture Patterns Reference](usage/fixture-patterns-reference.md) — Fixture types & patterns

**Reference**
- [Limitations & Threats to Validity](reference/limitations.md) — Known constraints
- [Test Suite & Validation](reference/testing.md) — Test coverage & strategy
- [Academic References](reference/references.md) — Citations & grounding
- [License](reference/license.md) — MIT code, CC BY 4.0 data
- [Using the Dataset for Research](usage/usage.md)
- [Fixture Patterns Reference](usage/fixture-patterns-reference.md)

### Reference & Specs
- [Limitations & Validity](reference/limitations.md)
- [License](reference/license.md)
- [Testing Strategy](reference/testing.md)
- [Scientific References](reference/references.md)

## Quick Navigation

- **New to FixtureDB?** → [What is FixtureDB?](getting-started/intro.md)
- **How do I install?** → [Setup & Requirements](getting-started/setup.md)
- **How do I run it?** → [Running the Pipeline](getting-started/running.md)
- **Where's the data schema?** → [Database Schema](architecture/database-schema.md)
- **How do I analyze CSVs?** → [CSV User Guide](data/csv-user-guide.md)
- **How do I query SQLite?** → [Using the Dataset for Research](usage/usage.md)
- **What are the limitations?** → [Limitations & Validity](reference/limitations.md)

## Citation

FixtureDB: A Multi-Language Dataset of Test Fixture Definitions from Open-Source Software  
João Almeida, Andre Hora  
*ICSME 2026 — Tool Demonstration and Data Showcase Track*  

(DOI will be assigned upon Zenodo publication)

## License

- **Code:** MIT License — See [LICENSE](../LICENSE) or [reference/license.md](reference/license.md)
- **Dataset:** CC BY 4.0 — See [reference/license.md](reference/license.md)
