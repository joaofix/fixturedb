# Repository Structure

```
fixture-corpus/
│
├── pipeline.py              # Main CLI — entry point for all operations
├── requirements.txt         # Python dependencies
├── .env.example             # Template for GitHub token configuration
│
├── collection/             # Core pipeline modules
│   ├── config.py            # All tunable parameters (thresholds, targets, paths)
│   ├── db.py                # SQLite schema definition and query helpers
│   ├── github_search_loader.py  # Load repos from SEART-GHS CSV files
│   ├── cloner.py            # Shallow git clone + post-clone quality filters
│   ├── detector.py          # Tree-sitter AST queries (fixture + mock detection)
│   ├── extractor.py         # Per-repo orchestration: files → fixtures → DB
│   ├── classifier.py        # Keyword-based domain labelling (web/cli/data/…)
│   ├── exporter.py          # Produces the Zenodo-ready zip (SQLite + CSVs)
│   └── validator.py         # Manual precision/recall validation scaffold
│
├── clones/                  # Temporary — shallow git clones live here during
│                            # extraction, then are deleted to reclaim disk space
├── data/
│   └── corpus.db            # The SQLite database (primary pipeline output)
│
├── export/                  # Output of `pipeline.py export` — Zenodo artifact
│   └── fixturedb_v*.zip     # Versioned zip: SQLite + CSVs + README
│
├── validation/              # Output of `pipeline.py validate`
│   └── sample_*.csv         # Stratified fixture samples for manual review
│
└── logs/
    └── pipeline.log         # Full pipeline run log
```
