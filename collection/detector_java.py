"""Java fixture detection: JUnit3/4/5, TestNG, Spring, Cucumber annotations."""

from .detector_shared import FixtureResult, _build_result, _source

JUNIT_FIXTURE_ANNOTATIONS = {
    "@BeforeEach": ("junit5_before_each", "per_test"),
    "@BeforeAll": ("junit5_before_all", "per_class"),
    "@AfterEach": ("junit5_after_each", "per_test"),
    "@AfterAll": ("junit5_after_all", "per_class"),
    "@Before": ("junit4_before", "per_test"),
    "@After": ("junit4_after", "per_test"),
    "@BeforeMethod": ("testng_before_method", "per_test"),  # TestNG
    "@AfterMethod": ("testng_after_method", "per_test"),  # TestNG
    "@DataProvider": ("testng_data_provider", "per_test"),  # TestNG data-driven fixture
    "@Rule": ("junit_rule", "per_test"),  # JUnit @Rule fixture fields
    "@ClassRule": ("junit_class_rule", "per_class"),  # JUnit @ClassRule fixture fields
    # Spring Framework annotations
    "@Bean": ("spring_bean", "per_class"),  # Spring @Bean factory method
    "@TestConfiguration": (
        "spring_test_config",
        "per_class",
    ),  # Spring @TestConfiguration
    # Cucumber BDD step definitions
    "@Given": ("cucumber_given", "per_test"),  # Cucumber @Given step
    "@When": ("cucumber_when", "per_test"),  # Cucumber @When step
    "@Then": ("cucumber_then", "per_test"),  # Cucumber @Then step
    "@And": ("cucumber_and", "per_test"),  # Cucumber @And step (context-dependent)
    "@But": ("cucumber_but", "per_test"),  # Cucumber @But step (context-dependent)
    "@Attachment": ("cucumber_attachment", "per_test"),  # Cucumber @Attachment hook
}

# Annotations that appear in both JUnit4 and TestNG (require context to disambiguate)
JUNIT_TESTNG_AMBIGUOUS = {
    "@BeforeClass": ("junit4_before_class", "testng_before_class", "per_class"),
    "@AfterClass": ("junit4_after_class", "testng_after_class", "per_class"),
}


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

                # Handle ambiguous annotations (same name in JUnit4 and TestNG)
                if ann_key in JUNIT_TESTNG_AMBIGUOUS:
                    junit4_type, testng_type, scope = JUNIT_TESTNG_AMBIGUOUS[ann_key]
                    # Default to TestNG for backward compatibility with existing corpus
                    # TODO: Could improve by checking for TestNG-specific imports
                    fixture_type = testng_type
                elif ann_key in JUNIT_FIXTURE_ANNOTATIONS:
                    fixture_type, scope = JUNIT_FIXTURE_ANNOTATIONS[ann_key]

                if fixture_type and scope:
                    results.append(
                        _build_result(
                            node=node,
                            func_node=node,
                            src_bytes=src_bytes,
                            fixture_type=fixture_type,
                            scope=scope,
                            framework="junit",
                            language="java",
                        )
                    )
                    break

            # JUnit 3 style: setUp() / tearDown() methods (no annotations, in TestCase subclass)
            # These are plain methods with specific names, not indicated by annotations
            name_node = node.child_by_field_name("name")
            if name_node:
                method_name = _source(name_node, src_bytes).strip()
                if method_name in ("setUp", "tearDown"):
                    # Check if not already matched by annotation
                    has_annotation = any(
                        ann
                        for ann in annotations
                        if "@Before" in ann or "@After" in ann
                    )
                    if not has_annotation:
                        scope = "per_test"
                        fixture_type = (
                            "junit3_setup"
                            if method_name == "setUp"
                            else "junit3_teardown"
                        )
                        results.append(
                            _build_result(
                                node=node,
                                func_node=node,
                                src_bytes=src_bytes,
                                fixture_type=fixture_type,
                                scope=scope,
                                framework="junit",
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
                    fixture_type, scope = JUNIT_FIXTURE_ANNOTATIONS[ann_key]
                    results.append(
                        _build_result(
                            node=node,
                            func_node=node,
                            src_bytes=src_bytes,
                            fixture_type=fixture_type,
                            scope=scope,
                            framework="junit",
                        )
                    )
                    break

        for child in node.children:
            visit(child)

    visit(tree.root_node)
    return results
