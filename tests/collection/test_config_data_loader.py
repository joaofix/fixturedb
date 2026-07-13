"""Guardrail tests for the config_data YAML catalogs and their loaders.

These exist to catch a malformed future edit to one of the YAML files
(typo, empty list, wrong shape) -- not to test collection logic itself.
"""

import re

from collection.config_data import (
    load_exclusion_keywords,
    load_feature_extraction_patterns,
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
    for section in ("unittest_setup", "pytest_class_method"):
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
    assert java_defs["annotations"]["@BeforeMethod"]["framework"] == "testng"
    # Only JUnit/TestNG are in scope -- Spring/Cucumber were removed (see
    # java.excluded) since they're not testing frameworks.
    assert "@Bean" not in java_defs["annotations"]
    assert "@Given" not in java_defs["annotations"]
    assert java_defs["excluded"], "java must document known boundary cases"


def test_fixture_definitions_javascript_typescript_shapes_and_scopes():
    js_defs = load_fixture_definitions()["javascript_typescript"]
    table = js_defs["hooks"]
    assert table, "hooks must have at least one entry"
    for fields in table.values():
        assert fields["scope"] in VALID_SCOPES
        assert fields["fixture_type"].strip()
    # Only Jest/Mocha/Vitest are in scope -- AVA/ts_decorators were removed
    # (see javascript_typescript.excluded) since AVA is niche and no real
    # package uses the ts_decorators convention.
    assert "ava_patterns" not in js_defs
    assert "ts_decorators" not in js_defs
    assert js_defs["excluded"], "javascript_typescript must document known boundary cases"


def _all_known_fixture_types() -> set[str]:
    """Every fixture_type value that fixture_definitions.yaml can produce
    (including the dormant junit4_before_class/after_class, kept in case
    the JUnit4/TestNG ambiguity is ever disambiguated -- see java.known_imprecisions)."""
    defs = load_fixture_definitions()
    types: set[str] = set()

    python_defs = defs["python"]
    types.add(python_defs["pytest_decorator"]["fixture_type"])
    types.add(python_defs["unittest_setup"]["fixture_type"])
    types.add(python_defs["pytest_class_method"]["fixture_type"])

    java_defs = defs["java"]
    types.update(f["fixture_type"] for f in java_defs["annotations"].values())
    types.update(java_defs["junit3_fallback"]["names"].values())
    for f in java_defs["ambiguous_annotations"].values():
        types.add(f["junit4_fixture_type"])
        types.add(f["testng_fixture_type"])

    js_defs = defs["javascript_typescript"]
    types.update(f["fixture_type"] for f in js_defs["hooks"].values())

    return types


def test_feature_extraction_patterns_has_expected_top_level_sections():
    patterns = load_feature_extraction_patterns()
    assert set(patterns) == {
        "mock_patterns",
        "mock_patterns_excluded",
        "mock_interaction_keywords",
        "external_call_patterns",
        "object_instantiation_patterns",
        "teardown_detection",
    }


def test_mock_patterns_excluded_are_documented():
    for entry in load_feature_extraction_patterns()["mock_patterns_excluded"]:
        assert entry["case"].strip() and entry["reason"].strip()


def test_mock_patterns_cover_expected_frameworks():
    """Guardrail for the .patch.object() gap fixed alongside this test:
    every framework we claim to support in docs must have at least one
    pattern, so a future edit can't silently drop one."""
    frameworks = {e["framework"] for e in load_feature_extraction_patterns()["mock_patterns"]}
    assert frameworks == {
        "unittest_mock",
        "pytest_mock",
        "pytest_monkeypatch",
        "mockito",
        "easymock",
        "jest",
        "sinon",
        "vitest",
        "gomock",
        "testify_mock",
    }


VALID_MOCK_CATEGORIES = {"dummy", "stub", "spy", "mock", "fake"}


def test_mock_patterns_have_valid_category():
    """Every mock_patterns entry must classify into the five-way classic
    test-double taxonomy (Meszaros): dummy/stub/spy/mock/fake."""
    for entry in load_feature_extraction_patterns()["mock_patterns"]:
        assert entry["category"] in VALID_MOCK_CATEGORIES, entry


def test_dummy_category_is_never_assigned():
    """Dummy detection requires data-flow analysis (is this double ever
    configured/verified?), not a simple keyword match -- per this project's
    preference for high-precision simple heuristics over completeness, no
    pattern should claim to detect it. If this ever fails, make sure the
    new "dummy" assignment is backed by a real, simple, high-precision
    signal, not a guess."""
    categories = {e["category"] for e in load_feature_extraction_patterns()["mock_patterns"]}
    assert "dummy" not in categories


def test_mock_patterns_category_overrides_are_documented():
    """Entries without a category keyword in their own construct name
    (i.e. the category isn't self-evident from the pattern) must carry a
    category_override_reason explaining the classification."""
    keyword_by_category = {
        "stub": "stub",
        "spy": "spy",
        "fake": "fake",
        "mock": "mock",
    }
    # Strip negative-lookbehind assertions (e.g. "(?<!mock\.)") before
    # searching for a keyword -- otherwise the bare-patch entries would
    # look like they self-evidently say "mock" just because the assertion
    # excluding mock./mocker. happens to contain that substring.
    lookbehind_re = re.compile(r"\(\?<[!=][^)]*\)")

    for entry in load_feature_extraction_patterns()["mock_patterns"]:
        keyword = keyword_by_category.get(entry["category"])
        construct_text = lookbehind_re.sub("", entry["pattern"]).lower()
        pattern_has_keyword = keyword is not None and keyword in construct_text
        if not pattern_has_keyword:
            assert entry.get("category_override_reason", "").strip(), entry


def test_mock_patterns_are_valid_regex_with_framework():
    for entry in load_feature_extraction_patterns()["mock_patterns"]:
        re.compile(entry["pattern"])
        assert entry["framework"].strip()


def test_external_call_patterns_are_valid_regex():
    for entry in load_feature_extraction_patterns()["external_call_patterns"]:
        re.compile(entry["pattern"])
        assert entry["matches"].strip()


def test_object_instantiation_patterns_are_valid_regex():
    for entry in load_feature_extraction_patterns()["object_instantiation_patterns"]:
        re.compile(entry["pattern"])
        assert entry["languages"] is None or isinstance(entry["languages"], list)


def test_mock_interaction_keywords_are_non_empty_strings():
    keywords = load_feature_extraction_patterns()["mock_interaction_keywords"]
    assert keywords
    for kw in keywords:
        assert isinstance(kw, str) and kw.strip()


def test_teardown_detection_pairs_reference_only_real_fixture_types():
    """Guardrail against the exact bug this catalog fixed: dead fixture
    types (nunit_setup, xunit_fact, ...) that no detector produces, and
    typos in fixture_type names, should never sneak back into the pairing
    tables."""
    known_types = _all_known_fixture_types()
    teardown = load_feature_extraction_patterns()["teardown_detection"]

    for fixture_type in teardown["yield_based_fixture_types"]:
        assert fixture_type in known_types, fixture_type

    for fixture_type, name_map in teardown["name_based_pairs"].items():
        assert fixture_type in known_types, fixture_type
        assert name_map, f"{fixture_type} must have at least one name pair"

    for setup_type, teardown_type in teardown["type_based_pairs"].items():
        assert setup_type in known_types, setup_type
        assert teardown_type in known_types, teardown_type


def test_teardown_detection_name_based_pairs_match_fixture_definitions_names():
    """The exact setup->teardown name pairs here must stay in sync with
    fixture_definitions.yaml's name maps (see the note in
    feature_extraction_patterns.yaml's name_based_pairs)."""
    python_defs = load_fixture_definitions()["python"]
    name_based = load_feature_extraction_patterns()["teardown_detection"][
        "name_based_pairs"
    ]

    for fixture_type, expected_names in (
        ("unittest_setup", {"setUp", "setUpClass", "setUpModule"}),
        ("pytest_class_method", {"setup_method", "setup_class"}),
    ):
        catalog_names = set(python_defs[fixture_type]["names"])
        pair_setup_names = set(name_based[fixture_type])
        assert pair_setup_names == expected_names
        assert pair_setup_names <= catalog_names
