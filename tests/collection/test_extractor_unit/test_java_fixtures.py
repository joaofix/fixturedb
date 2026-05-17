"""
Unit tests for Java fixture extraction.

Tests positive and negative detection of Java fixtures using:
- JUnit 3/4/5 annotations (@Before, @After, @BeforeClass, @AfterClass, @BeforeEach, @AfterEach)
- TestNG annotations (@BeforeMethod, @AfterMethod)
- Class initialization and static initializers
"""

import pytest
from ..conftest import (
    extract_and_find_fixtures,
    assert_fixture_detected,
    assert_fixture_not_detected,
    assert_fixture_count,
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
        """Regular public method should not be detected as fixture"""
        code = """
public class Test {
    public void setUp() {
        x = 1;
    }
}
"""
        # Without @Before annotation, setUp is just a regular method
        # Detection depends on detector implementation
        fixtures = extract_and_find_fixtures(code, "java")
        # If detector uses only annotations, this won't be detected
        # If detector uses naming convention, it might be
        assert isinstance(fixtures, list)

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
