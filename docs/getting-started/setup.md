# Setup

## Requirements

- Python 3.12. This is the version the project is developed and tested with.
- Git on the `PATH`. Cloning and commit scans use it.
- A GitHub token is optional but recommended. Without one, the GitHub API limits
  requests much more tightly. Set `GITHUB_TOKEN` in the environment or in a
  `.env` file in the project root.

## Install

```bash
git clone <repo-url>
cd fixturedb

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Check that the CLI runs:

```bash
python -m collection --help
python -m collection status
```

`status` lists, for each dataset, which stages have output and whether its
database exists. On a fresh clone, everything shows as missing.

## Smoke test

Run a small collection on a toy set. It writes to `toy-dataset/`, never to
`datasets/` or `db/`:

```bash
python -m collection toy --dataset a --repos 5
python -m collection toy --dataset c --repos 5
```

## Run the tests

```bash
pytest tests/
```

The suite takes about a minute.

## Troubleshooting

**`No module named collection`.** Run the command from the project root.

**`no such table` when reading `db/a.db`.** The database was not created yet.
Run `extract-fixtures --dataset a` first.

**GitHub returns HTTP 403 or 429.** You hit the rate limit. Set `GITHUB_TOKEN`
and run the step again. Steps skip the repositories they already finished.

**`git: command not found`.** Install Git and check `git --version`.

## Next

- [Repository structure](repository-structure.md): where code and data live.
- [Reproducing the study](../usage/reproducing.md): the full collection run.
