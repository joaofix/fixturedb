"""
Tests for new metrics: max_nesting_depth, has_teardown_pair, num_contributors.
"""

from pathlib import Path

from collection.detector import extract_fixtures


class TestMaxNestingDepth:
    """Test max_nesting_depth extraction.

    Assertions are exact, not loose lower bounds (`>= 1`, `>= 2`) -- loose
    bounds previously let a real double-counting bug (each level of nesting
    was counted twice, because a compound statement's own body wrapper node
    -- "block" in Python/Java's tree-sitter grammars -- was counted as an
    *additional* nesting level on top of the statement itself) go completely
    undetected: reported values were 2x-plus the true depth, but `>= 1`/`>= 2`
    still passed. See collection/detector_shared.py::_compute_nesting_depth.
    """

    def test_simple_fixture_no_nesting(self):
        """Fixture with no nesting should have max_nesting_depth=1."""
        code = """
@pytest.fixture
def fixture_simple():
    x = 1
    y = 2
    return x + y
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "python")
            fixture = next(f for f in result.fixtures if f.name == "fixture_simple")
            assert fixture.max_nesting_depth == 1

    def test_nested_if_statements(self):
        """Three levels of nested `if` should report max_nesting_depth=4
        (function body=1, plus one level per nested if)."""
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
            fixture = next(f for f in result.fixtures if f.name == "fixture_with_nesting")
            assert fixture.max_nesting_depth == 4

    def test_nested_loops(self):
        """Three levels of nested `for` should report max_nesting_depth=4."""
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
            fixture = next(f for f in result.fixtures if f.name == "fixture_with_loops")
            assert fixture.max_nesting_depth == 4

    def test_one_level_if_java(self):
        """Java: one level of `if` nesting inside a fixture method should
        report max_nesting_depth=2 (method body=1, if=2), not 4."""
        code = """
public class ServiceTest {
    @Before
    public void setUp() {
        if (true) {
            int x = 1;
        }
    }
}
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "java")
            fixture = next(f for f in result.fixtures if f.name == "setUp")
            assert fixture.max_nesting_depth == 2

    def test_try_catch_java(self):
        """Java: a try/catch is one nesting level total -- the catch clause
        is an alternate branch of the same try, not an additional level
        nested inside it."""
        code = """
public class ServiceTest {
    @Before
    public void setUp() {
        try {
            int x = 1;
        } catch (Exception e) {
            int y = 2;
        }
    }
}
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "java")
            fixture = next(f for f in result.fixtures if f.name == "setUp")
            assert fixture.max_nesting_depth == 2

    def test_enhanced_for_each_java(self):
        """Regression: Java's for-each loop ("enhanced_for_statement" in
        tree-sitter-java) was missing from the nesting-depth block-type set,
        so it was silently invisible to the metric -- an `if` nested inside
        a for-each reported depth 2 instead of 3."""
        code = """
public class ServiceTest {
    @Before
    public void setUp() {
        for (String item : items) {
            if (item != null) {
                process(item);
            }
        }
    }
}
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "java")
            fixture = next(f for f in result.fixtures if f.name == "setUp")
            assert fixture.max_nesting_depth == 3

    def test_one_level_if_javascript(self):
        """JavaScript was never affected by the double-counting bug (its
        block-body node is named "statement_block", not "block"), but is
        covered here as a same-input cross-language guard."""
        code = """
beforeEach(function() {
    if (true) {
        x = 1;
    }
});
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".test.js", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "javascript")
            assert result.fixtures[0].max_nesting_depth == 2


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

    def test_unittest_setup_with_addCleanup_has_teardown_pair(self):
        """Regression: setUp() registering cleanup inline via
        self.addCleanup(...) -- the modern, docs-recommended pattern -- and
        defining no separate tearDown() at all was previously reported as
        has_teardown_pair=0, despite genuinely having teardown logic."""
        code = """
class TestExample(unittest.TestCase):
    def setUp(self):
        self.resource = Resource()
        self.addCleanup(self.resource.cleanup)

    def test_something(self):
        assert True
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "python")
            setup = next(f for f in result.fixtures if f.name == "setUp")
            assert setup.has_teardown_pair == 1

    def test_unittest_setupclass_with_enterClassContext_has_teardown_pair(self):
        """Same as addCleanup, but for the class-level equivalent:
        setUpClass() using cls.enterClassContext(...) with no separate
        tearDownClass()."""
        code = """
class TestExample(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = cls.enterClassContext(make_server())

    def test_something(self):
        assert True
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "python")
            setup = next(f for f in result.fixtures if f.name == "setUpClass")
            assert setup.has_teardown_pair == 1

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

    def test_java_junit5_before_each_after_each_pair(self):
        """JUnit5 @BeforeEach/@AfterEach should be paired -- this is the
        single most common Java lifecycle pattern in the corpus, but had no
        dedicated pairing test (only TestNG's @BeforeMethod/@AfterMethod,
        which shares the same type_based_pairs mechanism, was covered)."""
        code = """
public class ServiceTest {
    @BeforeEach
    void setUp() { init(); }
    @AfterEach
    void tearDown() { cleanup(); }
}
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "java")
            setup = next(
                f for f in result.fixtures if f.fixture_type == "junit5_before_each"
            )
            assert setup.has_teardown_pair == 1

    def test_javascript_before_each_after_each_pair(self):
        """beforeEach/afterEach should be paired -- this is the single
        largest fixture_type in the whole corpus, but had no dedicated
        pairing test (only the *_all variants and Mocha's bare before/after
        were covered)."""
        code = """
beforeEach(() => { setup(); });
afterEach(() => { teardown(); });
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".test.js", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "javascript")
            setup = next(f for f in result.fixtures if f.fixture_type == "before_each")
            assert setup.has_teardown_pair == 1

    def test_javascript_independent_describe_blocks_do_not_cross_pair(self):
        """Two independent describe() blocks in one file must not have
        their hooks cross-paired just because they share fixture_type +
        scope -- container_id (the enclosing describe() block) must also
        match. Without this, UserService's beforeEach falsely read
        has_teardown_pair=1 purely because an unrelated afterEach existed
        in OrderService's block."""
        code = """
describe('UserService', () => {
    beforeEach(() => { setupUser(); });
});
describe('OrderService', () => {
    afterEach(() => { cleanupOrder(); });
});
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".test.js", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "javascript")
            setup = next(f for f in result.fixtures if f.fixture_type == "before_each")
            assert setup.has_teardown_pair == 0

    def test_javascript_same_describe_block_still_pairs(self):
        """A beforeEach/afterEach pair inside the same describe() block
        must still pair -- guards against the container_id check being
        overly strict."""
        code = """
describe('UserService', () => {
    beforeEach(() => { setupUser(); });
    afterEach(() => { cleanupUser(); });
});
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".test.js", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "javascript")
            setup = next(f for f in result.fixtures if f.fixture_type == "before_each")
            assert setup.has_teardown_pair == 1

    def test_java_nested_class_does_not_inherit_outer_teardown(self):
        """A @Nested inner class's own @BeforeEach must not be falsely
        paired with the OUTER class's @AfterEach just because they share
        fixture_type + scope -- container_id (the enclosing
        class_declaration) must also match. Reproduces the exact shape
        already present in
        test_java_realistic_fixtures.py::test_junit5_complex_hierarchy."""
        code = """
public class UserServiceTest {
    @BeforeEach
    public void setUp() { outerInit(); }
    @AfterEach
    public void tearDown() { outerCleanup(); }

    @Nested
    class UserCreationTests {
        @BeforeEach
        void setUp() { innerInit(); }
    }
}
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "java")
            before_eaches = sorted(
                (f for f in result.fixtures if f.fixture_type == "junit5_before_each"),
                key=lambda f: f.start_line,
            )
            assert len(before_eaches) == 2
            outer_setup, inner_setup = before_eaches
            assert outer_setup.has_teardown_pair == 1
            assert inner_setup.has_teardown_pair == 0

    def test_java_independent_top_level_classes_do_not_cross_pair(self):
        """Two independent top-level classes in one file must not have
        their hooks cross-paired just because they share fixture_type +
        scope."""
        code = """
class UserServiceTest {
    @BeforeEach
    void setUp() { init(); }
}

class OrderServiceTest {
    @AfterEach
    void tearDown() { cleanup(); }
}
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "java")
            setup = next(
                f for f in result.fixtures if f.fixture_type == "junit5_before_each"
            )
            assert setup.has_teardown_pair == 0

    def test_java_nested_class_with_own_complete_pair_still_pairs(self):
        """A @Nested class with its own complete @BeforeEach/@AfterEach
        pair must still pair, independent of the outer class's own hooks
        (and the outer class, which has no @AfterEach of its own, must not
        be falsely paired with the nested class's @AfterEach either)."""
        code = """
public class UserServiceTest {
    @BeforeEach
    public void setUp() { outerInit(); }

    @Nested
    class UserCreationTests {
        @BeforeEach
        void setUp() { innerInit(); }
        @AfterEach
        void tearDown() { innerCleanup(); }
    }
}
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "java")
            before_eaches = sorted(
                (f for f in result.fixtures if f.fixture_type == "junit5_before_each"),
                key=lambda f: f.start_line,
            )
            assert len(before_eaches) == 2
            outer_setup, inner_setup = before_eaches
            assert outer_setup.has_teardown_pair == 0
            assert inner_setup.has_teardown_pair == 1

    def test_java_junit_rule_always_has_teardown_pair(self):
        """@Rule fields wrap a TestRule whose apply() logic (including any
        teardown) lives outside the test file entirely -- source inspection
        can't confirm or deny teardown, so junit_rule is treated as always
        having it, regardless of raw_source content."""
        code = """
import org.junit.Rule;

public class TemporaryFolderTest {
    @Rule
    public TemporaryFolder temporaryFolder = new TemporaryFolder();
}
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "java")
            rule = next(f for f in result.fixtures if f.fixture_type == "junit_rule")
            assert rule.has_teardown_pair == 1

    def test_java_junit_class_rule_always_has_teardown_pair(self):
        """Same as junit_rule, for the class-scoped @ClassRule variant."""
        code = """
import org.junit.ClassRule;

public class DatabaseTest {
    @ClassRule
    public static ExternalResource database = new ExternalResource();
}
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "java")
            rule = next(
                f for f in result.fixtures if f.fixture_type == "junit_class_rule"
            )
            assert rule.has_teardown_pair == 1

    def test_vitest_around_each_always_has_teardown_pair(self):
        """aroundEach wraps setup+teardown around a runTest() callback whose
        parameter is developer-named (not a fixed marker like pytest's
        "yield"), so it's treated as always having teardown by definition
        of the hook -- even when the callback is passed onward rather than
        invoked directly, as here."""
        code = """
import { aroundEach, test } from 'vitest'

aroundEach(async (runTest) => {
    await db.transaction(runTest)
})
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".test.js", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "javascript")
            hook = next(
                f for f in result.fixtures if f.fixture_type == "vitest_around_each"
            )
            assert hook.has_teardown_pair == 1

    def test_vitest_around_all_always_has_teardown_pair(self):
        """Same as vitest_around_each, for the suite-scoped aroundAll variant."""
        code = """
import { aroundAll, test } from 'vitest'

aroundAll(async (runSuite) => {
    await tracer.trace('test-suite', runSuite)
})
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".test.js", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "javascript")
            hook = next(
                f for f in result.fixtures if f.fixture_type == "vitest_around_all"
            )
            assert hook.has_teardown_pair == 1


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
                assert hasattr(fixture, "has_teardown_pair")
                assert hasattr(fixture, "cyclomatic_complexity")
                assert hasattr(fixture, "num_parameters")

                # Verify they have sensible default values
                assert fixture.max_nesting_depth >= 1
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
    fixture's body -- start_line/end_line, num_external_calls, and mocks
    must all be scoped to the function only, consistent with raw_source
    (which was already function-only). Previously the decorated_definition
    node (decorator included) was used for line range/external-calls/mocks
    while the bare function_definition was used for raw_source/complexity,
    so the reported line range disagreed with raw_source by exactly the
    decorator line, and any I/O call or mock construct sitting in the
    decorator's own arguments leaked into that fixture's metrics. See
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

    def test_external_call_in_decorator_args_not_counted(self):
        code = """
@pytest.fixture(params=[open("leak.txt")])
def my_fixture():
    return 1
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "python")
            fixture = next(f for f in result.fixtures if f.name == "my_fixture")
            assert fixture.num_external_calls == 0

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


class TestDottedConstructorInstantiation:
    """new Namespace.ClassName(...) -- a common JS/TS idiom (e.g.
    new THREE.Vector3()) and valid Java (new java.util.ArrayList()) -- must
    be counted, not just a single bare identifier before the constructor
    call. See detector_shared.py's OBJECT_CREATION_NODE_TYPES /
    _count_object_instantiations() -- a dotted type is still a single
    object_creation_expression/new_expression node, so this is really
    testing that the node-type walk isn't accidentally scoped to bare
    identifiers only."""

    def test_javascript_dotted_constructor_counted(self):
        code = """
beforeEach(function() {
    x = new THREE.Vector3();
});
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".test.js", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "javascript")
            assert result.fixtures[0].num_objects_instantiated == 1

    def test_java_dotted_constructor_counted(self):
        code = """
public class ServiceTest {
    @Before
    public void setUp() {
        java.util.List x = new java.util.ArrayList();
    }
}
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(code)
            f.flush()
            result = extract_fixtures(Path(f.name), "java")
            setup = next(f for f in result.fixtures if f.name == "setUp")
            assert setup.num_objects_instantiated == 1


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
