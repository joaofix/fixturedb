# FixtureDB and the Between-Group Study

FixtureDB is a cross-language dataset of test fixtures comparing agent-authored and human-authored code across three independent corpora.

The study design is a between-group comparison across three datasets:

- **Dataset A (agent)** — fixtures introduced by AI coding agents in agent-enabled repositories, commits since 2025-01-01.
- **Dataset B (contemporary human)** — fixtures introduced by humans in the *same* repositories as Dataset A, same 2025-01-01+ window. This is a within-repo control that holds repository-level confounds (domain, maturity, agent adoption context) fixed.
- **Dataset C (pre-LLM human)** — fixtures introduced by humans in an independent pool of repositories created between 2016-01-01 and 2020-12-31, predating LLM-based coding assistance entirely. This is a cross-repo, pre-agent-era baseline.

Agent detection uses Tier 1 (co-authored-by/assisted-by/generated-by trailers, then author identity — see [Agent Detection](../architecture/agent-detection.md)). Control variables are language, domain, and repository age, each computed at its own dataset's temporal reference point. Because A, B, and C are three separate databases rather than matched pairs in one table, all statistical comparisons are unpaired: Mann-Whitney U for continuous variables, chi-square for categorical.

This design supports two related but distinct comparisons: A-vs-B ("within-repo," same repos, same window, isolates authorship) and A-vs-C ("cross-repo," different repos, different era, isolates the pre-/post-agent distinction). Treat them as separate questions — see [Analyzing the Datasets](../usage/usage.md) for why they shouldn't be pooled into one undifferentiated "agent vs. human" comparison.

## Why three datasets?

A-vs-B alone can't distinguish "agents write fixtures differently" from "any commit in an agent-adopting repo looks different" — the same-repo control isolates authorship. But A-vs-B alone also can't rule out a general secular trend in how fixtures are written over time, independent of agents; Dataset C's pre-agent-era baseline is what separates a genuine agent effect from that trend, at the cost of drawing from a different repo pool (see [Limitations](../reference/limitations.md)). Keeping three independent per-dataset databases, rather than one shared table with a role column, keeps each dataset's provenance and temporal reference point unambiguous.

## What the pipeline produces

Each dataset gets its own database (`db/a.db`, `db/b.db`, `db/c.db` — see [Database Schema](../architecture/database-schema.md)). Dataset A's fixtures are tagged `commit_kind='agent'` plus `agent_type`; Dataset B's are tagged `commit_kind='human'`; Dataset C has no commit-level tagging (see the schema doc for why). Control variables are computed at each dataset's own temporal snapshot (2025-01-01 for A/B, 2020-12-31 for C), alongside fixture metrics for type, scope, complexity, dependencies, and mocks.

A collection summary (`datasets/{dataset}/summary.yaml`, via `python -m collection summarize --dataset {a,b,c}`) reports repository statistics (languages, domains, contributor counts), fixture statistics (extraction rates by language, fixture type distributions), and, for Datasets A/B, the purity-gate acceptance rate.

The result is analysis-ready: independent per-dataset samples for unpaired comparison, fixture-level metrics for distribution analysis, and repository-level context for stratified analysis.

## Recommended extraction flow

All collection runs through one unified CLI: `python -m collection <verb> --dataset {a,b,c}`. To ensure the human control sample (Dataset B) is drawn only from repositories where agents actually produced fixtures, run the verbs in this order:

1. `discover-repos --dataset a` scans `github-search-raw/`, detects agent configuration files, and writes the per-language repo lists to `datasets/a/repos/{language}_repo.csv`.

	```bash
	python -m collection discover-repos --dataset a --language java
	```

2. `discover-commits --dataset a`, then `filter-test-commits --dataset a`, then `extract-fixtures --dataset a` detect agent test commits and extract Dataset A's fixtures, writing the per-language repo lists that yielded fixtures to `datasets/a/fixtures/repos/{language}_fixture_repos.csv`. Dataset B's repo pool is resolved from this output.

	```bash
	python -m collection discover-commits    --dataset a
	python -m collection filter-test-commits --dataset a
	python -m collection extract-fixtures    --dataset a --language java
	```

3. `discover-repos --dataset b`, then `filter-test-commits --dataset b`, then `extract-fixtures --dataset b` resolve Dataset B's repo list from Dataset A's already-collected repos (same agent-enabled repos, human-authored commits only), and write fixtures to `datasets/b/fixtures/{language}_fixtures.csv`.

	```bash
	python -m collection discover-repos      --dataset b
	python -m collection filter-test-commits --dataset b
	python -m collection extract-fixtures    --dataset b --language java
	```

Dataset C is independent of A/B and can be collected in any order — see `discover-repos --dataset c` / `extract-fixtures --dataset c` in [Repository Structure](repository-structure.md) for the full verb-to-dataset matrix, and `AGENTS.md` for details.
