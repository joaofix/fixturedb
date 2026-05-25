# FixtureDB and the Between-Group Study

FixtureDB is a cross-language dataset of test fixtures extracted from agent-enabled GitHub repositories.

The study design is a **between-group comparison within repositories**:

- **Dataset basis:** Agent-enabled repositories (containing agent config files like `.claude.md`, `.cursorrules`, etc.)
- **Temporal window:** Post-agent emergence (2023-06-01 onwards)
- **Agent fixtures:** From commits with agent authorship signals (Tier 1 detection: co-authored-by trailers, author signatures)
- **Human fixtures:** From non-agent commits in the same repositories, same temporal window
- **Control variables:** Language, domain, repository star tier, repository age
- **Statistical approach:** Paired tests within repositories (Wilcoxon signed-rank for continuous, McNemar for categorical)

This design enables within-repository comparison of fixtures written by agents vs humans, controlling for repository context.

## Why Within-Repository Design?

- Agents and humans contribute to the same codebases, providing natural pairs
- Within-repository comparison controls for language, framework, and project structure
- Same temporal window prevents temporal confounding
- Paired tests are more powerful than unpaired tests with matched units
- Direct observation of agent adoption effects within repositories

## What the Pipeline Produces

**Unified database:**
- Single `between-group.db` with fixtures from all agent-enabled repositories
- Each fixture labeled: `commit_kind` (human|agent), `agent_type` (when applicable)
- Control variables computed at temporal snapshot (2023-06-01)
- Fixture metrics: type, scope, complexity, dependencies, mocks

**Collection summary:**
- Repository statistics: languages, domains, star tiers, contributor counts
- Fixture statistics: extraction rates by language, fixture type distributions
- Agent type breakdown when applicable

**Analysis ready:**
- Paired observations for statistical comparison
- Fixture-level metrics for distribution analysis
- Repository-level context for stratified analysis

