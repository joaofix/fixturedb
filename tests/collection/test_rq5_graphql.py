"""RQ5 batch scan, end to end against a fake GitHub.

Each scenario is a repository described as `{path: text}` at its snapshot
commit. The fake answers every request `process_repos_graphql()` sends -- the
GraphQL snapshot commit with its root tree, file texts by blob id and directory
listings by `<commit>:<path>`, and the REST recursive tree -- from that
description, so the real request building and parsing run unchanged.
"""

import re
from unittest.mock import patch

import pytest

from collection.rq5_agent_file_scan import (
    GRAPHQL_MAX_ALIASES,
    GraphQLError,
    _cutoff_query,
    initialise_rq5_db,
    load_scanned_repo_names,
    process_repos_graphql,
    run_scan,
)
from tests.collection.test_rq5_agent_file_scan import (
    _TEST_CATALOG,
    _blob_json,
    _fake_response,
    _route,
)

SNAPSHOT = "2026-09-08"
AGENT_TEXT = "Always run the tests.\nUse the fixture setup for shared data."
BINARY = object()  # marks a file GitHub reports as binary


class Link:
    """A symbolic link; GitHub lists it as a blob with mode 0o120000 whose text
    is `target`."""

    def __init__(self, target):
        self.target = target
DIRECTORY = object()  # marks an empty directory


def _oid(repo_name, path):
    # No "/" in the id: the REST blob route reads the id from the URL's last segment.
    return "oid-" + f"{repo_name}:{path}".replace("/", "~")


class FakeRepo:
    """A repository at its snapshot commit: files by path, as text or BINARY."""

    def __init__(self, name, files, *, commit="c1", truncated=(), tree_truncated=False):
        self.name = name
        self.commit = commit
        self.files = files
        self.truncated = set(truncated)
        self.tree_truncated = tree_truncated

    def entries(self, directory):
        """Entries of `directory` ("" for the root), or None if not a directory."""
        prefix = f"{directory}/" if directory else ""
        if directory and not any(p.startswith(prefix) for p in self.files):
            return None
        children = {}
        for path, content in self.files.items():
            if not path.startswith(prefix):
                continue
            head, _, rest = path[len(prefix) :].partition("/")
            if rest or content is DIRECTORY:
                children[head] = ("tree", 0o40000)
            elif isinstance(content, Link):
                children[head] = ("blob", 0o120000)
            else:
                children.setdefault(head, ("blob", 0o100644))
        return [
            {"name": n, "type": t, "mode": m, "oid": _oid(self.name, prefix + n)}
            for n, (t, m) in sorted(children.items())
        ]

    def tree(self, sha, recursive):
        """The REST Git Trees response for the commit (`sha` = the commit) or a
        directory (`sha` = its oid), relative to it. When `tree_truncated`,
        GitHub cuts the commit's recursive listing short: the root entries
        only, flagged truncated."""
        if sha == self.commit:
            base = ""
        else:
            base = next((p for p in self._directories() if _oid(self.name, p) == sha), None)
            if base is None:
                return None
        cut = recursive and self.tree_truncated and base == ""
        entries, pending = [], [base]
        while pending:
            directory = pending.pop()
            for e in self.entries(directory) or []:
                path = f"{directory}/{e['name']}" if directory else e["name"]
                relative = path[len(base) + 1 :] if base else path
                entries.append({"path": relative, "type": e["type"], "mode": f"{e['mode']:o}", "sha": e["oid"]})
                if e["type"] == "tree" and recursive and not cut:
                    pending.append(path)
        return {"sha": sha, "tree": sorted(entries, key=lambda e: e["path"]), "truncated": cut}

    def _directories(self):
        dirs = set()
        for path in self.files:
            parts = path.split("/")
            dirs |= {"/".join(parts[:i]) for i in range(1, len(parts))}
        return dirs

    def blob(self, oid):
        for path, content in self.files.items():
            if _oid(self.name, path) == oid:
                return path, content
        return None, None


def _fake_github(repos):
    """Stands in for requests.post: answers cutoff, blob and directory queries."""
    by_name = {repo.name: repo for repo in repos}
    calls = []

    def _post(url, json=None, headers=None, timeout=None):
        query = json["query"]
        calls.append(query)
        data, errors = {}, []
        if "$until" in query:
            for alias, owner, name in re.findall(r'(r\d+): repository\(owner: "([^"]+)", name: "([^"]+)"\)', query):
                repo = by_name.get(f"{owner}/{name}")
                if repo is None:
                    data[alias] = None
                    errors.append({"type": "NOT_FOUND", "path": [alias]})
                elif repo.files is None:
                    data[alias] = {"defaultBranchRef": None}
                else:
                    data[alias] = {
                        "defaultBranchRef": {"target": {"history": {"nodes": [
                            {"oid": repo.commit, "authoredDate": "2026-09-08T12:00:00Z",
                             "tree": {"entries": repo.entries("")}}
                        ]}}}
                    }
        for alias, owner, name, oid in re.findall(
            r'(b\d+): repository\(owner: "([^"]+)", name: "([^"]+)"\) \{ object\(oid: "([^"]+)"\)', query
        ):
            repo = by_name[f"{owner}/{name}"]
            path, content = repo.blob(oid)
            if isinstance(content, Link):
                content = content.target
            if content is BINARY:
                data[alias] = {"object": {"text": None, "isBinary": True, "isTruncated": False}}
            elif path in repo.truncated:
                data[alias] = {"object": {"text": content[:5], "isBinary": False, "isTruncated": True}}
            else:
                data[alias] = {"object": {"text": content, "isBinary": False, "isTruncated": False}}
        for alias, owner, name, commit, directory in re.findall(
            r'(d\d+): repository\(owner: "([^"]+)", name: "([^"]+)"\) \{ object\(expression: "([^":]+):([^"]*)"\)', query
        ):
            repo = by_name[f"{owner}/{name}"]
            assert commit == repo.commit, "directories must be listed at the snapshot commit"
            entries = repo.entries(directory)
            data[alias] = {"object": None if entries is None else {"entries": entries}}
        return _fake_response(200, {"data": data, "errors": errors} if errors else {"data": data})

    _post.calls = calls
    return _post


def _rest(repos, *, missing_trees=()):
    blobs = {
        _oid(repo.name, path): _blob_json(text)
        for repo in repos
        for path, text in (repo.files or {}).items()
        if isinstance(text, str)
    }
    by_name = {repo.name: repo for repo in repos if repo.files is not None and repo.name not in missing_trees}

    def trees(repo_name, sha, recursive):
        repo = by_name.get(repo_name)
        return None if repo is None else repo.tree(sha, recursive)

    return _route(blobs=blobs, trees=trees)


def _scan(repos, catalog=_TEST_CATALOG, *, missing_trees=()):
    fake = _fake_github(repos)
    with patch("collection.rq5_agent_file_scan.requests.post", side_effect=fake), patch(
        "collection.rq5_agent_file_scan.requests.get", side_effect=_rest(repos, missing_trees=missing_trees)
    ):
        results = process_repos_graphql(
            [{"repo_name": r.name, "language": "python"} for r in repos],
            snapshot_date=SNAPSHOT,
            token="t",
            catalog=catalog,
        )
    return {r["repo"]["repo_name"]: r for r in results}, fake.calls


def _one(files, **kwargs):
    results, calls = _scan([FakeRepo("org/r", files, **kwargs)])
    return results["org/r"], calls


def _files(result):
    return {f["file_path"]: f for f in result["files"]}


class TestGuidanceFiles:
    def test_root_guidance_file_is_scanned(self):
        result, _ = _one({"AGENTS.md": AGENT_TEXT, "README.md": "unrelated readme"})
        assert result["repo"]["fetch_ok"] == 1
        assert result["repo"]["commit_sha"] == "c1"
        assert result["repo"]["commit_date"] == "2026-09-08"
        assert (result["repo"]["num_guidance_files"], result["repo"]["num_root_files"]) == (1, 1)
        agent = _files(result)["AGENTS.md"]
        assert (agent["location"], agent["symlink_target"]) == ("root", "")
        assert agent["has_test"] and agent["has_fixture"]
        assert agent["github_url"] == "https://github.com/org/r/blob/c1/AGENTS.md"
        assert {(m["keyword_list"], m["location"]) for m in result["matches"]} == {("test", "root"), ("fixture", "root")}

    def test_nested_guidance_files_are_scanned_at_any_depth(self):
        result, _ = _one(
            {"AGENTS.md": "x", "packages/api/CLAUDE.md": AGENT_TEXT, "a/b/c/d/e/GEMINI.md": "Use a fixture."}
        )
        assert set(_files(result)) == {"AGENTS.md", "packages/api/CLAUDE.md", "a/b/c/d/e/GEMINI.md"}
        nested = _files(result)["packages/api/CLAUDE.md"]
        assert (nested["location"], nested["file_type"]) == ("nested", "CLAUDE.md")
        assert nested["github_url"] == "https://github.com/org/r/blob/c1/packages/api/CLAUDE.md"
        assert {m["location"] for m in result["matches"] if m["file_path"] == "packages/api/CLAUDE.md"} == {"nested"}
        assert (result["repo"]["num_guidance_files"], result["repo"]["num_root_files"]) == (3, 1)

    def test_a_repository_with_nested_files_only(self):
        result, _ = _one({"docs/AGENTS.md": AGENT_TEXT})
        assert (result["repo"]["num_guidance_files"], result["repo"]["num_root_files"]) == (1, 0)

    def test_references_between_files_are_not_followed(self):
        result, _ = _one({"AGENTS.md": "See [testing](docs/TESTING.md).", "docs/TESTING.md": "fixtures"})
        assert set(_files(result)) == {"AGENTS.md"}

    def test_other_names_are_not_read(self):
        result, _ = _one({"AGENT.md": "fixture", "CONTRIBUTING.md": "fixture", ".github/copilot-instructions.md": "fixture"})
        assert result["files"] == []

    def test_files_under_excluded_directories_are_not_read(self):
        result, _ = _one({"node_modules/pkg/AGENTS.md": "fixture", "web/vendor/CLAUDE.md": "fixture", "web/AGENTS.md": "x"})
        assert set(_files(result)) == {"web/AGENTS.md"}

    def test_file_name_keeps_the_case_the_repository_used(self):
        result, _ = _one({"pkg/claude.md": AGENT_TEXT})
        [agent] = result["files"]
        assert (agent["file_path"], agent["file_name"], agent["file_type"]) == ("pkg/claude.md", "claude.md", "CLAUDE.md")

    def test_directory_named_like_a_guidance_file_is_not_a_file(self):
        result, _ = _one({"CLAUDE.md/notes.txt": "x"})
        assert result["files"] == []

    def test_binary_file_is_unreadable(self):
        result, _ = _one({"AGENTS.md": BINARY})
        assert result["files"] == [] and result["repo"]["fetch_ok"] == 1

    def test_truncated_text_is_reread_in_full(self):
        result, _ = _one({"pkg/AGENTS.md": AGENT_TEXT}, truncated={"pkg/AGENTS.md"})
        assert _files(result)["pkg/AGENTS.md"]["has_fixture"]

    def test_no_commit_on_the_branch(self):
        results, _ = _scan([FakeRepo("org/r", None)])
        assert results["org/r"]["repo"]["error_reason"] == "no_commit_at_or_before_cutoff"

    def test_missing_repository_does_not_fail_the_batch(self):
        repos = [FakeRepo("org/ok", {"AGENTS.md": AGENT_TEXT})]
        with patch("collection.rq5_agent_file_scan.requests.post", side_effect=_fake_github(repos)), patch(
            "collection.rq5_agent_file_scan.requests.get", side_effect=_rest(repos)
        ):
            results = {
                r["repo"]["repo_name"]: r
                for r in process_repos_graphql(
                    [{"repo_name": "org/ok", "language": "python"}, {"repo_name": "org/ghost", "language": "python"}],
                    snapshot_date=SNAPSHOT,
                    token="t",
                    catalog=_TEST_CATALOG,
                )
            }
        assert results["org/ok"]["repo"]["fetch_ok"] == 1
        assert results["org/ghost"]["repo"]["error_reason"] == "no_commit_at_or_before_cutoff"

    def test_a_tree_that_cannot_be_fetched_fails_only_that_repository(self):
        repos = [FakeRepo("org/a", {"AGENTS.md": AGENT_TEXT}), FakeRepo("org/b", {"AGENTS.md": AGENT_TEXT})]
        results, _ = _scan(repos, missing_trees={"org/b"})
        assert results["org/a"]["repo"]["fetch_ok"] == 1
        assert (results["org/b"]["repo"]["fetch_ok"], results["org/b"]["repo"]["error_reason"]) == (0, "tree_fetch_failed")


class TestTruncatedTrees:
    def test_a_truncated_listing_is_split_into_subdirectory_listings(self):
        files = {"AGENTS.md": "x", "pkg/api/CLAUDE.md": AGENT_TEXT, "node_modules/p/AGENTS.md": "fixture"}
        repos = [FakeRepo("org/r", files, tree_truncated=True)]
        rest = _rest(repos)
        gets = []

        def _get(url, params=None, **kwargs):
            gets.append((url.rsplit("/", 1)[-1], params))
            return rest(url, params=params, **kwargs)

        with patch("collection.rq5_agent_file_scan.requests.post", side_effect=_fake_github(repos)), patch(
            "collection.rq5_agent_file_scan.requests.get", side_effect=_get
        ):
            [result] = process_repos_graphql(
                [{"repo_name": "org/r", "language": "python"}], snapshot_date=SNAPSHOT, token="t", catalog=_TEST_CATALOG
            )
        assert {f["file_path"] for f in result["files"]} == {"AGENTS.md", "pkg/api/CLAUDE.md"}
        assert result["repo"]["tree_truncated"] == 1
        assert gets == [
            ("c1", {"recursive": "1"}),
            ("c1", None),
            (_oid("org/r", "pkg").rsplit("/", 1)[-1], {"recursive": "1"}),
        ]  # node_modules is never fetched

    def test_a_complete_listing_is_one_request(self):
        result, _ = _one({"pkg/api/CLAUDE.md": AGENT_TEXT})
        assert result["repo"]["tree_truncated"] == 0


class TestSymlinks:
    def test_a_link_to_a_guidance_file_is_counted_once(self):
        result, _ = _one({"AGENTS.md": AGENT_TEXT, "CLAUDE.md": Link("AGENTS.md")})
        assert set(_files(result)) == {"AGENTS.md"}
        assert result["repo"]["num_guidance_files"] == 1

    def test_a_link_to_another_file_is_read_through_its_target(self):
        result, _ = _one({"CLAUDE.md": Link("docs/ai-guide.md"), "docs/ai-guide.md": "Use the fixture setup."})
        link = _files(result)["CLAUDE.md"]
        assert (link["symlink_target"], link["has_fixture"], link["location"]) == ("docs/ai-guide.md", True, "root")
        assert link["github_url"] == "https://github.com/org/r/blob/c1/docs/ai-guide.md"
        assert {m["file_path"] for m in result["matches"]} == {"CLAUDE.md"}

    def test_a_nested_link_resolves_relative_to_its_directory(self):
        result, _ = _one({"pkg/a/AGENTS.md": Link("../../shared/AI.md"), "shared/AI.md": "fixture"})
        assert _files(result)["pkg/a/AGENTS.md"]["symlink_target"] == "shared/AI.md"

    def test_a_dangling_or_escaping_link_is_not_read(self):
        result, _ = _one({"CLAUDE.md": Link("missing.md"), "pkg/AGENTS.md": Link("../../outside.md")})
        assert result["files"] == []


class TestRequests:
    def test_a_batch_costs_three_graphql_requests_and_one_tree_per_repository(self):
        repos = [FakeRepo(f"org/r{i}", {"AGENTS.md": AGENT_TEXT, "pkg/CLAUDE.md": "x"}) for i in range(5)]
        rest = _rest(repos)
        gets = []

        def _get(url, **kwargs):
            gets.append(url)
            return rest(url, **kwargs)

        with patch("collection.rq5_agent_file_scan.requests.post", side_effect=_fake_github(repos)) as post, patch(
            "collection.rq5_agent_file_scan.requests.get", side_effect=_get
        ):
            process_repos_graphql(
                [{"repo_name": r.name, "language": "python"} for r in repos],
                snapshot_date=SNAPSHOT, token="t", catalog=_TEST_CATALOG,
            )
        assert post.call_count == 2  # cutoffs, file texts
        assert sorted(gets) == sorted(f"https://api.github.com/repos/org/r{i}/git/trees/c1" for i in range(5))

    def test_many_files_are_read_in_chunks(self):
        files = {f"d{i}/AGENTS.md": "fixture" for i in range(GRAPHQL_MAX_ALIASES + 5)}
        result, calls = _one(files)
        assert result["repo"]["num_guidance_files"] == GRAPHQL_MAX_ALIASES + 5
        assert len(calls) == 3  # cutoffs, 2 read chunks

    def test_cutoff_query_has_one_alias_per_repository_and_the_until_variable(self):
        query = _cutoff_query([{"repo_name": "owner/a"}, {"repo_name": "owner/b"}], SNAPSHOT)
        assert query.startswith("query($until: GitTimestamp!)")
        assert 'r0: repository(owner: "owner", name: "a")' in query
        assert 'r1: repository(owner: "owner", name: "b")' in query
        assert "history(first: 1, until: $until)" in query


class TestBatchFailures:
    def _run(self, post_side_effect, repos=None):
        fakes = repos or [FakeRepo("org/a", {"AGENTS.md": "x"}), FakeRepo("org/b", {"AGENTS.md": "x"})]
        with patch("collection.rq5_agent_file_scan.requests.post", side_effect=post_side_effect), patch(
            "collection.rq5_agent_file_scan.requests.get", side_effect=_rest(fakes)
        ), patch("collection.rq5_agent_file_scan.time.sleep"):
            return process_repos_graphql(
                [{"repo_name": r.name, "language": "python"} for r in fakes],
                snapshot_date=SNAPSHOT, token="t", catalog=_TEST_CATALOG,
            )

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

    def test_rest_tree_rate_limit_marks_the_batch_as_rate_limited(self):
        repos = [FakeRepo("org/a", {"AGENTS.md": "x"})]
        limited = _fake_response(429, {"message": "slow down"}, headers={"Retry-After": "0"})
        with patch("collection.rq5_agent_file_scan.requests.post", side_effect=_fake_github(repos)), patch(
            "collection.rq5_agent_file_scan.requests.get", return_value=limited
        ), patch("collection.rq5_agent_file_scan.time.sleep"):
            results = process_repos_graphql(
                [{"repo_name": "org/a", "language": "python"}], snapshot_date=SNAPSHOT, token="t", catalog=_TEST_CATALOG
            )
        assert results[0]["repo"]["error_reason"] == "rate_limited"

    def test_failure_while_reading_file_texts_fails_the_whole_batch(self):
        repos = [FakeRepo("org/a", {"AGENTS.md": "x"}), FakeRepo("org/b", {"AGENTS.md": "x"})]
        good = _fake_github(repos)

        def _post(url, json=None, headers=None, timeout=None):
            if "object(oid:" in json["query"]:
                return _fake_response(502, {"message": "Bad Gateway"})
            return good(url, json=json, headers=headers, timeout=timeout)

        results = self._run(_post, repos)
        assert {r["repo"]["error_reason"] for r in results} == {"tree_fetch_failed"}

    def test_rate_limit_then_success_recovers_without_losing_the_batch(self):
        repos = [FakeRepo("org/a", {"AGENTS.md": AGENT_TEXT}), FakeRepo("org/b", {})]
        good = _fake_github(repos)
        limited = _fake_response(200, {"data": None, "errors": [{"type": "RATE_LIMITED"}]})
        calls = {"n": 0}

        def _flaky(url, json=None, headers=None, timeout=None):
            calls["n"] += 1
            if calls["n"] == 1:
                return limited
            return good(url, json=json, headers=headers, timeout=timeout)

        results = self._run(_flaky, repos)
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
        universe = [{"repo_name": f"org/r{i}", "language": "python", "clone_url": "x"} for i in range(60)]
        batch_sizes = []

        def _fake_batch(batch, **kwargs):
            batch_sizes.append(len(batch))
            return [
                {"repo": {"repo_name": r["repo_name"], "language": "python", "fetch_ok": 1, "commit_sha": "c",
                          "commit_date": "2026-01-01", "num_guidance_files": 0, "num_root_files": 0,
                          "tree_truncated": 0, "error_reason": None, "scanned_at": "t"},
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
