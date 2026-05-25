# Phases

The paired pipeline still has internal stages, but they now serve a single commit-level study.

## Stage 1: Repository Discovery

Identify repositories with both human and agent commit history.

## Stage 2: Commit Role Scanning

Detect agent commits and collect matching non-agent commits within the same repository.

## Stage 3: Fixture Extraction

Extract fixtures at the commit level and attach provenance metadata.

## Stage 4: Observation Storage

Store the paired commit observations in the study database.

## Stage 5: Paired Analysis

Summarize the paired observations and prepare them for statistical analysis.

## Stage 6: Export and Validation

Write the paired-study summary and validate the resulting dataset.
