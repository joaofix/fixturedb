"""Tests for collection/detector_python.py's pytest fixture setup/teardown/
setup_and_teardown body-analysis classification.

`_classify()` mirrors classify_pytest_fixture_kind_from_source()'s own
node-location logic (parse -> find function_definition -> its "body" field)
but calls classify_pytest_fixture_kind() directly, so these tests exercise
the actual documented entry point (node + source bytes) rather than only
its source-string wrapper. classify_pytest_fixture_kind_from_source() itself
is covered separately, in TestClassifyFromSource, for its own parse-failure/
no-function-found fallback behavior.
"""

from __future__ import annotations

from collection.detector_python import (
    classify_pytest_fixture_kind,
    classify_pytest_fixture_kind_from_source,
)
from collection.detector_shared import _get_parser


def _classify(source: str) -> str:
    src_bytes = source.encode("utf-8")
    tree = _get_parser("python").parse(src_bytes)
    func_node = next(
        c for c in tree.root_node.children if c.type == "function_definition"
    )
    body_node = func_node.child_by_field_name("body")
    return classify_pytest_fixture_kind(body_node, src_bytes)


class TestReturnsSetupAndTeardown:
    def test_addfinalizer_with_setup_code_before_it(self):
        source = """
def db(request):
    conn = connect()
    request.addfinalizer(conn.close)
    return conn
"""
        assert _classify(source) == "setup_and_teardown"

    def test_addfinalizer_and_a_yield_both_present(self):
        source = """
def db(request):
    conn = connect()
    request.addfinalizer(conn.close)
    yield conn
"""
        assert _classify(source) == "setup_and_teardown"

    def test_yield_after_setup_code_standard_pattern(self):
        source = """
def db():
    conn = connect()
    yield conn
    conn.close()
"""
        assert _classify(source) == "setup_and_teardown"

    def test_yield_inside_with_block(self):
        source = """
def tmp_file():
    with open("/tmp/f", "w") as f:
        yield f
"""
        assert _classify(source) == "setup_and_teardown"

    def test_yield_inside_try_finally_block(self):
        source = """
def db():
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()
"""
        assert _classify(source) == "setup_and_teardown"

    def test_yield_inside_conditional(self):
        source = """
def maybe_db(request):
    conn = connect()
    if request.param:
        yield conn
    else:
        yield None
    conn.close()
"""
        assert _classify(source) == "setup_and_teardown"

    def test_yield_as_first_statement_but_with_a_value(self):
        source = """
def db():
    yield connect()
"""
        assert _classify(source) == "setup_and_teardown"

    def test_docstring_then_setup_code_then_yield(self):
        source = '''
def db():
    """Provides a live connection."""
    conn = connect()
    yield conn
    conn.close()
'''
        assert _classify(source) == "setup_and_teardown"

    def test_multiple_yields_first_has_a_value(self):
        """Multiple yields: not the bare-first-yield 'teardown' path (the
        first yield has a value), so falls through to setup_and_teardown --
        the same rule as any other non-bare-first yield, just with more
        than one yield present."""
        source = """
def counter():
    yield 1
    yield 2
"""
        assert _classify(source) == "setup_and_teardown"

    def test_addfinalizer_wins_over_bare_first_yield(self):
        """addfinalizer takes priority over the bare-first-yield 'teardown'
        rule, even when the fixture body would otherwise match it."""
        source = """
def db(request):
    request.addfinalizer(cleanup)
    yield
"""
        assert _classify(source) == "setup_and_teardown"

    def test_addfinalizer_matches_any_receiver_not_only_request(self):
        """Match is on the method name alone -- some codebases alias the
        fixture's request parameter to a different name."""
        source = """
def db(req):
    conn = connect()
    req.addfinalizer(conn.close)
    return conn
"""
        assert _classify(source) == "setup_and_teardown"


class TestReturnsSetup:
    def test_no_yield_no_addfinalizer_returns_a_value(self):
        source = """
def config():
    return {"debug": True}
"""
        assert _classify(source) == "setup"

    def test_no_yield_no_addfinalizer_no_return(self):
        source = """
def logger():
    configure_logging()
"""
        assert _classify(source) == "setup"

    def test_yield_only_inside_nested_function_definition(self):
        """A yield inside a nested `def` belongs to that inner function,
        not the fixture -- the fixture itself has no yield."""
        source = """
def make_generator():
    def inner():
        yield 1
    return inner
"""
        assert _classify(source) == "setup"

    def test_empty_body_no_statements_at_all(self):
        source = """
def noop():
    pass
"""
        assert _classify(source) == "setup"

    def test_body_with_only_a_docstring(self):
        source = '''
def noop():
    """Does nothing."""
'''
        assert _classify(source) == "setup"


class TestReturnsTeardown:
    def test_bare_yield_first_statement_teardown_code_after(self):
        source = """
def cleanup_only():
    yield
    remove_temp_files()
"""
        assert _classify(source) == "teardown"

    def test_docstring_then_bare_yield_as_first_executable_statement(self):
        source = '''
def cleanup_only():
    """Runs cleanup after the test."""
    yield
    remove_temp_files()
'''
        assert _classify(source) == "teardown"

    def test_comment_before_yield_is_not_a_statement(self):
        source = """
def cleanup_only():
    # nothing to set up
    yield
"""
        assert _classify(source) == "teardown"


class TestClassifyFromSource:
    """classify_pytest_fixture_kind_from_source() -- the raw_source-string
    entry point rq2.py's _kind() actually calls, including its own
    parse-failure/no-function-found fallback (distinct from
    classify_pytest_fixture_kind()'s 'setup' answer for a genuinely empty
    *but valid* body)."""

    def test_empty_string_returns_other(self):
        assert classify_pytest_fixture_kind_from_source("") == "other"

    def test_non_python_garbage_returns_other(self):
        assert classify_pytest_fixture_kind_from_source("{{{ not python") == "other"

    def test_real_decorator_stripped_source_round_trips(self):
        """fixtures.raw_source stores just the `def name(...): ...` text,
        decorator already stripped (see detector_python.py's _detect_python
        docstring / detector_shared.py's _detect_fixture_dependencies) --
        this is exactly that shape."""
        raw_source = """def db(request):
    conn = connect()
    request.addfinalizer(conn.close)
    yield conn
"""
        assert classify_pytest_fixture_kind_from_source(raw_source) == "setup_and_teardown"

    def test_plain_setup_source_round_trips(self):
        raw_source = """def config():
    return {"debug": True}
"""
        assert classify_pytest_fixture_kind_from_source(raw_source) == "setup"
