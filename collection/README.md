# Collection Package

This package implements the FixtureDB collection pipeline: three datasets
(A: agent-authored fixtures, B: human-authored within-repo matched control,
C: human-authored cross-repo pre-2021 baseline), built through one CLI with
uniform step verbs selected by `--dataset {a,b,c}`.

## Primary Command

```bash
python -m collection <verb> --dataset {a,b,c} [OPTIONS]
```

Every verb resolves its default input/output directories through
`collection/paths.py`. CSVs under `datasets/{a,b,c}/` are the real,
reviewable output of each stage; the per-dataset SQLite databases under
`db/` are secondary/derived.

## Command Reference

| Verb | a | b | c |
|---|---|---|---|
| `discover-repos` | ✓ | ✓ (resolved from A) | ✓ |
| `discover-commits [--tier2]` | ✓ | — | — |
| `filter-test-commits` | ✓ | ✓ | — |
| `extract-fixtures` | ✓ | ✓ | ✓ |
| `analyze-distribution --against Y` | ✓ | ✓ | ✓ |
| `sample` | ✓ | ✓ | ✓ |
| `export` | ✓ | ✓ | ✓ |
| `validate` | ✓ | ✓ | ✓ |
| `toy [--repos N]` | ✓ | ✓ | ✓ |

Invoking a verb for a dataset it doesn't apply to (e.g. `discover-commits --dataset c`)
exits 1 with an explicit message rather than silently doing nothing.

Also: `python -m collection paired` bootstraps `db/corpus.db` (only needed for
`discover-commits --tier2`); `python -m collection status` prints a short
per-dataset status summary.

## Example: Dataset A end-to-end

```bash
python -m collection discover-repos      --dataset a --language python
python -m collection discover-commits    --dataset a
python -m collection filter-test-commits --dataset a
python -m collection extract-fixtures    --dataset a --repos-per-language 50
```

## Example: Dataset B end-to-end

Dataset B's repo population is by definition the same agent-enabled repos
Dataset A already found, so its `discover-repos` step resolves from Dataset
A's output rather than an independent GitHub search:

```bash
python -m collection discover-repos      --dataset b --language python
python -m collection filter-test-commits --dataset b
python -m collection extract-fixtures    --dataset b
```

## Example: Dataset C end-to-end

```bash
python -m collection discover-repos   --dataset c
python -m collection extract-fixtures --dataset c --language python
```

## Example: analyze, sample, export, validate

```bash
python -m collection analyze-distribution --dataset a --against b
python -m collection sample    --dataset a --target-count 5000
python -m collection export    --dataset a
python -m collection validate  --dataset a
```

## Toy runs

Before a full collection, smoke-test the same code path end-to-end at small
scale, entirely under `toy-dataset/` (structurally isolated from the real
`datasets/`/`db/` tree — every path is resolved with `root=TOY_ROOT`):

```bash
python -m collection toy --dataset a --repos 5
```

## Study Model (paired command)

`python -m collection paired` is a separate, rarely-run bootstrap that builds
`db/corpus.db`:

- unit of comparison: commit
- pairing container: repository
- primary outcome: commit-level fixture observations
- statistical framing: paired comparisons within the same repository

This is intentionally not a human-vs-agent repository split. The repository
provides the matching context for the pair, not a class label for the whole
dataset.
