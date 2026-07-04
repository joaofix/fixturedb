"""Go fixture detection: TestMain, called-helper heuristics, testify/suite methods.

Not currently wired up: `DETECTORS` in `detector.py` has no "go" entry, and
`_get_parser()` never builds a Go tree-sitter grammar, so this module is
unreachable through the public `extract_fixtures()` API today. Preserved
as-is from before the module split rather than deleted or enabled, since
that's a behavior decision, not a refactor.
"""

import re

from .detector_shared import FixtureResult, _build_result, _source


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
