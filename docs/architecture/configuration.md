# Configuration Reference

## Important: Original Pipeline vs Split Pipeline

This document describes configuration for the **original FixtureDB collection pipeline**. 

For the **FixtureDB Split project**, see [Execution Guide](../split/EXECUTION_GUIDE.md) for phase-specific parameters and configuration.

---

## Original Pipeline Configuration

All collection parameters lived in `collection/config.py` for the original pipeline.

### Per-language targets

| Language       | `min_stars` | `target_repos` | Rationale |
|----------------|-------------|----------------|----------|
| Python         | 100         | 1,000          | Large ecosystem, high test culture |
| Java           | 100         | 1,000          | Direct comparability with Hamster |
| JavaScript     | 100         | 800            | Frontend repos often yield few fixtures |
| TypeScript     | 100         | 600            | Younger ecosystem |

### Star tiers

| Tier       | `stars` range | Rationale |
|------------|---------------|----------|
| `core`     | ≥ 500         | Threshold used in Hamster study (Pan et al., 2025). High-quality, mature projects with established testing practices. |
| `extended` | 100–499       | Adds diversity and smaller/emerging projects. 100-star floor aligns with MSR empirical study conventions and balances between popularity and novelty. |

### Quality filters (post-clone)

| Parameter             | Default | Rationale |
|-----------------------|---------|----------|
| `MIN_TEST_FILES`      | 5       | Empirical threshold; repos with fewer test files likely lack testing culture. Aligned with Ahmed et al. (2025) observations on test project characteristics. |
| `MIN_COMMITS`         | 50      | Ensures repositories have sufficient history and are non-trivial projects. Avoids prototype/example repos. |
| `MIN_FIXTURES_FOUND`  | 1       | Only repositories with at least one fixture definition are included in the final dataset (post-extraction filter). Avoids cluttering with test-only but fixture-less repos. |

### Pipeline tuning

| Parameter                          | Default | Notes |
|------------------------------------|---------|-------|
| `CLONE_WORKERS`                    | 12      | Parallel clone threads |
| `CLONE_BATCH_SIZE`                 | 50      | Repos per `clone` invocation (incremental mode) |
| `EXTRACT_WORKERS`                  | 8       | Parallel extraction workers (balanced for SQLite single-writer limit) |
| `MAX_COLLECTION_ITERATIONS`        | 10      | Max balanced collection loop iterations (safety limit) |

---

## Split Pipeline Configuration

### Phase Parameters

See [EXECUTION_GUIDE](../split/EXECUTION_GUIDE.md) for split pipeline phase-specific configuration:

- **Phase 1A-1B:** Agent detection (scans clones/ directory)
- **Phase 2:** Pre-2021 extraction (reads from corpus.db)
- **Phase 3:** AGENT extraction (reads from clones/ and corpus.db)
- **Phase 4-8:** Sampling, export, validation

### Key Differences from Original

| Aspect | Original | Split |
|--------|----------|-------|
| Data source | GitHub Search (SEART-GHS) | Existing corpus.db + clones/ |
| Databases | Single corpus.db | Three separate databases |
| Agent detection | None | Phases 1A-1B (required for Phase 3) |
| Fixture filtering | Language-specific | Temporal (pre-2021 vs 2021+) |
| Output | Single CSV set | Two CSV sets (human + AGENT) |

---

## See Also

- [Execution Guide](../split/EXECUTION_GUIDE.md) — Phase-by-phase execution
- [Data Models](../split/DATA_MODELS.md) — Schema details
- [Agent Detection](./agent-detection.md) — Agent detection methodology
