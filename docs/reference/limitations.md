# Limitations

This page lists the known threats to the study. Each entry says what the
problem is, what we do about it, and what is still open.

## Study design

**Time and authorship are mixed.** Agent fixtures come from 2025 onward.
Human fixtures come from repositories created by 2020. Any difference can come
from who wrote the code, from when it was written, or from both. The design
cannot separate the two. We report differences between the groups, not causes.

**Human fixtures are a snapshot.** Human fixtures are read at 2020-12-31. Agent
fixtures are read at the commit that added them. Fixtures that were edited later
were not captured as they were first written.

**The comparison is unpaired.** The two datasets come from different
repositories. Control variables (language, domain, repository age) are compared
with a balance test. In the current data, none of the three is balanced between
the two datasets. See `research_questions/balance.md` for the numbers.

## Sampling

**Popular repositories.** Repositories are filtered to at least 500 stars and
100 commits. Popular projects may test more carefully than typical projects.
Both datasets use the same filters, so the bias affects both sides.

**Four languages.** Python, Java, JavaScript and TypeScript only. Ruby (RSpec),
Kotlin, Scala, Rust and C# are not included.

## Agent detection

**Agents without a trace are counted as human.** Detection uses commit trailers
and author names. An agent that leaves neither is classified as human. The
number of agent commits is therefore a lower bound.

**Name collisions.** Some author names look like agent names. Manual review
found real people with the names `devin` and `cline`, and a placeholder identity
for `codex`. The broad `devin` and `cline` patterns were removed. The `codex`
placeholder is excluded in `known_human_collisions.csv`. The real Devin bot
identity (`devin-ai-integration`) is kept.

**Tangled commits are dropped.** An agent commit is kept only if it adds lines
and deletes none. Agent fixtures edited in a commit that also deletes code are
missing. The agent fixture count is therefore conservative.

## Repository data

**Duplicate repositories.** Two `repo_name`s can share the same history, for
example after an organisation transfer. Dataset A removes repositories that
share the same current HEAD commit. It also removes commits that appear under
more than one name. Dataset C checks each candidate against the others at its
cutoff commit. A pair that diverged before collection is not caught.

**Commits missing from Dataset A.** An earlier cross-check found agent commits
in some repositories that were not in Dataset A's commit list. The cross-check
was part of the removed second dataset. A likely cause is that the clone reads
only the default branch at the time of cloning. This is not confirmed. A rerun
of `discover-commits` on the affected repositories would test it.

**Language tags.** A repository has one language tag. Its test files can be in
other languages. In Dataset A, 8.04% of fixtures (4,061 of 50,498, measured
2026-07-31) are in a different language from their repository tag. This is part
of the corpus and is reported, not removed. Dataset C's rate needs a new run to
measure.

**Repositories disappear.** Repositories can be deleted or made private after
they were collected. Dataset C pins a commit and is not affected by new
commits. Dataset A reads the current history.

## Fixture and mock detection

**Recall is not measured per group.** Both groups use the same detector, but
recall can differ if agent code follows the framework idioms more closely than
human code. This has not been measured. The planned manual validation should
include a sample of human fixtures for this.

**Missing fixture styles.** The detector covers the main fixture mechanisms of
each framework. Custom helper functions, runtime-generated fixtures and niche
frameworks are missed. The exact list of covered and excluded patterns is in
[`fixture_definitions.yaml`](../../collection/heuristics/fixture_definitions.yaml).

**Missing mock libraries.** Mock detection uses regular expressions over the
fixture body. It covers 9 mock frameworks. Niche libraries such as PowerMock and
nock are not covered. The list is in
[`feature_extraction_patterns.yaml`](../../collection/heuristics/feature_extraction_patterns.yaml).
Mocks outside the fixture body are not counted.

**Parametrised tests.** A parametrised test counts once, not once per parameter
set. Projects that parametrise heavily show fewer fixtures per test than they
really use.

**Metric caveats.** Lines of code, cyclomatic complexity and comment density are
computed on fixture bodies. Java rules (`@Rule`, `@ClassRule`) are fields, not
methods. Their complexity is a default value, not a measurement. The metric
notes are in the [dataset card](../data/dataset-card.md).

## Statistics

**Repository-level tests.** Fixtures in the same repository are not independent.
Continuous metrics are summarised per repository before testing. Categorical
results are reported as repository shares, not fixture counts.

**Multiple comparisons.** Per-language p-values are corrected with
Benjamini-Hochberg within each metric. Overall p-values are not corrected.

## Validation

No inter-rater agreement (Cohen's kappa) has been measured. Precision and recall
of the agent detection and fixture detection are estimated from a manual sample
drawn with `validation_sampling.py`. The sampling method is in
[Manual validation](../usage/validation-sampling.md).
