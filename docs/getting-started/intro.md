# FixtureDB and the Between-Group Study

FixtureDB is a cross-language dataset of test fixtures comparing agent-authored and
human-authored code across three independent corpora.

The study design is a **between-group comparison across three datasets**:

- **Dataset A (agent):** Fixtures introduced by AI coding agents in agent-enabled
  repositories, commits since 2025-01-01.
- **Dataset B (contemporary human):** Fixtures introduced by humans in the *same*
  repositories as Dataset A, same 2025-01-01+ window — a within-repo control that holds
  repository-level confounds (domain, maturity, agent adoption context) fixed.
- **Dataset C (pre-LLM human):** Fixtures introduced by humans in an independent pool of
  repositories created between 2016-01-01 and 2020-12-31, predating LLM-based coding
  assistance entirely — a cross-repo, pre-agent-era baseline.
- **Agent detection:** Tier 1 (co-authored-by/assisted-by/generated-by trailers, author
  identity), checked in that priority order — see
  [Agent Detection](../architecture/agent-detection.md).
- **Control variables:** Language, domain, repository age — computed at each dataset's
  own temporal reference point.
- **Statistical approach:** Unpaired tests (Mann-Whitney U for continuous variables,
  chi-square for categorical), since A/B/C are three separate databases rather than
  matched pairs within one table.

This design supports two related but distinct comparisons: A-vs-B ("within-repo," same
repos, same window, isolates authorship) and A-vs-C ("cross-repo," different repos,
different era, isolates the pre-/post-agent distinction). Treat them as separate
questions — see [Analyzing the Datasets](../usage/usage.md) for why they shouldn't be
pooled into one undifferentiated "agent vs. human" comparison.

## Why Three Datasets?

- A-vs-B alone can't distinguish "agents write fixtures differently" from "any commit in
  an agent-adopting repo looks different" — the same-repo control isolates authorship.
- A-vs-B alone also can't distinguish a genuine agent effect from a general secular trend
  in how fixtures are written over time — Dataset C's pre-agent-era baseline is what
  separates those two explanations (at the cost of a different repo pool; see
  [Limitations](../reference/limitations.md)).
- Three independent per-dataset databases, rather than one shared table with a role
  column, keep each dataset's provenance and temporal reference point unambiguous.

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
- Repository statistics: languages, domains, contributor counts
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

Dataset C is independent of A/B and can be collected in any order — see
`discover-repos --dataset c` / `extract-fixtures --dataset c` in
[Repository Structure](repository-structure.md) for the full verb-to-dataset matrix and
AGENTS.md for details.
