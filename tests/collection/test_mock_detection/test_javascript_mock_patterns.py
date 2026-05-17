"""
Mock detection tests for JavaScript fixtures.

Validates that the extractor correctly identifies mock usage patterns
in JavaScript test fixtures.
"""

import pytest
from ..conftest import (
    extract_and_find_fixtures,
    assert_fixture_detected,
    assert_fixture_not_detected,
    assert_fixture_count,
    assert_fixture_with_type_detected,
)


class TestJavaScriptJestMockPatterns:
    """Jest mock patterns"""

    def test_jest_mock_function(self):
        """Jest jest.fn() mock in beforeEach"""
        code = """
describe('Module', () => {
    let mockCallback;
    
    beforeEach(() => {
        mockCallback = jest.fn();
        mockCallback.mockReturnValue(42);
    });
});
"""
        fixture = assert_fixture_with_type_detected(code, "javascript", "before_each")
        assert fixture.fixture_type == "before_each"

    def test_jest_mock_module(self):
        """jest.mock() for module mocking"""
        code = """
jest.mock('./api');
const api = require('./api');

beforeEach(() => {
    api.fetch.mockResolvedValue({data: []});
});
"""
        fixture = assert_fixture_with_type_detected(code, "javascript", "before_each")
        assert fixture.fixture_type == "before_each"


class TestJavaScriptSinonPatterns:
    """Sinon stub/spy patterns"""

    def test_sinon_stub_setup(self):
        """Sinon stub/spy setup in beforeEach"""
        code = """
const sinon = require('sinon');

describe('Test', function() {
    let stub;
    
    beforeEach(function() {
        stub = sinon.stub(obj, 'method').returns(42);
    });
    
    afterEach(function() {
        stub.restore();
    });
});
"""
        fixture = assert_fixture_with_type_detected(code, "javascript", "before_each")
        assert fixture.fixture_type == "before_each"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
