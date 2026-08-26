"""Tests for persistent_clone.py's _has_sufficient_test_files() -- the
pre-clone GitHub code-search API screen for MIN_TEST_FILES. Previously
untested: every branch (enough matches, too few, unsearchable repo, rate
limit / other error status, network failure) ran unexercised in production.

It fails open (returns True) on anything other than a confident "not
enough files" 200 response -- a false skip here discards a repo entirely
before it's ever cloned, which is worse than the wasted clone a false
positive would cost.
"""

from __future__ import annotations

import requests

from collection import persistent_clone
from collection.persistent_clone import _has_sufficient_test_files


class _FakeResponse:
    def __init__(self, status_code: int, json_data: dict | None = None):
        self.status_code = status_code
        self._json_data = json_data or {}

    def json(self) -> dict:
        return self._json_data


def test_language_without_test_path_patterns_skips_the_api_call_entirely(monkeypatch):
    calls = []

    def fake_get(*args, **kwargs):
        calls.append((args, kwargs))
        return _FakeResponse(200, {"total_count": 0})

    monkeypatch.setattr(requests, "get", fake_get)

    assert _has_sufficient_test_files("o/r", "not-a-real-language") is True
    assert calls == []


def test_enough_matches_returns_true(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: _FakeResponse(200, {"total_count": 10}))
    assert _has_sufficient_test_files("o/r", "python") is True


def test_too_few_matches_returns_false(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: _FakeResponse(200, {"total_count": 2}))
    assert _has_sufficient_test_files("o/r", "python") is False


def test_missing_total_count_key_defaults_to_zero_and_returns_false(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: _FakeResponse(200, {}))
    assert _has_sufficient_test_files("o/r", "python") is False


def test_422_unsearchable_repo_fails_open(monkeypatch):
    """422 means GitHub couldn't run the search at all (e.g. a repo too
    large to index) -- not evidence the repo lacks test files, so this must
    not cause a skip."""
    monkeypatch.setattr(requests, "get", lambda *a, **k: _FakeResponse(422))
    assert _has_sufficient_test_files("o/r", "python") is True


def test_rate_limited_or_other_error_status_fails_open(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: _FakeResponse(403))
    assert _has_sufficient_test_files("o/r", "python") is True


def test_network_failure_fails_open(monkeypatch):
    def raise_connection_error(*args, **kwargs):
        raise requests.exceptions.ConnectionError("boom")

    monkeypatch.setattr(requests, "get", raise_connection_error)
    assert _has_sufficient_test_files("o/r", "python") is True


def test_timeout_fails_open(monkeypatch):
    def raise_timeout(*args, **kwargs):
        raise requests.exceptions.Timeout("boom")

    monkeypatch.setattr(requests, "get", raise_timeout)
    assert _has_sufficient_test_files("o/r", "python") is True


def test_query_scopes_to_repo_and_uses_at_most_three_path_patterns(monkeypatch):
    captured = {}

    def fake_get(url, headers=None, params=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        captured["timeout"] = timeout
        return _FakeResponse(200, {"total_count": 10})

    monkeypatch.setattr(requests, "get", fake_get)
    _has_sufficient_test_files("owner/repo", "python")

    assert captured["url"] == "https://api.github.com/search/code"
    assert captured["params"]["per_page"] == "1"
    query = captured["params"]["q"]
    assert query.startswith("repo:owner/repo (")
    patterns = persistent_clone.LANGUAGE_CONFIGS["python"].test_path_patterns[:3]
    for pattern in patterns:
        assert f"path:{pattern}" in query
    assert query.count("path:") == len(patterns)


def test_authorization_header_included_only_when_token_configured(monkeypatch):
    captured = {}

    def fake_get(url, headers=None, params=None, timeout=None):
        captured["headers"] = headers
        return _FakeResponse(200, {"total_count": 10})

    monkeypatch.setattr(requests, "get", fake_get)

    monkeypatch.setattr(persistent_clone, "GITHUB_TOKEN", "secret-token")
    _has_sufficient_test_files("o/r", "python")
    assert captured["headers"]["Authorization"] == "Bearer secret-token"

    monkeypatch.setattr(persistent_clone, "GITHUB_TOKEN", None)
    _has_sufficient_test_files("o/r", "python")
    assert "Authorization" not in captured["headers"]
