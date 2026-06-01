"""Lightweight AST parse cache to reuse parsed trees for identical file contents.

This module provides `parse_bytes(src_bytes, language)` which returns a
Tree-sitter `Tree` object for the given source bytes and language. It uses
an in-memory LRU cache keyed by a content hash to avoid reparsing unchanged
files during bulk extraction.
"""

import hashlib
from functools import lru_cache
from typing import Any

# Import parser factory lazily to avoid circular imports with detector


def _content_hash(src_bytes: bytes) -> str:
    return hashlib.sha1(src_bytes).hexdigest()


@lru_cache(maxsize=2048)
def _parse_by_hash(content_hash: str, src_bytes: bytes, language: str) -> Any:
    from .detector import _get_parser

    parser = _get_parser(language)
    return parser.parse(src_bytes)


def parse_bytes(src_bytes: bytes, language: str):
    """Return a parsed tree for the given source bytes and language.

    Uses an in-memory LRU cache to avoid reparsing identical file contents.
    """
    h = _content_hash(src_bytes)
    return _parse_by_hash(h, src_bytes, language)
