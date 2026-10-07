# FixtureDB

Replication package for the paper:

> **An empirical study on test fixture usage by coding agents on open source software**
> João Almeida, Andre Hora

FixtureDB collects test fixtures from open-source repositories. It compares
fixtures written by coding agents with fixtures written by humans before LLM
coding tools existed. The code covers Python, Java, JavaScript and TypeScript.

## Datasets

- **Dataset A (agent).** Fixtures from commits made by coding agents, in
  repositories that have agent configuration files.
- **Dataset C (human, pre-LLM).** Fixtures from repositories created from 2016
  to 2020, read at their last commit on or before 2020-12-31.

Details are in the [dataset card](docs/data/dataset-card.md).

## Quick start

```bash
pip install -r requirements.txt
python -m collection --help
python -m collection toy --dataset a --repos 5
pytest tests/
```

The toy run writes to `toy-dataset/`. It does not touch `datasets/` or `db/`.

## Documentation

- [Documentation index](docs/INDEX.md)
- [Setup](docs/getting-started/setup.md)
- [Research questions](docs/research-questions.md)
- [Reproducing the study](docs/usage/reproducing.md)
- [Limitations](docs/reference/limitations.md)

## Acknowledgments

Some agent-detection heuristics (co-authored-by trailer parsing, config-file
patterns for individual agents) were checked and improved against
[agent-mining](https://github.com/labri-progress/agent-mining), a catalog of AI
coding agent detection heuristics maintained by the
[LaBRI](https://www.labri.fr/) research group.
