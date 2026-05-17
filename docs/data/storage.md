# Storage and Scale Estimates - Split Datasets

## Split Datasets (Final Storage)

Based on the FixtureDB Split project with two separate databases:

### FixtureDB-Human (Pre-2021)
- SQLite database: ~50–100 MB
- CSV exports: ~20–40 MB
- Total: ~80–150 MB
- Fixtures: 32,895
- Repositories: 189

### FixtureDB-AGENT (2021+)
- SQLite database: ~150–250 MB
- CSV exports: ~40–80 MB
- Total: ~200–350 MB
- Fixtures: 87,432
- Repositories: 145

### Combined Datasets
- Total storage: ~280–500 MB
- ZIP archives (with documentation): ~300–550 MB
- With source code included: ~500–1,000 MB

### Temporary Storage During Processing

During Phase 1-8 execution (requires cloned repositories):
- clones/ directory: ~8–12 GB (200 repos × 50–60 MB each)
- Extracted JSON files (Phase 2-5): ~500–800 MB
- Database creation (Phase 6-7): ~300–400 MB
- **Peak disk usage:** ~10–15 GB

After completion, clones/ can be deleted:
- Permanent storage: ~300–500 MB (just the two databases + CSVs)
- Cleanup: `rm -rf clones/` frees 8–12 GB

---

## Database Size Breakdown

### FixtureDB-Human Database
- fixtures table: ~32,895 rows × ~2 KB per row ≈ 65 MB
- test_files table: ~157,000 rows × ~500 B per row ≈ 78 MB
- repositories table: ~189 rows × ~1 KB per row ≈ 190 KB
- indexes: ~5–10 MB
- **Total: ~50–100 MB**

### FixtureDB-AGENT Database
- fixtures table: ~87,432 rows × ~3 KB per row ≈ 262 MB
- test_files table: ~78,000 rows × ~500 B per row ≈ 39 MB
- repositories table: ~145 rows × ~1 KB per row ≈ 145 KB
- indexes: ~10–20 MB
- commit metadata tables: ~5–10 MB
- **Total: ~150–250 MB**

**Note:** Sizes include:
- All indexes for query performance
- Foreign key tables (test_files, repositories)
- Computed columns (agent_type, is_complete_addition)
- Does NOT include raw_source column (fixture source code)

With raw_source included (for research reproducibility):
- FixtureDB-Human: ~200–400 MB
- FixtureDB-AGENT: ~500–1,000 MB

---

## Storage Optimization Tips

### For Paper Writing (CSV Only)
```bash
# Just use CSV exports, ~30–60 MB total
# Sufficient for statistics and plots
du -h *.csv
```

### For Full Reproducibility
```bash
# Store both databases + documentation
# ~300–500 MB
du -h fixturedb-*.db
```

### For Long-Term Archive
```bash
# ZIP with documentation and metadata
# ~300–550 MB (compressed)
zip -r fixturedb-split-2026.zip fixturedb-*.db *.csv README.md SCHEMA.md
```

---

## Comparing to Original FixtureDB

| Aspect | Original | Split |
|--------|----------|-------|
| Single database | corpus.db (~150–300 MB) | Two separate databases (~250–350 MB) |
| Total repos | 200 | Human: 189, AGENT: 145 |
| Total fixtures | 35,169 | Human: 32,895, AGENT: 87,432 |
| CSV exports | 1 set | 2 sets (human + AGENT) |
| Agent metadata | None | Full commit traceability (AGENT only) |

**Key Difference:** Split dataset adds ~100 MB due to duplicate metadata (repositories, test_files) in two databases, but enables independent analysis and comparison.
