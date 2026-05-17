# Human vs Agent Fixture Collection Pipeline

Two-tier methodology for comparing human-created vs LLM-generated fixtures.

## Overview

This pipeline implements the following approach:

1. **Tier 1 (Within-Repo Comparison)**: Search the existing ~500-repo corpus for agent commits (2022+)
   - Eliminates confounders: same project, domain, team culture
   - Expected yield: ~30-80 repos with agent fixture activity

2. **Tier 2 (Between-Repo Comparison)**: If Tier 1 insufficient, use SEART to find matched repos
   - Matching criteria: same language, similar stars, similar domain, agent config files
   - Explicitly labeled in final data (tier=1 vs tier=2)
   - Added only to supplement Tier 1 for statistical power

## Phases

### Phase 1A: Scan Corpus Repos for Agent Commits
```bash
python -m collection phase-1a
```
Searches the ~500-repo corpus for agent commits (Co-authored-by trailers, 2022+).
Output: JSON with agent commits per repo, ready for Phase 1B verification.

### Phase 1B: Verify Agent Commits
```bash
python -m collection phase-1b
```
Verifies Co-authored-by trailers in detected commits.
Confirms agent authenticity with high confidence.

### Phase 1C: Assess Tier 1 Yield
```bash
python -m collection phase-1c
```
Evaluates if Tier 1 meets statistical power thresholds:
- Minimum 30 repos with agent commits
- Minimum 100 agent commits total

Recommends Tier 2 if insufficient.

### Phase 1D: Discover Matched Repos (Tier 2)
```bash
python -m collection phase-1d
```
**Only runs if Phase 1C flags Tier 1 insufficient.**

Uses SEART to find supplementary repos with agent activity.
Matching criteria: same language, similar stars, similar domain, agent config files.

### Toy Dataset: Quick Validation Mode
```bash
python -m collection toy
```
Builds a small validation dataset with 20 repositories per language by default.
Use `--language python` to restrict to one language, or `--repos-per-language 20` to override the default target.

### Phase 2: Extract Pre-2021 Fixtures
```bash
python -m collection phase-2
```
Extracts human-created fixtures using snapshot-based approach at pinned commits.
Creates `fixturedb-human.db`.

### Phase 3: Extract LLM Fixtures
```bash
python -m collection phase-3
```
Extracts agent-generated fixtures from verified agent commits (Tier 1 + Tier 2).
Each fixture includes:
- `commit_sha`: Exact commit where fixture was added (for verification)
- `agent_type`: claude/copilot/cursor/github-actions/other
- `tier`: 1 (corpus repo) or 2 (matched repo)
- `is_complete_addition`: Validation flag

Creates `fixturedb-llm.db`.

### Phase 4: Analyze Distribution
```bash
python -m collection phase-4
```
Analyzes fixture distribution across both datasets.

### Phase 5: Stratified Sampling
```bash
python -m collection phase-5
```
Samples pre-2021 fixtures to match LLM fixture count.
Ensures balanced comparison (same N for both datasets).

### Phase 6-7: Export and Documentation
```bash
python -m collection phase-6-7
```
Exports both databases as CSV + ZIP archives.
Creates methodology documentation.

### Phase 8: Final Validation
```bash
python -m collection phase-8
```
Validates both datasets for quality, completeness, and consistency.

## Quick Start

```bash
cd /home/joao/icsme-nier-2026

# Quick validation dataset (20 repos per language by default)
python -m collection toy

# Or use the umbrella CLI
python -m collection toy

# Step 1: Scan corpus for agent commits (Tier 1)
python -m collection phase-1a

# Step 2: Assess if Tier 1 is sufficient
python -m collection phase-1c

# Step 3: If needed, discover Tier 2 repos (placeholder for SEART integration)
python -m collection phase-1d

# Step 4: Extract fixtures
python -m collection phase-2
python -m collection phase-3

# Step 5: Continue with analysis and export
python -m collection phase-4
python -m collection phase-5
python -m collection phase-6-7
python -m collection.phase_8_final_validation
```

## Output Files

- **fixturedb-human.db**: Balanced human-created fixture dataset
- **fixturedb-llm.db**: Balanced agent-generated fixture dataset (with tier labels and commit info)
- **export/**: Exported CSV and ZIP files
- **output/**: Phase-by-phase JSON results and statistics

## Database Schema

Both databases include core columns from corpus.db, plus LLM-specific additions (in fixturedb-llm.db):

- `commit_sha`: Exact commit where fixture added
- `agent_type`: Agent type (for attribution)
- `tier`: Tier 1 or 2 (for transparent reporting)
- `is_complete_addition`: Validation flag

## Reporting

When publishing results:

> "X repos in the existing corpus had agent commits (Tier 1, within-repo comparison); 
> supplemented with Y matched repos discovered via SEART (Tier 2, between-repo comparison). 
> Results remained consistent across both tiers, supporting the robustness of our findings."

This transparency allows reviewers to understand the methodology and assess any potential biases.

## Configuration

Key thresholds in `collection/config.py`:

- `TIER1_MINIMUM_REPOS_WITH_AGENT = 30`: Minimum corpus repos needed
- `TIER1_MINIMUM_AGENT_COMMITS = 100`: Minimum agent commits needed
- `TIER2_MATCHING_*`: Parameters for SEART-based Tier 2 discovery

## See Also

- [Implementation Plan](../docs/internal/FIXTUREDB_SPLIT_IMPLEMENTATION_PLAN.md)
- [Collection Module](../collection/)
- [Tests](../tests/)
