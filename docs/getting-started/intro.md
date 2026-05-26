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

## Recommended Extraction Flow

To ensure the human control sample is drawn only from repositories where agents actually produced fixtures, follow this order:

0. Build the repo-QC inputs from `github-search-raw/`. This step scans the raw repository search results, detects agent configuration files, and writes the per-language repo lists to `github-search-agent/agent_repositories/{language}_agent_repo.csv`. You can limit the run to one or more languages with `--languages`.

	Example:

	```bash
	python -m collection.repository_quality_control.agent_repository_counter --source-dir github-search-raw --output-dir github-search-agent/agent_repositories --languages java javascript
	```

1. Run the agent extraction step (per-language). This detects agent test commits, extracts fixtures, and writes per-language repo lists of repositories that yielded agent fixtures to `github-search-agent/agent_fixtures/{language}_agent_fixture_repos.csv`.

	Example:

	```bash
	python -m collection.agent_corpus --languages java javascript --repos-per-language 50
	```

2. Optionally write per-language human test-commit CSVs (the human collector will prefer the agent-produced repo lists). This is useful if you only want to collect test-commit rows without running full fixture extraction.

	```bash
	python -m collection.human_corpus --corpus-db data/corpus.db --repo-qc-dir github-search-agent/agent_repositories --language python --test-commits-csv /path/to/output --only-write-test-commits
	```

3. Run the human fixture extraction step. The human collector will prefer `github-search-agent/agent_fixtures/{language}_agent_fixture_repos.csv` if present and will restrict selection accordingly.

	```bash
	python -m collection.human_corpus --corpus-db data/corpus.db --repo-qc-dir github-search-agent/agent_repositories --language python
	```

Backwards compatibility: if the agent fixture repo lists are not present, the human collector falls back to `github-search-agent/tests_commits/*_agent_test_commit.csv` and then to `github-search-agent/agent_repositories/*_agent_repo.csv`.

