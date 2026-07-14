# FixtureDB and the Between-Group Study

FixtureDB is a cross-language dataset of test fixtures extracted from agent-enabled GitHub repositories.

The study design is a **between-group comparison within repositories**:

- **Dataset basis:** Agent-enabled repositories (containing agent config files like `.claude.md`, `.cursorrules`, etc.)
- **Temporal window:** Post-agent emergence (2025-01-01 onwards)
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

**Per-dataset databases** (`db/a.db`, `db/b.db`, `db/c.db` — see
[Database Schema](../architecture/database-schema.md)):
- Dataset A fixtures tagged `commit_kind='agent'` + `agent_type`; Dataset B tagged
  `commit_kind='human'`; Dataset C has no commit-level tagging (see schema doc for why)
- Control variables computed at each dataset's own temporal snapshot (2025-01-01 for
  A/B, 2020-12-31 for C)
- Fixture metrics: type, scope, complexity, dependencies, mocks

**Collection summary** (`datasets/{dataset}/summary.yaml`, via
`python -m collection summarize --dataset {a,b,c}`):
- Repository statistics: languages, domains, star tiers, contributor counts
- Fixture statistics: extraction rates by language, fixture type distributions
- Purity-gate acceptance rate (Datasets A/B)

**Analysis ready:**
- Independent per-dataset samples for unpaired statistical comparison (A-vs-B, A-vs-C)
- Fixture-level metrics for distribution analysis
- Repository-level context for stratified analysis

## Recommended Extraction Flow

All collection runs through one unified CLI: `python -m collection <verb> --dataset {a,b,c}`.
To ensure the human control sample (Dataset B) is drawn only from repositories where agents
actually produced fixtures, run the verbs in this order:

1. `discover-repos --dataset a` — scans `github-search-raw/`, detects agent configuration
   files, and writes the per-language repo lists to `datasets/a/repos/{language}_repo.csv`.

	```bash
	python -m collection discover-repos --dataset a --language java
	```

2. `discover-commits --dataset a` then `filter-test-commits --dataset a` then
   `extract-fixtures --dataset a` — detects agent test commits and extracts Dataset A's
   fixtures, writing the per-language repo lists that yielded fixtures to
   `datasets/a/fixtures/repos/{language}_fixture_repos.csv`. Dataset B's repo pool (below)
   is resolved from this output.

	```bash
	python -m collection discover-commits    --dataset a
	python -m collection filter-test-commits --dataset a
	python -m collection extract-fixtures    --dataset a --language java
	```

3. `discover-repos --dataset b` then `filter-test-commits --dataset b` then
   `extract-fixtures --dataset b` — resolves Dataset B's repo list from Dataset A's
   already-collected repos (same agent-enabled repos, human-authored commits only), and
   writes fixtures to `datasets/b/fixtures/{language}_fixtures.csv`.

	```bash
	python -m collection discover-repos      --dataset b
	python -m collection filter-test-commits --dataset b
	python -m collection extract-fixtures    --dataset b --language java
	```

See [Repository Structure](repository-structure.md) for the full verb-to-dataset matrix
and AGENTS.md for which verbs apply to Dataset C.

