"""Focused tests for agent repository/config detection logic."""

from pathlib import Path

from collection.agent_patterns import scan_cloned_repo_for_agent_configs
from collection.agent_signal_primitives import GitHubAgentFileChecker


def _make_repo(tmp_path: Path, repo_name: str = "owner__repo") -> Path:
    repo_root = tmp_path / "clones"
    repo_root.mkdir()
    repo_path = repo_root / repo_name
    repo_path.mkdir()
    return repo_path


def test_scan_cloned_repo_for_agent_configs_is_case_insensitive(tmp_path):
    repo_path = _make_repo(tmp_path)
    (repo_path / "CLAUDE.MD").write_text("# Claude instructions\n")

    assert scan_cloned_repo_for_agent_configs(repo_path) is not None


def test_scan_cloned_repo_for_agent_configs_matches_copilot_wildcard(tmp_path):
    repo_path = _make_repo(tmp_path)
    (repo_path / ".copilot-SETUP.md").write_text("# Copilot\n")

    assert scan_cloned_repo_for_agent_configs(repo_path) is not None


def test_scan_cloned_repo_for_agent_configs_matches_nested_directory(tmp_path):
    repo_path = _make_repo(tmp_path)
    nested = repo_path / ".anthropic"
    nested.mkdir()
    (nested / "README.md").write_text("# Anthropic\n")

    assert scan_cloned_repo_for_agent_configs(repo_path) is not None


def test_github_api_checker_recurses_one_level_for_nested_configs(monkeypatch):
    checker = GitHubAgentFileChecker()

    responses = {
        ("owner/repo", ""): [
            {"name": "docs", "path": "docs", "type": "dir"},
        ],
        ("owner/repo", "docs"): [
            {"name": "CLAUDE.MD", "path": "docs/CLAUDE.MD", "type": "file"},
        ],
    }

    def fake_get_repo_contents(full_repo_name, path="", ref="HEAD", timeout=5):
        return responses.get((full_repo_name, path), [])

    monkeypatch.setattr(checker, "_get_repo_contents", fake_get_repo_contents)

    has_files, found = checker.has_agent_config_files("owner/repo")

    assert has_files is True
    assert any("CLAUDE" in item.upper() for item in found)


def test_get_repo_contents_parses_directory_listing(monkeypatch):
    """Direct test of _get_repo_contents() against a mocked requests.Response,
    covering the real HTTP-call implementation (not monkeypatched away, as
    the test above does for has_agent_config_files)."""
    checker = GitHubAgentFileChecker()

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return [{"name": "CLAUDE.md", "path": "CLAUDE.md", "type": "file"}]

    captured = {}

    def fake_get(url, headers=None, params=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        return FakeResponse()

    import requests

    monkeypatch.setattr(requests, "get", fake_get)

    result = checker._get_repo_contents("owner/repo")

    assert result == [{"name": "CLAUDE.md", "path": "CLAUDE.md", "type": "file"}]
    assert captured["url"] == "https://api.github.com/repos/owner/repo/contents/"
    assert captured["params"] is None


def test_get_repo_contents_returns_none_on_404(monkeypatch):
    checker = GitHubAgentFileChecker()

    class FakeResponse:
        status_code = 404

        def raise_for_status(self):
            import requests

            error = requests.HTTPError("404")
            error.response = self
            raise error

        def json(self):
            return {}

    import requests

    monkeypatch.setattr(requests, "get", lambda *a, **kw: FakeResponse())

    result = checker._get_repo_contents("owner/missing-repo")

    assert result is None


class _FakeRateLimitedResponse:
    def __init__(self, status_code, remaining="0", retry_after=None):
        self.status_code = status_code
        self.headers = {"X-RateLimit-Remaining": remaining}
        if retry_after is not None:
            self.headers["Retry-After"] = retry_after

    def raise_for_status(self):
        import requests

        error = requests.HTTPError(str(self.status_code))
        error.response = self
        raise error

    def json(self):
        return {}


def _make_rate_limited_response(status_code, remaining="0", retry_after=None):
    return _FakeRateLimitedResponse(status_code, remaining=remaining, retry_after=retry_after)


def test_get_repo_contents_retries_on_rate_limit_then_succeeds(monkeypatch):
    """Regression: a 403 (X-RateLimit-Remaining: 0) or 429 response was
    treated identically to a genuine 404 -- returned None immediately, no
    retry -- which has_agent_config_files() then silently records as
    "verified: no agent config files," permanently dropping a repo from the
    Tier 2 candidate pool just because the scan happened to hit a rate
    limit, indistinguishable from a real negative."""
    checker = GitHubAgentFileChecker()

    class FakeSuccessResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return [{"name": "CLAUDE.md", "path": "CLAUDE.md", "type": "file"}]

    responses = [
        _make_rate_limited_response(429),
        FakeSuccessResponse(),
    ]

    import requests

    sleep_calls = []
    monkeypatch.setattr(requests, "get", lambda *a, **kw: responses.pop(0))
    monkeypatch.setattr(
        "collection.agent_signal_primitives.time.sleep",
        lambda s: sleep_calls.append(s),
    )

    result = checker._get_repo_contents("owner/repo")

    assert result == [{"name": "CLAUDE.md", "path": "CLAUDE.md", "type": "file"}]
    assert len(sleep_calls) == 1


def test_get_repo_contents_returns_none_after_exhausting_rate_limit_retries(
    monkeypatch,
):
    checker = GitHubAgentFileChecker()

    import requests

    monkeypatch.setattr(
        requests, "get", lambda *a, **kw: _make_rate_limited_response(403)
    )
    monkeypatch.setattr(
        "collection.agent_signal_primitives.time.sleep", lambda s: None
    )

    result = checker._get_repo_contents("owner/repo", max_retries=2)

    assert result is None


def test_get_repo_contents_does_not_retry_on_403_private_repo(monkeypatch):
    """A 403 WITHOUT X-RateLimit-Remaining: 0 means private/blocked, not
    rate-limited -- must not be retried (retrying a permission denial is
    pointless and would just slow the scan down for no benefit)."""
    checker = GitHubAgentFileChecker()

    import requests

    sleep_calls = []
    monkeypatch.setattr(
        requests,
        "get",
        lambda *a, **kw: _make_rate_limited_response(403, remaining="42"),
    )
    monkeypatch.setattr(
        "collection.agent_signal_primitives.time.sleep",
        lambda s: sleep_calls.append(s),
    )

    result = checker._get_repo_contents("owner/private-repo")

    assert result is None
    assert sleep_calls == []
