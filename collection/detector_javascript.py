"""JavaScript/TypeScript fixture detection: Jest/Mocha/Vitest hooks, AVA, TS decorators."""

from .detector_shared import FixtureResult, _build_result, _source

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
