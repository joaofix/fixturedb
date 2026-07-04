"""Guardrail tests for the config_data YAML catalogs and their loaders.

These exist to catch a malformed future edit to one of the YAML files
(typo, empty list, wrong shape) -- not to test collection logic itself.
"""

from collection.config_data import (
    load_exclusion_keywords,
    load_framework_registry,
    load_language_configs_data,
    load_non_code_extensions,
)


def test_non_code_extensions_are_dotted_lowercase_strings():
    extensions = load_non_code_extensions()
    assert extensions, "catalog must not be empty"
    for ext in extensions:
        assert isinstance(ext, str) and ext.startswith("."), ext
        assert ext == ext.lower(), f"{ext} should be lowercase"
    assert len(extensions) == len(set(extensions)), "no duplicate extensions"


def test_exclusion_keywords_are_non_empty_strings():
    keywords = load_exclusion_keywords()
    assert keywords, "catalog must not be empty"
    for kw in keywords:
        assert isinstance(kw, str) and kw.strip()


def test_framework_registry_covers_all_four_languages():
    registry = load_framework_registry()
    assert set(registry) == {"python", "java", "javascript", "typescript"}
    for language, frameworks in registry.items():
        assert frameworks, f"{language} must have at least one framework"
        for fw in frameworks:
            assert isinstance(fw, str) and fw.strip()


def test_language_configs_have_required_fields():
    data = load_language_configs_data()
    assert set(data) == {"python", "java", "javascript", "typescript"}
    required_fields = {
        "name",
        "github_language",
        "full_target",
        "test_path_patterns",
        "test_file_suffixes",
    }
    for lang, fields in data.items():
        assert required_fields.issubset(fields.keys()), lang
        assert fields["test_path_patterns"], f"{lang} needs test_path_patterns"
        assert fields["test_file_suffixes"], f"{lang} needs test_file_suffixes"
        assert isinstance(fields["full_target"], int) and fields["full_target"] > 0
