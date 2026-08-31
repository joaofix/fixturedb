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

from .detector_shared import FixtureResult, _build_result, _get_parser, _source
from .heuristics import load_fixture_definitions

_DEFS = load_fixture_definitions()["python"]

PYTEST_SCOPE_KEYWORD_MAP: dict[str, str] = _DEFS["pytest_decorator"]["scope_keyword_map"]
PYTEST_FIXTURE_DECORATOR_RE = re.compile(_DEFS["pytest_decorator"]["match_pattern"])
UNITTEST_SETUP_NAMES: dict[str, str] = _DEFS["unittest_setup"]["names"]
PYTEST_CLASS_METHOD_NAMES: dict[str, str] = _DEFS["pytest_class_method"]["names"]


# ---------------------------------------------------------------------------
# pytest fixture setup/teardown/setup_and_teardown classification
# ---------------------------------------------------------------------------
#
# `pytest_decorator` fixtures can't be split into setup vs. teardown by
# fixture_type or name the way unittest_setup/pytest_class_method can (see
# internal-docs/methodology-improvements/pytest-yield-teardown-vs-fixture-kind.md
# for why that was, historically, left as "other" everywhere) -- a bare
# `@pytest.fixture` function is just whatever the developer named it, with an
# *optional* teardown phase expressed as code after a `yield`. The functions
# below classify that by reading the fixture's own body instead, and are
# consumed at RQ2 report-generation time by
# `research_questions/rq2.py::_kind()` (there's no persisted DB column for
# this -- see that module's docstring).


def _walk_excluding_nested_functions(node):
    """Yield `node` and every descendant, without descending into a nested
    function/lambda's own body -- a `yield` or `request.addfinalizer(...)`
    inside a nested `def` belongs to that inner function, not the fixture
    itself, and must not be attributed to it."""
    yield node
    if node.type in ("function_definition", "lambda"):
        return
    for child in node.children:
        yield from _walk_excluding_nested_functions(child)


def _contains_yield(body_node) -> bool:
    """True if `body_node` contains a `yield` anywhere at any nesting level
    (with-blocks, try/finally, conditionals, ...), excluding nested
    function/lambda bodies."""
    return any(n.type == "yield" for n in _walk_excluding_nested_functions(body_node))


def _contains_addfinalizer(body_node, source_text: bytes) -> bool:
    """True if `body_node` contains a call to `<anything>.addfinalizer(...)`
    anywhere (excluding nested function/lambda bodies). Matched on the
    method name alone -- not restricted to a receiver literally named
    `request` -- since some codebases alias the pytest fixture request
    object to a different parameter name."""
    for node in _walk_excluding_nested_functions(body_node):
        if node.type != "call":
            continue
        func = node.child_by_field_name("function")
        if func is None or func.type != "attribute":
            continue
        attr = func.child_by_field_name("attribute")
        if attr is not None and _source(attr, source_text) == "addfinalizer":
            return True
    return False


def _is_docstring_statement(stmt_node) -> bool:
    """True if `stmt_node` is a bare string-literal expression statement
    (a triple-quoted string on its own line) -- the tree-sitter shape of a
    docstring."""
    return (
        stmt_node.type == "expression_statement"
        and stmt_node.named_child_count == 1
        and stmt_node.named_children[0].type == "string"
    )


def _first_executable_statement(body_node):
    """The first statement in `body_node` that isn't a comment or a leading
    docstring, or None if the body has no such statement (empty body, or a
    body containing only a docstring)."""
    statements = [c for c in body_node.named_children if c.type != "comment"]
    if not statements:
        return None
    first = statements[0]
    if _is_docstring_statement(first):
        return statements[1] if len(statements) > 1 else None
    return first


def _is_bare_yield_statement(stmt_node) -> bool:
    """True if `stmt_node` is a standalone `yield` with no value (not
    `yield something`)."""
    if stmt_node.type != "expression_statement" or stmt_node.named_child_count != 1:
        return False
    expr = stmt_node.named_children[0]
    return expr.type == "yield" and expr.named_child_count == 0


def classify_pytest_fixture_kind(fixture_node, source_text: bytes) -> str:
    """Classify a pytest fixture's body into 'setup', 'teardown', or
    'setup_and_teardown'.

    `fixture_node` is the tree-sitter node for the fixture *function's
    body* (a function_definition's "body" field), `source_text` is the raw
    source bytes it was parsed from. Priority order (first match wins):

    1. `request.addfinalizer(...)` (any receiver) anywhere in the body ->
       'setup_and_teardown' -- addfinalizer always accompanies resource
       creation in the same fixture, so a fixture that registers a
       finalizer always sets something up first.
    2. No `yield` anywhere in the body -> 'setup' -- no yield means no
       teardown path exists.
    3. The first executable statement (docstrings/comments skipped) is a
       bare `yield` (no value) -> 'teardown' -- nothing before the yield
       is setup, and nothing is returned to the test; the fixture exists
       purely for its teardown phase.
    4. Everything else (a yield present but not first, or a valued yield
       as the first statement) -> 'setup_and_teardown' -- code before the
       yield is setup, code after is teardown; or the fixture both
       provides a value and has teardown.
    """
    if _contains_addfinalizer(fixture_node, source_text):
        return "setup_and_teardown"

    if not _contains_yield(fixture_node):
        return "setup"

    first_statement = _first_executable_statement(fixture_node)
    if first_statement is not None and _is_bare_yield_statement(first_statement):
        return "teardown"

    return "setup_and_teardown"


def classify_pytest_fixture_kind_from_source(raw_source: str) -> str:
    """`classify_pytest_fixture_kind()`, from a fixture's own standalone
    `def name(...): ...` source text (as stored in fixtures.raw_source --
    decorator excluded, re-parses cleanly on its own; same pattern as
    detector_shared.py::_detect_fixture_dependencies()).

    Not on the extraction hot path -- `_detect_python()` classifies
    pytest_decorator fixtures directly from the tree-sitter body node it
    already has, at detection time (see its own comment), and persists the
    result as fixtures.fixture_type_kind. This standalone, raw_source-string
    entry point exists for anything working from already-persisted
    raw_source text instead of a live AST node -- ad-hoc analysis, or
    backfilling fixture_type_kind into a database collected before that
    column existed.

    Returns 'other' if `raw_source` doesn't parse into a recognizable
    function body at all (empty string, non-Python text, or similar) --
    deliberately distinct from classify_pytest_fixture_kind()'s own
    'setup' answer for a genuinely empty *but valid* function body; this
    path means there was nothing to analyze in the first place, not that
    analysis concluded 'no teardown'.
    """
    try:
        src_bytes = raw_source.encode("utf-8")
        tree = _get_parser("python").parse(src_bytes)
    except Exception:
        return "other"

    func_node = next(
        (c for c in tree.root_node.children if c.type == "function_definition"),
        None,
    )
    if func_node is None:
        return "other"

    body_node = func_node.child_by_field_name("body")
    if body_node is None:
        return "other"

    return classify_pytest_fixture_kind(body_node, src_bytes)


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

                    result = _build_result(
                        func_node=func_def,
                        src_bytes=src_bytes,
                        fixture_type="pytest_decorator",
                        scope=scope,
                        framework="pytest",
                        language="python",
                    )
                    # Classified directly here, not by detector_shared.py's
                    # generic _classify_fixture_kinds() post-processing pass
                    # -- pytest_decorator can't be split by type/name (every
                    # pytest fixture is just named whatever the developer
                    # called it), so it needs body analysis instead, and the
                    # tree-sitter body node is already in hand right here
                    # (no need to re-parse raw_source later).
                    body_node = func_def.child_by_field_name("body")
                    if body_node is not None:
                        result.fixture_type_kind = classify_pytest_fixture_kind(
                            body_node, src_bytes
                        )
                    results.append(result)
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
