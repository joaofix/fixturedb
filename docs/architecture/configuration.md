# Configuration Reference - FixtureDB Between-Group Study

This document describes configuration options for the between-group study collection pipeline.

## Three-Stage Pipeline

The between-group study uses a three-stage CLI-based pipeline:

```
Stage 1: python pipeline.py human    → Human corpus (pre-2021)
Stage 2: python pipeline.py agent    → Agent corpus (2025+)
Stage 3: python pipeline.py between-group-stats → Statistical comparison
```

All configuration is via command-line arguments (no configuration files needed).

## Stage 1: Human Corpus Collection

```bash
python pipeline.py human [OPTIONS]
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `--repos-per-language` | INT | 100 | Target fixtures per language |
| `--language` | STR | (all) | Specific language: python, java, javascript, typescript |
| `--output-db` | PATH | data/between-group.db | SQLite database output path |

### Control Variables (Fixed)

Control variables are **computed automatically** at 2020-12-31 snapshot:

| Variable | Description |
|----------|-------------|
| `language` | Programming language (python, java, javascript, typescript) |
| `domain` | Repository domain (computed from topics/description) |
| `star_tier` | GitHub stars tier at snapshot (core: ≥500, extended: 100-499) |
| `repo_age_years` | Repository age in years at 2020-12-31 |

### Example

```bash
# Collect 100 Python fixtures from pre-2021 repositories
python pipeline.py human --repos-per-language 100 --language python

# Collect all languages, 200 fixtures each
python pipeline.py human --repos-per-language 200

# Specify output database location
python pipeline.py human --repos-per-language 100 --output-db output/my-between-group.db
```

## Stage 2: Agent Corpus Collection

```bash
python pipeline.py agent [OPTIONS]
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `--repos-per-language` | INT | 100 | Target fixtures per language |
| `--language` | STR | (all) | Specific language: python, java, javascript, typescript |
| `--github-token` | STR | $GITHUB_TOKEN | GitHub API token (for rate limits) |
| `--output-db` | PATH | data/between-group.db | SQLite database output path |

### Control Variables (Fixed)

Control variables are **computed automatically** at 2025-01-01 snapshot:

| Variable | Description |
|----------|-------------|
| `language` | Programming language |
| `domain` | Repository domain |
| `star_tier` | GitHub stars tier at snapshot |
| `repo_age_years` | Repository age in years at 2025-01-01 |
| `agent_type` | Agent classifier: claude, copilot, cursor, aider, or NULL |
| `commit_kind` | Always 'agent' for Stage 2 |

### Agent Detection

Agents detected via **Tier 1 (author metadata + co-authored-by trailers)**:

```
Agent patterns recognized:
- co-authored-by: Claude <claude@anthropic.com>
- co-authored-by: GitHub Copilot <copilot@github.com>
- co-authored-by: Cursor <cursor@anysoftware.io>
- co-authored-by: Aider <aider@paul.pub>
```

### Example

```bash
# Collect 100 agent-authored fixtures per language
python pipeline.py agent --repos-per-language 100

# Collect JavaScript only with authentication
export GITHUB_TOKEN=github_pat_...
python pipeline.py agent --language javascript --repos-per-language 50

# Override rate limit behavior with explicit token
python pipeline.py agent --github-token $GITHUB_TOKEN
```

## Stage 3: Statistical Comparison

```bash
python pipeline.py between-group-stats [OPTIONS]
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `--db` | PATH | data/between-group.db | Between-group database |
| `--human-stats` | PATH | output/human_corpus_summary_*.json | Human corpus JSON |
| `--agent-stats` | PATH | output/agent_corpus_summary_*.json | Agent corpus JSON |
| `--output-dir` | PATH | output/ | Output directory for results JSON |

### Statistical Tests

Stage 3 runs the following tests:

| Control | Test | Interpretation |
|---------|------|-----------------|
| language | Chi-square test | p ≥ 0.05 → balanced |
| domain | Chi-square test | p ≥ 0.05 → balanced |
| star_tier | Chi-square test | p ≥ 0.05 → balanced |
| repo_age_years | Mann-Whitney U | p ≥ 0.05 → balanced |

Results saved to JSON file in output directory.

### Example

```bash
# Run comparison with default output locations
python pipeline.py between-group-stats

# Specify custom paths
python pipeline.py between-group-stats \
  --db output/my-between-group.db \
  --human-stats output/custom_human.json \
  --agent-stats output/custom_agent.json \
  --output-dir output/comparison/
```

## Temporal Boundaries

Fixed snapshot dates (not configurable):

| Corpus | Snapshot Date | Repositories | Rationale |
|--------|---------------|--------------|-----------|
| Human | 2020-12-31 | Created before 2021 | Pre-AI agent era |
| Agent | 2025-01-01 | Created before 2025-01 | Agent availability (2025+) |

These dates ensure:
- No agent involvement in human corpus (2021 < 2025)
- Sufficient agent maturity by 2025-01
- ~2.5 year temporal gap for framework/practice evolution

## Database Configuration

Both stages use the same database with different corpora:

```sql
-- Human fixtures
SELECT COUNT(*) FROM fixtures WHERE commit_kind = 'human';

-- Agent fixtures
SELECT COUNT(*) FROM fixtures WHERE commit_kind = 'agent';

-- Filtered by agent type
SELECT agent_type, COUNT(*) FROM fixtures
WHERE commit_kind = 'agent'
GROUP BY agent_type;
```

## Quality Filters

### Stage 1 (Human)

Auto-applied filters:
- Repositories created on or before 2020-12-31
- At least 5 test files found
- At least 1 fixture extracted

### Stage 2 (Agent)

Auto-applied filters:
- Repositories with agent commits (co-authored-by trailers)
- At least 1 fixture extracted
- Tier 1 agent detection only (no heuristics)

## Logging and Monitoring

Both stages produce JSON summaries:

```
output/
├── human_corpus_summary_20240115_143022.json
├── agent_corpus_summary_20240115_160545.json
└── between_group_comparison_20240115_161500.json
```

Check JSON for:
- `summary.total_fixtures` — Fixture counts
- `control_variables.distributions` — Balance statistics
- `qa_results` — Quality assurance checks

## Environment Variables

| Variable | Usage | Example |
|----------|-------|---------|
| `GITHUB_TOKEN` | GitHub API auth (Stage 2) | github_pat_1A2B3C4D5E6F |
| `PYTHONPATH` | Module import path | `export PYTHONPATH=$PWD` |

## Advanced Options

### Memory Management

```bash
# For limited-memory machines (< 2GB)
python pipeline.py human --repos-per-language 10

# For high-memory machines (8GB+)
python pipeline.py agent --repos-per-language 500
```

### Database Optimization

```bash
# Rebuild indexes after collection
sqlite3 data/between-group.db "VACUUM; ANALYZE;"

# Check database health
sqlite3 data/between-group.db "PRAGMA integrity_check;"
```

## See Also

- [Reproducing Results](../usage/reproducing.md) — Step-by-step collection guide
- [Database Schema](./database-schema.md) — Table structure and columns
- [Agent Detection](./agent-detection.md) — How agents are identified

