# Running the Pipeline

## Prerequisites

Before running the pipeline, download repository data from SEART-GHS:

1. **Visit** https://seart-ghs.si.usi.ch/
2. **Configure filters** for each language (Python, Java, JavaScript, TypeScript)
3. **Download CSV files** and place them in the `github-search/` directory

Required files:
```
github-search/
  ├── python-results.csv.gz
  ├── java-results.csv.gz
  ├── javascript-results.csv.gz
  └── typescript-results.csv.gz
```

See [Data Collection](../data/data-collection.md#phase-1--repository-loading-from-seart-ghs-search) 
for details on why SEART-GHS and how to obtain the data.

## Quick Start (Toy Dataset)

For rapid validation after code changes, use the toy dataset:

```bash
# Build toy dataset: 10 repos per language (~60 repos total)
python pipeline.py toy

# Toy dataset for a single language
python pipeline.py toy --language python
```

The `toy` command executes the full pipeline (load → clone → extract → classify)
on a small, representative sample of repositories. Completes in minutes and useful
for:
- Validating recent code changes
- Testing new features before full runs
- Debugging the collection pipeline
- Quick accuracy checks on fixture detection

## Full run (recommended)

```bash
# All languages, full targets (~4,800 repos loaded, ~3,000 expected to survive)
python pipeline.py run

# Single language, full target
python pipeline.py run --language python

# Smoke test with a small batch
python pipeline.py run --language python --max 20
```

The `run` command executes all phases in order: init → load → clone → extract → classify.

## Running phases independently

```bash
# Phase 1: load repos from SEART-GHS CSV (writes to DB, no cloning yet)
python pipeline.py load --language java --max 1000

# Phase 2: clone a batch of discovered repos
python pipeline.py clone --language java --batch 50

# Phase 3: extract fixtures from all cloned repos
python pipeline.py extract --language java

# Phase 4: assign domain labels
python pipeline.py classify

# Check current counts
python pipeline.py stats
```

Running phases independently is useful for incremental collection — you can
run `clone` and `extract` in a loop, processing repos in batches without
re-running the load phase.

## Validation (for the paper's precision/recall numbers)

```bash
# Step 1: generate a stratified sample (50 fixtures per language)
python pipeline.py validate --sample 50

# Step 2: open validation/sample_<timestamp>.csv
# For each row, read 'raw_source' and set 'is_true_fixture' to 1 or 0

# Step 3: compute precision
python pipeline.py validate --compute validation/sample_<timestamp>.csv
```

## Export (Zenodo deposit)

```bash
python pipeline.py export --version 1.0
# Produces: export/fixturedb_<date>.zip
```
