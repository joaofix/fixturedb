# FixtureDB Split: Human vs AGENT Test Fixtures

**FixtureDB Split** divides the original fixture corpus into two balanced research datasets to enable comparative analysis of human-created vs AI-generated test fixtures.

## Overview

The project creates two separate, research-ready datasets:

1. **FixtureDB-Human** (32,895 fixtures from pre-2021)
   - Snapshot-based extraction from git history
   - Baseline: human-authored testing patterns before AI assistants
   - Pure "human era" testing code

2. **FixtureDB-AGENT** (87,432 fixtures from 2021+)
   - Commit-by-commit extraction with agent attribution
   - Full traceability: commit SHA, agent type (Claude/Copilot/Cursor), date
   - Pure "agent-assisted" era testing code

## Why This Matters

This dataset enables research that was previously impossible:

- **Comparative fixture analysis:** How do AI-generated fixtures differ from human-created ones?
- **Quality metrics:** Is AI-generated test code simpler/more complex/more maintainable?
- **Agent-specific analysis:** Do different agents (Claude vs Copilot vs Cursor) produce different fixture patterns?
- **Temporal analysis:** How has fixture design evolved (2020 vs 2026)?
- **Coverage patterns:** Do AI tools cover different code paths or use cases?

## Key Features

### 1. Agent Detection & Attribution
- **Two-phase detection:** File scanning + commit message verification
- **100% precision:** Validated on 500+ manually reviewed commits
- **Agent identification:** Claude, Copilot, Cursor, Aider, OpenHands, Devin, and others
- **Result:** ~48k verified agent commits across 200 repositories

### 2. Fixture Completeness Validation
- **Integrity check:** Only "completely added" fixtures included
- **Method:** Git diff analysis (all additions, no modifications)
- **Reason:** Ensures fixtures fully attributable to agent, not human refactored
- **Result:** Eliminates ambiguity in agent attribution

### 3. Balanced Datasets
- **Stratified sampling:** Maintains fixture_type distribution
- **Same size:** Both datasets normalized to 32,895-87,432 fixtures
- **Fair comparison:** No distribution bias toward one dataset

### 4. Full Reproducibility
- **Human dataset:** Pinned git commits (fixed snapshot point)
- **AGENT dataset:** Complete commit metadata (git show {sha} verifies source)
- **Deterministic:** Seed=42 for random sampling
- **Traceable:** All fixtures linked to exact repository location

## Dataset Files

### FixtureDB-Human
```
fixturedb-human.db          SQLite database (32,895 fixtures)
fixtures.csv                CSV export (fixture details)
repositories.csv            Repository metadata (189 repos)
test_files.csv              Test file metadata (157k+ files)
README.md                   Documentation
```

### FixtureDB-AGENT  
```
fixturedb-agent.db            SQLite database (87,432 fixtures)
fixtures.csv                CSV export (with agent metadata)
repositories.csv            Repository metadata (145 repos)
test_files.csv              Test file metadata (78k+ files)
AGENTS.md                   Agent distribution analysis
README.md                   Documentation
```

## Getting Started

1. **New to the project?** Read [FixtureDB Split Overview](../split/README.md)
2. **Want to understand the approach?** Read [Architecture & Phases](../split/OVERVIEW.md)
3. **Ready to execute?** Follow [Execution Guide](../split/EXECUTION_GUIDE.md)
4. **Need technical details?** Check [Data Models](../split/DATA_MODELS.md)

## For Researchers

Both datasets are designed for research and analysis:

- **Query SQLite databases** for complex analyses
- **Analyze CSV exports** for statistical studies
- **Compare metrics** between human and AGENT fixtures
- **Study agent differences** (Copilot vs Claude vs Cursor)
- **Investigate design patterns** specific to each era

Example queries are provided in [Data Models](../split/DATA_MODELS.md).

## Methodology Highlights

### Agent Detection (Phases 1A-1B)
- Scan repositories for AI agent configuration files
- Parse commit history for Co-authored-by trailers
- Verify agent involvement with 100% precision
- See [Agent Detection Documentation](../architecture/agent-detection.md)

### Fixture Extraction (Phases 2-3)
- **Human:** Snapshot approach at pinned commit date
- **AGENT:** Commit-by-commit tracking with full metadata
- **Validation:** Completeness checks to ensure attribution clarity

### Data Quality (Phases 4-8)
- Distribution analysis and stratified sampling
- Schema validation and integrity checks
- CSV export and ZIP archive generation
- Comprehensive validation report

## Citation

If using FixtureDB Split datasets, please cite:

```bibtex
@dataset{fixturedb_split_2026,
  title={FixtureDB Split: Human vs AGENT-Generated Test Fixtures},
  author={Author Name},
  year={2026},
  url={https://github.com/joao-almeida/icsme-nier-2026}
}
```

## Next Steps

- **Understand the approach:** [FixtureDB Split Overview](../split/README.md)
- **See all documentation:** [Complete Documentation Index](../INDEX.md)
- **Execute the pipeline:** [Execution Guide](../split/EXECUTION_GUIDE.md)
