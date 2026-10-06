"""RQ5 GraphQL batch path: the same records as the REST path, in fewer requests.

Each scenario is described once and served twice: through the REST endpoints
that `process_repo()` calls, and through the GraphQL payload that
`process_repos_graphql()` reads. The two results must agree.
"""

import re
from unittest.mock import patch

import pytest

from collection.rq5_agent_file_scan import (
    GraphQLError,
    _cutoff_query,
    initialise_rq5_db,
    load_scanned_repo_names,
    process_repo,
    process_repos_graphql,
    run_scan,
)
from tests.collection.test_rq5_agent_file_scan import (
    _TEST_CATALOG,
    _blob_json,
    _commit_json,
    _fake_response,
    _route,
    _tree_entry,
)

SNAPSHOT = "2026-09-08"
AGENT_TEXT = "Always run pytest.\nUse the fixture setup for shared data."


def _graphql_node(commit_sha, tree_entries, date="2026-09-08T12:00:00Z"):
    return {
        "defaultBranchRef": {
            "target": {
                "history": {
                    "nodes": [
                        {
                            "oid": commit_sha,
                            "authoredDate": date,
                            "tree": {
                                "entries": [
                                    {"name": e["path"], "type": e["type"], "oid": e["sha"]} for e in tree_entries
                                ]
                            },
                        }
                    ]
                }
            }
        }
    }


def _scenarios():
    """name -> the REST responses and the GraphQL node describing the same repository."""
    return {
        "root_agent_file": {
            "commits": [_commit_json("c1")],
            "trees": {"c1": [_tree_entry("AGENTS.md", "b1"), _tree_entry("README.md", "b2")]},
            "blobs": {"b1": _blob_json(AGENT_TEXT), "b2": _blob_json("unrelated readme")},
            "node": _graphql_node("c1", [_tree_entry("AGENTS.md", "b1"), _tree_entry("README.md", "b2")]),
            "texts": {"b1": AGENT_TEXT, "b2": "unrelated readme"},
        },
        "no_commit_on_branch": {
            "commits": [],
            "trees": {},
            "blobs": {},
            "node": {"defaultBranchRef": None},
        },
        "empty_tree": {
            "commits": [_commit_json("c2")],
            "trees": {"c2": []},
            "blobs": {},
            "node": _graphql_node("c2", []),
        },
        "directory_named_like_a_target": {
            "commits": [_commit_json("c3")],
            "trees": {"c3": [_tree_entry("CLAUDE.md", "d1", type_="tree", mode="040000")]},
            "blobs": {},
            "node": _graphql_node("c3", [_tree_entry("CLAUDE.md", "d1", type_="tree", mode="040000")]),
        },
        "binary_blob_is_unreadable": {
            "commits": [_commit_json("c4")],
            "trees": {"c4": [_tree_entry("AGENTS.md", "b9")]},
            "blobs": {"b9": {"content": "", "encoding": "none"}},
            "node": _graphql_node("c4", [_tree_entry("AGENTS.md", "b9")]),
            "texts": {"b9": None},
        },
        "truncated_text_is_reread_in_full": {
            "commits": [_commit_json("c5")],
            "trees": {"c5": [_tree_entry("AGENTS.md", "b5")]},
            "blobs": {"b5": _blob_json(AGENT_TEXT)},
            "node": _graphql_node("c5", [_tree_entry("AGENTS.md", "b5")]),
            "texts": {"b5": "Always run pyt"},
            "truncated": {"b5"},
        },
        "file_name_case_is_preserved": {
            "commits": [_commit_json("c6")],
            "trees": {"c6": [_tree_entry("claude.md", "b6")]},
            "blobs": {"b6": _blob_json(AGENT_TEXT)},
            "node": _graphql_node("c6", [_tree_entry("claude.md", "b6")]),
            "texts": {"b6": AGENT_TEXT},
        },
    }


def _repo(name):
    return {"repo_name": name, "language": "python"}


def _graphql_fake(scenarios):
    """Stands in for requests.post. Answers the cutoff query and the blob query
    from the scenario table, and recognises missing repositories as NOT_FOUND."""
    by_repo = {f"org/{name}": spec for name, spec in scenarios.items()}

    def _post(url, json=None, headers=None, timeout=None):
        query = json["query"]
        if "$until" in query:
            data, errors = {}, []
            for alias, owner, name in re.findall(r'(r\d+): repository\(owner: "([^"]+)", name: "([^"]+)"\)', query):
                repo_name = f"{owner}/{name}"
                if repo_name not in by_repo:
                    data[alias] = None
                    errors.append({"type": "NOT_FOUND", "path": [alias]})
                else:
                    data[alias] = by_repo[repo_name]["node"]
            return _fake_response(200, {"data": data, "errors": errors} if errors else {"data": data})
        data = {}
        for alias, owner, name, oid in re.findall(
            r'(b\d+): repository\(owner: "([^"]+)", name: "([^"]+)"\) \{ object\(oid: "([^"]+)"\)', query
        ):
            repo_name = f"{owner}/{name}"
            spec = by_repo[repo_name]
            text = spec.get("texts", {}).get(oid)
            truncated = oid in spec.get("truncated", set())
            binary = oid in spec.get("texts", {}) and text is None
            data[alias] = {"object": {"text": text, "isBinary": binary, "isTruncated": truncated}}
        return _fake_response(200, {"data": data})

    return _post


def _canonical_result(result):
    repo = dict(result["repo"])
    repo.pop("scanned_at", None)
    files = sorted((sorted(f.items()) for f in result["files"]), key=str)
    matches = sorted((sorted(m.items()) for m in result["matches"]), key=str)
    return {"repo": sorted(repo.items()), "files": files, "matches": matches}


class TestGraphqlMatchesRest:
    @pytest.fixture
    def compared(self):
        scenarios = _scenarios()
        rest_results = {}
        for name, spec in scenarios.items():
            route = _route(commits=spec["commits"], trees=spec["trees"], blobs=spec["blobs"])
            with patch("collection.rq5_agent_file_scan.requests.get", side_effect=route):
                rest_results[name] = process_repo(
                    _repo(f"org/{name}"), snapshot_date=SNAPSHOT, token="t", catalog=_TEST_CATALOG
                )
        all_blobs = {}
        for spec in scenarios.values():
            all_blobs.update(spec["blobs"])
        # Only a truncated blob is read through REST during the GraphQL run.
        with patch(
            "collection.rq5_agent_file_scan.requests.post", side_effect=_graphql_fake(scenarios)
        ), patch("collection.rq5_agent_file_scan.requests.get", side_effect=_route(blobs=all_blobs)):
            batch = process_repos_graphql(
                [_repo(f"org/{name}") for name in scenarios],
                snapshot_date=SNAPSHOT,
                token="t",
                catalog=_TEST_CATALOG,
            )
        gql_results = {result["repo"]["repo_name"]: result for result in batch}
        return {name: (rest_results[name], gql_results[f"org/{name}"]) for name in scenarios}

    @pytest.mark.parametrize("name", list(_scenarios()))
    def test_same_repository_row_and_files_as_the_rest_path(self, compared, name):
        rest, gql = compared[name]
        assert _canonical_result(gql) == _canonical_result(rest)

    def test_root_agent_file_produces_the_expected_matches(self, compared):
        _, gql = compared["root_agent_file"]
        assert gql["repo"]["fetch_ok"] == 1
        assert gql["repo"]["commit_sha"] == "c1"
        assert gql["repo"]["commit_date"] == "2026-09-08"
        [agent] = gql["files"]
        assert agent["file_name"] == "AGENTS.md"
        assert agent["has_test"] and agent["has_fixture"]
        assert {m["keyword_list"] for m in gql["matches"]} == {"test", "fixture"}

    def test_missing_branch_is_recorded_like_the_rest_path(self, compared):
        _, gql = compared["no_commit_on_branch"]
        assert gql["repo"]["error_reason"] == "no_commit_at_or_before_cutoff"

    def test_file_name_keeps_the_case_the_repository_used(self, compared):
        _, gql = compared["file_name_case_is_preserved"]
        assert gql["files"][0]["file_name"] == "claude.md"
        assert gql["files"][0]["file_type"] == "CLAUDE.md"


class TestMissingRepositoryInBatch:
    def test_not_found_alias_is_recorded_as_no_commit_and_does_not_fail_the_batch(self):
        scenarios = _scenarios()
        repos = [_repo("org/root_agent_file"), _repo("org/ghost")]
        with patch("collection.rq5_agent_file_scan.requests.post", side_effect=_graphql_fake(scenarios)):
            results = {
                r["repo"]["repo_name"]: r
                for r in process_repos_graphql(repos, snapshot_date=SNAPSHOT, token="t", catalog=_TEST_CATALOG)
            }
        assert results["org/root_agent_file"]["repo"]["fetch_ok"] == 1
        assert results["org/ghost"]["repo"]["error_reason"] == "no_commit_at_or_before_cutoff"


class TestBatchRequestCount:
    def test_a_batch_costs_two_graphql_requests_regardless_of_size(self):
        scenarios = _scenarios()
        post = patch("collection.rq5_agent_file_scan.requests.post", side_effect=_graphql_fake(scenarios))
        with post as mocked:
            process_repos_graphql(
                [_repo(f"org/{name}") for name in scenarios], snapshot_date=SNAPSHOT, token="t", catalog=_TEST_CATALOG
            )
        assert mocked.call_count == 2

    def test_cutoff_query_has_one_alias_per_repository_and_the_until_variable(self):
        query = _cutoff_query([_repo("owner/a"), _repo("owner/b")], SNAPSHOT)
        assert query.startswith("query($until: GitTimestamp!)")
        assert 'r0: repository(owner: "owner", name: "a")' in query
        assert 'r1: repository(owner: "owner", name: "b")' in query
        assert "history(first: 1, until: $until)" in query


class TestBatchFailures:
    def _run(self, post_side_effect):
        repos = [_repo("org/root_agent_file"), _repo("org/empty_tree")]
        with patch("collection.rq5_agent_file_scan.requests.post", side_effect=post_side_effect), patch(
            "collection.rq5_agent_file_scan.time.sleep"
        ):
            return process_repos_graphql(repos, snapshot_date=SNAPSHOT, token="t", catalog=_TEST_CATALOG)

    def test_transport_error_marks_every_repository_in_the_batch_as_retryable(self):
        import requests

        results = self._run(requests.ConnectionError("reset"))
        assert [r["repo"]["error_reason"] for r in results] == ["tree_fetch_failed", "tree_fetch_failed"]
        assert all(r["repo"]["fetch_ok"] == 0 for r in results)

    def test_http_error_marks_the_batch_as_retryable(self):
        results = self._run(lambda *a, **k: _fake_response(502, {"message": "Bad Gateway"}))
        assert {r["repo"]["error_reason"] for r in results} == {"tree_fetch_failed"}

    def test_rate_limit_error_in_the_body_is_retried_then_recorded_as_rate_limited(self):
        limited = {"data": None, "errors": [{"type": "RATE_LIMITED", "message": "limit"}]}
        results = self._run(lambda *a, **k: _fake_response(200, limited))
        assert {r["repo"]["error_reason"] for r in results} == {"rate_limited"}

    def test_rate_limit_then_success_recovers_without_losing_the_batch(self):
        scenarios = _scenarios()
        good = _graphql_fake(scenarios)
        limited = _fake_response(200, {"data": None, "errors": [{"type": "RATE_LIMITED"}]})
        calls = {"n": 0}

        def _flaky(url, json=None, headers=None, timeout=None):
            calls["n"] += 1
            if calls["n"] == 1:
                return limited
            return good(url, json=json, headers=headers, timeout=timeout)

        with patch("collection.rq5_agent_file_scan.requests.post", side_effect=_flaky), patch(
            "collection.rq5_agent_file_scan.time.sleep"
        ):
            results = process_repos_graphql(
                [_repo("org/root_agent_file")], snapshot_date=SNAPSHOT, token="t", catalog=_TEST_CATALOG
            )
        assert results[0]["repo"]["fetch_ok"] == 1

    def test_non_json_body_raises_graphql_error_inside_the_helper(self):
        from collection.rq5_agent_file_scan import _graphql_post

        bad = _fake_response(200, None)
        bad._content = b"<html>"
        with patch("collection.rq5_agent_file_scan.requests.post", return_value=bad):
            with pytest.raises(GraphQLError):
                _graphql_post("query { x }", {}, token="t", rate_limiter=None)


class TestRunScanUsesBatches:
    def test_repositories_are_sent_in_batches_of_the_given_size(self, tmp_path):
        db_path = tmp_path / "rq5.db"
        initialise_rq5_db(db_path)
        universe = [_repo(f"org/r{i}") | {"clone_url": "x"} for i in range(60)]
        batch_sizes = []

        def _fake_batch(batch, **kwargs):
            batch_sizes.append(len(batch))
            return [
                {"repo": {"repo_name": r["repo_name"], "language": "python", "fetch_ok": 1, "commit_sha": "c",
                          "commit_date": "2026-01-01", "num_agent_files": 0,
                          "error_reason": None, "scanned_at": "t"},
                 "files": [], "matches": []}
                for r in batch
            ]

        with patch("collection.rq5_agent_file_scan.load_corpus", return_value=universe), patch(
            "collection.rq5_agent_file_scan.process_repos_graphql", side_effect=_fake_batch
        ):
            counts = run_scan(
                snapshot_date=SNAPSHOT,
                db_path=db_path,
                workers=1,
                progress_path=tmp_path / "progress.json",
                notify=False,
                batch_size=25,
            )

        assert sorted(batch_sizes) == [10, 25, 25]
        assert counts["scanned_this_run"] == 60
        assert len(load_scanned_repo_names(db_path)) == 60
