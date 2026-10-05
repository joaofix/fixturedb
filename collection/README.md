# Collection Package

This package implements the FixtureDB collection pipeline: two datasets
(A: agent-authored fixtures, C: human-authored cross-repo pre-2021 baseline),
built through one CLI with
uniform step verbs selected by `--dataset {a,c}`.

## Primary Command

```bash
python -m collection <verb> --dataset {a,c} [OPTIONS]
```

Every verb resolves its default input/output directories through
`collection/paths.py`. CSVs under `datasets/{a,c}/` are the real,
reviewable output of each stage; the per-dataset SQLite databases under
`db/` are secondary/derived.

## Command Reference

| Verb | a | c |
|---|---|---|
| `discover-repos` | ✓ | ✓ |
| `discover-commits` | ✓ | — |
| `filter-test-commits` | ✓ | — |
| `extract-fixtures` | ✓ | ✓ |
| `analyze-distribution --against Y` | ✓ | ✓ |
| `sample` | ✓ | ✓ |
| `export` | ✓ | ✓ |
| `validate` | ✓ | ✓ |
| `toy [--repos N]` | ✓ | ✓ |

Invoking a verb for a dataset it doesn't apply to (e.g. `discover-commits --dataset c`)
exits 1 with an explicit message rather than silently doing nothing.

Also: `python -m collection status` prints a short per-dataset status summary.

## Example: Dataset A end-to-end

```bash
python -m collection discover-repos      --dataset a --language python
python -m collection discover-commits    --dataset a
python -m collection filter-test-commits --dataset a
python -m collection extract-fixtures    --dataset a --repos-per-language 50
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

