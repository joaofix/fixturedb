# FixtureDB — Fixture Collection Pipeline

[![Tests & Coverage](https://github.com/joao-almeida/icsme-nier-2026/actions/workflows/coverage.yml/badge.svg)](https://github.com/joao-almeida/icsme-nier-2026/actions/workflows/coverage.yml)
![Coverage](./.github/coverage.svg)

Replication package for the paper:

> **FixtureDB: A Multi-Language Dataset of Test Fixture Definitions**
> João Almeida, Andre Hora
> *ICSME 2026 — Tool Demonstration and Data Showcase Track*

This repository contains the pipeline used to build FixtureDB and the study derived from it. The collection flow now includes a test-commit detection step before fixture extraction, and the study is a paired, within-repository commit-level comparison.

The central idea is simple:

- sample repositories that contain both human and agent commit histories
- detect commits that touch test files before extracting fixtures
- compare agent test commits against non-agent test commits inside the same repository
- store commit-level observations in one dataset for paired statistical analysis

## Primary Workflow

Run the study with:

```bash
python pipeline.py paired
```

or:

```bash
python -m collection paired
```

## What the Dataset Stores

- repository metadata and provenance
- commit-level observations for the paired comparison
- extracted fixtures and their structural metrics
- commit role labels used for paired analysis

The paired design keeps the comparison at the commit level and avoids forcing repositories into separate human and agent corpora.

## Quick Start

```bash
pip install -r requirements.txt
cp .env.example .env
# add your GITHUB_TOKEN

python -m collection paired
```

## Documentation

- [collection/README.md](collection/README.md) for the command reference
- [docs/getting-started/intro.md](docs/getting-started/intro.md) for the study overview
- [docs/split/README.md](docs/split/README.md) for the paired-study documentation set

## Tests

```bash
pytest tests/
pytest tests/collection/
```

## FixtureDB at a Glance

FixtureDB is a cross-language dataset of test fixture definitions extracted from open-source GitHub repositories. It records structural metrics and mock usage patterns for fixtures in Python, Java, JavaScript, and TypeScript.
