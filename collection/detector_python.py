"""Python fixture detection: pytest decorators, unittest setup/teardown.

Only pytest and unittest are covered -- these are Python's two dominant,
actively-maintained testing frameworks. Other frameworks (nose, Behave) are
deliberately out of scope; see fixture_definitions.yaml's python.excluded
list for why.

Pattern tables (scope keyword maps, setup/teardown name -> scope maps) are
loaded from collection/heuristics/fixture_definitions.yaml rather than
hardcoded here -- see that file for the full operational definition of
"fixture" per language, including documented exclusions.

Async fixtures (async def, decorated with either @pytest.fixture or
@pytest_asyncio.fixture) are captured the same as sync ones: the decorator
text is the detection signal, not the function's async qualifier, and
@pytest_asyncio.fixture matches the same "pytest"+"fixture" substring check
as @pytest.fixture (pytest_asyncio fixtures are not a separate fixture_type)
-- see tests/collection/test_extractor_unit/test_python_fixtures.py::TestAsyncPythonFixtures.
"""

import re

from .detector_shared import FixtureResult, _build_result, _source
from .heuristics import load_fixture_definitions

_DEFS = load_fixture_definitions()["python"]

PYTEST_SCOPE_KEYWORD_MAP: dict[str, str] = _DEFS["pytest_decorator"]["scope_keyword_map"]
PYTEST_FIXTURE_DECORATOR_RE = re.compile(_DEFS["pytest_decorator"]["match_pattern"])
UNITTEST_SETUP_NAMES: dict[str, str] = _DEFS["unittest_setup"]["names"]
PYTEST_CLASS_METHOD_NAMES: dict[str, str] = _DEFS["pytest_class_method"]["names"]


def _detect_python(
    tree, src_bytes: bytes, language: str = "python"
) -> list[FixtureResult]:
    results = []
    root = tree.root_node
    # Functions already counted via their @pytest.fixture-style decorator --
    # visit() also reaches the same function_definition node as a plain
    # child of decorated_definition, so without this a method like
    # `@pytest.fixture(autouse=True) def setup_method(self):` would be
    # detected twice: once as pytest_decorator, once by name as
    # pytest_class_method. See toy Dataset B review (dagster-io/dagster
    # test_freshness_result_condition.py).
    decorator_matched_funcs: set[int] = set()

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
                if PYTEST_FIXTURE_DECORATOR_RE.search(dec_text):
                    scope = "per_test"
                    scope_match = re.search(r'scope\s*=\s*["\'](\w+)["\']', dec_text)
                    if scope_match:
                        scope = PYTEST_SCOPE_KEYWORD_MAP.get(
                            scope_match.group(1), "per_test"
                        )

                    results.append(
                        _build_result(
                            func_node=func_def,
                            src_bytes=src_bytes,
                            fixture_type="pytest_decorator",
                            scope=scope,
                            framework="pytest",
                            language="python",
                        )
                    )
                    decorator_matched_funcs.add(id(func_def))
                    break

        # unittest setUp/tearDown inside TestCase subclass and setup_method/teardown_method
        elif node.type == "function_definition" and id(node) not in decorator_matched_funcs:
            name_node = node.child_by_field_name("name")
            if name_node:
                name = _source(name_node, src_bytes)

                # unittest-style fixtures: setUp/tearDown/setUpClass/tearDownClass/setUpModule/tearDownModule
                if name in UNITTEST_SETUP_NAMES:
                    results.append(
                        _build_result(
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
                            func_node=node,
                            src_bytes=src_bytes,
                            fixture_type="pytest_class_method",
                            scope=PYTEST_CLASS_METHOD_NAMES[name],
                            framework="pytest",
                            language="python",
                        )
                    )

        for child in node.children:
            visit(child)

    visit(root)
    return results
