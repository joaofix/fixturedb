# Reviewer Critique: Agent-Detection & Fixture-Detection Methodology

Written as an academic-reviewer-style critique of the agent-activity-detection and
fixture-detection methodology shared across Datasets A, B, and C — produced during
the toy-dataset qualitative review (Dataset A/B review pass, 2026-07-13). Not
actioned yet; parked here to return to after Dataset C's review. See
`docs/reference/limitations.md` and `docs/architecture/agent-detection.md` for the
existing, already-published threats-to-validity disclosures this critique builds on
top of (deliberately not duplicated below).

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
2. Wire purity-gate acceptance-rate-by-group into `between_group_comparison.py`
   (closes #3; cheap, data already exists).
3. Add the B-vs-C residual-risk sensitivity note to `limitations.md` (closes #4;
   documentation-only, no code).
4. Add a versioned gold-label CI regression test (closes #5; moderate effort,
   ongoing payoff).

None of this is being actioned right now — parked here per explicit instruction
to return to after the Dataset C toy-output review.
