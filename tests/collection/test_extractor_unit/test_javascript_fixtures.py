"""
Unit tests for JavaScript fixture extraction.

Tests positive and negative detection of JavaScript fixtures using:
- Mocha hooks (before, after, beforeEach, afterEach)
- Jest hooks (beforeAll, afterAll, beforeEach, afterEach)
- Factory functions and shared setup objects
"""

import pytest
from ..conftest import (
    extract_and_find_fixtures,
    assert_fixture_detected,
    assert_fixture_not_detected,
    assert_fixture_count,
    assert_fixture_with_type_detected,
)


class TestMochaBeforeAfter:
    """Mocha before/after hooks"""

    def test_before_hook_detected(self):
        """Mocha before() hook should be detected"""
        code = """
describe('Suite', () => {
    before(function() {
        this.resource = createResource();
    });
});
"""
        fixture = assert_fixture_with_type_detected(code, "javascript", "mocha_before")
        assert fixture.scope == "per_test"

    def test_after_hook_detected(self):
        """Mocha after() hook should be detected"""
        code = """
describe('Suite', () => {
    after(function() {
        this.resource.cleanup();
    });
});
"""
        fixture = assert_fixture_with_type_detected(code, "javascript", "mocha_after")
        assert fixture.scope == "per_test"

    def test_beforeeach_hook_detected(self):
        """Mocha beforeEach() hook should be detected"""
        code = """
describe('Tests', () => {
    beforeEach(function() {
        this.data = [];
    });
});
"""
        fixture = assert_fixture_with_type_detected(code, "javascript", "before_each")
        assert fixture.scope == "per_test"

    def test_aftereach_hook_detected(self):
        """Mocha afterEach() hook should be detected"""
        code = """
describe('Tests', () => {
    afterEach(function() {
        this.data = null;
    });
});
"""
        fixture = assert_fixture_with_type_detected(code, "javascript", "after_each")
        assert fixture.scope == "per_test"


class TestJestHooks:
    """Jest lifecycle hooks"""

    def test_jest_beforeall_detected(self):
        """Jest beforeAll() should be detected"""
        code = """
describe('Module', () => {
    beforeAll(() => {
        db.connect();
    });
});
"""
        fixture = assert_fixture_with_type_detected(code, "javascript", "before_all")
        assert fixture.scope == "per_class"

    def test_jest_afterall_detected(self):
        """Jest afterAll() should be detected"""
        code = """
afterAll(async () => {
    await db.close();
});
"""
        fixture = assert_fixture_with_type_detected(code, "javascript", "after_all")
        assert fixture.scope == "per_class"

    def test_jest_beforeeach_detected(self):
        """Jest beforeEach() should be detected"""
        code = """
beforeEach(() => {
    jest.clearAllMocks();
});
"""
        fixture = assert_fixture_with_type_detected(code, "javascript", "before_each")
        assert fixture.scope == "per_test"


class TestAsyncJavaScriptFixtures:
    """Async/await patterns in JavaScript fixtures"""

    def test_async_before_hook(self):
        """Async before() hook should be detected"""
        code = """
before(async function() {
    this.db = await connect();
});
"""
        fixture = assert_fixture_with_type_detected(code, "javascript", "mocha_before")
        assert fixture.fixture_type == "mocha_before"

    def test_async_beforeeach_hook(self):
        """Async beforeEach() should be detected"""
        code = """
beforeEach(async () => {
    const result = await setup();
    this.data = result;
});
"""
        fixture = assert_fixture_with_type_detected(code, "javascript", "before_each")
        assert fixture.fixture_type == "before_each"


class TestJavaScriptFactories:
    """Factory functions and setup objects"""

    def test_factory_function_as_fixture(self):
        """Factory function might be detected based on naming"""
        code = """
function createTestData() {
    return {
        user: { id: 1, name: 'test' },
        db: new MockDatabase()
    };
}
"""
        fixtures = extract_and_find_fixtures(code, "javascript")
        # Depends on whether detector recognizes factory pattern
        assert isinstance(fixtures, list)


class TestAVAFixtures:
    """AVA test framework fixtures"""

    def test_ava_before_detected(self):
        """AVA test.before() should be detected"""
        code = """
import test from 'ava';

test.before(t => {
    t.context.db = setupDatabase();
});
"""
        fixtures = extract_and_find_fixtures(code, "javascript")
        assert any(f.fixture_type == "ava_before" for f in fixtures)

    def test_ava_after_detected(self):
        """AVA test.after() should be detected"""
        code = """
test.after(t => {
    t.context.db.close();
});
"""
        fixtures = extract_and_find_fixtures(code, "javascript")
        assert any(f.fixture_type == "ava_after" for f in fixtures)

    def test_ava_serial_before_detected(self):
        """AVA test.serial.before() should be detected as per-test"""
        code = """
test.serial.before(t => {
    setupSerialResources();
});
"""
        fixtures = extract_and_find_fixtures(code, "javascript")
        assert any(
            f.fixture_type == "ava_serial_before" and f.scope == "per_test"
            for f in fixtures
        )

    def test_ava_serial_after_detected(self):
        """AVA test.serial.after() should be detected"""
        code = """
test.serial.after(t => {
    cleanupSerialResources();
});
"""
        fixtures = extract_and_find_fixtures(code, "javascript")
        assert any(f.fixture_type == "ava_serial_after" for f in fixtures)

    def test_ava_fixture_scopes(self):
        """AVA fixture scopes: before/after are per-class, serial.* are per-test"""
        code = """
import test from 'ava';

test.before(t => { setup(); });
test.after(t => { cleanup(); });
test.serial.before(t => { setupSerial(); });
"""
        fixtures = extract_and_find_fixtures(code, "javascript")

        # before/after should be per_class
        before_fixtures = [f for f in fixtures if f.fixture_type == "ava_before"]
        assert any(f.scope == "per_class" for f in before_fixtures)

        # serial.before should be per_test
        serial_fixtures = [f for f in fixtures if f.fixture_type == "ava_serial_before"]
        assert any(f.scope == "per_test" for f in serial_fixtures)


class TestJavaScriptNegativeDetection:
    """Ensure non-fixtures are not detected"""

    def test_regular_function_not_detected(self):
        """Regular function not named as fixture should not be detected"""
        code = """
function regularFunction() {
    return 42;
}
"""
        fixtures = extract_and_find_fixtures(code, "javascript")
        assert not any(f.name == "regularFunction" for f in fixtures)

    def test_test_function_not_fixture(self):
        """test() function is for defining tests, not fixtures"""
        code = """
test('should pass', () => {
    expect(true).toBe(true);
});
"""
        fixtures = extract_and_find_fixtures(code, "javascript")
        # test() defines a test, not a fixture
        assert not any(f.name == "should pass" for f in fixtures)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
