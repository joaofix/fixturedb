# Reproducing the Datasets

## Reproducing the Original Corpus (corpus.db)

The original FixtureDB corpus is reproducible via `pinned_commit` SHA stored in the `repositories` table.

```bash
# Query the pinned commit for a specific repository
sqlite3 corpus.db \
  "SELECT full_name, pinned_commit FROM repositories
   WHERE full_name = 'pytest-dev/pytest';"

# Re-clone at the exact state used in the paper
git clone https://github.com/pytest-dev/pytest.git
cd pytest
git fetch --depth 1 origin <pinned_commit>
git checkout <pinned_commit>
```

This approach ensures fixtures are extracted from the exact same code state documented in the paper.

---

## Reproducing the Split Datasets

For the **FixtureDB Split** project, reproducibility is handled differently:

### Human Dataset (fixturedb-human.db)
- Based on `corpus.db` at pinned_commit
- Deterministic: Same input → same output
- Reproducible command:
  ```bash
   python -m collection phase-2
  ```

### AGENT Dataset (fixturedb-agent.db)
- Based on git commits in clones/ directory
- Deterministic: Same commit history → same output
- Reproducible components:
  1. Agent detection: Co-authored-by trailer matching (100% precision)
  2. Fixture completeness: Git diff analysis (deterministic)
  3. Stratified sampling: Seed=42 (reproducible)

```bash
# Full reproducibility requires:
# 1. Exact same clones/ repository snapshots
# 2. Same agent pattern library
# 3. Same date cutoff (2021-01-01)

python -m collection phase-1a
python -m collection phase-1b
python -m collection phase-2
python -m collection phase-3
python -m collection phase-4
python -m collection phase-5
python -m collection phase-6-7
python -m collection phase-8
```

---

## Verifying Extraction State

### Check corpus.db Integrity
```bash
# Verify original corpus exists and is valid
sqlite3 corpus.db "SELECT COUNT(*) as total_fixtures FROM fixtures;"

# Verify all 200 repositories are present
sqlite3 corpus.db "SELECT COUNT(*) as total_repos FROM repositories;"
```

### Check Split Database Integrity
```bash
# Verify pre-2021 extraction
sqlite3 fixturedb-human.db "SELECT COUNT(*) as total_fixtures FROM fixtures;"

# Verify AGENT extraction with agent data
sqlite3 fixturedb-agent.db "SELECT agent_type, COUNT(*) FROM fixtures GROUP BY agent_type;"
```

---

## Determinism & Reproducibility Guarantees

### Fully Deterministic (Phase 2, 4-8)
- **Phase 2:** Snapshot extraction (same input → same output)
- **Phase 4:** Distribution analysis (pure aggregation)
- **Phase 5:** Stratified sampling (seed=42 makes it reproducible)
- **Phase 6-7:** Export (deterministic CSV generation)
- **Phase 8:** Validation (deterministic checks)

### Conditionally Deterministic (Phase 1, 3)
- **Phase 1A:** Depends on file system state (repos must be present)
- **Phase 1B:** Depends on git history (repos must be cloned)
- **Phase 3:** Depends on git diff output (same repos → same output)

**Guarantee:** If clones/ snapshots are frozen, all 8 phases are fully reproducible.

---

## Limitations on Reproducibility

### GitHub-Dependent Issues
1. **Repository deletions:** If repos are deleted, Phase 1-3 cannot run
   - **Mitigation:** Use Zenodo deposit (archives the data state)
2. **Repository changes:** If repos are modified, Phase 1-3 gives different results
   - **Mitigation:** Clone at fixed commit (Phase 2 already does this)

### Determinism Issues
1. **SQLite write ordering:** May vary on different systems
   - **Mitigation:** Indexes ensure consistent query results
2. **Floating point precision:** Statistics may differ slightly
   - **Mitigation:** Minimal rounding - no significant impact

---

## See Also

- [Execution Guide](../split/EXECUTION_GUIDE.md) — How to run each phase
- [Database Schema](../architecture/database-schema.md) — Data structure reference
- [Agent Detection](../architecture/agent-detection.md) — Determinism of agent matching
- [Data Models](../split/DATA_MODELS.md) — Schema details
