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
    extract_and_find_fixtures,
    assert_fixture_detected,
    assert_fixture_not_detected,
    assert_fixture_count,
    assert_fixture_with_type_detected,
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
