# Storage and Scale Estimates

## During collection (temporary)

Each shallow clone occupies roughly 50–200 MB depending on repository size.
With 4 parallel workers the peak transient disk usage is:

```
4 workers × 200 MB = ~800 MB peak during cloning
```

Clones are deleted immediately after extraction, so sustained disk usage
stays low even over a long collection run.

## Final dataset (permanent)

Based on the target collection of ~4,000 searched repos and an expected
~60 % survival rate after filters (~2,400 analysed repos):

| Item                                   | Estimate |
|----------------------------------------|-------------|
| SQLite database (without `raw_source`) | ~150–300 MB |
| SQLite database (with `raw_source`)    | ~1–3 GB |
| All CSV exports (without `raw_source`) | ~130–200 MB |
| Zenodo zip (without `raw_source`)      | ~150–250 MB |

**Note on storage:** The latest estimates include two new aggregated CSV files:
- `repository_statistics.csv` — Aggregated metrics per repository (47 KB)
- `test_file_statistics.csv` — Aggregated metrics per test file (13 MB)

The `raw_source` column in the SQLite database dominates storage. The Zenodo
deposit excludes it from CSVs by default but includes it in the SQLite file,
giving researchers access to the full fixture text while keeping the primary
download size manageable.

## Database (corpus.db) growth during a run

The pipeline writes incrementally. You can query progress at any time:

```bash
python pipeline.py stats
```
