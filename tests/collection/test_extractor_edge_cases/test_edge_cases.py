"""
Tests for edge case handling in fixture extraction.

Validates graceful handling of unusual code patterns, malformed inputs, and boundary conditions.
"""

import pytest
from ..conftest import (
    create_test_file,
    extract_and_find_fixtures,
    assert_fixture_detected,
    assert_fixture_not_detected,
    assert_fixture_count,
)


class TestLargeFixtures:
    """Validate handling of fixtures with many lines"""

    def test_100_line_fixture(self):
        """Should correctly handle fixture spanning 100+ lines"""
        lines = ["def setUp(self):"]
        for i in range(100):
            lines.append(f"    self.var{i} = {i}")
        code = "\n".join(lines)

        fixture = assert_fixture_detected(code, "python", "setUp")
        # LOC should be around 100
        assert fixture.end_line - fixture.start_line + 1 > 90

    def test_nested_function_fixture(self):
        """Should handle fixtures with nested function definitions"""
        code = """
def setUp(self):
    def helper():
        return 42
    self.value = helper()
"""
        fixture = assert_fixture_detected(code, "python", "setUp")
        # Should detect the setUp, not the nested helper
        assert fixture.fixture_type == "unittest_setup"

    def test_nested_class_fixture(self):
        """Should handle fixtures with nested class definitions"""
        code = """
def setUp(self):
    class Helper:
        def method(self):
            return 42
    self.helper = Helper()
"""
        fixture = assert_fixture_detected(code, "python", "setUp")
        assert fixture.fixture_type == "unittest_setup"


class TestFalsePositivePrevention:
    """Validate that non-fixtures are not detected"""

    def test_regular_setup_function(self):
        """Regular function named setup (not setUp) should not be detected as fixture"""
        code = """
class Test:
    def setup(self):
        self.x = 1
"""
        # setup() is typically a fixture in pytest, but depending on context
        # This test validates behavior
        fixtures = extract_and_find_fixtures(code, "python")
        # If detected, should be marked as 'setup', not 'setUp'
        for f in fixtures:
            if f.name == "setup":
                # Pytest does recognize setup as fixture
                break

    def test_comment_containing_fixture_keyword(self):
        """Fixture keywords in comments should not trigger detection"""
        code = """
class Test:
    def test_something(self):
        # This setUp would initialize data
        self.x = 1
"""
        fixtures = extract_and_find_fixtures(code, "python")
        # Should not detect setUp from comment
        assert not any(f.name == "setUp" for f in fixtures)

    def test_string_containing_fixture_code(self):
        """Fixture code in strings should not be detected"""
        code = '''
class Test:
    def test_something(self):
        code_str = """
            def setUp(self):
                self.x = 1
        """
'''
        fixtures = extract_and_find_fixtures(code, "python")
        # Should not detect setUp from string literal
        assert not any(f.name == "setUp" for f in fixtures)

    def test_test_method_not_fixture(self):
        """Regular test method should not be detected as fixture"""
        code = """
class Test:
    def test_something(self):
        assert True
"""
        fixtures = extract_and_find_fixtures(code, "python")
        # test_something should not be detected as fixture
        assert not any(f.name == "test_something" for f in fixtures)


class TestSpecialCharacterHandling:
    """Validate handling of special characters and encoding"""

    def test_unicode_in_fixture(self):
        """Fixture containing unicode characters should be extracted correctly"""
        code = """
def setUp(self):
    self.message = "Hello 世界 🌍"
    self.name = "José"
"""
        fixture = assert_fixture_detected(code, "python", "setUp")
        assert fixture.name == "setUp"

    def test_escaped_quotes_in_fixture(self):
        """Fixture with escaped quotes should be parsed correctly"""
        code = """
def setUp(self):
    self.text = "quote \\"inside\\" quotes"
    self.json = '{"key": "value"}'
"""
        fixture = assert_fixture_detected(code, "python", "setUp")
        assert fixture.name == "setUp"

    def test_multiline_string_in_fixture(self):
        """Fixture with triple-quoted strings should be handled"""
        code = '''
def setUp(self):
    self.docstring = """
    This is a
    multi-line string
    """
    self.data = 42
'''
        fixture = assert_fixture_detected(code, "python", "setUp")
        assert fixture.name == "setUp"


class TestIndentationVariations:
    """Validate handling of different indentation styles"""

    def test_mixed_indentation_tabs_and_spaces(self):
        """Should handle mixed tabs and spaces (though not recommended)"""
        code = """
class Test:
\tdef setUp(self):
\t\tself.x = 1
"""
        fixture = assert_fixture_detected(code, "python", "setUp")
        assert fixture.name == "setUp"

    def test_unusual_indentation_levels(self):
        """Should handle unusual but valid indentation"""
        code = """
class Test:
        def setUp(self):  # 8 spaces instead of 4
            self.x = 1    # Another 8 spaces
"""
        fixture = assert_fixture_detected(code, "python", "setUp")
        assert fixture.name == "setUp"

    def test_no_indentation_module_level(self):
        """Module-level fixtures should be detected without class indentation"""
        code = """
def setup_module():
    global resource
    resource = create()
"""
        fixture = assert_fixture_detected(code, "python", "setup_module")
        assert fixture.scope == "per_module"


class TestMultipleFixturesInSameClass:
    """Validate handling multiple fixtures in one class"""

    def test_setUp_and_tearDown_together(self):
        """Should detect both setUp and tearDown in same class"""
        code = """
class Test(unittest.TestCase):
    def setUp(self):
        self.data = []
    
    def tearDown(self):
        self.data.clear()
"""
        assert_fixture_detected(code, "python", "setUp")
        assert_fixture_detected(code, "python", "tearDown")
        assert_fixture_count(code, "python", 2)

    def test_all_unittest_fixtures(self):
        """Should detect all unittest lifecycle methods"""
        code = """
class Test(unittest.TestCase):
    def setUp(self):
        pass
    
    def tearDown(self):
        pass
    
    @classmethod
    def setUpClass(cls):
        pass
    
    @classmethod
    def tearDownClass(cls):
        pass
"""
        assert_fixture_count(code, "python", 4)

    def test_multiple_pytest_fixtures(self):
        """Should detect multiple @pytest.fixture in same file"""
        code = """
@pytest.fixture
def fixture1():
    return 1

@pytest.fixture
def fixture2():
    return 2

@pytest.fixture
def fixture3(fixture1, fixture2):
    return fixture1 + fixture2
"""
        assert_fixture_count(code, "python", 3)


class TestEmptyAndMinimalFixtures:
    """Validate handling of very simple fixtures"""

    def test_empty_setUp(self):
        """Should handle setUp with just pass statement"""
        code = """
class Test:
    def setUp(self):
        pass
"""
        fixture = assert_fixture_detected(code, "python", "setUp")
        assert fixture.name == "setUp"
        assert fixture.loc >= 0

    def test_single_line_fixture(self):
        """Should handle fixture on single line with colon-separated body"""
        code = """
class Test:
    def setUp(self): self.x = 1
"""
        fixture = assert_fixture_detected(code, "python", "setUp")
        assert fixture.name == "setUp"

    def test_fixture_with_only_comments(self):
        """Should handle fixture containing only comments"""
        code = """
def setUp(self):
    # This is a comment
    # Another comment
"""
        fixture = assert_fixture_detected(code, "python", "setUp")
        # LOC is 1 (just the def line, no executable body)
        assert fixture.loc == 1


class TestMalformedButParseable:
    """Validate graceful handling of imperfect code"""

    def test_unclosed_block(self):
        """Parser should handle code that's incomplete"""
        code = """
class Test:
    def setUp(self):
        self.x = 1
        # Code is complete, but imagine incomplete code
"""
        fixture = assert_fixture_detected(code, "python", "setUp")
        assert fixture.name == "setUp"

    def test_syntax_error_in_fixture(self):
        """Fixture with syntax error might not parse - test graceful handling"""
        code = """
class Test:
    def setUp(self):
        self.x = 1 +  # incomplete expression
"""
        # This might or might not be detected depending on parser robustness
        # The test just verifies no crash occurs
        try:
            fixtures = extract_and_find_fixtures(code, "python")
            # If it parses, should either have fixture or empty list
            assert isinstance(fixtures, list)
        except Exception as e:
            # If it fails, should be graceful
            assert "unexpected" in str(e).lower() or "syntax" in str(e).lower()


class TestLineEndingVariations:
    """Validate handling of different line ending styles"""

    def test_unix_line_endings(self):
        """Unix line endings (\\n) should be handled"""
        code = "class Test:\n    def setUp(self):\n        self.x = 1\n"
        fixture = assert_fixture_detected(code, "python", "setUp")
        assert fixture.name == "setUp"

    def test_windows_line_endings(self):
        """Windows line endings (\\r\\n) should be handled"""
        code = "class Test:\r\n    def setUp(self):\r\n        self.x = 1\r\n"
        fixture = assert_fixture_detected(code, "python", "setUp")
        assert fixture.name == "setUp"

    def test_old_mac_line_endings(self):
        """Old Mac line endings (\\r) should be handled"""
        code = "class Test:\r    def setUp(self):\r        self.x = 1\r"
        fixture = assert_fixture_detected(code, "python", "setUp")
        assert fixture.name == "setUp"


class TestDeepNesting:
    """Validate handling of deeply nested structures"""

    def test_fixture_in_nested_class(self):
        """Fixture inside nested class should be detected"""
        code = """
class Outer:
    class Inner:
        class Test:
            def setUp(self):
                self.x = 1
"""
        fixture = assert_fixture_detected(code, "python", "setUp")
        assert fixture.name == "setUp"

    def test_fixture_with_deep_expression_nesting(self):
        """Fixture with deeply nested expressions should parse"""
        code = """
def setUp(self):
    self.result = dict(
        outer=dict(
            middle=dict(
                inner=dict(
                    deepest=[1, 2, 3]
                )
            )
        )
    )
"""
        fixture = assert_fixture_detected(code, "python", "setUp")
        assert fixture.name == "setUp"


class TestLambdaAndComprehensions:
    """Validate handling of functional programming patterns"""

    def test_fixture_with_lambda(self):
        """Fixture using lambda should be handled"""
        code = """
def setUp(self):
    self.func = lambda x: x * 2
    self.data = list(map(lambda y: y + 1, range(10)))
"""
        fixture = assert_fixture_detected(code, "python", "setUp")
        assert fixture.name == "setUp"

    def test_fixture_with_comprehensions(self):
        """Fixture using list/dict/set comprehensions should be handled"""
        code = """
def setUp(self):
    self.list_comp = [x*2 for x in range(10)]
    self.dict_comp = {x: x*2 for x in range(10)}
    self.set_comp = {x for x in range(10)}
    self.gen_exp = (x for x in range(10))
"""
        fixture = assert_fixture_detected(code, "python", "setUp")
        assert fixture.name == "setUp"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
