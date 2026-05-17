"""
Integration tests for JavaScript fixture extraction on realistic code.

Tests extraction on actual test files with multiple fixtures,
complex setups, and real-world patterns from popular JS frameworks.
"""

import pytest
from ..conftest import (
    extract_and_find_fixtures,
    assert_fixture_detected,
    assert_fixture_count,
    assert_fixture_with_type_detected,
)


class TestJavaScriptJestFixtures:
    """Integration tests using Jest patterns"""

    def test_jest_complex_setup(self):
        """Jest test file with multiple setup methods"""
        code = """
const { setupDatabase, teardownDatabase } = require('./db-setup');

describe('User API', () => {
    let app;
    let request;
    
    beforeAll(async () => {
        await setupDatabase();
        app = require('./app');
        request = require('supertest')(app);
    });
    
    beforeEach(() => {
        jest.clearAllMocks();
    });
    
    afterEach(async () => {
        await User.deleteMany({});
    });
    
    afterAll(async () => {
        await teardownDatabase();
    });
});
"""
        assert_fixture_with_type_detected(code, "javascript", "before_all")
        assert_fixture_with_type_detected(code, "javascript", "before_each")
        assert_fixture_with_type_detected(code, "javascript", "after_each")
        assert_fixture_with_type_detected(code, "javascript", "after_all")


class TestJavaScriptMochaFixtures:
    """Integration tests using Mocha patterns"""

    def test_mocha_with_context(self):
        """Mocha test with describe/context blocks"""
        code = """
const assert = require('assert');

describe('Array', () => {
    let array;
    
    beforeEach(() => {
        array = [1, 2, 3];
    });
    
    describe('methods', () => {
        let length;
        
        beforeEach(function() {
            length = array.length;
        });
        
        it('should have correct length', () => {
            assert.equal(length, 3);
        });
    });
});
"""
        # Should detect nested beforeEach fixtures
        assert_fixture_count(code, "javascript", 2)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
