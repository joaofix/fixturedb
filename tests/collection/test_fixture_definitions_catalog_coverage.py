"""Exhaustive, catalog-driven coverage of every fixture_definitions.yaml entry.

Same idea as tests/collection/test_mock_detection/test_mock_pattern_catalog_coverage.py,
applied to fixture detection instead of mock detection: rather than a
hand-picked selection of example fixtures, this file is parametrized
directly over every language/annotation/name entry in
collection/heuristics/fixture_definitions.yaml, and each case is driven
through the real extract_fixtures() pipeline (not a bare regex check --
fixture detection is AST-based, so this exercises the actual
detector_python.py / detector_java.py / detector_javascript.py code paths).

This is what caught real bugs, not just gaps, when first built: Java's
JUnit3 fallback (setUp()/tearDown() with no annotation) had no check for
class inheritance at all despite the YAML's own comment restricting it to
a TestCase subclass, and its "already matched by annotation" guard only
excluded "@Before"/"@After" substrings -- so a @Given-annotated method
named tearDown was detected twice, and a @Test-annotated method named
setUp was misclassified as a fixture. Both are now separately regression-
tested in tests/collection/test_extractor_unit/test_java_fixtures.py;
this file's job is breadth (every catalog entry fires at all), not those
specific regressions.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from collection.detector import extract_fixtures
from collection.heuristics import load_fixture_definitions

_DEFS = load_fixture_definitions()


def _run(code: str, language: str, ext: str):
    path = Path(tempfile.mktemp(suffix=ext))
    path.write_text(code)
    try:
        return extract_fixtures(path, language).fixtures
    finally:
        os.remove(path)


# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------

_PYTHON_DEFS = _DEFS["python"]


def _python_pytest_decorator_cases():
    cases = []
    decorator_info = _PYTHON_DEFS["pytest_decorator"]
    for keyword, scope in decorator_info["scope_keyword_map"].items():
        code = f"""
@pytest.fixture(scope='{keyword}')
def fx():
    return 1
"""
        cases.append(
            pytest.param(
                code, "pytest_decorator", scope, "pytest", id=f"pytest_decorator:scope={keyword}"
            )
        )
    cases.append(
        pytest.param(
            "@pytest.fixture\ndef fx():\n    return 1\n",
            "pytest_decorator",
            decorator_info["default_scope"],
            "pytest",
            id="pytest_decorator:no_explicit_scope",
        )
    )
    return cases


def _python_class_body_name_cases(group_key: str):
    """unittest_setup and pytest_class_method: names are methods inside a class."""
    cases = []
    info = _PYTHON_DEFS[group_key]
    for name, scope in info["names"].items():
        code = f"""
class T:
    def {name}(self):
        pass
"""
        cases.append(
            pytest.param(
                code, info["fixture_type"], scope, info["framework"],
                id=f"{group_key}:{name}",
            )
        )
    return cases


PYTHON_CASES = (
    _python_pytest_decorator_cases()
    + _python_class_body_name_cases("unittest_setup")
    + _python_class_body_name_cases("pytest_class_method")
)


@pytest.mark.parametrize("code,fixture_type,scope,framework", PYTHON_CASES)
def test_python_catalog_entry_detected(code, fixture_type, scope, framework):
    fixtures = _run(code, "python", ".py")
    matching = [f for f in fixtures if f.fixture_type == fixture_type]
    assert matching, f"No fixture of type {fixture_type!r} detected in:\n{code}"
    assert matching[0].scope == scope
    assert matching[0].framework == framework


def test_python_catalog_case_count_matches_yaml():
    """Guardrail: every name/keyword entry across all 3 python pattern
    groups must have a generated case -- if a future YAML edit adds a new
    name/scope keyword, this count must be updated alongside it (a silent
    mismatch here means the new entry isn't actually being exercised)."""
    expected = (
        len(_PYTHON_DEFS["pytest_decorator"]["scope_keyword_map"]) + 1  # + no-explicit-scope
        + len(_PYTHON_DEFS["unittest_setup"]["names"])
        + len(_PYTHON_DEFS["pytest_class_method"]["names"])
    )
    assert len(PYTHON_CASES) == expected


# ---------------------------------------------------------------------------
# Java
# ---------------------------------------------------------------------------

_JAVA_DEFS = _DEFS["java"]


def _java_annotation_cases():
    cases = []
    for ann, fields in _JAVA_DEFS["annotations"].items():
        ann_name = ann.lstrip("@")
        code = f"""
public class T {{
    {ann}
    public void m() {{
    }}
}}
"""
        cases.append(
            pytest.param(
                code, fields["fixture_type"], fields["scope"], fields["framework"],
                id=f"annotations:{ann_name}",
            )
        )
    return cases


def _java_ambiguous_annotation_cases():
    """Always resolves to the testng_* variant -- see known_imprecisions."""
    cases = []
    for ann, fields in _JAVA_DEFS["ambiguous_annotations"].items():
        ann_name = ann.lstrip("@")
        code = f"""
public class T {{
    {ann}
    public static void m() {{
    }}
}}
"""
        cases.append(
            pytest.param(
                code, fields["testng_fixture_type"], fields["scope"], fields["framework"],
                id=f"ambiguous_annotations:{ann_name}",
            )
        )
    return cases


def _java_junit3_fallback_cases():
    cases = []
    info = _JAVA_DEFS["junit3_fallback"]
    for name, fixture_type in info["names"].items():
        code = f"""
public class LegacyTest extends TestCase {{
    public void {name}() {{
    }}
}}
"""
        cases.append(
            pytest.param(
                code, fixture_type, info["scope"], info["framework"],
                id=f"junit3_fallback:{name}",
            )
        )
    return cases


JAVA_METHOD_CASES = (
    _java_annotation_cases()
    + _java_ambiguous_annotation_cases()
    + _java_junit3_fallback_cases()
)


@pytest.mark.parametrize("code,fixture_type,scope,framework", JAVA_METHOD_CASES)
def test_java_catalog_entry_detected(code, fixture_type, scope, framework):
    fixtures = _run(code, "java", ".java")
    matching = [f for f in fixtures if f.fixture_type == fixture_type]
    assert matching, f"No fixture of type {fixture_type!r} detected in:\n{code}"
    assert matching[0].scope == scope
    assert matching[0].framework == framework


def test_java_rule_field_declaration_cases():
    """@Rule/@ClassRule are field declarations, not methods -- a different
    AST shape/branch in detector_java.py, tested separately from the
    method-annotation cases above."""
    for ann in ("@Rule", "@ClassRule"):
        fields = _JAVA_DEFS["annotations"][ann]
        code = f"""
public class T {{
    {ann}
    public TemporaryFolder resource = new TemporaryFolder();
}}
"""
        fixtures = _run(code, "java", ".java")
        matching = [f for f in fixtures if f.fixture_type == fields["fixture_type"]]
        assert matching, f"No fixture detected for {ann} field declaration"
        assert matching[0].scope == fields["scope"]
        assert matching[0].framework == fields["framework"]
        assert matching[0].name == "resource"


def test_java_catalog_case_count_matches_yaml():
    expected = (
        len(_JAVA_DEFS["annotations"])
        + len(_JAVA_DEFS["ambiguous_annotations"])
        + len(_JAVA_DEFS["junit3_fallback"]["names"])
    )
    assert len(JAVA_METHOD_CASES) == expected


# ---------------------------------------------------------------------------
# JavaScript / TypeScript
# ---------------------------------------------------------------------------

_JS_DEFS = _DEFS["javascript_typescript"]


def _js_hook_cases():
    cases = []
    for name, fields in _JS_DEFS["hooks"].items():
        code = f"""
{name}(() => {{
    doSetup();
}});
"""
        cases.append(
            pytest.param(
                code, fields["fixture_type"], fields["scope"], id=f"hooks:{name}"
            )
        )
    return cases


JS_CALL_CASES = _js_hook_cases()


@pytest.mark.parametrize("code,fixture_type,scope", JS_CALL_CASES)
def test_javascript_catalog_entry_detected(code, fixture_type, scope):
    fixtures = _run(code, "javascript", ".test.js")
    matching = [f for f in fixtures if f.fixture_type == fixture_type]
    assert matching, f"No fixture of type {fixture_type!r} detected in:\n{code}"
    assert matching[0].scope == scope


def test_javascript_typescript_catalog_case_count_matches_yaml():
    expected_call = len(_JS_DEFS["hooks"])
    assert len(JS_CALL_CASES) == expected_call


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
