"""Python fixture detection: pytest decorators, unittest/nose setup/teardown, Behave BDD steps."""

import re

from .detector_shared import FixtureResult, _build_result, _source


def _detect_python(
    tree, src_bytes: bytes, language: str = "python"
) -> list[FixtureResult]:
    results = []
    root = tree.root_node

    def visit(node):
        # pytest.fixture decorator pattern
        if node.type == "decorated_definition":
            decorators = [c for c in node.children if c.type == "decorator"]
            func_def = next(
                (c for c in node.children if c.type == "function_definition"), None
            )
            if not func_def:
                return

            for dec in decorators:
                dec_text = _source(dec, src_bytes)

                # pytest.fixture decorator
                if "fixture" in dec_text and "pytest" in dec_text:
                    scope = "per_test"
                    scope_match = re.search(r'scope\s*=\s*["\'](\w+)["\']', dec_text)
                    if scope_match:
                        scope_map = {
                            "function": "per_test",
                            "class": "per_class",
                            "module": "per_module",
                            "package": "per_module",
                            "session": "global",
                        }
                        scope = scope_map.get(scope_match.group(1), "per_test")

                    results.append(
                        _build_result(
                            node=node,
                            func_node=func_def,
                            src_bytes=src_bytes,
                            fixture_type="pytest_decorator",
                            scope=scope,
                            framework="pytest",
                            language="python",
                        )
                    )
                    break

                # BDD fixtures: Behave @given, @when, @then, @step decorators
                behave_match = re.search(r"@(given|when|then|step)\s*\(", dec_text)
                if behave_match:
                    fixture_type_map = {
                        "given": "behave_given",
                        "when": "behave_when",
                        "then": "behave_then",
                        "step": "behave_step",
                    }
                    fixture_type = fixture_type_map.get(
                        behave_match.group(1), "behave_step"
                    )
                    results.append(
                        _build_result(
                            node=node,
                            func_node=func_def,
                            src_bytes=src_bytes,
                            fixture_type=fixture_type,
                            scope="per_test",  # BDD steps are per-test
                            framework="behave",
                            language="python",
                        )
                    )
                    break

        # unittest setUp/tearDown inside TestCase subclass and setup_method/teardown_method
        elif node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = _source(name_node, src_bytes)

                # unittest-style fixtures: setUp/tearDown/setUpClass/tearDownClass/setUpModule/tearDownModule
                if name in (
                    "setUp",
                    "tearDown",
                    "setUpClass",
                    "tearDownClass",
                    "setUpModule",
                    "tearDownModule",
                ):
                    scope = (
                        "per_class"
                        if name in ("setUpClass", "tearDownClass")
                        else "per_test"
                    )
                    if "Module" in name:
                        scope = "per_module"
                    results.append(
                        _build_result(
                            node=node,
                            func_node=node,
                            src_bytes=src_bytes,
                            fixture_type="unittest_setup",
                            scope=scope,
                            framework="unittest",
                            language="python",
                        )
                    )

                # TestCase method style (setup_method/teardown_method)
                elif name in (
                    "setup_method",
                    "teardown_method",
                    "setup_class",
                    "teardown_class",
                ):
                    scope = (
                        "per_class"
                        if name in ("setup_class", "teardown_class")
                        else "per_test"
                    )
                    results.append(
                        _build_result(
                            node=node,
                            func_node=node,
                            src_bytes=src_bytes,
                            fixture_type="pytest_class_method",
                            scope=scope,
                            framework="pytest",
                            language="python",
                        )
                    )

                # Nose-style fixtures: setup/teardown/setup_module/teardown_module/setup_package/teardown_package
                elif name in (
                    "setup",
                    "teardown",
                    "setup_module",
                    "teardown_module",
                    "setup_package",
                    "teardown_package",
                ):
                    scope = "per_test"
                    if "module" in name:
                        scope = "per_module"
                    elif "package" in name:
                        scope = "per_module"
                    results.append(
                        _build_result(
                            node=node,
                            func_node=node,
                            src_bytes=src_bytes,
                            fixture_type="nose_fixture",
                            scope=scope,
                            language="python",
                        )
                    )

        for child in node.children:
            visit(child)

    visit(root)
    return results
