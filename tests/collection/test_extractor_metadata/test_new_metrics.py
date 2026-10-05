"""
Tests for FixtureResult's remaining metric fields (cyclomatic_complexity,
num_parameters, comment_density) and detection edge cases.
"""

from pathlib import Path

from collection.detector import extract_fixtures


class TestFixtureResultStructure:
    """Test that FixtureResult contains all new fields."""

    def test_fixture_result_has_all_fields(self):
        """FixtureResult should include all metric fields."""
        code = """
@pytest.fixture
def complete_fixture(dep):
    if True:
        x = 1
    yield x
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "python")

            if result.fixtures:
                fixture = result.fixtures[0]
                # Check all required fields exist
                assert hasattr(fixture, "cyclomatic_complexity")
                assert hasattr(fixture, "num_parameters")

                # Verify they have sensible default values
                assert fixture.cyclomatic_complexity >= 1
                assert fixture.num_parameters >= 0

    def test_fixture_baseline_metrics_consistent(self):
        """Verify baseline metrics are consistent with earlier phase implementations."""
        code = """
@pytest.fixture
def baseline_fixture(a, b):
    result = a + b
    if result > 10:
        result *= 2
    return result
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "python")

            if result.fixtures:
                fixture = result.fixtures[0]
                # Verify phase 1+2 metrics are still computed
                assert fixture.cyclomatic_complexity >= 1  # Lizard
                assert fixture.num_parameters == 2  # Lizard (a, b)


class TestPythonSelfClsExcludedFromParameterCount:
    """num_parameters must not count the implicit `self`/`cls` receiver --
    Java/JS/TS have no equivalent implicit first parameter, so leaving it in
    (Lizard's native behavior) silently inflated every Python method-style
    fixture (unittest/pytest-class-method/nose) by 1 relative to an
    equivalent bare pytest_decorator function or a same-shaped Java/JS
    fixture. See collection/detector_shared.py::_build_result."""

    def test_self_only_is_zero_parameters(self):
        code = """
class TestExample(unittest.TestCase):
    def setUp(self):
        self.x = 1
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "python")
            setup = next(f for f in result.fixtures if f.name == "setUp")
            assert setup.num_parameters == 0

    def test_self_plus_two_explicit_params(self):
        code = """
class TestExample(unittest.TestCase):
    def setUp(self, a, b):
        self.x = a + b
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "python")
            setup = next(f for f in result.fixtures if f.name == "setUp")
            assert setup.num_parameters == 2

    def test_cls_only_is_zero_parameters(self):
        code = """
class TestExample(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pass
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "python")
            setup = next(f for f in result.fixtures if f.name == "setUpClass")
            assert setup.num_parameters == 0


class TestPythonDecoratorExcludedFromFixtureScope:
    """A pytest/behave decorator's own arguments are not part of the
    fixture's body -- start_line/end_line and mocks must all be scoped to
    the function only, consistent with raw_source (which was already
    function-only). The decorated_definition node (decorator
    included) was used for line range/mocks while the bare
    function_definition was used for raw_source/complexity, so the
    reported line range disagreed with raw_source by exactly the decorator
    line, and any mock construct sitting in the decorator's own arguments
    leaked into that fixture's metrics. See
    collection/detector_shared.py::_build_result."""

    def test_line_range_matches_raw_source_not_decorator(self):
        code = """
@pytest.fixture
def my_fixture():
    return create_object()
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "python")
            fixture = next(f for f in result.fixtures if f.name == "my_fixture")
            # Decorator on line 2, function on line 3-4
            assert fixture.start_line == 3
            assert fixture.end_line == 4
            assert fixture.raw_source == "def my_fixture():\n    return create_object()"

    def test_mock_in_decorator_args_not_attributed_to_fixture(self):
        code = """
@pytest.fixture(params=[MagicMock()])
def my_fixture():
    return 1
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "python")
            fixture = next(f for f in result.fixtures if f.name == "my_fixture")
            assert fixture.mocks == []


class TestCommentDensity:
    """num_comment_lines/comment_density -- counted by walking the fixture's
    own tree-sitter node for comment-type nodes (see
    collection/detector_shared.py::_count_comment_lines), not a text-based
    scan, so a `#`/`//` inside a string literal can never be mistaken for a
    real comment. comment_density is always cross-checked against
    num_comment_lines/loc directly (the real formula) rather than a
    hardcoded fraction, so these tests don't depend on the exact loc a
    given detector reports for the fixture's own line span (e.g. whether an
    annotation line is included)."""

    def test_python_hash_comments_only(self):
        """Two standalone `#` comment lines (kept off any code line, to
        avoid ambiguity about whether a trailing same-line comment counts
        -- see _count_comment_lines()'s docstring: it counts by AST node,
        not by "is this whole physical line comment-only")."""
        code = """
@pytest.fixture
def fixture_with_comments():
    # comment one
    x = 1
    # comment two
    return x
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "python")
            fixture = next(f for f in result.fixtures if f.name == "fixture_with_comments")
            assert fixture.num_comment_lines == 2
            assert fixture.comment_density == fixture.num_comment_lines / fixture.loc

    def test_java_line_and_block_comments(self):
        """`//` line comment (1 line) plus a `/* */` block comment spanning
        two lines -- 3 total, via two distinct tree-sitter node types
        (line_comment/block_comment)."""
        code = """
public class ServiceTest {
    @Before
    public void setUp() {
        // line comment
        int x = 1;
        /* block
           comment */
        int y = 2;
    }
}
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "java")
            setup = next(f for f in result.fixtures if f.name == "setUp")
            assert setup.num_comment_lines == 3  # 1 line comment + 2-line block comment
            assert setup.comment_density == setup.num_comment_lines / setup.loc

    def test_typescript_line_and_block_comments(self):
        """Both `//` and `/* */` styles are the same "comment" node type in
        the JS/TS grammar (unlike Java's two distinct types) -- same 1 + 2
        = 3 shape as the Java test above."""
        code = """
beforeEach(() => {
    // line comment
    const x = 1;
    /* block
       comment */
    const y = 2;
});
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".test.ts", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "typescript")
            fixture = result.fixtures[0]
            assert fixture.num_comment_lines == 3
            assert fixture.comment_density == fixture.num_comment_lines / fixture.loc

    def test_python_docstring_not_counted_as_comment(self):
        """A docstring is a string-literal expression_statement in
        tree-sitter-python's grammar, never a `comment` node -- excluded
        from num_comment_lines structurally (there is no deliberate
        "skip docstrings" filter anywhere in the code; tree-sitter simply
        never classifies one as a comment in the first place)."""
        code = '''
@pytest.fixture
def fixture_with_docstring():
    """Sets up the fixture.

    Plays the same documentation role a Java Javadoc or JS/TS JSDoc
    block comment would.
    """
    # a real comment
    x = 1
    return x
'''
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "python")
            fixture = next(f for f in result.fixtures if f.name == "fixture_with_docstring")
            assert fixture.num_comment_lines == 1
            assert fixture.comment_density == fixture.num_comment_lines / fixture.loc

    def test_java_javadoc_preceding_method_not_counted(self):
        """A Javadoc block comment immediately preceding the method it
        documents is a sibling of method_declaration inside the
        enclosing class_body in tree-sitter-java's grammar, never a
        descendant of the method itself -- so it falls outside the
        fixture's own node span and _count_comment_lines()'s descendant
        walk never reaches it. Different mechanism than Python's
        docstring exclusion (sibling position vs. node type), same
        result: fixture-level documentation is never counted as an
        implementation comment."""
        code = """
public class ServiceTest {
    /**
     * Sets up the test.
     * Plays the same documentation role a Python docstring would.
     */
    @Before
    public void setUp() {
        // a real comment
        int x = 1;
    }
}
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "java")
            setup = next(f for f in result.fixtures if f.name == "setUp")
            assert setup.num_comment_lines == 1
            assert setup.comment_density == setup.num_comment_lines / setup.loc

    def test_java_javadoc_preceding_rule_field_not_counted(self):
        """Same exclusion for a field-level fixture (@Rule): the Javadoc
        is a sibling of field_declaration at the class_body level, not
        one of its descendants."""
        code = """
public class ServiceTest {
    /** The rule under test. */
    @Rule
    public TestName name = new TestName();
}
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "java")
            fixture = result.fixtures[0]
            assert fixture.num_comment_lines == 0

    def test_javascript_jsdoc_preceding_hook_not_counted(self):
        """A JSDoc block comment immediately preceding beforeEach(...) is
        a sibling within the enclosing block, not a descendant of the
        hook's own callback body -- same sibling-position exclusion as
        Java's Javadoc above."""
        code = """
describe('suite', () => {
    /**
     * Sets up the test.
     */
    beforeEach(() => {
        // a real comment
        const x = 1;
    });
});
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".test.js", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "javascript")
            fixture = result.fixtures[0]
            assert fixture.num_comment_lines == 1
            assert fixture.comment_density == fixture.num_comment_lines / fixture.loc

    def test_typescript_jsdoc_preceding_hook_not_counted(self):
        """Same exclusion in TypeScript's grammar as the JavaScript test
        above."""
        code = """
describe('suite', () => {
    /**
     * Sets up the test.
     */
    beforeEach(() => {
        // a real comment
        const x: number = 1;
    });
});
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".test.ts", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "typescript")
            fixture = result.fixtures[0]
            assert fixture.num_comment_lines == 1
            assert fixture.comment_density == fixture.num_comment_lines / fixture.loc

    def test_zero_comments_gives_zero_density(self):
        code = """
@pytest.fixture
def no_comments_fixture():
    x = 1
    y = 2
    return x + y
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "python")
            fixture = next(f for f in result.fixtures if f.name == "no_comments_fixture")
            assert fixture.num_comment_lines == 0
            assert fixture.comment_density == 0.0

    def test_zero_loc_gives_zero_density_not_a_crash(self):
        """loc=0 can't actually be produced by a real extracted fixture
        (even a bare one-line signature counts as 1 non-blank line), but
        _comment_density() -- the pure division helper _build_result() calls
        after computing loc -- must not raise ZeroDivisionError if it's ever
        called with one, and must return 0.0 rather than propagating a
        garbage value."""
        from collection.detector_shared import _comment_density

        assert _comment_density(0, 0) == 0.0
        assert _comment_density(5, 0) == 0.0  # non-zero numerator too -- still guarded
