"""Tests for collection/rq5_agent_file_scan.py.

Same standard as tests/collection/test_rq1_prevalence_scan.py: this scan
runs exactly once over ~24.7k repos, so every piece of real business logic
(keyword-pattern construction, per-line matching + code-fence tracking,
case-insensitive root-file matching, API response handling, rate-limit
retry, DB upsert/resume, CSV output) is exercised directly. Unlike the
first version of this module (which cloned every repo), there is no git/
network dependency to work around here at all -- every GitHub REST call
goes through `requests.get`, which is mocked throughout this file via real
`requests.Response` objects (so `.json()`/`.status_code`/`.headers` behave
exactly like the real library, not a hand-rolled approximation of it).
"""

from __future__ import annotations

import base64
import json
import sqlite3
import sys
import threading
import time
from unittest.mock import patch

import pytest
import requests

from collection.rq5_agent_file_scan import (
    REPAIRABLE_ERROR_REASONS,
    RQ5_LANGUAGES,
    TARGET_REQUESTS_PER_HOUR,
    RateLimitExhausted,
    _api_get,
    _build_keyword_pattern,
    _build_patterns,
    _is_rate_limited,
    _RateLimiter,
    _repo_row,
    _retry_wait_seconds,
    _scan_result,
    find_cutoff_commit_via_api,
    find_keyword_matches,
    find_target_files_at_commit,
    initialise_rq5_db,
    list_root_tree_via_api,
    load_repos_needing_retry,
    load_rq5_keyword_catalog,
    load_scanned_repo_names,
    main,
    persist_result,
    process_repo,
    read_blob_via_api,
    retry_failed_repos,
    run_scan,
    scan_file_content,
)


def _fake_response(status_code, json_data=None, headers=None):
    """Returns a real `requests.Response` with the given status, JSON and headers, so the tests run the real parsing code."""
    resp = requests.Response()
    resp.status_code = status_code
    resp._content = json.dumps(json_data).encode("utf-8") if json_data is not None else b""
    resp.headers = requests.structures.CaseInsensitiveDict(headers or {})
    return resp


def _commit_json(sha, date="2026-09-08T12:00:00Z"):
    return {"sha": sha, "commit": {"author": {"date": date}, "committer": {"date": date}}}


def _blob_json(content_str, encoding="base64"):
    return {
        "content": base64.b64encode(content_str.encode("utf-8")).decode("ascii"),
        "encoding": encoding,
    }


def _tree_entry(path, sha, type_="blob", mode="100644"):
    return {"path": path, "type": type_, "sha": sha, "mode": mode}


def _route(*, commits=None, trees=None, blobs=None):
    """requests.get side_effect routing by URL shape:
    .../commits           -> `commits` (a list of commit dicts; None means empty result)
    .../git/trees/<sha>   -> `trees[sha]` (a list of tree entries)
    .../git/blobs/<sha>   -> `blobs[sha]` (a blob dict)
    Any sha not present in `trees`/`blobs` is treated as a 404.
    """
    trees = trees or {}
    blobs = blobs or {}

    def _get(url, headers=None, params=None, timeout=None):
        if url.endswith("/commits"):
            return _fake_response(200, commits if commits is not None else [])
        if "/git/trees/" in url:
            sha = url.rsplit("/", 1)[-1]
            if sha not in trees:
                return _fake_response(404, {"message": "Not Found"})
            return _fake_response(200, {"sha": sha, "tree": trees[sha], "truncated": False})
        if "/git/blobs/" in url:
            sha = url.rsplit("/", 1)[-1]
            if sha not in blobs:
                return _fake_response(404, {"message": "Not Found"})
            return _fake_response(200, blobs[sha])
        raise AssertionError(f"unexpected URL in test: {url}")

    return _get


def _per_repo(fake):
    """Adapt a one-repository fake to the batch signature of process_repos_graphql()."""

    def _batch(batch, **kwargs):
        return [fake(repo, **kwargs) for repo in batch]

    return _batch


# Terms the catalog excludes on purpose (see its header comment): the spaced
# lifecycle phrases match ordinary English, bare "teardown" matches generic
# cleanup prose.
EXCLUDED_FIXTURE_KEYWORDS = ("before each", "after each", "before all", "after all", "teardown")

_TEST_CATALOG = {
    "target_files": ["AGENTS.md", "CLAUDE.md"],
    "test_keywords": ["test", "pytest"],
    "fixture_keywords": ["fixture", "fixtures", "conftest", "test setup", "beforeEach"],
}


class TestLoadRq5KeywordCatalog:
    def test_real_catalog_has_expected_shape(self):
        catalog = load_rq5_keyword_catalog()
        assert catalog["target_files"] == ["AGENTS.md", "CLAUDE.md"]
        assert "test" in catalog["test_keywords"]
        assert "fixture" in catalog["fixture_keywords"]

    def test_bare_setup_is_never_a_standalone_keyword(self):
        catalog = load_rq5_keyword_catalog()
        assert "setup" not in catalog["test_keywords"]
        assert "setup" not in catalog["fixture_keywords"]

    def test_bare_teardown_is_never_a_standalone_keyword(self):
        """Same defect class as bare "setup" above -- see the catalog's
        exclusions: "teardown" alone matches generic resource/UI/infra
        cleanup prose with no test relevance."""
        catalog = load_rq5_keyword_catalog()
        assert "teardown" not in catalog["fixture_keywords"]

    def test_excluded_keywords_never_reappear(self):
        catalog = load_rq5_keyword_catalog()
        for excluded in EXCLUDED_FIXTURE_KEYWORDS:
            assert excluded not in catalog["fixture_keywords"]
        # The unambiguous camelCase forms and "setup and teardown" are how
        # these concepts are still caught.
        for kept in ("beforeEach", "afterEach", "beforeAll", "afterAll", "setup and teardown"):
            assert kept in catalog["fixture_keywords"]


class TestBuildKeywordPattern:
    def test_single_word_respects_word_boundaries(self):
        pattern = _build_keyword_pattern("test")
        assert pattern.search("a test here")
        assert not pattern.search("latest")
        assert not pattern.search("contest")
        assert not pattern.search("attestation")

    def test_case_insensitive(self):
        pattern = _build_keyword_pattern("test")
        assert pattern.search("This is a TEST.")

    def test_multi_word_accepts_space_hyphen_or_no_separator(self):
        pattern = _build_keyword_pattern("test setup")
        assert pattern.search("test setup")
        assert pattern.search("test-setup")
        assert pattern.search("testsetup")
        assert pattern.search("TESTSETUP")

    def test_multi_word_still_respects_outer_word_boundaries(self):
        pattern = _build_keyword_pattern("test setup")
        assert not pattern.search("testsetupx")
        assert not pattern.search("xtestsetup")

    def test_camel_case_keyword_matched_literally(self):
        pattern = _build_keyword_pattern("beforeEach")
        assert pattern.search("call beforeEach now")
        assert pattern.search("BEFOREEACH")

    def test_internal_hyphen_in_a_word_is_preserved_literally(self):
        pattern = _build_keyword_pattern("end-to-end test")
        assert pattern.search("end-to-end test")
        assert pattern.search("end-to-end-test")
        assert pattern.search("end-to-endtest")
        assert not pattern.search("endtoend test")


class TestBuildPatterns:
    def test_builds_one_pattern_per_keyword(self):
        patterns = _build_patterns(["test", "fixture"])
        assert set(patterns.keys()) == {"test", "fixture"}


class TestFindKeywordMatches:
    def test_records_every_occurrence_with_line_number_and_context(self):
        patterns = _build_patterns(["test"])
        content = "line one\na test and another test here\nline three"
        matches = find_keyword_matches(content, patterns)
        assert len(matches) == 2
        assert all(m["keyword"] == "test" for m in matches)
        assert all(m["line_number"] == 2 for m in matches)
        assert all(m["line_context"] == "a test and another test here" for m in matches)

    def test_line_context_is_stripped_of_surrounding_whitespace(self):
        patterns = _build_patterns(["test"])
        matches = find_keyword_matches("   a test line   \n", patterns)
        assert matches[0]["line_context"] == "a test line"

    def test_no_matches_on_content_without_any_keyword(self):
        patterns = _build_patterns(["test"])
        assert find_keyword_matches("nothing relevant here", patterns) == []

    def test_lines_inside_fenced_code_block_are_flagged(self):
        patterns = _build_patterns(["teardown"])
        content = "intro teardown\n```\nfenced teardown\n```\noutro teardown"
        matches = find_keyword_matches(content, patterns)
        by_context = {m["line_context"]: m["in_code_block"] for m in matches}
        assert by_context["intro teardown"] is False
        assert by_context["fenced teardown"] is True
        assert by_context["outro teardown"] is False

    def test_tilde_fences_also_toggle_code_block_state(self):
        patterns = _build_patterns(["teardown"])
        content = "~~~\nfenced teardown\n~~~"
        matches = find_keyword_matches(content, patterns)
        assert matches[0]["in_code_block"] is True

    def test_two_separate_fenced_blocks_each_toggle_correctly(self):
        patterns = _build_patterns(["teardown"])
        content = "```\nfirst teardown\n```\nbetween teardown\n```\nsecond teardown\n```"
        matches = find_keyword_matches(content, patterns)
        by_context = {m["line_context"]: m["in_code_block"] for m in matches}
        assert by_context["first teardown"] is True
        assert by_context["between teardown"] is False
        assert by_context["second teardown"] is True


class TestScanFileContent:
    def test_separates_test_and_fixture_matches(self):
        test_patterns = _build_patterns(["test"])
        fixture_patterns = _build_patterns(["fixture"])
        result = scan_file_content(
            "a test and a fixture", test_patterns=test_patterns, fixture_patterns=fixture_patterns
        )
        assert len(result["test_matches"]) == 1
        assert len(result["fixture_matches"]) == 1


class TestApiGet:
    def test_returns_response_on_success(self):
        with patch("requests.get", return_value=_fake_response(200, {"ok": True})):
            response = _api_get("https://api.github.com/x", token="tok")
        assert response.status_code == 200
        assert response.json() == {"ok": True}

    def test_returns_response_on_404_without_retrying(self):
        get_mock = patch("requests.get", return_value=_fake_response(404, {})).start()
        try:
            response = _api_get("https://api.github.com/x", token="tok")
        finally:
            patch.stopall()
        assert response.status_code == 404
        assert get_mock.call_count == 1

    def test_retries_on_rate_limit_then_succeeds(self):
        rate_limited = _fake_response(403, {}, headers={"X-RateLimit-Remaining": "0", "Retry-After": "0"})
        ok = _fake_response(200, {"ok": True})
        with (
            patch("requests.get", side_effect=[rate_limited, ok]),
            patch("collection.rq5_agent_file_scan.time.sleep"),
        ):
            response = _api_get("https://api.github.com/x", token="tok", max_retries=3)
        assert response.status_code == 200

    def test_exhausts_retries_and_raises_rate_limit_exhausted(self):
        """When every retry is rate-limited, the call raises `RateLimitExhausted`. It does not return `None`, because `None` means the file was not found."""
        rate_limited = _fake_response(429, {}, headers={"Retry-After": "0"})
        with (
            patch("requests.get", return_value=rate_limited) as get_mock,
            patch("collection.rq5_agent_file_scan.time.sleep"),
        ):
            with pytest.raises(RateLimitExhausted):
                _api_get("https://api.github.com/x", token="tok", max_retries=2)
        assert get_mock.call_count == 3  # initial + 2 retries

    def test_network_exception_returns_none(self):
        with patch("requests.get", side_effect=requests.ConnectionError("boom")):
            response = _api_get("https://api.github.com/x", token="tok")
        assert response is None

    def test_sends_authorization_header_when_token_given(self):
        with patch("requests.get", return_value=_fake_response(200, {})) as get_mock:
            _api_get("https://api.github.com/x", token="abc123")
        assert get_mock.call_args.kwargs["headers"]["Authorization"] == "token abc123"

    def test_omits_authorization_header_when_no_token(self):
        with patch("requests.get", return_value=_fake_response(200, {})) as get_mock:
            _api_get("https://api.github.com/x", token="")
        assert "Authorization" not in get_mock.call_args.kwargs["headers"]

    def test_calls_rate_limiter_acquire_once_per_attempt(self):
        limiter = _RateLimiter(rate_per_second=1000)  # fast, just checking call count
        rate_limited = _fake_response(429, {}, headers={"Retry-After": "0"})
        ok = _fake_response(200, {})
        with (
            patch("requests.get", side_effect=[rate_limited, ok]),
            patch("collection.rq5_agent_file_scan.time.sleep"),
            patch.object(limiter, "acquire", wraps=limiter.acquire) as acquire_mock,
        ):
            _api_get("https://api.github.com/x", token="tok", rate_limiter=limiter)
        assert acquire_mock.call_count == 2  # initial attempt + the one retry

    def test_no_rate_limiter_means_no_pacing(self):
        with patch("requests.get", return_value=_fake_response(200, {})) as get_mock:
            _api_get("https://api.github.com/x", token="tok", rate_limiter=None)
        assert get_mock.call_count == 1  # just confirms this path needs no limiter at all


class TestIsRateLimited:
    """Rate-limit detection. GitHub's secondary limit returns a 403 without a zero `X-RateLimit-Remaining`, so the check also reads `Retry-After`. A 403 with neither header is a real permission error and is not retried."""

    def test_429_is_always_rate_limited(self):
        assert _is_rate_limited(_fake_response(429, {})) is True

    def test_403_with_zeroed_remaining_is_rate_limited(self):
        """The primary hourly-quota exhaustion case -- already handled
        before this fix, must keep working."""
        response = _fake_response(403, {}, headers={"X-RateLimit-Remaining": "0"})
        assert _is_rate_limited(response) is True

    def test_403_with_retry_after_but_nonzero_remaining_is_rate_limited(self):
        """A 403 with `Retry-After` and a non-zero remaining quota is rate limiting. This is the secondary-limit case."""
        response = _fake_response(403, {}, headers={"Retry-After": "60", "X-RateLimit-Remaining": "4000"})
        assert _is_rate_limited(response) is True

    def test_403_with_retry_after_and_no_remaining_header_at_all_is_rate_limited(self):
        response = _fake_response(403, {}, headers={"Retry-After": "30"})
        assert _is_rate_limited(response) is True

    def test_plain_403_with_neither_signal_is_not_rate_limited(self):
        """A 403 with neither header is a real permission error. It is not retried."""
        response = _fake_response(403, {})
        assert _is_rate_limited(response) is False

    def test_404_is_never_rate_limited(self):
        assert _is_rate_limited(_fake_response(404, {})) is False

    def test_200_is_never_rate_limited(self):
        assert _is_rate_limited(_fake_response(200, {})) is False

    def test_none_response_is_not_rate_limited(self):
        assert _is_rate_limited(None) is False


class TestRetryWaitSeconds:
    def test_prefers_retry_after_header(self):
        response = _fake_response(429, {}, headers={"Retry-After": "42"})
        assert _retry_wait_seconds(response, attempt=0) == 42.0

    def test_falls_back_to_rate_limit_reset_when_retry_after_absent(self):
        reset_at = time.time() + 120
        response = _fake_response(403, {}, headers={"X-RateLimit-Reset": str(int(reset_at))})
        wait = _retry_wait_seconds(response, attempt=0)
        # within a couple seconds of the real 120s gap, accounting for timing jitter + the 1s buffer
        assert 118 <= wait <= 123

    def test_falls_back_to_exponential_backoff_when_neither_header_present(self):
        response = _fake_response(429, {}, headers={})
        assert _retry_wait_seconds(response, attempt=0) == 1
        assert _retry_wait_seconds(response, attempt=2) == 4
        assert _retry_wait_seconds(response, attempt=10) == 30  # capped

    def test_ignores_a_reset_timestamp_already_in_the_past(self):
        """A stale/already-passed reset time must not produce a negative
        wait -- falls through to the exponential backoff instead."""
        response = _fake_response(403, {}, headers={"X-RateLimit-Reset": str(int(time.time()) - 100)})
        assert _retry_wait_seconds(response, attempt=0) == 1

    def test_malformed_headers_fall_back_gracefully(self):
        response = _fake_response(429, {}, headers={"Retry-After": "not-a-number"})
        assert _retry_wait_seconds(response, attempt=1) == 2


class TestRateLimiter:
    def test_first_acquire_does_not_block(self):
        limiter = _RateLimiter(rate_per_second=1)
        start = time.monotonic()
        limiter.acquire()
        assert time.monotonic() - start < 0.1

    def test_paces_consecutive_calls_to_the_target_rate(self):
        limiter = _RateLimiter(rate_per_second=20)  # 50ms interval
        start = time.monotonic()
        for _ in range(3):
            limiter.acquire()
        elapsed = time.monotonic() - start
        # 3 calls at a 50ms interval -> at least ~100ms for the 2nd and 3rd waits
        assert elapsed >= 0.09

    def test_does_not_accumulate_a_backlog_after_an_idle_period(self):
        """Idle time between calls must not let a later burst "catch up"
        -- exactly the burst behavior this limiter deliberately avoids
        (see its own docstring)."""
        limiter = _RateLimiter(rate_per_second=10)  # 100ms interval
        limiter.acquire()
        time.sleep(0.3)  # idle well past several intervals
        start = time.monotonic()
        limiter.acquire()
        assert time.monotonic() - start < 0.05  # should NOT wait out a backlog


class TestFindCutoffCommitViaApi:
    def test_returns_sha_and_date_from_the_first_commit(self):
        commits = [_commit_json("abc123", date="2026-09-08T16:40:33Z")]
        with patch("requests.get", side_effect=_route(commits=commits)):
            result = find_cutoff_commit_via_api("owner/repo", "2026-09-08")
        assert result == {"sha": "abc123", "date": "2026-09-08"}

    def test_empty_commit_list_returns_none(self):
        with patch("requests.get", side_effect=_route(commits=[])):
            result = find_cutoff_commit_via_api("owner/repo", "2026-09-08")
        assert result is None

    def test_non_200_returns_none(self):
        with patch("requests.get", return_value=_fake_response(404, {})):
            result = find_cutoff_commit_via_api("owner/repo", "2026-09-08")
        assert result is None

    def test_uses_until_parameter_bounded_to_end_of_cutoff_day(self):
        with patch("requests.get", return_value=_fake_response(200, [])) as get_mock:
            find_cutoff_commit_via_api("owner/repo", "2026-09-08")
        assert get_mock.call_args.kwargs["params"]["until"] == "2026-09-08T23:59:59Z"

    def test_propagates_rate_limit_exhausted_rather_than_returning_none(self):
        """A caller must be able to tell "genuinely no commit" apart from
        "couldn't check, GitHub throttled us" -- this does NOT catch
        RateLimitExhausted itself; process_repo() is what catches it."""
        rate_limited = _fake_response(429, {}, headers={"Retry-After": "0"})
        with (
            patch("requests.get", return_value=rate_limited),
            patch("collection.rq5_agent_file_scan.time.sleep"),
        ):
            with pytest.raises(RateLimitExhausted):
                find_cutoff_commit_via_api("owner/repo", "2026-09-08", rate_limiter=None)


class TestListRootTreeViaApi:
    def test_returns_tree_entries(self):
        entries = [_tree_entry("AGENTS.md", "sha1")]
        with patch("requests.get", side_effect=_route(trees={"abc": entries})):
            result = list_root_tree_via_api("owner/repo", "abc")
        assert result == entries

    def test_missing_sha_returns_none(self):
        with patch("requests.get", side_effect=_route(trees={})):
            result = list_root_tree_via_api("owner/repo", "missing")
        assert result is None


class TestReadBlobViaApi:
    def test_decodes_base64_content(self):
        with patch("requests.get", side_effect=_route(blobs={"sha1": _blob_json("hello world")})):
            content = read_blob_via_api("owner/repo", "sha1")
        assert content == "hello world"

    def test_symlink_blob_returns_its_literal_target_text(self):
        """A symlink's blob content IS the literal link-target text --
        this is exactly why no type-based branching is needed anywhere:
        the Blobs API returns bytes, not a resolved file."""
        with patch("requests.get", side_effect=_route(blobs={"sha1": _blob_json("AGENTS.md")})):
            content = read_blob_via_api("owner/repo", "sha1")
        assert content == "AGENTS.md"

    def test_missing_blob_returns_none(self):
        with patch("requests.get", side_effect=_route(blobs={})):
            content = read_blob_via_api("owner/repo", "missing")
        assert content is None

    def test_non_base64_encoding_returns_none_not_a_crash(self):
        with patch("requests.get", side_effect=_route(blobs={"sha1": {"content": "x", "encoding": "none"}})):
            content = read_blob_via_api("owner/repo", "sha1")
        assert content is None

    def test_malformed_base64_returns_none_not_a_crash(self):
        with patch(
            "requests.get",
            side_effect=_route(blobs={"sha1": {"content": "not-valid-base64!!!", "encoding": "base64"}}),
        ):
            content = read_blob_via_api("owner/repo", "sha1")
        assert content is None

    def test_decodes_permissively_on_invalid_utf8(self):
        raw = b"\xff\xfe not valid utf-8"
        blob = {"content": base64.b64encode(raw).decode("ascii"), "encoding": "base64"}
        with patch("requests.get", side_effect=_route(blobs={"sha1": blob})):
            content = read_blob_via_api("owner/repo", "sha1")
        assert content is not None  # decoded with errors="replace", never raised


class TestFindTargetFilesAtCommit:
    def test_matches_case_insensitively(self):
        entries = [_tree_entry("agents.md", "sha1")]
        found = find_target_files_at_commit(entries, ["AGENTS.md", "CLAUDE.md"])
        assert found == [("agents.md", "AGENTS.md", "sha1")]

    def test_excludes_a_directory_with_a_matching_name(self):
        entries = [_tree_entry("AGENTS.md", "sha1", type_="tree")]
        found = find_target_files_at_commit(entries, ["AGENTS.md", "CLAUDE.md"])
        assert found == []

    def test_finds_both_target_files_independently(self):
        entries = [_tree_entry("AGENTS.md", "sha1"), _tree_entry("CLAUDE.md", "sha2")]
        found = sorted(find_target_files_at_commit(entries, ["AGENTS.md", "CLAUDE.md"]))
        assert found == [("AGENTS.md", "AGENTS.md", "sha1"), ("CLAUDE.md", "CLAUDE.md", "sha2")]

    def test_no_match_returns_empty_list(self):
        entries = [_tree_entry("README.md", "sha1")]
        assert find_target_files_at_commit(entries, ["AGENTS.md", "CLAUDE.md"]) == []

    def test_symlink_mode_is_still_a_blob_and_matches(self):
        """A symlink's tree entry has mode 120000 but type "blob" -- it
        must still be picked up for reading, same as any other file."""
        entries = [_tree_entry("CLAUDE.md", "sha1", type_="blob", mode="120000")]
        found = find_target_files_at_commit(entries, ["AGENTS.md", "CLAUDE.md"])
        assert found == [("CLAUDE.md", "CLAUDE.md", "sha1")]


class TestRepoRowAndScanResult:
    def test_repo_row_coerces_fetch_ok_to_int(self):
        row = _repo_row("o/r", "python", "t", fetch_ok=True)
        assert row["fetch_ok"] == 1
        row = _repo_row("o/r", "python", "t", fetch_ok=False)
        assert row["fetch_ok"] == 0

    def test_repo_row_defaults(self):
        row = _repo_row("o/r", "python", "t", fetch_ok=False, error_reason="clone_failed")
        assert row["commit_sha"] is None
        assert row["num_agent_files"] == 0
        assert row["error_reason"] == "clone_failed"

    def test_scan_result_defaults_files_and_matches_to_empty_lists(self):
        row = _repo_row("o/r", "python", "t", fetch_ok=False)
        result = _scan_result(row)
        assert result == {"repo": row, "files": [], "matches": []}


class TestProcessRepo:
    def _repo_dict(self, name="owner/repo", language="python"):
        return {"repo_name": name, "language": language, "clone_url": "https://example.com/owner/repo.git"}

    def test_successful_scan_with_one_matching_file(self):
        commits = [_commit_json("sha1", date="2026-08-01T00:00:00Z")]
        tree = [_tree_entry("AGENTS.md", "blobsha1")]
        blob = _blob_json("Run `pytest` and check the fixture setup.\nUse beforeEach for fixtures.")

        with patch(
            "requests.get",
            side_effect=_route(commits=commits, trees={"sha1": tree}, blobs={"blobsha1": blob}),
        ):
            result = process_repo(self._repo_dict(), snapshot_date="2026-09-08", catalog=_TEST_CATALOG)

        assert result["repo"]["fetch_ok"] == 1
        assert result["repo"]["error_reason"] is None
        assert result["repo"]["num_agent_files"] == 1
        assert result["repo"]["commit_sha"] == "sha1"

        assert len(result["files"]) == 1
        file_row = result["files"][0]
        assert file_row["file_name"] == "AGENTS.md"
        assert file_row["file_type"] == "AGENTS.md"
        assert file_row["has_test"] is True
        assert file_row["has_fixture"] is True
        assert file_row["test_match_count"] == 1  # "pytest" only
        # "fixture" (line 1) + "beforeEach" + "fixtures" (line 2).
        assert file_row["fixture_match_count"] == 3
        assert "pytest" in file_row["matched_test_keywords"]
        assert file_row["github_url"] == "https://github.com/owner/repo/blob/sha1/AGENTS.md"

        assert len(result["matches"]) == file_row["test_match_count"] + file_row["fixture_match_count"]
        assert all(m["repo_name"] == "owner/repo" for m in result["matches"])
        assert all(m["file_name"] == "AGENTS.md" for m in result["matches"])

    def test_repo_with_no_target_files_is_fetch_ok_with_zero_files(self):
        commits = [_commit_json("sha1")]
        tree = [_tree_entry("README.md", "blobsha1")]

        with patch("requests.get", side_effect=_route(commits=commits, trees={"sha1": tree})):
            result = process_repo(self._repo_dict(), snapshot_date="2026-09-08", catalog=_TEST_CATALOG)

        assert result["repo"]["fetch_ok"] == 1
        assert result["repo"]["error_reason"] is None
        assert result["repo"]["num_agent_files"] == 0
        assert result["files"] == []
        assert result["matches"] == []

    def test_no_commit_before_cutoff_returns_zero_row(self):
        with patch("requests.get", side_effect=_route(commits=[])):
            result = process_repo(self._repo_dict(), snapshot_date="2026-09-08", catalog=_TEST_CATALOG)

        assert result["repo"]["fetch_ok"] == 0
        assert result["repo"]["error_reason"] == "no_commit_at_or_before_cutoff"
        assert result["files"] == []
        assert result["matches"] == []

    def test_tree_fetch_failure_returns_zero_row(self):
        commits = [_commit_json("sha1")]
        # trees={} means the Trees API 404s for "sha1" -- simulated failure.
        with patch("requests.get", side_effect=_route(commits=commits, trees={})):
            result = process_repo(self._repo_dict(), snapshot_date="2026-09-08", catalog=_TEST_CATALOG)

        assert result["repo"]["fetch_ok"] == 0
        assert result["repo"]["error_reason"] == "tree_fetch_failed"

    def test_one_unreadable_blob_does_not_block_the_other(self):
        commits = [_commit_json("sha1")]
        tree = [_tree_entry("AGENTS.md", "blob_missing"), _tree_entry("CLAUDE.md", "blob_present")]
        blobs = {"blob_present": _blob_json("a fixture file")}  # blob_missing -> 404

        with patch("requests.get", side_effect=_route(commits=commits, trees={"sha1": tree}, blobs=blobs)):
            result = process_repo(self._repo_dict(), snapshot_date="2026-09-08", catalog=_TEST_CATALOG)

        assert result["repo"]["fetch_ok"] == 1
        assert [f["file_name"] for f in result["files"]] == ["CLAUDE.md"]

    def test_symlinked_claude_md_is_scanned_as_its_own_literal_content(self):
        commits = [_commit_json("sha1")]
        tree = [
            _tree_entry("AGENTS.md", "blob_agents"),
            _tree_entry("CLAUDE.md", "blob_claude_symlink", mode="120000"),
        ]
        blobs = {
            "blob_agents": _blob_json("a test mention and a fixture mention"),
            "blob_claude_symlink": _blob_json("AGENTS.md"),  # the symlink's own literal target text
        }

        with patch("requests.get", side_effect=_route(commits=commits, trees={"sha1": tree}, blobs=blobs)):
            result = process_repo(self._repo_dict(), snapshot_date="2026-09-08", catalog=_TEST_CATALOG)

        by_name = {f["file_name"]: f for f in result["files"]}
        assert by_name["AGENTS.md"]["has_test"] is True
        assert by_name["AGENTS.md"]["has_fixture"] is True
        # CLAUDE.md's blob content is literally "AGENTS.md" -- no keyword in that string.
        assert by_name["CLAUDE.md"]["has_test"] is False
        assert by_name["CLAUDE.md"]["has_fixture"] is False

    def test_default_catalog_is_loaded_when_none_is_passed(self):
        commits = [_commit_json("sha1")]
        tree = [_tree_entry("AGENTS.md", "blobsha1")]
        blob = _blob_json("mentions conftest for fixtures")

        with patch(
            "requests.get", side_effect=_route(commits=commits, trees={"sha1": tree}, blobs={"blobsha1": blob})
        ):
            result = process_repo(self._repo_dict(), snapshot_date="2026-09-08")

        assert result["files"][0]["has_fixture"] is True

    def test_rate_limit_exhausted_during_cutoff_lookup_is_recorded_distinctly(self):
        rate_limited = _fake_response(429, {}, headers={"Retry-After": "0"})
        with (
            patch("requests.get", return_value=rate_limited),
            patch("collection.rq5_agent_file_scan.time.sleep"),
        ):
            result = process_repo(self._repo_dict(), snapshot_date="2026-09-08", catalog=_TEST_CATALOG)

        assert result["repo"]["fetch_ok"] == 0
        assert result["repo"]["error_reason"] == "rate_limited"
        # Must never be conflated with a genuine negative result:
        assert result["repo"]["error_reason"] != "no_commit_at_or_before_cutoff"

    def test_rate_limit_exhausted_during_tree_fetch_is_recorded_distinctly(self):
        commits = [_commit_json("sha1")]
        rate_limited = _fake_response(429, {}, headers={"Retry-After": "0"})

        def _get(url, headers=None, params=None, timeout=None):
            if url.endswith("/commits"):
                return _fake_response(200, commits)
            return rate_limited  # the /git/trees/ call

        with (
            patch("requests.get", side_effect=_get),
            patch("collection.rq5_agent_file_scan.time.sleep"),
        ):
            result = process_repo(self._repo_dict(), snapshot_date="2026-09-08", catalog=_TEST_CATALOG)

        assert result["repo"]["fetch_ok"] == 0
        assert result["repo"]["error_reason"] == "rate_limited"

    def test_rate_limit_exhausted_mid_file_loop_discards_partial_results(self):
        """One file already read successfully, then the second blob fetch
        gets rate limited -- the whole repo must fail cleanly with no
        files/matches at all, never a partial fetch_ok=1 row that looks
        like "this repo only has 1 agent file" when the truth is unknown."""
        commits = [_commit_json("sha1")]
        tree = [_tree_entry("AGENTS.md", "blob_ok"), _tree_entry("CLAUDE.md", "blob_limited")]
        rate_limited = _fake_response(429, {}, headers={"Retry-After": "0"})

        def _get(url, headers=None, params=None, timeout=None):
            if url.endswith("/commits"):
                return _fake_response(200, commits)
            if url.endswith("/git/trees/sha1"):
                return _fake_response(200, {"tree": tree})
            if url.endswith("/blob_ok"):
                return _fake_response(200, _blob_json("a test file"))
            return rate_limited  # the blob_limited fetch

        with (
            patch("requests.get", side_effect=_get),
            patch("collection.rq5_agent_file_scan.time.sleep"),
        ):
            result = process_repo(self._repo_dict(), snapshot_date="2026-09-08", catalog=_TEST_CATALOG)

        assert result["repo"]["fetch_ok"] == 0
        assert result["repo"]["error_reason"] == "rate_limited"
        assert result["files"] == []
        assert result["matches"] == []

    def test_threads_rate_limiter_through_to_every_api_call(self):
        limiter = _RateLimiter(rate_per_second=1000)
        commits = [_commit_json("sha1")]
        tree = [_tree_entry("AGENTS.md", "blobsha1")]
        blob = _blob_json("a test file")

        with (
            patch(
                "requests.get", side_effect=_route(commits=commits, trees={"sha1": tree}, blobs={"blobsha1": blob})
            ),
            patch.object(limiter, "acquire", wraps=limiter.acquire) as acquire_mock,
        ):
            process_repo(self._repo_dict(), snapshot_date="2026-09-08", catalog=_TEST_CATALOG, rate_limiter=limiter)

        # commit lookup + tree listing + one blob fetch = 3 calls, each paced.
        assert acquire_mock.call_count == 3


class TestProcessRepoRobustness:
    def test_connection_error_is_treated_as_a_failed_fetch_not_a_crash(self):
        repo = {"repo_name": "owner/repo", "language": "python", "clone_url": "x"}
        with patch("requests.get", side_effect=requests.ConnectionError("boom")):
            result = process_repo(repo, snapshot_date="2026-09-08", catalog=_TEST_CATALOG)
        assert result["repo"]["fetch_ok"] == 0
        assert result["repo"]["error_reason"] == "no_commit_at_or_before_cutoff"


class TestLoadScannedRepoNames:
    def test_missing_db_returns_empty_set(self, tmp_path):
        assert load_scanned_repo_names(tmp_path / "missing.db") == set()

    def test_returns_persisted_repo_names(self, tmp_path):
        db_path = tmp_path / "rq5.db"
        initialise_rq5_db(db_path)
        persist_result(_scan_result(_repo_row("o/a", "python", "t", fetch_ok=True)), db_path)
        assert load_scanned_repo_names(db_path) == {"o/a"}


class TestPersistResult:
    def test_upserts_repo_row_by_name(self, tmp_path):
        db_path = tmp_path / "rq5.db"
        initialise_rq5_db(db_path)
        persist_result(
            _scan_result(_repo_row("o/a", "python", "t1", fetch_ok=False, error_reason="no_commit_at_or_before_cutoff")),
            db_path,
        )
        persist_result(
            _scan_result(
                _repo_row("o/a", "python", "t2", fetch_ok=True, commit_sha="abc", num_agent_files=1)
            ),
            db_path,
        )

        with sqlite3.connect(db_path) as conn:
            rows = conn.execute("SELECT fetch_ok, commit_sha FROM repo_scan WHERE repo_name='o/a'").fetchall()
        assert rows == [(1, "abc")]

    def test_re_persisting_replaces_file_and_match_rows_not_duplicates_them(self, tmp_path):
        db_path = tmp_path / "rq5.db"
        initialise_rq5_db(db_path)

        file1 = {
            "repo_name": "o/a",
            "file_name": "AGENTS.md",
            "file_type": "AGENTS.md",
            "language": "python",
            "commit_sha": "sha1",
            "has_test": True,
            "has_fixture": False,
            "test_match_count": 1,
            "fixture_match_count": 0,
            "matched_test_keywords": "test",
            "matched_fixture_keywords": "",
            "github_url": "https://github.com/o/a/blob/sha1/AGENTS.md",
        }
        match1 = {
            "repo_name": "o/a",
            "file_name": "AGENTS.md",
            "keyword_list": "test",
            "keyword": "test",
            "line_number": 1,
            "line_context": "a test",
            "line_before_2": "",
            "line_before_1": "",
            "line_after_1": "",
            "line_after_2": "",
            "in_code_block": False,
        }
        persist_result(
            _scan_result(
                _repo_row("o/a", "python", "t1", fetch_ok=True, commit_sha="sha1", num_agent_files=1),
                files=[file1],
                matches=[match1, match1],
            ),
            db_path,
        )

        persist_result(
            _scan_result(
                _repo_row("o/a", "python", "t2", fetch_ok=True, commit_sha="sha2", num_agent_files=0)
            ),
            db_path,
        )

        with sqlite3.connect(db_path) as conn:
            file_count = conn.execute("SELECT COUNT(*) FROM agent_files WHERE repo_name='o/a'").fetchone()[0]
            match_count = conn.execute(
                "SELECT COUNT(*) FROM agent_file_matches WHERE repo_name='o/a'"
            ).fetchone()[0]
        assert file_count == 0
        assert match_count == 0

    def test_persists_files_and_matches(self, tmp_path):
        db_path = tmp_path / "rq5.db"
        initialise_rq5_db(db_path)
        file1 = {
            "repo_name": "o/a",
            "file_name": "AGENTS.md",
            "file_type": "AGENTS.md",
            "language": "python",
            "commit_sha": "sha1",
            "has_test": True,
            "has_fixture": True,
            "test_match_count": 1,
            "fixture_match_count": 1,
            "matched_test_keywords": "test",
            "matched_fixture_keywords": "fixture",
            "github_url": "https://github.com/o/a/blob/sha1/AGENTS.md",
        }
        match_test = {
            "repo_name": "o/a",
            "file_name": "AGENTS.md",
            "keyword_list": "test",
            "keyword": "test",
            "line_number": 1,
            "line_context": "a test",
            "line_before_2": "",
            "line_before_1": "",
            "line_after_1": "",
            "line_after_2": "",
            "in_code_block": False,
        }
        match_fixture = {
            "repo_name": "o/a",
            "file_name": "AGENTS.md",
            "keyword_list": "fixture",
            "keyword": "fixture",
            "line_number": 2,
            "line_context": "a fixture",
            "line_before_2": "",
            "line_before_1": "",
            "line_after_1": "",
            "line_after_2": "",
            "in_code_block": True,
        }
        persist_result(
            _scan_result(
                _repo_row("o/a", "python", "t", fetch_ok=True, commit_sha="sha1", num_agent_files=1),
                files=[file1],
                matches=[match_test, match_fixture],
            ),
            db_path,
        )

        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            file_row = conn.execute("SELECT * FROM agent_files WHERE repo_name='o/a'").fetchone()
            match_rows = conn.execute(
                "SELECT * FROM agent_file_matches WHERE repo_name='o/a' ORDER BY line_number"
            ).fetchall()

        assert file_row["has_test"] == 1
        assert file_row["has_fixture"] == 1
        assert len(match_rows) == 2
        assert match_rows[1]["in_code_block"] == 1


class TestRunScan:
    def test_run_scan_skips_already_scanned_repos(self, tmp_path):
        db_path = tmp_path / "rq5.db"
        initialise_rq5_db(db_path)
        persist_result(_scan_result(_repo_row("org/already", "python", "t", fetch_ok=True)), db_path)

        universe = [
            {"repo_name": "org/already", "language": "python", "clone_url": "x"},
            {"repo_name": "org/new", "language": "python", "clone_url": "y"},
        ]
        processed = []

        def _fake_process_repo(repo, **kwargs):
            processed.append(repo["repo_name"])
            return _scan_result(_repo_row(repo["repo_name"], repo["language"], "t2", fetch_ok=True))

        with (
            patch("collection.rq5_agent_file_scan.load_corpus", return_value=universe),
            patch("collection.rq5_agent_file_scan.process_repos_graphql", side_effect=_per_repo(_fake_process_repo)),
        ):
            counts = run_scan(snapshot_date="2026-09-08", 
                db_path=db_path,
                workers=1,
                progress_path=tmp_path / "progress.json",
                notify=False,
            )

        assert processed == ["org/new"]
        assert counts == {"total": 2, "already_done": 1, "scanned_this_run": 1}
        assert load_scanned_repo_names(db_path) == {"org/already", "org/new"}

    def test_run_scan_threads_token_through_to_process_repo(self, tmp_path):
        universe = [{"repo_name": "org/a", "language": "python", "clone_url": "x"}]
        seen_kwargs = {}

        def _fake_process_repo(repo, **kwargs):
            seen_kwargs.update(kwargs)
            return _scan_result(_repo_row(repo["repo_name"], repo["language"], "t", fetch_ok=True))

        with (
            patch("collection.rq5_agent_file_scan.load_corpus", return_value=universe),
            patch("collection.rq5_agent_file_scan.process_repos_graphql", side_effect=_per_repo(_fake_process_repo)),
        ):
            run_scan(snapshot_date="2026-09-08", 
                db_path=tmp_path / "rq5.db",
                workers=1,
                progress_path=tmp_path / "progress.json",
                notify=False,
                token="sometoken",
            )

        assert seen_kwargs["token"] == "sometoken"

    def test_run_scan_builds_and_threads_a_real_rate_limiter_by_default(self, tmp_path):
        universe = [{"repo_name": "org/a", "language": "python", "clone_url": "x"}]
        seen_kwargs = {}

        def _fake_process_repo(repo, **kwargs):
            seen_kwargs.update(kwargs)
            return _scan_result(_repo_row(repo["repo_name"], repo["language"], "t", fetch_ok=True))

        with (
            patch("collection.rq5_agent_file_scan.load_corpus", return_value=universe),
            patch("collection.rq5_agent_file_scan.process_repos_graphql", side_effect=_per_repo(_fake_process_repo)),
        ):
            run_scan(snapshot_date="2026-09-08", 
                db_path=tmp_path / "rq5.db",
                workers=1,
                progress_path=tmp_path / "progress.json",
                notify=False,
            )

        assert isinstance(seen_kwargs["rate_limiter"], _RateLimiter)

    def test_run_scan_disables_throttling_when_target_is_falsy(self, tmp_path):
        universe = [{"repo_name": "org/a", "language": "python", "clone_url": "x"}]
        seen_kwargs = {}

        def _fake_process_repo(repo, **kwargs):
            seen_kwargs.update(kwargs)
            return _scan_result(_repo_row(repo["repo_name"], repo["language"], "t", fetch_ok=True))

        with (
            patch("collection.rq5_agent_file_scan.load_corpus", return_value=universe),
            patch("collection.rq5_agent_file_scan.process_repos_graphql", side_effect=_per_repo(_fake_process_repo)),
        ):
            run_scan(snapshot_date="2026-09-08", 
                db_path=tmp_path / "rq5.db",
                workers=1,
                progress_path=tmp_path / "progress.json",
                notify=False,
                target_requests_per_hour=None,
            )

        assert seen_kwargs["rate_limiter"] is None

    def test_run_scan_passes_the_same_loaded_catalog_to_every_repo(self, tmp_path):
        universe = [
            {"repo_name": "org/a", "language": "python", "clone_url": "x"},
            {"repo_name": "org/b", "language": "python", "clone_url": "y"},
        ]
        seen_catalogs = []

        def _fake_process_repo(repo, **kwargs):
            seen_catalogs.append(kwargs["catalog"])
            return _scan_result(_repo_row(repo["repo_name"], repo["language"], "t", fetch_ok=True))

        with (
            patch("collection.rq5_agent_file_scan.load_corpus", return_value=universe),
            patch("collection.rq5_agent_file_scan.process_repos_graphql", side_effect=_per_repo(_fake_process_repo)),
        ):
            run_scan(snapshot_date="2026-09-08", 
                db_path=tmp_path / "rq5.db",
                workers=1,
                progress_path=tmp_path / "progress.json",
                notify=False,
            )

        assert seen_catalogs[0] is seen_catalogs[1]
        assert seen_catalogs[0]["target_files"] == ["AGENTS.md", "CLAUDE.md"]

    def test_run_scan_writes_progress_file_with_correct_tallies(self, tmp_path):
        db_path = tmp_path / "rq5.db"
        progress_path = tmp_path / "progress.json"
        universe = [
            {"repo_name": "org/a", "language": "python", "clone_url": "x"},
            {"repo_name": "org/b", "language": "python", "clone_url": "y"},
        ]

        def _fake_process_repo(repo, **kwargs):
            ok = repo["repo_name"] == "org/a"
            row = _repo_row(
                repo["repo_name"],
                repo["language"],
                "t",
                fetch_ok=ok,
                error_reason=None if ok else "no_commit_at_or_before_cutoff",
                num_agent_files=1 if ok else 0,
            )
            files = (
                [
                    {
                        "repo_name": repo["repo_name"],
                        "file_name": "AGENTS.md",
                        "file_type": "AGENTS.md",
                        "language": repo["language"],
                        "commit_sha": "sha1",
                        "has_test": True,
                        "has_fixture": False,
                        "test_match_count": 1,
                        "fixture_match_count": 0,
                        "matched_test_keywords": "test",
                        "matched_fixture_keywords": "",
                        "github_url": "https://github.com/org/a/blob/sha1/AGENTS.md",
                    }
                ]
                if ok
                else []
            )
            return {"repo": row, "files": files, "matches": []}

        with (
            patch("collection.rq5_agent_file_scan.load_corpus", return_value=universe),
            patch("collection.rq5_agent_file_scan.process_repos_graphql", side_effect=_per_repo(_fake_process_repo)),
        ):
            run_scan(snapshot_date="2026-09-08", 
                db_path=db_path,
                workers=1,
                progress_path=progress_path,
                log_every=1,
                notify=False,
            )

        state = json.loads(progress_path.read_text())
        assert state["total_repos"] == 2
        assert state["completed_this_run"] == 2
        assert state["fetch_ok"] == 1
        assert state["fetch_failed"] == 1
        assert state["agent_files_found"] == 1


class TestRunScanNotifications:
    def _fake_process_repo(self, repo, **kwargs):
        return _scan_result(_repo_row(repo["repo_name"], repo["language"], "t", fetch_ok=True))

    def test_notifies_once_per_language_plus_one_final_push(self, tmp_path):
        universe = [
            {"repo_name": "org/py", "language": "python", "clone_url": "x"},
            {"repo_name": "org/js", "language": "javascript", "clone_url": "y"},
        ]
        notify_calls = []

        with (
            patch("collection.rq5_agent_file_scan.load_corpus", return_value=universe),
            patch("collection.rq5_agent_file_scan.process_repos_graphql", side_effect=_per_repo(self._fake_process_repo)),
            patch("collection.rq5_agent_file_scan._notify", side_effect=lambda msg: notify_calls.append(msg)),
        ):
            run_scan(snapshot_date="2026-09-08", 
                db_path=tmp_path / "rq5.db",
                workers=1,
                progress_path=tmp_path / "progress.json",
                notify=True,
            )

        assert len(notify_calls) == len(RQ5_LANGUAGES) + 1
        assert "all done" in notify_calls[-1]

    def test_no_notifications_when_notify_is_false(self, tmp_path):
        universe = [{"repo_name": "org/py", "language": "python", "clone_url": "x"}]

        with (
            patch("collection.rq5_agent_file_scan.load_corpus", return_value=universe),
            patch("collection.rq5_agent_file_scan.process_repos_graphql", side_effect=_per_repo(self._fake_process_repo)),
            patch("collection.rq5_agent_file_scan._notify") as notify_mock,
        ):
            run_scan(snapshot_date="2026-09-08", 
                db_path=tmp_path / "rq5.db",
                workers=1,
                progress_path=tmp_path / "progress.json",
                notify=False,
            )

        notify_mock.assert_not_called()


class TestLoadReposNeedingRetry:
    def test_missing_db_returns_empty_list(self, tmp_path):
        assert load_repos_needing_retry(db_path=tmp_path / "missing.db") == []

    def test_selects_only_matching_error_reasons_and_restores_language_and_url(self, tmp_path):
        db_path = tmp_path / "rq5.db"
        initialise_rq5_db(db_path)
        persist_result(
            _scan_result(_repo_row("org/a", "python", "t", fetch_ok=False, error_reason="rate_limited")),
            db_path,
        )
        persist_result(
            _scan_result(
                _repo_row("org/b", "python", "t", fetch_ok=False, error_reason="no_commit_at_or_before_cutoff")
            ),
            db_path,
        )
        persist_result(
            _scan_result(_repo_row("org/c", "python", "t", fetch_ok=False, error_reason="some_other_reason")),
            db_path,
        )
        persist_result(_scan_result(_repo_row("org/d", "python", "t", fetch_ok=True)), db_path)

        universe = [
            {"repo_name": "org/a", "language": "python", "clone_url": "url-a"},
            {"repo_name": "org/b", "language": "python", "clone_url": "url-b"},
            {"repo_name": "org/c", "language": "python", "clone_url": "url-c"},
            {"repo_name": "org/d", "language": "python", "clone_url": "url-d"},
        ]
        with patch("collection.rq5_agent_file_scan.load_corpus", return_value=universe):
            targets = load_repos_needing_retry(db_path=db_path)

        assert {t["repo_name"] for t in targets} == {"org/a", "org/b"}
        by_name = {t["repo_name"]: t for t in targets}
        assert by_name["org/a"]["clone_url"] == "url-a"

    def test_no_matching_rows_returns_empty_list(self, tmp_path):
        db_path = tmp_path / "rq5.db"
        initialise_rq5_db(db_path)
        persist_result(_scan_result(_repo_row("org/a", "python", "t", fetch_ok=True)), db_path)
        with patch("collection.rq5_agent_file_scan.load_corpus", return_value=[]):
            assert load_repos_needing_retry(db_path=db_path) == []

    def test_custom_error_reasons_narrows_selection(self, tmp_path):
        db_path = tmp_path / "rq5.db"
        initialise_rq5_db(db_path)
        persist_result(
            _scan_result(_repo_row("org/a", "python", "t", fetch_ok=False, error_reason="rate_limited")),
            db_path,
        )
        persist_result(
            _scan_result(_repo_row("org/b", "python", "t", fetch_ok=False, error_reason="timeout")), db_path
        )
        universe = [
            {"repo_name": "org/a", "language": "python", "clone_url": "url-a"},
            {"repo_name": "org/b", "language": "python", "clone_url": "url-b"},
        ]
        with patch("collection.rq5_agent_file_scan.load_corpus", return_value=universe):
            targets = load_repos_needing_retry(error_reasons=("rate_limited",), db_path=db_path)
        assert {t["repo_name"] for t in targets} == {"org/a"}

    def test_default_error_reasons_is_the_repairable_set(self):
        assert REPAIRABLE_ERROR_REASONS == (
            "no_commit_at_or_before_cutoff",
            "tree_fetch_failed",
            "timeout",
            "rate_limited",
        )


class TestRetryFailedRepos:
    def test_retries_only_selected_repos_and_upserts_results(self, tmp_path):
        db_path = tmp_path / "rq5.db"
        initialise_rq5_db(db_path)
        persist_result(
            _scan_result(
                _repo_row("org/a", "python", "t", fetch_ok=False, error_reason="no_commit_at_or_before_cutoff")
            ),
            db_path,
        )
        persist_result(
            _scan_result(_repo_row("org/untouched", "python", "t", fetch_ok=True, num_agent_files=1)),
            db_path,
        )

        universe = [
            {"repo_name": "org/a", "language": "python", "clone_url": "url-a"},
            {"repo_name": "org/untouched", "language": "python", "clone_url": "url-u"},
        ]

        def _fake_process_repo(repo, **kwargs):
            return _scan_result(
                _repo_row(repo["repo_name"], repo["language"], "t2", fetch_ok=True, num_agent_files=2)
            )

        with (
            patch("collection.rq5_agent_file_scan.load_corpus", return_value=universe),
            patch("collection.rq5_agent_file_scan.process_repo", side_effect=_fake_process_repo),
        ):
            counts = retry_failed_repos(snapshot_date="2026-09-08", db_path=db_path, workers=1, notify=False)

        assert counts == {"attempted": 1, "recovered": 1, "still_failed": 0}
        rows = {
            r[0]: (r[1], r[2])
            for r in sqlite3.connect(db_path).execute("SELECT repo_name, fetch_ok, num_agent_files FROM repo_scan")
        }
        assert rows["org/a"] == (1, 2)
        assert rows["org/untouched"] == (1, 1)  # never touched by the retry

    def test_still_failing_repos_are_counted_correctly(self, tmp_path):
        db_path = tmp_path / "rq5.db"
        initialise_rq5_db(db_path)
        persist_result(
            _scan_result(_repo_row("org/a", "python", "t", fetch_ok=False, error_reason="timeout")), db_path
        )
        universe = [{"repo_name": "org/a", "language": "python", "clone_url": "url-a"}]

        def _fake_process_repo(repo, **kwargs):
            return _scan_result(
                _repo_row(repo["repo_name"], repo["language"], "t2", fetch_ok=False, error_reason="rate_limited")
            )

        with (
            patch("collection.rq5_agent_file_scan.load_corpus", return_value=universe),
            patch("collection.rq5_agent_file_scan.process_repo", side_effect=_fake_process_repo),
        ):
            counts = retry_failed_repos(snapshot_date="2026-09-08", db_path=db_path, workers=1, notify=False)

        assert counts == {"attempted": 1, "recovered": 0, "still_failed": 1}

    def test_a_stuck_repo_is_recorded_as_timeout_not_hung(self, tmp_path):
        db_path = tmp_path / "rq5.db"
        initialise_rq5_db(db_path)
        persist_result(
            _scan_result(_repo_row("org/stuck", "python", "t", fetch_ok=False, error_reason="rate_limited")),
            db_path,
        )
        universe = [{"repo_name": "org/stuck", "language": "python", "clone_url": "url"}]
        stop_event = threading.Event()

        def _fake_process_repo(repo, **kwargs):
            stop_event.wait(5)
            return _scan_result(_repo_row(repo["repo_name"], repo["language"], "never", fetch_ok=True))

        try:
            with (
                patch("collection.rq5_agent_file_scan.load_corpus", return_value=universe),
                patch("collection.rq5_agent_file_scan.process_repo", side_effect=_fake_process_repo),
            ):
                counts = retry_failed_repos(snapshot_date="2026-09-08", 
                    db_path=db_path, workers=1, notify=False, process_repo_timeout_seconds=0.05
                )
        finally:
            stop_event.set()

        assert counts == {"attempted": 1, "recovered": 0, "still_failed": 1}
        row = sqlite3.connect(db_path).execute(
            "SELECT fetch_ok, error_reason FROM repo_scan WHERE repo_name='org/stuck'"
        ).fetchone()
        assert row == (0, "timeout")

    def test_notifies_with_a_recovery_summary(self, tmp_path):
        db_path = tmp_path / "rq5.db"
        initialise_rq5_db(db_path)
        persist_result(
            _scan_result(_repo_row("org/a", "python", "t", fetch_ok=False, error_reason="rate_limited")),
            db_path,
        )
        universe = [{"repo_name": "org/a", "language": "python", "clone_url": "url-a"}]

        def _fake_process_repo(repo, **kwargs):
            return _scan_result(_repo_row(repo["repo_name"], repo["language"], "t2", fetch_ok=True))

        notify_calls = []
        with (
            patch("collection.rq5_agent_file_scan.load_corpus", return_value=universe),
            patch("collection.rq5_agent_file_scan.process_repo", side_effect=_fake_process_repo),
            patch("collection.rq5_agent_file_scan._notify", side_effect=lambda msg: notify_calls.append(msg)),
        ):
            retry_failed_repos(snapshot_date="2026-09-08", db_path=db_path, workers=1, notify=True)

        assert len(notify_calls) == 1
        assert "1/1 repos recovered" in notify_calls[0]

    def test_threads_rate_limiter_and_token_through_to_process_repo(self, tmp_path):
        db_path = tmp_path / "rq5.db"
        initialise_rq5_db(db_path)
        persist_result(
            _scan_result(_repo_row("org/a", "python", "t", fetch_ok=False, error_reason="rate_limited")),
            db_path,
        )
        universe = [{"repo_name": "org/a", "language": "python", "clone_url": "url-a"}]
        seen_kwargs = {}

        def _fake_process_repo(repo, **kwargs):
            seen_kwargs.update(kwargs)
            return _scan_result(_repo_row(repo["repo_name"], repo["language"], "t2", fetch_ok=True))

        with (
            patch("collection.rq5_agent_file_scan.load_corpus", return_value=universe),
            patch("collection.rq5_agent_file_scan.process_repo", side_effect=_fake_process_repo),
        ):
            retry_failed_repos(snapshot_date="2026-09-08", db_path=db_path, workers=1, notify=False, token="sometoken")

        assert seen_kwargs["token"] == "sometoken"
        assert isinstance(seen_kwargs["rate_limiter"], _RateLimiter)


class TestMainCli:
    def _run_main_with_argv(self, argv):
        with (
            patch.object(sys, "argv", ["rq5_agent_file_scan.py", "--snapshot-date", "2026-09-08", *argv]),
            patch("collection.rq5_agent_file_scan.configure_logging"),
            patch("collection.rq5_agent_file_scan.add_file_logging"),
            patch("collection.rq5_agent_file_scan.write_review_outputs"),
            patch("collection.rq5_agent_file_scan.run_scan", return_value={}) as run_scan_mock,
        ):
            main()
        return run_scan_mock

    def test_defaults_to_twenty_workers(self):
        run_scan_mock = self._run_main_with_argv([])
        assert run_scan_mock.call_args.kwargs["workers"] == 20

    def test_workers_flag_is_threaded_through(self):
        run_scan_mock = self._run_main_with_argv(["--workers", "16"])
        assert run_scan_mock.call_args.kwargs["workers"] == 16

    def test_defaults_to_target_requests_per_hour_constant(self):
        run_scan_mock = self._run_main_with_argv([])
        assert run_scan_mock.call_args.kwargs["target_requests_per_hour"] == TARGET_REQUESTS_PER_HOUR

    def test_max_requests_per_hour_flag_is_threaded_through(self):
        run_scan_mock = self._run_main_with_argv(["--max-requests-per-hour", "2500"])
        assert run_scan_mock.call_args.kwargs["target_requests_per_hour"] == 2500.0

    def test_zero_max_requests_per_hour_disables_throttling(self):
        run_scan_mock = self._run_main_with_argv(["--max-requests-per-hour", "0"])
        assert run_scan_mock.call_args.kwargs["target_requests_per_hour"] is None

    def test_fixtures_dir_defaults_to_the_current_dataset_a_build(self):
        from collection.rq5_agent_file_scan import DATASET_A_FIXTURES_DIR

        run_scan_mock = self._run_main_with_argv([])
        assert run_scan_mock.call_args.kwargs["fixtures_dir"] == DATASET_A_FIXTURES_DIR

    def test_fixtures_dir_flag_points_the_corpus_at_an_earlier_build(self, tmp_path):
        run_scan_mock = self._run_main_with_argv(["--fixtures-dir", str(tmp_path)])
        assert run_scan_mock.call_args.kwargs["fixtures_dir"] == tmp_path

    def test_warns_when_no_token_is_available(self):
        with patch("collection.rq5_agent_file_scan.GITHUB_TOKEN", ""):
            with (
                patch.object(sys, "argv", ["rq5_agent_file_scan.py", "--snapshot-date", "2026-09-08"]),
                patch("collection.rq5_agent_file_scan.configure_logging"),
                patch("collection.rq5_agent_file_scan.add_file_logging"),
                patch("collection.rq5_agent_file_scan.write_review_outputs"),
                patch("collection.rq5_agent_file_scan.run_scan", return_value={}),
                patch("collection.rq5_agent_file_scan.logger") as logger_mock,
            ):
                main()
        logger_mock.warning.assert_called_once()

    def test_retry_failed_flag_calls_retry_failed_repos_instead_of_run_scan(self):
        with (
            patch.object(sys, "argv", ["rq5_agent_file_scan.py", "--snapshot-date", "2026-09-08", "--retry-failed"]),
            patch("collection.rq5_agent_file_scan.configure_logging"),
            patch("collection.rq5_agent_file_scan.add_file_logging"),
            patch("collection.rq5_agent_file_scan.write_review_outputs"),
            patch("collection.rq5_agent_file_scan.run_scan") as run_scan_mock,
            patch("collection.rq5_agent_file_scan.retry_failed_repos", return_value={}) as retry_mock,
        ):
            main()

        retry_mock.assert_called_once()
        run_scan_mock.assert_not_called()

    def test_retry_failed_threads_workers_and_rate_through(self):
        with (
            patch.object(sys, "argv", ["rq5_agent_file_scan.py", "--snapshot-date", "2026-09-08", "--retry-failed", "--workers", "16"]),
            patch("collection.rq5_agent_file_scan.configure_logging"),
            patch("collection.rq5_agent_file_scan.add_file_logging"),
            patch("collection.rq5_agent_file_scan.write_review_outputs"),
            patch("collection.rq5_agent_file_scan.retry_failed_repos", return_value={}) as retry_mock,
        ):
            main()

        assert retry_mock.call_args.kwargs["workers"] == 16
        assert retry_mock.call_args.kwargs["target_requests_per_hour"] == TARGET_REQUESTS_PER_HOUR
