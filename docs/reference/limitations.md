# Limitations and Threats to Validity - FixtureDB Between-Group Study

## Between-Group Study Design

The between-group methodology collects human and agent corpora at different time periods to avoid temporal confounding. However, this design introduces its own limitations:

### Temporal Separation Confounding
- **Problem:** The human corpus is drawn from pre-2021 repositories (fixture collection snapshot at 2020-12-31), while the agent corpus is drawn from 2025+ repositories with agent commits (snapshot at 2025-01-01). Changes in Python/JavaScript frameworks, testing best practices, and hardware between 2021 and 2025 may affect fixture patterns independently of agent involvement.
- **Mitigation:** Control variables (language, domain, repo_age_years) are balanced across corpora using statistical tests (chi-square, Mann-Whitney U) — see `collection/between_group_comparison.py` and [Analyzing the Datasets § Comparing two datasets](../usage/usage.md#comparing-two-datasets). The balance report confirms no significant differences (p ≥ 0.05).

### Agent Detection Conservatism
- **Problem:** Agents are identified via Tier 1 detection only — `co-authored-by` commit trailers and author identity. Agents without proper trailers are classified as human, so the true agent detection rate may be higher than reported.
- **Mitigation:** Use conservative Tier 1 estimates. Tier 2 (heuristic-based) detection is documented in [Agent Detection Methodology](../architecture/agent-detection.md).

### Differential False-Negative Risk: Dataset B vs. Dataset C
- **Dataset B** draws its repo pool from the *same* agent-adopting repositories as Dataset A (every B repo is a subset of A's agent-config-having pool). This is a real strength for controlling repo-level confounds (domain, maturity) — but it also means B's "human"-labeled commits sit in repos where agent use is actively encouraged, so an untrailed, informally-agent-assisted commit (see "Agent Detection Conservatism" above) is more likely to occur in B than it would in a naive agent-free control.
- **Dataset C** draws from a different, non-agent-config repo pool and does not share this specific elevated risk to the same degree.
- **Impact:** B and C are not interchangeable "human" baselines with respect to this risk. The A-vs-B ("within-repo") and A-vs-C ("cross-repo") comparisons carry different residual confidence even though both nominally compare agent commits against a "human" corpus.

**Mitigation:** None currently measured or applied — this is a structural property of each dataset's repo-selection strategy, not a detection bug to fix. Treat A-vs-B and A-vs-C findings as testing related but distinct questions rather than pooling them into one undifferentiated "agent vs. human" conclusion.

### Repository Availability
- **Problem:** The human corpus assumes pre-2021 repositories are still publicly available; the agent corpus depends on GitHub API availability and rate limits. Extinct or private repositories can't be collected.
- **Mitigation:** `discover-repos` and `discover-commits` query the live GitHub API with error handling; `--tier2` agent discovery additionally falls back to the pre-curated `db/corpus.db`.

### Repository-Level Duplication (Forks, Org Transfers, Shadow Copies)
- **Problem:** Two different `repo_name`s in `github-search-raw/` can share partly or fully identical git history — GitHub org transfers, community mirrors, and independently-created "shadow copies" (a raw `git push` of one repo's history into a brand-new repo object). Each is counted as an independent repository, silently inflating sample size and duplicating fixtures. Not caught by the "exclude forks" query filter applied at source — `isFork=true` appears zero times across the entire raw candidate pool, since GitHub's own fork bookkeeping only covers repos created via its "Fork" button/API.
- **Mitigation:** Dataset C checks each candidate's commit at the fixed cutoff date against every other candidate via the GitHub API before selection (`collection/dedupe_dataset_c_repos.py`) — a shared commit SHA is a cryptographic guarantee of identical content, never a false positive. Dataset A automatically drops repos currently sharing a HEAD commit (`lastCommitSHA`, already present in the raw SEART export for free) before cloning; this only catches repos still byte-identical *today*, not a pair that was mirrored for a while and has since diverged (e.g. `datahub-project/datahub`/`linkedin/datahub`). For that case, `collection/dedupe_commits_by_sha.py` runs after commit-level collection and removes any commit whose exact `commit_sha` was collected under more than one `repo_name` — a shared commit SHA there is the same cryptographic guarantee, just checked post-collection instead of via a live API call. For Dataset A this is fully preventive (`extract-fixtures --dataset a` reads its commit list from the exact file this step cleans, so a removed duplicate is never extracted, on this run or any future one). See `internal-docs/methodology-improvements/repo-deduplication.md` for the full investigation.
- **Dataset B needs a second, recurring mitigation, not just the one above:** `extract-fixtures --dataset b` never reads `datasets/b/test-commits/*.csv` — it independently re-clones and re-scans every repo's full commit history itself, so it silently rediscovers the same duplicate commits under every repo_name variant regardless of how clean that file is. Confirmed at scale on Dataset B's first real python extraction run: 36.6% of extracted fixtures shared a `commit_sha` with a different `repo_name` (real examples beyond `datahub`/`linkedin`: `phidatahq/phidata`/`agno-agi/agno`, `instructor-ai/instructor`/`567-labs/instructor`/`jxnl/instructor`). Mitigated by `collection/dedupe_fixtures_by_sha.py`, which runs the same duplicate-detection logic against the already-extracted `datasets/b/fixtures/*.csv` and `db/b.db` directly — but unlike every other mechanism here, this is a **recurring cleanup that must be run after every `extract-fixtures --dataset b` invocation**, not a one-time fix, since extraction keeps independently reconstructing the duplication on each run. Restructuring extraction to consume the deduped commit CSV directly (which would make this one-time too) is a real, deliberately deferred follow-up — see `internal-docs/methodology-improvements/repo-deduplication.md` section 9.
- **Residual gap:** the commit-level check can only catch a duplicate if both repo_names' shared commits were actually collected in the first place. Two repos diverging before the collection window, or one side failing to yield any collected commits at all (confirmed real example: `camunda/zeebe`/`camunda-cloud/zeebe`/`camunda/camunda`, none of which have any rows in Dataset A's own commit CSVs, for a reason not yet root-caused), have no shared `commit_sha` to key on and are not caught by either mitigation above. Not implemented: a fix would need repo-identity matching independent of what got collected (e.g. a live API check of full commit-set overlap), not just a post-hoc check on already-collected data.

### Dataset A Commit-Discovery Completeness (Cross-Checked via Dataset B)
- **Problem:** Dataset B's independent commit-role scan cross-checks every commit it classifies as agent-authored against Dataset A's already-collected commit list for the same repo (`collection/human_test_commit_filter.py`'s `_check_against_dataset_a()`), logging any disagreement to `datasets/b/test-commits/commit_role_disagreements.csv`. Observed disagreements have all been of type `dataset_a_missing` (Dataset B found an agent commit absent from Dataset A's list for that repo), concentrated in a small subset of repos rather than spread evenly — **none** have been of type `mismatch` (both datasets classifying the same commit differently), so this is not a detection-logic bug: everywhere both datasets examined the identical commit, they agreed.
- **Investigation:** For the most-affected repos checked so far, a large majority of their "missing" commits have author dates *inside* Dataset A's own already-scanned commit-date range for that repo — ruling out "just new activity since Dataset A's snapshot" as the primary explanation. Leading hypothesis, not confirmed: branch-reachability at clone time. Dataset A's single-branch clone only contains whatever was reachable from the default branch *at the moment it was cloned*; a commit authored earlier on a feature branch that merged into the default branch only *after* Dataset A's clone would be invisible to Dataset A regardless of its author date, while Dataset B's later, independent clone of the same repo would see it (with its original, earlier author date intact). Both datasets' commit-trailer detection code was traced and confirmed to share the same underlying logic (`Tier1RepositoryScanner`), ruling out an implementation divergence as the cause.
- **Status:** Documented, unconfirmed, not pursued further. Whether this means Dataset A's fixture corpus is missing real agent-authored fixtures for the affected repos (i.e. whether a fresh re-collection would grow the corpus) has not been tested.
- **Mitigation:** None applied. Treat Dataset A's commit corpus, and any fixture counts derived from it, as a point-in-time snapshot that can undercount a repo's true agent-commit activity, especially for actively-developed repos with long-lived feature branches. `commit_role_disagreements.csv` is the audit trail; re-running `discover-commits --dataset a` for the affected repos would test (but has not yet tested) whether the gap actually closes.

### Cross-Language Fixture Leakage
- **Problem:** A repo's `language` (its single SEART-assigned tag) is a repo-level label, not a per-file fact — a "python" repo can genuinely contain a JavaScript config-test file, a Java repo a Python tooling script, etc. When extraction discovers test files from a commit's full diff (Datasets A/B) or a checkout snapshot (Dataset C), it can find and extract fixtures from these non-primary-language files too. This is real corpus content, not corruption, but it means "the python corpus" isn't 100% python by file, and it needs to be measured and reported, not silently ignored.
- **Measurement, no new column needed:** every fixture's own detected language is already captured on `test_files.language` (set from the fixture's own file extension at persist time — see `collection/corpus_utils.py::persist_repository_and_fixtures()`), separate from `repositories.language` (the repo's tag). Leakage is a straight join:
  ```sql
  SELECT COUNT(*) AS total, SUM(CASE WHEN tf.language != r.language THEN 1 ELSE 0 END) AS leaked
  FROM fixtures f
  JOIN test_files tf ON f.file_id = tf.id
  JOIN repositories r ON f.repo_id = r.id;
  ```
- **Measured rates (2026-07-31):** Dataset B 12.15% (8,302/68,346), Dataset A 8.04% (4,061/50,498), Dataset C 0% at the time of measurement — **not because C's repos are more language-homogeneous**, but because `dataset_c.py` used to discover test files by checking each file against the repo's own tagged language only (`find_test_files_at_commit()`), never even looking for other-language files. Fixed (2026-07-31): `find_test_files_with_language()` now detects each file's own language from its extension, matching how A/B already discover test files — see `docs/architecture/collection.md`'s "Sampling modes". C's real leakage rate isn't known yet; it requires a fresh `extract-fixtures --dataset c --force` run to materialize, since leaked fixtures were never extracted under the old code, not merely mislabeled (nothing to backfill on already-collected data).
- **Mitigation:** none needed beyond measurement — leakage is not an error to eliminate, just a corpus property to disclose. Report the rate per dataset; do not assume 100% language purity when describing corpus composition in the paper.

### Agent-Identity Name Collisions (`devin`/`cline`/`codex`)
- **Problem:** manual validation review of Dataset A's `agent-commits-dataset-a` sample (2026-07-17, live-verified against real GitHub commits) found real authors misattributed via exact name/email/employer-domain collisions with no trailer to disambiguate — e.g. authors literally named "Devin Jameson"/"Devin Robison", a human surnamed "Cline", actual Cline-company employees (including its creator) committing under an `@cline.bot` work email, and a repo-internal placeholder bot (`codex-review@example.com`) unrelated to real OpenAI Codex. See [Agent Detection § Known Limitations](../architecture/agent-detection.md#known-limitations) for the full investigation.
- **Mitigation:** the collision-causing `devin`/`cline` patterns are removed from `collection/heuristics/agent-mining/agent_authors.csv` entirely; the `codex` placeholder identity is excluded via `known_human_collisions.csv` (the bare `codex` pattern itself is still needed for genuine trailer-based detection elsewhere). The real Devin AI bot identity (`devin-ai-integration`) and genuine trailer-based Codex detection are untouched and still correctly detected.

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

Parametrized test functions are counted as single test functions, not multiplied by parameter set count. Test-to-fixture ratio may under-represent reuse in projects with heavy parametrization.

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
| `has_teardown_pair` | Heuristic detection; implicit cleanup (connection pooling, auto-cleanup) not detected. Ambiguous in JavaScript/TypeScript. Pairing is intra-file only — a setup fixture's teardown counterpart defined in a different file (e.g. inherited from a Java base test class) is never detected. | Use `raw_source` for manual verification on important fixtures. |
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

Each fixture is also classified into the classic test-double taxonomy (Meszaros) — `dummy`/`stub`/`spy`/`mock`/`fake` — as `mock_usages.category`. Classification scans the fixture's own full body text, case-insensitively, for one of the five category terms in priority order (dummy > stub > spy > fake > mock), falling back to `mock` when none is found — an identifier-keyword method, not a lookup keyed on which framework matched. One category is computed per fixture and applied to every mock recorded in it, so a fixture that legitimately creates two differently-named mocks (e.g. both a `dummy_x` and a `real_service_mock`) gets the same category for both, since classification isn't re-run per individual mock call. Treat `category` as a per-fixture classification, not a claim about how each individual mock instance was specifically used.

---

## Control Variable Balance

- **Problem:** RQ1-3's comparisons are only informative about authorship/era if the underlying repo samples are otherwise comparable — if domain or repo age differ systematically between two datasets, a metric difference could reflect that instead of what's being attributed to it. This was described as verified (`between_group_comparison_*.json`, generated by `BetweenGroupComparator`) but never actually was: that class reads from a `between-group.db` that has never existed in this repo, and isn't wired into `collection/__main__.py`'s CLI anywhere — leftover from an earlier architecture, before the current Dataset A/B/C split. No such JSON file has ever existed.
- **Mitigation:** `collection/research_questions/balance.py` (added 2026-07-31) checks this for real, against the current `db/{a,b,c}.db` — repo-level (each fixture-yielding repo counted once, not fixture-weighted), chi-square for `language`/`domain`, Mann-Whitney U for `repo_age_years`, both with effect sizes (Cramér's V / Cliff's delta) so statistical significance (which p-values alone conflate with sample size) can be told apart from practical magnitude. Run via `python -m collection.research_questions.balance`, output at `research_questions/balance.md`.
- **Current result (2026-07-31):** none of the three variables are balanced (p < 0.05) for either A-vs-B or A-vs-C, but the effect sizes matter here — A-vs-B's domain (V=0.09) and repo_age_years (δ=0.10) imbalances are statistically real but *negligible* in magnitude; A-vs-B's language imbalance (V=0.57) is large and is the one that matters, already addressed by RQ2/RQ3's per-language stratified comparisons. A-vs-C shows non-negligible imbalance on all three (language medium, domain and repo_age_years small) — A-vs-C comparisons deserve more caution than A-vs-B ones for this reason.
- **Limitation:** balance testing only checks for differences in the three measured distributions; unmeasured confounds (e.g., framework version changes, testing best practices evolution) may still exist.

