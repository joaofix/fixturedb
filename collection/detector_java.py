"""Java fixture detection: JUnit3/4/5, TestNG, Spring, Cucumber annotations.

Pattern tables are loaded from
collection/config_data/fixture_definitions.yaml rather than hardcoded here
-- see that file for the full operational definition of "fixture" per
language, including documented exclusions and known imprecisions (e.g. an
ambiguous @BeforeClass/@AfterClass is always attributed to TestNG).
"""

from .config_data import load_fixture_definitions
from .detector_shared import FixtureResult, _build_result, _source

_DEFS = load_fixture_definitions()["java"]

JUNIT_FIXTURE_ANNOTATIONS: dict[str, tuple[str, str, str]] = {
    ann: (fields["fixture_type"], fields["scope"], fields["framework"])
    for ann, fields in _DEFS["annotations"].items()
}

# Annotations that appear in both JUnit4 and TestNG (require context to disambiguate)
JUNIT_TESTNG_AMBIGUOUS: dict[str, tuple[str, str, str, str]] = {
    ann: (
        fields["junit4_fixture_type"],
        fields["testng_fixture_type"],
        fields["scope"],
        fields["framework"],
    )
    for ann, fields in _DEFS["ambiguous_annotations"].items()
}

# JUnit3-style setUp()/tearDown() methods with no annotation at all.
JUNIT3_FALLBACK_NAMES: dict[str, str] = _DEFS["junit3_fallback"]["names"]
JUNIT3_FALLBACK_SCOPE: str = _DEFS["junit3_fallback"]["scope"]
JUNIT3_FALLBACK_FRAMEWORK: str = _DEFS["junit3_fallback"]["framework"]


def _detect_java(tree, src_bytes: bytes, language: str = "java") -> list[FixtureResult]:
    results = []

    def visit(node):
        if node.type == "method_declaration":
            # Annotations in Java are inside the modifiers node
            annotations = []
            for c in node.children:
                if c.type == "modifiers":
                    # Look for marker_annotation or annotation inside modifiers
                    for mod_child in c.children:
                        if (
                            mod_child.type == "marker_annotation"
                            or mod_child.type == "annotation"
                        ):
                            annotations.append(_source(mod_child, src_bytes).strip())

            # Also check for direct annotation children (fallback)
            for c in node.children:
                if c.type == "marker_annotation" or c.type == "annotation":
                    annotations.append(_source(c, src_bytes).strip())

            for ann in annotations:
                # Strip parameter content for lookup
                ann_key = "@" + ann.lstrip("@").split("(")[0].strip()
                fixture_type = None
                scope = None
                framework = None

                # Handle ambiguous annotations (same name in JUnit4 and TestNG)
                if ann_key in JUNIT_TESTNG_AMBIGUOUS:
                    junit4_type, testng_type, scope, framework = JUNIT_TESTNG_AMBIGUOUS[
                        ann_key
                    ]
                    # Default to TestNG for backward compatibility with existing corpus
                    # TODO: Could improve by checking for TestNG-specific imports
                    fixture_type = testng_type
                elif ann_key in JUNIT_FIXTURE_ANNOTATIONS:
                    fixture_type, scope, framework = JUNIT_FIXTURE_ANNOTATIONS[ann_key]

                if fixture_type and scope:
                    results.append(
                        _build_result(
                            node=node,
                            func_node=node,
                            src_bytes=src_bytes,
                            fixture_type=fixture_type,
                            scope=scope,
                            framework=framework,
                            language="java",
                        )
                    )
                    break

            # JUnit 3 style: setUp() / tearDown() methods (no annotations, in TestCase subclass)
            # These are plain methods with specific names, not indicated by annotations
            name_node = node.child_by_field_name("name")
            if name_node:
                method_name = _source(name_node, src_bytes).strip()
                if method_name in JUNIT3_FALLBACK_NAMES:
                    # Check if not already matched by annotation
                    has_annotation = any(
                        ann
                        for ann in annotations
                        if "@Before" in ann or "@After" in ann
                    )
                    if not has_annotation:
                        results.append(
                            _build_result(
                                node=node,
                                func_node=node,
                                src_bytes=src_bytes,
                                fixture_type=JUNIT3_FALLBACK_NAMES[method_name],
                                scope=JUNIT3_FALLBACK_SCOPE,
                                framework=JUNIT3_FALLBACK_FRAMEWORK,
                                language="java",
                            )
                        )

        # Handle @Rule and @ClassRule field declarations
        elif node.type == "field_declaration":
            annotations = []
            for c in node.children:
                if c.type == "modifiers":
                    for mod_child in c.children:
                        if (
                            mod_child.type == "marker_annotation"
                            or mod_child.type == "annotation"
                        ):
                            annotations.append(_source(mod_child, src_bytes).strip())

            for ann in annotations:
                ann_key = "@" + ann.lstrip("@").split("(")[0].strip()
                if ann_key in ("@Rule", "@ClassRule"):
                    fixture_type, scope, framework = JUNIT_FIXTURE_ANNOTATIONS[ann_key]
                    results.append(
                        _build_result(
                            node=node,
                            func_node=node,
                            src_bytes=src_bytes,
                            fixture_type=fixture_type,
                            scope=scope,
                            framework=framework,
                        )
                    )
                    break

        for child in node.children:
            visit(child)

    visit(tree.root_node)
    return results
