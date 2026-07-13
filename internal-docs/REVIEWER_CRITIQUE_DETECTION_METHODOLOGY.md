# Reviewer Critique: Agent-Detection & Fixture-Detection Methodology

Written as an academic-reviewer-style critique of the agent-activity-detection and
fixture-detection methodology shared across Datasets A, B, and C — produced during
the toy-dataset qualitative review (Dataset A/B review pass, 2026-07-13). Not
actioned yet; parked here to return to after Dataset C's review. See
`docs/reference/limitations.md` and `docs/architecture/agent-detection.md` for the
existing, already-published threats-to-validity disclosures this critique builds on
top of (deliberately not duplicated below).

## Status (as of 2026-07-13)

| # | Gap | Status |
|---|-----|--------|
| 1 | No completed empirical validation study | **Deferred** — waits until the full (non-toy) dataset is collected. |
| 2 | Differential recall across authorship groups | **Discussed, documented, unresolved.** Detector-broadening mitigation considered and rejected (not pursued). Written up as a threats-to-validity entry in `docs/reference/limitations.md` ("Differential Recall Across Authorship Groups"). The concrete follow-up (validate the human corpus explicitly, not skip it as redundant) is queued into gap #1's eventual execution — see that gap's updated note below. Revisit at a later moment, not today. |
| 3 | Purity-gate rejection rate not compared between corpora | **Addressed (2026-07-13).** Not wired into `between_group_comparison.py` as originally proposed -- instead landed as a standalone `summarize --dataset {a,b,c}` verb writing `{dataset}/summary.yaml`, auditable per-dataset without running a comparison. Also fixed a real gap found along the way: Dataset B never tracked purity accept/reject counts at all (`human_corpus.py` discarded them silently); now written to `test-commits/{lang}_purity_stats.csv`. Real number from toy data: Dataset A's acceptance rate is 47% overall. |
| 4 | Dataset B's elevated false-negative floor not called out specifically | Queued for later today (2026-07-13). |
| 5 | No regression protection on recall claims over time | Queued for later today (2026-07-13). |

## What already holds up

A rigorous reviewer would not get far with generic complaints — most of the obvious
ones are already pre-empted, with reasoned tradeoffs on record:

- Word-boundary matching for agent-name collisions (the "Devin Smith" case is
  explicitly named and handled: trailer checked before author identity).
- Free-text commit-message scanning was tried, produced real false positives
  ("Revert a bad Claude suggestion", "Fix cursor blinking bug"), and was
  deliberately removed — a genuine empirical finding, not a hypothetical.
- Bot-vs-agent disambiguation (`bots.csv` checked first, terminal match).
- Star-based sampling bias disclosed with a citation to prior work (Hamster study,
  Pan et al. 2025) using the same tradeoff.
- Star-count-is-current-not-historical limitation already disclosed in
  `docs/architecture/database-schema.md`.
- Control-variable balance tested statistically (chi-square / Mann-Whitney U)
  between corpora.
- Temporal confounding for Dataset C (2021 vs 2025 snapshots) explicitly named,
  with a stated mitigation (balance testing).

## Gaps that would survive to a rebuttal round

### 1. No completed empirical validation study — only the tooling to run one

`docs/reference/limitations.md` states outright: *"No inter-rater reliability
metrics (Cohen's kappa) available."* `collection/validation_sampling.py`
implements Cochran-sized sampling correctly (verified by reading it), but
`validation-samples/` has never been created or committed — confirmed via
`find` and `git log --all -- validation-samples/` (no hits). The published
recall table (">95% Python/Java, >90% JS/TS" in `limitations.md`) reads as an
informed estimate from the authors, not a measured result from an actual
completed review round. This is the single highest-leverage gap: the
infrastructure to close it already exists, it just has never been run.

**Fix:** Run `validation_sampling.py` end-to-end on real (not toy) data, have
it manually reviewed, and report actual precision/recall/kappa.

**Update (2026-07-13):** When this eventually runs, it must not follow
`docs/usage/validation-sampling.md`'s current "Reduced validation set" table
verbatim — that table marks human-fixture-detection validation "No, uses the
identical AST fixture detector" and skips it as redundant with Dataset A's.
That reasoning covers code-path correctness but not recall, which can depend
on the input distribution (see gap #2). Draw an explicit comparison sample
from the human corpus (B and/or C) as part of this run, specifically to test
whether recall differs by authorship group — this resolves gap #2 as a
byproduct rather than needing a separate validation effort.

### 2. Detection recall may correlate with the independent variable itself (agent vs. human) — a differential-misclassification confound, not yet discussed anywhere

Both agent-detection and fixture-detection are pattern/trailer-based. If
agent-generated code is more likely to follow canonical idioms (structured
`Co-authored-by` trailers from CLI tooling, textbook `@pytest.fixture` usage)
than average human code (older, idiosyncratic, sometimes framework-violating),
the *detector itself* may have systematically higher recall on agent-authored
artifacts. Any between-group difference the paper reports could then be partly
a detection artifact rather than a true behavioral difference. Checked: the
existing recall table in `limitations.md` is broken out by language only,
never by authorship group (`agent_type`/`commit_kind`). This is sharper than
"recall isn't 100%" — it's "recall may not be independent of the thing being
measured."

**Fix:** When running the validation study above, stratify explicitly by
`agent_type`/`commit_kind` so recall-by-group is directly measurable. Either
resolves the concern (recall statistically indistinguishable across groups) or
quantifies a correctable bias.

**Update (2026-07-13):** Discussed. Broadening detector recall for
non-canonical/non-textbook fixture patterns (an alternative mitigation that
would shrink the ceiling on this bias regardless of direction, without
needing measurement) was considered and is **not being pursued**. As a
partial, informal check, a canary comparison was run on already-collected
toy data (fixture-type distribution for A vs. B *within the same
repos*, ~51 overlapping Python repos / ~35 Java repos — not rigorous, small
N, not citable, just illustrative): Python `pytest_class_method` was 9.9%
of agent fixtures vs. 2.2% of human fixtures in the same repos; Java
`junit5_before_each` was 37.2% vs. 27.9%. A real compositional shift is
visible even at toy scale — consistent with either a genuine behavioral
difference (the actual research question) or a detection-recall artifact;
the toy data can't distinguish these without ground truth. Formally
documented as an unresolved threat to validity in
`docs/reference/limitations.md` ("Differential Recall Across Authorship
Groups", added 2026-07-13), including the A-vs-B / A-vs-C asymmetry (B
shares repos with A, so both are constrained to whatever framework the
repo's maintainers already chose — a structural, partial mitigation that
does not apply to C). No further action until gap #1's validation study
runs — see that gap's updated note above for the concrete follow-up.

### 3. Purity-gate rejection rate is tracked per-repo but never compared between corpora — an unmeasured selection-bias risk

The commit-level purity gate (reject the whole commit if *any* touched test
file has a deletion, applied identically to A and B) is good design. But if
agents are systematically more likely to one-shot a whole new test file
(passing the gate) while humans interleave edits into existing files (failing
it more often), the fixtures that *survive* the gate are not a random sample
of each group's test-authorship activity — they're a subset filtered for
atomicity, and that filter's selectivity may itself differ by group.
`agent_corpus.py` already computes `rejected_mixed_test_diff`/`accepted`
counters per repo (confirmed via grep, lines ~539, 727-731, 932-935). Checked
`between_group_comparison.py`: it never references these counters — the data
needed to check this confound already exists in `fixture_repos.csv`, it's
just never surfaced as a between-group diagnostic.

**Fix:** Add purity-gate acceptance rate as a reported diagnostic in
`between_group_comparison.py`'s output, split by group. Cheap — the raw counts
already exist.

**Update (2026-07-13):** Addressed, differently than proposed above. Rather
than folding this into `between_group_comparison.py` (a pairwise-comparison
tool), it's now a standalone per-dataset artifact: `python -m collection
summarize --dataset {a,b,c}` writes `{dataset}/summary.yaml` (real:
`datasets/{dataset}/`, toy: `toy-dataset/{dataset}/`, also written
automatically at the end of `toy`), covering repo/test-commit/fixture counts,
avg fixtures per repo/file, and -- for A and B -- the purity-gate acceptance
rate by language. Building this surfaced a second, real gap: Dataset B's
`human_corpus.py` never tracked purity accept/reject counts at all (Dataset
A's `agent_corpus.py` did, via `fixture_repos.csv`'s `rejected_mixed_test_diff`/
`accepted` columns; B's `_extract_from_agent_commits()` call never passed the
`stats=` dict needed to capture them, so the data didn't exist anywhere to
report). Fixed in `human_corpus.py`; now written to
`test-commits/{lang}_purity_stats.csv`. Real result from the toy data
already on disk: Dataset A's purity-gate acceptance rate is 47% overall
(java 48%, javascript 56%, python 45%, typescript 47%) -- once Dataset B is
collected (real or toy), its rate will be directly comparable via the same
file, which is exactly what this gap asked for.

**Second-pass review (2026-07-13):** a self-review of `summary.yaml` from a
deliberately hostile-reviewer stance caught a real correctness bug, not just
presentation nits: `avg_fixtures_per_repo` divided fixture count by repos
*appearing in fixtures.csv only* -- a repo scanned but yielding zero
fixtures never gets a row there, so it silently vanished from the
denominator instead of pulling the average down. Verified against real toy
data: Dataset A's Python average was reported as 14.93, while the true
corpus-wide average (`fixtures.total / repos.total`, including the 64% of
repos that yielded nothing) is 5.4 -- a 2.76x inflation presented as fact.
Fixed: the old metric is now explicitly named
`avg_fixtures_per_repo_with_fixtures`, and a real
`avg_fixtures_per_repo_overall` (unconditional, overall-only) sits next to
it so the gap is visible instead of hidden. Also fixed on the same pass:
`by_language` was ambiguous between two genuinely different partitions in
this file (a repo's assigned language vs. each fixture's own detected
language) -- renamed to `by_repo_language`/`by_fixture_language`
throughout so the distinction is legible from the key name alone, no prose
explanation required; `sampling_seed` (permanently null for A/B, verified
no RNG is used anywhere in their real `--stratified` path) is now omitted
for those two rather than shown as always-empty; added `schema_version`
and switched the timestamp to explicit UTC.

### 4. Dataset B's "human" baseline has a structurally elevated false-negative floor that the general "Agent Detection Conservatism" section doesn't call out specifically

B draws its repo pool from the *same* agent-adopting repos as A (confirmed
this session: every B repo is a verified subset of A's `fixture_repos.csv`
pool). That's a real strength for controlling repo-level confounds (domain,
maturity) — but it also means B's "human" commits sit in repos where agent use
is actively encouraged, so an untrailed, informally-agent-assisted commit is
more likely to occur in B than it would in a naive agent-free control. C
(different, non-agent-config repos) doesn't share this specific risk at the
same magnitude. `limitations.md`'s "Agent Detection Conservatism" section
discusses false negatives in general but doesn't flag that B and C carry
*different magnitudes* of this specific risk — which matters for how
confidently each comparison (A-vs-B "within-repo" vs A-vs-C "cross-repo") can
be interpreted, and whether they should be presented as interchangeable
"human" baselines in the writeup.

**Fix:** A short sensitivity note distinguishing B's and C's residual-risk
magnitude explicitly. Optionally, a cheap additional signal for B specifically
— e.g. scanning sibling commits in the same PR/branch for agent trailers even
when the specific commit under test lacks one — without resorting to full
free-text scanning (which was already tried and rejected for good reason, see
"What already holds up" above).

### 5. No regression protection ties the published recall claims to the actual detector code over time

This session found and fixed a real double-detection bug in the Python
detector (`detector_python.py`): a method with both a `@pytest.fixture`-style
decorator and a `setup_method`-style name was counted twice (once as
`pytest_decorator`, once as `pytest_class_method`) — found via real toy
Dataset B data (`dagster-io/dagster`), not by the existing unit test suite.
The existing tests check individual pattern rules in isolation; there is no
versioned, human-labeled "gold" sample re-run in CI to catch a recall
regression when detector code changes. So the ">95%" figure in
`limitations.md` has no mechanism keeping it honest as the detector evolves.

**Fix:** A small versioned gold-label regression test — a handful of real,
hand-checked fixtures per language, re-run in CI — distinct from the existing
rule-level unit tests, that would catch future detector drift end-to-end.

## Suggested priority order

1. Run `validation_sampling.py` on real data, get it manually reviewed, report
   precision/recall/kappa (closes #1, and stratifying by group also closes #2).
2. ~~Wire purity-gate acceptance-rate-by-group into `between_group_comparison.py`~~
   **Done (2026-07-13)** — as a standalone `summarize` verb instead (closes #3).
3. Add the B-vs-C residual-risk sensitivity note to `limitations.md` (closes #4;
   documentation-only, no code).
4. Add a versioned gold-label CI regression test (closes #5; moderate effort,
   ongoing payoff).

None of this is being actioned right now — parked here per explicit instruction
to return to after the Dataset C toy-output review.
