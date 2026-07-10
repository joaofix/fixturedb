"""
Unit tests for Java fixture extraction.

Tests positive and negative detection of Java fixtures using:
- JUnit 3/4/5 annotations (@Before, @After, @BeforeClass, @AfterClass, @BeforeEach, @AfterEach)
- TestNG annotations (@BeforeMethod, @AfterMethod)
- Class initialization and static initializers
"""

import pytest

from ..conftest import (
    assert_fixture_count,
    assert_fixture_detected,
    assert_fixture_not_detected,
    extract_and_find_fixtures,
)


class TestJUnitBeforeAfter:
    """JUnit 3/4 @Before/@After annotations"""

    def test_before_annotation_detected(self):
        """@Before annotated method should be detected as fixture"""
        code = """
import org.junit.Before;

public class TestExample {
    @Before
    public void setUp() {
        data = new ArrayList();
    }
}
"""
        fixture = assert_fixture_detected(code, "java", "setUp")
        assert fixture.fixture_type == "junit4_before"
        assert fixture.scope == "per_test"

    def test_after_annotation_detected(self):
        """@After annotated method should be detected as fixture"""
        code = """
import org.junit.After;

public class TestExample {
    @After
    public void tearDown() {
        data.clear();
    }
}
"""
        fixture = assert_fixture_detected(code, "java", "tearDown")
        assert fixture.fixture_type == "junit4_after"
        assert fixture.scope == "per_test"

    def test_before_and_after_together(self):
        """Both @Before and @After should be detected"""
        code = """
public class TestExample {
    @Before
    public void setUp() {
        resource = new Resource();
    }
    
    @After
    public void tearDown() {
        resource.close();
    }
}
"""
        assert_fixture_count(code, "java", 2)
        assert_fixture_detected(code, "java", "setUp")
        assert_fixture_detected(code, "java", "tearDown")


class TestJUnit3Fallback:
    """JUnit3-style setUp()/tearDown() with no annotation at all, in a
    TestCase subclass. Regression tests for three bugs found while
    auditing this codebase's fixture-detection test rigor: the fallback's
    old guard only checked for "@Before"/"@After" *substrings* in existing
    annotations (missing any other annotation entirely), and it never
    checked class inheritance at all despite fixture_definitions.yaml's
    own comment restricting it to a TestCase subclass."""

    def test_setup_teardown_in_test_case_subclass_detected(self):
        """The genuine JUnit3 case: no annotations, extends TestCase."""
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
        assert_fixture_count(code, "java", 2)
        setup = assert_fixture_detected(code, "java", "setUp")
        teardown = assert_fixture_detected(code, "java", "tearDown")
        assert setup.fixture_type == "junit3_setup"
        assert setup.framework == "junit"
        assert setup.scope == "per_test"
        assert teardown.fixture_type == "junit3_teardown"

    def test_setup_not_extending_test_case_is_not_detected(self):
        """A plain class (no TestCase inheritance) must not trigger the
        JUnit3 fallback, even with a matching method name."""
        code = """
public class PlainClass {
    public void setUp() {
        init();
    }
}
"""
        assert_fixture_not_detected(code, "java", "setUp")

    def test_annotated_method_is_not_double_detected_via_fallback(self):
        """A method with a DIFFERENT, unrecognized annotation (not
        @Before/@After) named tearDown must not be picked up by the JUnit3
        fallback. Previously the fallback's guard only excluded
        "@Before"/"@After" substrings, so an (at the time) @Given-annotated
        method named tearDown produced two fixtures (cucumber_given AND a
        spurious junit3_teardown) for the same method. @Given is no longer a
        recognized annotation at all (Cucumber is out of scope -- see
        fixture_definitions.yaml's java.excluded), so the correct outcome
        now is zero fixtures for this method, not a double-count."""
        code = """
public class Steps extends TestCase {
    @Given("a precondition")
    public void tearDown() {
        cleanup();
    }
}
"""
        assert_fixture_count(code, "java", 0)

    def test_test_annotated_method_named_setup_is_not_misclassified(self):
        """A @Test-annotated method that happens to be named setUp is a
        real test method, not a fixture -- it must not be reported as
        junit3_setup. Previously it was: @Test contains neither
        "@Before" nor "@After", so the old guard let it through."""
        code = """
public class MyTest extends TestCase {
    @Test
    public void setUp() {
        assertTrue(true);
    }
}
"""
        assert_fixture_not_detected(code, "java", "setUp")


class TestJUnitClassLevel:
    """JUnit 3/4 @BeforeClass/@AfterClass annotations"""

    def test_beforeclass_annotation(self):
        """@BeforeClass should be detected as class-level fixture"""
        code = """
public class TestExample {
    @BeforeClass
    public static void setUpClass() {
        db = Database.connect();
    }
}
"""
        fixture = assert_fixture_detected(code, "java", "setUpClass")
        assert fixture.fixture_type == "testng_before_class"
        assert fixture.scope == "per_class"

    def test_afterclass_annotation(self):
        """@AfterClass should be detected as class-level fixture"""
        code = """
public class TestExample {
    @AfterClass
    public static void tearDownClass() {
        db.disconnect();
    }
}
"""
        fixture = assert_fixture_detected(code, "java", "tearDownClass")
        assert fixture.fixture_type == "testng_after_class"
        assert fixture.framework == "testng"
        assert fixture.scope == "per_class"


class TestJUnit5LifecycleMethods:
    """JUnit 5 @BeforeEach/@AfterEach annotations"""

    def test_beforeeach_annotation(self):
        """JUnit 5 @BeforeEach should be detected"""
        code = """
import org.junit.jupiter.api.BeforeEach;

public class TestExample {
    @BeforeEach
    void setUp() {
        service = new UserService();
    }
}
"""
        fixture = assert_fixture_detected(code, "java", "setUp")
        assert fixture.fixture_type == "junit5_before_each"
        assert fixture.framework == "junit"
        assert fixture.scope == "per_test"

    def test_beforeall_annotation(self):
        """JUnit 5 @BeforeAll should be detected"""
        code = """
import org.junit.jupiter.api.BeforeAll;

public class TestExample {
    @BeforeAll
    static void setUpAll() {
        server = startServer();
    }
}
"""
        fixture = assert_fixture_detected(code, "java", "setUpAll")
        assert fixture.fixture_type == "junit5_before_all"
        assert fixture.framework == "junit"
        assert fixture.scope == "per_class"


class TestTestNGFixtures:
    """TestNG @BeforeMethod/@AfterMethod annotations"""

    def test_beforemethod_annotation(self):
        """TestNG @BeforeMethod should be detected"""
        code = """
import org.testng.annotations.BeforeMethod;

public class TestExample {
    @BeforeMethod
    public void setUp() {
        driver = new WebDriver();
    }
}
"""
        fixture = assert_fixture_detected(code, "java", "setUp")
        assert fixture.fixture_type == "testng_before_method"
        assert fixture.framework == "testng"
        assert fixture.scope == "per_test"

    def test_aftermethod_annotation(self):
        """TestNG @AfterMethod should be detected"""
        code = """
import org.testng.annotations.AfterMethod;

public class TestExample {
    @AfterMethod
    public void tearDown() {
        driver.quit();
    }
}
"""
        fixture = assert_fixture_detected(code, "java", "tearDown")
        assert fixture.fixture_type == "testng_after_method"
        assert fixture.framework == "testng"
        assert fixture.scope == "per_test"

    def test_dataprovider_annotation(self):
        """TestNG @DataProvider should be detected as data-driven fixture"""
        code = """
import org.testng.annotations.DataProvider;

public class DataTests {
    @DataProvider(name = "testData")
    public Object[][] provideTestData() {
        return new Object[][] {
            {"user1", "pass1"},
            {"user2", "pass2"}
        };
    }
}
"""
        fixture = assert_fixture_detected(code, "java", "provideTestData")
        assert fixture.fixture_type == "testng_data_provider"
        assert fixture.scope == "per_test"

    def test_dataprovider_with_params(self):
        """DataProvider with method parameters"""
        code = """
@DataProvider
public Object[][] provide() {
    return new Object[][] { {1}, {2}, {3} };
}
"""
        fixture = assert_fixture_detected(code, "java", "provide")
        assert fixture.fixture_type == "testng_data_provider"


class TestJavaNegativeDetection:
    """Ensure non-fixtures in Java are not detected"""

    def test_regular_method_not_detected(self):
        """A plain setUp() in a class that does NOT extend TestCase must
        not be detected as a JUnit3 fixture -- the YAML's own
        junit3_fallback comment restricts this to "a (JUnit3-style)
        TestCase subclass", but the code did not actually check
        inheritance until this test was tightened (previously asserted
        only `isinstance(fixtures, list)`, a tautology that passed
        regardless of whether the bug was present)."""
        code = """
public class Test {
    public void setUp() {
        x = 1;
    }
}
"""
        assert_fixture_not_detected(code, "java", "setUp")

    def test_helper_method_not_detected(self):
        """Helper methods should not be detected as fixtures"""
        code = """
public class Test {
    private void helperSetup() {
        initialize();
    }
}
"""
        fixtures = extract_and_find_fixtures(code, "java")
        assert not any(f.name == "helperSetup" for f in fixtures)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
