"""
Extraction orchestrator.

Walks every 'cloned' repository, identifies test files, runs the AST
detector, and writes fixtures + mock usages to the database.

After successful extraction the repo status is updated to 'analysed'.
After extraction the local clone is deleted to reclaim disk space.
"""

import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from collection.config import (
    LANGUAGE_CONFIGS,
    MIN_FIXTURES_FOUND,
    EXTRACT_WORKERS,
    FILE_EXTRACTION_TIMEOUT,
    FILE_SIZE_WARN_MB,
    MAX_FILE_SIZE_BYTES,
    NON_CODE_EXTENSIONS,
)
from collection.cloner import get_clone_path, delete_clone
from collection.db import (
    db_session,
    get_repos_by_status,
    set_repo_status,
    set_repo_analysed,
    upsert_test_file,
    update_test_file_counts,
    insert_fixture,
    insert_mock_usage,
    get_corpus_stats,
    get_analyzed_count_for_language,
)
from collection.detector import extract_fixtures

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Language-specific file extensions
# ---------------------------------------------------------------------------

LANGUAGE_EXTENSIONS = {
    "python": {".py"},
    "java": {".java"},
    "javascript": {".js", ".jsx", ".mjs", ".cjs"},
    "typescript": {".ts", ".tsx"},
    "go": {".go"},
}


def should_process_file(file_path: Path, repo_language: str) -> bool:
    """
    Validate that file extension matches the repository language.

    Skips files with mismatched extensions (e.g., Kotlin in TypeScript repo).
    Unknown languages are processed (safe fallback).

    Args:
        file_path: Path to the file
        repo_language: Repository language (python/java/javascript/typescript/go)

    Returns:
        True if file should be processed, False if extension mismatch
    """
    if repo_language not in LANGUAGE_EXTENSIONS:
        return True  # Unknown language - process anyway

    ext = file_path.suffix.lower()
    return ext in LANGUAGE_EXTENSIONS[repo_language]


# ---------------------------------------------------------------------------
# Timeout handler for long-running file extraction
# ---------------------------------------------------------------------------


class ExtractionTimeoutError(Exception):
    """Raised when file extraction exceeds the timeout."""

    pass


def extract_fixtures_with_timeout(
    tf_path: Path, language: str, timeout: int = FILE_EXTRACTION_TIMEOUT
):
    """
    Extract fixtures from a test file with a timeout.

    TIMEOUT STRATEGY
    ================

    Tree-sitter AST parsing can hang indefinitely on certain malformed or
    pathological code patterns. Two failure modes seen in practice:

    1. **Parser bugs**: Some language grammars have infinite loops on
       corner cases (e.g., deeply nested parentheses, unusual token sequences)
    2. **Exotic/synthetic code**: Generated test data, decompiled code, or
       intentionally obfuscated code can trigger exponential backtracking

    Timeout prevents:
    - A single pathological file from blocking the entire extraction phase
    - Memory exhaustion from pathological inputs
    - Worker threads hanging indefinitely (requires ThreadPoolExecutor)

    Uses ThreadPoolExecutor to run extraction in a separate thread, allowing
    timeout enforcement even when called from existing worker threads. On
    timeout, returns empty ExtractResult to mark the file as skipped.

    Args:
        tf_path: Path to the test file
        language: Programming language
        timeout: Maximum seconds to spend on this file (default: 5s from config)

    Returns:
        ExtractResult with fixtures and file-level metrics

    Raises:
        ExtractionTimeoutError: If extraction takes longer than timeout
    """
    from concurrent.futures import (
        ThreadPoolExecutor,
        TimeoutError as FuturesTimeoutError,
    )
    from collection.detector import ExtractResult

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(extract_fixtures, tf_path, language)
            return future.result(timeout=timeout)
    except FuturesTimeoutError:
        raise ExtractionTimeoutError(f"File extraction exceeded {timeout}s timeout")


# ---------------------------------------------------------------------------
# Test file discovery
# ---------------------------------------------------------------------------


def _find_test_files(repo_dir: Path, language: str) -> list[Path]:
    """
    Return all files in repo_dir that match the language's test file
    naming conventions. Excludes vendor / third-party directories.
    """
    config = LANGUAGE_CONFIGS.get(language)
    if config is None:
        return []

    SKIP_DIRS = {
        "vendor",
        "node_modules",
        ".git",
        "dist",
        "build",
        "target",
        ".gradle",
        "__pycache__",
        ".tox",
        "venv",
        ".venv",
        "site-packages",
        "third_party",
        "third-party",
        "resources",
        "resource",  # test resource data directories
    }

    test_files: list[Path] = []

    for path in repo_dir.rglob("*"):
        # Skip excluded directories anywhere in the path
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if not path.is_file():
            continue

        name = path.name.lower()
        rel = str(path.relative_to(repo_dir))

        # Skip files with no extension (typically data/resource files)
        if "." not in name:
            continue

        # Skip non-source-code files
        if any(name.endswith(ext) for ext in NON_CODE_EXTENSIONS):
            continue

        matched = False
        name_lower = name.lower()
        
        # Check file suffix patterns (handles prefix patterns like "test_", suffix patterns like "_test.py", and full names like "conftest.py")
        for pat in config.test_file_suffixes:
            pat_lower = pat.lower()
            if pat_lower.startswith("test_"):
                # Prefix pattern like "test_.py" - match files starting with "test_" and ending with extension
                if name_lower.startswith("test_") and name_lower.endswith(pat_lower.split("test_")[1]):
                    matched = True
                    break
            elif pat_lower == "conftest.py":
                # Exact filename match
                if name_lower == "conftest.py":
                    matched = True
                    break
            else:
                # Suffix patterns (like ".test.js", "_test.py", "Test.java", "IT.java", "Spec.java")
                # Check if filename ends with this pattern (case-insensitive)
                if name_lower.endswith(pat_lower):
                    matched = True
                    break
        
        if not matched:
            # Match path patterns with proper boundary checking
            # Directory patterns should match complete path components only
            rel_lower = rel.lower()
            rel_parts = rel_lower.split("/")
            for pat in config.test_path_patterns:
                pat_lower = pat.lower()
                # All test_path_patterns end with "/" by design
                if pat_lower.endswith("/"):
                    dir_pattern = pat_lower.rstrip("/")
                    # Check if the directory pattern appears as a complete path component
                    if dir_pattern in rel_parts:
                        matched = True
                        break

        if matched:
            # Skip files larger than MAX_FILE_SIZE_BYTES (likely not real test files)
            try:
                if path.stat().st_size > MAX_FILE_SIZE_BYTES:
                    continue
            except OSError:
                # Can't stat, skip to be safe
                continue
            test_files.append(path)

    return test_files


# ---------------------------------------------------------------------------
# Single-repo extraction
# ---------------------------------------------------------------------------


def extract_repo(repo_id: int, full_name: str, language: str) -> dict:
    """
    Extract fixtures from a single cloned repository.
    Returns a summary dict with counts.
    """
    repo_dir = get_clone_path(full_name)
    if not repo_dir.exists():
        logger.error(f"[extract] Clone not found for {full_name}")
        with db_session() as conn:
            set_repo_status(conn, repo_id, "error", "clone directory missing")
        return {}

    test_files = _find_test_files(repo_dir, language)
    num_test_files = len(test_files)
    logger.info(f"[extract] {full_name}: {num_test_files} test files found")

    # Calculate and log total test file size for this repo
    total_test_size_bytes = 0
    largest_file_mb = 0
    try:
        for tf_path in test_files:
            file_size = tf_path.stat().st_size
            total_test_size_bytes += file_size
            largest_file_mb = max(largest_file_mb, file_size / (1024 * 1024))

        total_test_size_mb = total_test_size_bytes / (1024 * 1024)
        logger.info(
            f"[extract] {full_name}: Total test file size = {total_test_size_mb:.2f} MB, Largest = {largest_file_mb:.2f} MB"
        )
    except Exception as e:
        logger.debug(f"Could not calculate file sizes for {full_name}: {e}")

    total_fixtures = 0
    total_mocks = 0

    for tf_path in test_files:
        relative = str(tf_path.relative_to(repo_dir))

        # Validate file extension matches repository language
        if not should_process_file(tf_path, language):
            continue

        # Log file size before processing
        try:
            file_size_bytes = tf_path.stat().st_size
            file_size_mb = file_size_bytes / (1024 * 1024)
            # info(f"[extract] Processing test file: {relative} ({file_size_mb:.2f} MB)")
            if file_size_mb > FILE_SIZE_WARN_MB:
                logger.warning(
                    f"[extract] Large test file in {full_name}: {relative} is {file_size_mb:.2f} MB"
                )
        except Exception as e:
            logger.debug(f"Could not get file size for {relative}: {e}")

        # Register the test file in DB
        with db_session() as conn:
            file_id = upsert_test_file(conn, repo_id, relative, language)

        # Extract fixtures with timeout protection
        try:
            extract_result = extract_fixtures_with_timeout(tf_path, language)
        except ExtractionTimeoutError:
            logger.warning(
                f"[extract] ⏱ Timeout for {full_name}/{relative}: "
                f"extraction exceeded {FILE_EXTRACTION_TIMEOUT}s limit, skipping file"
            )
            extract_result = None

        if extract_result is None:
            fixtures = []
            file_loc = 0
            num_test_functions = 0
            total_fixture_loc = 0
        else:
            fixtures = extract_result.fixtures
            file_loc = extract_result.file_loc
            num_test_functions = extract_result.num_test_functions
            total_fixture_loc = sum(f.loc for f in fixtures)

        file_fixture_count = len(fixtures)
        file_test_count = (
            num_test_functions  # Use the extracted count instead of estimate
        )

        with db_session() as conn:
            update_test_file_counts(
                conn,
                file_id,
                file_test_count,
                file_fixture_count,
                file_loc=file_loc,
                total_fixture_loc=total_fixture_loc,
            )

            for fix in fixtures:
                fixture_record = {
                    "file_id": file_id,
                    "repo_id": repo_id,
                    "name": fix.name,
                    "fixture_type": fix.fixture_type,
                    "framework": fix.framework,
                    "scope": fix.scope,
                    "start_line": fix.start_line,
                    "end_line": fix.end_line,
                    "loc": fix.loc,
                    "cyclomatic_complexity": fix.cyclomatic_complexity,
                    "max_nesting_depth": fix.max_nesting_depth,
                    "num_objects_instantiated": fix.num_objects_instantiated,
                    "num_external_calls": fix.num_external_calls,
                    "num_parameters": fix.num_parameters,
                    "reuse_count": fix.reuse_count,
                    "has_teardown_pair": fix.has_teardown_pair,
                    "raw_source": fix.raw_source,
                    "num_mocks": len(fix.mocks),
                }
                fixture_id = insert_fixture(conn, fixture_record)

                for mock in fix.mocks:
                    mock_record = {
                        "fixture_id": fixture_id,
                        "repo_id": repo_id,
                        "framework": mock.framework,
                        "target_identifier": mock.target_identifier,
                        "num_interactions_configured": mock.num_interactions_configured,
                        "raw_snippet": mock.raw_snippet,
                    }
                    insert_mock_usage(conn, mock_record)
                    total_mocks += 1

        total_fixtures += file_fixture_count

    # Apply the minimum-fixtures quality filter
    if total_fixtures < MIN_FIXTURES_FOUND:
        logger.info(
            f"[extract] Skip {full_name}: "
            f"only {total_fixtures} fixtures found (threshold: {MIN_FIXTURES_FOUND})"
        )
        with db_session() as conn:
            set_repo_analysed(
                conn, repo_id, num_test_files, total_fixtures, total_mocks
            )
            # Also update status to skipped with reason
            set_repo_status(
                conn,
                repo_id,
                "skipped",
                skip_reason=f"insufficient fixtures ({total_fixtures} < {MIN_FIXTURES_FOUND})",
            )
        delete_clone(full_name)
        return {"fixtures": 0, "mocks": 0}

    with db_session() as conn:
        set_repo_analysed(conn, repo_id, num_test_files, total_fixtures, total_mocks)

    delete_clone(full_name)

    logger.info(
        f"[extract] ✓ {full_name}: "
        f"{num_test_files} test files, {total_fixtures} fixtures, {total_mocks} mock usages"
    )
    return {"fixtures": total_fixtures, "mocks": total_mocks}


# ---------------------------------------------------------------------------
# Test function count estimator (lightweight, no full parse needed)
# ---------------------------------------------------------------------------

import re

TEST_FUNC_PATTERNS = {
    "python": re.compile(r"^\s*def\s+test_", re.MULTILINE),
    "java": re.compile(r"@Test\b"),
    "javascript": re.compile(r"\bit\s*\(|\btest\s*\("),
    "typescript": re.compile(r"\bit\s*\(|\btest\s*\("),
    "go": re.compile(r"^func\s+Test[A-Z]", re.MULTILINE),
}


def _estimate_test_count(file_path: Path, language: str) -> int:
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
        pattern = TEST_FUNC_PATTERNS.get(language)
        if pattern:
            return len(pattern.findall(text))
    except Exception:
        pass
    return 0


# ---------------------------------------------------------------------------
# Batch extraction
# ---------------------------------------------------------------------------


def extract_all_cloned(
    language: str | None = None,
    target_analyzed: int | None = None,
    target_per_language: int | None = None,
    target_per_language_dict: dict[str, int] | None = None,
) -> dict:
    """
    Extract fixtures from repos in 'cloned' status using parallel workers.

    Extraction uses round-robin ordering across creation year buckets to maintain
    temporal balance during the extraction phase (independent of discovery strategy).

    If target_analyzed is set, stop early when global target is reached.
    If target_per_language is set, stop early when each language reaches that count.
    If target_per_language_dict is set, stop early when each language reaches its specific count.

    Args:
        language: Filter to specific language (or None for all)
        target_analyzed: Optional global target count; stop when reached
        target_per_language: Optional per-language target; stop when each language reaches this count
        target_per_language_dict: Optional dict mapping language names to their specific target counts

    Returns:
        dict with extraction summary and 'early_stopped' flag
    """
    with db_session() as conn:
        # If using per-language targets, get current counts to skip already-satisfied languages
        languages_to_skip = set()
        if target_per_language or target_per_language_dict:
            from collection.config import LANGUAGE_CONFIGS

            cursor = conn.execute("""
                SELECT language, COUNT(DISTINCT r.id) as count
                FROM repositories r
                WHERE r.status = 'analysed' AND EXISTS (SELECT 1 FROM fixtures WHERE repo_id = r.id)
                GROUP BY language
            """)
            lang_counts = {row["language"]: row["count"] for row in cursor.fetchall()}
            
            if target_per_language_dict:
                languages_to_skip = {
                    lang
                    for lang in LANGUAGE_CONFIGS.keys()
                    if lang_counts.get(lang, 0) >= target_per_language_dict.get(lang, 0)
                }
            else:
                languages_to_skip = {
                    lang
                    for lang in LANGUAGE_CONFIGS.keys()
                    if lang_counts.get(lang, 0) >= target_per_language
                }
            
            if languages_to_skip:
                logger.info(
                    f"Skipping extraction for languages already at target: {languages_to_skip}"
                )

        # Fetch all cloned repos grouped by creation year (for stratified extraction)
        cursor = conn.execute("""
            SELECT 
                r.id, r.full_name, r.language,
                STRFTIME('%Y', r.created_at) as year
            FROM repositories r
            WHERE r.status = 'cloned'
            ORDER BY STRFTIME('%Y', r.created_at), r.id
            """)
        rows = cursor.fetchall()

        if language:
            rows = [r for r in rows if r["language"] == language]

        # Filter out repos from languages that have already reached their target
        if languages_to_skip:
            rows = [r for r in rows if r["language"] not in languages_to_skip]

    if not rows:
        logger.info("No cloned repos to extract.")
        return {"fixtures": 0, "mocks": 0, "early_stopped": False}

    # Group repos by creation year for round-robin extraction order
    by_year = {}
    for row in rows:
        year = row["year"]
        if year not in by_year:
            by_year[year] = []
        by_year[year].append(row)

    # Build extraction queue in round-robin order across years (balance extraction across time)
    extraction_queue = []
    max_year_count = max(len(v) for v in by_year.values())
    for i in range(max_year_count):
        for year in sorted(by_year.keys()):
            if i < len(by_year[year]):
                extraction_queue.append(by_year[year][i])

    logger.info(
        f"Extracting {len(extraction_queue)} repos with {EXTRACT_WORKERS} workers "
        f"(round-robin across {len(by_year)} creation years) …"
    )
    if target_analyzed:
        logger.info(f"Will stop early when {target_analyzed} analyzed repos reached")
    if target_per_language:
        logger.info(
            f"Will stop early when each language reaches {target_per_language} analyzed repos"
        )
    if target_per_language_dict:
        logger.info(
            f"Will stop early when each language reaches its target: {target_per_language_dict}"
        )

    totals: dict[str, int] = {"fixtures": 0, "mocks": 0}
    early_stopped = False

    with ThreadPoolExecutor(max_workers=EXTRACT_WORKERS) as executor:
        # Submit all jobs but track which ones to process
        futures = {
            executor.submit(
                extract_repo,
                row["id"],
                row["full_name"],
                row["language"],
            ): row
            for row in extraction_queue
        }

        for future in as_completed(futures):
            summary = future.result()
            for k, v in summary.items():
                totals[k] = totals.get(k, 0) + v

            # Check if we've reached target (early stop)
            should_stop = False

            if target_analyzed:
                with db_session() as conn:
                    if language:
                        analyzed = get_analyzed_count_for_language(conn, language)
                    else:
                        cursor = conn.execute(
                            "SELECT COUNT(DISTINCT r.id) as n FROM repositories r "
                            "WHERE r.status = 'analysed' AND EXISTS (SELECT 1 FROM fixtures WHERE repo_id = r.id)"
                        )
                        analyzed = cursor.fetchone()["n"]

                if analyzed >= target_analyzed:
                    logger.info(
                        f"Target reached ({analyzed} analyzed). Stopping extraction early."
                    )
                    should_stop = True

            if target_per_language and not should_stop:
                with db_session() as conn:
                    # Check per-language analyzed counts
                    cursor = conn.execute("""
                        SELECT language, COUNT(DISTINCT r.id) as count
                        FROM repositories r
                        WHERE r.status = 'analysed' AND EXISTS (SELECT 1 FROM fixtures WHERE repo_id = r.id)
                        GROUP BY language
                    """)
                    lang_counts = {
                        row["language"]: row["count"] for row in cursor.fetchall()
                    }

                    # Check if all languages have reached their target
                    from collection.config import LANGUAGE_CONFIGS

                    all_reached = all(
                        lang_counts.get(lang, 0) >= target_per_language
                        for lang in LANGUAGE_CONFIGS.keys()
                    )

                    if all_reached:
                        logger.info(
                            f"Per-language targets reached: {lang_counts}. Stopping extraction early."
                        )
                        should_stop = True

            if target_per_language_dict and not should_stop:
                with db_session() as conn:
                    # Check per-language analyzed counts
                    cursor = conn.execute("""
                        SELECT language, COUNT(DISTINCT r.id) as count
                        FROM repositories r
                        WHERE r.status = 'analysed' AND EXISTS (SELECT 1 FROM fixtures WHERE repo_id = r.id)
                        GROUP BY language
                    """)
                    lang_counts = {
                        row["language"]: row["count"] for row in cursor.fetchall()
                    }

                    # Check if all languages have reached their specific targets
                    all_reached = all(
                        lang_counts.get(lang, 0) >= target_per_language_dict.get(lang, 0)
                        for lang in target_per_language_dict.keys()
                    )

                    if all_reached:
                        logger.info(
                            f"Per-language targets reached: {lang_counts}. Stopping extraction early."
                        )
                        should_stop = True

            if should_stop:
                executor.shutdown(wait=False, cancel_futures=True)
                early_stopped = True
                break

    with db_session() as conn:
        stats = get_corpus_stats(conn)

    logger.info(
        f"Extraction complete (early_stopped={early_stopped}). Corpus stats: {stats}"
    )
    totals["early_stopped"] = early_stopped
    return totals
