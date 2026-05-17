"""
Tests for extraction metadata accuracy.

Validates that extracted fixture metadata (line numbers, LOC, scope, type, metrics) is correct.
"""

import pytest
from ..conftest import (
    extract_and_find_fixtures,
    assert_fixture_detected,
    assert_line_range,
    assert_loc,
    assert_fixture_metrics,
)


class TestLineNumberAccuracy:
    """Validate start_line and end_line are correct"""

    def test_single_line_fixture_line_numbers(self):
        """Single-line fixture should have same start and end line"""
        code = """import unittest

class Test(unittest.TestCase):
    def setUp(self): self.x = 1
"""
        # Line numbers are 1-indexed
        fixture = assert_fixture_detected(code, "python", "setUp")
        # setUp is on line 4
        assert fixture.start_line == 4
        assert fixture.end_line == 4

    def test_multiline_fixture_line_numbers(self):
        """Multi-line fixture should have correct start and end"""
        code = """import unittest

class Test(unittest.TestCase):
    def setUp(self):
        self.x = 1
        self.y = 2
        self.z = 3
"""
        fixture = assert_fixture_detected(code, "python", "setUp")
        # setUp starts on line 4, ends on line 7
        assert_line_range(fixture, 4, 7)

    def test_fixture_with_blank_lines(self):
        """Fixture containing blank lines should have correct line range"""
        code = """
def setUp(self):
    x = 1

    y = 2
    
    z = 3
"""
        fixture = assert_fixture_detected(code, "python", "setUp")
        # Check that line range includes blank lines
        assert fixture.start_line < fixture.end_line

    def test_pytest_fixture_line_numbers(self):
        """Pytest fixtures should have accurate line numbers"""
        code = """
@pytest.fixture
def my_fixture():
    return create_object()
"""
        fixture = assert_fixture_detected(code, "python", "my_fixture")
        # Decorator is on line 2, function starts on line 3
        # Line range should include decorator
        assert fixture.start_line == 2  # Starts at decorator
        assert fixture.end_line == 4  # Ends after return


class TestLineOfCodeCounting:
    """Validate loc (lines of code) counting"""

    def test_single_statement_loc(self):
        """Single statement fixture should have LOC=2"""
        code = """
def setUp(self):
    self.x = 1
"""
        fixture = assert_fixture_detected(code, "python", "setUp")
        assert_loc(fixture, 2)

    def test_multiline_fixture_loc(self):
        """Multi-line fixture LOC should count all lines"""
        code = """
def setUp(self):
    self.x = 1
    self.y = 2
    self.z = 3
"""
        fixture = assert_fixture_detected(code, "python", "setUp")
        # 4 lines total (def + 3 statements)
        assert_loc(fixture, 4)

    def test_fixture_with_comments_loc(self):
        """LOC includes comment lines"""
        code = """
def setUp(self):
    # Initialize data
    self.x = 1
    # Set y
    self.y = 2
"""
        fixture = assert_fixture_detected(code, "python", "setUp")
        # LOC includes comments: def + comment + statement + comment + statement = 5
        assert_loc(fixture, 5)

    def test_fixture_with_blank_lines_loc(self):
        """LOC counting for fixtures with blank lines"""
        code = """
def setUp(self):
    self.x = 1

    self.y = 2

    self.z = 3
"""
        fixture = assert_fixture_detected(code, "python", "setUp")
        # Detector counts non-blank lines: def + 3 statements = 4
        assert_loc(fixture, 4)


class TestFixtureTypeClassification:
    """Validate fixture_type is correctly classified"""

    def test_setUp_type(self):
        """setUp should be classified as 'unittest_setup' type"""
        code = """
class Test(unittest.TestCase):
    def setUp(self):
        pass
"""
        fixture = assert_fixture_detected(code, "python", "setUp")
        assert fixture.fixture_type == "unittest_setup"

    def test_tearDown_type(self):
        """tearDown should be classified as 'unittest_setup' type"""
        code = """
class Test(unittest.TestCase):
    def tearDown(self):
        pass
"""
        fixture = assert_fixture_detected(code, "python", "tearDown")
        assert fixture.fixture_type == "unittest_setup"

    def test_pytest_fixture_type(self):
        """@pytest.fixture should be classified as 'pytest_decorator' type"""
        code = """
@pytest.fixture
def my_data():
    return {"key": "value"}
"""
        fixture = assert_fixture_detected(code, "python", "my_data")
        assert fixture.fixture_type == "pytest_decorator"

    def test_setup_module_type(self):
        """setup_module should be classified as nose_fixture"""
        code = """
def setup_module():
    global db
    db = create_db()
"""
        fixture = assert_fixture_detected(code, "python", "setup_module")
        # Should be nose_fixture
        assert fixture.fixture_type == "nose_fixture"


class TestFixtureScopeDetection:
    """Validate scope is correctly determined"""

    def test_per_test_scope(self):
        """Regular setUp should be per_test scope"""
        code = """
class Test(unittest.TestCase):
    def setUp(self):
        self.x = 1
"""
        fixture = assert_fixture_detected(code, "python", "setUp")
        assert fixture.scope == "per_test"

    def test_per_class_scope(self):
        """setUpClass should be per_class scope"""
        code = """
class Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = create_db()
"""
        fixture = assert_fixture_detected(code, "python", "setUpClass")
        assert fixture.scope == "per_class"

    def test_per_module_scope(self):
        """setup_module should be per_module scope"""
        code = """
def setup_module():
    global resource
    resource = create_resource()
"""
        fixture = assert_fixture_detected(code, "python", "setup_module")
        assert fixture.scope == "per_module"

    def test_pytest_fixture_default_scope(self):
        """Default pytest fixture should be per_test scope"""
        code = """
@pytest.fixture
def my_fixture():
    return value
"""
        fixture = assert_fixture_detected(code, "python", "my_fixture")
        # Default pytest scope is function (per_test)
        assert fixture.scope in ("per_test", "per_function")


class TestFixtureMetrics:
    """Validate complexity and code metrics"""

    def test_simple_fixture_metrics(self):
        """Simple fixture should have low complexity and few parameters"""
        code = """
def setUp(self):
    self.x = 1
"""
        fixture = assert_fixture_detected(code, "python", "setUp")
        # Should be simple: low complexity, no parameters (self doesn't count)
        assert_fixture_metrics(fixture, max_complexity=5)

    def test_fixture_with_conditional_complexity(self):
        """Fixture with if/else should have higher cyclomatic complexity"""
        code = """
def setUp(self):
    if condition:
        self.x = 1
    else:
        self.x = 2
"""
        fixture = assert_fixture_detected(code, "python", "setUp")
        # Should have complexity >= 2 due to branch
        assert_fixture_metrics(fixture, min_complexity=2)

    def test_fixture_with_loop_complexity(self):
        """Fixture with loop should increase complexity"""
        code = """
def setUp(self):
    self.items = []
    for i in range(10):
        self.items.append(i)
"""
        fixture = assert_fixture_detected(code, "python", "setUp")
        # Should have complexity >= 2 due to loop
        assert_fixture_metrics(fixture, min_complexity=2)

    def test_fixture_with_parameters(self):
        """Fixture with parameters should track num_parameters"""
        code = """
@pytest.fixture
def my_fixture(param1, param2):
    return param1 + param2
"""
        fixture = assert_fixture_detected(code, "python", "my_fixture")
        # Should have 2 parameters
        assert_fixture_metrics(fixture, num_parameters=2)

    def test_fixture_instantiations(self):
        """Fixture creating objects should track num_objects_instantiated"""
        code = """
def setUp(self):
    self.user = User(name="test")
    self.db = Database()
    self.cache = Cache()
"""
        fixture = assert_fixture_detected(code, "python", "setUp")
        # Should detect 3 constructor calls
        assert fixture.num_objects_instantiated >= 3

    def test_fixture_external_calls(self):
        """Fixture with external I/O should track num_external_calls"""
        code = """
def setUp(self):
    self.db = open('database.db')
    self.file = open('data.txt')
    self.session = requests.Session()
"""
        fixture = assert_fixture_detected(code, "python", "setUp")
        # Should detect external calls (open, requests, etc.)
        assert fixture.num_external_calls > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
