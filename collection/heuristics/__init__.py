"""Loader for the AI coding agent detection heuristics catalog.

The catalog itself lives in agent_heuristics.yaml, next to this file, as a
plain data file — see that file's header comment for the schema. This
module is the only place that reads it; collection/agent_patterns.py
consumes the parsed result and derives the shapes existing call sites
expect.
"""

from pathlib import Path
from typing import Any, Dict

import yaml

_HEURISTICS_PATH = Path(__file__).parent / "agent_heuristics.yaml"


def load_agent_heuristics(path: Path = _HEURISTICS_PATH) -> Dict[str, Any]:
    """Parse and return the agent heuristics catalog (file_based, commit_signatures, paper_scope)."""
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)
