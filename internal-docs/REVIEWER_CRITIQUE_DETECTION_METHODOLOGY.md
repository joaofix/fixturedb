# Reviewer Critique: Agent-Detection & Fixture-Detection Methodology

Academic-reviewer-style critique of the agent-activity-detection and fixture-detection
methodology shared across Datasets A, B, and C. See `docs/reference/limitations.md` and
`docs/architecture/agent-detection.md` for the published threats-to-validity
disclosures this critique builds on top of (deliberately not duplicated below).

## Status

| # | Gap | Status |
|---|-----|--------|
| 1 | No completed empirical validation study (precision/recall/kappa) | **Open** — infrastructure exists (`collection/validation_sampling.py`), never run end-to-end on real (non-toy) data. Already disclosed in `docs/reference/limitations.md`. |
| 2 | Differential recall across authorship groups — the detector may have systematically higher recall on agent-authored code (canonical trailers, textbook `@pytest.fixture` usage) than on idiosyncratic human code | Documented as an unresolved threat to validity in `docs/reference/limitations.md` ("Differential Recall Across Authorship Groups"). Resolves alongside #1 if that validation run is stratified by `agent_type`/`commit_kind`. |
| 3 | Purity-gate rejection rate not compared between corpora | Resolved — `python -m collection summarize --dataset {a,b,c}` reports purity-gate acceptance rate per dataset/language in `{dataset}/summary.yaml`. |
| 4 | Dataset B's elevated false-negative floor vs. Dataset C not called out specifically | Resolved — see `docs/reference/limitations.md`, "Differential False-Negative Risk: Dataset B vs. Dataset C". |
| 5 | No regression protection on recall claims over time | Resolved — `tests/collection/test_gold_fixture_regression.py`: hand-verified real fixtures per language, byte-checked against the actual GitHub source, runs automatically in CI. |

## What already holds up

A rigorous reviewer would not get far with generic complaints — most of the obvious
ones are already pre-empted, with reasoned tradeoffs on record:

- Word-boundary matching for agent-name collisions (the "Claude Smith" case is
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

## Open item

**#1 — empirical validation study.** When it runs: draw the sample via
`collection/validation_sampling.py`, and stratify explicitly by `agent_type`/
`commit_kind` (not just language) so recall-by-authorship-group is directly
measurable — this closes gap #2 as a byproduct rather than needing a separate
validation effort. Deferred until the full (non-toy) dataset is collected.
