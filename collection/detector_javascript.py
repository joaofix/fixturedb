"""JavaScript/TypeScript fixture detection: Jest/Mocha/Vitest hooks, AVA, TS decorators.

Pattern tables are loaded from
collection/config_data/fixture_definitions.yaml rather than hardcoded here
-- see that file for the full operational definition of "fixture" per
language, including documented exclusions (Jest globalSetup, Vitest
setupFiles, aliased AVA imports, etc.).
"""

from .config_data import load_fixture_definitions
from .detector_shared import FixtureResult, _build_result, _source

_DEFS = load_fixture_definitions()["javascript_typescript"]

JS_FIXTURE_CALLS: dict[str, tuple[str, str]] = {
    name: (fields["fixture_type"], fields["scope"])
    for name, fields in _DEFS["hooks"].items()
}

# AVA fixture patterns - using member access like test.before()
AVA_FIXTURE_PATTERNS: dict[str, tuple[str, str]] = {
    name: (fields["fixture_type"], fields["scope"])
    for name, fields in _DEFS["ava_patterns"].items()
}

# TypeScript decorator-style hooks: @Before, @After, @BeforeEach, etc.
TS_DECORATOR_MAP: dict[str, tuple[str, str]] = {
    name: (fields["fixture_type"], fields["scope"])
    for name, fields in _DEFS["ts_decorators"].items()
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

                        if dec_name in TS_DECORATOR_MAP:
                            fixture_type, scope = TS_DECORATOR_MAP[dec_name]
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
