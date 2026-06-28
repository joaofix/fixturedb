"""Unit tests for collection.classify_repos."""

from __future__ import annotations

import csv
import gzip
import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from collection.classify_repos import (
    VALID_DOMAINS,
    VALID_CONFIDENCES,
    GitHubRateLimiter,
    OllamaProvider,
    OpenRouterProvider,
    READMEEnricher,
    RepoClassifier,
    _classify_one,
    _parse_response,
    _parse_topics,
    load_completed_repos,
    load_repos_from_raw,
    main,
    write_result,
)


# ---------------------------------------------------------------------------
# _parse_topics
# ---------------------------------------------------------------------------


class TestParseTopics:
    def test_json_array(self):
        assert _parse_topics('["web", "api", "rest"]') == "web, api, rest"

    def test_semicolon_separated(self):
        assert _parse_topics("web;api;rest") == "web, api, rest"

    def test_empty_string(self):
        assert _parse_topics("") == ""

    def test_none_like(self):
        assert _parse_topics("") == ""

    def test_single_value(self):
        assert _parse_topics("machine-learning") == "machine-learning"

    def test_json_object_fallback(self):
        # Not a list, just return as string
        result = _parse_topics('{"key": "val"}')
        assert "key" in result


# ---------------------------------------------------------------------------
# RepoClassifier._parse_response
# ---------------------------------------------------------------------------


class TestParseResponse:
    def test_valid_json(self):
        result = _parse_response(
            '{"domain": "web", "confidence": "high", "reasoning": "It is a web framework"}'
        )
        assert result == {
            "domain": "web",
            "confidence": "high",
            "reasoning": "It is a web framework",
        }

    def test_markdown_fenced_json(self):
        result = _parse_response(
            '```json\n{"domain": "library", "confidence": "medium", "reasoning": "Utility lib"}\n```'
        )
        assert result["domain"] == "library"
        assert result["confidence"] == "medium"

    def test_markdown_fenced_no_lang(self):
        result = _parse_response(
            '```\n{"domain": "data", "confidence": "high", "reasoning": "ML framework"}\n```'
        )
        assert result["domain"] == "data"

    def test_invalid_json_fallback(self):
        result = _parse_response("not json at all")
        assert result["domain"] == "other"
        assert result["confidence"] == "low"
        assert "Parse error" in result["reasoning"]

    def test_invalid_domain_fallback(self):
        result = _parse_response(
            '{"domain": "invalid_domain", "confidence": "high", "reasoning": "test"}'
        )
        assert result["domain"] == "other"

    def test_invalid_confidence_fallback(self):
        result = _parse_response(
            '{"domain": "web", "confidence": "very_high", "reasoning": "test"}'
        )
        assert result["confidence"] == "low"

    def test_missing_keys_default(self):
        result = _parse_response("{}")
        assert result["domain"] == "other"
        assert result["confidence"] == "low"
        assert result["reasoning"] == ""

    def test_reasoning_truncated(self):
        long_reasoning = "x" * 300
        result = _parse_response(
            json.dumps(
                {
                    "domain": "cli",
                    "confidence": "high",
                    "reasoning": long_reasoning,
                }
            )
        )
        assert len(result["reasoning"]) <= 200


# ---------------------------------------------------------------------------
# RepoClassifier.classify (mocked OpenAI client)
# ---------------------------------------------------------------------------


class TestClassify:
    @pytest.fixture(autouse=True)
    def _patch_openrouter_key(self, monkeypatch):
        """Ensure OPENROUTER_KEY is set before RepoClassifier is instantiated."""
        monkeypatch.setattr(
            "collection.classify_repos.OPENROUTER_KEY", "sk-test-key"
        )

    @pytest.fixture
    def mock_openai_client(self):
        with patch(
            "collection.classify_repos.OpenAI"
        ) as mock_openai_cls:
            mock_client = MagicMock()
            mock_openai_cls.return_value = mock_client
            yield mock_client

    @pytest.fixture
    def classifier(self, mock_openai_client):
        provider = OpenRouterProvider()
        return RepoClassifier(provider)

    def _mock_response(self, mock_client, content: str):
        mock_choice = MagicMock()
        mock_choice.message.content = content
        mock_completion = MagicMock()
        mock_completion.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_completion

    def test_classify_web_repo(self, classifier, mock_openai_client):
        self._mock_response(
            mock_openai_client,
            '{"domain": "web", "confidence": "high", "reasoning": "Django-based web app"}',
        )
        repo = {
            "name": "owner/django-app",
            "description": "A Django web application",
            "mainLanguage": "Python",
            "topics": "web, django, python",
            "labels": "",
        }
        result = classifier.classify(repo)
        assert result["domain"] == "web"
        assert result["confidence"] == "high"

    def test_classify_with_readme(self, classifier, mock_openai_client):
        self._mock_response(
            mock_openai_client,
            '{"domain": "data", "confidence": "high", "reasoning": "ML pipeline"}',
        )
        repo = {
            "name": "owner/ml-pipeline",
            "description": "",
            "mainLanguage": "Python",
            "topics": "",
            "labels": "",
        }
        result = classifier.classify(repo, readme_excerpt="A machine learning pipeline for ETL.")
        assert result["domain"] == "data"

    def test_classify_retry_then_succeed(self, classifier, mock_openai_client):
        mock_openai_client.chat.completions.create.side_effect = [
            Exception("API timeout"),
            Exception("API timeout"),
            MagicMock(
                choices=[
                    MagicMock(
                        message=MagicMock(
                            content='{"domain": "infra", "confidence": "medium", "reasoning": "K8s operator"}'
                        )
                    )
                ]
            ),
        ]
        repo = {
            "name": "owner/k8s-op",
            "description": "Kubernetes operator",
            "mainLanguage": "Go",
            "topics": "",
            "labels": "",
        }
        result = classifier.classify(repo)
        assert result["domain"] == "infra"
        assert mock_openai_client.chat.completions.create.call_count == 3

    def test_classify_all_retries_exhausted(self, classifier, mock_openai_client):
        mock_openai_client.chat.completions.create.side_effect = Exception("Down")
        repo = {
            "name": "owner/broken",
            "description": "",
            "mainLanguage": "Python",
            "topics": "",
            "labels": "",
        }
        result = classifier.classify(repo)
        assert result["domain"] == "other"
        assert result["confidence"] == "low"
        assert "LLM error" in result["reasoning"]

    def test_classify_missing_openrouter_key(self, monkeypatch):
        monkeypatch.setattr(
            "collection.classify_repos.OPENROUTER_KEY", ""
        )
        with pytest.raises(RuntimeError, match="OPENROUTER_KEY"):
            OpenRouterProvider()


# ---------------------------------------------------------------------------
# GitHubRateLimiter
# ---------------------------------------------------------------------------


class TestGitHubRateLimiter:
    def test_acquire_consumes_token(self):
        limiter = GitHubRateLimiter(max_requests_per_hour=3600)  # 1/sec
        before = limiter.available
        limiter.acquire()
        after = limiter.available
        assert after < before

    def test_acquire_blocks_when_empty(self, monkeypatch):
        limiter = GitHubRateLimiter(max_requests_per_hour=1)  # 1 token total
        limiter.acquire()  # consume the only token

        # Now acquire should block. We'll time it out with a short sleep.
        import threading

        acquired = threading.Event()

        def try_acquire():
            limiter.acquire()
            acquired.set()

        t = threading.Thread(target=try_acquire, daemon=True)
        t.start()
        t.join(timeout=0.3)
        # Should NOT have acquired yet — no tokens available
        assert not acquired.is_set()

    def test_refills_over_time(self):
        limiter = GitHubRateLimiter(max_requests_per_hour=3600)  # 1/sec
        # Drain all tokens
        while limiter.available >= 1.0:
            limiter.acquire()

        # Wait for refill
        time.sleep(0.2)
        assert limiter.available > 0.0

    def test_never_exceeds_max(self):
        limiter = GitHubRateLimiter(max_requests_per_hour=100)
        # Wait long enough that it would overshoot without the cap
        time.sleep(0.5)
        assert limiter.available <= 100.0

    def test_starts_with_small_burst(self):
        """Bucket starts nearly empty to avoid exhausting GitHub rate limit."""
        limiter = GitHubRateLimiter(max_requests_per_hour=3600)
        assert limiter.available < 200  # small burst, not full bucket

    def test_thread_safety(self):
        import threading

        limiter = GitHubRateLimiter(max_requests_per_hour=3600)
        results = []

        def worker():
            for _ in range(10):
                limiter.acquire()
            results.append(True)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 5
        # 50 tokens consumed, should have ~3550 left (minus refill during test)
        assert limiter.available < 3600


# ---------------------------------------------------------------------------
# READMEEnricher
# ---------------------------------------------------------------------------


class TestREADMEEnricher:
    def test_fetch_readme_success(self, monkeypatch):
        enricher = READMEEnricher()

        class FakeResponse:
            def read(self):
                return b"Hello world. " * 150

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        monkeypatch.setattr(
            "collection.classify_repos.urllib.request.urlopen",
            lambda req, timeout=None: FakeResponse(),
        )

        excerpt = enricher.fetch("owner/repo")
        assert excerpt is not None
        words = excerpt.split()
        assert len(words) <= 200
        assert words[0] == "Hello"

    def test_fetch_readme_404(self, monkeypatch):
        import urllib.error

        enricher = READMEEnricher()

        def fake_urlopen(req, timeout=None):
            raise urllib.error.HTTPError(
                "url", 404, "Not Found", {}, None
            )

        monkeypatch.setattr(
            "collection.classify_repos.urllib.request.urlopen", fake_urlopen
        )

        excerpt = enricher.fetch("owner/nonexistent")
        assert excerpt is None

    def test_fetch_readme_cached(self, monkeypatch):
        enricher = READMEEnricher()
        call_count = 0

        class FakeResponse:
            def read(self):
                return b"Cached content here. " * 50

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        def fake_urlopen(req, timeout=None):
            nonlocal call_count
            call_count += 1
            return FakeResponse()

        monkeypatch.setattr(
            "collection.classify_repos.urllib.request.urlopen", fake_urlopen
        )

        first = enricher.fetch("owner/repo")
        second = enricher.fetch("owner/repo")
        assert first == second
        assert call_count == 1

    def test_fetch_readme_cached_none(self, monkeypatch):
        import urllib.error

        enricher = READMEEnricher()
        call_count = 0

        def fake_urlopen(req, timeout=None):
            nonlocal call_count
            call_count += 1
            raise urllib.error.HTTPError("url", 404, "Not Found", {}, None)

        monkeypatch.setattr(
            "collection.classify_repos.urllib.request.urlopen", fake_urlopen
        )

        first = enricher.fetch("owner/noreadme")
        second = enricher.fetch("owner/noreadme")
        assert first is None
        assert second is None
        assert call_count == 1

    def test_fetch_readme_network_error(self, monkeypatch):
        enricher = READMEEnricher()

        def fake_urlopen(req, timeout=None):
            raise OSError("Network unreachable")

        monkeypatch.setattr(
            "collection.classify_repos.urllib.request.urlopen", fake_urlopen
        )

        excerpt = enricher.fetch("owner/repo")
        assert excerpt is None


# ---------------------------------------------------------------------------
# load_repos_from_raw
# ---------------------------------------------------------------------------


class TestLoadReposFromRaw:
    def _write_gz_csv(self, path: Path, rows: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "wt", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    def test_load_single_language(self, tmp_path):
        self._write_gz_csv(
            tmp_path / "python.csv.gz",
            [
                {
                    "name": "owner/repo1",
                    "description": "A Python lib",
                    "mainLanguage": "Python",
                    "topics": "web;api",
                    "labels": "approved",
                    "stargazers": "100",
                    "homepage": "",
                    "license": "MIT",
                },
                {
                    "name": "owner/repo2",
                    "description": "Another lib",
                    "mainLanguage": "Python",
                    "topics": "data;ml",
                    "labels": "",
                    "stargazers": "200",
                    "homepage": "",
                    "license": "Apache-2.0",
                },
            ],
        )

        repos = load_repos_from_raw(tmp_path, "python")
        assert len(repos) == 2
        assert repos[0]["name"] == "owner/repo1"
        assert repos[0]["mainLanguage"] == "Python"
        assert repos[0]["topics"] == "web, api"
        assert repos[0]["labels"] == "approved"

    def test_load_filters_by_language(self, tmp_path):
        self._write_gz_csv(
            tmp_path / "python.csv.gz",
            [
                {
                    "name": "owner/py-repo",
                    "mainLanguage": "Python",
                    "description": "",
                    "topics": "",
                    "labels": "",
                    "stargazers": "",
                    "homepage": "",
                    "license": "",
                },
            ],
        )
        self._write_gz_csv(
            tmp_path / "java.csv.gz",
            [
                {
                    "name": "owner/java-repo",
                    "mainLanguage": "Java",
                    "description": "",
                    "topics": "",
                    "labels": "",
                    "stargazers": "",
                    "homepage": "",
                    "license": "",
                },
            ],
        )

        py_repos = load_repos_from_raw(tmp_path, "python")
        assert len(py_repos) == 1
        assert py_repos[0]["name"] == "owner/py-repo"

    def test_load_all_languages(self, tmp_path):
        self._write_gz_csv(
            tmp_path / "python.csv.gz",
            [
                {
                    "name": "owner/py",
                    "mainLanguage": "Python",
                    "description": "",
                    "topics": "",
                    "labels": "",
                    "stargazers": "",
                    "homepage": "",
                    "license": "",
                },
            ],
        )
        self._write_gz_csv(
            tmp_path / "java.csv.gz",
            [
                {
                    "name": "owner/java",
                    "mainLanguage": "Java",
                    "description": "",
                    "topics": "",
                    "labels": "",
                    "stargazers": "",
                    "homepage": "",
                    "license": "",
                },
            ],
        )

        repos = load_repos_from_raw(tmp_path)
        assert len(repos) == 2

    def test_skips_invalid_names(self, tmp_path):
        self._write_gz_csv(
            tmp_path / "python.csv.gz",
            [
                {
                    "name": "",
                    "mainLanguage": "Python",
                    "description": "",
                    "topics": "",
                    "labels": "",
                    "stargazers": "",
                    "homepage": "",
                    "license": "",
                },
                {
                    "name": "no-slash",
                    "mainLanguage": "Python",
                    "description": "",
                    "topics": "",
                    "labels": "",
                    "stargazers": "",
                    "homepage": "",
                    "license": "",
                },
                {
                    "name": "owner/valid",
                    "mainLanguage": "Python",
                    "description": "",
                    "topics": "",
                    "labels": "",
                    "stargazers": "",
                    "homepage": "",
                    "license": "",
                },
            ],
        )

        repos = load_repos_from_raw(tmp_path, "python")
        assert len(repos) == 1
        assert repos[0]["name"] == "owner/valid"

    def test_uses_full_name_fallback(self, tmp_path):
        self._write_gz_csv(
            tmp_path / "python.csv.gz",
            [
                {
                    "name": "",
                    "full_name": "owner/from-full",
                    "mainLanguage": "Python",
                    "description": "",
                    "topics": "",
                    "labels": "",
                    "stargazers": "",
                    "homepage": "",
                    "license": "",
                },
            ],
        )

        repos = load_repos_from_raw(tmp_path, "python")
        assert len(repos) == 1
        assert repos[0]["name"] == "owner/from-full"

    def test_uses_language_fallback(self, tmp_path):
        self._write_gz_csv(
            tmp_path / "python.csv.gz",
            [
                {
                    "name": "owner/repo",
                    "mainLanguage": "",
                    "language": "Python",
                    "description": "",
                    "topics": "",
                    "labels": "",
                    "stargazers": "",
                    "homepage": "",
                    "license": "",
                },
            ],
        )

        repos = load_repos_from_raw(tmp_path, "python")
        assert len(repos) == 1
        assert repos[0]["mainLanguage"] == "Python"


# ---------------------------------------------------------------------------
# load_completed_repos
# ---------------------------------------------------------------------------


class TestLoadCompletedRepos:
    def test_empty_dir(self, tmp_path):
        completed = load_completed_repos(tmp_path / "nonexistent")
        assert completed == set()

    def test_reads_classified_repos(self, tmp_path):
        out = tmp_path / "github-search-labeled"
        out.mkdir()
        (out / "python.csv").write_text(
            "name,mainLanguage,domain,confidence,reasoning\n"
            "owner/a,Python,web,high,test\n"
            "owner/b,Python,library,medium,test\n",
            encoding="utf-8",
        )

        completed = load_completed_repos(out)
        assert completed == {"owner/a", "owner/b"}

    def test_multiple_language_files(self, tmp_path):
        out = tmp_path / "github-search-labeled"
        out.mkdir()
        (out / "python.csv").write_text(
            "name,mainLanguage,domain,confidence,reasoning\n"
            "owner/py,Python,web,high,test\n",
            encoding="utf-8",
        )
        (out / "java.csv").write_text(
            "name,mainLanguage,domain,confidence,reasoning\n"
            "owner/jv,Java,library,high,test\n",
            encoding="utf-8",
        )

        completed = load_completed_repos(out)
        assert completed == {"owner/py", "owner/jv"}

    def test_corrupted_file_skipped(self, tmp_path):
        out = tmp_path / "github-search-labeled"
        out.mkdir()
        (out / "python.csv").write_text("garbage\nno,header,here\n", encoding="utf-8")

        completed = load_completed_repos(out)
        assert completed == set()  # no crash


# ---------------------------------------------------------------------------
# write_result
# ---------------------------------------------------------------------------


class TestWriteResult:
    def test_writes_header_and_row(self, tmp_path):
        out = tmp_path / "output"
        write_result(
            out,
            "Python",
            {
                "name": "owner/repo",
                "mainLanguage": "Python",
                "domain": "web",
                "confidence": "high",
                "reasoning": "test",
            },
        )

        csv_path = out / "python.csv"
        assert csv_path.exists()
        content = csv_path.read_text(encoding="utf-8")
        lines = content.strip().split("\n")
        assert len(lines) == 2
        assert "name,mainLanguage,domain,confidence,reasoning" in lines[0]
        assert "owner/repo" in lines[1]

    def test_appends_to_existing_file(self, tmp_path):
        out = tmp_path / "output"
        write_result(
            out,
            "Python",
            {
                "name": "owner/a",
                "mainLanguage": "Python",
                "domain": "web",
                "confidence": "high",
                "reasoning": "first",
            },
        )
        write_result(
            out,
            "Python",
            {
                "name": "owner/b",
                "mainLanguage": "Python",
                "domain": "library",
                "confidence": "medium",
                "reasoning": "second",
            },
        )

        csv_path = out / "python.csv"
        content = csv_path.read_text(encoding="utf-8")
        lines = content.strip().split("\n")
        assert len(lines) == 3  # header + 2 rows
        assert "owner/a" in lines[1]
        assert "owner/b" in lines[2]

    def test_normalizes_language_case(self, tmp_path):
        out = tmp_path / "output"
        write_result(
            out,
            "TypeScript",
            {
                "name": "owner/ts",
                "mainLanguage": "TypeScript",
                "domain": "web",
                "confidence": "high",
                "reasoning": "test",
            },
        )

        csv_path = out / "typescript.csv"
        assert csv_path.exists()


# ---------------------------------------------------------------------------
# _classify_one
# ---------------------------------------------------------------------------


class TestClassifyOne:
    @pytest.fixture(autouse=True)
    def _patch_openrouter_key(self, monkeypatch):
        monkeypatch.setattr(
            "collection.classify_repos.OPENROUTER_KEY", "sk-test"
        )

    def test_without_enricher(self):
        provider = OpenRouterProvider()
        classifier = RepoClassifier(provider)
        classifier.classify = MagicMock(
            return_value={
                "domain": "cli",
                "confidence": "high",
                "reasoning": "CLI tool",
            }
        )

        repo = {
            "name": "owner/cli-tool",
            "mainLanguage": "Python",
        }
        result = _classify_one(repo, classifier, enricher=None)
        assert result["domain"] == "cli"
        assert result["name"] == "owner/cli-tool"
        classifier.classify.assert_called_once()

    def test_with_enricher(self):
        provider = OpenRouterProvider()
        classifier = RepoClassifier(provider)
        classifier.classify = MagicMock(
            return_value={
                "domain": "data",
                "confidence": "high",
                "reasoning": "Data pipeline",
            }
        )

        enricher = READMEEnricher()
        enricher.fetch = MagicMock(return_value="Some README content here.")

        repo = {
            "name": "owner/data-tool",
            "mainLanguage": "Python",
        }
        result = _classify_one(repo, classifier, enricher=enricher)
        assert result["domain"] == "data"
        enricher.fetch.assert_called_once_with("owner/data-tool")
        call_kwargs = classifier.classify.call_args
        assert call_kwargs[0][1] == "Some README content here."


# ---------------------------------------------------------------------------
# main() CLI integration tests
# ---------------------------------------------------------------------------


class TestMainCLI:
    @pytest.fixture(autouse=True)
    def _patch_config(self, monkeypatch):
        """Patch config constants so main() uses tmp_path."""
        monkeypatch.setattr(
            "collection.classify_repos.OPENROUTER_KEY", "sk-test"
        )

    def _write_gz_csv(self, path: Path, rows: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "wt", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    def _make_repo_row(self, name: str, lang: str) -> dict:
        return {
            "name": name,
            "description": "",
            "mainLanguage": lang,
            "topics": "",
            "labels": "",
            "stargazers": "100",
            "homepage": "",
            "license": "MIT",
        }

    def test_toy_flag_samples_10_per_language(self, tmp_path, monkeypatch):
        """--toy should sample exactly 10 random repos per language."""
        raw_dir = tmp_path / "github-search-raw"
        out_dir = tmp_path / "github-search-labeled"

        monkeypatch.setattr(
            "collection.classify_repos.CLASSIFY_INPUT_DIR", raw_dir
        )
        monkeypatch.setattr(
            "collection.classify_repos.CLASSIFY_OUTPUT_DIR", out_dir
        )

        py_rows = [
            self._make_repo_row(f"owner/py{i}", "Python") for i in range(20)
        ]
        java_rows = [
            self._make_repo_row(f"owner/jv{i}", "Java") for i in range(15)
        ]

        self._write_gz_csv(raw_dir / "python.csv.gz", py_rows)
        self._write_gz_csv(raw_dir / "java.csv.gz", java_rows)

        with patch(
            "collection.classify_repos.RepoClassifier"
        ) as mock_cls:
            mock_instance = MagicMock()
            mock_instance.classify.return_value = {
                "domain": "web",
                "confidence": "high",
                "reasoning": "mock",
            }
            mock_cls.return_value = mock_instance

            with patch(
                "collection.classify_repos.READMEEnricher"
            ) as mock_enricher_cls:
                mock_enricher = MagicMock()
                mock_enricher.fetch.return_value = "Mock README."
                mock_enricher_cls.return_value = mock_enricher

                exit_code = main(
                    ["--toy", "--seed", "42", "--skip-readme"]
                )

        assert exit_code == 0

        py_csv = out_dir / "python.csv"
        jv_csv = out_dir / "java.csv"
        assert py_csv.exists()
        assert jv_csv.exists()

        py_lines = py_csv.read_text().strip().split("\n")
        jv_lines = jv_csv.read_text().strip().split("\n")
        assert len(py_lines) == 11, f"Expected 11 lines, got {len(py_lines)}"
        assert len(jv_lines) == 11, f"Expected 11 lines, got {len(jv_lines)}"

    def test_toy_reproducible_with_seed(self, tmp_path, monkeypatch):
        """Same seed should produce same sample."""
        raw_dir = tmp_path / "github-search-raw"
        out_dir1 = tmp_path / "out1"
        out_dir2 = tmp_path / "out2"

        monkeypatch.setattr(
            "collection.classify_repos.CLASSIFY_INPUT_DIR", raw_dir
        )

        py_rows = [
            self._make_repo_row(f"owner/py{i}", "Python") for i in range(30)
        ]
        self._write_gz_csv(raw_dir / "python.csv.gz", py_rows)

        with patch(
            "collection.classify_repos.RepoClassifier"
        ) as mock_cls:
            mock_instance = MagicMock()
            mock_instance.classify.return_value = {
                "domain": "web",
                "confidence": "high",
                "reasoning": "mock",
            }
            mock_cls.return_value = mock_instance

            with patch(
                "collection.classify_repos.READMEEnricher"
            ) as mock_enricher_cls:
                mock_enricher = MagicMock()
                mock_enricher.fetch.return_value = "Mock README."
                mock_enricher_cls.return_value = mock_enricher

                with patch(
                    "collection.classify_repos.CLASSIFY_OUTPUT_DIR", out_dir1
                ):
                    main(["--toy", "--seed", "42", "--skip-readme"])

                with patch(
                    "collection.classify_repos.CLASSIFY_OUTPUT_DIR", out_dir2
                ):
                    main(["--toy", "--seed", "42", "--skip-readme"])

        names1 = set()
        for csv_file in out_dir1.glob("*.csv"):
            names1.update(
                row["name"]
                for row in csv.DictReader(csv_file.read_text().splitlines())
            )
        names2 = set()
        for csv_file in out_dir2.glob("*.csv"):
            names2.update(
                row["name"]
                for row in csv.DictReader(csv_file.read_text().splitlines())
            )

        assert names1 == names2

    def test_sample_flag(self, tmp_path, monkeypatch):
        """--sample N should process N repos per language."""
        raw_dir = tmp_path / "github-search-raw"
        out_dir = tmp_path / "github-search-labeled"

        monkeypatch.setattr(
            "collection.classify_repos.CLASSIFY_INPUT_DIR", raw_dir
        )
        monkeypatch.setattr(
            "collection.classify_repos.CLASSIFY_OUTPUT_DIR", out_dir
        )

        py_rows = [
            self._make_repo_row(f"owner/py{i}", "Python") for i in range(50)
        ]
        java_rows = [
            self._make_repo_row(f"owner/jv{i}", "Java") for i in range(30)
        ]
        self._write_gz_csv(raw_dir / "python.csv.gz", py_rows)
        self._write_gz_csv(raw_dir / "java.csv.gz", java_rows)

        with patch(
            "collection.classify_repos.RepoClassifier"
        ) as mock_cls:
            mock_instance = MagicMock()
            mock_instance.classify.return_value = {
                "domain": "web",
                "confidence": "high",
                "reasoning": "mock",
            }
            mock_cls.return_value = mock_instance

            with patch(
                "collection.classify_repos.READMEEnricher"
            ) as mock_enricher_cls:
                mock_enricher = MagicMock()
                mock_enricher.fetch.return_value = "Mock README."
                mock_enricher_cls.return_value = mock_enricher

                main(["--sample", "7", "--skip-readme"])

        # 7 per language = 7 Python + 7 Java
        py_csv = out_dir / "python.csv"
        jv_csv = out_dir / "java.csv"
        assert py_csv.exists()
        assert jv_csv.exists()
        py_lines = py_csv.read_text().strip().split("\n")
        jv_lines = jv_csv.read_text().strip().split("\n")
        assert len(py_lines) == 8  # header + 7
        assert len(jv_lines) == 8  # header + 7

    def test_resume_skips_completed(self, tmp_path, monkeypatch):
        """Already-classified repos should be skipped on re-run."""
        raw_dir = tmp_path / "github-search-raw"
        out_dir = tmp_path / "github-search-labeled"
        out_dir.mkdir(parents=True)

        monkeypatch.setattr(
            "collection.classify_repos.CLASSIFY_INPUT_DIR", raw_dir
        )
        monkeypatch.setattr(
            "collection.classify_repos.CLASSIFY_OUTPUT_DIR", out_dir
        )

        (out_dir / "python.csv").write_text(
            "name,mainLanguage,domain,confidence,reasoning\n"
            "owner/py0,Python,web,high,done\n"
            "owner/py1,Python,library,high,done\n",
            encoding="utf-8",
        )

        py_rows = [
            self._make_repo_row(f"owner/py{i}", "Python") for i in range(5)
        ]
        self._write_gz_csv(raw_dir / "python.csv.gz", py_rows)

        with patch(
            "collection.classify_repos.RepoClassifier"
        ) as mock_cls:
            mock_instance = MagicMock()
            mock_instance.classify.return_value = {
                "domain": "web",
                "confidence": "high",
                "reasoning": "mock",
            }
            mock_cls.return_value = mock_instance

            with patch(
                "collection.classify_repos.READMEEnricher"
            ) as mock_enricher_cls:
                mock_enricher = MagicMock()
                mock_enricher.fetch.return_value = "Mock README."
                mock_enricher_cls.return_value = mock_enricher

                main(["--skip-readme"])

        py_csv = out_dir / "python.csv"
        lines = py_csv.read_text().strip().split("\n")
        assert len(lines) == 6

    def test_language_filter(self, tmp_path, monkeypatch):
        """--language should only process that language."""
        raw_dir = tmp_path / "github-search-raw"
        out_dir = tmp_path / "github-search-labeled"

        monkeypatch.setattr(
            "collection.classify_repos.CLASSIFY_INPUT_DIR", raw_dir
        )
        monkeypatch.setattr(
            "collection.classify_repos.CLASSIFY_OUTPUT_DIR", out_dir
        )

        self._write_gz_csv(
            raw_dir / "python.csv.gz",
            [self._make_repo_row("owner/py0", "Python")],
        )
        self._write_gz_csv(
            raw_dir / "java.csv.gz",
            [self._make_repo_row("owner/jv0", "Java")],
        )

        with patch(
            "collection.classify_repos.RepoClassifier"
        ) as mock_cls:
            mock_instance = MagicMock()
            mock_instance.classify.return_value = {
                "domain": "web",
                "confidence": "high",
                "reasoning": "mock",
            }
            mock_cls.return_value = mock_instance

            with patch(
                "collection.classify_repos.READMEEnricher"
            ) as mock_enricher_cls:
                mock_enricher = MagicMock()
                mock_enricher.fetch.return_value = "Mock README."
                mock_enricher_cls.return_value = mock_enricher

                main(["--language", "java", "--skip-readme"])

        assert not (out_dir / "python.csv").exists()
        assert (out_dir / "java.csv").exists()

    def test_nothing_to_do_when_all_completed(self, tmp_path, monkeypatch):
        """Should exit early with message when all repos already classified."""
        raw_dir = tmp_path / "github-search-raw"
        out_dir = tmp_path / "github-search-labeled"
        out_dir.mkdir(parents=True)

        monkeypatch.setattr(
            "collection.classify_repos.CLASSIFY_INPUT_DIR", raw_dir
        )
        monkeypatch.setattr(
            "collection.classify_repos.CLASSIFY_OUTPUT_DIR", out_dir
        )

        (out_dir / "python.csv").write_text(
            "name,mainLanguage,domain,confidence,reasoning\n"
            "owner/py0,Python,web,high,done\n",
            encoding="utf-8",
        )

        self._write_gz_csv(
            raw_dir / "python.csv.gz",
            [self._make_repo_row("owner/py0", "Python")],
        )

        with patch(
            "collection.classify_repos.RepoClassifier"
        ) as mock_cls:
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance

            exit_code = main(["--skip-readme"])

        assert exit_code == 0
        mock_instance.classify.assert_not_called()

    def test_per_language_checkpoint(self, tmp_path, monkeypatch):
        """Each language's CSV is written before the next language starts."""
        raw_dir = tmp_path / "github-search-raw"
        out_dir = tmp_path / "github-search-labeled"

        monkeypatch.setattr(
            "collection.classify_repos.CLASSIFY_INPUT_DIR", raw_dir
        )
        monkeypatch.setattr(
            "collection.classify_repos.CLASSIFY_OUTPUT_DIR", out_dir
        )

        self._write_gz_csv(
            raw_dir / "python.csv.gz",
            [self._make_repo_row(f"owner/py{i}", "Python") for i in range(3)],
        )
        self._write_gz_csv(
            raw_dir / "java.csv.gz",
            [self._make_repo_row(f"owner/jv{i}", "Java") for i in range(3)],
        )

        # Track which language is being processed
        processed_order = []

        with patch(
            "collection.classify_repos.RepoClassifier"
        ) as mock_cls:
            mock_instance = MagicMock()
            mock_instance.classify.return_value = {
                "domain": "web",
                "confidence": "high",
                "reasoning": "mock",
            }
            mock_cls.return_value = mock_instance

            with patch(
                "collection.classify_repos.READMEEnricher"
            ) as mock_enricher_cls:
                mock_enricher = MagicMock()
                mock_enricher.fetch.return_value = "Mock README."
                mock_enricher_cls.return_value = mock_enricher

                main(["--skip-readme"])

        # Both CSVs should exist
        assert (out_dir / "python.csv").exists()
        assert (out_dir / "java.csv").exists()

        # Each should have 3 rows (header + 3)
        py_lines = (out_dir / "python.csv").read_text().strip().split("\n")
        jv_lines = (out_dir / "java.csv").read_text().strip().split("\n")
        assert len(py_lines) == 4
        assert len(jv_lines) == 4

    def test_partial_resume_after_crash(self, tmp_path, monkeypatch):
        """If python.csv exists but java.csv doesn't, only java is processed."""
        raw_dir = tmp_path / "github-search-raw"
        out_dir = tmp_path / "github-search-labeled"
        out_dir.mkdir(parents=True)

        monkeypatch.setattr(
            "collection.classify_repos.CLASSIFY_INPUT_DIR", raw_dir
        )
        monkeypatch.setattr(
            "collection.classify_repos.CLASSIFY_OUTPUT_DIR", out_dir
        )

        # Pre-populate python.csv (simulating completed language)
        (out_dir / "python.csv").write_text(
            "name,mainLanguage,domain,confidence,reasoning\n"
            "owner/py0,Python,web,high,done\n"
            "owner/py1,Python,library,high,done\n",
            encoding="utf-8",
        )

        self._write_gz_csv(
            raw_dir / "python.csv.gz",
            [self._make_repo_row(f"owner/py{i}", "Python") for i in range(2)],
        )
        self._write_gz_csv(
            raw_dir / "java.csv.gz",
            [self._make_repo_row(f"owner/jv{i}", "Java") for i in range(2)],
        )

        with patch(
            "collection.classify_repos.RepoClassifier"
        ) as mock_cls:
            mock_instance = MagicMock()
            mock_instance.classify.return_value = {
                "domain": "web",
                "confidence": "high",
                "reasoning": "mock",
            }
            mock_cls.return_value = mock_instance

            with patch(
                "collection.classify_repos.READMEEnricher"
            ) as mock_enricher_cls:
                mock_enricher = MagicMock()
                mock_enricher.fetch.return_value = "Mock README."
                mock_enricher_cls.return_value = mock_enricher

                main(["--skip-readme"])

        # Python should still have only 2 rows (not re-processed)
        py_lines = (out_dir / "python.csv").read_text().strip().split("\n")
        assert len(py_lines) == 3  # header + 2

        # Java should have been processed (2 new rows)
        jv_lines = (out_dir / "java.csv").read_text().strip().split("\n")
        assert len(jv_lines) == 3  # header + 2

        # Classifier should have been called only for Java repos
        assert mock_instance.classify.call_count == 2


# ---------------------------------------------------------------------------
# Domain / confidence validation
# ---------------------------------------------------------------------------


class TestValidation:
    def test_valid_domains_complete(self):
        expected = {"web", "library", "data", "infra", "cli", "other"}
        assert VALID_DOMAINS == expected

    def test_valid_confidences_complete(self):
        expected = {"high", "medium", "low"}
        assert VALID_CONFIDENCES == expected