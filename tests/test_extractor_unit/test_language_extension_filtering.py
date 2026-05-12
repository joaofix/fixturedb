"""
Unit tests for language-specific file extension filtering in collection/extractor.py

Validates that files with mismatched extensions (e.g., Kotlin in TypeScript repo)
are properly skipped during extraction.
"""

from pathlib import Path
import pytest

from collection.extractor import should_process_file


class TestLanguageExtensionFiltering:
    """Test file extension validation for language matching."""

    # ========================================================================
    # Python Files
    # ========================================================================

    def test_python_file_accepted(self):
        """Python files with .py extension should be processed."""
        assert should_process_file(Path("test.py"), "python") is True

    def test_python_file_rejected_wrong_extension(self):
        """Non-Python files should be skipped in Python repos."""
        assert should_process_file(Path("test.kt"), "python") is False
        assert should_process_file(Path("test.java"), "python") is False
        assert should_process_file(Path("test.go"), "python") is False
        assert should_process_file(Path("test.ts"), "python") is False

    # ========================================================================
    # Java Files
    # ========================================================================

    def test_java_file_accepted(self):
        """Java files with .java extension should be processed."""
        assert should_process_file(Path("TestSuite.java"), "java") is True

    def test_java_file_rejected_wrong_extension(self):
        """Non-Java files should be skipped in Java repos."""
        assert should_process_file(Path("test.kt"), "java") is False  # Kotlin
        assert should_process_file(Path("test.py"), "java") is False
        assert should_process_file(Path("test.go"), "java") is False
        assert should_process_file(Path("test.ts"), "java") is False

    # ========================================================================
    # JavaScript Files
    # ========================================================================

    def test_javascript_file_accepted(self):
        """JavaScript files with standard extensions should be processed."""
        assert should_process_file(Path("test.js"), "javascript") is True

    def test_javascript_variants_accepted(self):
        """JavaScript variants (.mjs, .cjs, .jsx) should be processed."""
        assert should_process_file(Path("test.mjs"), "javascript") is True
        assert should_process_file(Path("test.cjs"), "javascript") is True
        assert should_process_file(Path("test.jsx"), "javascript") is True

    def test_javascript_file_rejected_wrong_extension(self):
        """Non-JavaScript files should be skipped in JavaScript repos."""
        assert should_process_file(Path("test.ts"), "javascript") is False
        assert should_process_file(Path("test.py"), "javascript") is False
        assert should_process_file(Path("test.java"), "javascript") is False
        assert should_process_file(Path("test.kt"), "javascript") is False

    # ========================================================================
    # TypeScript Files
    # ========================================================================

    def test_typescript_file_accepted(self):
        """TypeScript files with .ts extension should be processed."""
        assert should_process_file(Path("test.ts"), "typescript") is True

    def test_typescript_variants_accepted(self):
        """TypeScript variants (.tsx) should be processed."""
        assert should_process_file(Path("test.tsx"), "typescript") is True

    def test_typescript_file_rejected_wrong_extension(self):
        """Non-TypeScript files should be skipped in TypeScript repos."""
        assert should_process_file(Path("test.js"), "typescript") is False
        assert should_process_file(Path("test.py"), "typescript") is False
        assert (
            should_process_file(Path("test.kt"), "typescript") is False
        )  # Kotlin case
        assert should_process_file(Path("test.java"), "typescript") is False

    # ========================================================================
    # Go Files
    # ========================================================================

    def test_go_file_accepted(self):
        """Go files with .go extension should be processed."""
        assert should_process_file(Path("example_test.go"), "go") is True

    def test_go_file_rejected_wrong_extension(self):
        """Non-Go files should be skipped in Go repos."""
        assert should_process_file(Path("test.py"), "go") is False
        assert should_process_file(Path("test.java"), "go") is False
        assert should_process_file(Path("test.kt"), "go") is False
        assert should_process_file(Path("test.ts"), "go") is False

    # ========================================================================
    # Edge Cases
    # ========================================================================

    def test_case_insensitive_extension(self):
        """File extensions should be case-insensitive."""
        assert should_process_file(Path("TEST.PY"), "python") is True
        assert should_process_file(Path("Test.Ts"), "typescript") is True
        assert should_process_file(Path("EXAMPLE.JAVA"), "java") is True

    def test_unknown_language_always_processed(self):
        """Files in unknown languages should always be processed (safe fallback)."""
        assert should_process_file(Path("test.rb"), "ruby") is True
        assert should_process_file(Path("test.scala"), "scala") is True
        assert should_process_file(Path("test.xyz"), "unknown") is True

    def test_nested_path_extension_checked(self):
        """Extension should be checked even for deeply nested paths."""
        assert (
            should_process_file(Path("src/test/utils/test_helper.py"), "python") is True
        )
        assert (
            should_process_file(Path("src/test/utils/test_helper.kt"), "python")
            is False
        )
        assert (
            should_process_file(
                Path("app/src/test/java/com/example/MyTest.java"), "java"
            )
            is True
        )

    def test_multiple_dots_in_filename(self):
        """Only the final extension should be checked."""
        assert should_process_file(Path("test.fixture.py"), "python") is True
        assert should_process_file(Path("test.data.json"), "python") is False
        assert should_process_file(Path("my.test.spec.ts"), "typescript") is True

    # ========================================================================
    # Real-World Regression Test: Kotlin in TypeScript Repo
    # ========================================================================

    def test_kotlin_in_typescript_repo_filtered(self):
        """
        Real case from validation: Kotlin file in TypeScript repository.
        This should be filtered out.

        Context: mongodb/docs had Kotlin test file (.kt) in what should be
        TypeScript tests. This was a false positive that should have been caught.
        """
        # The problematic file from the validation
        kotlin_path = Path(
            "content/kotlin/upcoming/examples/src/test/kotlin/FiltersBuildersTest.kt"
        )

        # Should be rejected in a TypeScript repo
        assert should_process_file(kotlin_path, "typescript") is False

        # Should be accepted if the repo was actually Kotlin
        assert should_process_file(kotlin_path, "kotlin") is True
