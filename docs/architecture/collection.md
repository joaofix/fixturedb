# Collection pipeline

The `collection/` package runs the pipeline. Each step is a verb of
`python -m collection`. The verbs are listed in
[Reproducing the study](../usage/reproducing.md).

## Dataset build

Each dataset calls one collector per verb. No code decides at run time which
dataset is being built.

| Dataset | `extract-fixtures` entry point | Collector |
|---------|-------------------------------|-----------|
| A (agent) | `extract-fixtures --dataset a` | `agent_corpus.AgentCorpusCollector` |
| C (human, pre-LLM) | `extract-fixtures --dataset c` | `dataset_c.collect_dataset_c_fixtures()` |

Dataset C has no commit history scan. It reads each repository once, at its
pinned commit. Dataset A reads commit history.

## Cloning

Three modules clone repositories. Pick the one that fits the job.

| Module | Use it for |
|--------|------------|
| `clone_primitives.py` | One clone into a temporary folder. No throttling, no database. |
| `ephemeral_clone.py` | The same, with a clone limit, free-disk checks and cleanup on exit. The collectors use this one. |
| `persistent_clone.py` | Clones into `clones/` and records the result in the database. |

Clones are removed when their context ends. `clones/` is the only folder that
grows large during a run. It can be deleted after the run.

A commit-history clone can be cut at a date with `shallow_since`. Dataset A uses
this. Dataset C does not, because it needs the last commit before a fixed date.

## Database writes

Extraction runs in worker threads. Only the calling thread writes to the
database. Each repository is written in one short transaction, so a crash loses
at most the repositories still in progress.

## Duplicate repositories

Some repositories appear under two names, for example after an organisation
transfer. The pipeline removes them at three points:

- Dataset A drops repositories that share the same current HEAD commit, before
  cloning.
- Dataset A drops commits that appear under more than one repository name, after
  collection.
- Dataset C checks each candidate against the others at its pinned commit.

The method and its limits are in
[Limitations](../reference/limitations.md#repository-data). The full analysis
is in `internal-docs/methodology-improvements/repo-deduplication.md`.

## Runbook

1. Set `clones/` to a folder with enough free space.
2. Run the Dataset C steps and the Dataset A steps. The order is not fixed.
3. Run `summarize`, then `sample`, `export` and `validate`, for each dataset.
4. For a manual check, run `collection/validation_sampling.py` on the step's
   output. See [Manual validation](../usage/validation-sampling.md).
5. Delete `clones/` when the run is finished.

## Troubleshooting

- **`database is locked`.** A caller is opening a second write transaction.
  Find the nested write and close it.
- **The disk fills up during a run.** Raise the free-space threshold in
  `ephemeral_clone.py`, and remove old clones with `prune_old_clones()`.
