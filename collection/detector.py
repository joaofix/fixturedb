"""
AST-based fixture and mock detector using Tree-sitter.

FIXTURE DETECTION APPROACH
===========================

For each of the supported languages, we define:

1. **Fixture patterns** — How to identify fixture *definitions* in a test file
   - Python: Functions decorated with @pytest.fixture or @unittest setUp/tearDown
   - Java: Methods with @Before/@BeforeClass, @Setup, or @Test annotations
   - JavaScript/TypeScript: Functions named beforeEach/beforeAll/describe/setUp

   Pattern matching uses tree-sitter AST node types that are
   language-agnostic (e.g., 'function_declaration', 'decorator', etc.)

2. **Mock patterns** — How to identify mock usages within a fixture
   Uses regex-based heuristics to detect mock framework calls:
   - unittest_mock (Python), Mockito (Java), Jest (JS), Sinon (JS), etc.
   - See collection/heuristics/feature_extraction_patterns.yaml's
     mock_patterns for the exact catalog.

3. **Fixture metrics** — Quantitative properties of the fixture
   - LOC: Lines of code (custom: non-blank line count)
   - Cyclomatic Complexity: Branch count via Lizard library
   - num_objects_instantiated: Custom count of new X(...) constructor calls
     (Java/JS/TS) or capitalized-call heuristic (Python)
   - num_external_calls: Custom regex detection of I/O patterns (db, file, http, network)
   - num_parameters: Function signature parameter count via Lizard library,
     with self/cls stripped back out for Python methods
   - max_nesting_depth: Custom tree-sitter AST traversal (Lizard's nesting
     metric doesn't work at function granularity)

   Cognitive complexity was evaluated and dropped: the only programmatic
   implementation (complexipy) is Python-only, and no equivalent exists for
   Java/JS/TS, so it was removed rather than shipped as a Python-only metric
   or an unreliable cross-language formula.

MODULE LAYOUT
=============

This is a slim facade over per-language detector modules:
  - detector_shared.py: dataclasses, tree-sitter parser cache, AST helpers,
    mock detection, the shared fixture builder, and cross-fixture
    post-processing passes (teardown pairing, dependency detection, scope
    propagation)
  - detector_python.py / detector_java.py / detector_javascript.py: one
    `_detect_<language>()` function per language, each self-contained; their
    pattern tables (annotation/decorator/name -> fixture_type + scope) are
    loaded from collection/heuristics/fixture_definitions.yaml rather than
    hardcoded -- that file is the operational definition of "fixture" per
    language, including a documented `excluded` list of known boundary cases

Go support (a fixture detector module) and mock-framework dependency-file
verification (cross-checking a detected mock framework against the repo's
actual requirements.txt/pom.xml/package.json) both existed as unwired,
never-called modules and were deleted rather than kept as dead code; see
git history for `detector_go.py` / `detector_framework_registry.py` if
either is revived.

The detector delegates metric calculation to industry-standard tools:
- Lizard: cyclomatic complexity, parameter count
- Tree-sitter: AST parsing for fixture detection, scope analysis, and
  nesting depth
- Regex: I/O and constructor-call pattern detection (external_calls,
  object_instantiation), catalogued in
  collection/heuristics/feature_extraction_patterns.yaml

See collection/complexity_provider.py for the Lizard integration and
docs/architecture/metrics-reference.md for full per-metric methodology.

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

from pathlib import Path

from collection.logging_utils import get_logger

from .ast_cache import parse_bytes as parse_src_bytes
from .complexity_provider import get_file_function_count
from .config import MAX_FILE_SIZE_BYTES, NON_CODE_EXTENSIONS
from .detector_java import _detect_java
from .detector_javascript import _detect_js
from .detector_python import _detect_python
from .detector_shared import (
    ExtractResult,
    FixtureResult,
    MockResult,
    _calculate_teardown_pairs,
    _count_file_loc,
    _detect_fixture_dependencies,
    _get_parser,
    _propagate_fixture_scopes,
    fixture_result_to_dict,
)

logger = get_logger(__name__)

__all__ = [
    "ALLOWED_EXTS",
    "ExtractResult",
    "FixtureResult",
    "MockResult",
    "extract_fixtures",
    "fixture_result_to_dict",
    "_get_parser",
]

DETECTORS = {
    "python": _detect_python,
    "java": _detect_java,
    "javascript": _detect_js,
    "typescript": _detect_js,  # TypeScript shares JS grammar for this purpose
}

# Conservative per-language allowlist of source file extensions, checked by
# extract_fixtures() below. This ensures we do not run heavy analysis on
# non-source files. We still keep `NON_CODE_EXTENSIONS` (from config) for a
# broad blacklist used elsewhere in the codebase; here we use it as an early
# exit plus a language-specific whitelist to be stricter for the languages
# under study. Module-level (not function-local) and imported by
# pre2021_fixture_extractor.py's own pre-filter rather than that module
# hand-copying its own extension set: it previously did, and had already
# drifted (missing .pyw/.pyi for python; a .cts entry for typescript that
# would pass that file's own filter only to be silently rejected here one
# step later, since this is the authoritative check).
ALLOWED_EXTS = {
    "python": {".py", ".pyw", ".pyi"},
    "javascript": {".js", ".mjs", ".cjs", ".jsx"},
    "typescript": {".ts", ".tsx", ".mts"},
    "java": {".java"},
}


def _parser_key_for_file(file_path: Path, language: str) -> str:
    """Parser-selection key for `file_path` -- distinct from `language`.

    `.tsx` files contain JSX and need `_get_parser`'s "tsx" grammar
    (`tree_sitter_typescript.language_tsx()`), not the plain "typescript"
    one (`language_typescript()`, not JSX-aware) that every other
    `.ts`/`.mts` file uses. The reported `language` stays "typescript" for
    both -- only the grammar used to build the AST differs.
    """
    if language == "typescript" and file_path.suffix.lower() == ".tsx":
        return "tsx"
    return language


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

    ext = file_path.suffix.lower()
    # First, skip anything explicitly marked as non-code.
    if ext in NON_CODE_EXTENSIONS:
        logger.debug(f"Skipping non-code extension {ext} for {file_path}")
        return ExtractResult(fixtures=[], file_loc=0, num_test_functions=0)

    # If the file has an extension, require it to be in the allowed set for the
    # language. This avoids analyzing files like README.md or data files.
    allowed = ALLOWED_EXTS.get(language)
    if ext and allowed is not None and ext not in allowed:
        logger.debug(
            f"Skipping file with extension {ext} not in allowed list for {language}: {file_path}"
        )
        return ExtractResult(fixtures=[], file_loc=0, num_test_functions=0)

    # Log file size before reading (helps identify memory issues with large files)
    try:
        file_size_bytes = file_path.stat().st_size
        file_size_mb = file_size_bytes / (1024 * 1024)

        # Skip files larger than MAX_FILE_SIZE_BYTES (not real test files)
        if file_size_bytes > MAX_FILE_SIZE_BYTES:
            logger.warning(
                f"[extract] Skipping oversized file: {file_path.name} is {file_size_mb:.2f} MB (> {MAX_FILE_SIZE_BYTES / (1024 * 1024):.0f} MB limit)"
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
        tree = parse_src_bytes(src_bytes, _parser_key_for_file(file_path, language))
    except Exception as e:
        logger.warning(f"Parse error in {file_path}: {e}")
        return ExtractResult(fixtures=[], file_loc=0, num_test_functions=0)

    try:
        fixtures = DETECTORS[language](tree, src_bytes, language)

        # Post-process fixtures to calculate metrics that depend on file-wide context
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
