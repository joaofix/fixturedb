# Data Collection Process

**Collection Metadata**  
- **Collection Period**: April 1–2, 2026
- **Languages**: Python, Java, JavaScript, TypeScript
- **Repository Selection**: Minimum 500 stars
- **Extraction Timestamp Range**: 2026-04-01 20:16:59 to 2026-04-01 23:18:03 UTC
- **Reproducibility**: All collection parameters pinned in code; repos at specific commits preserved

## Tool Versions (for Reproducibility)

The following tools were used during extraction. See [requirements.txt](../../requirements.txt) for exact pinned versions to replicate the corpus:

```
GitHub API:                    v3 REST API
Tree-sitter:                   Core + language grammars for Python, Java, JavaScript, TypeScript
Complexity Analysis:           Lizard (cyclomatic complexity, LOC, parameters, external call count)
                               Language-specific cognitive complexity tools
Python Runtime:                3.8+
SQLite:                        3.x
```

**Key Tools & Rationale:**

- **Lizard**: Cyclomatic complexity, LOC, parameters, and external function call detection across all languages. Industry-standard tool for reproducible metrics.

- **Language-Specific Cognitive Complexity**: Python uses SonarQube-standard implementation; other languages use Lizard-based formula fallback for consistency.

- **Tree-sitter**: AST parsing for fixture detection, scope analysis, and code structure metrics. Provides consistent abstract syntax representation independent of language syntax quirks.

For exact tool versions, see [requirements.txt](../../requirements.txt).

## Collection Strategy

**Reproducibility**: All versions pinned in [requirements.txt](../../requirements.txt) to ensure bit-for-bit replicability. GitHub API, Tree-sitter grammars, and metric tools can change behavior between versions.

**Time Window**: April 1–2, 2026 (20:16–23:18 UTC). Corpus collection completed without API incidents; all 160 repos successfully analyzed.

---

## Collection Pipeline

The pipeline runs in five sequential phases. Each phase is idempotent — if it
is interrupted and restarted, already-completed work is skipped.

## Phase 1 — Repository Loading from SEART-GHS (`load`)

Rather than querying GitHub directly, repositories are loaded from pre-scraped 
data provided by [SEART-GHS](https://seart-ghs.si.usi.ch/), a curated research 
dataset of GitHub repositories.

### Why SEART-GHS?

Direct GitHub API searching is non-deterministic, temporally unstable, and rate-limited. SEART-GHS provides an immutable, curated dataset with fixed filters and no rate limits — enabling reproducible collection.

### Data Source

CSV files downloaded from https://seart-ghs.si.usi.ch/ and stored locally:

```
github-search/
  ├── python-results.csv.gz
  ├── java-results.csv.gz
  ├── javascript-results.csv.gz
  └── typescript-results.csv.gz
```

### Filtering on Load

Quality filters applied to loaded repositories:
- Not archived (`isArchived = false`)
- Not a fork (`isFork = false`)  
- Minimum commits ≥ 100 (configurable by language)
- Exclude keyword-based repos (`tutorial`, `homework`, `exercise`, `bootcamp`, `demo`, `awesome-*`)

Repositories passing these filters are written to the `repositories` table 
with `status = 'discovered'` and are ready for Phase 2 cloning.

### How to Update the Dataset

When SEART-GHS publishes newer versions or when you want to collect different 
languages:

1. **Visit** https://seart-ghs.si.usi.ch/
2. **Configure filters** (language, minimum stars, minimum commits, etc.)
3. **Download results** as CSV (gzip-compressed)
4. **Place in** `github-search/` folder with naming pattern: `{language}-results.csv.gz`
5. **Run** the pipeline: `python pipeline.py search --language python`

The pipeline will automatically detect the CSV, apply filters, and load 
repositories into the database. Existing repos are updated in-place; new repos 
are inserted.

### Command Reference

```bash
# Load all repos from python-results.csv.gz
python pipeline.py load --language python

# Load only first 1000 repos (useful for testing)
python pipeline.py load --language python --max 1000

# Load from all languages
python pipeline.py load
```

### Documentation References

- **SEART-GHS**: https://github.com/seart-group/ghs (GitHub repository)
- **SEART-GHS Web UI**: https://seart-ghs.si.usi.ch/ (Search and download interface)

## Phase 2 — Cloning

Shallow-clones repositories in parallel. Applies quality filters:
- Commit count ≥ 50 (filters prototypes)
- Test file count ≥ 5 (filters minimal testing culture)

Repos passing both filters marked `cloned`.

## Phase 3 — Extraction

For each cloned repository: walk test files, parse with Tree-sitter, detect fixtures via AST patterns, detect mocks via regex. Results stored in database. Repo marked `analysed` (or `skipped` if zero fixtures found).

## Phase 4 — Domain Classification

Assigns domain label (`web`, `data`, `cli`, `infra`, `library`, `other`) based on repository name, description, and GitHub topics.

## Phase 5 — Export

Produces versioned zip file with:
- **SQLite database** (`fixtures.db`) — Full queryable data with raw source code
- **CSV exports** — Multi-level statistics and individual records:
  - `repositories.csv` — Repository metadata
  - `repository_statistics.csv` — Aggregated metrics per repository
  - `test_files.csv` — Test file metadata
  - `test_file_statistics.csv` — Aggregated metrics per test file
  - `fixtures.csv` — Individual fixture records
  - `stats.txt` — Summary by language

See [data-pipeline-overview.md](../architecture/data-pipeline-overview.md) for schema documentation.
