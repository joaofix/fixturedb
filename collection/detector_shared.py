"""Cross-language plumbing shared by all `detector_<language>.py` modules.

Holds the tree-sitter parser cache, the `FixtureResult`/`MockResult`/
`ExtractResult` dataclasses, generic AST helpers (source extraction, LOC,
nesting depth), mock detection (one flat pattern table scanned regardless of
source language), the shared `_build_result()` fixture builder, and the
post-processing passes that need to see the whole fixture list at once
(reuse counts, dependency detection, scope propagation, teardown pairing) —
none of these can live in a single per-language file because they either
span languages or need the full fixture set as context.
"""

import re
from dataclasses import dataclass, field
from typing import Optional

from collection.logging_utils import get_logger

from .complexity_provider import analyze_function_complexity

logger = get_logger(__name__)

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
    reuse_count: int = (
        0  # number of test functions using this fixture (calculated later)
    )
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

    def visit(node, current_depth=1):
        nonlocal max_depth
        # Identify block-creating nodes
        block_types = {
            "if_statement",
            "while_statement",
            "for_statement",
            "try_statement",
            "with_statement",
            "def",
            "class_definition",
            "block",
            "for_in_statement",
            "foreach_statement",
            "do_statement",
            "catch_clause",
            "finally_clause",
        }

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


def _count_external_calls(node, src_bytes: bytes) -> int:
    """
    Count calls that look like external I/O or system operations.

    This is a custom regex-based assessment since Lizard's fan_out metric
    measures inter-function calls within the same module, not external I/O.

    Detects patterns like: database, network, file I/O, and subprocess calls.
    """
    text = _source(node, src_bytes).lower()
    external_patterns = [
        r"\bopen\s*\(",  # file
        r"\bconnect\s*\(",  # db/network
        r"\bcreate_engine\s*\(",  # SQLAlchemy
        r"\bsession\s*\.",  # db sessions
        r"\brequests?\.",  # HTTP
        r"\bhttpclient\b",  # Go / Java
        r"\bos\.environ\b",  # env config
        r"\bsubprocess\.",  # subprocess
        r"\bsocket\s*\(",  # raw sockets
        r"\btempfile\.",  # filesystem
        r"\bshutil\.",  # filesystem
    ]
    return sum(len(re.findall(p, text)) for p in external_patterns)


# ---------------------------------------------------------------------------
# Constants for snippet extraction and thresholds
# ---------------------------------------------------------------------------

SNIPPET_CONTEXT_BEFORE = 20  # characters before match in mock detection
SNIPPET_CONTEXT_AFTER = 60  # characters after match in mock detection

# ---------------------------------------------------------------------------
# Mock detection (language-agnostic heuristic pass)
# ---------------------------------------------------------------------------

MOCK_PATTERNS = [
    # Python
    (r"mock\.patch\s*\(\s*['\"]([^'\"]+)['\"]", "unittest_mock"),
    (r"mocker\.patch\s*\(\s*['\"]([^'\"]+)['\"]", "pytest_mock"),
    (r"MagicMock\s*\(|Mock\s*\(|AsyncMock\s*\(", "unittest_mock"),
    # Java
    (r"Mockito\.mock\s*\(\s*(\w+)\.class", "mockito"),
    (r"@Mock\b", "mockito"),
    (r"EasyMock\.createMock\s*\(\s*(\w+)\.class", "easymock"),
    (r"mock\s*\(\s*(\w+)\.class", "mockk"),  # MockK (Kotlin)
    # JavaScript / TypeScript
    (r"jest\.fn\s*\(", "jest"),
    (r"jest\.spyOn\s*\(", "jest"),
    (r"jest\.mock\s*\(\s*['\"]([^'\"]+)['\"]", "jest"),
    (r"sinon\.(stub|spy|mock)\s*\(", "sinon"),
    (r"vi\.fn\s*\(", "vitest"),
    (r"vi\.mock\s*\(\s*['\"]([^'\"]+)['\"]", "vitest"),
    # Go
    (r"gomock\.NewController", "gomock"),
    (r"testify/mock", "testify_mock"),
    (r"\.On\s*\(\s*['\"](\w+)['\"]", "testify_mock"),
]


def _extract_mocks(node, src_bytes: bytes) -> list[MockResult]:
    text = _source(node, src_bytes)
    found = []
    for pattern, framework in MOCK_PATTERNS:
        for m in re.finditer(pattern, text):
            target = m.group(1) if m.lastindex and m.lastindex >= 1 else ""
            snippet_start = max(m.start() - SNIPPET_CONTEXT_BEFORE, 0)
            snippet_end = min(m.end() + SNIPPET_CONTEXT_AFTER, len(text))
            snippet = text[snippet_start:snippet_end].replace("\n", " ")

            # Count .return_value / .side_effect / when(...).thenReturn style
            interactions = len(
                re.findall(
                    r"return_value|side_effect|thenReturn|thenThrow|doReturn",
                    text[m.start() : m.end() + 200],
                )
            )

            found.append(
                MockResult(
                    framework=framework,
                    target_identifier=target,
                    num_interactions_configured=interactions,
                    raw_snippet=snippet,
                )
            )
    return found


# ---------------------------------------------------------------------------
# Shared result builder
# ---------------------------------------------------------------------------


def _build_result(
    node,
    func_node,
    src_bytes: bytes,
    fixture_type: str,
    scope: str,
    framework: Optional[str] = None,
    language: str = "python",
) -> FixtureResult:
    src_text = _source(func_node, src_bytes)
    name_node = func_node.child_by_field_name("name")
    name = (
        _source(name_node, src_bytes)
        if name_node
        else f"<anonymous>_{node.start_point[0]}"
    )

    # Get metrics from Lizard via complexity_provider
    # Includes: cyclomatic_complexity, num_parameters
    metrics = analyze_function_complexity(src_text, language)

    # Compute nesting depth from AST (Lizard's max_nesting_depth doesn't work for functions)
    nesting_depth = _compute_nesting_depth(func_node)

    return FixtureResult(
        name=name,
        fixture_type=fixture_type,
        framework=framework,
        scope=scope,
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        loc=_count_loc(src_text),  # Custom counting (non-blank lines)
        cyclomatic_complexity=metrics.get("cyclomatic_complexity", 1),
        max_nesting_depth=nesting_depth,
        num_objects_instantiated=metrics.get(
            "num_objects_instantiated", 0
        ),  # Via Lizard + post-processing
        num_external_calls=_count_external_calls(
            node, src_bytes
        ),  # Custom regex for I/O patterns
        num_parameters=metrics.get("num_parameters", 0),
        reuse_count=0,  # Calculated in post-processing
        has_teardown_pair=0,  # Calculated in post-processing
        raw_source=src_text,
        mocks=_extract_mocks(node, src_bytes),
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


def _calculate_reuse_counts(
    fixtures: list[FixtureResult], tree, src_bytes: bytes, language: str
) -> None:
    """
    Post-process fixtures to count reuse: how many test functions use each fixture.

    For pytest fixtures, counts test functions that declare the fixture as a parameter.
    For JUnit/xUnit, counts test methods in the same class that share @BeforeEach.
    For other frameworks, counts test functions in the same scope.

    Modifies fixtures in-place.
    """
    if language.lower() == "python":
        # For Python, scan for test functions and count which fixtures they declare
        fixture_usages = {f.name: 0 for f in fixtures}

        def visit(node):
            # Find test functions (def test_...)
            if node.type == "function_definition" and _source(
                node.child_by_field_name("name"), src_bytes
            ).startswith("test_"):
                # Get parameters
                params_node = node.child_by_field_name("parameters")
                if params_node:
                    for child in params_node.children:
                        param_name = _source(child, src_bytes).strip()
                        # Remove type hints and defaults
                        if ":" in param_name:
                            param_name = param_name.split(":")[0].strip()
                        if "=" in param_name:
                            param_name = param_name.split("=")[0].strip()
                        # Count usage
                        if param_name in fixture_usages:
                            fixture_usages[param_name] += 1

            for child in node.children:
                visit(child)

        visit(tree.root_node)

        # Apply counts to fixtures
        for fixture in fixtures:
            fixture.reuse_count = fixture_usages.get(fixture.name, 0)

    else:
        # For other languages, use a simpler heuristic: count by scope
        # (same-scope fixtures are typically reused by multiple tests)
        scope_groups: dict[str, list] = {}
        for fixture in fixtures:
            key = fixture.scope
            if key not in scope_groups:
                scope_groups[key] = []
            scope_groups[key].append(fixture)

        # In same scope, assume fixtures are used by remaining test functions
        for group in scope_groups.values():
            # Simple heuristic: if scope is per_test, reuse_count is likely 1
            # if per_class, it's likely multiple tests per class (estimate as 3-5)
            for fixture in group:
                if fixture.scope == "per_test":
                    fixture.reuse_count = 1
                elif fixture.scope == "per_class":
                    fixture.reuse_count = max(
                        1, len(group)
                    )  # At least as many as fixtures
                else:
                    fixture.reuse_count = 1


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

        # Extract parameter names from raw source
        # Pattern: def fixture_name(param1, param2, ...): or async def fixture_name(...):
        # Use regex to extract parameters
        # Match: def name(params) or async def name(params)
        param_match = re.search(
            r"(?:async\s+)?def\s+\w+\s*\(([^)]*)\)", fixture.raw_source
        )
        if not param_match:
            continue

        params_str = param_match.group(1)
        if not params_str.strip():
            continue

        # Parse parameter names (simple split by comma, handle type hints)
        param_names = []
        for param in params_str.split(","):
            param = param.strip()
            if not param or param == "self":
                continue

            # Extract parameter name (before : or =)
            # Examples: "name", "name: Type", "name: Type = default", "name=default"
            param_name = param.split(":")[0].split("=")[0].strip()
            if param_name:
                param_names.append(param_name)

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


def _calculate_teardown_pairs(fixtures: list[FixtureResult]) -> None:
    """
    Post-process fixtures to detect has_teardown_pair: whether a fixture has cleanup logic.

    For Python pytest:
      - checks if fixture has 'yield' statement (fixture-style teardown)
    For Python unittest:
      - setUp is paired with tearDown
    For Java/etc:
      - @BeforeEach is paired with @AfterEach
      - @Before is paired with @After
      - etc.

    Modifies fixtures in-place.
    """
    # Group fixtures by type/scope to find pairs
    fixture_types_setup = {
        "pytest_decorator",
        "unittest_setup",
        "junit5_before_each",
        "junit4_before",
        "before_each",
        "nunit_setup",
        "xunit_fact",
        "xunit_theory",
    }

    for fixture in fixtures:
        has_teardown = False

        # For pytest: check if source has 'yield' (fixture cleanup)
        if fixture.fixture_type == "pytest_decorator":
            has_teardown = "yield" in fixture.raw_source

        # For unittest: check if there's a matching tearDown
        elif fixture.fixture_type in ("unittest_setup", "setup_method", "setup_class"):
            matching_name = fixture.name.replace("setUp", "tearDown")
            for other in fixtures:
                if other.name == matching_name and other.fixture_type.replace(
                    "setUp", "tearDown"
                ) == fixture.fixture_type.replace("setUp", "tearDown"):
                    has_teardown = True
                    break

        # For JUnit/xUnit: check for matching @After, @AfterEach, etc.
        elif fixture.fixture_type in fixture_types_setup:
            # Map setup types to teardown types
            teardown_map = {
                "junit5_before_each": "junit5_after_each",
                "junit4_before": "junit4_after",
                "before_each": "after_each",
                "nunit_setup": "nunit_teardown",
            }
            expected_teardown = teardown_map.get(fixture.fixture_type)
            if expected_teardown:
                for other in fixtures:
                    if (
                        other.fixture_type == expected_teardown
                        and other.scope == fixture.scope
                    ):
                        has_teardown = True
                        break

        fixture.has_teardown_pair = 1 if has_teardown else 0
