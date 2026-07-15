# Repository Domain Classification

FixtureDB uses two complementary domain classification systems: a fast heuristic classifier embedded in the database layer, and an optional LLM-based classifier for higher accuracy.

## Heuristic Classifier (Default)

The primary domain classification is performed by `collection/db.py::classify_domain()`, which uses keyword matching over repository topics and description. This classifier runs automatically during corpus collection and populates the `domain` control variable in the `repositories` table.

### Domains

| Domain | Keywords |
|--------|----------|
| `web` | web, rest, http, frontend, react, vue, angular, django, flask, rails |
| `systems` | kernel, driver, os, system, compiler, linux, windows, unix |
| `ml` | machine learning, ml, ai, neural, deep learning, tensorflow, pytorch, scikit |
| `security` | security, crypto, encryption, ssl, tls, auth, oauth |
| `database` | database, db, sql, nosql, mongodb, postgresql, mysql, cache, redis |
| `devops` | devops, kubernetes, docker, ci/cd, jenkins, ansible, terraform |
| `other` | Fallback when no keywords match |

### Usage

The heuristic classifier is called automatically by `compute_repo_metadata()` in `collection/corpus_utils.py`:

```python
from collection.corpus_utils import compute_repo_metadata

metadata = compute_repo_metadata(repo_dict, temporal_reference="2025-01-01")
# Returns: {"domain": "web", "repo_age_years": 4.5}
```

No manual invocation is needed during normal collection.

## LLM Classifier (Optional)

An optional LLM-based classifier is available via `python -m collection classify`. This module reads raw GitHub search results from `github-search-raw/*.csv.gz`, optionally enriches them with README excerpts from the GitHub API, and writes labeled CSVs to `github-search-labeled/`.

### Domains (LLM)

| Domain | Description |
|--------|-------------|
| `web` | HTTP servers, REST/GraphQL APIs, web frameworks, frontend frameworks, web tooling |
| `library` | Reusable packages, SDKs, client libraries, utility frameworks (not primarily web) |
| `data` | Data science, ML, data pipelines, analytics, notebooks |
| `infra` | DevOps, cloud infrastructure, containers, CI/CD, monitoring, system software |
| `cli` | Command-line tools, build systems, developer tooling, automation scripts |
| `other` | Does not clearly fit any category |

### Command

```bash
python -m collection classify \
  --language python \
  --workers 10 \
  --provider openrouter \
  --skip-readme
```

### Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--language` | (all) | Limit to one language |
| `--workers` | 10 | Concurrent workers |
| `--provider` | openrouter | `openrouter` or `ollama` |
| `--skip-readme` | false | Skip README fetching from GitHub |
| `--sample N` | 0 | Process only N repos (for testing) |
| `--toy` | false | Sample 10 random repos per language for quick test |
| `--seed` | 42 | Random seed for `--toy` |

### Providers

**OpenRouter (default)**
- Model: `openai/gpt-4o-mini`
- Requires `OPENROUTER_KEY` in `.env`
- Rate-limited via token bucket (4,500 req/hr target)

**Ollama (local)**
- Model: `qwen3:14b`
- Requires local Ollama server at `OLLAMA_BASE_URL` (default: `http://localhost:11434`)
- Workers capped at 4 to avoid overwhelming local hardware

### Input/Output

- **Input:** `github-search-raw/{language}.csv.gz` — GitHub API search results
- **Output:** `github-search-labeled/{language}.csv` — Per-language labeled repos

Output columns: `name`, `mainLanguage`, `domain`, `confidence`, `reasoning`

### Relationship to Heuristic Classifier

The LLM classifier and the heuristic classifier use **different domain taxonomies**. The heuristic classifier (used in the collection pipeline) produces domains: `web`, `systems`, `ml`, `security`, `database`, `devops`, `other`. The LLM classifier produces: `web`, `library`, `data`, `infra`, `cli`, `other`.

Currently, the collection pipeline uses the heuristic classifier. The LLM classifier output is stored in `github-search-labeled/` for inspection and potential future integration.

## Configuration

Key settings in `collection/config.py`:

```python
CLASSIFY_INPUT_DIR = ROOT_DIR / "github-search-raw"
CLASSIFY_OUTPUT_DIR = ROOT_DIR / "github-search-labeled"
CLASSIFY_WORKERS = 10
OPENROUTER_KEY = os.getenv("OPENROUTER_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = "openai/gpt-4o-mini"
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen3:14b"
```
