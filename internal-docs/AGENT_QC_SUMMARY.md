# Agent QC Summary

Date: 2026-05-21

## Overview

This file summarizes the results of the preliminary QC run over the `github-search` candidates. It reports per-language counts and the exact quality-control filters applied by the pipeline.

## Per-language results

- **python**: analysed repos: 12,824 — agent configuration detected: 635 (4.95%)
- **javascript**: analysed repos: 10,506 — agent configuration detected: 238 (2.27%)
- **typescript**: analysed repos: 8,651 — agent configuration detected: 1,141 (13.19%)
- **java**: analysed repos: 4,757 — agent configuration detected: 168 (3.53%)

**Totals**: processed rows: 36,738 — agent configuration detected: 2,182 (≈5.94%)

Notes:
- `analysed repos` = rows in per-language QC CSVs (`github-search/agent/*_agent_repo_qc.csv`).
- `unique repos` deduplicates by `repo_name` across each per-language CSV.
- `config-positive` indicates the repository shallow clone contained one or more agent configuration files.

## Exact QC filters used by the pipeline

These values are read from `collection/config.py` and implemented in the QC code (`collection/agent_repo_preliminar_quality_control.py`, `collection/agent_corpus.py`).

- Temporal boundary for agent commits: `AGENT_CORPUS_START_DATE = 2025-01-01`.
- Minimum star floor used for discovery and language configs: `MIN_STARS = 100` (per-language configs also use this by default).
- Minimum repository thresholds applied post-clone:
  - `MIN_COMMITS = 100`
  - `MIN_TEST_FILES = 5`
  - `MIN_FIXTURES_FOUND = 1`
- Agent configuration files (direct matches):
  - `.cursorrules`, `.claude`, `.cursor`, `copilot-instructions.md` (listed in `AGENT_CONFIG_FILES`).
- Additional agent config patterns (search patterns):
  - See `AGENT_CONFIG_PATTERNS` (e.g., `CLAUDE.md`, `.claude/`, `.copilot*`, `.cursor/`, etc.).
- Commit-level agent detection on the 500+ star corpus produced no hits, so no commit-level summary is included for that run.

Other pipeline/selection behavior worth noting:
- `read_repo_list()` chooses one search artifact per base name (prefer `-results.csv`/`-results.csv.gz` over JSON) to avoid duplicate dataset processing.
- Progress is saved atomically to `github-search/agent/qc_progress.json` and rebuilt from existing CSVs if corrupted.

## Filters applied earlier (SEART / github-search pre-filtering)


Search artifacts in `github-search/` were created by prior SEART-based queries and file exports. The exact quality filters applied during SEART discovery (upstream of QC) were:

- Language-specific search using GitHub language labels (from `LANGUAGE_CONFIGS`): `Python`, `Java`, `JavaScript`, `TypeScript`.
- SEART quality filters: **≥5 test files**, **≥50 commits**, **≥500 stars**.
- Exclusion keywords applied when building candidate lists in the repo-QC loader and when backfilling the agent commit dataset to avoid tutorials/demos: `EXCLUSION_KEYWORDS` such as `tutorial`, `course`, `example`, `demo`, `homework`, `interview`, `leetcode`, etc.

If you need the exact SEART query strings used to produce each `*-results.*` file, I can extract them from the search logs or the script that generated the `github-search` artifacts (these are external to the QC script and stored alongside the search exports).

---

Generated automatically from the QC outputs and `collection/config.py` on 2026-05-21.
