"""JavaScript/TypeScript fixture detection: Jest/Mocha/Vitest hooks.

Only Jest, Mocha, and Vitest are covered -- these are JS/TS's dominant,
actively-maintained testing frameworks. Other frameworks (AVA) and
speculative patterns not tied to any real, currently-used package (TS
decorator-style hooks) are deliberately out of scope; see
fixture_definitions.yaml's javascript_typescript.excluded list for why.

Pattern tables are loaded from
collection/heuristics/fixture_definitions.yaml rather than hardcoded here
-- see that file for the full operational definition of "fixture" per
language, including documented exclusions (Jest globalSetup, Vitest
setupFiles/onTestFinished, etc.).

Async fixtures are captured the same as sync ones: `beforeEach(async () =>
{...})` is still a call_expression whose function name is "beforeEach" (the
`async` keyword only qualifies the callback argument, not the call itself).
The lifecycle hook name is the detection signal, not the function's async
qualifier -- see
tests/collection/test_extractor_unit/test_javascript_fixtures.py::TestAsyncJavaScriptFixtures.
"""

from .detector_shared import FixtureResult, _build_result, _source
from .heuristics import load_fixture_definitions

_DEFS = load_fixture_definitions()["javascript_typescript"]

JS_FIXTURE_CALLS: dict[str, tuple[str, str]] = {
    name: (fields["fixture_type"], fields["scope"])
    for name, fields in _DEFS["hooks"].items()
}


def _enclosing_describe_id(node, src_bytes: bytes) -> "int | None":
    """Walk up from a hook's call_expression node to the nearest enclosing
    describe(...) call and return its AST byte-offset as a stable identity
    for teardown pairing -- distinguishes independent describe() blocks in
    the same file (a beforeEach in one block must not pair with an afterEach
    in an unrelated sibling block just for sharing a type+scope). None if
    the hook isn't wrapped in any describe() (e.g. a bare top-level hook)."""
    current = node.parent
    while current is not None:
        if current.type == "call_expression":
            func_node = current.child_by_field_name("function")
            if func_node is not None and _source(func_node, src_bytes).strip() == "describe":
                return current.start_byte
        current = current.parent
    return None


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

                # Check standard hooks (Jest/Mocha/Vitest) - ambiguous, so framework=None
                if name in JS_FIXTURE_CALLS:
                    fixture_type, scope = JS_FIXTURE_CALLS[name]
                    results.append(
                        _build_result(
                            func_node=target,
                            src_bytes=src_bytes,
                            fixture_type=fixture_type,
                            scope=scope,
                            framework=None,  # Ambiguous: could be Jest, Mocha, or Vitest
                            language=language,
                            container_id=_enclosing_describe_id(target, src_bytes),
                        )
                    )

        for child in node.children:
            visit(child)

    visit(tree.root_node)
    return results
