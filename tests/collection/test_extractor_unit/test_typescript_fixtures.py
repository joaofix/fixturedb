"""
Unit tests for TypeScript fixture extraction.

Tests positive and negative detection of TypeScript fixtures using:
- Jest hooks with type annotations
- Mocha hooks in TypeScript
- Async fixture patterns
- Type-aware fixture detection
"""

import pytest

from ..conftest import (
    assert_fixture_count,
    assert_fixture_with_type_detected,
    extract_and_find_fixtures,
)


class TestTypeScriptJestHooks:
    """Jest fixtures with TypeScript type annotations"""

    def test_jest_beforeall_with_types(self):
        """Jest beforeAll() with TypeScript types"""
        code = """
import { describe, beforeAll } from '@jest/globals';

describe('Module', () => {
    let db: Database;
    
    beforeAll(async (): Promise<void> => {
        db = new Database();
        await db.connect();
    });
});
"""
        fixture = assert_fixture_with_type_detected(code, "typescript", "before_all")
        assert fixture.fixture_type == "before_all"

    def test_jest_beforeeach_with_types(self):
        """Jest beforeEach() with TypeScript types"""
        code = """
beforeEach(async (): Promise<void> => {
    await cache.clear();
});
"""
        fixture = assert_fixture_with_type_detected(code, "typescript", "before_each")
        assert fixture.scope == "per_test"


class TestTypeScriptMochaHooks:
    """Mocha fixtures in TypeScript"""

    def test_mocha_before_with_types(self):
        """Mocha before() hook in TypeScript"""
        code = """
import { describe, before } from 'mocha';

describe('Suite', () => {
    let service: UserService;
    
    before(async function(): Promise<void> {
        service = new UserService();
        await service.initialize();
    });
});
"""
        fixture = assert_fixture_with_type_detected(code, "typescript", "mocha_before")
        assert fixture.fixture_type == "mocha_before"


class TestTypeScriptVitestAroundHooks:
    """Vitest 4.1+ aroundEach/aroundAll in TypeScript."""

    def test_around_each_with_types(self):
        code = """
import { aroundEach, test } from 'vitest'

aroundEach(async (runTest: () => Promise<void>) => {
    await db.transaction(runTest)
})
"""
        fixture = assert_fixture_with_type_detected(
            code, "typescript", "vitest_around_each"
        )
        assert fixture.scope == "per_test"


class TestTypeScriptAsyncAwait:
    """Async/await patterns in TypeScript fixtures"""

    def test_async_fixture_with_await(self):
        """TypeScript fixture with async/await"""
        code = """
beforeEach(async () => {
    const response = await fetch('/api/data');
    this.data = await response.json();
});
"""
        fixture = assert_fixture_with_type_detected(code, "typescript", "before_each")
        assert fixture.fixture_type == "before_each"


class TestTypeScriptDecoratorHooksNotDetected:
    """Decorator-style lifecycle hooks (@BeforeEach etc. on class methods)
    are deliberately NOT detected -- verified that no currently real,
    actively-used package provides this exact decorator convention (the
    obvious candidate, mocha-typescript, is deprecated; its successor
    @testdeck/mocha uses plain before()/after() methods, not decorators;
    see fixture_definitions.yaml's javascript_typescript.excluded list)."""

    def test_before_each_decorator_not_detected(self):
        code = """
class MySuite {
    @BeforeEach
    setup() {
        this.value = 1;
    }
}
"""
        assert_fixture_count(code, "typescript", 0)

    def test_before_decorator_not_detected(self):
        code = """
class MySuite {
    @Before
    setup() {
        this.value = 1;
    }
}
"""
        assert_fixture_count(code, "typescript", 0)


class TestTypeScriptInterfaces:
    """Fixtures with TypeScript interfaces and types"""

    def test_fixture_returning_typed_object(self):
        """Fixture returning object with interface type"""
        code = """
interface TestContext {
    user: User;
    db: Database;
}

beforeEach(function(this: TestContext) {
    this.user = new User();
    this.db = new Database();
});
"""
        fixture = assert_fixture_with_type_detected(code, "typescript", "before_each")
        assert fixture.fixture_type == "before_each"


class TestTypeScriptNegativeDetection:
    """Non-fixtures in TypeScript"""

    def test_arrow_function_not_fixture(self):
        """Regular arrow function should not be detected"""
        code = """
const regularFunction = (): number => {
    return 42;
};
"""
        fixtures = extract_and_find_fixtures(code, "typescript")
        assert not any(f.name == "regularFunction" for f in fixtures)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
