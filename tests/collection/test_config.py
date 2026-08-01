"""Tests for small pure helpers in collection/config.py."""

from __future__ import annotations

from collection.config import SHALLOW_CLONE_BUFFER_DAYS, shallow_clone_since


def test_shallow_clone_since_subtracts_the_configured_buffer():
    # SHALLOW_CLONE_BUFFER_DAYS is study-parameter-driven; derive the expected
    # date from it rather than hardcoding "7" so this doesn't silently rot if
    # the buffer is retuned later.
    from datetime import date, timedelta

    since = "2025-06-15"
    expected = (
        date.fromisoformat(since) - timedelta(days=SHALLOW_CLONE_BUFFER_DAYS)
    ).isoformat()
    assert shallow_clone_since(since) == expected


def test_shallow_clone_since_crosses_a_year_boundary():
    assert shallow_clone_since("2025-01-01") == "2024-12-25"


def test_shallow_clone_since_crosses_a_month_boundary():
    assert shallow_clone_since("2025-03-03") == "2025-02-24"
