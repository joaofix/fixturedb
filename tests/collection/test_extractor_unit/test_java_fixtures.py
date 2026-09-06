"""
Unit tests for Java fixture extraction.

Tests positive and negative detection of Java fixtures using:
- JUnit 3/4/5 annotations (@Before, @After, @BeforeClass, @AfterClass, @BeforeEach, @AfterEach)
- TestNG annotations (@BeforeMethod, @AfterMethod, @BeforeSuite/@AfterSuite,
  @BeforeTest/@AfterTest, @BeforeGroups/@AfterGroups, @DataProvider, @Factory)
- Class initialization and static initializers

@BeforeClass/@AfterClass collide with JUnit4's own annotations of the same
name -- TestClassLevelFrameworkResolution below covers all three possible
per-file import-based resolutions (junit-only/testng-only/ambiguous), and
confirms fixture_type_kind (setup/teardown) is correct in every case
regardless of whether the specific framework could be resolved -- see
detector_java.py's JUNIT_TESTNG_AMBIGUOUS and fixture_definitions.yaml's
java.known_imprecisions.
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


class TestClassLevelFrameworkResolution:
    """@BeforeClass/@AfterClass collide with JUnit4's own annotations of
    the same name -- resolved per-file via the file's own imports
    (detector_java.py's _detect_test_framework_imports()), not a fixed
    default. fixture_type_kind (setup/teardown) must be correct in EVERY
    case below regardless of whether the specific framework could be
    resolved -- that's the actual paper-relevant guarantee; the
    framework-specific fixture_type/framework fields are best-effort only."""

    def test_beforeclass_with_only_junit_import_resolves_to_junit4(self):
        code = """
import org.junit.BeforeClass;

public class TestExample {
    @BeforeClass
    public static void setUpClass() {
        db = Database.connect();
    }
}
"""
        fixture = assert_fixture_detected(code, "java", "setUpClass")
        assert fixture.fixture_type == "junit4_before_class"
        assert fixture.framework == "junit"
        assert fixture.scope == "per_class"
        assert fixture.fixture_type_kind == "setup"

    def test_beforeclass_with_only_testng_import_resolves_to_testng(self):
        code = """
import org.testng.annotations.BeforeClass;

public class TestExample {
    @BeforeClass
    public static void setUpClass() {
        db = Database.connect();
    }
}
"""
        fixture = assert_fixture_detected(code, "java", "setUpClass")
        assert fixture.fixture_type == "testng_before_class"
        assert fixture.framework == "testng"
        assert fixture.scope == "per_class"
        assert fixture.fixture_type_kind == "setup"

    def test_beforeclass_with_both_imports_is_ambiguous_but_still_setup(self):
        """A file mixing both frameworks' imports can't be disambiguated --
        framework is left unresolved (None), NOT guessed -- but
        fixture_type_kind must still be correctly 'setup', unaffected by
        the framework ambiguity."""
        code = """
import org.junit.BeforeClass;
import org.testng.annotations.DataProvider;

public class TestExample {
    @BeforeClass
    public static void setUpClass() {
        db = Database.connect();
    }
}
"""
        fixture = assert_fixture_detected(code, "java", "setUpClass")
        assert fixture.fixture_type == "before_class_ambiguous"
        assert fixture.framework is None
        assert fixture.scope == "per_class"
        assert fixture.fixture_type_kind == "setup"

    def test_beforeclass_with_no_imports_is_ambiguous_but_still_setup(self):
        """No imports at all (e.g. same-package classes, wildcard imports
        elided from this snippet) is the other ambiguous case -- same
        unresolved-framework outcome as both-imports, still correctly
        classified as setup."""
        code = """
public class TestExample {
    @BeforeClass
    public static void setUpClass() {
        db = Database.connect();
    }
}
"""
        fixture = assert_fixture_detected(code, "java", "setUpClass")
        assert fixture.fixture_type == "before_class_ambiguous"
        assert fixture.framework is None
        assert fixture.fixture_type_kind == "setup"

    def test_afterclass_with_only_junit_import_resolves_to_junit4(self):
        code = """
import org.junit.AfterClass;

public class TestExample {
    @AfterClass
    public static void tearDownClass() {
        db.disconnect();
    }
}
"""
        fixture = assert_fixture_detected(code, "java", "tearDownClass")
        assert fixture.fixture_type == "junit4_after_class"
        assert fixture.framework == "junit"
        assert fixture.scope == "per_class"
        assert fixture.fixture_type_kind == "teardown"

    def test_afterclass_with_only_testng_import_resolves_to_testng(self):
        code = """
import org.testng.annotations.AfterClass;

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
        assert fixture.fixture_type_kind == "teardown"

    def test_afterclass_with_both_imports_is_ambiguous_but_still_teardown(self):
        code = """
import org.junit.AfterClass;
import org.testng.annotations.DataProvider;

public class TestExample {
    @AfterClass
    public static void tearDownClass() {
        db.disconnect();
    }
}
"""
        fixture = assert_fixture_detected(code, "java", "tearDownClass")
        assert fixture.fixture_type == "after_class_ambiguous"
        assert fixture.framework is None
        assert fixture.fixture_type_kind == "teardown"

    def test_afterclass_with_no_imports_is_ambiguous_but_still_teardown(self):
        code = """
public class TestExample {
    @AfterClass
    public static void tearDownClass() {
        db.disconnect();
    }
}
"""
        fixture = assert_fixture_detected(code, "java", "tearDownClass")
        assert fixture.fixture_type == "after_class_ambiguous"
        assert fixture.framework is None
        assert fixture.fixture_type_kind == "teardown"


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
        assert fixture.fixture_type_kind == "other"

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

    @pytest.mark.parametrize(
        "signature",
        [
            "()",
            "(ITestResult result)",
            "(Method method)",
            "(Object[] params)",
            "(Method method, Object[] params, ITestResult testResult)",
        ],
        ids=["no_arg", "itestresult", "method", "object_array", "all_three"],
    )
    def test_beforemethod_detected_regardless_of_parameter_signature(self, signature):
        """@BeforeMethod/@AfterMethod detection must not be signature-
        sensitive -- TestNG allows injecting ITestResult/Method/Object[]
        (the test's own parameters) into lifecycle methods, unlike JUnit's
        always-no-arg equivalents. Detection reads only the annotation, on
        any method_declaration, never inspecting formal_parameters at all
        -- this locks that in as a regression guard."""
        code = f"""
import org.testng.annotations.BeforeMethod;

public class TestExample {{
    @BeforeMethod
    public void setUp{signature} {{
        driver = new WebDriver();
    }}
}}
"""
        fixture = assert_fixture_detected(code, "java", "setUp")
        assert fixture.fixture_type == "testng_before_method"
        assert fixture.fixture_type_kind == "setup"

    @pytest.mark.parametrize(
        "signature",
        [
            "()",
            "(ITestResult result)",
            "(Method method)",
            "(Object[] params)",
            "(Method method, Object[] params, ITestResult testResult)",
        ],
        ids=["no_arg", "itestresult", "method", "object_array", "all_three"],
    )
    def test_aftermethod_detected_regardless_of_parameter_signature(self, signature):
        code = f"""
import org.testng.annotations.AfterMethod;

public class TestExample {{
    @AfterMethod
    public void tearDown{signature} {{
        driver.quit();
    }}
}}
"""
        fixture = assert_fixture_detected(code, "java", "tearDown")
        assert fixture.fixture_type == "testng_after_method"
        assert fixture.fixture_type_kind == "teardown"


class TestTestNGSuiteAndGroupLifecycle:
    """@BeforeSuite/@AfterSuite, @BeforeTest/@AfterTest, @BeforeGroups/
    @AfterGroups -- TestNG-only names (no JUnit collision), confirmed
    negligible in real-world prevalence (~0% Dataset A, ~5% Dataset C
    sample) but added for completeness since they're real, correctly-
    classifiable fixtures when present."""

    @pytest.mark.parametrize(
        "annotation,fixture_type",
        [
            ("@BeforeSuite", "testng_before_suite"),
            ("@BeforeTest", "testng_before_test"),
            ("@BeforeGroups", "testng_before_groups"),
        ],
    )
    def test_before_level_annotations_detected_as_setup(self, annotation, fixture_type):
        code = f"""
public class TestExample {{
    {annotation}
    public void setUp() {{
        globalResource = acquire();
    }}
}}
"""
        fixture = assert_fixture_detected(code, "java", "setUp")
        assert fixture.fixture_type == fixture_type
        assert fixture.framework == "testng"
        assert fixture.scope == "global"
        assert fixture.fixture_type_kind == "setup"

    @pytest.mark.parametrize(
        "annotation,fixture_type",
        [
            ("@AfterSuite", "testng_after_suite"),
            ("@AfterTest", "testng_after_test"),
            ("@AfterGroups", "testng_after_groups"),
        ],
    )
    def test_after_level_annotations_detected_as_teardown(self, annotation, fixture_type):
        code = f"""
public class TestExample {{
    {annotation}
    public void tearDown() {{
        globalResource.release();
    }}
}}
"""
        fixture = assert_fixture_detected(code, "java", "tearDown")
        assert fixture.fixture_type == fixture_type
        assert fixture.framework == "testng"
        assert fixture.scope == "global"
        assert fixture.fixture_type_kind == "teardown"


class TestTestNGFactory:
    """@Factory supplies test-class instances (data-driven class
    instantiation) -- same role as @DataProvider, so it's classified the
    same way: detected, but fixture_type_kind='other' (neither setup nor
    teardown), matching @DataProvider's existing treatment. No JUnit
    collision risk for this name, so no import-based resolution needed."""

    def test_factory_annotation_detected_as_other(self):
        code = """
import org.testng.annotations.Factory;

public class FactoryTests {
    @Factory
    public Object[] createInstances() {
        return new Object[] { new LoginTest("admin"), new LoginTest("guest") };
    }
}
"""
        fixture = assert_fixture_detected(code, "java", "createInstances")
        assert fixture.fixture_type == "testng_factory"
        assert fixture.framework == "testng"
        assert fixture.fixture_type_kind == "other"


class TestTestNGListenersOutOfScope:
    """@Listeners registers a class-level listener -- not a setup/teardown
    or data-supplying method, and structurally never reachable even if it
    were: it annotates the class_declaration itself, which detector_java.py
    never inspects for annotations (only method_declaration/
    field_declaration are). Sanity check only, no fix expected."""

    def test_listeners_annotation_alone_produces_no_fixtures(self):
        code = """
import org.testng.annotations.Listeners;

@Listeners(MyTestListener.class)
public class TestExample {
    public void helperMethod() {
        doSomething();
    }
}
"""
        assert_fixture_count(code, "java", 0)

    def test_listeners_alongside_a_real_fixture_is_not_itself_detected(self):
        """@Listeners on the class must not produce a spurious second
        fixture when the class also has a real one."""
        code = """
import org.testng.annotations.BeforeMethod;
import org.testng.annotations.Listeners;

@Listeners(MyTestListener.class)
public class TestExample {
    @BeforeMethod
    public void setUp() {
        driver = new WebDriver();
    }
}
"""
        assert_fixture_count(code, "java", 1)


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
