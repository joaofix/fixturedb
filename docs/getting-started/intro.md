# What is FixtureDB?

FixtureDB is the first **cross-language dataset of test fixture definitions** extracted from 160 open-source repositories across Python, Java, JavaScript, and TypeScript. It contains **~40,700 fixture definitions** and **~12,800 mock usages**, enabling empirical research on test fixture design patterns that was previously impossible at scale.

## Why FixtureDB Matters

Prior work on fixtures (TestHound, TestEvoHound) studied Java exclusively. Meanwhile, large-scale empirical studies (Hamster, Pan et al. 2025) reveal widespread gaps in understanding fixture design and mock usage **across languages**. FixtureDB closes this gap with:

- **First cross-language resource** treating fixtures as the primary unit of analysis
- **Structured quantitative metrics** (complexity, scope, mock usage, reuse patterns)
- **Multi-framework coverage** (pytest, unittest, JUnit 3–5, TestNG, Jest, Mocha, Vitest)
- **Reproducible methodology** (pinned commits, published on Zenodo)

## What Research Becomes Possible

With FixtureDB, researchers can now:
- **Compare fixture design patterns** across languages and frameworks
- **Analyze mock usage trends** in large-scale open-source projects
- **Study fixture complexity** and test modularity at scale
- **Identify testing best practices** grounded in real-world data
- **Baseline future work** on fixture quality, refactoring, or generation

## Dataset Composition

FixtureDB comprises:

- **Public CSV exports** — Quantitative metrics at multiple levels:
  - **Repository-level** (`repositories.csv`, `repository_statistics.csv`) — Metadata and aggregated metrics per repository
  - **Test-file-level** (`test_files.csv`, `test_file_statistics.csv`) — File paths and aggregated metrics per file
  - **Fixture-level** (`fixtures.csv`) — Individual fixture definitions with detailed metrics
- **Full SQLite database** — Complete dataset + internal infrastructure for reproducibility
- **Repository metadata** — GitHub stars, domain classification, contributor counts, pinned commits

**Recommended format:** 
- **CSV exports** for statistical analysis and paper writing (structure, complexity, scope distribution, mock adoption)
- **SQLite database** for verification, reproducibility, and detailed queries across levels
