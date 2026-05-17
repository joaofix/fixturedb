# Corpus Structure Visualization

## Directory Layout

```
icsme-nier-2026/
│
├── collection/
│   ├── seart_seeder.py                    # SEART API client
│   ├── seart_seed_collection.py          # CLI tool (refactored for corpus)
│   └── ...
│
├── corpus/                                 # Corpus base directory (auto-created)
│   │
│   ├── corpus-1/                          # First seeding run
│   │   ├── corpus.db                      # SQLite: discovered repos
│   │   ├── README.md                      # Metadata + data age (Aug 5, 2024)
│   │   ├── seed-query.json               # Search criteria (reproducible)
│   │   │
│   │   ├── python-repos.csv              # Python repos (tabular)
│   │   ├── python-repos.json             # Python repos (JSON)
│   │   │
│   │   ├── java-repos.csv                # Java repos
│   │   ├── java-repos.json               
│   │   │
│   │   ├── javascript-repos.csv          # JavaScript repos
│   │   ├── javascript-repos.json         
│   │   │
│   │   ├── typescript-repos.csv          # TypeScript repos
│   │   └── typescript-repos.json         
│   │
│   ├── corpus-2/                          # Second seeding run (different criteria)
│   │   ├── corpus.db
│   │   ├── README.md
│   │   ├── seed-query.json
│   │   └── {language}-repos.{csv,json}
│   │
│   └── corpus-3/                          # Third seeding run, etc.
│       └── ...
│
├── docs/
│   └── data/
│       └── 04-seart-ghs-seeding.md       # Full documentation
│
├── tests/
│   └── test_seart_seeding.py             # Tests for SEART integration
│
└── README.md                              # Project overview

```

## Corpus File Details

### corpus-N/corpus.db

SQLite database with 4 tables:
- **repositories** — Discovered repos with `status='discovered'`
- **test_files** — Empty (populated by Phase 3)
- **fixtures** — Empty (populated by Phase 4)
- **mock_usages** — Empty (populated by Phase 5)

### corpus-N/README.md

Example contents:
```markdown
# FixtureDB Corpus Metadata

Corpus Directory: `corpus-1/`
Created: 2026-04-14T18:30:00.123456Z
Data Source: SEART GHS

## Data Currency

️ Important: SEART database contains data as of August 5, 2024.
- Repository Count: 928,546 (in SEART dump)
- Dump File Size: 1.3 GB
- Limitations: Repos created after Aug 5, 2024 not included

## Search Criteria

```json
{
  "languages": ["python", "java", "javascript", "typescript"],
  "stars_min": 0,
  "commits_min": 1,
  "exclude_forks": true
}
```

## Repositories Collected

Total: 12,345 repositories

By Language:
- Python: 4,560 repositories
- Java: 3,120 repositories
- JavaScript: 2,890 repositories
- TypeScript: 1,775 repositories
...
```

### corpus-N/seed-query.json

Complete query specification:
```json
{
  "timestamp": "2026-04-14T18:30:00.123456Z",
  "seart_ghs_api": "http://localhost:48001/api",
  "search_criteria": {
    "languages": ["python", "java", "javascript", "typescript"],
    "stars_min": 0,
    "commits_min": 1,
    "exclude_forks": true
  }
}
```

### corpus-N/{language}-repos.csv

Tab

ular format for Excel/pandas:
```csv
id,name,owner,url,description,language,stargazers,forks,createdAt,updatedAt,...
123456,pytest,pytest-dev,https://github.com/pytest-dev/pytest,The pytest framework,python,10500,850,2010-01-01T00:00:00Z,2026-04-13T12:00:00Z,...
...
```

### corpus-N/{language}-repos.json

Full JSON records (same data as CSV):
```json
[
  {
    "id": 123456,
    "name": "pytest",
    "owner": {"login": "pytest-dev"},
    "url": "https://github.com/pytest-dev/pytest",
    "description": "The pytest framework",
    "language": "Python",
    "stargazers": 10500,
    "forks": 850,
    "createdAt": "2010-01-01T00:00:00Z",
    ...
  },
  ...
]
```

## Workflow

1. **Seeding (Phase 0)**
   ```bash
   python -m collection.seart_seed_collection \
     --stars-min 0 \
     --commits-min 1
   
   # Creates: corpus/corpus-1/
   ```

2. **Cloning (Phase 2)**
   ```bash
   python pipeline.py --phase clone --corpus corpus-1
   # Populates: corpus-1/test_files (but initially empty)
   ```

3. **Extraction (Phase 3)**
   ```bash
   python pipeline.py --phase extract --corpus corpus-1
   # Populates: corpus-1/test_files table
   ```

4. **Detection (Phase 4)**
   ```bash
   python pipeline.py --phase detect --corpus corpus-1
   # Populates: corpus-1/fixtures table
   ```

5. **Classification (Phase 5)**
   ```bash
   python pipeline.py --phase classify --corpus corpus-1
   # Populates: corpus-1/mock_usages table
   ```

## Multiple Corpora Example

```bash
# Corpus 1: All repos (baseline)
python -m collection.seart_seed_collection
# Creates: corpus/corpus-1/

# Corpus 2: High-quality only
python -m collection.seart_seed_collection --stars-min 500 --commits-min 50
# Creates: corpus/corpus-2/

# Corpus 3: 2020 repos (temporal analysis)
python -m collection.seart_seed_collection \
  --created-min 2020-01-01 \
  --created-max 2020-12-31
# Creates: corpus/corpus-3/
```

Result:
```
corpus/
├── corpus-1/  (all repos, different analysis)
├── corpus-2/  (500+ stars, quality analysis)
└── corpus-3/  (2020 repos, temporal analysis)
```

## Data Flow

```
SEART GHS API
(928,546 repos as of Aug 5, 2024)
          ↓
Phase 0: SEARCH
          ↓
[Query SEART with criteria]
    ↓
[organize_repos_by_language()]
    ↓
[save_repos_to_files()]        [generate_corpus_readme()]
    ↓                                  ↓
CSV + JSON files        README.md (with data age)
    ↓
corpus-N/
    ├── seed-query.json      [reproducibility]
    ├── {lang}-repos.*       [inspection]
    └── corpus.db            [Phase 2-5 processing]
```

## Citation Format for Papers

Reference a specific corpus in your paper:

> Repositories were seeded from SEART GHS using the criteria documented in `corpus/corpus-1/seed-query.json`. 
> The SEART database reflects repository metadata as of August 5, 2024 
> (see `corpus/corpus-1/README.md` for full metadata and limitations).

Exact query from `corpus-1/seed-query.json`:
```json
{
  "timestamp": "2026-04-14T18:30:00.123456Z",
  "search_criteria": {
    "languages": ["python", "java", "javascript", "typescript"],
    "stars_min": 0,
    "commits_min": 1,
    "exclude_forks": true
  }
}
```

This provides complete reproducibility and auditability.
