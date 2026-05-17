# Quick Reference: SEART GHS Seeding

**TL;DR**: Use SEART GHS to seed repositories into a corpus directory with full metadata.

## Output Structure

```
corpus/
├── corpus-1/                    # Auto-incremented corpus directory
│   ├── corpus.db                # SQLite database (ready for Phase 2)
│   ├── README.md                # Metadata, data age, search criteria
│   ├── seed-query.json          # Exact SEART query (reproducible)
│   ├── python-repos.csv         # Repositories by language (CSV)
│   ├── python-repos.json        # Repositories by language (JSON)
│   ├── java-repos.csv
│   ├── java-repos.json
│   ├── javascript-repos.csv
│   ├── javascript-repos.json
│   ├── typescript-repos.csv
│   └── typescript-repos.json
├── corpus-2/                    # Next corpus (auto-incremented)
│   └── ...
```

## Prerequisites

1. **SEART running locally**:
   ```bash
   # Check it's up
   curl http://localhost:7030/   # webserver
   curl http://localhost:48001/api/r/search?page=0&size=5  # API
   ```

2. **SEART database populated** (IMPORTANT!):
   - Empty by default
   - Load pre-populated dump OR enable crawler
   - See [SEART README](https://github.com/seart-group/ghs) for details

3. **Python environment ready**:
   ```bash
   source venv/bin/activate
   pip install -r requirements.txt
   ```

## Basic Usage

### Default (all 4 languages, no star minimum)
```bash
python -m collection.seart_seed_collection
```

Creates `corpus/corpus-1/` with:
- `corpus.db` — Database with discovered repositories (ready for Phase 2)
- `README.md` — Metadata, data age (August 5, 2024), search criteria
- `seed-query.json` — Exact SEART query used (reproducible)
- `{language}-repos.csv` & `.json` — Repositories per language

### High quality (500+ stars)
```bash
python -m collection.seart_seed_collection \
  --stars-min 500 \
  --commits-min 50
```

Creates `corpus/corpus-2/` (auto-incremented)

### Test without writing
```bash
python -m collection.seart_seed_collection --dry-run
```

### Custom corpus base directory
```bash
python -m collection.seart_seed_collection \
  --corpus-dir /projects/my-research
```

## Full Command Help

```bash
python -m collection.seart_seed_collection --help
```

## Verify It Worked

```bash
# Check corpus structure
ls -lh corpus/corpus-1/
cat corpus/corpus-1/README.md

# Count repositories in database
sqlite3 corpus/corpus-1/corpus.db \
  "SELECT language, COUNT(*) as count FROM repositories GROUP BY language;"

# View seed query (reproducibility)
cat corpus/corpus-1/seed-query.json
```

## Troubleshooting

### "Connection refused" at localhost:48001
```bash
# Check SEART is running
curl http://localhost:7030/
```

### No repositories found (0 results)
- SEART database is empty → load dump or enable crawler
- See [SEART README](https://github.com/seart-group/ghs) for setup

### Database locked
- Wait ~30 seconds (retries up to 260s automatically)
- Close any Jupyter kernels using corpus.db

## Continue with Collection

```bash
# Phase 2: Clone repositories (from corpus-1)
python pipeline.py --phase clone --corpus corpus-1

# Phase 3: Extract test files
python pipeline.py --phase extract --corpus corpus-1

# Phase 4: Detect fixtures
python pipeline.py --phase detect --corpus corpus-1

# Phase 5: Classify fixtures
python pipeline.py --phase classify --corpus corpus-1
```

## Publishing

The corpus includes metadata for reproducibility. Include in your paper:

> Repositories were seeded using SEART GHS with criteria documented in `corpus/corpus-1/seed-query.json`. The SEART database reflects repository data as of August 5, 2024.

See `corpus/corpus-1/README.md` for full citation guidance.

## Docs

- **Full guide**: [docs/data/04-seart-ghs-seeding.md](docs/data/04-seart-ghs-seeding.md)
- **Implementation summary**: [SEART_GHS_IMPLEMENTATION_SUMMARY.md](SEART_GHS_IMPLEMENTATION_SUMMARY.md)
- **Tests**: [tests/test_seart_seeding.py](tests/test_seart_seeding.py)

## One-Liner Examples

```bash
# Default seeding (creates corpus/corpus-1/)
python -m collection.seart_seed_collection

# High-confidence repos only
python -m collection.seart_seed_collection --stars-min 500 --commits-min 50

# Dry-run (no writes)
python -m collection.seart_seed_collection --dry-run

# Verbose logging
python -m collection.seart_seed_collection -v

# Custom language subset
python -m collection.seart_seed_collection --languages python java

# Temporal slice (2020 repos only)
python -m collection.seart_seed_collection --created-min 2020-01-01 --created-max 2020-12-31
```

---

**Questions?** See [docs/data/04-seart-ghs-seeding.md](docs/data/04-seart-ghs-seeding.md) for detailed guide, or [SEART_GHS_IMPLEMENTATION_SUMMARY.md](SEART_GHS_IMPLEMENTATION_SUMMARY.md) for FAQ.
