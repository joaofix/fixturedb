"""Python fixture detection: pytest decorators, unittest/nose setup/teardown, Behave BDD steps.

Pattern tables (scope keyword maps, BDD type map, setup/teardown name ->
scope maps) are loaded from collection/config_data/fixture_definitions.yaml
rather than hardcoded here -- see that file for the full operational
definition of "fixture" per language, including documented exclusions.

Async fixtures (async def, decorated with either @pytest.fixture or
@pytest_asyncio.fixture) are captured the same as sync ones: the decorator
text is the detection signal, not the function's async qualifier, and
@pytest_asyncio.fixture matches the same "pytest"+"fixture" substring check
as @pytest.fixture (pytest_asyncio fixtures are not a separate fixture_type)
-- see tests/collection/test_extractor_unit/test_python_fixtures.py::TestAsyncPythonFixtures.
"""

import re

from .config_data import load_fixture_definitions
from .detector_shared import FixtureResult, _build_result, _source

_DEFS = load_fixture_definitions()["python"]

PYTEST_SCOPE_KEYWORD_MAP: dict[str, str] = _DEFS["pytest_decorator"]["scope_keyword_map"]
PYTEST_MATCH_SUBSTRINGS: list[str] = _DEFS["pytest_decorator"]["match_substrings"]
BEHAVE_TYPE_MAP: dict[str, str] = _DEFS["behave_steps"]["type_map"]
UNITTEST_SETUP_NAMES: dict[str, str] = _DEFS["unittest_setup"]["names"]
PYTEST_CLASS_METHOD_NAMES: dict[str, str] = _DEFS["pytest_class_method"]["names"]
NOSE_FIXTURE_NAMES: dict[str, str] = _DEFS["nose_fixture"]["names"]


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
                if all(s in dec_text for s in PYTEST_MATCH_SUBSTRINGS):
                    scope = "per_test"
                    scope_match = re.search(r'scope\s*=\s*["\'](\w+)["\']', dec_text)
                    if scope_match:
                        scope = PYTEST_SCOPE_KEYWORD_MAP.get(
                            scope_match.group(1), "per_test"
                        )

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
                    fixture_type = BEHAVE_TYPE_MAP.get(
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
                if name in UNITTEST_SETUP_NAMES:
                    results.append(
                        _build_result(
                            node=node,
                            func_node=node,
                            src_bytes=src_bytes,
                            fixture_type="unittest_setup",
                            scope=UNITTEST_SETUP_NAMES[name],
                            framework="unittest",
                            language="python",
                        )
                    )

                # TestCase method style (setup_method/teardown_method)
                elif name in PYTEST_CLASS_METHOD_NAMES:
                    results.append(
                        _build_result(
                            node=node,
                            func_node=node,
                            src_bytes=src_bytes,
                            fixture_type="pytest_class_method",
                            scope=PYTEST_CLASS_METHOD_NAMES[name],
                            framework="pytest",
                            language="python",
                        )
                    )

                # Nose-style fixtures: setup/teardown/setup_module/teardown_module/setup_package/teardown_package
                elif name in NOSE_FIXTURE_NAMES:
                    results.append(
                        _build_result(
                            node=node,
                            func_node=node,
                            src_bytes=src_bytes,
                            fixture_type="nose_fixture",
                            scope=NOSE_FIXTURE_NAMES[name],
                            language="python",
                        )
                    )

        for child in node.children:
            visit(child)

    visit(root)
    return results
