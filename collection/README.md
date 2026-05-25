# Collection Package

This package implements the paired within-repository study for FixtureDB.

## Primary Command

```bash
python -m collection paired
```

The paired command samples repositories that contain both human and agent commits, extracts fixtures at the commit level, and writes a paired-study summary plus the study database.

## Command Reference

- `python -m collection paired` - run the paired study
- `python -m collection status` - print a short status message

The top-level wrapper `python pipeline.py paired` is equivalent.

## Study Model

- unit of comparison: commit
- pairing container: repository
- primary outcome: commit-level fixture observations
- statistical framing: paired comparisons within the same repository

This is intentionally not a human-vs-agent repository split. The repository provides the matching context for the pair, not a class label for the whole dataset.

## Internal Phases

The phase scripts remain available for lower-level inspection and troubleshooting, but they are implementation details of the paired pipeline rather than the main user workflow.
