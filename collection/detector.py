"""
AST-based fixture and mock detector using Tree-sitter.

FIXTURE DETECTION APPROACH
===========================

For each of the 6 supported languages, we define:

1. **Fixture patterns** — How to identify fixture *definitions* in a test file
   - Python: Functions decorated with @pytest.fixture or @unittest setUp/tearDown
   - Java: Methods with @Before/@BeforeClass, @Setup, or @Test annotations
   - JavaScript/TypeScript: Functions named beforeEach/beforeAll/describe/setUp
   - Go: Functions starting with Test/, functions using testing.T

   Pattern matching uses tree-sitter AST node types that are
   language-agnostic (e.g., 'function_declaration', 'decorator', etc.)

2. **Mock patterns** — How to identify mock usages within a fixture
   Uses regex-based heuristics to detect mock framework calls:
   - unittest_mock (Python), Mockito (Java), Jest (JS), Sinon (JS), etc.
   - ~40 framework-specific patterns across 12 mock frameworks
   - Detects both mock *instantiation* and mock *usage*

3. **Fixture metrics** — Quantitative properties of the fixture
   - LOC: Lines of code (custom: non-blank line count)
   - Cyclomatic Complexity: Branch count via Lizard library
   - Cognitive Complexity: Nesting-depth-weighted via cognitive-complexity (Python) + formula
   - num_objects_instantiated: Custom count of new X(...) constructor calls
   - num_external_calls: Custom regex detection of I/O patterns (db, file, http, network)
   - num_parameters: Function signature parameter count via Lizard library

IMPLEMENTATION ARCHITECTURE
===========================

The detector delegates metric calculation to industry-standard tools:
- Lizard (v1.21+): cyclomatic complexity, cognitive complexity, parameters
- cognitive-complexity (v1.3+): Python-specific SonarQube-standard complexity
- Tree-sitter: AST parsing for fixture detection and scope analysis
- Regex: Custom I/O pattern detection (external_calls, object_instantiation)

See collection/complexity_provider.py for metric facade and docs/COMPLEXITY_METRICS_MIGRATION.md
for full methodology and justification.

PUBLIC INTERFACE
================

extract_fixtures(file_path: Path, language: str) -> ExtractResult

ExtractResult contains:
  - fixtures: list[FixtureResult] — all fixture definitions found
  - file_loc: int — non-blank lines of code in the file
  - num_test_functions: int — count of test functions in the file

Each FixtureResult carries all the fields needed to populate the DB tables:
  fixture_type, scope, start_line, end_line, loc,
  cyclomatic_complexity, max_nesting_depth,
  num_objects_instantiated, num_external_calls, num_parameters,
  framework (mock framework used, if any), raw_source text
"""

import re
import logging
from dataclasses import dataclass, field
from pathlib import Path

from .config import MAX_FILE_SIZE_BYTES
from .ast_cache import parse_bytes as parse_src_bytes
from .complexity_provider import (
    analyze_function_complexity,
    get_file_loc,
    get_file_function_count,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy-load Tree-sitter grammars to avoid import overhead when unused
# ---------------------------------------------------------------------------

_PARSERS: dict = {}


def _get_parser(language: str):
    """Return (and cache) a tree_sitter.Parser for the given language key."""
    if language in _PARSERS:
        return _PARSERS[language]

    try:
        import tree_sitter_python
        import tree_sitter_java
        import tree_sitter_javascript
        import tree_sitter_typescript
        import tree_sitter_go
        from tree_sitter import Language, Parser

        lang_map = {
            "python": Language(tree_sitter_python.language()),
            "java": Language(tree_sitter_java.language()),
            "javascript": Language(tree_sitter_javascript.language()),
            "typescript": Language(tree_sitter_typescript.language_typescript()),
            "go": Language(tree_sitter_go.language()),
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
    framework: str
    target_identifier: str
    num_interactions_configured: int
    raw_snippet: str


@dataclass
class FixtureResult:
    name: str
    fixture_type: str  # see per-language constants below
    framework: str  # testing framework: pytest, unittest, junit, nunit, testify, etc.
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


def is_mock_framework_available(
    framework: str, language: str, repo_path: Path = None
) -> bool:
    """
    Check if a detected mock framework is actually available in the project (Phase 4).

    When a mock framework is detected via code pattern matching, this function
    attempts to verify that the framework is actually installed/declared as a
    dependency in the project. This reduces false positives from using similar
    framework names or homonyms.

    Args:
        framework: Detected framework name (e.g., "mockito", "unittest_mock", "jest")
        language: Programming language
        repo_path: Optional path to repository root for dependency file scanning

    Returns:
        True if framework is confirmed as available or repo_path not provided,
        False if verified as NOT available in dependencies

    Implementation:
        Scans language-specific dependency files:
        - Python: requirements.txt, setup.py, pyproject.toml, poetry.lock, Pipfile
        - Java: pom.xml, build.gradle, build.gradle.kts
        - JavaScript/TypeScript: package.json, package-lock.json, yarn.lock, pnpm-lock.yaml
        - Go: go.mod, go.sum

    Returns True if:
    - repo_path not provided (cannot verify, assume available)
    - Framework found in any dependency file
    - Framework is built-in (e.g., unittest for Python)

    Returns False if:
    - Framework pattern searched but NOT found in any dependency file
    """
    if not repo_path:
        # No repo context provided, accept all frameworks
        return True

    # Map framework names to package/module names to search for
    framework_mappings = {
        # Python frameworks
        "unittest_mock": ["unittest"],  # built-in
        "pytest_mock": ["pytest", "pytest-mock"],
        "mockito": ["mockito", "mockito-python"],
        "mock": ["mock", "unittest"],  # built-in or pypi
        # Java frameworks
        "mockito": ["mockito"],  # looks for org.mockito:mockito-core
        "easymock": ["easymock"],
        "mockk": ["mockk"],
        "jmockit": ["jmockit"],
        # JavaScript/TypeScript frameworks
        "jest": ["jest"],
        "sinon": ["sinon"],
        "vitest": ["vitest"],
        "mocha": ["mocha"],
        "jasmine": ["jasmine"],
        # Go frameworks
        "gomock": ["gomock", "mock"],
        "testify_mock": ["testify"],
    }

    # Get package names to search for
    package_names = framework_mappings.get(framework, [framework])

    # Language-specific dependency file scanning
    if language.lower() == "python":
        return _check_python_dependencies(repo_path, package_names)
    elif language.lower() == "java":
        return _check_java_dependencies(repo_path, package_names)
    elif language.lower() in ("javascript", "typescript"):
        return _check_javascript_dependencies(repo_path, package_names)
    elif language.lower() == "go":
        return _check_go_dependencies(repo_path, package_names)

    # Unknown language, assume available
    return True


def _check_python_dependencies(repo_path: Path, package_names: list[str]) -> bool:
    """Check if any package is listed in Python dependency files."""
    package_names_lower = [p.lower() for p in package_names]

    # Check requirements.txt
    req_file = repo_path / "requirements.txt"
    if req_file.exists():
        try:
            content = req_file.read_text(errors="ignore")
            for pkg in package_names_lower:
                # Match package name (case-insensitive, handle version specs)
                if re.search(rf"\b{re.escape(pkg)}\b", content, re.IGNORECASE):
                    return True
        except Exception:
            pass

    # Check setup.py
    setup_file = repo_path / "setup.py"
    if setup_file.exists():
        try:
            content = setup_file.read_text(errors="ignore")
            for pkg in package_names_lower:
                if re.search(rf"\b{re.escape(pkg)}\b", content, re.IGNORECASE):
                    return True
        except Exception:
            pass

    # Check pyproject.toml
    pyproject_file = repo_path / "pyproject.toml"
    if pyproject_file.exists():
        try:
            content = pyproject_file.read_text(errors="ignore")
            for pkg in package_names_lower:
                if re.search(rf"\b{re.escape(pkg)}\b", content, re.IGNORECASE):
                    return True
        except Exception:
            pass

    # Check poetry.lock
    poetry_file = repo_path / "poetry.lock"
    if poetry_file.exists():
        try:
            content = poetry_file.read_text(errors="ignore")
            for pkg in package_names_lower:
                if re.search(
                    rf"^name = \"{re.escape(pkg)}\"",
                    content,
                    re.IGNORECASE | re.MULTILINE,
                ):
                    return True
        except Exception:
            pass

    # If no files found with the package, assume not available
    return False


def _check_java_dependencies(repo_path: Path, package_names: list[str]) -> bool:
    """Check if any package is listed in Java dependency files."""
    package_names_lower = [p.lower() for p in package_names]

    # Check pom.xml (Maven)
    pom_file = repo_path / "pom.xml"
    if pom_file.exists():
        try:
            content = pom_file.read_text(errors="ignore")
            for pkg in package_names_lower:
                # Search for artifact ID or group ID containing package name
                if re.search(
                    rf"<artifactId>.*{re.escape(pkg)}.*</artifactId>",
                    content,
                    re.IGNORECASE,
                ):
                    return True
                if re.search(
                    rf"<groupId>.*{re.escape(pkg)}.*</groupId>", content, re.IGNORECASE
                ):
                    return True
        except Exception:
            pass

    # Check build.gradle
    gradle_file = repo_path / "build.gradle"
    if gradle_file.exists():
        try:
            content = gradle_file.read_text(errors="ignore")
            for pkg in package_names_lower:
                if re.search(rf"\b{re.escape(pkg)}\b", content, re.IGNORECASE):
                    return True
        except Exception:
            pass

    # Check build.gradle.kts
    gradle_kts_file = repo_path / "build.gradle.kts"
    if gradle_kts_file.exists():
        try:
            content = gradle_kts_file.read_text(errors="ignore")
            for pkg in package_names_lower:
                if re.search(rf"\b{re.escape(pkg)}\b", content, re.IGNORECASE):
                    return True
        except Exception:
            pass

    return False


def _check_javascript_dependencies(repo_path: Path, package_names: list[str]) -> bool:
    """Check if any package is listed in JavaScript dependency files."""
    import json

    package_names_lower = [p.lower() for p in package_names]

    # Check package.json
    package_file = repo_path / "package.json"
    if package_file.exists():
        try:
            content = json.loads(package_file.read_text())
            deps = content.get("dependencies", {})
            dev_deps = content.get("devDependencies", {})
            all_deps = {**deps, **dev_deps}

            for pkg in package_names_lower:
                if pkg in all_deps or pkg.replace("-", "_") in all_deps:
                    return True
        except Exception:
            pass

    # Check package-lock.json
    lock_file = repo_path / "package-lock.json"
    if lock_file.exists():
        try:
            content = json.loads(lock_file.read_text())
            packages = content.get("packages", {})
            for pkg_path in packages:
                for pkg in package_names_lower:
                    if pkg in pkg_path.lower():
                        return True
        except Exception:
            pass

    # Check yarn.lock (text format)
    yarn_file = repo_path / "yarn.lock"
    if yarn_file.exists():
        try:
            content = yarn_file.read_text(errors="ignore")
            for pkg in package_names_lower:
                if re.search(
                    rf"^{re.escape(pkg)}@", content, re.IGNORECASE | re.MULTILINE
                ):
                    return True
        except Exception:
            pass

    return False


def _check_go_dependencies(repo_path: Path, package_names: list[str]) -> bool:
    """Check if any package is listed in Go dependency files."""
    package_names_lower = [p.lower() for p in package_names]

    # Check go.mod
    gomod_file = repo_path / "go.mod"
    if gomod_file.exists():
        try:
            content = gomod_file.read_text(errors="ignore")
            for pkg in package_names_lower:
                if re.search(rf"\b{re.escape(pkg)}\b", content, re.IGNORECASE):
                    return True
        except Exception:
            pass

    # Check go.sum
    gosum_file = repo_path / "go.sum"
    if gosum_file.exists():
        try:
            content = gosum_file.read_text(errors="ignore")
            for pkg in package_names_lower:
                if re.search(rf"{re.escape(pkg)}", content, re.IGNORECASE):
                    return True
        except Exception:
            pass

    return False


def _validate_framework(framework: str, language: str) -> str:
    """
    Validate detected framework against FRAMEWORK_REGISTRY.

    If framework is not in the registry for the language, returns it as-is
    (we still record it to discover new frameworks), but logs a warning.
    This allows the system to be forward-compatible with new frameworks
    while maintaining a canonical registry of known ones.

    Args:
        framework: Detected framework name (e.g., "pytest", "mockito")
        language: Programming language (e.g., "python", "java")

    Returns:
        The framework name (unchanged, for further processing)
    """
    from .config import is_known_framework, get_known_frameworks

    if not is_known_framework(framework, language):
        known = get_known_frameworks(language)
        logger.debug(
            f"Detected framework '{framework}' not in registry for {language}. "
            f"Known frameworks: {known}. "
            f"This may be a new/custom framework or a detection error."
        )

    return framework


# ---------------------------------------------------------------------------
# Python detector
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Java detector
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# JavaScript / TypeScript detector
# ---------------------------------------------------------------------------

JS_FIXTURE_CALLS = {
    "beforeEach": ("before_each", "per_test"),
    "beforeAll": ("before_all", "per_class"),
    "afterEach": ("after_each", "per_test"),
    "afterAll": ("after_all", "per_class"),
    "before": (
        "mocha_before",
        "per_test",
    ),  # default to per_test for ambiguous mocha hooks
    "after": (
        "mocha_after",
        "per_test",
    ),  # default to per_test for ambiguous mocha hooks
}

# AVA fixture patterns - using member access like test.before()
AVA_FIXTURE_PATTERNS = {
    "before": ("ava_before", "per_class"),
    "after": ("ava_after", "per_class"),
    "serial.before": ("ava_serial_before", "per_test"),
    "serial.after": ("ava_serial_after", "per_test"),
}


def _detect_js(
    tree, src_bytes: bytes, language: str = "javascript"
) -> list[FixtureResult]:
    results = []

    def visit(node):
        if node.type in ("call_expression", "await_expression"):
            target = node
            if node.type == "await_expression":
                target = next(
                    (c for c in node.children if c.type == "call_expression"), None
                )
            if target is None:
                return

            func_node = target.child_by_field_name("function")
            if func_node:
                name = _source(func_node, src_bytes).strip()

                # Check standard hooks (Jest/Mocha style) - ambiguous, so framework=None
                if name in JS_FIXTURE_CALLS:
                    fixture_type, scope = JS_FIXTURE_CALLS[name]
                    results.append(
                        _build_result(
                            node=target,
                            func_node=target,
                            src_bytes=src_bytes,
                            fixture_type=fixture_type,
                            scope=scope,
                            framework=None,  # Ambiguous: could be Jest, Mocha, Vitest, Jasmine, etc.
                            language=language,
                        )
                    )

                # Check AVA patterns: test.before, test.after, test.serial.before, test.serial.after
                # These appear as member_access_expression like "test.before" or "test.serial.before"
                elif func_node.type == "member_expression":
                    # Get the full member access chain
                    member_src = _source(func_node, src_bytes).strip()

                    # Check if it's a test.* pattern
                    if member_src.startswith("test."):
                        ava_pattern = member_src[5:]  # Remove "test." prefix
                        if ava_pattern in AVA_FIXTURE_PATTERNS:
                            fixture_type, scope = AVA_FIXTURE_PATTERNS[ava_pattern]
                            results.append(
                                _build_result(
                                    node=target,
                                    func_node=target,
                                    src_bytes=src_bytes,
                                    fixture_type=fixture_type,
                                    scope=scope,
                                    framework="ava",
                                    language=language,
                                )
                            )

        # TypeScript decorator patterns: @Before, @After, @BeforeEach, etc.
        elif node.type == "method_definition":
            # Check if there's a preceding decorator node
            parent = node.parent
            if parent:
                # Find this node's index in its parent's children
                node_index = None
                for i, child in enumerate(parent.children):
                    if child == node:
                        node_index = i
                        break

                # Check if the preceding sibling is a decorator
                if node_index is not None and node_index > 0:
                    prev_sibling = parent.children[node_index - 1]
                    if prev_sibling.type == "decorator":
                        dec_text = _source(prev_sibling, src_bytes).strip()
                        # Remove @ symbol and check if it's a known decorator
                        dec_name = dec_text.lstrip("@").split("(")[0].strip()

                        # Mapping of TypeScript decorators to fixture types
                        decorator_map = {
                            "Before": ("mocha_before", "per_test"),
                            "After": ("mocha_after", "per_test"),
                            "BeforeEach": ("before_each", "per_test"),
                            "AfterEach": ("after_each", "per_test"),
                            "BeforeAll": ("before_all", "per_class"),
                            "AfterAll": ("after_all", "per_class"),
                        }

                        if dec_name in decorator_map:
                            fixture_type, scope = decorator_map[dec_name]
                            results.append(
                                _build_result(
                                    node=node,
                                    func_node=node,
                                    src_bytes=src_bytes,
                                    fixture_type=fixture_type,
                                    scope=scope,
                                    language=language,
                                )
                            )

        for child in node.children:
            visit(child)

    visit(tree.root_node)
    return results


# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Go detector
# ---------------------------------------------------------------------------


def _detect_go(tree, src_bytes: bytes, language: str = "go") -> list[FixtureResult]:
    """
    Go has no formal fixture annotation. We detect:
      1. TestMain(m *testing.M) — package-level setup
      2. Functions that are NOT TestXxx/BenchmarkXxx/ExampleXxx but are
         called from 3+ test functions in the same file (helper fixtures).
         Only functions with setup/teardown/fixture-like keywords are included
         to reduce false positives.
      3. t.Cleanup(func() { ... }) inline teardowns (noted but not extracted
         as top-level fixtures — counted inside calling test)
    """
    results = []
    all_func_names: set[str] = set()
    test_func_calls: dict[str, set[str]] = {}  # test_func -> {called functions}

    def collect_functions(node):
        if node.type == "function_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                all_func_names.add(_source(name_node, src_bytes))
        for child in node.children:
            collect_functions(child)

    def collect_calls(node, current_test: str | None):
        if node.type == "function_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                fname = _source(name_node, src_bytes)
                if re.match(r"^Test[A-Z]", fname):
                    current_test = fname
                    test_func_calls.setdefault(fname, set())

        if current_test and node.type == "call_expression":
            func = node.child_by_field_name("function")
            if func:
                test_func_calls[current_test].add(
                    _source(func, src_bytes).split("(")[0]
                )

        for child in node.children:
            collect_calls(child, current_test)

    collect_functions(tree.root_node)
    collect_calls(tree.root_node, None)

    # Helper functions called from ≥ 3 test functions (raised from 2 to reduce false positives)
    # Also filter to only include functions with setup/teardown/fixture-like keywords
    helper_call_count: dict[str, int] = {}
    for calls in test_func_calls.values():
        for c in calls:
            if c in all_func_names and not re.match(r"^(Test|Benchmark|Example)", c):
                helper_call_count[c] = helper_call_count.get(c, 0) + 1

    # Semantic filtering: only keep helpers with setup/teardown/fixture-like keywords
    setup_keywords = r"\b(setup|setUp|initialize|Init|prepare|create|build|Before|After|teardown|cleanup|Clean|Destroy|tear)\b"
    multi_used_helpers = {
        n
        for n, cnt in helper_call_count.items()
        if cnt >= 3  # Threshold raised from 2 to 3
        and re.search(setup_keywords, n, re.IGNORECASE)  # Semantic filtering
    }

    # Also include all TestMain functions regardless of calls
    multi_used_helpers_all = multi_used_helpers.copy()

    def extract_fixtures(node):
        if node.type == "function_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = _source(name_node, src_bytes)
                if name == "TestMain":
                    results.append(
                        _build_result(
                            node=node,
                            func_node=node,
                            src_bytes=src_bytes,
                            fixture_type="test_main",
                            scope="global",
                            framework="golang_testing",
                            language=language,
                        )
                    )
                elif name in multi_used_helpers_all:
                    results.append(
                        _build_result(
                            node=node,
                            func_node=node,
                            src_bytes=src_bytes,
                            fixture_type="go_helper",
                            scope="per_test",
                            framework=None,  # Heuristic-detected helper, not framework-specific
                            language=language,
                        )
                    )

        # testify/suite methods: SetupSuite, TeardownSuite, SetupTest, TeardownTest
        elif node.type == "method_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = _source(name_node, src_bytes)
                if name in ("SetupSuite", "TeardownSuite", "SetupTest", "TeardownTest"):
                    scope = (
                        "per_class"
                        if name in ("SetupSuite", "TeardownSuite")
                        else "per_test"
                    )
                    fixture_type_map = {
                        "SetupSuite": "go_setup_suite",
                        "TeardownSuite": "go_teardown_suite",
                        "SetupTest": "go_setup_test",
                        "TeardownTest": "go_teardown_test",
                    }
                    results.append(
                        _build_result(
                            node=node,
                            func_node=node,
                            src_bytes=src_bytes,
                            fixture_type=fixture_type_map[name],
                            scope=scope,
                            framework="testify",
                            language=language,
                        )
                    )

        for child in node.children:
            extract_fixtures(child)

    extract_fixtures(tree.root_node)
    return results


# ---------------------------------------------------------------------------
# Shared result builder
# ---------------------------------------------------------------------------


def _build_result(
    node,
    func_node,
    src_bytes: bytes,
    fixture_type: str,
    scope: str,
    framework: str = None,
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
        "go": _count_test_functions_go,
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
        scope_groups = {}
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
        import re

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
    for iteration in range(max_iterations):
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

    fixture_types_teardown = {
        "unittest_teardown",
        "junit5_after_each",
        "junit4_after",
        "after_each",
        "nunit_teardown",
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


DETECTORS = {
    "python": _detect_python,
    "java": _detect_java,
    "javascript": _detect_js,
    "typescript": _detect_js,  # TypeScript shares JS grammar for this purpose
    "go": _detect_go,
}


def extract_fixtures(file_path: Path, language: str) -> ExtractResult:
    """
    Parse a test file and return all fixture definitions found in it,
    along with file-level metrics (LOC, test function count).

    Returns ExtractResult with empty fixtures list if the file cannot be parsed
    or the language is not supported.
    """
    if language not in DETECTORS:
        logger.warning(f"No detector for language '{language}'")
        return ExtractResult(fixtures=[], file_loc=0, num_test_functions=0)

    # Conservative per-language allowlist of source file extensions. This
    # ensures we do not run heavy analysis on non-source files. We still keep
    # `NON_CODE_EXTENSIONS` (from config) for a broad blacklist used elsewhere
    # in the codebase; here we use it as an early exit plus a language-specific
    # whitelist to be stricter for the languages under study.
    from .config import NON_CODE_EXTENSIONS

    ALLOWED_EXTS = {
        "python": {".py", ".pyw", ".pyi"},
        "javascript": {".js", ".mjs", ".cjs", ".jsx"},
        "typescript": {".ts", ".tsx", ".mts"},
        "java": {".java"},
    }

    ext = file_path.suffix.lower()
    # First, skip anything explicitly marked as non-code.
    if ext in NON_CODE_EXTENSIONS:
        logger.debug(f"Skipping non-code extension {ext} for {file_path}")
        return ExtractResult(fixtures=[], file_loc=0, num_test_functions=0)

    # If the file has an extension, require it to be in the allowed set for the
    # language. This avoids analyzing files like README.md or data files.
    allowed = ALLOWED_EXTS.get(language)
    if ext and allowed is not None and ext not in allowed:
        logger.debug(f"Skipping file with extension {ext} not in allowed list for {language}: {file_path}")
        return ExtractResult(fixtures=[], file_loc=0, num_test_functions=0)

    # Log file size before reading (helps identify memory issues with large files)
    try:
        file_size_bytes = file_path.stat().st_size
        file_size_mb = file_size_bytes / (1024 * 1024)
        # logger.info(f"[extract] Reading {file_path.name} ({file_size_mb:.2f} MB) for {language}")

        # Skip files larger than MAX_FILE_SIZE_BYTES (not real test files)
        if file_size_bytes > MAX_FILE_SIZE_BYTES:
            logger.warning(
                f"[extract] Skipping oversized file: {file_path.name} is {file_size_mb:.2f} MB (> {MAX_FILE_SIZE_BYTES / (1024*1024):.0f} MB limit)"
            )
            return ExtractResult(fixtures=[], file_loc=0, num_test_functions=0)

        # Warn if file is large but within limits
        if file_size_mb > 3:
            logger.info(
                f"[extract] Processing large test file: {file_path.name} ({file_size_mb:.2f} MB)"
            )
    except Exception as e:
        logger.debug(f"Could not get file size for {file_path}: {e}")

    try:
        src_bytes = file_path.read_bytes()
    except (OSError, PermissionError) as e:
        logger.warning(f"Cannot read {file_path}: {e}")
        return ExtractResult(fixtures=[], file_loc=0, num_test_functions=0)

    if not src_bytes.strip():
        return ExtractResult(fixtures=[], file_loc=0, num_test_functions=0)

    try:
        # Use cached parser results when possible to avoid repeated tree-sitter
        # parses of identical file contents during bulk extraction.
        tree = parse_src_bytes(src_bytes, language)
    except Exception as e:
        logger.warning(f"Parse error in {file_path}: {e}")
        return ExtractResult(fixtures=[], file_loc=0, num_test_functions=0)

    try:
        fixtures = DETECTORS[language](tree, src_bytes, language)

        # Post-process fixtures to calculate metrics that depend on file-wide context
        _calculate_reuse_counts(fixtures, tree, src_bytes, language)
        _detect_fixture_dependencies(
            fixtures
        )  # Phase 4: detect pytest fixture dependencies
        _propagate_fixture_scopes(fixtures)  # Phase 4: propagate scope constraints
        _calculate_teardown_pairs(fixtures)

        # Extraction phase: Use Lizard for file-level metrics instead of manual counting
        # This provides consistency with fixture-level complexity analysis
        file_loc = _count_file_loc(
            src_bytes
        )  # Keep manual counting for non-blank lines
        num_test_functions = get_file_function_count(file_path, language)
        return ExtractResult(
            fixtures=fixtures, file_loc=file_loc, num_test_functions=num_test_functions
        )
    except Exception as e:
        logger.warning(f"Detection error in {file_path}: {e}")
        return ExtractResult(fixtures=[], file_loc=0, num_test_functions=0)
