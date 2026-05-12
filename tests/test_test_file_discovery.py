"""
Tests for test file discovery logic in the extractor module.

Validates that:
1. Test files are correctly identified by path and filename patterns
2. False positives are avoided (e.g., "latest" doesn't match "test")
3. Path pattern matching respects directory boundaries (uses "/" delimiters)
4. Vendor/third-party directories are correctly excluded
"""

import pytest
import tempfile
from pathlib import Path
from collection.extractor import _find_test_files
from collection.config import LANGUAGE_CONFIGS


class TestTestFileDiscoveryPythonPositives:
    """Test that valid Python test files are correctly identified."""

    def test_discover_test_underscore_prefix(self):
        """Discover test_*.py files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)

            # Create test files
            (repo / "test_main.py").write_text("# test")
            (repo / "test_utils.py").write_text("# test")
            (repo / "_test.py").write_text("# test")
            (repo / "utils_test.py").write_text("# test")

            test_files = _find_test_files(repo, "python")
            names = {f.name for f in test_files}

            assert "test_main.py" in names
            assert "test_utils.py" in names
            assert "_test.py" in names
            assert "utils_test.py" in names

    def test_discover_test_directory(self):
        """Discover files in /test/ and /tests/ directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)

            # Create test directories and files
            (repo / "test").mkdir()
            (repo / "test" / "test_main.py").write_text("# test")

            (repo / "tests").mkdir()
            (repo / "tests" / "main_test.py").write_text("# test")

            test_files = _find_test_files(repo, "python")
            names = {f.name for f in test_files}

            assert "test_main.py" in names
            assert "main_test.py" in names

    def test_discover_testing_directory(self):
        """Discover files in /testing/ directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)

            # Create testing directory
            (repo / "testing").mkdir()
            (repo / "testing" / "test_main.py").write_text("# test")

            test_files = _find_test_files(repo, "python")

            # Should match because filename has test_ prefix
            assert len(test_files) >= 1
            assert any("test_main.py" in str(f) for f in test_files)

    def test_discover_conftest(self):
        """Discover conftest files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)

            (repo / "conftest.py").write_text("# test")
            (repo / "tests").mkdir()
            (repo / "tests" / "conftest.py").write_text("# test")

            test_files = _find_test_files(repo, "python")
            # Both should be found: one by filename pattern (conftest.py), one by being in tests/ dir
            assert len(test_files) >= 1
            assert any("conftest.py" in str(f) for f in test_files)


class TestTestFileDiscoveryPythonNegatives:
    """Test that non-test files are NOT identified as test files."""

    def test_false_positive_latest_not_matched(self):
        """CRITICAL: 'latest' should NOT match /test/ pattern."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)

            # Create a folder structure with "latest" in the path
            (repo / "src" / "latest" / "models").mkdir(parents=True)
            (repo / "src" / "latest" / "models" / "user.py").write_text("# code")

            test_files = _find_test_files(repo, "python")

            # Should NOT include files under "latest"
            assert not any(
                "user.py" in str(f) for f in test_files
            ), "File under 'latest' directory should not be detected as test file"

    def test_false_positive_testing_as_word(self):
        """'testing' as a word in a directory name should not match."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)

            # Create directories with "testing" as substring but not actual test dir
            (repo / "mytesting" / "utils").mkdir(parents=True)
            (repo / "mytesting" / "utils" / "helper.py").write_text("# code")

            test_files = _find_test_files(repo, "python")

            # Should NOT include files under "mytesting"
            assert not any(
                "helper.py" in str(f) for f in test_files
            ), "File under 'mytesting' should not be detected as test file"

    def test_false_positive_contest_not_matched(self):
        """'conftest' pattern should not match 'contest'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)

            (repo / "contest").mkdir()
            (repo / "contest" / "main.py").write_text("# code")

            test_files = _find_test_files(repo, "python")

            # Should NOT include files from "contest" directory
            assert not any(
                "main.py" in str(f) for f in test_files
            ), "File under 'contest' should not be detected as test file"

    def test_exclude_regular_files_without_test_pattern(self):
        """Regular Python files should not be detected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)

            (repo / "src").mkdir()
            (repo / "src" / "main.py").write_text("# code")
            (repo / "src" / "utils.py").write_text("# code")

            test_files = _find_test_files(repo, "python")

            assert len(test_files) == 0


class TestTestFileDiscoveryJavaScript:
    """Test JavaScript test file discovery."""

    def test_discover_jest_test_files(self):
        """Discover Jest test files (.test.js, .spec.js)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)

            (repo / "main.test.js").write_text("// test")
            (repo / "main.spec.js").write_text("// test")

            test_files = _find_test_files(repo, "javascript")
            names = {f.name for f in test_files}

            assert "main.test.js" in names
            assert "main.spec.js" in names

    def test_discover_tests_directory(self):
        """Discover files in /tests/ and /test/ directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)

            (repo / "tests").mkdir()
            (repo / "tests" / "main.test.js").write_text("// test")

            test_files = _find_test_files(repo, "javascript")
            assert len(test_files) == 1

    def test_discover_tests_directory_with_underscore(self):
        """Discover files in /__tests__/ directory (Node.js convention)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)

            (repo / "__tests__").mkdir()
            (repo / "__tests__" / "main.test.js").write_text("// test")

            test_files = _find_test_files(repo, "javascript")
            assert len(test_files) == 1

    def test_javascript_false_positive_latest(self):
        """'latest' should NOT match /test/ pattern in JavaScript."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)

            (repo / "src" / "latest").mkdir(parents=True)
            (repo / "src" / "latest" / "index.js").write_text("// code")

            test_files = _find_test_files(repo, "javascript")

            assert not any("index.js" in str(f) for f in test_files)

    def test_discover_spec_directory(self):
        """Discover files in /spec/ directory (Jasmine/Jest convention)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)

            (repo / "spec").mkdir()
            (repo / "spec" / "user.js").write_text("// test")
            (repo / "spec" / "service.js").write_text("// test")

            test_files = _find_test_files(repo, "javascript")
            names = {f.name for f in test_files}

            assert "user.js" in names
            assert "service.js" in names
            assert len(test_files) == 2

    def test_discover_nested_spec_directory(self):
        """Discover files in nested spec paths like src/spec/."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)

            (repo / "src" / "spec").mkdir(parents=True)
            (repo / "src" / "spec" / "helper.js").write_text("// test")

            test_files = _find_test_files(repo, "javascript")
            assert len(test_files) == 1
            assert "helper.js" in test_files[0].name

    def test_discover_spec_file_and_spec_directory(self):
        """Discover .spec.js files in both spec/ directory and elsewhere."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)

            # File in spec/ directory (no suffix required)
            (repo / "spec").mkdir()
            (repo / "spec" / "user.js").write_text("// test")

            # File with .spec.js suffix (matched by filename)
            (repo / "app.spec.js").write_text("// test")

            # File in spec/ directory WITH .spec.js suffix
            (repo / "spec" / "service.spec.js").write_text("// test")

            test_files = _find_test_files(repo, "javascript")
            names = {f.name for f in test_files}

            assert len(test_files) == 3
            assert "user.js" in names
            assert "app.spec.js" in names
            assert "service.spec.js" in names

    def test_javascript_false_positive_spectrum(self):
        """'spectrum' directory should NOT match /spec/ pattern."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)

            (repo / "spectrum" / "colors").mkdir(parents=True)
            (repo / "spectrum" / "colors" / "palette.js").write_text("// code")

            test_files = _find_test_files(repo, "javascript")

            assert not any("palette.js" in str(f) for f in test_files)

    def test_javascript_false_positive_respect(self):
        """'respect' directory should NOT match /spec/ pattern."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)

            (repo / "respect" / "rules").mkdir(parents=True)
            (repo / "respect" / "rules" / "config.js").write_text("// code")

            test_files = _find_test_files(repo, "javascript")

            assert not any("config.js" in str(f) for f in test_files)


class TestTestFileDiscoveryJava:
    """Test Java test file discovery."""

    def test_discover_test_class_files(self):
        """Discover Java test files (*Tests.java, *IT.java, *Spec.java)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)

            # Note: Java suffix patterns use exact endswith matching
            # "Test.java", "Tests.java", "IT.java", "Spec.java"
            (repo / "MainTests.java").write_text("// test")
            (repo / "ServiceIT.java").write_text("// test")
            (repo / "UserSpec.java").write_text("// test")

            test_files = _find_test_files(repo, "java")
            names = {f.name for f in test_files}

            assert "MainTests.java" in names
            assert "ServiceIT.java" in names
            assert "UserSpec.java" in names

    def test_discover_src_test_directory(self):
        """Discover files in /src/test/ directory (Maven structure)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)

            (repo / "src" / "test" / "java").mkdir(parents=True)
            (repo / "src" / "test" / "java" / "TestMain.java").write_text("// test")

            test_files = _find_test_files(repo, "java")
            assert len(test_files) == 1


class TestTestFileDiscoveryTypeScript:
    """Test TypeScript test file discovery."""

    def test_discover_typescript_test_files(self):
        """Discover TypeScript test files (.test.ts, .spec.ts)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)

            (repo / "main.test.ts").write_text("// test")
            (repo / "main.spec.ts").write_text("// test")

            test_files = _find_test_files(repo, "typescript")
            names = {f.name for f in test_files}

            assert "main.test.ts" in names
            assert "main.spec.ts" in names

    def test_discover_spec_directory_typescript(self):
        """Discover files in /spec/ directory for TypeScript."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)

            (repo / "spec").mkdir()
            (repo / "spec" / "user.ts").write_text("// test")
            (repo / "spec" / "service.ts").write_text("// test")

            test_files = _find_test_files(repo, "typescript")
            names = {f.name for f in test_files}

            assert "user.ts" in names
            assert "service.ts" in names
            assert len(test_files) == 2

    def test_discover_nested_spec_directory_typescript(self):
        """Discover files in nested spec paths like src/spec/ for TypeScript."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)

            (repo / "src" / "spec").mkdir(parents=True)
            (repo / "src" / "spec" / "helper.ts").write_text("// test")

            test_files = _find_test_files(repo, "typescript")
            assert len(test_files) == 1
            assert "helper.ts" in test_files[0].name

    def test_discover_spec_file_and_spec_directory_typescript(self):
        """Discover .spec.ts files in both spec/ directory and elsewhere for TypeScript."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)

            # File in spec/ directory (no suffix required)
            (repo / "spec").mkdir()
            (repo / "spec" / "user.ts").write_text("// test")

            # File with .spec.ts suffix (matched by filename)
            (repo / "app.spec.ts").write_text("// test")

            # File in spec/ directory WITH .spec.ts suffix
            (repo / "spec" / "service.spec.ts").write_text("// test")

            test_files = _find_test_files(repo, "typescript")
            names = {f.name for f in test_files}

            assert len(test_files) == 3
            assert "user.ts" in names
            assert "app.spec.ts" in names
            assert "service.spec.ts" in names

    def test_typescript_false_positive_spectrum(self):
        """'spectrum' directory should NOT match /spec/ pattern for TypeScript."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)

            (repo / "spectrum" / "colors").mkdir(parents=True)
            (repo / "spectrum" / "colors" / "palette.ts").write_text("// code")

            test_files = _find_test_files(repo, "typescript")

            assert not any("palette.ts" in str(f) for f in test_files)

    def test_typescript_false_positive_respect(self):
        """'respect' directory should NOT match /spec/ pattern for TypeScript."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)

            (repo / "respect" / "rules").mkdir(parents=True)
            (repo / "respect" / "rules" / "config.ts").write_text("// code")

            test_files = _find_test_files(repo, "typescript")

            assert not any("config.ts" in str(f) for f in test_files)


class TestTestFileDiscoveryVendorExclusion:
    """Test that vendor/third-party directories are excluded."""

    def test_exclude_node_modules(self):
        """Exclude files in node_modules."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)

            (repo / "node_modules" / "jest").mkdir(parents=True)
            (repo / "node_modules" / "jest" / "test.js").write_text("// test")

            (repo / "test.js").write_text("// test")

            test_files = _find_test_files(repo, "javascript")

            # Should only find the root test.js, not the one in node_modules
            assert len(test_files) == 1
            assert test_files[0].name == "test.js"

    def test_exclude_vendor(self):
        """Exclude files in vendor directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)

            (repo / "vendor" / "test").mkdir(parents=True)
            (repo / "vendor" / "test" / "main_test.php").write_text("// test")

            test_files = _find_test_files(repo, "python")

            # Vendor should be excluded
            assert len(test_files) == 0

    def test_exclude_pycache(self):
        """Exclude files in __pycache__."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)

            (repo / "__pycache__").mkdir()
            (repo / "__pycache__" / "test_main.pyc").write_text("# compiled")

            test_files = _find_test_files(repo, "python")

            assert len(test_files) == 0

    def test_exclude_build_and_dist(self):
        """Exclude files in build and dist directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)

            (repo / "build" / "tests").mkdir(parents=True)
            (repo / "build" / "tests" / "test.py").write_text("# test")

            (repo / "dist" / "tests").mkdir(parents=True)
            (repo / "dist" / "tests" / "test.py").write_text("# test")

            test_files = _find_test_files(repo, "python")

            assert len(test_files) == 0


class TestTestFileDiscoveryBoundaryConditions:
    """Test boundary conditions and path matching."""

    def test_nested_test_directories(self):
        """Discover test files in nested directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)

            (repo / "src" / "tests" / "unit").mkdir(parents=True)
            (repo / "src" / "tests" / "unit" / "main_test.py").write_text("# test")

            (repo / "src" / "tests" / "integration").mkdir(parents=True)
            (repo / "src" / "tests" / "integration" / "api_test.py").write_text(
                "# test"
            )

            test_files = _find_test_files(repo, "python")
            assert len(test_files) == 2

    def test_mixed_test_and_source_files(self):
        """Handle directories with both test and source files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)

            (repo / "src").mkdir()
            (repo / "src" / "main.py").write_text("# code")
            (repo / "src" / "test_main.py").write_text("# test")

            test_files = _find_test_files(repo, "python")

            # Should only find test_main.py
            assert len(test_files) == 1
            assert test_files[0].name == "test_main.py"

    def test_path_pattern_case_insensitivity(self):
        """Path patterns should match case-insensitively."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)

            # Create Tests directory (uppercase) with test file
            (repo / "Tests").mkdir()
            (repo / "Tests" / "MyTest.py").write_text("# test")

            test_files = _find_test_files(repo, "python")

            # Should find file in /Tests/ (case-insensitive match to /tests/)
            assert len(test_files) >= 1
            assert any("MyTest.py" in str(f) for f in test_files)


class TestTestFileDiscoveryEdgeCases:
    """Test edge cases and unusual scenarios."""

    def test_empty_repository(self):
        """Handle empty repository."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)

            test_files = _find_test_files(repo, "python")

            assert len(test_files) == 0

    def test_single_file_repository(self):
        """Handle repository with single test file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)

            (repo / "test_main.py").write_text("# test")

            test_files = _find_test_files(repo, "python")

            assert len(test_files) == 1

    def test_files_without_extension(self):
        """Skip files without extensions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)

            (repo / "test").mkdir()
            (repo / "test" / "Makefile").write_text("# makefile")
            (repo / "test" / "test_readme").write_text("# readme")

            test_files = _find_test_files(repo, "python")

            # Files without extensions should be skipped
            assert len(test_files) == 0

    def test_very_large_file(self):
        """Skip files larger than MAX_FILE_SIZE_BYTES."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)

            # Create a test file that's too large (> 5 MB)
            large_file = repo / "test_large.py"
            large_file.write_text("# " + "x" * (6 * 1024 * 1024))

            test_files = _find_test_files(repo, "python")

            # Large file should be excluded
            assert not any("test_large.py" in str(f) for f in test_files)

    def test_symlinked_test_directory(self):
        """Handle symlinked test directories (should work on systems that support it)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)

            # Create actual test directory
            actual_tests = repo / "actual_tests"
            actual_tests.mkdir()
            (actual_tests / "test_main.py").write_text("# test")

            # Create symlink
            try:
                symlink = repo / "tests"
                symlink.symlink_to(actual_tests)

                test_files = _find_test_files(repo, "python")

                # Should find the test file through symlink
                assert len(test_files) >= 1
            except OSError:
                # Skip on systems that don't support symlinks
                pytest.skip("Symlinks not supported on this system")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
