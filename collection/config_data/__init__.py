"""Loaders for reference-data catalogs kept as YAML instead of hardcoded Python.

Each catalog lives in its own file, next to this one, as plain data:
- non_code_extensions.yaml -- file extensions skipped during test-file scanning
- exclusion_keywords.yaml -- repo name/description keywords for boilerplate/toy repos
- framework_registry.yaml -- known testing frameworks per language
- language_configs.yaml -- per-language search and test-detection settings
- fixture_definitions.yaml -- operational definition of "fixture" per language
  (see that file's header comment for the schema and the per-language
  `excluded` boundary-case catalog)

collection/config.py loads the first four and derives the module-level
constants (NON_CODE_EXTENSIONS, EXCLUSION_KEYWORDS, FRAMEWORK_REGISTRY,
LANGUAGE_CONFIGS) existing call sites already use; collection/detector_python.py,
detector_java.py, and detector_javascript.py load fixture_definitions.yaml and
derive their own pattern tables -- editing a catalog is a YAML change, not a
Python change.
"""

from pathlib import Path
from typing import Any, Dict, List

import yaml

_DATA_DIR = Path(__file__).parent


def _load_yaml(filename: str) -> Any:
    with (_DATA_DIR / filename).open("r", encoding="utf-8") as fh:
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
    """
    return _load_yaml("fixture_definitions.yaml")
