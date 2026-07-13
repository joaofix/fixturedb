"""Loaders for reference-data catalogs kept as YAML instead of hardcoded Python.

Each catalog lives in its own file, next to this one, as plain data:
- non_code_extensions.yaml -- file extensions skipped during test-file scanning
- exclusion_keywords.yaml -- repo name/description keywords for boilerplate/toy repos
- framework_registry.yaml -- known testing frameworks per language
- language_configs.yaml -- per-language search and test-detection settings
- feature_extraction_patterns.yaml -- mock-framework/external-call/
  object-instantiation regex tables and setup/teardown pairing rules behind
  the quantitative fixture metrics (see that file's header comment)

fixture_definitions.yaml -- operational definition of "fixture" per language
(see that file's header comment for the schema and the per-language
`excluded` boundary-case catalog) -- lives in collection/heuristics/, not
here, alongside the other detection-heuristic catalogs (agent_heuristics.yaml,
agent-mining/); load_fixture_definitions() below reads it from there.

collection/config.py loads the first four and derives the module-level
constants (NON_CODE_EXTENSIONS, EXCLUSION_KEYWORDS, FRAMEWORK_REGISTRY,
LANGUAGE_CONFIGS) existing call sites already use; collection/detector_python.py,
detector_java.py, and detector_javascript.py load fixture_definitions.yaml and
derive their own pattern tables; collection/detector_shared.py and
complexity_provider.py load feature_extraction_patterns.yaml -- editing a
catalog is a YAML change, not a Python change.
"""

from pathlib import Path
from typing import Any, Dict, List

import yaml

_DATA_DIR = Path(__file__).parent
_HEURISTICS_DIR = Path(__file__).parent.parent / "heuristics"


def _load_yaml(filename: str, directory: Path = _DATA_DIR) -> Any:
    with (directory / filename).open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_non_code_extensions() -> List[str]:
    """Return the list of non-source-code file extensions to skip."""
    return _load_yaml("non_code_extensions.yaml")


def load_exclusion_keywords() -> List[str]:
    """Return repo name/description keywords that signal a boilerplate/toy repo."""
    return _load_yaml("exclusion_keywords.yaml")


def load_framework_registry() -> Dict[str, List[str]]:
    """Return the known-testing-framework catalog, keyed by language."""
    return _load_yaml("framework_registry.yaml")


def load_language_configs_data() -> Dict[str, Dict[str, Any]]:
    """Return raw per-language config field dicts, keyed by language."""
    return _load_yaml("language_configs.yaml")


def load_fixture_definitions() -> Dict[str, Any]:
    """Return the parsed fixture-definition catalog, keyed by language.

    Each per-language section holds both the executable pattern tables the
    detector modules build their lookups from, and an `excluded` list of
    documented boundary cases -- see fixture_definitions.yaml's header.
    Lives in collection/heuristics/, not config_data/ -- see this module's
    docstring.
    """
    return _load_yaml("fixture_definitions.yaml", directory=_HEURISTICS_DIR)


def load_feature_extraction_patterns() -> Dict[str, Any]:
    """Return the parsed feature-extraction pattern catalog.

    Holds mock_patterns, mock_interaction_keywords, external_call_patterns,
    object_instantiation_patterns, and teardown_detection (yield-based,
    name-based, and type-based setup/teardown pairing rules) -- see
    feature_extraction_patterns.yaml's header for the full schema.
    """
    return _load_yaml("feature_extraction_patterns.yaml")
