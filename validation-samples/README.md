# Manual-Validation Samples

Every CSV under `validation-samples/<step>/` shares one fixed schema so a
reviewer can open any of them without needing to know which pipeline step
produced it:

| Column | Meaning |
|---|---|
| `validation_id` | Unique row identifier (`<step>-<n>`), stable for a given sampling run |
| `validation_type` | `repo` \| `commit` \| `fixture` |
| `language` | Language of the item (`all` is never used -- each row's own language) |
| `repo_full_name` | `owner/repo` slug |
| `item_id` | repo full name / commit SHA / composite fixture key |
| `item_url` | Direct clickable GitHub URL to the item |
| `detection_signal` | What triggered detection (matched config filename, agent type, or fixture type) |
| `evidence` | Raw text/context for the reviewer to judge the detection against |
| `label` | Empty -- reviewer fills in: TP \| FP \| Unsure \| 404 |
| `reviewer_notes` | Empty -- reviewer fills in optional free text |

## Label values

- **TP** -- detection is correct.
- **FP** -- detection is wrong; this is not what was claimed.
- **Unsure** -- reviewer cannot determine with confidence from the available evidence.
- **404** -- artifact no longer accessible (repo went private, commit deleted, file
  removed). Excluded from the precision denominator, not counted as FP.

## Known gap

Commit `evidence` is currently best-effort (`agent_type` + `commit_date` +
author), not the commit message or diff text -- that data isn't captured by
the pipeline yet. See docs/usage/validation-sampling.md for details.

Each `sample_metadata_<timestamp>.json` alongside these CSVs records the
population size (N), sample size (n), confidence level, margin of error,
seed, and (for stratified steps) the per-stratum breakdown used to draw the
sample.
