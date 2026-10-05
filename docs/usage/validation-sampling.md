# Manual validation

The automatic detectors can make mistakes. A reviewer checks a random sample of
their output by hand. The tool that draws the sample is
`collection/validation_sampling.py`. It is run by hand. It is not part of the
pipeline.

## What is validated

Only the steps where an error would change the study are sampled:

| `--step` | Checks | Input |
|----------|--------|-------|
| `agent-repos` | Repositories marked agent-enabled | `datasets/a/repos/*_repo.csv` |
| `agent-commits-dataset-a` | Commits marked as agent work | `datasets/a/commits/*_commit.csv` |
| `agent-fixtures-dataset-a` | Fixtures found in Dataset A | `datasets/a/fixtures/{language}_fixtures.csv` |
| `human-fixtures-dataset-c` | Fixtures found in Dataset C | `datasets/c/fixtures/{language}_fixtures.csv` |

Agent test-file matching is not sampled. It is a file-path match, which unit
tests cover.

## Sample size

The size is set by Cochran's formula with a finite-population correction:

```
n0 = z² · p · (1 − p) / e²
n  = n0 / (1 + (n0 − 1) / N)
```

The defaults are 95% confidence (z = 1.96), a margin of error of 0.05, p = 0.5
and seed 42. The sample is never larger than the population. All three
parameters are command-line flags.

Rows are sorted by a hash of their content before the seeded draw. The same
rows are picked for the same seed, whatever the input order.

For the two combined steps, the sample is stratified. `agent-repos` stratifies
by language. `agent-commits-dataset-a` stratifies by language and agent type.
Each stratum gets a share of the sample in proportion to its size.

For `agent-repos`, only rows with `has_agent_config = 1` are sampled.

## Usage

```bash
# Combined step: one sample across all languages
python -m collection.validation_sampling \
  --step agent-repos \
  --input datasets/a/repos/python_repo.csv datasets/a/repos/java_repo.csv

# Per-file step: one sample per input file
python -m collection.validation_sampling \
  --step agent-fixtures-dataset-a \
  --input datasets/a/fixtures/python_fixtures.csv

# Change the defaults
python -m collection.validation_sampling --step agent-fixtures-dataset-a \
  --input datasets/a/fixtures/python_fixtures.csv \
  --confidence-level 0.99 --margin-error 0.03 --seed 7
```

`python -m collection.validation_sampling --help` lists every flag.

## Output

Samples are written under `validation-samples/`. Each run writes a
`sample_metadata_<timestamp>.json` with the population size, the sample size,
the confidence level, the margin of error, the seed and the strata. Cite this
file when you report a validation result.

`validation-samples/` is committed to git. The sampled rows are the artifact a
reviewer checks, so they are kept with the code.

## Columns

Every sample file has the same columns:

| Column | Meaning |
|--------|---------|
| `validation_id` | Row id, for example `agent-repos-0001` |
| `validation_type` | `repo`, `commit` or `fixture` |
| `language` | Language of the item |
| `repo_full_name` | `owner/repo` |
| `item_id` | Repository name, commit SHA, or `repo:commit:file:line` |
| `item_url` | GitHub link to the item |
| `detection_signal` | What flagged the item: config file, agent type or fixture type |
| `evidence` | Text the reviewer checks the detection against |
| `label` | Reviewer fills in: `TP`, `FP`, `Unsure` or `404` |
| `reviewer_notes` | Reviewer fills in free text |

The schema and label list are also in `validation-samples/README.md`, which is
rewritten on every run.

## Known gaps

Commit evidence is thin. The sample has the agent type, the commit date and the
author, but not the commit message or the diff. The reviewer opens `item_url` to
read them. Adding the message and diff to the collected data would need a change
to the commit stage.

Older CSVs lack the `matched_config_file` and `raw_source` columns. For those,
the tool writes a placeholder in `evidence` instead of failing.
