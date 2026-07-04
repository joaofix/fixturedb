"""Shared file-extension-to-language mapping used across the collection pipeline."""

from pathlib import Path


def get_language_static(file_path: Path) -> str:
    """Infer language from file extension (module-level, no instance needed)."""
    ext = file_path.suffix.lower()
    return {
        ".py": "python",
        ".java": "java",
        ".js": "javascript",
        ".jsx": "javascript",
        ".mjs": "javascript",
        ".cjs": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".mts": "typescript",
        ".cts": "typescript",
    }.get(ext, "unknown")
