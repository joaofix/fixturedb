# Execution Guide

## Run the Study

```bash
python pipeline.py paired
```

or:

```bash
python -m collection paired
```

## Optional Filters

- `--language python` limits the run to one language
- `--repos-per-language N` changes the number of repositories considered per language
- `--max-commits-per-role N` limits how many commits are sampled per role in each repository

Example:

```bash
python -m collection paired --language python --repos-per-language 10 --max-commits-per-role 4
```

## Outputs

- `output/paired_study_summary_*.json`
- the study database written under `data/`
- extracted fixture records with commit-role labels

## Verification

After a run, inspect the latest paired-study summary and confirm that the repository-level pairs and commit-role counts look reasonable.
