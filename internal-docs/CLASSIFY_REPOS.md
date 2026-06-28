# Repository Domain Classifier (`classify_repos.py`)

> **Created**: 2026-06-27  
> **Module**: `collection/classify_repos.py`  
> **CLI**: `python -m collection classify [options]`

---

## Overview

Classifies ~23,488 GitHub repositories (from SEART-GHS) into one of six domain categories using **GPT-4o-mini via OpenRouter**. Outputs labeled CSVs to `github-search-labeled/`.

### Domain categories

| Category | Description | Examples |
|----------|-------------|----------|
| `web` | HTTP servers, REST/GraphQL APIs, web frameworks, frontend frameworks, web tooling | Django, Express, React, FastAPI, Spring Boot |
| `library` | Reusable packages, SDKs, client libraries, utility frameworks (not primarily web) | pandas, lodash, Guava, testing libraries |
| `data` | Data science, ML, data pipelines, analytics, notebooks | PyTorch, TensorFlow, Airflow, Spark, Jupyter |
| `infra` | DevOps, cloud infrastructure, containers, CI/CD, monitoring, system software | Docker tools, K8s operators, Terraform, Prometheus |
| `cli` | Command-line tools, build systems, developer tooling, automation scripts | linters, formatters, task runners, compilers |
| `other` | Does not clearly fit any category | — |

---

## Architecture

```
github-search-raw/*.csv.gz          (input: 4 files, ~23K repos)
        │
        ▼
  load_repos_from_raw()             (reads CSV.gz, parses metadata)
        │
        ▼
  READMEEnricher.fetch()            (optional: GitHub API → first 200 words)
        │
        ▼
  RepoClassifier.classify()         (OpenRouter GPT-4o-mini → JSON)
        │
        ▼
  write_result()                    (append to github-search-labeled/{lang}.csv)
```

### Key classes

| Class | Role |
|-------|------|
| `RepoClassifier` | Wraps OpenRouter API call, builds prompt, parses JSON response, retries on failure |
| `READMEEnricher` | Fetches README from GitHub API, truncates to 200 words, thread-safe in-memory cache |
| `GitHubRateLimiter` | Token-bucket rate limiter (4,500 req/hr) to stay under GitHub's 5,000/hr limit |

### Key functions

| Function | Role |
|----------|------|
| `load_repos_from_raw()` | Reads `*.csv.gz` files, extracts name/description/language/topics/labels |
| `load_completed_repos()` | Reads existing output CSVs for resume support |
| `write_result()` | Thread-safe append to `{language}.csv` (guarded by `threading.Lock`) |
| `_classify_one()` | Worker: fetch README → classify → return result |
| `_parse_topics()` | Normalizes semicolon-separated or JSON-array topics |

---

## Concurrency & rate limiting

### GitHub API rate limiter

`GitHubRateLimiter` is a **token-bucket** that caps GitHub API calls at **4,500 req/hr** (90% of the 5,000/hr authenticated limit). Workers call `acquire()` before each README fetch — if no tokens are available, the thread blocks briefly and retries.

- **Burst capacity**: starts with a full bucket (4,500 tokens), so the first ~4,500 calls go through instantly
- **Sustained rate**: ~1.25 req/s after the bucket drains
- **Thread safety**: `threading.Lock` protects the token counter; `acquire()` spins with 50ms sleep when empty

### CSV writes

`write_result()` uses a single `threading.Lock` (`_write_lock`) held only for the duration of the `open()`/`write()`/`close()` — microseconds. No starvation risk even with many workers.

### README cache

`READMEEnricher._cache` is guarded by `threading.Lock`. Cache hits skip the rate limiter entirely.

### Recommended workers

| Scenario | Workers | Bottleneck |
|----------|---------|------------|
| With READMEs | **10** (default) | GitHub rate limiter (1.25 req/s sustained) |
| Without READMEs (`--skip-readme`) | **15–20** | OpenRouter API latency only |

With READMEs, the rate limiter is the bottleneck — 10 workers is plenty since they'll mostly be waiting on `acquire()`. Without READMEs, you can push higher since OpenRouter has no hard rate limit.

---

## Prompt design

**System prompt** (~50 tokens): classification rules, 6 categories, JSON output format.

**User prompt** (~150 tokens): repo name, description, language, topics, labels, README excerpt.

**Response**: `max_tokens=100`, `temperature=0.0`. Expected JSON:
```json
{"domain": "web", "confidence": "high", "reasoning": "Django-based web framework"}
```

### Cost estimate

| Item | Estimate |
|------|----------|
| Input tokens per repo | ~200 |
| Output tokens per repo | ~50 |
| Total input (23,488 repos) | ~4.7M |
| Total output | ~1.2M |
| **Total cost (GPT-4o-mini)** | **~$1.80** |

---

## CLI usage

```bash
# Full run (all 4 languages, with README fetching):
python -m collection classify --workers 10

# Toy mode: 10 random repos per language (40 total), full pipeline:
python -m collection classify --toy

# Single language, sample of 50:
python -m collection classify --language python --sample 50

# Resume is automatic — just re-run the same command
```

### Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--language` | all | Filter to one of: `python`, `javascript`, `java`, `typescript` |
| `--workers` | 10 | Concurrent worker threads |
| `--skip-readme` | off | Skip GitHub README fetching (faster, less accurate) |
| `--sample N` | 0 (all) | Process N repos per language |
| `--toy` | off | Sample 10 random repos per language (40 total) |
| `--seed` | 42 | Random seed for `--toy` sampling |

---

## Output format

**Directory**: `github-search-labeled/`  
**Files**: `python.csv`, `javascript.csv`, `java.csv`, `typescript.csv`

**Schema**:
```csv
name,mainLanguage,domain,confidence,reasoning
owner/repo,Python,web,high,Django-based web framework
```

---

## Resume / idempotency

- **Per-language checkpoints**: repos are processed one language at a time. Each language's CSV is written to disk before the next language starts. If the process crashes during `python`, only `python` progress is lost — `java` and `javascript` (already completed) are safe.
- On startup, reads all existing `github-search-labeled/*.csv` files
- Skips any repo whose `name` already appears in output
- Safe to interrupt and re-run — only incomplete languages are processed

### Per-language summary

After each language completes, a domain distribution summary is logged:

```
[java] done — ok:3744 fail:0  domains: library:1200  web:800  data:600  cli:500  infra:400  other:244
```

---

## Input data

**Source**: [SEART-GHS](https://seart-ghs.si.usi.ch/), downloaded 2025-05-25

| Language | File | Repos |
|----------|------|-------|
| Python | `python.csv.gz` | 8,119 |
| TypeScript | `typescript.csv.gz` | 6,331 |
| JavaScript | `javascript.csv.gz` | 5,294 |
| Java | `java.csv.gz` | 3,744 |
| **Total** | | **23,488** |

**Quality filters**: ≥500 stars, ≥100 commits, ≥5K non-blank LOC, excluding forks.

**Columns used**: `name`, `description`, `mainLanguage`, `topics`, `labels`.

---

## Configuration

All constants in `collection/config.py`:

```python
OPENROUTER_KEY = os.getenv("OPENROUTER_KEY", "")       # set in .env
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = "openai/gpt-4o-mini"
CLASSIFY_WORKERS = 10
CLASSIFY_INPUT_DIR = ROOT_DIR / "github-search-raw"
CLASSIFY_OUTPUT_DIR = ROOT_DIR / "github-search-labeled"
```

---

## Testing

**Test file**: `tests/collection/test_classify_repos.py` — **54 tests**, all passing.

### Test coverage

| Test class | What it covers |
|------------|---------------|
| `TestParseTopics` | JSON array, semicolon-separated, empty, single value, fallback |
| `TestParseResponse` | Valid JSON, markdown fences, invalid JSON, invalid domain/confidence, truncation |
| `TestClassify` | Web repo, with README, retry logic, exhausted retries, missing API key |
| `TestGitHubRateLimiter` | Token consumption, blocking when empty, refill over time, max cap, thread safety |
| `TestREADMEEnricher` | Success, 404, caching (hit + miss), network error |
| `TestLoadReposFromRaw` | Single language, filter, all languages, invalid names, fallback columns |
| `TestLoadCompletedRepos` | Empty dir, reads classified, multiple files, corrupted file |
| `TestWriteResult` | Header+row, append, language case normalization |
| `TestClassifyOne` | Without enricher, with enricher (README passed to classify) |
| `TestMainCLI` | `--toy` sampling, seed reproducibility, `--sample` per-language, resume, `--language` filter, all-completed early exit, per-language checkpoint, partial resume after crash |
| `TestValidation` | Domain and confidence value sets |

### Running tests

```bash
python -m pytest tests/collection/test_classify_repos.py -v
```

---

## Dependencies

- `openai>=1.0.0` — OpenRouter-compatible client
- `tqdm` — progress bars (already in project)
- `OPENROUTER_KEY` in `.env` — API key for OpenRouter
- `GITHUB_TOKEN` in `.env` — for README fetching (optional, works without but hits lower rate limits)

---

## Related files

| File | Relationship |
|------|-------------|
| `collection/config.py` | Configuration constants |
| `collection/__main__.py` | CLI subcommand registration |
| `collection/github_fetch.py` | Reference pattern for GitHub API calls |
| `collection/test_commit_filter.py` | Reference pattern for reading `*.csv.gz` |
| `collection/cloner.py` | Reference pattern for `ThreadPoolExecutor` |
| `collection/csv_adapter.py` | Reference pattern for CSV I/O |
| `collection/resume_utils.py` | Reference pattern for resume/skip logic |
| `collection/db.py:classify_domain()` | Existing keyword-based classifier (different approach) |