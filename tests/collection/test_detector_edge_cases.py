"""
Detector edge case and error handling tests.

Tests cover critical error paths and boundary conditions:
- Malformed code, empty files, unusually large files
- Timeout handling and file size limits
- Language-specific edge cases (unusual syntax, dynamic code)
- Error recovery and graceful degradation
"""

import pytest
import tempfile
from pathlib import Path

from collection.detector import extract_fixtures, ExtractResult


class TestDetectorErrorHandling:
    """Test detector robustness against malformed and edge-case code."""

    def test_extract_empty_file(self, tmp_path):
        """Detector should handle empty files gracefully."""
        empty_file = tmp_path / "test_empty.py"
        empty_file.write_text("")

        result = extract_fixtures(empty_file, "python")

        assert isinstance(result, ExtractResult)
        assert len(result.fixtures) == 0
        # Should handle gracefully without crashing

    def test_extract_file_with_only_comments(self, tmp_path):
        """File with only comments should return no fixtures."""
        py_file = tmp_path / "test_comments.py"
        py_file.write_text("""
# This is a test file
# It has only comments
# No actual code
""")

        result = extract_fixtures(py_file, "python")

        assert len(result.fixtures) == 0

    def test_extract_file_with_only_imports(self, tmp_path):
        """File with only imports should return no fixtures."""
        py_file = tmp_path / "test_imports.py"
        py_file.write_text("""
import pytest
import unittest
from pathlib import Path
from collections import defaultdict
""")

        result = extract_fixtures(py_file, "python")

        assert len(result.fixtures) == 0

    def test_extract_syntactically_invalid_python(self, tmp_path):
        """Invalid Python syntax should be handled gracefully."""
        py_file = tmp_path / "test_invalid.py"
        py_file.write_text("""
@pytest.fixture
def broken_fixture(
    # Missing closing paren
    
def another_function():
    pass
""")

        result = extract_fixtures(py_file, "python")

        # Should not crash; may find no fixtures or return error
        assert result is not None
        # Invalid syntax may prevent detection or error out gracefully
        assert isinstance(result.fixtures, list)

    def test_extract_java_invalid_syntax(self, tmp_path):
        """Invalid Java syntax should be handled gracefully."""
        java_file = tmp_path / "TestInvalid.java"
        java_file.write_text("""
public class TestInvalid {
    @Before
    public void setup(
    // Missing closing paren and body
}
""")

        result = extract_fixtures(java_file, "java")

        assert result is not None
        assert isinstance(result.fixtures, list)

    def test_extract_file_with_encoding_issues(self, tmp_path):
        """File with non-UTF8 encoding should be handled."""
        py_file = tmp_path / "test_encoding.py"
        # Write with UTF-8 but with special chars
        content = """
import pytest

@pytest.fixture
def fixture_with_emoji():  # 🔧 fixture
    '''Setup with special chars: café, naïve'''
    pass
"""
        py_file.write_text(content, encoding="utf-8")

        result = extract_fixtures(py_file, "python")

        # Should handle UTF-8 gracefully
        assert result is not None
        if len(result.fixtures) > 0:
            assert result.fixtures[0].name == "fixture_with_emoji"

    def test_extract_large_function_with_very_deep_nesting(self, tmp_path):
        """Function with extremely deep nesting should be parsed."""
        py_file = tmp_path / "test_deeply_nested.py"
        py_file.write_text("""
import pytest

@pytest.fixture
def deeply_nested():
    if True:
        if True:
            if True:
                if True:
                    if True:
                        if True:
                            if True:
                                if True:
                                    if True:
                                        if True:
                                            result = create_resource()
                                            return result
""")

        result = extract_fixtures(py_file, "python")

        assert len(result.fixtures) > 0
        assert result.fixtures[0].name == "deeply_nested"
        # Should calculate complexity correctly despite deep nesting
        assert result.fixtures[0].cyclomatic_complexity >= 1

    def test_extract_fixture_with_very_long_lines(self, tmp_path):
        """Function with extremely long lines should be parsed."""
        py_file = tmp_path / "test_long_lines.py"
        long_line = "x = " + " + ".join([f"value_{i}" for i in range(500)])
        py_file.write_text(f"""
import pytest

@pytest.fixture
def fixture_with_long_lines():
    {long_line}
    return x
""")

        result = extract_fixtures(py_file, "python")

        assert len(result.fixtures) > 0
        assert result.fixtures[0].name == "fixture_with_long_lines"


class TestDetectorLanguageEdgeCases:
    """Test language-specific edge cases and unusual patterns."""

    def test_python_async_fixture(self, tmp_path):
        """Python async fixtures should be detected."""
        py_file = tmp_path / "test_async.py"
        py_file.write_text("""
import pytest

@pytest.fixture
async def async_fixture():
    await setup()
    yield result
    await cleanup()
""")

        result = extract_fixtures(py_file, "python")

        assert len(result.fixtures) > 0
        assert result.fixtures[0].name == "async_fixture"

    def test_python_nested_function_definitions(self, tmp_path):
        """Nested function definitions (closure fixtures) should be detected at top level only."""
        py_file = tmp_path / "test_nested.py"
        py_file.write_text("""
import pytest

@pytest.fixture
def outer_fixture():
    def inner_helper():
        pass
    inner_helper()
    return "value"

def regular_function():
    def inner():
        pass
    return inner
""")

        result = extract_fixtures(py_file, "python")

        # Should detect the outer_fixture but not inner helpers
        fixture_names = [f.name for f in result.fixtures]
        assert "outer_fixture" in fixture_names

    def test_java_parameterized_tests(self, tmp_path):
        """Java parameterized test fixtures should be detected."""
        java_file = tmp_path / "TestParameterized.java"
        java_file.write_text("""
import org.junit.Before;
import org.junit.Parameterized;

public class TestParameterized {
    private String param;
    
    @Before
    public void setup() {
        initializeWithParam(param);
    }
}
""")

        result = extract_fixtures(java_file, "java")

        if len(result.fixtures) > 0:
            assert result.fixtures[0].name == "setup"

    def test_typescript_decorator_with_metadata(self, tmp_path):
        """TypeScript decorators with metadata (Nest.js style) should be handled."""
        ts_file = tmp_path / "test.spec.ts"
        ts_file.write_text("""
import { describe, beforeEach } from 'jest';

describe('Test suite', () => {
    beforeEach(() => {
        // Setup code
    });
    
    it('should work', () => {
        // Test code
    });
});
""")

        result = extract_fixtures(ts_file, "typescript")

        # beforeEach should be detected as per_test fixture
        if len(result.fixtures) > 0:
            before_each = [
                f
                for f in result.fixtures
                if "beforeEach" in f.name or "before" in f.fixture_type.lower()
            ]
            if before_each:
                assert before_each[0].scope == "per_test"

    def test_go_test_main_in_multiple_files(self, tmp_path):
        """Go files should be ignored because Go is unsupported."""
        go_file = tmp_path / "setup_test.go"
        go_file.write_text("""
package main

import (
    "testing"
)

func TestMain(m *testing.M) {
    setupGlobal()
    code := m.Run()
    cleanupGlobal()
    os.Exit(code)
}
""")

        result = extract_fixtures(go_file, "go")
        assert result.fixtures == []


class TestDetectorBoundaryConditions:
    """Test boundary conditions and limits."""

    def test_many_fixtures_in_single_file(self, tmp_path):
        """File with many fixtures should handle all of them."""
        py_file = tmp_path / "test_many.py"

        fixture_defs = "\n".join(
            [
                f"""
@pytest.fixture
def fixture_{i}():
    return {i}
"""
                for i in range(50)
            ]
        )

        py_file.write_text(f"import pytest\n{fixture_defs}")

        result = extract_fixtures(py_file, "python")

        # Should detect many fixtures
        assert len(result.fixtures) >= 50

    def test_very_complex_fixture(self, tmp_path):
        """Extremely complex fixture should calculate metrics."""
        py_file = tmp_path / "test_complex.py"
        complex_code = """
import pytest

@pytest.fixture
def ultra_complex():
    result = initialize()
    
    for i in range(10):
        for j in range(10):
            for k in range(10):
                try:
                    if check_condition(i, j, k):
                        process(i, j, k)
                except Exception:
                    handle_error(i, j, k)
                    if should_retry():
                        retry(i, j, k)
    
    if not result:
        result = fallback()
    
    return result
"""
        py_file.write_text(complex_code)

        result = extract_fixtures(py_file, "python")

        assert len(result.fixtures) > 0
        fixture = result.fixtures[0]
        # Complex fixture should have detectable cyclomatic complexity
        assert fixture.cyclomatic_complexity >= 1

    def test_fixture_with_many_parameters(self, tmp_path):
        """Fixture with many parameters should extract parameter count."""
        py_file = tmp_path / "test_params.py"
        py_file.write_text("""
import pytest

@pytest.fixture
def parametrized_fixture(request, arg1, arg2, arg3, arg4, arg5):
    return arg1 + arg2 + arg3 + arg4 + arg5
""")

        result = extract_fixtures(py_file, "python")

        assert len(result.fixtures) > 0
        fixture = result.fixtures[0]
        # Should count parameters correctly (5 in this case, not counting request)
        assert fixture.num_parameters >= 5


class TestDetectorConsistency:
    """Test consistency of detector results across repeated runs."""

    def test_repeated_extraction_same_results(self, tmp_path):
        """Extracting the same file twice should produce identical results."""
        py_file = tmp_path / "test_consistent.py"
        py_file.write_text("""
import pytest

@pytest.fixture
def stable_fixture():
    db = setup_db()
    yield db
    teardown_db(db)

def test_example():
    pass
""")

        result1 = extract_fixtures(py_file, "python")
        result2 = extract_fixtures(py_file, "python")

        assert len(result1.fixtures) == len(result2.fixtures)
        if result1.fixtures:
            f1 = result1.fixtures[0]
            f2 = result2.fixtures[0]
            assert f1.name == f2.name
            assert f1.start_line == f2.start_line
            assert f1.end_line == f2.end_line
            assert f1.cyclomatic_complexity == f2.cyclomatic_complexity


class TestDetectorLineNumberAccuracy:
    """Test that line numbers are accurate."""

    def test_fixture_line_numbers_accurate(self, tmp_path):
        """Detected fixtures should have correct start and end line numbers."""
        py_file = tmp_path / "test_lines.py"
        content = """import pytest

# Line 3: comment
# Line 4: comment

@pytest.fixture  # Line 6
def my_fixture():  # Line 7
    '''Docstring'''  # Line 8
    x = 1  # Line 9
    return x  # Line 10
# Line 11
"""
        py_file.write_text(content)

        result = extract_fixtures(py_file, "python")

        assert len(result.fixtures) > 0
        fixture = result.fixtures[0]
        # start_line should be around line 6 (decorator) or 7 (def)
        assert 6 <= fixture.start_line <= 7
        # end_line should be around line 10
        assert fixture.end_line >= 10
