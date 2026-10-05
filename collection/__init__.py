"""FixtureDB collection pipeline.

Agent-authored fixtures (Dataset A) are compared against pre-LLM human fixtures
from an independent repository pool (Dataset C). Every step is a verb of the
one CLI:

  python -m collection <verb> --dataset {a,c} [OPTIONS]

See docs/architecture/collection.md for the full pipeline.
"""

__version__ = "2.0.0"
__author__ = "João Almeida, Andre Hora"
