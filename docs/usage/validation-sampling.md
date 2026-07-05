# Manual-Validation Sampling (Cochran's Formula)

For the paper, several pipeline outputs need a human-reviewed accuracy
sample: agent-repository detection, agent-signed commit detection, human
commit detection (in agent-enabled repos), and the extracted agent/human
fixtures themselves. `collection/validation_sampling.py` draws a
statistically-sized sample for a reviewer to manually check, sized with
Cochran's formula rather than an arbitrary fixed count.

**This tool is not part of the automatic phase pipeline.** It never runs on
its own — invoke it by hand, whenever a manual-validation sample is actually
needed, against whatever CSV(s) that pipeline step already produced.

## Methodology

Sample size uses Cochran's formula with the finite-population correction:

```
n0 = z^2 * p * (1 - p) / e^2
n  = n0 / (1 + (n0 - 1) / N)        (N = population size)
```

- `z` is derived from the confidence level (95% → z≈1.96) via `scipy.stats.norm.ppf`.
- `p` (assumed population proportion) defaults to 0.5 — Cochran's conservative
  choice when there's no prior estimate, since it maximizes the required
  sample size.
- `e` is the margin of error (default 0.05).
- The finite-population correction shrinks `n` for small populations, and the
  result is always capped at the population size (you can't sample more rows
  than exist).

Defaults match the paper's stated methodology: **95% confidence, 5% margin of
error**. Both are CLI flags, not hardcoded, in case a future validation step
needs different rigor.

**Sampling is deterministic by content, not just by seed.** Rows are sorted
by a hash of their full content before the seeded random sample is drawn, so
the exact same rows are selected for a given seed regardless of the order
rows happen to appear in the source CSV (which can vary run-to-run under
threaded export). This matters because the sampled rows are a citable
research artifact — re-running the tool against the same underlying data
must reproduce the same reviewed sample.

## The six steps

| `--step` | What it validates | Typical `--input` | Population |
|---|---|---|---|
| `agent-repos` | Agent-enabled repository detection | `github-search-agent/agent_repositories/*_agent_repo.csv` (all languages) | Combined — one pooled sample |
| `agent-commits-dataset-a` | Agent-signed commit detection | `github-search-agent/test-commits/*_agent_test_commit_qc.csv` (all languages) | Combined — one pooled sample |
| `human-commits-dataset-b` | Human commit detection in agent-enabled repos | `github-search-human/2025_test_commits/*_human_test_commit.csv` (all languages) | Combined — one pooled sample |
| `agent-fixtures-dataset-a` | Dataset A fixture extraction | `fixtures-from-agents/{language}_agent_fixtures.csv` | Per-language — one sample per file |
| `human-fixtures-dataset-b` | Dataset B fixture extraction (within-repo) | `fixtures-from-humans/same-repo/{language}_human_fixtures.csv` | Per-language — one sample per file |
| `human-fixtures-dataset-c` | Dataset C fixture extraction (cross-repo baseline) | `fixtures-from-humans/cross-repo/{language}_human_fixtures.csv` | Per-language — one sample per file |

The repo/commit-detection steps are language-agnostic: even though their QC
CSVs are split per language on disk, pass them all in one invocation and
they're pooled into a single population with one sample size. The fixture
steps are language-specific (extraction differs per language/grammar), so
each language file you pass is sampled as its own independent population,
producing one output CSV per file.

## Usage

```bash
# Combined-mode step: pool all languages into one sample
python -m collection.validation_sampling \
  --step agent-repos \
  --input github-search-agent/agent_repositories/python_agent_repo.csv \
          github-search-agent/agent_repositories/java_agent_repo.csv \
          github-search-agent/agent_repositories/javascript_agent_repo.csv \
          github-search-agent/agent_repositories/typescript_agent_repo.csv

# Per-language-mode step: one output per input file
python -m collection.validation_sampling \
  --step agent-fixtures-dataset-a \
  --input fixtures-from-agents/python_agent_fixtures.csv \
          fixtures-from-agents/java_agent_fixtures.csv

# Override confidence level / margin of error / seed
python -m collection.validation_sampling \
  --step human-fixtures-dataset-c \
  --input fixtures-from-humans/cross-repo/python_human_fixtures.csv \
  --confidence-level 0.99 --margin-error 0.03 --seed 7
```

Full flag reference: `python -m collection.validation_sampling --help`.

## Output

```
validation-samples/
  agent-repos/
    agent-repos_sample_<timestamp>.csv
    sample_metadata_<timestamp>.json
  agent-commits-dataset-a/
  human-commits-dataset-b/
  agent-fixtures-dataset-a/
    python_agent_fixtures_sample_<timestamp>.csv
    java_agent_fixtures_sample_<timestamp>.csv
    sample_metadata_<timestamp>.json
  human-fixtures-dataset-b/
  human-fixtures-dataset-c/
```

Each run also writes a `sample_metadata_<timestamp>.json` recording the
population size (N), computed sample size (n), confidence level, margin of
error, assumed proportion, and seed for every output file produced — this is
what the paper's methodology section should cite per validated step.

`validation-samples/` is committed to the repository (not gitignored): the
specific sampled rows are the actual artifact a reviewer checks against for
the paper's reported precision/recall figures, so they're a citable
research artifact rather than a disposable derivative like the pipeline's
DB/CSV outputs.

## See Also

- [Collection Architecture](../architecture/collection.md) — Dataset A/B/C build map
- [Configuration Reference](../architecture/configuration.md) — reference-data catalogs
