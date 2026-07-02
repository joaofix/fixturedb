#!/usr/bin/env python3
"""Classify GitHub repositories into domain categories via OpenRouter LLM.

Reads repository metadata from github-search-raw/*.csv.gz, optionally enriches
with README excerpts from the GitHub API, classifies each repo into one of six
domains (web/library/data/infra/cli/other), and writes labeled CSVs to
github-search-classified/{model_name}/.

Usage:
    python -m collection classify [--language LANG] [--workers N] [--skip-readme] [--sample N]
"""

from __future__ import annotations

import csv
import gzip
import json
import random
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional, Protocol

import requests
from openai import OpenAI
from tqdm import tqdm

from .config import (
    CLASSIFY_INPUT_DIR,
    CLASSIFY_OUTPUT_DIR,
    CLASSIFY_WORKERS,
    GITHUB_TOKEN,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    OPENROUTER_BASE_URL,
    OPENROUTER_KEY,
    OPENROUTER_MODEL,
)
from .logging_utils import configure_logging, get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# GitHub API rate limiter (token bucket)
# ---------------------------------------------------------------------------

# Authenticated GitHub API: 5,000 req/hr. We target 4,500/hr to stay safe.
_GITHUB_RATE_LIMIT_PER_HOUR = 4500


class GitHubRateLimiter:
    """Token-bucket rate limiter for GitHub API calls.

    Allows bursts up to *max_tokens* then throttles to the sustained rate.
    Thread-safe — multiple workers can call ``acquire()`` concurrently.
    """

    def __init__(self, max_requests_per_hour: int = _GITHUB_RATE_LIMIT_PER_HOUR):
        self._max_tokens = max_requests_per_hour
        # Start with a small burst allowance (100) to avoid exhausting the
        # GitHub rate limit in the first few minutes. The bucket refills at
        # ~1.25 tokens/sec, matching the sustained 4,500/hr rate.
        self._tokens = 100.0
        self._refill_rate = max_requests_per_hour / 3600.0  # tokens / second
        self._lock = threading.Lock()
        self._last_refill = time.monotonic()

    def acquire(self) -> None:
        """Block until a token is available, then consume one."""
        while True:
            with self._lock:
                now = time.monotonic()
                elapsed = now - self._last_refill
                self._tokens = min(
                    self._max_tokens, self._tokens + elapsed * self._refill_rate
                )
                self._last_refill = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
            # No token — sleep briefly and retry
            time.sleep(0.05)

    @property
    def available(self) -> float:
        """Current token count (for debugging / logging)."""
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            return min(
                self._max_tokens, self._tokens + elapsed * self._refill_rate
            )


# ---------------------------------------------------------------------------
# Prompt templates — kept minimal to reduce token costs
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
Classify a GitHub repository into exactly one domain category.
Return ONLY valid JSON: {"domain":"...","confidence":"...","reasoning":"..."}

Categories:
- web: HTTP servers, REST/GraphQL APIs, web frameworks, frontend frameworks, web tooling
- library: Reusable packages, SDKs, client libraries, utility frameworks (not primarily web)
- data: Data science, ML, data pipelines, analytics, notebooks
- infra: DevOps, cloud infrastructure, containers, CI/CD, monitoring, system software
- cli: Command-line tools, build systems, developer tooling, automation scripts
- other: Does not clearly fit any category

Rules: Choose the PRIMARY purpose. One category only. Confidence: high/medium/low."""

USER_PROMPT_TEMPLATE = """\
Name: {name}
Description: {description}
Language: {language}
Topics: {topics}
Labels: {labels}
README: {readme}"""

# ---------------------------------------------------------------------------
# Valid outputs
# ---------------------------------------------------------------------------

VALID_DOMAINS = frozenset({"web", "library", "data", "infra", "cli", "other"})
VALID_CONFIDENCES = frozenset({"high", "medium", "low"})


# ---------------------------------------------------------------------------
# RepoClassifier
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# LLM Provider interface
# ---------------------------------------------------------------------------


class LLMProvider(Protocol):
    """Protocol for LLM backends (OpenRouter, Ollama, etc.)."""

    def classify(self, repo: dict, readme_excerpt: Optional[str] = None) -> dict:
        """Classify a single repository. Returns {domain, confidence, reasoning}."""
        ...


# ---------------------------------------------------------------------------
# OpenRouter provider
# ---------------------------------------------------------------------------


class OpenRouterProvider:
    """Classify via OpenRouter API (GPT-4o-mini)."""

    def __init__(self) -> None:
        if not OPENROUTER_KEY:
            raise RuntimeError(
                "OPENROUTER_KEY not set. Add it to your .env file."
            )
        self._client = OpenAI(
            base_url=OPENROUTER_BASE_URL,
            api_key=OPENROUTER_KEY,
        )

    def classify(
        self, repo: dict, readme_excerpt: Optional[str] = None
    ) -> dict:
        prompt = _build_user_prompt(repo, readme_excerpt)
        name = repo.get("name", "")

        for attempt in range(3):
            try:
                response = self._client.chat.completions.create(
                    model=OPENROUTER_MODEL,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.0,
                    max_tokens=100,
                )
                raw = response.choices[0].message.content.strip()
                return _parse_response(raw)
            except Exception as exc:
                if attempt < 2:
                    time.sleep(2**attempt)
                else:
                    logger.warning("OpenRouter failed for %s: %s", name, exc)
                    return _fallback_response(f"LLM error: {str(exc)[:80]}")

        return _fallback_response("Unexpected")


# ---------------------------------------------------------------------------
# Ollama provider
# ---------------------------------------------------------------------------


class OllamaProvider:
    """Classify via local Ollama instance (e.g. qwen3:14b)."""

    def __init__(self) -> None:
        self._base_url = OLLAMA_BASE_URL
        self._model = OLLAMA_MODEL

    def classify(
        self, repo: dict, readme_excerpt: Optional[str] = None
    ) -> dict:
        prompt = _build_user_prompt(repo, readme_excerpt)
        full_prompt = SYSTEM_PROMPT + "\n\n" + prompt
        name = repo.get("name", "")

        payload = {
            "model": self._model,
            "prompt": full_prompt,
            "stream": False,
            "options": {"think": False},
        }

        for attempt in range(3):
            try:
                resp = requests.post(
                    f"{self._base_url}/api/generate",
                    json=payload,
                    timeout=120,
                )
                resp.raise_for_status()
                data = resp.json()
                raw = data.get("response", "").strip()
                return _parse_response(raw)
            except Exception as exc:
                if attempt < 2:
                    time.sleep(2**attempt)
                else:
                    logger.warning("Ollama failed for %s: %s", name, exc)
                    return _fallback_response(f"LLM error: {str(exc)[:80]}")

        return _fallback_response("Unexpected")


# ---------------------------------------------------------------------------
# RepoClassifier (facade)
# ---------------------------------------------------------------------------


class RepoClassifier:
    """Classify repositories using the configured LLM provider."""

    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    def classify(
        self, repo: dict, readme_excerpt: Optional[str] = None
    ) -> dict:
        return self._provider.classify(repo, readme_excerpt)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _build_user_prompt(repo: dict, readme_excerpt: Optional[str] = None) -> str:
    """Build the user prompt string from repo metadata."""
    name = repo.get("name", "")
    description = (repo.get("description") or "").strip()
    language = (
        repo.get("mainLanguage") or repo.get("language") or ""
    ).strip()
    topics = (repo.get("topics") or "").strip()
    labels = (repo.get("labels") or "").strip()
    readme = (readme_excerpt or "N/A").strip()

    return USER_PROMPT_TEMPLATE.format(
        name=name,
        description=description or "N/A",
        language=language or "N/A",
        topics=topics or "N/A",
        labels=labels or "N/A",
        readme=readme,
    )


def _parse_response(raw: str) -> dict:
    """Parse LLM JSON response with fallback for malformed output."""
    try:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.strip()

        result = json.loads(cleaned)
        domain = str(result.get("domain", "other")).lower().strip()
        confidence = str(result.get("confidence", "low")).lower().strip()
        reasoning = str(result.get("reasoning", "")).strip()

        if domain not in VALID_DOMAINS:
            domain = "other"
        if confidence not in VALID_CONFIDENCES:
            confidence = "low"

        return {
            "domain": domain,
            "confidence": confidence,
            "reasoning": reasoning[:200],
        }
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        logger.debug("Failed to parse LLM response: %s", raw[:100])
        return _fallback_response(f"Parse error: {str(exc)[:80]}")


def _fallback_response(reason: str) -> dict:
    """Return a safe fallback classification."""
    return {"domain": "other", "confidence": "low", "reasoning": reason}


# ---------------------------------------------------------------------------
# READMEEnricher
# ---------------------------------------------------------------------------


class READMEEnricher:
    """Fetch README excerpts from the GitHub API with an in-memory cache.

    Accepts an optional *rate_limiter* to throttle GitHub API calls.
    """

    _README_WORD_LIMIT = 200

    def __init__(self, rate_limiter: Optional[GitHubRateLimiter] = None) -> None:
        self._cache: dict[str, Optional[str]] = {}
        self._lock = threading.Lock()
        self._rate_limiter = rate_limiter

    def fetch(self, repo_full_name: str) -> Optional[str]:
        """Fetch and truncate the README for *repo_full_name*.

        Returns the first 200 words, or *None* when no README is available.
        Results are cached so each repo is only fetched once.
        """
        with self._lock:
            if repo_full_name in self._cache:
                return self._cache[repo_full_name]

        # Rate-limit before hitting GitHub
        if self._rate_limiter is not None:
            self._rate_limiter.acquire()

        try:
            url = f"https://api.github.com/repos/{repo_full_name}/readme"
            req = urllib.request.Request(url)
            req.add_header("Accept", "application/vnd.github.v3.raw")
            if GITHUB_TOKEN:
                req.add_header("Authorization", f"token {GITHUB_TOKEN}")

            with urllib.request.urlopen(req, timeout=15) as resp:
                text = resp.read().decode("utf-8", errors="replace")

            words = text.split()
            excerpt = " ".join(words[: self._README_WORD_LIMIT])

            with self._lock:
                self._cache[repo_full_name] = excerpt
            return excerpt

        except urllib.error.HTTPError as exc:
            # 403 can mean: private repo, rate-limited, or blocked
            if exc.code == 403:
                # Try to read rate-limit headers to distinguish cause
                try:
                    remaining = exc.headers.get("X-RateLimit-Remaining", "?")
                except Exception:
                    remaining = "?"
                if remaining == "0":
                    logger.warning(
                        "README 403 (rate limited): %s", repo_full_name
                    )
                else:
                    logger.warning(
                        "README 403 (private/denied, rate-limit-remaining=%s): %s",
                        remaining,
                        repo_full_name,
                    )
            elif exc.code != 404:
                logger.debug("README HTTP %d for %s", exc.code, repo_full_name)
            with self._lock:
                self._cache[repo_full_name] = None
            return None
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            logger.warning("README network error for %s: %s", repo_full_name, exc)
            with self._lock:
                self._cache[repo_full_name] = None
            return None
        except Exception as exc:
            logger.debug("README fetch failed for %s: %s", repo_full_name, exc)
            with self._lock:
                self._cache[repo_full_name] = None
            return None


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def _parse_topics(raw: str) -> str:
    """Convert topics (JSON array or semicolon-separated) into a comma-separated string."""
    if not raw:
        return ""
    # Try JSON first
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return ", ".join(str(t) for t in parsed)
        return str(parsed)
    except (json.JSONDecodeError, TypeError):
        pass
    # Fallback: semicolon-separated
    return raw.replace(";", ", ")


def load_repos_from_raw(
    input_dir: Path, language: Optional[str] = None
) -> list[dict]:
    """Load repository metadata from ``github-search-raw/*.csv.gz``."""
    language_filter = (language or "").strip().lower() or None
    repos: list[dict] = []

    for csv_path in sorted(input_dir.glob("*.csv.gz"), key=lambda p: p.name):
        file_lang = csv_path.stem.split(".")[0]
        if language_filter and file_lang.lower() != language_filter:
            continue

        logger.info("Loading %s …", csv_path.name)
        count = 0
        with gzip.open(csv_path, "rt", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                name = (row.get("name") or row.get("full_name") or "").strip()
                if not name or "/" not in name:
                    continue

                repos.append(
                    {
                        "name": name,
                        "description": row.get("description", ""),
                        "mainLanguage": row.get("mainLanguage")
                        or row.get("language")
                        or file_lang,
                        "topics": _parse_topics(row.get("topics", "")),
                        "labels": _parse_topics(row.get("labels", "")),
                        "stargazers": row.get("stargazers", ""),
                        "homepage": row.get("homepage", ""),
                        "license": row.get("license", ""),
                    }
                )
                count += 1

        logger.info("  → %d repos loaded (%d total)", count, len(repos))

    return repos


def load_completed_repos(output_dir: Path) -> set[str]:
    """Return the set of repo names already present in output CSVs (resume)."""
    completed: set[str] = set()
    if not output_dir.exists():
        return completed

    for csv_path in sorted(output_dir.glob("*.csv")):
        try:
            with open(csv_path, encoding="utf-8", newline="") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    name = (row.get("name") or "").strip()
                    if name:
                        completed.add(name)
        except Exception:
            pass

    return completed


# ---------------------------------------------------------------------------
# Output (thread-safe append)
# ---------------------------------------------------------------------------

_OUTPUT_FIELDNAMES = ["name", "mainLanguage", "domain", "confidence", "reasoning"]
_write_lock = threading.Lock()


def _normalize_language(lang: str) -> str:
    """Normalize a language name to a lowercase filename-safe key."""
    return lang.strip().lower()


def write_result(output_dir: Path, language: str, result: dict) -> None:
    """Append a single classification row to ``{language}.csv``."""
    output_dir.mkdir(parents=True, exist_ok=True)
    lang_key = _normalize_language(language)
    csv_path = output_dir / f"{lang_key}.csv"

    with _write_lock:
        file_exists = csv_path.exists()
        with open(csv_path, "a", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=_OUTPUT_FIELDNAMES)
            if not file_exists:
                writer.writeheader()
            writer.writerow(result)


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------


def _classify_one(
    repo: dict,
    classifier: RepoClassifier,
    enricher: Optional[READMEEnricher],
) -> dict:
    """Fetch README (if enricher is set) and classify a single repo."""
    readme = None
    if enricher is not None:
        readme = enricher.fetch(repo["name"])

    classification = classifier.classify(repo, readme)

    return {
        "name": repo["name"],
        "mainLanguage": repo["mainLanguage"],
        "domain": classification["domain"],
        "confidence": classification["confidence"],
        "reasoning": classification["reasoning"],
    }


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Classify repositories into domain categories via LLM"
    )
    parser.add_argument(
        "--language",
        choices=["python", "javascript", "java", "typescript"],
        help="Limit to one language",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=CLASSIFY_WORKERS,
        help="Number of concurrent workers (default: %(default)s)",
    )
    parser.add_argument(
        "--skip-readme",
        action="store_true",
        help="Do not fetch README excerpts from GitHub",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=0,
        help="Process only N repos (for testing)",
    )
    parser.add_argument(
        "--provider",
        choices=["openrouter", "ollama"],
        default="openrouter",
        help="LLM provider (default: openrouter)",
    )
    parser.add_argument(
        "--toy",
        action="store_true",
        help="Sample 10 random repos per language (40 total) for a quick end-to-end test",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for --toy sampling (default: 42)",
    )
    args = parser.parse_args(argv)

    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------
    configure_logging()
    logger.info("=" * 60)
    logger.info("Repository Domain Classifier")
    logger.info("Provider: %s", args.provider)
    if args.provider == "openrouter":
        logger.info("Model: %s", OPENROUTER_MODEL)
    else:
        logger.info("Model: %s @ %s", OLLAMA_MODEL, OLLAMA_BASE_URL)
    logger.info("Workers: %d", args.workers)
    logger.info("README fetching: %s", "OFF" if args.skip_readme else "ON")

    # Ollama on local hardware — cap concurrency to avoid overwhelming the server
    if args.provider == "ollama" and args.workers > 4:
        logger.info("Ollama: capping workers at 4 (was %d)", args.workers)
        args.workers = 4

    logger.info("=" * 60)

    # ------------------------------------------------------------------
    # Load repos
    # ------------------------------------------------------------------
    all_repos = load_repos_from_raw(CLASSIFY_INPUT_DIR, args.language)
    logger.info("Total repos loaded: %d", len(all_repos))

    # Group by language for per-language checkpoint processing
    by_lang: dict[str, list[dict]] = {}
    for r in all_repos:
        lang = (r.get("mainLanguage") or "").strip().lower()
        by_lang.setdefault(lang, []).append(r)

    # Toy mode: 10 random repos per language
    if args.toy:
        random.seed(args.seed)
        for lang in sorted(by_lang):
            pool = by_lang[lang]
            n = min(10, len(pool))
            by_lang[lang] = random.sample(pool, n)
            logger.info("Toy: sampled %d/%d repos for %s", n, len(pool), lang)
        logger.info("Toy mode: %d repos total (seed=%d)", sum(len(v) for v in by_lang.values()), args.seed)

    # Sample mode: N repos per language
    if args.sample and args.sample > 0:
        for lang in sorted(by_lang):
            by_lang[lang] = by_lang[lang][: args.sample]
        logger.info("Sample mode: %d repos per language", args.sample)

    # Resume: skip already-classified repos (per language)
    completed = load_completed_repos(CLASSIFY_OUTPUT_DIR)
    if completed:
        for lang in sorted(by_lang):
            before = len(by_lang[lang])
            by_lang[lang] = [r for r in by_lang[lang] if r["name"] not in completed]
            skipped = before - len(by_lang[lang])
            if skipped:
                logger.info("Resume [%s]: %d already classified, %d remaining", lang, skipped, len(by_lang[lang]))

    # Remove empty languages
    by_lang = {k: v for k, v in by_lang.items() if v}

    if not by_lang:
        logger.info("Nothing to do — all repos already classified.")
        return 0

    # ------------------------------------------------------------------
    # Classify — one language at a time (checkpoint per language)
    # ------------------------------------------------------------------
    if args.provider == "ollama":
        provider = OllamaProvider()
    else:
        provider = OpenRouterProvider()
    classifier = RepoClassifier(provider)
    rate_limiter = None if args.skip_readme else GitHubRateLimiter()
    enricher = None if args.skip_readme else READMEEnricher(rate_limiter=rate_limiter)

    if not args.skip_readme:
        logger.info(
            "GitHub rate limit: %d req/hr (%.1f req/s)",
            _GITHUB_RATE_LIMIT_PER_HOUR,
            _GITHUB_RATE_LIMIT_PER_HOUR / 3600.0,
        )

    total_success = 0
    total_failed = 0

    for lang in sorted(by_lang):
        repos = by_lang[lang]
        logger.info("=" * 60)
        logger.info("Processing %s: %d repos", lang, len(repos))
        logger.info("=" * 60)

        success = 0
        failed = 0

        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(_classify_one, repo, classifier, enricher): repo
                for repo in repos
            }

            with tqdm(total=len(repos), desc=f"Classifying {lang}", unit="repo") as pbar:
                for future in as_completed(futures):
                    repo = futures[future]
                    try:
                        result = future.result()
                        write_result(
                            CLASSIFY_OUTPUT_DIR, result["mainLanguage"], result
                        )
                        success += 1
                    except Exception as exc:
                        logger.error("Failed %s: %s", repo["name"], exc)
                        failed += 1

                    pbar.set_description_str(
                        f"{lang} [ok:{success} fail:{failed}]"
                    )
                    pbar.update(1)

        total_success += success
        total_failed += failed

        # Per-language summary
        _log_language_summary(lang, success, failed)

    logger.info("Done — total success: %d, total failed: %d", total_success, total_failed)
    return 0 if total_failed == 0 else 1


def _log_language_summary(lang: str, success: int, failed: int) -> None:
    """Log a per-language domain distribution summary."""
    csv_path = CLASSIFY_OUTPUT_DIR / f"{lang}.csv"
    if not csv_path.exists():
        return

    domain_counts: dict[str, int] = {}
    try:
        with open(csv_path, encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                d = (row.get("domain") or "unknown").strip()
                domain_counts[d] = domain_counts.get(d, 0) + 1
    except Exception:
        return

    parts = "  ".join(f"{d}:{c}" for d, c in sorted(domain_counts.items(), key=lambda x: -x[1]))
    logger.info("[%s] done — ok:%d fail:%d  domains: %s", lang, success, failed, parts)


if __name__ == "__main__":
    sys.exit(main())