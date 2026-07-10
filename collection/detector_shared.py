"""Cross-language plumbing shared by all `detector_<language>.py` modules.

Holds the tree-sitter parser cache, the `FixtureResult`/`MockResult`/
`ExtractResult` dataclasses, generic AST helpers (source extraction, LOC,
nesting depth), mock detection (one flat pattern table scanned regardless of
source language), the shared `_build_result()` fixture builder, and the
post-processing passes that need to see the whole fixture list at once
(dependency detection, scope propagation, teardown pairing) —
none of these can live in a single per-language file because they either
span languages or need the full fixture set as context.

The mock/external-call/object-instantiation regex tables and the
setup/teardown pairing rules are loaded from
collection/config_data/feature_extraction_patterns.yaml rather than
hardcoded here -- see that file for the full catalog and the reasoning
behind each pairing.
"""

import re
from dataclasses import dataclass, field
from typing import Optional

from collection.logging_utils import get_logger

from .complexity_provider import analyze_function_complexity
from .config_data import load_feature_extraction_patterns

logger = get_logger(__name__)

_PATTERNS = load_feature_extraction_patterns()

# ---------------------------------------------------------------------------
# Lazy-load Tree-sitter grammars to avoid import overhead when unused
# ---------------------------------------------------------------------------

_PARSERS: dict = {}


def _get_parser(language: str):
    """Return (and cache) a tree_sitter.Parser for the given language key."""
    if language in _PARSERS:
        return _PARSERS[language]

    try:
        import tree_sitter_java
        import tree_sitter_javascript
        import tree_sitter_python
        import tree_sitter_typescript
        from tree_sitter import Language, Parser

        lang_map = {
            "python": Language(tree_sitter_python.language()),
            "java": Language(tree_sitter_java.language()),
            "javascript": Language(tree_sitter_javascript.language()),
            "typescript": Language(tree_sitter_typescript.language_typescript()),
        }
        for key, lang in lang_map.items():
            p = Parser(lang)
            _PARSERS[key] = p

    except ImportError as e:
        raise ImportError(
            "tree-sitter language bindings not installed. "
            "Run: pip install -r requirements.txt"
        ) from e

    return _PARSERS[language]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class MockResult:
    """A single mock/stub usage detected inside a fixture body."""

    framework: str
    target_identifier: str
    num_interactions_configured: int
    raw_snippet: str
    category: str = ""  # test-double taxonomy: dummy/stub/spy/mock/fake -- see
    # feature_extraction_patterns.yaml's "Test-double category classification"


@dataclass
class FixtureResult:
    """A detected test fixture and its extracted structural/usage metrics."""

    name: str
    fixture_type: str  # see per-language constants below
    framework: Optional[str]  # testing framework: pytest, unittest, junit, nunit, testify, etc.
    scope: str  # per_test / per_class / per_module / global
    start_line: int
    end_line: int
    loc: int  # non-blank lines
    cyclomatic_complexity: int
    max_nesting_depth: int  # maximum block nesting level from Lizard
    num_objects_instantiated: int
    num_external_calls: int
    num_parameters: int
    has_teardown_pair: int = 0  # 1 if teardown/cleanup logic exists, 0 otherwise
    fixture_dependencies: list[str] = field(
        default_factory=list
    )  # list of fixture names this fixture depends on (Phase 4)
    raw_source: str = ""
    mocks: list[MockResult] = field(default_factory=list)


@dataclass
class ExtractResult:
    """Result of extracting fixtures from a file, including file-level metrics."""

    fixtures: list[FixtureResult]
    file_loc: int  # non-blank lines in the file
    num_test_functions: int  # count of test functions in the file


# ---------------------------------------------------------------------------
# Shared AST utilities
# ---------------------------------------------------------------------------


def _source(node, src_bytes: bytes) -> str:
    """Extract source code text for a tree-sitter node."""
    return src_bytes[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _count_loc(text: str) -> int:
    """Count non-blank lines of code in a text string."""
    return sum(1 for line in text.splitlines() if line.strip())


def _count_file_loc(src_bytes: bytes) -> int:
    """Count non-blank lines of code in a source file."""
    try:
        text = src_bytes.decode("utf-8", errors="replace")
        return _count_loc(text)
    except (AttributeError, ValueError) as e:
        logger.debug(f"Failed to count LOC: {e}")
        return 0


def _compute_nesting_depth(node) -> int:
    """
    Compute maximum nesting depth of a function body using Tree-sitter AST.

    Returns the maximum level of nested blocks (if, for, while, try, etc.)
    within the function. Level 1 = no nesting, Level 2+ = nested blocks.

    This is used because Lizard's max_nesting_depth doesn't work properly
    for function-level analysis (returns 0).
    """
    max_depth = 1

    # Each of these node types is itself the one unit of nesting a control
    # construct contributes. Their body is a generic wrapper node ("block" in
    # Python/Java, "def" is just the literal `def` keyword token) that must
    # NOT also be counted, or every level gets bumped twice: once for e.g.
    # `if_statement`, again for the `block` node that is that statement's own
    # body. Likewise `catch_clause`/`finally_clause` are alternate branches of
    # the *same* `try_statement` nesting level, not an additional level nested
    # inside it, so they are deliberately excluded too.
    block_types = {
        "if_statement",
        "while_statement",
        "for_statement",
        "try_statement",
        "with_statement",
        "class_definition",
        "for_in_statement",
        "foreach_statement",
        "enhanced_for_statement",
        "do_statement",
    }

    def visit(node, current_depth=1):
        nonlocal max_depth

        if node.type in block_types:
            current_depth += 1
            max_depth = max(max_depth, current_depth)

        for child in node.children:
            visit(child, current_depth)

    visit(node)
    return max_depth


# ---------------------------------------------------------------------------
# Helper functions for metrics extraction
# ---------------------------------------------------------------------------


EXTERNAL_CALL_PATTERNS: list[str] = [
    entry["pattern"] for entry in _PATTERNS["external_call_patterns"]
]


def _count_external_calls(node, src_bytes: bytes) -> int:
    """
    Count calls that look like external I/O or system operations.

    This is a custom regex-based assessment since Lizard's fan_out metric
    measures inter-function calls within the same module, not external I/O.

    Detects patterns like: database, network, file I/O, and subprocess calls.
    """
    text = _source(node, src_bytes).lower()
    return sum(len(re.findall(p, text)) for p in EXTERNAL_CALL_PATTERNS)


# ---------------------------------------------------------------------------
# Constants for snippet extraction and thresholds
# ---------------------------------------------------------------------------

SNIPPET_CONTEXT_BEFORE = 20  # characters before match in mock detection
SNIPPET_CONTEXT_AFTER = 60  # characters after match in mock detection

# ---------------------------------------------------------------------------
# Mock detection (language-agnostic heuristic pass)
# ---------------------------------------------------------------------------

MOCK_PATTERNS: list[tuple[str, str, str]] = [
    (entry["pattern"], entry["framework"], entry["category"])
    for entry in _PATTERNS["mock_patterns"]
]

MOCK_INTERACTION_PATTERN = "|".join(_PATTERNS["mock_interaction_keywords"])


def _extract_mocks(node, src_bytes: bytes) -> list[MockResult]:
    text = _source(node, src_bytes)
    found = []
    for pattern, framework, category in MOCK_PATTERNS:
        for m in re.finditer(pattern, text):
            target = m.group(1) if m.lastindex and m.lastindex >= 1 else ""
            snippet_start = max(m.start() - SNIPPET_CONTEXT_BEFORE, 0)
            snippet_end = min(m.end() + SNIPPET_CONTEXT_AFTER, len(text))
            snippet = text[snippet_start:snippet_end].replace("\n", " ")

            # Count .return_value / .side_effect / when(...).thenReturn style
            interactions = len(
                re.findall(
                    MOCK_INTERACTION_PATTERN,
                    text[m.start() : m.end() + 200],
                )
            )

            found.append(
                MockResult(
                    framework=framework,
                    target_identifier=target,
                    num_interactions_configured=interactions,
                    raw_snippet=snippet,
                    category=category,
                )
            )
    return found


# ---------------------------------------------------------------------------
# Shared result builder
# ---------------------------------------------------------------------------


def _find_name_node(func_node):
    """Return the identifier node naming this fixture, if any.

    Handles both function/method-shaped nodes (a direct "name" field) and
    Java field_declaration nodes (e.g. @Rule/@ClassRule fixture fields),
    whose name lives one level down on their variable_declarator child
    instead -- field_declaration itself has no "name" field.
    """
    name_node = func_node.child_by_field_name("name")
    if name_node:
        return name_node
    for child in func_node.children:
        if child.type == "variable_declarator":
            return child.child_by_field_name("name")
    return None


def _build_result(
    func_node,
    src_bytes: bytes,
    fixture_type: str,
    scope: str,
    framework: Optional[str] = None,
    language: str = "python",
) -> FixtureResult:
    """Build a FixtureResult from a single node spanning the whole fixture.

    Every metric (line range, raw_source, external calls, mocks, complexity)
    is derived from this one node. Python's pytest-decorator/behave-step
    detection used to pass a wider `decorated_definition` node for the line
    range/external-calls/mocks scan while using the bare `function_definition`
    for raw_source/complexity -- so a fixture's reported line range disagreed
    with its own raw_source text by exactly the decorator line, and an
    `open(...)`/`MagicMock()` call sitting in the decorator's own arguments
    (e.g. `@pytest.fixture(params=[...])`) leaked into that fixture's
    num_external_calls/mocks even though it isn't part of the fixture body.
    Callers now always pass the fixture's own function/method node (decorator
    excluded), never the decorated wrapper.
    """
    src_text = _source(func_node, src_bytes)
    name_node = _find_name_node(func_node)
    name = (
        _source(name_node, src_bytes)
        if name_node
        else f"<anonymous>_{func_node.start_point[0]}"
    )

    # Get metrics from Lizard via complexity_provider
    # Includes: cyclomatic_complexity, num_parameters
    metrics = analyze_function_complexity(src_text, language)

    if language == "python":
        # Lizard counts `self`/`cls` as an ordinary parameter, inflating
        # num_parameters by 1 for nearly every unittest/pytest-class-method/
        # nose-style fixture (anything defined as a method, not a bare
        # function). Java/JS/TS have no equivalent implicit first parameter,
        # so this override is Python-only.
        metrics["num_parameters"] = len(_extract_parameter_names(func_node, src_bytes))

    # Compute nesting depth from AST (Lizard's max_nesting_depth doesn't work for functions)
    nesting_depth = _compute_nesting_depth(func_node)

    return FixtureResult(
        name=name,
        fixture_type=fixture_type,
        framework=framework,
        scope=scope,
        start_line=func_node.start_point[0] + 1,
        end_line=func_node.end_point[0] + 1,
        loc=_count_loc(src_text),  # Custom counting (non-blank lines)
        cyclomatic_complexity=metrics.get("cyclomatic_complexity", 1),
        max_nesting_depth=nesting_depth,
        num_objects_instantiated=metrics.get(
            "num_objects_instantiated", 0
        ),  # Via Lizard + post-processing
        num_external_calls=_count_external_calls(
            func_node, src_bytes
        ),  # Custom regex for I/O patterns
        num_parameters=metrics.get("num_parameters", 0),
        has_teardown_pair=0,  # Calculated in post-processing
        raw_source=src_text,
        mocks=_extract_mocks(func_node, src_bytes),
    )


# ---------------------------------------------------------------------------
# Test function counting helpers
# ---------------------------------------------------------------------------


def _count_test_functions_python(tree, src_bytes: bytes) -> int:
    """Count test functions/methods in Python (test_* or inside TestCase)."""
    count = 0

    def visit(node):
        nonlocal count
        if node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = _source(name_node, src_bytes)
                if name.startswith("test_"):
                    count += 1
        for child in node.children:
            visit(child)

    visit(tree.root_node)
    return count


def _count_test_functions_java(tree, src_bytes: bytes) -> int:
    """Count test methods in Java (annotated with @Test or similar)."""
    count = 0
    test_annotations = {
        "@Test",
        "@Before",
        "@After",
        "@BeforeClass",
        "@AfterClass",
        "@BeforeEach",
        "@AfterEach",
    }

    def visit(node):
        nonlocal count
        if node.type == "method_declaration":
            # Check for test annotations
            for c in node.children:
                if c.type == "modifiers":
                    for mod_child in c.children:
                        if mod_child.type in ("marker_annotation", "annotation"):
                            ann_text = _source(mod_child, src_bytes).strip()
                            if any(ann_text.startswith(ta) for ta in test_annotations):
                                count += 1
                                return
            # Count methods starting with test (heuristic fallback)
            name_node = node.child_by_field_name("name")
            if name_node:
                name = _source(name_node, src_bytes)
                if name.startswith("test"):
                    count += 1
        for child in node.children:
            visit(child)

    visit(tree.root_node)
    return count


def _count_test_functions_js(tree, src_bytes: bytes) -> int:
    """Count test blocks in JavaScript/TypeScript (describe, it, test calls)."""
    count = 0

    def visit(node):
        nonlocal count
        if node.type == "call_expression":
            func = node.child_by_field_name("function")
            if func:
                func_name = _source(func, src_bytes).strip().split("(")[0].strip()
                if func_name in ("it", "test", "describe"):
                    count += 1
        for child in node.children:
            visit(child)

    visit(tree.root_node)
    return count


def _count_test_functions_go(tree, src_bytes: bytes) -> int:
    """Count test functions in Go (functions starting with Test)."""
    count = 0

    def visit(node):
        nonlocal count
        if node.type == "function_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = _source(name_node, src_bytes)
                if name.startswith("Test"):
                    count += 1
        elif node.type == "method_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = _source(name_node, src_bytes)
                if name.startswith("Test"):
                    count += 1
        for child in node.children:
            visit(child)

    visit(tree.root_node)
    return count


def _count_test_functions(tree, src_bytes: bytes, language: str) -> int:
    """Dispatch to language-specific test function counter."""
    counters = {
        "python": _count_test_functions_python,
        "java": _count_test_functions_java,
        "javascript": _count_test_functions_js,
        "typescript": _count_test_functions_js,
    }
    counter = counters.get(language)
    return counter(tree, src_bytes) if counter else 0


def _extract_parameter_names(func_node, src_bytes: bytes) -> list[str]:
    """Return this function/method node's parameter names, excluding
    `self`/`cls`.

    Reads each parameter's own AST node individually (not a manual
    comma-split of the whole parameter-list text), so a default value
    containing a `)` or `,` (e.g. `items=list()`, `data={"a": 1, "b": 2}`)
    can't truncate or mis-split the list -- each parameter node's text
    always starts with its own identifier regardless of what its default
    value contains.
    """
    params_node = func_node.child_by_field_name("parameters")
    if not params_node:
        return []

    # "keyword_separator" (bare `*`) and "positional_separator" (bare `/`)
    # mark keyword-only/positional-only argument boundaries (e.g.
    # `def f(a, *, b)`, `def f(a, b, /, c)`) -- they are not parameters.
    separator_node_types = {"keyword_separator", "positional_separator"}

    names = []
    for child in params_node.children:
        if child.type in separator_node_types:
            continue
        text = _source(child, src_bytes).strip()
        if not text or text in ("(", ")", ","):
            continue
        name = text.split(":")[0].split("=")[0].strip()
        if name and name not in ("self", "cls"):
            names.append(name)
    return names


def _detect_fixture_dependencies(fixtures: list[FixtureResult]) -> None:
    """
    Detect fixture dependencies for pytest fixtures (Phase 4).

    For pytest fixtures, detects when a fixture takes another fixture as a parameter.
    Example: @pytest.fixture; def fixture_a(fixture_b): ...

    This enables analysis of:
    - Fixture dependency graphs
    - Scope propagation (dependent on higher-level scopes)
    - Modularity patterns (how fixtures are reused and composed)

    Modifies fixtures in-place, populating fixture_dependencies field.
    """
    # Build a name -> fixture mapping for quick lookup
    fixtures_by_name = {f.name: f for f in fixtures}

    for fixture in fixtures:
        # Only detect dependencies for pytest fixtures (which have parameters)
        if fixture.fixture_type != "pytest_decorator":
            continue

        # raw_source is just this fixture's own "def name(...): ..." text
        # (the decorator isn't included -- see detector_python.py), so it
        # re-parses cleanly as a standalone snippet. Parsing it (rather
        # than regexing the text) is what lets _extract_parameter_names
        # read each parameter as its own AST node.
        try:
            tree = _get_parser("python").parse(fixture.raw_source.encode("utf-8"))
        except Exception:
            continue
        func_node = next(
            (c for c in tree.root_node.children if c.type == "function_definition"),
            None,
        )
        if func_node is None:
            continue

        param_names = _extract_parameter_names(
            func_node, fixture.raw_source.encode("utf-8")
        )

        # Check which parameters are fixtures (exist in fixtures_by_name)
        for param_name in param_names:
            if param_name in fixtures_by_name:
                fixture.fixture_dependencies.append(param_name)


def _propagate_fixture_scopes(fixtures: list[FixtureResult]) -> None:
    """
    Propagate scope constraints based on fixture dependencies (Phase 4).

    When fixture A depends on fixture B, the scope of A is constrained by B:
    - If B is per_test and A is per_module, A must be downgraded to per_test
    - Scope hierarchy: per_test < per_class < per_module < global

    This prevents impossible configurations (module-scoped fixture depending on test-scoped fixture).

    Modifies fixtures in-place, updating scope field.
    """
    scope_order = {
        "per_test": 0,
        "per_class": 1,
        "per_module": 2,
        "global": 3,
    }

    # Build name -> fixture map
    fixtures_by_name = {f.name: f for f in fixtures}

    # Propagate scopes (may need multiple passes for chains of dependencies)
    max_iterations = len(fixtures)
    for _iteration in range(max_iterations):
        changed = False

        for fixture in fixtures:
            if not fixture.fixture_dependencies:
                continue

            current_scope_level = scope_order.get(fixture.scope, 0)

            # Find the most restrictive scope among dependencies
            most_restrictive_level = current_scope_level
            for dep_name in fixture.fixture_dependencies:
                dep_fixture = fixtures_by_name.get(dep_name)
                if dep_fixture:
                    dep_scope_level = scope_order.get(dep_fixture.scope, 0)
                    most_restrictive_level = min(
                        most_restrictive_level, dep_scope_level
                    )

            # If scope needs to be updated, do it
            if most_restrictive_level < current_scope_level:
                # Find the scope name for this level
                for scope_name, level in scope_order.items():
                    if level == most_restrictive_level:
                        fixture.scope = scope_name
                        changed = True
                        break

        # If no changes, we're done
        if not changed:
            break


_TEARDOWN_DETECTION = _PATTERNS["teardown_detection"]
YIELD_BASED_TEARDOWN_TYPES: set[str] = set(
    _TEARDOWN_DETECTION["yield_based_fixture_types"]
)
NAME_BASED_TEARDOWN_PAIRS: dict[str, dict[str, str]] = _TEARDOWN_DETECTION[
    "name_based_pairs"
]
TYPE_BASED_TEARDOWN_PAIRS: dict[str, str] = _TEARDOWN_DETECTION["type_based_pairs"]
SELF_REGISTERED_CLEANUP: dict[str, dict[str, list[str]]] = _TEARDOWN_DETECTION.get(
    "self_registered_cleanup", {}
)


def _calculate_teardown_pairs(fixtures: list[FixtureResult]) -> None:
    """
    Post-process fixtures to detect has_teardown_pair: whether a fixture has cleanup logic.

    Four detection mechanisms, all driven by
    collection/config_data/feature_extraction_patterns.yaml's
    teardown_detection table:
      - yield_based: pytest fixtures -- checks for a 'yield' statement in the
        fixture's own body (no pairing against another fixture needed).
      - name_based: setup and teardown share the same fixture_type and are
        distinguished only by name (unittest_setup, pytest_class_method,
        nose_fixture) -- paired by exact setup-name -> teardown-name.
      - self_registered_cleanup: some setup-side fixtures (unittest's setUp/
        setUpClass) can register their own teardown inline via a cleanup
        call (self.addCleanup(...), self.enterContext(...), etc.) instead of
        a separately-named teardown method -- checked as an OR alongside
        name_based, by substring in the setup fixture's own raw_source.
      - type_based: setup and teardown are different fixture_types, paired
        by type + matching scope (e.g. junit5_before_each/junit5_after_each).

    Only the setup-side fixture of a pair is flagged (has_teardown_pair=1);
    the teardown-side fixture itself is not, matching this column's existing
    semantics. Modifies fixtures in-place.
    """
    for fixture in fixtures:
        has_teardown = False

        if fixture.fixture_type in YIELD_BASED_TEARDOWN_TYPES:
            has_teardown = "yield" in fixture.raw_source

        elif fixture.fixture_type in NAME_BASED_TEARDOWN_PAIRS:
            expected_name = NAME_BASED_TEARDOWN_PAIRS[fixture.fixture_type].get(
                fixture.name
            )
            if expected_name:
                has_teardown = any(
                    other.fixture_type == fixture.fixture_type
                    and other.name == expected_name
                    for other in fixtures
                )

            cleanup_substrings = SELF_REGISTERED_CLEANUP.get(
                fixture.fixture_type, {}
            ).get(fixture.name)
            if cleanup_substrings and any(
                substring in fixture.raw_source for substring in cleanup_substrings
            ):
                has_teardown = True

        elif fixture.fixture_type in TYPE_BASED_TEARDOWN_PAIRS:
            expected_type = TYPE_BASED_TEARDOWN_PAIRS[fixture.fixture_type]
            has_teardown = any(
                other.fixture_type == expected_type and other.scope == fixture.scope
                for other in fixtures
            )

        fixture.has_teardown_pair = 1 if has_teardown else 0
