# Limitations and Threats to Validity - FixtureDB Between-Group Study

## Between-Group Study Design

The between-group methodology collects human and agent corpora at different time periods to avoid temporal confounding. However, this design introduces its own limitations:

### Temporal Separation Confounding
- **Human corpus:** Pre-2021 repositories (fixture collection snapshot at 2020-12-31)
- **Agent corpus:** 2025+ repositories with agent commits (fixture collection snapshot at 2025-01-01)
- **Confound:** Changes in Python/JavaScript frameworks, testing best practices, and hardware between 2021 and 2025 may affect fixture patterns independently of agent involvement

**Mitigation:** Control variables (language, domain, repo_age_years) are balanced across corpora using statistical tests (chi-square, Mann-Whitney U) — see `collection/between_group_comparison.py` and [Analyzing the Datasets § Comparing two datasets](../usage/usage.md#comparing-two-datasets). Balance report confirms no significant differences (p ≥ 0.05).

### Agent Detection Conservatism
- **Tier 1 detection only:** Agents identified via `co-authored-by` commit trailers only
- **False negatives:** Agents without proper trailers are classified as human
- **Impact:** True agent detection rate may be higher than reported

**Mitigation:** Use conservative Tier 1 estimates. Tier 2/3 (heuristic-based) detection documented in [Agent Detection Methodology](../architecture/agent-detection.md).

### Differential False-Negative Risk: Dataset B vs. Dataset C
- **Dataset B** draws its repo pool from the *same* agent-adopting repositories as Dataset A (every B repo is a subset of A's agent-config-having pool). This is a real strength for controlling repo-level confounds (domain, maturity) — but it also means B's "human"-labeled commits sit in repos where agent use is actively encouraged, so an untrailed, informally-agent-assisted commit (see "Agent Detection Conservatism" above) is more likely to occur in B than it would in a naive agent-free control.
- **Dataset C** draws from a different, non-agent-config repo pool and does not share this specific elevated risk to the same degree.
- **Impact:** B and C are not interchangeable "human" baselines with respect to this risk. The A-vs-B ("within-repo") and A-vs-C ("cross-repo") comparisons carry different residual confidence even though both nominally compare agent commits against a "human" corpus.

**Mitigation:** None currently measured or applied — this is a structural property of each dataset's repo-selection strategy, not a detection bug to fix. Treat A-vs-B and A-vs-C findings as testing related but distinct questions rather than pooling them into one undifferentiated "agent vs. human" conclusion.

### Repository Availability
- **Human corpus:** Assumes pre-2021 repositories are still publicly available
- **Agent corpus:** Depends on GitHub API availability and rate limits
- **Impact:** Extinct or private repositories cannot be collected

**Mitigation:** `discover-repos` and `discover-commits` query the live GitHub API with error handling; `--tier2` agent discovery additionally falls back to the pre-curated `db/corpus.db`.

### Repository-Level Duplication (Forks, Org Transfers, Shadow Copies)
- **Problem:** Two different `repo_name`s in `github-search-raw/` can share partly or fully identical git history — GitHub org transfers, community mirrors, and independently-created "shadow copies" (a raw `git push` of one repo's history into a brand-new repo object). Each is counted as an independent repository, silently inflating sample size and duplicating fixtures. Not caught by the "exclude forks" query filter applied at source — `isFork=true` appears zero times across the entire raw candidate pool, since GitHub's own fork bookkeeping only covers repos created via its "Fork" button/API.
- **Measured impact on already-collected data** (grouping fixtures by `commit_sha`, flagging SHAs shared across >1 `repo_name`): Dataset A 0.3% (132/46,831), Dataset B 17.9% (33,002/184,772), Dataset C 16.2% (34,653/214,436). Worst single cluster: 5 OpenJDK-derived repos sharing one commit, 21.9% of Java's entire Dataset C corpus.
- **Mitigation (forward-looking, not retroactive):** Dataset C now checks each candidate's commit at the fixed cutoff date against every other candidate via the GitHub API before selection (`collection/dedupe_dataset_c_repos.py`) — a shared commit SHA is a cryptographic guarantee of identical content, never a false positive. Dataset A automatically drops repos currently sharing a HEAD commit (`lastCommitSHA`, already present in the raw SEART export for free) before cloning. Dataset B inherits Dataset A's fix automatically, since its repo pool is resolved from Dataset A's own output. See `internal-docs/methodology-improvements/repo-deduplication.md` for the full investigation.
- **Residual gap, deliberately deferred:** Dataset A's free check only catches repos still byte-identical *today* — a pair that was mirrored for a while and has since diverged (confirmed real example: `datahub-project/datahub`/`linkedin/datahub`, whose SEART-crawled `lastCommitSHA` is stale) is not caught. A complete fix needs full in-window commit-set comparison per repo, not a point-in-time fingerprint. Not implemented.
- **Impact:** the percentages above describe the datasets as currently collected; neither mechanism has been applied retroactively. Analysis drawing on the existing `datasets/{a,b,c}/fixtures/*.csv` should account for this known duplication rate until a re-collection (or an explicitly-scoped retroactive patch) is done.

---

## Sampling bias

Both human and agent corpora are drawn from repositories with ≥500 GitHub stars. Popular,
actively maintained projects may exhibit higher test discipline than typical
open-source software. This is a known limitation in empirical software
engineering studies (Hamster study by Pan et al., 2025) which also used
star-based sampling to ensure sufficient test coverage. To mitigate this bias
and improve generalizability, both corpora are restricted to high-star repositories
across 4 programming languages, and control variables are balanced.

## Language coverage

FixtureDB covers four languages: Python, Java, JavaScript, and TypeScript.
Other languages such as Ruby (RSpec), Kotlin, Scala, Rust, and C# are not included.

## Parametrized Tests

Parametrized test functions are counted as **single test functions**, not multiplied by parameter set count. Test-to-fixture ratio may under-represent reuse in projects with heavy parametrization.

To assess: Query `test_files` for parametrized patterns (regex: `parametrize|ParameterizedTest|test.each`).

---

## Mock detection completeness

Mock detection uses regular expressions over source text. Framework versions
or unusual coding styles may produce false negatives. The `raw_source`
column is included in the SQLite file specifically so that researchers can
re-run or improve detection against the original fixture text.

## Fixture Detection Recall

**Expected detection recall by language:**

| Language | Recall | Notes |
|----------|--------|-------|
| Python | >95% | Strong decorator standardization. Dynamically-created fixtures may be missed. |
| Java | >95% | Annotation-based detection is unambiguous. Custom base class patterns are caught. |
| JavaScript | >90% | Framework conventions vary. Helper functions not matching standard naming patterns may be missed. |
| TypeScript | >90% | Same as JavaScript. Type annotations don't improve fixture detection. |

**Sources of false negatives:**
- Custom helper functions implementing fixture-like behavior without standard naming/decoration
- Metaprogrammed/dynamic fixtures created at runtime
- Non-standard fixture mechanisms that abstract framework APIs

The three bullets above are the general pattern; the exact, per-language list
of what counts as a fixture and what's deliberately excluded (with a reason
for each) is `collection/heuristics/fixture_definitions.yaml` — it is both
the executable pattern table the detector is built from and the audit trail
a reviewer can check against without reading `detector_python.py` /
`detector_java.py` / `detector_javascript.py` directly.

**Mitigation:** `raw_source` column in SQLite allows manual audit. Draw a manual-review sample with `collection/validation_sampling.py` (Cochran's formula, 95% confidence / 5% margin of error by default — see [Manual-Validation Sampling](../usage/validation-sampling.md)) rather than an arbitrary fixed count, to calculate project-specific recall.

---

## Differential Recall Across Authorship Groups

Fixture detection uses the identical AST-pattern detector for both the agent
and human corpora — the same code path, just applied to different input.
Detection is pattern/idiom-based (decorator conventions, naming conventions),
so recall could differ by authorship group even with zero code defects, if
agent-generated code follows canonical framework idioms more consistently
than human-written code (which includes older, idiosyncratic, or
framework-violating styles). If so, a reported between-group difference in
fixture prevalence or characteristics could be partly a detection artifact
rather than a true behavioral difference.

This has not been measured. The current manual-validation design (see
[Manual-Validation Sampling](../usage/validation-sampling.md)'s "Reduced
validation set" table) treats human-fixture-detection validation as
redundant with Dataset A's, on the reasoning that it's "the identical AST
fixture detector" — that justification covers code-path correctness, not
recall, which can depend on the input distribution rather than the code path
alone.

The two between-group comparisons carry different residual risk here:
Dataset B is drawn from the same repositories as Dataset A, so both corpora
are constrained to whatever test framework a repo's human maintainers
already established — an agent cannot introduce a different framework than
what's already in use, which structurally limits (but does not eliminate)
this risk for the A-vs-B comparison. Dataset C (cross-repo) does not share
this constraint.

**Status:** Documented, unresolved. Broadening detector recall for
non-canonical/non-textbook fixture patterns was considered as a mitigation
and is not being pursued.

**Mitigation (deferred):** When the full-dataset manual-validation study is
run, draw an explicit comparison sample from the human corpus (B and/or C)
rather than skipping it as redundant, specifically to test whether recall
differs by authorship group.

---

## Advanced Metrics Limitations

| Metric | Limitation | Mitigation |
|--------|-----------|-----------|
| `has_teardown_pair` | Heuristic detection; implicit cleanup (connection pooling, auto-cleanup) not detected. Ambiguous in JavaScript/TypeScript. | Use `raw_source` for manual verification on important fixtures. |
| `num_contributors` | GitHub API page limit (~30 per page); repos with >100 contributors may be under-counted. | For precise counts, query GitHub API or web interface directly. |
| `max_nesting_depth` | May over-estimate when counting lambda/closure nesting vs. control flow nesting. | Use `cyclomatic_complexity` for cross-validation of structural complexity. |

---

## Validation Status

**Status:** Heuristic-based detection. No inter-rater reliability metrics (Cohen's kappa) available. For critical research, use `collection/validation_sampling.py --step agent-fixtures-dataset-a` to draw a Cochran-sized (95% confidence / 5% margin of error by default) sample per language, then manually inspect it to establish project-specific precision and recall. Human fixture detection uses the identical AST detector and is intentionally not sampled separately — see the reduced validation set in [Manual-Validation Sampling](../usage/validation-sampling.md).

**Language-Specific Confidence:**

| Language | Status | Notes |
|----------|--------|-------|
| Python | High | Decorator-based detection is unambiguous. |
| Java | High | Annotation-based detection is unambiguous. |
| JavaScript | Medium | Framework conventions vary; helper detection relies on naming. |
| TypeScript | Medium | Same as JavaScript. |

**Known gaps:** Parametrized test detection edge cases, false-positive rates (~5–15% for `num_objects_instantiated`).

---

## Mock Detection

30 regex patterns across 11 mock frameworks detected (`unittest.mock`, `pytest-mock`, pytest's built-in `monkeypatch`, Mockito, EasyMock, MockK, Jest, Sinon, Vitest, gomock, testify — see the full, exact list in [collection/heuristics/feature_extraction_patterns.yaml](../../collection/heuristics/feature_extraction_patterns.yaml)'s `mock_patterns`). Coverage excludes niche frameworks (e.g. PowerMock) and non-standard APIs; the exact documented exclusions are in that same file's `mock_patterns_excluded`. Detects mocks within the fixture's own body only — not test bodies, and not module-level setup outside any fixture (e.g. Jest's conventional top-level `jest.mock('./module')` is invisible to this detector even though the pattern exists, since it's structurally outside any fixture's AST node). Treat `num_mocks=0` as reliable only within that scope; use `num_mocks>0` as a presence indicator, not an exact count.

Each detected mock is also classified into the classic test-double taxonomy (Meszaros) — `dummy`/`stub`/`spy`/`mock`/`fake` — as `mock_usages.category`. Classification is keyword-matched against the construct's own name (e.g. `sinon.spy` → spy), with a small set of individually-justified manual overrides for constructs whose name contains no category keyword (`category_override_reason` in the YAML). **`dummy` is never assigned**: whether a double counts as a dummy depends on how it's used afterward (never configured or verified), which requires data-flow analysis, not a keyword match — so it's left undetected by design rather than guessed at low confidence. Treat `category` as a reasonable per-construct classification, not a claim about how each individual mock instance was actually used in its fixture.

---

## Control Variable Balance

The between-group study balances control variables (language, domain, repo_age_years) across human and agent corpora. Balance is verified using:

- **Chi-square test:** Categorical controls (p ≥ 0.05 indicates balance)
- **Mann-Whitney U test:** Continuous controls (p ≥ 0.05 indicates balance)

**Limitation:** Balance testing only checks for differences in distributions; unmeasured confounds (e.g., framework version changes, testing best practices evolution) may still exist.

**Mitigation:** Statistical tests reported in between_group_comparison_*.json. Inspect balance report before drawing conclusions.

