# Manual-Validation Sampling (Cochran's Formula)

For the paper, a subset of pipeline outputs needs a human-reviewed accuracy
sample — not every pipeline output, only the ones where a detection error
would actually mislabel or contaminate the study's data (see "Reduced
validation set" below). `collection/validation_sampling.py` draws a
statistically-sized sample for a reviewer to manually check, sized with
Cochran's formula rather than an arbitrary fixed count, and normalizes every
sample to one fixed reviewer-facing CSV schema regardless of which pipeline
step produced it.

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
error, seed 42**. All three are CLI flags, not hardcoded, in case a future
validation step needs different rigor — but the seed default should stay
fixed across runs so the paper's reported sample is reproducible.

**Sampling is deterministic by content, not just by seed.** Rows are sorted
by a hash of their full content before the seeded random sample is drawn, so
the exact same rows are selected for a given seed regardless of the order
rows happen to appear in the source CSV (which can vary run-to-run under
threaded export). This matters because the sampled rows are a citable
research artifact — re-running the tool against the same underlying data
must reproduce the same reviewed sample.

**Repo and commit steps are stratified**, not pooled-and-drawn-uniformly:
`agent-repos` stratifies by `language`; `agent-commits-dataset-a` stratifies
by `(language, agent_type)`. Each stratum gets a proportional share of the
total sample size (largest-remainder allocation, so the shares always sum
exactly to the computed `n`), so the reviewed set mirrors the corpus'
language/agent composition instead of skewing toward whichever language or
agent happens to dominate row count. `agent-fixtures-dataset-a` needs no
extra stratification: it already draws one independent sample per language
file (see "The three steps" below).

## Fixed output schema

Every validation CSV — regardless of step — has exactly these columns, in
this order:

| Column | Meaning |
|---|---|
| `validation_id` | Unique row identifier (`<step>-<n>`, e.g. `agent-repos-0001`) |
| `validation_type` | `repo` \| `commit` \| `fixture` |
| `language` | The item's language |
| `repo_full_name` | `owner/repo` slug |
| `item_id` | Repo full name / commit SHA / composite fixture key (`repo:commit:file:start_line`) |
| `item_url` | Direct clickable GitHub URL to the item being judged |
| `detection_signal` | What triggered detection (matched config filename, agent type, or fixture type) |
| `evidence` | Text for the reviewer to judge the detection against |
| `label` | Empty — reviewer fills in: `TP` \| `FP` \| `Unsure` \| `404` |
| `reviewer_notes` | Empty — reviewer fills in optional free text |

A `README.md` documenting this schema and the label vocabulary is written
(and refreshed) at the root of `validation-samples/` on every run, so it's
readable straight from the output directory without needing this doc.

### Per-type field mapping and known gaps

| | `repo` | `commit` | `fixture` |
|---|---|---|---|
| `item_url` | `https://github.com/{repo_full_name}` | `commit_url` column (or reconstructed from repo + SHA) | `github_url` column (already precomputed at collection time) |
| `detection_signal` | The matched agent-config filename (e.g. `CLAUDE.md`), or `agent_config_present` for CSVs collected before this column existed | `agent_type` (e.g. `claude`, `copilot`) | `fixture_type` (e.g. `pytest_decorator`) |
| `evidence` | Same as `detection_signal` — no full config-file content is captured today, so the filename is the best available evidence | `agent_type` + `commit_date` + author — **not** the commit message or diff text (see "Known gap" below) | `raw_source` — the full fixture source text |

**Known gap — commit evidence is best-effort.** The original spec for this
tool assumed commit message + diff lines were "stored in DB"; they aren't.
`agent_commit_counter.py` doesn't yet know which files in a commit are test
files (that's determined later, in `test_commit_filter.py`), and no diff
content is captured at all. Building real message/diff evidence would mean
new git-diff capture logic threaded through an earlier pipeline stage. Until
that exists, commit evidence is `agent_type`/`commit_date`/author only — a
reviewer judging a sampled commit needs to open `item_url` on GitHub to see
the actual message and diff.

**Repo/fixture evidence requires the current collector code.** The
`matched_config_file` and `raw_source` columns are populated by
`agent_repository_counter.py` and `agent_corpus.py`'s fixture CSV export,
respectively (as of the change that introduced the fixed schema above). CSVs
collected before that change won't have these columns; the tool falls back
to `agent_config_present` / an empty `evidence` string for those older files
rather than erroring.

## Reduced validation set

Not every pipeline output carries the same risk if its detection logic has
an error. The table below is the full inventory of candidate validation
targets and which ones actually warrant a human-reviewed sample, for a
reader who wants to judge the methodology without reading the source code.

| Validation target | Necessary? | Why |
|---|---|---|
| Agent repository detection | **Yes** | This is the corpus's entry point. A repository wrongly flagged as agent-enabled contaminates every commit and fixture derived from it downstream — an error here can't be caught later. |
| Agent commit detection | **Yes** | This is the paper's core attribution claim: that a specific commit was authored or co-authored by an AI coding agent. A detection error here directly mislabels a data point between the agent and human corpora. |
| Agent test-commit detection | No | Once a commit is already confirmed agent-authored, deciding whether it touches a test file is a mechanical file-path/pattern match, not an attribution judgment call — a code-correctness concern suited to ordinary unit tests, not manual review. |
| Agent fixture detection (per language) | **Yes** | Fixture extraction (AST-pattern-based, per language grammar) produces the metric-bearing unit of analysis for the whole study. A false positive/negative here directly changes reported fixture counts and characteristics. |
| Human test-commit detection | No | Uses the identical file-path/pattern-matching logic as agent test-commit detection, just applied to non-agent commits. Validating the agent side already exercises this same code path. |
| Human fixture detection (per language) | No | Uses the identical AST fixture detector as agent fixture detection (the same `detector.extract_fixtures()` call), just run against human-authored files instead of agent-authored ones. Validating Dataset A's fixture detection already covers this detector's correctness. |

Concretely, `collection/validation_sampling.py` only exposes `--step` choices
for the three "Yes" rows — the three "No" rows are deliberately not
selectable, so the tool's own surface area reflects this decision rather
than merely documenting it separately from the code.

## The three steps

| `--step` | What it validates | Typical `--input` | Population |
|---|---|---|---|
| `agent-repos` | Agent-enabled repository detection | `github-search-agent/agent_repositories/*_agent_repo.csv` (all languages) | Combined, stratified by language — rows with `has_agent_config != 1` are filtered out before sampling |
| `agent-commits-dataset-a` | Agent commit attribution | `github-search-agent/agent_commits/*_agent_commit.csv` (all languages) | Combined, stratified by `(language, agent_type)` |
| `agent-fixtures-dataset-a` | Dataset A fixture extraction | `fixtures-from-agents/{language}_agent_fixtures.csv` | Per-language — one sample per file |

The two detection steps are language-agnostic: even though their QC CSVs are
split per language on disk, pass them all in one invocation and they're
pooled into a single population, then a proportional sample is drawn per
language (and per agent type, for commits). The fixture step is
language-specific (extraction differs per language/grammar), so each
language file you pass is sampled as its own independent population,
producing one output CSV per file.

For `agent-repos`, only rows already flagged `has_agent_config=1` are
sampled — the source CSV also contains scanned-but-negative repos, and
validating "agent repository detection" means checking the claimed
positives, not the whole scanned candidate pool.

## Usage

```bash
# Combined-mode step: pool all languages into one stratified sample
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
  --step agent-fixtures-dataset-a \
  --input fixtures-from-agents/python_agent_fixtures.csv \
  --confidence-level 0.99 --margin-error 0.03 --seed 7
```

Full flag reference: `python -m collection.validation_sampling --help`.

## Output

```
validation-samples/
  README.md                          # schema + label vocabulary, refreshed every run
  agent-repos/
    agent-repos_sample_<timestamp>.csv
    sample_metadata_<timestamp>.json
  agent-commits-dataset-a/
  agent-fixtures-dataset-a/
    python_agent_fixtures_sample_<timestamp>.csv
    java_agent_fixtures_sample_<timestamp>.csv
    sample_metadata_<timestamp>.json
```

Each run also writes a `sample_metadata_<timestamp>.json` recording the
population size (N), computed sample size (n), confidence level, margin of
error, assumed proportion, and seed for every output file produced. For
stratified steps, it also includes a `strata` breakdown — each stratum's key
(e.g. `{"language": "python"}` or `{"language": "python", "agent_type":
"claude"}`), population size, and sample size — this is what the paper's
methodology section should cite per validated step.

`validation-samples/` is committed to the repository (not gitignored): the
specific sampled rows are the actual artifact a reviewer checks against for
the paper's reported precision/recall figures, so they're a citable
research artifact rather than a disposable derivative like the pipeline's
DB/CSV outputs.

## See Also

- [Collection Architecture](../architecture/collection.md) — Dataset A/B/C build map
- [Configuration Reference](../architecture/configuration.md) — reference-data catalogs
