"""
Mock detection tests for JavaScript fixtures.

Validates that the extractor correctly identifies mock usage patterns
in JavaScript test fixtures -- these assert on `fixture.mocks` directly,
not just that the surrounding fixture was extracted, since a fixture can
be detected correctly while its mock usage inside is silently missed.
"""

import pytest

from ..conftest import (
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
        assert fixture.mocks and fixture.mocks[0].framework == "jest"

    def test_jest_mock_module_call_inside_fixture_body(self):
        """jest.mock('./api') is detected when it's literally inside the
        fixture body being scanned."""
        code = """
beforeEach(() => {
    jest.mock('./api');
});
"""
        fixture = assert_fixture_with_type_detected(code, "javascript", "before_each")
        assert fixture.mocks
        assert fixture.mocks[0].framework == "jest"
        assert fixture.mocks[0].target_identifier == "./api"

    def test_jest_mock_module_at_top_level_is_not_attributed_to_fixture(self):
        """jest.mock('./api') at its conventional call site -- module top
        level, auto-hoisted by babel-jest -- is NOT detected as a mock on
        the beforeEach fixture below it. This is a documented, structural
        limitation (see feature_extraction_patterns.yaml's
        mock_patterns_excluded): mock detection only scans the fixture's
        own AST node text, not surrounding module-level statements."""
        code = """
jest.mock('./api');
const api = require('./api');

beforeEach(() => {
    api.fetch.mockResolvedValue({data: []});
});
"""
        fixture = assert_fixture_with_type_detected(code, "javascript", "before_each")
        assert fixture.mocks == []

    def test_jest_mocked(self):
        """jest.mocked(moduleRef) should be detected, capturing the
        wrapped identifier as target_identifier."""
        code = """
beforeEach(() => {
    const mocked = jest.mocked(myModule);
    mocked.fetch.mockResolvedValue({});
});
"""
        fixture = assert_fixture_with_type_detected(code, "javascript", "before_each")
        assert fixture.mocks
        assert fixture.mocks[0].framework == "jest"
        assert fixture.mocks[0].target_identifier == "myModule"

    def test_jest_create_mock_from_module(self):
        """jest.createMockFromModule('./api') should be detected."""
        code = """
beforeEach(() => {
    const api = jest.createMockFromModule('./api');
});
"""
        fixture = assert_fixture_with_type_detected(code, "javascript", "before_each")
        assert fixture.mocks
        assert fixture.mocks[0].framework == "jest"
        assert fixture.mocks[0].target_identifier == "./api"


class TestJavaScriptSinonPatterns:
    """Sinon stub/spy/fake/replace patterns"""

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
        assert fixture.mocks
        assert fixture.mocks[0].framework == "sinon"
        assert fixture.mocks[0].target_identifier == "stub"

    def test_sinon_fake_and_replace(self):
        """sinon.fake() and sinon.replace() were previously missing from
        the sinon alternation (only stub|spy|mock were covered)."""
        code = """
beforeEach(function() {
    const f = sinon.fake();
    sinon.replace(obj, 'method', f);
});
"""
        fixture = assert_fixture_with_type_detected(code, "javascript", "before_each")
        operations = {m.target_identifier for m in fixture.mocks}
        assert operations == {"fake", "replace"}
        assert all(m.framework == "sinon" for m in fixture.mocks)

    def test_sinon_create_stub_instance(self):
        """sinon.createStubInstance(MyClass) should be detected, capturing
        the class name as target_identifier."""
        code = """
beforeEach(function() {
    const stub = sinon.createStubInstance(MyClass);
});
"""
        fixture = assert_fixture_with_type_detected(code, "javascript", "before_each")
        assert fixture.mocks
        assert fixture.mocks[0].framework == "sinon"
        assert fixture.mocks[0].target_identifier == "MyClass"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
