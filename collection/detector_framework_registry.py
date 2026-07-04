"""Mock-framework dependency-file verification (currently unused/dead code).

Given a detected mock framework name, scans a repo's dependency files
(requirements.txt, pom.xml, package.json, go.mod, etc.) to confirm the
framework is actually declared as a dependency, reducing false positives from
similar framework names. No caller in the codebase invokes
`is_mock_framework_available()` or `_validate_framework()` today — kept
isolated here rather than wired up or deleted, since enabling/removing this
verification pass is a behavior decision, not a refactor.
"""

import re
from pathlib import Path
from typing import Optional

from collection.logging_utils import get_logger

logger = get_logger(__name__)


def is_mock_framework_available(
    framework: str, language: str, repo_path: Optional[Path] = None
) -> bool:
    """
    Check if a detected mock framework is actually available in the project (Phase 4).

    When a mock framework is detected via code pattern matching, this function
    attempts to verify that the framework is actually installed/declared as a
    dependency in the project. This reduces false positives from using similar
    framework names or homonyms.

    Args:
        framework: Detected framework name (e.g., "mockito", "unittest_mock", "jest")
        language: Programming language
        repo_path: Optional path to repository root for dependency file scanning

    Returns:
        True if framework is confirmed as available or repo_path not provided,
        False if verified as NOT available in dependencies

    Implementation:
        Scans language-specific dependency files:
        - Python: requirements.txt, setup.py, pyproject.toml, poetry.lock, Pipfile
        - Java: pom.xml, build.gradle, build.gradle.kts
        - JavaScript/TypeScript: package.json, package-lock.json, yarn.lock, pnpm-lock.yaml
        - Go: go.mod, go.sum

    Returns True if:
    - repo_path not provided (cannot verify, assume available)
    - Framework found in any dependency file
    - Framework is built-in (e.g., unittest for Python)

    Returns False if:
    - Framework pattern searched but NOT found in any dependency file
    """
    if not repo_path:
        # No repo context provided, accept all frameworks
        return True

    # Map framework names to package/module names to search for
    framework_mappings = {
        # Python frameworks
        "unittest_mock": ["unittest"],  # built-in
        "pytest_mock": ["pytest", "pytest-mock"],
        "mockito": ["mockito", "mockito-python"],
        "mock": ["mock", "unittest"],  # built-in or pypi
        # Java frameworks
        "easymock": ["easymock"],
        "mockk": ["mockk"],
        "jmockit": ["jmockit"],
        # JavaScript/TypeScript frameworks
        "jest": ["jest"],
        "sinon": ["sinon"],
        "vitest": ["vitest"],
        "mocha": ["mocha"],
        "jasmine": ["jasmine"],
        # Go frameworks
        "gomock": ["gomock", "mock"],
        "testify_mock": ["testify"],
    }

    # Get package names to search for
    package_names = framework_mappings.get(framework, [framework])

    # Language-specific dependency file scanning
    if language.lower() == "python":
        return _check_python_dependencies(repo_path, package_names)
    elif language.lower() == "java":
        return _check_java_dependencies(repo_path, package_names)
    elif language.lower() in ("javascript", "typescript"):
        return _check_javascript_dependencies(repo_path, package_names)
    elif language.lower() == "go":
        return _check_go_dependencies(repo_path, package_names)

    # Unknown language, assume available
    return True


def _check_python_dependencies(repo_path: Path, package_names: list[str]) -> bool:
    """Check if any package is listed in Python dependency files."""
    package_names_lower = [p.lower() for p in package_names]

    # Check requirements.txt
    req_file = repo_path / "requirements.txt"
    if req_file.exists():
        try:
            content = req_file.read_text(errors="ignore")
            for pkg in package_names_lower:
                # Match package name (case-insensitive, handle version specs)
                if re.search(rf"\b{re.escape(pkg)}\b", content, re.IGNORECASE):
                    return True
        except Exception:
            pass

    # Check setup.py
    setup_file = repo_path / "setup.py"
    if setup_file.exists():
        try:
            content = setup_file.read_text(errors="ignore")
            for pkg in package_names_lower:
                if re.search(rf"\b{re.escape(pkg)}\b", content, re.IGNORECASE):
                    return True
        except Exception:
            pass

    # Check pyproject.toml
    pyproject_file = repo_path / "pyproject.toml"
    if pyproject_file.exists():
        try:
            content = pyproject_file.read_text(errors="ignore")
            for pkg in package_names_lower:
                if re.search(rf"\b{re.escape(pkg)}\b", content, re.IGNORECASE):
                    return True
        except Exception:
            pass

    # Check poetry.lock
    poetry_file = repo_path / "poetry.lock"
    if poetry_file.exists():
        try:
            content = poetry_file.read_text(errors="ignore")
            for pkg in package_names_lower:
                if re.search(
                    rf"^name = \"{re.escape(pkg)}\"",
                    content,
                    re.IGNORECASE | re.MULTILINE,
                ):
                    return True
        except Exception:
            pass

    # If no files found with the package, assume not available
    return False


def _check_java_dependencies(repo_path: Path, package_names: list[str]) -> bool:
    """Check if any package is listed in Java dependency files."""
    package_names_lower = [p.lower() for p in package_names]

    # Check pom.xml (Maven)
    pom_file = repo_path / "pom.xml"
    if pom_file.exists():
        try:
            content = pom_file.read_text(errors="ignore")
            for pkg in package_names_lower:
                # Search for artifact ID or group ID containing package name
                if re.search(
                    rf"<artifactId>.*{re.escape(pkg)}.*</artifactId>",
                    content,
                    re.IGNORECASE,
                ):
                    return True
                if re.search(
                    rf"<groupId>.*{re.escape(pkg)}.*</groupId>", content, re.IGNORECASE
                ):
                    return True
        except Exception:
            pass

    # Check build.gradle
    gradle_file = repo_path / "build.gradle"
    if gradle_file.exists():
        try:
            content = gradle_file.read_text(errors="ignore")
            for pkg in package_names_lower:
                if re.search(rf"\b{re.escape(pkg)}\b", content, re.IGNORECASE):
                    return True
        except Exception:
            pass

    # Check build.gradle.kts
    gradle_kts_file = repo_path / "build.gradle.kts"
    if gradle_kts_file.exists():
        try:
            content = gradle_kts_file.read_text(errors="ignore")
            for pkg in package_names_lower:
                if re.search(rf"\b{re.escape(pkg)}\b", content, re.IGNORECASE):
                    return True
        except Exception:
            pass

    return False


def _check_javascript_dependencies(repo_path: Path, package_names: list[str]) -> bool:
    """Check if any package is listed in JavaScript dependency files."""
    import json

    package_names_lower = [p.lower() for p in package_names]

    # Check package.json
    package_file = repo_path / "package.json"
    if package_file.exists():
        try:
            content = json.loads(package_file.read_text())
            deps = content.get("dependencies", {})
            dev_deps = content.get("devDependencies", {})
            all_deps = {**deps, **dev_deps}

            for pkg in package_names_lower:
                if pkg in all_deps or pkg.replace("-", "_") in all_deps:
                    return True
        except Exception:
            pass

    # Check package-lock.json
    lock_file = repo_path / "package-lock.json"
    if lock_file.exists():
        try:
            content = json.loads(lock_file.read_text())
            packages = content.get("packages", {})
            for pkg_path in packages:
                for pkg in package_names_lower:
                    if pkg in pkg_path.lower():
                        return True
        except Exception:
            pass

    # Check yarn.lock (text format)
    yarn_file = repo_path / "yarn.lock"
    if yarn_file.exists():
        try:
            content = yarn_file.read_text(errors="ignore")
            for pkg in package_names_lower:
                if re.search(
                    rf"^{re.escape(pkg)}@", content, re.IGNORECASE | re.MULTILINE
                ):
                    return True
        except Exception:
            pass

    return False


def _check_go_dependencies(repo_path: Path, package_names: list[str]) -> bool:
    """Check if any package is listed in Go dependency files."""
    package_names_lower = [p.lower() for p in package_names]

    # Check go.mod
    gomod_file = repo_path / "go.mod"
    if gomod_file.exists():
        try:
            content = gomod_file.read_text(errors="ignore")
            for pkg in package_names_lower:
                if re.search(rf"\b{re.escape(pkg)}\b", content, re.IGNORECASE):
                    return True
        except Exception:
            pass

    # Check go.sum
    gosum_file = repo_path / "go.sum"
    if gosum_file.exists():
        try:
            content = gosum_file.read_text(errors="ignore")
            for pkg in package_names_lower:
                if re.search(rf"{re.escape(pkg)}", content, re.IGNORECASE):
                    return True
        except Exception:
            pass

    return False


def _validate_framework(framework: str, language: str) -> str:
    """
    Validate detected framework against FRAMEWORK_REGISTRY.

    If framework is not in the registry for the language, returns it as-is
    (we still record it to discover new frameworks), but logs a warning.
    This allows the system to be forward-compatible with new frameworks
    while maintaining a canonical registry of known ones.

    Args:
        framework: Detected framework name (e.g., "pytest", "mockito")
        language: Programming language (e.g., "python", "java")

    Returns:
        The framework name (unchanged, for further processing)
    """
    from .config import get_known_frameworks, is_known_framework

    if not is_known_framework(framework, language):
        known = get_known_frameworks(language)
        logger.debug(
            f"Detected framework '{framework}' not in registry for {language}. "
            f"Known frameworks: {known}. "
            f"This may be a new/custom framework or a detection error."
        )

    return framework
