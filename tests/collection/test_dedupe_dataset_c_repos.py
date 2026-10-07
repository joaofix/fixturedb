from __future__ import annotations

import csv
from unittest.mock import Mock

import pytest
import requests

from collection.dedupe_dataset_c_repos import (
    OUTPUT_FIELDNAMES,
    CommitLookupUnavailable,
    fetch_reference_commit_sha,
    find_duplicate_clusters,
    write_duplicate_repos_csv,
)


def _repo(name, language, stars, github_id):
    return {"repo_name": name, "language": language, "stars": stars, "github_id": github_id}


class TestFindDuplicateClusters:
    def test_cluster_of_two_produces_one_removal_row(self, tmp_path):
        repos = [
            _repo("owner/low-stars", "python", 10, 2),
            _repo("owner/high-stars", "python", 100, 1),
        ]
        fake_sha = {"owner/low-stars": "abc123", "owner/high-stars": "abc123"}

        rows = find_duplicate_clusters(
            repos,
            reference_date="2020-12-31",
            github_token="fake",
            checkpoint_path=tmp_path / "checkpoint.json",
            fetch_fn=lambda name, ref, token: fake_sha[name],
        )

        assert len(rows) == 1
        assert rows[0]["repo_to_remove"] == "owner/low-stars"
        assert rows[0]["repo_to_keep"] == "owner/high-stars"
        assert rows[0]["shared_commit_sha"] == "abc123"
        assert rows[0]["cluster_size"] == 2

    def test_cluster_of_five_keeps_only_highest_stars(self, tmp_path):
        repos = [_repo(f"owner/repo{i}", "java", stars, 100 + i) for i, stars in enumerate([10, 50, 999, 20, 5])]
        rows = find_duplicate_clusters(
            repos,
            reference_date="2020-12-31",
            github_token="fake",
            checkpoint_path=tmp_path / "checkpoint.json",
            fetch_fn=lambda name, ref, token: "same-sha",
        )
        removed = {r["repo_to_remove"] for r in rows}
        assert removed == {"owner/repo0", "owner/repo1", "owner/repo3", "owner/repo4"}
        assert all(r["repo_to_keep"] == "owner/repo2" for r in rows)
        assert all(r["cluster_size"] == 5 for r in rows)

    def test_singletons_produce_no_output(self, tmp_path):
        repos = [
            _repo("owner/a", "python", 10, 1),
            _repo("owner/b", "python", 20, 2),
        ]
        rows = find_duplicate_clusters(
            repos,
            reference_date="2020-12-31",
            github_token="fake",
            checkpoint_path=tmp_path / "checkpoint.json",
            fetch_fn=lambda name, ref, token: {"owner/a": "sha-a", "owner/b": "sha-b"}[name],
        )
        assert rows == []

    def test_lookup_failure_never_causes_a_drop(self, tmp_path):
        repos = [
            _repo("owner/a", "python", 10, 1),
            _repo("owner/b", "python", 20, 2),
        ]
        rows = find_duplicate_clusters(
            repos,
            reference_date="2020-12-31",
            github_token="fake",
            checkpoint_path=tmp_path / "checkpoint.json",
            fetch_fn=lambda name, ref, token: None,
        )
        assert rows == []

    def test_lookup_unavailable_never_causes_a_drop_and_is_not_checkpointed(self, tmp_path):
        """A transient failure (CommitLookupUnavailable) must be treated as
        'keep this repo' for the current run, same as a definitive None --
        but, unlike a definitive None, must NOT be written to the
        checkpoint, so it's retried on the next invocation instead of being
        permanently miscached as 'no duplicate' (the real bug this covers:
        two Dataset C repos were cached this way, hiding a genuine
        shared-commit duplicate from every subsequent run)."""
        repos = [
            _repo("owner/a", "python", 10, 1),
            _repo("owner/b", "python", 20, 2),
        ]
        checkpoint_path = tmp_path / "checkpoint.json"

        def flaky_fetch(name, ref, token):
            if name == "owner/a":
                raise CommitLookupUnavailable("rate limited")
            return "same-sha"

        rows = find_duplicate_clusters(
            repos,
            reference_date="2020-12-31",
            github_token="fake",
            checkpoint_path=checkpoint_path,
            fetch_fn=flaky_fetch,
        )
        assert rows == []  # owner/a's failure means it's never clustered with owner/b

        import json

        checkpoint = json.loads(checkpoint_path.read_text())
        assert "owner/a" not in checkpoint  # not cached -- must be retried next run
        assert checkpoint["owner/b"] == "same-sha"

    def test_checkpoint_resume_does_not_refetch(self, tmp_path):
        repos = [
            _repo("owner/a", "python", 10, 1),
            _repo("owner/b", "python", 20, 2),
        ]
        checkpoint_path = tmp_path / "checkpoint.json"
        call_log = []

        def fetch(name, ref, token):
            call_log.append(name)
            return "same-sha"

        find_duplicate_clusters(
            repos,
            reference_date="2020-12-31",
            github_token="fake",
            checkpoint_path=checkpoint_path,
            fetch_fn=fetch,
        )
        assert sorted(call_log) == ["owner/a", "owner/b"]

        call_log.clear()
        rows = find_duplicate_clusters(
            repos,
            reference_date="2020-12-31",
            github_token="fake",
            checkpoint_path=checkpoint_path,
            fetch_fn=fetch,
        )
        assert call_log == []  # nothing re-fetched
        assert len(rows) == 1


class TestWriteDuplicateReposCsv:
    def test_round_trip(self, tmp_path):
        rows = [
            {
                "repo_to_remove": "owner/dup",
                "repo_to_keep": "owner/original",
                "shared_commit_sha": "abc123",
                "cluster_size": 2,
                "language": "python",
                "stars_removed": 5,
                "stars_kept": 50,
            }
        ]
        out_path = tmp_path / "duplicate_repos.csv"
        write_duplicate_repos_csv(rows, out_path)

        with out_path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            assert reader.fieldnames == OUTPUT_FIELDNAMES
            read_rows = list(reader)
        assert read_rows[0]["repo_to_remove"] == "owner/dup"
        assert read_rows[0]["repo_to_keep"] == "owner/original"


class TestFetchReferenceCommitSha:
    def test_returns_sha_from_first_result(self, monkeypatch):
        response = Mock()
        response.raise_for_status = Mock()
        response.json.return_value = [{"sha": "deadbeef"}]
        monkeypatch.setattr(requests, "get", lambda *a, **k: response)

        sha = fetch_reference_commit_sha("owner/repo", "2020-12-31", "fake-token")
        assert sha == "deadbeef"

    def test_empty_result_returns_none(self, monkeypatch):
        response = Mock()
        response.raise_for_status = Mock()
        response.json.return_value = []
        monkeypatch.setattr(requests, "get", lambda *a, **k: response)

        assert fetch_reference_commit_sha("owner/repo", "2020-12-31", "fake-token") is None

    def test_retries_on_rate_limit_then_succeeds(self, monkeypatch):
        rate_limited_response = Mock()
        rate_limited_response.status_code = 403
        rate_limited_response.headers = {"X-RateLimit-Remaining": "0"}

        success_response = Mock()
        success_response.raise_for_status = Mock()
        success_response.json.return_value = [{"sha": "recovered-sha"}]

        rate_limit_error = requests.HTTPError(response=rate_limited_response)

        call_count = {"n": 0}

        def fake_get(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                error_response = Mock()
                error_response.raise_for_status = Mock(side_effect=rate_limit_error)
                error_response.status_code = 403
                error_response.headers = {"X-RateLimit-Remaining": "0"}
                return error_response
            return success_response

        monkeypatch.setattr(requests, "get", fake_get)
        monkeypatch.setattr("time.sleep", lambda _: None)

        sha = fetch_reference_commit_sha(
            "owner/repo", "2020-12-31", "fake-token", max_retries=2
        )
        assert sha == "recovered-sha"
        assert call_count["n"] == 2

    def test_404_returns_none_without_retry(self, monkeypatch):
        error_response = Mock()
        error_response.status_code = 404
        error_response.headers = {}

        def fake_get(*args, **kwargs):
            resp = Mock()
            resp.raise_for_status = Mock(
                side_effect=requests.HTTPError(response=error_response)
            )
            return resp

        monkeypatch.setattr(requests, "get", fake_get)
        assert fetch_reference_commit_sha("owner/repo", "2020-12-31", "fake-token") is None

    def test_rate_limit_exhausted_raises_lookup_unavailable_not_none(self, monkeypatch):
        """A None here (the old behavior) is indistinguishable from a
        confirmed 404 and gets permanently cached -- must raise instead so
        the caller knows to retry later, not cache a false negative."""
        rate_limited_response = Mock()
        rate_limited_response.status_code = 403
        rate_limited_response.headers = {"X-RateLimit-Remaining": "0"}

        def fake_get(*args, **kwargs):
            resp = Mock()
            resp.raise_for_status = Mock(
                side_effect=requests.HTTPError(response=rate_limited_response)
            )
            resp.status_code = 403
            resp.headers = {"X-RateLimit-Remaining": "0"}
            return resp

        monkeypatch.setattr(requests, "get", fake_get)
        monkeypatch.setattr("time.sleep", lambda _: None)

        with pytest.raises(CommitLookupUnavailable):
            fetch_reference_commit_sha("owner/repo", "2020-12-31", "fake-token", max_retries=1)

    def test_network_error_raises_lookup_unavailable_not_none(self, monkeypatch):
        def fake_get(*args, **kwargs):
            raise requests.ConnectionError("connection reset")

        monkeypatch.setattr(requests, "get", fake_get)

        with pytest.raises(CommitLookupUnavailable):
            fetch_reference_commit_sha("owner/repo", "2020-12-31", "fake-token")


class TestProgressLogging:
    """The dedupe run must say how far it is, so a long run can be followed from its log."""

    def _repos(self, n):
        return [{"repo_name": f"owner/r{i}", "language": "python", "stars": 1, "github_id": i} for i in range(n)]

    def test_logs_progress_during_the_run_and_a_final_summary(self, tmp_path, caplog):
        import logging

        from collection.dedupe_dataset_c_repos import CommitLookupUnavailable

        def fetch(name, date, token):
            if name == "owner/r3":
                raise CommitLookupUnavailable("rate limited")
            return "sha-same" if name in ("owner/r0", "owner/r1") else f"sha-{name}"

        with caplog.at_level(logging.INFO, logger="collection.dedupe_dataset_c_repos"):
            find_duplicate_clusters(
                self._repos(10),
                reference_date="2020-12-31",
                github_token="t",
                checkpoint_path=tmp_path / "ck.json",
                fetch_fn=fetch,
                log_every=4,
            )

        messages = [r.getMessage() for r in caplog.records]
        progress = [m for m in messages if "lookups" in m and "/" in m]
        assert progress, messages
        assert any("4/10" in m for m in progress)
        assert any("ETA" in m for m in progress)
        summary = [m for m in messages if "summary" in m]
        assert summary and "10 repositories" in summary[-1]
        assert "1 unavailable" in summary[-1]

    def test_cached_repositories_are_reported_separately_from_new_lookups(self, tmp_path, caplog):
        import logging

        ck = tmp_path / "ck.json"
        ck.write_text('{"owner/r0": "sha-a", "owner/r1": "sha-b"}', encoding="utf-8")
        calls = []

        def fetch(name, date, token):
            calls.append(name)
            return f"sha-{name}"

        with caplog.at_level(logging.INFO, logger="collection.dedupe_dataset_c_repos"):
            find_duplicate_clusters(
                self._repos(4), reference_date="2020-12-31", github_token="t",
                checkpoint_path=ck, fetch_fn=fetch, log_every=100,
            )

        assert calls == ["owner/r2", "owner/r3"]
        assert any("2 already resolved" in r.getMessage() for r in caplog.records)


def test_progress_is_logged_every_thousand_lookups_by_default():
    import inspect

    from collection.dedupe_dataset_c_repos import find_duplicate_clusters as f

    assert inspect.signature(f).parameters["log_every"].default == 1000


class TestRequestPacer:
    """The dedupe stays under a per-hour request budget, however many lookups run."""

    def _clock(self):
        state = {"now": 0.0, "slept": []}

        def clock():
            return state["now"]

        def sleep(seconds):
            state["slept"].append(seconds)
            state["now"] += seconds

        return state, clock, sleep

    def test_spaces_requests_evenly_across_the_hour_budget(self):
        from collection.dedupe_dataset_c_repos import RequestPacer

        state, clock, sleep = self._clock()
        pacer = RequestPacer(3600, clock=clock, sleep=sleep)  # one request per second
        for _ in range(4):
            pacer.acquire()
        assert state["slept"] == [1.0, 1.0, 1.0]

    def test_a_pause_longer_than_the_interval_does_not_build_up_a_burst(self):
        from collection.dedupe_dataset_c_repos import RequestPacer

        state, clock, sleep = self._clock()
        pacer = RequestPacer(3600, clock=clock, sleep=sleep)
        pacer.acquire()
        state["now"] += 100.0  # a long pause
        pacer.acquire()
        pacer.acquire()
        assert state["slept"] == [1.0]  # the pause is not banked into a burst of requests

    def test_every_rest_attempt_is_paced_including_retries(self, monkeypatch):
        from collection import dedupe_dataset_c_repos as dd

        class _Pacer:
            calls = 0

            def acquire(self):
                _Pacer.calls += 1

        class _Resp:
            status_code = 429  # a rate-limit response, which is the case that retries
            headers = {"Retry-After": "0"}

            def raise_for_status(self):
                raise requests.HTTPError(response=self)

            def json(self):
                return []

        monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp())
        monkeypatch.setattr("time.sleep", lambda _: None)
        with pytest.raises(dd.CommitLookupUnavailable):
            dd.fetch_reference_commit_sha("owner/repo", "2020-12-31", "t", max_retries=2, pacer=_Pacer())
        assert _Pacer.calls == 3  # the first attempt and both retries

    def test_find_duplicate_clusters_passes_the_pacer_to_each_lookup(self, tmp_path):
        from collection.dedupe_dataset_c_repos import RequestPacer

        seen = []

        def fetch(name, date, token, pacer=None):
            seen.append(pacer)
            return f"sha-{name}"

        marker = object()
        find_duplicate_clusters(
            [{"repo_name": "owner/a", "language": "python", "stars": 1, "github_id": 1}],
            reference_date="2020-12-31",
            github_token="t",
            checkpoint_path=tmp_path / "ck.json",
            fetch_fn=fetch,
            pacer=marker,
        )
        assert seen == [marker]


def test_default_request_budget_stays_below_githubs_hourly_limit():
    from collection.dedupe_dataset_c_repos import DEFAULT_MAX_REQUESTS_PER_HOUR, build_parser

    assert 0 < DEFAULT_MAX_REQUESTS_PER_HOUR < 5000
    assert build_parser().parse_args([]).max_requests_per_hour == DEFAULT_MAX_REQUESTS_PER_HOUR


class TestGraphqlLookup:
    """The GraphQL lookup answers the same question as the REST one, in batches."""

    def _payload(self, data, errors=None):
        return {"data": data, **({"errors": errors} if errors else {})}

    def test_batch_returns_each_repositorys_default_branch_commit_at_the_cutoff(self, monkeypatch):
        from collection import dedupe_dataset_c_repos as dd

        seen = {}

        def post(query, variables, *, token, rate_limiter):
            seen["query"] = query
            seen["variables"] = variables
            return self._payload({
                "r0": {"defaultBranchRef": {"target": {"history": {"nodes": [{"oid": "sha-a"}]}}}},
                "r1": {"defaultBranchRef": {"target": {"history": {"nodes": [{"oid": "sha-b"}]}}}},
            })

        monkeypatch.setattr(dd, "_graphql_post", post)
        out = dd.fetch_reference_commit_shas_graphql(["owner/a", "owner/b"], "2020-12-31", "t")

        assert out == {"owner/a": "sha-a", "owner/b": "sha-b"}
        assert seen["variables"] == {"until": "2020-12-31T23:59:59Z"}
        assert 'r0: repository(owner: "owner", name: "a")' in seen["query"]
        assert "history(first: 1, until: $until)" in seen["query"]

    def test_missing_repository_is_a_definitive_none_and_other_errors_are_unavailable(self, monkeypatch):
        from collection import dedupe_dataset_c_repos as dd

        def post(query, variables, *, token, rate_limiter):
            return self._payload(
                {"r0": None, "r1": None, "r2": {"defaultBranchRef": None}},
                errors=[{"type": "NOT_FOUND", "path": ["r0"]}, {"type": "SOMETHING", "path": ["r1"]}],
            )

        monkeypatch.setattr(dd, "_graphql_post", post)
        out = dd.fetch_reference_commit_shas_graphql(["o/gone", "o/broken", "o/empty"], "2020-12-31", "t")

        assert out["o/gone"] is None
        assert out["o/broken"] is dd.UNAVAILABLE
        assert out["o/empty"] is None  # no default branch: no commit at the cutoff

    def test_a_failed_request_marks_the_whole_batch_unavailable(self, monkeypatch):
        from collection import dedupe_dataset_c_repos as dd
        from collection.rq5_agent_file_scan import RateLimitExhausted

        def post(query, variables, *, token, rate_limiter):
            raise RateLimitExhausted("graphql")

        monkeypatch.setattr(dd, "_graphql_post", post)
        out = dd.fetch_reference_commit_shas_graphql(["o/a", "o/b"], "2020-12-31", "t")
        assert out == {"o/a": dd.UNAVAILABLE, "o/b": dd.UNAVAILABLE}

    def test_find_duplicate_clusters_in_graphql_batches_with_the_same_checkpoint(self, tmp_path, monkeypatch):
        from collection import dedupe_dataset_c_repos as dd

        batches = []

        def batch_fetch(names, date, token, *, pacer=None):
            batches.append(list(names))
            return {n: f"sha-{n}" for n in names}

        repos = [{"repo_name": f"o/r{i}", "language": "python", "stars": 1, "github_id": i} for i in range(7)]
        ck = tmp_path / "ck.json"
        find_duplicate_clusters(
            repos, reference_date="2020-12-31", github_token="t", checkpoint_path=ck,
            batch_fetch_fn=batch_fetch, batch_size=3,
        )

        assert [len(b) for b in batches] == [3, 3, 1]
        import json as _json

        assert set(_json.loads(ck.read_text())) == {f"o/r{i}" for i in range(7)}

    def test_unavailable_in_a_batch_is_not_checkpointed(self, tmp_path):
        from collection import dedupe_dataset_c_repos as dd

        def batch_fetch(names, date, token, *, pacer=None):
            return {n: dd.UNAVAILABLE for n in names}

        repos = [{"repo_name": "o/x", "language": "python", "stars": 1, "github_id": 1}]
        ck = tmp_path / "ck.json"
        rows = find_duplicate_clusters(
            repos, reference_date="2020-12-31", github_token="t", checkpoint_path=ck,
            batch_fetch_fn=batch_fetch,
        )
        assert rows == []
        assert not ck.exists() or "o/x" not in ck.read_text()

    def test_lookup_option_defaults_to_rest_and_accepts_graphql(self):
        from collection.dedupe_dataset_c_repos import build_parser

        assert build_parser().parse_args([]).lookup == "rest"
        assert build_parser().parse_args(["--lookup", "graphql"]).lookup == "graphql"
