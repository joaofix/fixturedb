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

Object instantiation (`num_objects_instantiated`) used to be computed here
too, as a regex-filtered post-processing pass over Lizard's own
external_call_count. It's been moved to detector_shared.py's
`_count_object_instantiations()` -- a proper tree-sitter AST walk (`new
X(...)`'s dedicated node type in Java/JS/TS; a capitalized-target `call`
node in Python) run against the fixture's already-parsed node, not a
second regex pass over its raw text. See internal-docs/methodology-
improvements/num-objects-instantiated-false-positive-rate.md for why:
the regex approach counted matches inside string literals/comments (e.g.
SQL embedded in a fixture body, or a fixture's own capitalized name
self-matching its `def NAME(...):` line) as if they were real code.
"""

from pathlib import Path
from typing import Optional

from lizard import analyze_file as lizard_analyze_file

from collection.logging_utils import get_logger

logger = get_logger(__name__)


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

    Note:
        LOC is not included because our definition (non-blank lines) differs from
        Lizard's definition (total lines spanning the function).

        num_objects_instantiated is NOT computed here -- see this module's
        docstring for why (it's an AST walk in detector_shared.py now, not
        a Lizard-adjacent metric). Lizard's own external_call_count isn't
        returned either: it was only ever read here to validate/cap the
        old regex-based object-instantiation count, which no longer exists.

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

    return metrics


def _get_extension(language: str) -> str:
    """Map language name to file extension."""
    ext_map = {
        "python": "py",
        "java": "java",
        "javascript": "js",
        "typescript": "ts",
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
