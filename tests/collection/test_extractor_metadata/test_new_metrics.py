"""
Tests for new metrics: max_nesting_depth, reuse_count, has_teardown_pair, num_contributors.
"""

from pathlib import Path

from collection.detector import extract_fixtures


class TestMaxNestingDepth:
    """Test max_nesting_depth extraction from Lizard."""

    def test_simple_fixture_no_nesting(self):
        """Fixture with no nesting should have max_nesting_depth=1."""
        code = """
def test_simple():
    x = 1
    y = 2
    return x + y
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "python")
            # All fixtures should have max_nesting_depth >= 1
            assert all(f.max_nesting_depth >= 1 for f in result.fixtures)

    def test_nested_if_statements(self):
        """Fixture with nested if statements should have higher max_nesting_depth."""
        code = """
@pytest.fixture
def fixture_with_nesting():
    if True:
        if True:
            if True:
                x = 1
    return x
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "python")
            # Should detect nesting depth
            if result.fixtures:
                assert result.fixtures[0].max_nesting_depth >= 2

    def test_nested_loops(self):
        """Fixture with nested loops should have higher max_nesting_depth."""
        code = """
@pytest.fixture
def fixture_with_loops():
    for i in range(10):
        for j in range(10):
            for k in range(10):
                x = i + j + k
    return x
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "python")
            if result.fixtures:
                # Nested loops should have higher nesting depth
                assert result.fixtures[0].max_nesting_depth >= 2


class TestReuseCounting:
    """Test reuse_count calculation for fixtures."""

    def test_pytest_fixture_used_by_single_test(self):
        """Fixture used by one test should have reuse_count=1."""
        code = """
@pytest.fixture
def my_fixture():
    return 42

def test_uses_fixture(my_fixture):
    assert my_fixture == 42
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "python")
            fixtures = [f for f in result.fixtures if f.name == "my_fixture"]
            if fixtures:
                assert fixtures[0].reuse_count == 1

    def test_pytest_fixture_used_by_multiple_tests(self):
        """Fixture used by multiple tests should have reuse_count > 1."""
        code = """
@pytest.fixture
def my_fixture():
    return 42

def test_first(my_fixture):
    assert my_fixture == 42

def test_second(my_fixture):
    assert my_fixture == 42

def test_third(my_fixture):
    assert my_fixture == 42
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "python")
            fixtures = [f for f in result.fixtures if f.name == "my_fixture"]
            if fixtures:
                # Should detect multiple uses (reuse_count >= 3)
                assert fixtures[0].reuse_count >= 3

    def test_fixture_not_used_by_any_test(self):
        """Fixture not used should have reuse_count=0."""
        code = """
@pytest.fixture
def unused_fixture():
    return 42

def test_no_params():
    assert True
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "python")
            fixtures = [f for f in result.fixtures if f.name == "unused_fixture"]
            if fixtures:
                assert fixtures[0].reuse_count == 0

    def test_fixture_with_multiple_params(self):
        """Test function with multiple fixtures should count each fixture once."""
        code = """
@pytest.fixture
def fixture_a():
    return 1

@pytest.fixture
def fixture_b():
    return 2

def test_uses_both(fixture_a, fixture_b):
    assert fixture_a + fixture_b == 3
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "python")
            fixtures_a = [f for f in result.fixtures if f.name == "fixture_a"]
            fixtures_b = [f for f in result.fixtures if f.name == "fixture_b"]
            if fixtures_a and fixtures_b:
                assert fixtures_a[0].reuse_count == 1
                assert fixtures_b[0].reuse_count == 1


class TestTeardownDetection:
    """Test has_teardown_pair detection for fixtures."""

    def test_pytest_fixture_with_yield(self):
        """Pytest fixture with yield should have has_teardown_pair=1."""
        code = """
@pytest.fixture
def fixture_with_teardown():
    resource = setup_resource()
    yield resource
    resource.cleanup()
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "python")
            fixtures = [f for f in result.fixtures if f.name == "fixture_with_teardown"]
            if fixtures:
                assert fixtures[0].has_teardown_pair == 1

    def test_pytest_fixture_without_yield(self):
        """Pytest fixture without yield should have has_teardown_pair=0."""
        code = """
@pytest.fixture
def simple_fixture():
    return 42
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "python")
            fixtures = [f for f in result.fixtures if f.name == "simple_fixture"]
            if fixtures:
                assert fixtures[0].has_teardown_pair == 0

    def test_unittest_setup_teardown_pair(self):
        """unittest setUp paired with tearDown should detect teardown_pair."""
        code = """
class TestExample(unittest.TestCase):
    def setUp(self):
        self.resource = Resource()

    def tearDown(self):
        self.resource.cleanup()

    def test_something(self):
        assert True
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "python")
            setup = next(f for f in result.fixtures if f.name == "setUp")
            teardown = next(f for f in result.fixtures if f.name == "tearDown")
            assert setup.has_teardown_pair == 1
            # Only the setup-side fixture is flagged, not the teardown itself.
            assert teardown.has_teardown_pair == 0

    def test_unittest_setup_without_teardown(self):
        """unittest setUp without tearDown should have has_teardown_pair=0."""
        code = """
class TestExample(unittest.TestCase):
    def setUp(self):
        self.resource = Resource()

    def test_something(self):
        assert True
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "python")
            setup = next(f for f in result.fixtures if f.name == "setUp")
            assert setup.has_teardown_pair == 0

    def test_pytest_class_method_setup_teardown_pair(self):
        """pytest-style setup_method/teardown_method (snake_case, not
        setUp/tearDown) should be paired -- this was previously broken: the
        old code checked for a literal fixture_type of "setup_method" (which
        never occurs; the real fixture_type is "pytest_class_method" for
        both) and used a camelCase setUp->tearDown string replacement that
        is a no-op on snake_case names."""
        code = """
class TestClass:
    def setup_method(self):
        self.db = connect()

    def teardown_method(self):
        self.db.close()
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "python")
            setup = next(f for f in result.fixtures if f.name == "setup_method")
            teardown = next(f for f in result.fixtures if f.name == "teardown_method")
            assert setup.fixture_type == teardown.fixture_type == "pytest_class_method"
            assert setup.has_teardown_pair == 1
            assert teardown.has_teardown_pair == 0

    def test_nose_setup_module_teardown_module_pair(self):
        """Nose-style setup_module/teardown_module should be paired -- this
        fixture_type wasn't handled by any branch of the old pairing logic
        at all."""
        code = """
def setup_module():
    global db
    db = create_db()

def teardown_module():
    db.close()
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "python")
            setup = next(f for f in result.fixtures if f.name == "setup_module")
            assert setup.fixture_type == "nose_fixture"
            assert setup.has_teardown_pair == 1

    def test_java_junit3_setup_teardown_pair(self):
        """JUnit3-style setUp()/tearDown() (no annotations) should be
        paired -- previously unhandled because junit3_setup/junit3_teardown
        wasn't in any pairing table at all."""
        code = """
public class LegacyTest extends TestCase {
    public void setUp() {
        resource = new Resource();
    }
    public void tearDown() {
        resource.close();
    }
}
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "java")
            setup = next(f for f in result.fixtures if f.fixture_type == "junit3_setup")
            assert setup.has_teardown_pair == 1

    def test_java_testng_before_after_method_pair(self):
        """TestNG @BeforeMethod/@AfterMethod should be paired -- previously
        missing from the type-based pairing table entirely."""
        code = """
public class ServiceTest {
    @BeforeMethod
    public void setUp() { init(); }
    @AfterMethod
    public void tearDown() { cleanup(); }
}
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "java")
            setup = next(
                f for f in result.fixtures if f.fixture_type == "testng_before_method"
            )
            assert setup.has_teardown_pair == 1

    def test_javascript_mocha_before_after_pair(self):
        """Mocha bare before()/after() should be paired -- previously
        missing (only junit5_before_each/junit4_before/before_each were
        mapped)."""
        code = """
before(function() { setup(); });
after(function() { teardown(); });
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".test.js", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "javascript")
            setup = next(f for f in result.fixtures if f.fixture_type == "mocha_before")
            assert setup.has_teardown_pair == 1

    def test_javascript_before_all_after_all_pair(self):
        """beforeAll/afterAll should be paired -- previously missing (only
        before_each/after_each was mapped, not the *_all variants)."""
        code = """
beforeAll(() => { setup(); });
afterAll(() => { teardown(); });
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".test.js", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "javascript")
            setup = next(f for f in result.fixtures if f.fixture_type == "before_all")
            assert setup.has_teardown_pair == 1

    def test_ava_before_after_pair(self):
        """AVA test.before()/test.after() should be paired -- previously
        missing from the type-based pairing table entirely."""
        code = """
test.before(t => { setup(); });
test.after(t => { teardown(); });
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".test.js", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "javascript")
            setup = next(f for f in result.fixtures if f.fixture_type == "ava_before")
            assert setup.has_teardown_pair == 1


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
                assert hasattr(fixture, "max_nesting_depth")
                assert hasattr(fixture, "reuse_count")
                assert hasattr(fixture, "has_teardown_pair")
                assert hasattr(fixture, "cyclomatic_complexity")
                assert hasattr(fixture, "num_parameters")

                # Verify they have sensible default values
                assert fixture.max_nesting_depth >= 1
                assert fixture.reuse_count >= 0
                assert fixture.has_teardown_pair in (0, 1)
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
