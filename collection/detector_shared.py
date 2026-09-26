"""Cross-language plumbing shared by all `detector_<language>.py` modules.

Holds the tree-sitter parser cache, the `FixtureResult`/`MockResult`/
`ExtractResult` dataclasses, generic AST helpers (source extraction, LOC),
mock detection (one flat pattern table scanned regardless of source
language), the shared `_build_result()` fixture builder, and
`_classify_fixture_kinds()` -- the one post-processing pass that needs to
see the whole fixture list at once (setup/teardown/setup_and_teardown/other
classification, via cross-referencing setup/teardown fixture_type pairs) --
none of these can live in a single per-language file because they either
span languages or need the full fixture set as context.

The mock pattern table and the setup/teardown pairing rules are loaded from
collection/heuristics/feature_extraction_patterns.yaml rather than
hardcoded here -- see that file for the full catalog and the reasoning
behind each pairing.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from collection.logging_utils import get_logger

from .complexity_provider import analyze_function_complexity
from .heuristics import load_feature_extraction_patterns

logger = get_logger(__name__)

_PATTERNS = load_feature_extraction_patterns()

# ---------------------------------------------------------------------------
# Lazy-load Tree-sitter grammars to avoid import overhead when unused
# ---------------------------------------------------------------------------

_PARSERS: dict = {}


def _get_parser(language: str):
    """Return (and cache) a tree_sitter.Parser for the given language key.

    "tsx" is a distinct parser key from "typescript": it's the *only* key
    with JSX support (`tree_sitter_typescript.language_tsx()` vs. the plain
    `language_typescript()` grammar), needed for `.tsx` files. It exists
    purely as a parser-selection key -- the "language" value used for
    reporting/CSV/DB (`fixture_type` tables, the `language` column, etc.)
    stays "typescript" for both `.ts` and `.tsx` files; only
    `extract_fixtures()`'s parser lookup distinguishes them (see
    `_parser_key_for_file()`). Parsing a `.tsx` file's JSX syntax (e.g.
    `<Component />`) with the non-JSX grammar produces a malformed tree --
    e.g. a `before_each` fixture's raw_source bleeding into unrelated
    trailing code.
    """
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
            "tsx": Language(tree_sitter_typescript.language_tsx()),
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
    raw_snippet: str
    category: str = ""  # test-double taxonomy: dummy/stub/spy/mock/fake -- see
    # feature_extraction_patterns.yaml's "Test-double category classification"


@dataclass
class FixtureResult:
    """A detected test fixture and its extracted structural/usage metrics."""

    name: str
    fixture_type: str  # see per-language constants below
    start_line: int
    end_line: int
    loc: int  # non-blank lines
    cyclomatic_complexity: int
    num_comment_lines: int  # comment-only lines within the fixture's own line span
    comment_density: float  # num_comment_lines / loc (0.0 if loc == 0)
    num_parameters: int
    fixture_role: str = "other"  # setup/teardown/setup_and_teardown/other --
    # set by _classify_fixture_kinds() in post-processing (pytest_decorator is the
    # one exception, classified directly in detector_python.py's _detect_python()
    # via body analysis -- see that post-processing pass's docstring above)
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


# ---------------------------------------------------------------------------
# Comment density
# ---------------------------------------------------------------------------

# Tree-sitter node type(s) that mark a comment, per language (verified
# directly against each grammar). Python has one undifferentiated `comment`
# type (line-only -- the grammar has no block comment construct); Java
# splits `//` and `/* */` into two distinct types; JavaScript/TypeScript
# share a single `comment` type across both styles.
COMMENT_NODE_TYPES: dict[str, set[str]] = {
    "python": {"comment"},
    "java": {"line_comment", "block_comment"},
    "javascript": {"comment"},
    "typescript": {"comment"},
}


def _count_comment_lines(fixture_node, language: str) -> int:
    """Count comment lines inside `fixture_node`'s own span, from the same
    parsed tree-sitter tree fixture detection already produced (no
    re-parsing, no regex over raw_source -- a `#`/`//` inside a string
    literal would false-positive a text-based scan, but can never be
    mis-tagged as a comment node by the parser).

    Walks every descendant of `fixture_node` (recursively -- a comment can
    appear at any depth, not just as a direct child), and for each node
    whose type is this language's comment node type(s), counts the lines it
    spans, clipped to `fixture_node`'s own start_line..end_line range. A
    plain `//`/`#` line comment always spans exactly one line; a `/* */`
    block comment can span several -- both are handled by the same
    end-start+1 formula. In practice every comment found this way is
    already a genuine descendant of `fixture_node`, so it's inherently
    within the fixture's own line span (can't extend past a parent node's
    own span) -- the explicit bounds check/clip is a defensive belt, not a
    load-bearing filter, but is unconditional rather than assumed.

    `language` not in COMMENT_NODE_TYPES (i.e. no comment node type known
    for it) returns 0 rather than raising -- callers only ever pass one of
    the four supported languages, but this stays a safe no-op instead of a
    KeyError if that ever changes."""
    comment_types = COMMENT_NODE_TYPES.get(language)
    if not comment_types:
        return 0

    fixture_start_line = fixture_node.start_point[0] + 1
    fixture_end_line = fixture_node.end_point[0] + 1
    total = 0

    def visit(node) -> None:
        nonlocal total
        if node.type in comment_types:
            node_start_line = node.start_point[0] + 1
            node_end_line = node.end_point[0] + 1
            if fixture_start_line <= node_start_line <= fixture_end_line:
                clipped_start = max(node_start_line, fixture_start_line)
                clipped_end = min(node_end_line, fixture_end_line)
                total += max(0, clipped_end - clipped_start + 1)
            return  # comment nodes are leaves -- nothing to descend into
        for child in node.children:
            visit(child)

    visit(fixture_node)
    return total


def _comment_density(num_comment_lines: int, loc: int) -> float:
    """num_comment_lines / loc, or 0.0 if loc is 0 -- avoids a
    ZeroDivisionError. A real extracted fixture's loc is never actually 0
    (even a bare one-line signature counts as 1 non-blank line), but this
    guards the arithmetic defensively rather than assuming that always
    holds."""
    return num_comment_lines / loc if loc else 0.0


# ---------------------------------------------------------------------------
# Constants for snippet extraction and thresholds
# ---------------------------------------------------------------------------

SNIPPET_CONTEXT_BEFORE = 20  # characters before match in mock detection
SNIPPET_CONTEXT_AFTER = 60  # characters after match in mock detection

# ---------------------------------------------------------------------------
# Mock detection (language-agnostic heuristic pass)
# ---------------------------------------------------------------------------

MOCK_PATTERNS: list[tuple[str, str]] = [
    (entry["pattern"], entry["framework"]) for entry in _PATTERNS["mock_patterns"]
]

# (category, [terms]) in priority order -- first term found wins. See
# feature_extraction_patterns.yaml's "Test-double category classification"
# for the method and rationale (matches the identifier-keyword approach
# used in related work).
MOCK_CATEGORY_KEYWORDS: list[tuple[str, list[str]]] = [
    (entry["category"], entry["terms"]) for entry in _PATTERNS["mock_category_keywords"]
]


def _classify_mock_category(text: str) -> str:
    """Return the test-double category for *text*, by case-insensitive
    substring match against MOCK_CATEGORY_KEYWORDS in priority order.
    Falls back to "mock" (the least-specific, catch-all term) when no
    keyword is found.

    Callers pass the *whole fixture body*, not just a match's own nearby
    snippet -- deliberately: a mock is frequently created and named several
    lines away from where it's instantiated (e.g. a `dummy_request`
    fixture that just does `return Mock()`, with no keyword anywhere near
    the call itself), so a small fixed-size window around the match misses
    real identifiers a whole-body scan catches. This matches the
    identifier-keyword method used in related work, which parses a whole
    code block for identifiers rather than a windowed excerpt around one
    call site. The one precision cost: if a single fixture legitimately
    creates two differently-named mocks (e.g. both a `dummy_x` and a
    `real_service_mock`), both still get the same category, since this
    scans the fixture once, not per match.
    """
    lowered = text.lower()
    for category, terms in MOCK_CATEGORY_KEYWORDS:
        if any(term in lowered for term in terms):
            return category
    return "mock"


def _mask_comment_spans(node, src_bytes: bytes, language: str) -> str:
    """`node`'s own source text (same content `_source(node, src_bytes)`
    returns), with every comment node's span blanked out to spaces of the
    same *character* length -- so match/slice positions computed against
    the result line up exactly with positions in the real, unmasked text.

    Why this exists: `_extract_mocks()` below runs its MOCK_PATTERNS
    regexes and `_classify_mock_category()`'s keyword scan directly over
    the fixture's flat source text, with no notion that a substring inside
    a `//`/`#`/`/* */` comment isn't real code -- unlike fixture detection
    and `classify_pytest_fixture_kind()` (detector_python.py), which only
    ever walk actual tree-sitter node *types* (a comment is its own
    distinct node type there, never mistaken for a real `call`/`yield`
    node). Found via manual validation sampling: a fixture whose only
    `jest.spyOn(...)` call was commented out still got `has_mock=True`,
    because regex has no concept of "this text is inside a comment token".
    Masking reuses `COMMENT_NODE_TYPES` -- the exact same per-language
    comment node names `_count_comment_lines()` already relies on for
    `num_comment_lines` -- rather than a hand-rolled comment/string
    stripper (regex-based lexing of 4 different comment grammars is easy
    to get subtly wrong, e.g. on nested quotes; tree-sitter has already
    done that work correctly).

    Character offsets, not byte offsets: tree-sitter's `node.start_byte`/
    `end_byte` are byte positions into `src_bytes`, but `_source()` decodes
    to a `str`, and `str` indexing is by character -- multi-byte UTF-8
    content (e.g. a non-English comment) means byte and character offsets
    diverge. Decoding the *prefix* up to each comment boundary (from the
    same fixture-relative byte origin `_source()` uses) converts each
    boundary to the matching character offset, so the masked-out span's
    length exactly matches how many characters that comment decodes to --
    not how many bytes it occupies -- keeping every position after it
    aligned with the real (unmasked) text. Blanking with plain spaces
    (not newlines) is safe here: MOCK_PATTERNS only ever requires `\\s*`/
    word-boundary gaps, never cares whether a gap was originally a space
    or a newline.

    Only comments are masked, not string literals -- e.g. a mock call
    quoted inside a docstring example is a separate, distinct false-
    positive class not covered by this fix.

    `language` not in COMMENT_NODE_TYPES returns the text unchanged
    (same safe-no-op convention as `_count_comment_lines()`)."""
    text = _source(node, src_bytes)
    comment_types = COMMENT_NODE_TYPES.get(language)
    if not comment_types:
        return text

    spans: list[tuple[int, int]] = []

    def visit(n) -> None:
        if n.type in comment_types:
            char_start = len(
                src_bytes[node.start_byte : n.start_byte].decode("utf-8", errors="replace")
            )
            char_end = len(
                src_bytes[node.start_byte : n.end_byte].decode("utf-8", errors="replace")
            )
            spans.append((char_start, char_end))
            return  # comment nodes are leaves -- nothing to descend into
        for child in n.children:
            visit(child)

    visit(node)
    if not spans:
        return text

    masked = list(text)
    for start, end in spans:
        for i in range(start, min(end, len(masked))):
            masked[i] = " "
    return "".join(masked)


def _extract_mocks(node, src_bytes: bytes, language: str) -> list[MockResult]:
    text = _source(node, src_bytes)
    masked_text = _mask_comment_spans(node, src_bytes, language)
    category = _classify_mock_category(masked_text)
    found = []
    for pattern, framework in MOCK_PATTERNS:
        for m in re.finditer(pattern, masked_text):
            target = m.group(1) if m.lastindex and m.lastindex >= 1 else ""
            snippet_start = max(m.start() - SNIPPET_CONTEXT_BEFORE, 0)
            snippet_end = min(m.end() + SNIPPET_CONTEXT_AFTER, len(text))
            # Sliced from the real (unmasked) text -- a reviewer reading
            # raw_snippet should see the actual surrounding code, comments
            # included; masking only ever decides *whether* something
            # counts as a match, never what gets shown for one that does.
            snippet = text[snippet_start:snippet_end].replace("\n", " ")

            found.append(
                MockResult(
                    framework=framework,
                    target_identifier=target,
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
    language: str = "python",
) -> FixtureResult:
    """Build a FixtureResult from a single node spanning the whole fixture.

    Every metric (line range, raw_source, mocks, complexity) is derived
    from this one node. Python's pytest-decorator detection used to pass a
    wider `decorated_definition` node for the line range/mocks scan while
    using the bare `function_definition` for raw_source/complexity -- so a
    fixture's reported line range disagreed with its own raw_source text by
    exactly the decorator line, and a `MagicMock()` call sitting in the
    decorator's own arguments (e.g. `@pytest.fixture(params=[...])`) leaked
    into that fixture's mocks even though it isn't part of the fixture
    body. Callers now always pass the fixture's own function/method node
    (decorator excluded), never the decorated wrapper.
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
        # num_parameters by 1 for nearly every unittest/pytest-class-method
        # fixture (anything defined as a method, not a bare function).
        # Java/JS/TS have no equivalent implicit first parameter, so this
        # override is Python-only.
        metrics["num_parameters"] = len(_extract_parameter_names(func_node, src_bytes))

    # comment_density depends on loc, so it's computed after loc rather than
    # inline in the FixtureResult(...) call below.
    loc = _count_loc(src_text)  # Custom counting (non-blank lines)
    num_comment_lines = _count_comment_lines(func_node, language)

    return FixtureResult(
        name=name,
        fixture_type=fixture_type,
        start_line=func_node.start_point[0] + 1,
        end_line=func_node.end_point[0] + 1,
        loc=loc,
        cyclomatic_complexity=metrics.get("cyclomatic_complexity", 1),
        num_comment_lines=num_comment_lines,  # Tree-sitter comment-node walk
        comment_density=_comment_density(num_comment_lines, loc),
        num_parameters=metrics.get("num_parameters", 0),
        raw_source=src_text,
        mocks=_extract_mocks(func_node, src_bytes, language),
    )


def fixture_result_to_dict(
    fixture: FixtureResult, *, language: str, file_path: str, **extra: Any
) -> dict:
    """Flatten a FixtureResult (plus its mocks) into the flat dict shape
    every extraction call site writes into fixtures.csv / the fixtures DB
    table.

    `language`/`file_path` are call-site context a FixtureResult doesn't
    carry itself (it's produced per-file, but doesn't know its own
    filename or which language detector produced it). `**extra` adds
    whatever further fields a specific extraction path needs on top of the
    common core -- e.g. `repo_name`, `commit_sha`, `agent_type`,
    `is_complete_addition` for a commit-level extraction, or `commit_kind`
    for a snapshot one.

    Previously each of four call sites (agent_fixture_extractor.py's
    `_extract_from_commit`/`_extract_from_snapshot_file`,
    pre2021_fixture_extractor.py's `_extract_from_repo`, and
    fixture_extractor.py's `extract_fixtures_at_commit`) hand-rolled its own
    ~20-key dict literal from the same FixtureResult fields, with nothing
    enforcing the four stayed in sync -- a new FixtureResult field added
    later could easily be wired into one call site and silently forgotten
    in the other three.
    """
    return {
        "name": fixture.name,
        "fixture_type": fixture.fixture_type,
        "loc": fixture.loc,
        "language": language,
        "file_path": file_path,
        "start_line": fixture.start_line,
        "end_line": fixture.end_line,
        "cyclomatic_complexity": fixture.cyclomatic_complexity,
        "num_comment_lines": fixture.num_comment_lines,
        "comment_density": fixture.comment_density,
        "num_parameters": fixture.num_parameters,
        "fixture_role": fixture.fixture_role,
        "raw_source": fixture.raw_source,
        "mocks": [
            {
                "framework": m.framework,
                "category": m.category,
                "target_identifier": m.target_identifier,
                "raw_snippet": m.raw_snippet,
            }
            for m in fixture.mocks
        ],
        **extra,
    }


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


_TEARDOWN_DETECTION = _PATTERNS["teardown_detection"]
NAME_BASED_TEARDOWN_PAIRS: dict[str, dict[str, str]] = _TEARDOWN_DETECTION[
    "name_based_pairs"
]
TYPE_BASED_TEARDOWN_PAIRS: dict[str, str] = _TEARDOWN_DETECTION["type_based_pairs"]


# ---------------------------------------------------------------------------
# fixture_role: setup / teardown / setup_and_teardown / other
# ---------------------------------------------------------------------------
#
# "setup_and_teardown" only ever arises from the pytest_decorator body-
# analysis path (classify_pytest_fixture_kind() in detector_python.py) --
# the type/name-based classification below only ever distinguishes setup
# from teardown (or falls through to "other"), never both at once.
#
# `pytest_decorator` is handled separately, NOT here: type/name alone can't
# split it (every pytest fixture is just named whatever the developer called
# it), so detector_python.py's _detect_python() classifies it directly via
# body analysis (classify_pytest_fixture_kind()) at detection time, using
# the tree-sitter body node it already has -- before _classify_fixture_kinds()
# ever runs. This function skips fixture_type == "pytest_decorator" rows
# rather than overwriting that.
TYPE_BASED_SETUP_KIND_TYPES: set[str] = set(TYPE_BASED_TEARDOWN_PAIRS.keys())
TYPE_BASED_TEARDOWN_KIND_TYPES: set[str] = set(TYPE_BASED_TEARDOWN_PAIRS.values())
NAME_BASED_SETUP_KIND_NAMES: dict[str, set[str]] = {
    ft: set(names.keys()) for ft, names in NAME_BASED_TEARDOWN_PAIRS.items()
}
NAME_BASED_TEARDOWN_KIND_NAMES: dict[str, set[str]] = {
    ft: set(names.values()) for ft, names in NAME_BASED_TEARDOWN_PAIRS.items()
}


def _classify_fixture_kind(fixture_type: str, name: str) -> str:
    """setup/teardown/other for one (fixture_type, name) pair -- everything
    except pytest_decorator (see module comment above). junit_rule/
    vitest_around_*/testng_data_provider fall through to 'other': they
    can't be split by type or name either, but unlike pytest_decorator
    there's no body-analysis mechanism for them (yet)."""
    if fixture_type in TYPE_BASED_SETUP_KIND_TYPES:
        return "setup"
    if fixture_type in TYPE_BASED_TEARDOWN_KIND_TYPES:
        return "teardown"
    if fixture_type in NAME_BASED_TEARDOWN_PAIRS:
        if name in NAME_BASED_SETUP_KIND_NAMES[fixture_type]:
            return "setup"
        if name in NAME_BASED_TEARDOWN_KIND_NAMES[fixture_type]:
            return "teardown"
    return "other"


def _classify_fixture_kinds(fixtures: list[FixtureResult]) -> None:
    """Post-process fixtures to set fixture_role for every fixture
    except pytest_decorator, which detector_python.py's _detect_python()
    already classified directly (body analysis, not type/name) at
    detection time. Modifies fixtures in-place."""
    for fixture in fixtures:
        if fixture.fixture_type == "pytest_decorator":
            continue
        fixture.fixture_role = _classify_fixture_kind(
            fixture.fixture_type, fixture.name
        )
