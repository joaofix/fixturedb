"""Guardrail tests for the config_data YAML catalogs and their loaders.

These exist to catch a malformed future edit to one of the YAML files
(typo, empty list, wrong shape) -- not to test collection logic itself.
"""

from collection.config_data import (
    load_exclusion_keywords,
    load_fixture_definitions,
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


VALID_SCOPES = {"per_test", "per_class", "per_module", "global"}


def test_fixture_definitions_covers_all_languages():
    defs = load_fixture_definitions()
    assert set(defs) == {"python", "java", "javascript_typescript"}


def test_fixture_definitions_python_shapes_and_scopes():
    python_defs = load_fixture_definitions()["python"]
    assert set(python_defs["pytest_decorator"]["scope_keyword_map"].values()) <= VALID_SCOPES
    for section in ("unittest_setup", "pytest_class_method", "nose_fixture"):
        names = python_defs[section]["names"]
        assert names, f"{section} must have at least one name"
        assert set(names.values()) <= VALID_SCOPES
    assert python_defs["excluded"], "python must document known boundary cases"
    for entry in python_defs["excluded"]:
        assert entry["case"].strip() and entry["reason"].strip()


def test_fixture_definitions_java_shapes_and_scopes():
    java_defs = load_fixture_definitions()["java"]
    for ann, fields in java_defs["annotations"].items():
        assert ann.startswith("@")
        assert fields["scope"] in VALID_SCOPES
        assert fields["fixture_type"].strip()
        assert fields["framework"].strip()
    for ann, fields in java_defs["ambiguous_annotations"].items():
        assert ann.startswith("@")
        assert fields["scope"] in VALID_SCOPES
        assert fields["framework"].strip()
    assert set(java_defs["junit3_fallback"]["names"].values()) == {
        "junit3_setup",
        "junit3_teardown",
    }
    assert java_defs["junit3_fallback"]["framework"] == "junit"
    # Spring/Cucumber annotations must not be mislabeled as generic "junit"
    # -- this was a known imprecision, fixed alongside this catalog.
    assert java_defs["annotations"]["@Bean"]["framework"] == "spring"
    assert java_defs["annotations"]["@Given"]["framework"] == "cucumber"
    assert java_defs["annotations"]["@BeforeMethod"]["framework"] == "testng"
    assert java_defs["excluded"], "java must document known boundary cases"


def test_fixture_definitions_javascript_typescript_shapes_and_scopes():
    js_defs = load_fixture_definitions()["javascript_typescript"]
    for section in ("hooks", "ava_patterns", "ts_decorators"):
        table = js_defs[section]
        assert table, f"{section} must have at least one entry"
        for fields in table.values():
            assert fields["scope"] in VALID_SCOPES
            assert fields["fixture_type"].strip()
    assert js_defs["excluded"], "javascript_typescript must document known boundary cases"
