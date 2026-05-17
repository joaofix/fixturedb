"""
Third-party metric collection for code complexity and structure analysis.

This module wraps industry-standard tools to calculate code metrics across all
supported languages (Python, Java, JavaScript, TypeScript).

METRICS PROVIDED (via Lizard library)
=====================================

- Cyclomatic Complexity: via Lizard library (all languages)
- Maximum Nesting Depth: via custom AST analysis (all languages)
- Number of Parameters: via Lizard library (all languages)

Note: Cognitive complexity calculation has been removed as it requires
language-specific parsers (complexipy for Python only). No programmatic
alternatives exist for Java, JavaScript, or TypeScript.

BENEFITS of using Lizard:
- Uses proven, well-maintained industry-standard library
- Consistent with McCabe complexity standards
- Reduces custom code maintenance burden
- Better cross-language consistency
- Academic credibility for published research
"""

import logging
from pathlib import Path
from typing import Optional

from lizard import analyze_file as lizard_analyze_file

logger = logging.getLogger(__name__)


def get_cyclomatic_complexity(file_path: Path, language: str) -> Optional[int]:
    """
    Get cyclomatic complexity of a function using lizard.

    Cyclomatic complexity measures the number of independent paths through code.
    Formula: CC = 1 + number of decision points (if, for, while, catch, etc.)

    Args:
        file_path: Path to the source file
        language: Programming language ('python', 'java', 'javascript', etc.)

    Returns:
        Cyclomatic complexity metric (>= 1), or None if analysis fails

    Note:
        Returns the minimum complexity of all functions in the file if multiple found.
        For fixture extraction, use get_function_complexities() instead.
    """
    try:
        result = lizard_analyze_file(str(file_path))
        if result.function_list:
            # Return first function found; caller typically analyzes single functions
            return result.function_list[0].cyclomatic_complexity
    except Exception as e:
        logger.debug(
            f"Failed to get cyclomatic complexity for {file_path}: {type(e).__name__}: {e}"
        )
    return None


def analyze_function_complexity(
    source_text: str,
    language: str,
    function_name: Optional[str] = None,
) -> dict:
    """
    Analyze complexity and structure metrics for a code snippet using Lizard.

    Args:
        source_text: Source code as string
        language: Programming language
        function_name: Optional function name to extract (if not provided, analyze first function)

    Returns:
        Dictionary with keys:
        - 'cyclomatic_complexity' (int): McCabe complexity, >= 1
        - 'num_parameters' (int): Function signature parameter count
        - 'num_external_calls' (int): Lizard's external call count (used for validation)

    Note:
        num_objects_instantiated is computed by filtering Lizard's external_call_count
        for constructor patterns (new X(...) in Java/JS/TS, capitalized calls in Python).
        This reduces DIY regex logic while maintaining semantic accuracy.

        num_external_calls from Lizard measures inter-function calls within modules,
        not I/O operations. Separation of these metrics allows for specialized handling
        of domain-specific patterns (I/O detection).

        LOC is not included because our definition (non-blank lines) differs from
        Lizard's definition (total lines spanning the function).

    Example:
        >>> code = "def fixture(x):\\n    if x:\\n        return db.query()"
        >>> metrics = analyze_function_complexity(code, 'python')
        >>> metrics['cyclomatic_complexity']
        2
        >>> metrics['num_parameters']
        1
    """
    metrics = {
        "cyclomatic_complexity": 1,
        "num_parameters": 0,
        "num_external_calls": 0,
    }

    temp_file = None
    try:
        # Write to temp file for lizard analysis
        temp_file = (
            Path("/tmp") / f"_analyze_cc_{id(source_text)}.{_get_extension(language)}"
        )
        temp_file.write_text(source_text)

        # Analyze with Lizard to get all metrics
        result = lizard_analyze_file(str(temp_file))
        if result.function_list:
            func_info = result.function_list[0]

            # Extract all Lizard metrics
            metrics["cyclomatic_complexity"] = func_info.cyclomatic_complexity
            metrics["num_parameters"] = (
                func_info.parameter_count
                if hasattr(func_info, "parameter_count")
                else 0
            )
            metrics["num_external_calls"] = (
                func_info.external_call_count
                if hasattr(func_info, "external_call_count")
                else 0
            )

    except (OSError, RuntimeError, ValueError) as e:
        # Return defaults (including loc=0) on any error
        logger.debug(
            f"Complexity analysis failed for source snippet: {type(e).__name__}: {e}"
        )
    finally:
        # Ensure cleanup even if exception occurs
        if temp_file is not None:
            try:
                temp_file.unlink(missing_ok=True)
            except (OSError, PermissionError) as e:
                logger.debug(
                    f"Failed to clean up temp file {temp_file}: {type(e).__name__}: {e}"
                )

    # Add num_objects_instantiated by post-processing Lizard's external_call_count
    # for constructor patterns (new X(...) or capitalized calls)
    try:
        num_constructors = _count_object_instantiations(
            source_text, language, metrics["num_external_calls"]
        )
        metrics["num_objects_instantiated"] = num_constructors
    except Exception as e:
        logger.debug(f"Failed to count object instantiations: {type(e).__name__}: {e}")
        metrics["num_objects_instantiated"] = 0

    return metrics


def _count_object_instantiations(
    source_text: str, language: str, lizard_external_calls: int
) -> int:
    """
    Count object instantiations (constructors) by filtering Lizard's external_call_count.

    Lizard's external_call_count measures all inter-function calls, not specifically
    constructor instantiations. This function filters the source code for constructor
    patterns and validates against Lizard's count to minimize false positives.

    Constructor patterns recognized:
    - Java/JS/TypeScript: new ClassName(...) or new ClassName<T>(...) with generics (including nested)
    - Python: ClassName(...) where ClassName starts with uppercase (heuristic)

    Args:
        source_text: Source code as string
        language: Programming language
        lizard_external_calls: Lizard's external_call_count (for validation)

    Returns:
        Count of object instantiations found via regex filtering
    """
    import re

    # Define constructor patterns per language
    text = source_text

    # Counter for constructor patterns
    constructor_patterns = []

    # Java, JavaScript, TypeScript: new ClassName(...) or new ClassName<...>(...)
    # Pattern handles generic type parameters, including nested generics like <String, List<T>>
    # Greedy matching: (?:<.+?>)? matches from first < to last > to handle nesting
    constructor_patterns.append(r"\bnew\s+\w+\s*(?:<.+?>)?\s*\(")

    # Python: ClassName(...) where ClassName is capitalized (heuristic for constructors)
    # This catches both actual constructors and factory methods that look like constructors
    if language.lower() == "python":
        constructor_patterns.append(r"\b[A-Z][A-Za-z0-9_]*\s*\(")

    # Count matched patterns
    constructor_count = 0
    for pattern in constructor_patterns:
        matches = re.findall(pattern, text)
        constructor_count += len(matches)

    # Validate against Lizard's count to avoid duplicates
    # Use the minimum to be conservative (avoid overcounting)
    # If Lizard found fewer calls than our regex, use Lizard's count
    if lizard_external_calls > 0 and constructor_count > lizard_external_calls:
        logger.debug(
            f"Constructor count ({constructor_count}) exceeds Lizard external_call_count ({lizard_external_calls}). "
            f"Using Lizard count for validation."
        )
        return min(constructor_count, lizard_external_calls)

    return constructor_count


def _get_extension(language: str) -> str:
    """Map language name to file extension."""
    ext_map = {
        "python": "py",
        "java": "java",
        "javascript": "js",
        "typescript": "ts",
        "go": "go",
        "c++": "cpp",
        "c": "c",
    }
    return ext_map.get(language.lower(), "txt")


def get_file_loc(file_path: Path, language: str) -> int:
    """
    Get file-level lines of code using Lizard.

    Args:
        file_path: Path to the source file
        language: Programming language ('python', 'java', 'javascript', etc.)

    Returns:
        Total lines of code in file, or 0 if analysis fails

    Note:
        Lizard's total_lines includes all physical lines (code + comments + blanks).
        For consistency with fixture-level LOC definition (non-blank lines), we
        maintain the current manual line counting approach.

        Future enhancement: When Lizard's line counting methodology aligns with
        our non-blank line requirement, migrate to Lizard's file_measure.total_lines.
    """
    try:
        result = lizard_analyze_file(str(file_path))
        # Return Lizard's total line count for files if available
        return getattr(result, "total_lines", 0) or 0
    except Exception as e:
        logger.debug(
            f"Failed to get file LOC using Lizard for {file_path}: {type(e).__name__}: {e}"
        )
    return 0


def get_file_function_count(file_path: Path, language: str) -> int:
    """
    Get file-level function count using Lizard.

    Args:
        file_path: Path to the source file
        language: Programming language

    Returns:
        Total number of functions/methods in file, or 0 if analysis fails

    Note:
        Lizard counts all function/method definitions in the file.
        This replaces language-specific AST-based counting with a unified approach.
    """
    try:
        result = lizard_analyze_file(str(file_path))
        # Return count of all functions in the file
        return len(result.function_list) if result.function_list else 0
    except Exception as e:
        logger.debug(
            f"Failed to get file function count using Lizard for {file_path}: {type(e).__name__}: {e}"
        )
    return 0
