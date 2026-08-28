# Limitations and Threats to Validity - FixtureDB Between-Group Study

## Between-Group Study Design

The between-group methodology collects human and agent corpora at different time periods to avoid temporal confounding. However, this design introduces its own limitations:

### Temporal Separation Confounding
- **Problem:** The human corpus is drawn from pre-2021 repositories (fixture collection snapshot at 2020-12-31), while the agent corpus is drawn from 2025+ repositories with agent commits (snapshot at 2025-01-01). Changes in Python/JavaScript frameworks, testing best practices, and hardware between 2021 and 2025 may affect fixture patterns independently of agent involvement.
- **Mitigation:** Control variables (language, domain, repo_age_years) are balanced across corpora using statistical tests (chi-square, Mann-Whitney U) — see `collection/between_group_comparison.py` and [Analyzing the Datasets § Comparing two datasets](../usage/usage.md#comparing-two-datasets). The balance report confirms no significant differences (p ≥ 0.05).

### Agent Detection Conservatism
- **Problem:** Agents are identified via Tier 1 detection only — `co-authored-by` commit trailers and author identity. Agents without proper trailers are classified as human, so the true agent detection rate may be higher than reported.
- **Mitigation:** Use conservative Tier 1 estimates. See [Agent Detection Methodology](../architecture/agent-detection.md) for the full detection method.

### Differential False-Negative Risk: Dataset B vs. Dataset C
- **Dataset B** draws its repo pool from the *same* agent-adopting repositories as Dataset A (every B repo is a subset of A's agent-config-having pool). This is a real strength for controlling repo-level confounds (domain, maturity) — but it also means B's "human"-labeled commits sit in repos where agent use is actively encouraged, so an untrailed, informally-agent-assisted commit (see "Agent Detection Conservatism" above) is more likely to occur in B than it would in a naive agent-free control.
- **Dataset C** draws from a different, non-agent-config repo pool and does not share this specific elevated risk to the same degree.
- **Impact:** B and C are not interchangeable "human" baselines with respect to this risk. The A-vs-B ("within-repo") and A-vs-C ("cross-repo") comparisons carry different residual confidence even though both nominally compare agent commits against a "human" corpus.

**Mitigation:** None currently measured or applied — this is a structural property of each dataset's repo-selection strategy, not a detection bug to fix. Treat A-vs-B and A-vs-C findings as testing related but distinct questions rather than pooling them into one undifferentiated "agent vs. human" conclusion.

### Repository Availability
- **Problem:** The human corpus assumes pre-2021 repositories are still publicly available; the agent corpus depends on GitHub API availability and rate limits. Extinct or private repositories can't be collected.
- **Mitigation:** `discover-repos` and `discover-commits` query the live GitHub API with error handling.

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

**Known gaps:** Parametrized test detection edge cases. `num_objects_instantiated` was regex-based and matched text wherever it appeared (inside a string literal/comment, or a fixture's own capitalized name self-matching its signature line) until 2026-08-16, when it was rewritten to walk real tree-sitter AST node types instead (`object_creation_expression`/`new_expression` for Java/JS/TS, a capitalized-target `call` node for Python) -- see [internal-docs/methodology-improvements/num-objects-instantiated-false-positive-rate.md](../../internal-docs/methodology-improvements/num-objects-instantiated-false-positive-rate.md) for the investigation and fix. Java/JS/TS are now exact by construction (a string/comment's contents are never parsed as nested code); Python retains a residual, much narrower heuristic-naming ambiguity (a capitalized call that isn't actually a constructor), found in 0 of a 46-match manual sample.

---

## Mock Detection

27 regex patterns across 9 mock frameworks detected (`unittest.mock`, `pytest-mock`, pytest's built-in `monkeypatch`, Mockito, EasyMock, MockK, Jest, Sinon, Vitest — see the full, exact list in [collection/heuristics/feature_extraction_patterns.yaml](../../collection/heuristics/feature_extraction_patterns.yaml)'s `mock_patterns`). Coverage excludes niche frameworks (e.g. PowerMock) and non-standard APIs; the exact documented exclusions are in that same file's `mock_patterns_excluded`. Detects mocks within the fixture's own body only — not test bodies, and not module-level setup outside any fixture (e.g. Jest's conventional top-level `jest.mock('./module')` is invisible to this detector even though the pattern exists, since it's structurally outside any fixture's AST node). Treat `num_mocks=0` as reliable only within that scope; use `num_mocks>0` as a presence indicator, not an exact count.

Each fixture is also classified into the classic test-double taxonomy (Meszaros) — `dummy`/`stub`/`spy`/`mock`/`fake` — as `mock_usages.category`. Classification scans the fixture's own full body text, case-insensitively, for one of the five category terms in priority order (dummy > stub > spy > fake > mock), falling back to `mock` when none is found — an identifier-keyword method, not a lookup keyed on which framework matched. One category is computed per fixture and applied to every mock recorded in it, so a fixture that legitimately creates two differently-named mocks (e.g. both a `dummy_x` and a `real_service_mock`) gets the same category for both, since classification isn't re-run per individual mock call. Treat `category` as a per-fixture classification, not a claim about how each individual mock instance was specifically used.

---

## Control Variable Balance

- **Problem:** RQ1-3's comparisons are only informative about authorship/era if the underlying repo samples are otherwise comparable — if domain or repo age differ systematically between two datasets, a metric difference could reflect that instead of what's being attributed to it. This was described as verified (`between_group_comparison_*.json`, generated by `BetweenGroupComparator`) but never actually was: that class reads from a `between-group.db` that has never existed in this repo, and isn't wired into `collection/__main__.py`'s CLI anywhere — leftover from an earlier architecture, before the current Dataset A/B/C split. No such JSON file has ever existed.
- **Mitigation:** `collection/research_questions/balance.py` (added 2026-07-31) checks this for real, against the current `db/{a,b,c}.db` — repo-level (each fixture-yielding repo counted once, not fixture-weighted), chi-square for `language`/`domain`, Mann-Whitney U for `repo_age_years`, both with effect sizes (Cramér's V / Cliff's delta) so statistical significance (which p-values alone conflate with sample size) can be told apart from practical magnitude. Run via `python -m collection.research_questions.balance`, output at `research_questions/balance.md`.
- **Current result (2026-07-31):** none of the three variables are balanced (p < 0.05) for either A-vs-B or A-vs-C, but the effect sizes matter here — A-vs-B's domain (V=0.09) and repo_age_years (δ=0.10) imbalances are statistically real but *negligible* in magnitude; A-vs-B's language imbalance (V=0.57) is large and is the one that matters, already addressed by RQ2/RQ3's per-language stratified comparisons. A-vs-C shows non-negligible imbalance on all three (language medium, domain and repo_age_years small) — A-vs-C comparisons deserve more caution than A-vs-B ones for this reason.
- **Limitation:** balance testing only checks for differences in the three measured distributions; unmeasured confounds (e.g., framework version changes, testing best practices evolution) may still exist.

---

## Categorical Pseudo-Replication

- **Problem:** RQ1's `fixture_type` distribution, RQ2's `fixture_type_kind` (setup/teardown/other), and RQ3's `has_mock` prevalence, `framework` distribution, and test-double `category` distribution were each tested with a plain chi-square over fixture/mock-level counts (`compute_categorical_balance()`, [between_group_comparison.py](../../collection/between_group_comparison.py)). That treats every fixture/mock as an independent observation, but fixtures/mocks are nested in files nested in repos — a repo contributing hundreds of correlated rows (one framework choice, one team convention) is effectively one independent observation, not hundreds. Flagged in a 2026-08-11 methodology review: this inflates the chi-square statistic and, to a lesser degree, corrupts Cramér's V (which normalizes by n, and n is inflated by the same clustering) — three of the four headline RQ1/RQ3 effects were affected.
- **Mitigation:** each of the 5 metrics above is now also tested with per-repo category proportions compared via Mann-Whitney U + Cliff's δ (`compare_categorical_repo_level()`, [_shared.py](../../collection/research_questions/_shared.py)) — the same de-clustering fix RQ1/RQ2's continuous metrics (LOC/CC/nesting/parameters, setup-to-teardown ratio) already used, extended to categorical variables: instead of one raw count per fixture, one proportion per repo, so each repo counts once regardless of how many fixtures/mocks it contributed. Rendered in each RQ script's "Repo-level aggregates" section, alongside (not replacing) the original fixture-level chi-square table.
- **What the paper reports:** for `fixture_type`, the repo-level proportion test is what's cited in the paper — the pooled fixture-level chi-square table is kept in the generated `research_questions/rq1.md` report for transparency/comparison only and is explicitly marked "not used in the paper" (with a pointer to the repo-level result) at the point it's rendered. `has_mock`'s repo-level test was reported the same way through 2026-08-22, then superseded by RQ3's new mocking-coverage table — see the RQ3-simplification bullet below; its pooled fixture-level chi-square is kept but moved to a "Legacy" section in `research_questions/rq3.md`, same "not used in the paper" framing. For RQ3's `framework`/`category`, see the language-composition-confound bullet below — neither has a pooled result at all anymore, and (2026-08-22) neither has ANY rendered table anymore, pooled or repo-level. RQ2's `fixture_type_kind` also has no pooled result anymore — see the RQ2-simplification bullets below (2026-08-14, then superseded 2026-08-22), which removed it (and the setup-to-teardown ratio and no-teardown-repo rate metrics entirely) in favor of two tables: a purely descriptive fixture-count table and a repo-level teardown-coverage test. Every other categorical result in these reports (RQ1's `scope`/`commit_type` and all the per-language stratified tables) is unaffected by this and is used as-is.
- **Scope:** only the 5 metrics above were converted. RQ1's `scope`/`commit_type` pooled tests, and every per-language *stratified* categorical test (`compute_stratified_categorical_balance()`), have the identical clustering flaw but are still fixture-level, left as a known limitation of those specific tables rather than converted, since per-language repo counts are already small and repo-declustering them further would hit "insufficient data" often. RQ2's `repo_zero_teardown_rate` and `balance.py`'s language/domain checks needed no fix — both already count each repo once by construction.
- **Per-language reporting (2026-08-11, same-day follow-up):** every A-vs-C comparison in rq1.py/rq2.py/rq3.py now reports an exact p-value (raw and BH-FDR-adjusted, never just "significant/not significant") and `n_A`/`n_C` -- always a repo count, even for these still-fixture-level chi-square tests, specifically so a reader can see how many repos actually back a given cell. Per-language stratified tests were added for every metric named in this doc's "Problem" bullet above, plus RQ1's `scope`, RQ2's setup-to-teardown ratio and no-teardown-repo rate -- each its own BH-FDR correction family (exactly that metric's 4 per-language tests, never mixed with another metric's or with the pooled "Overall" row, which is a single uncorrected test). RQ3's `framework`/`category` briefly got this treatment too, then had it removed the next day -- see the next bullet.
- **Language-composition confound, RQ3 `framework`/`category` (2026-08-12, further superseded 2026-08-22 -- see below):** Dataset A is TypeScript-heavy, Dataset C skews Python/JavaScript. `mock_usages.framework` names are language-specific *by construction* (`unittest.mock` only exists for Python, Sinon only for JS, Mockito only for Java) and test-double `category` naming conventions vary systematically by ecosystem too (Sinon's explicit `.spy()`/`.stub()` API vs Python's monolithic `Mock`/`MagicMock`). That means *any* pooled-across-languages number for either variable -- the fixture-level chi-square Overall row, its per-language-stratified sibling rows (each still fine on its own, but sitting next to a table whose headline row wasn't), and even the repo-level-proportion Mann-Whitney fix described above (which pools every repo's proportion regardless of language) -- reflects each dataset's language mix, not an authorship-era effect. Fix at the time: `framework`'s entire chi-square table and its repo-level-proportion test were removed outright, replaced with a purely descriptive per-language top-3-frameworks table (no test, no effect size). `category`'s chi-square table was similarly removed; its repo-level-proportion test was kept but restructured to run once per language instead of pooled, so each language's own 5-category family (dummy/fake/mock/spy/stub) was its own BH-FDR family. `has_mock` was untouched at the time -- a binary yes/no isn't a language-specific construct the way a framework *name* or a category *naming convention* is, so pooling it across languages doesn't have the same confound. **As of 2026-08-22, `framework`'s descriptive table and `category`'s per-language test are both gone from the report entirely** (not just their pooled versions) -- see the next bullet; the raw data (`framework_dist`/`category_dist`/etc.) is still fetched and available on `DatasetMetrics`, just no longer rendered.
- **RQ2 simplified to one repo-level table (2026-08-14, superseded 2026-08-22 -- see the next bullet):** the paper settled on a single RQ2 table -- median per-repo `setup_pct`/`teardown_pct` (from the `fixture_type_kind` classification above) per language and Overall, plus one repo-level effect size + BH-FDR p-value per language, reusing `compare_categorical_repo_level()` exactly as described above. This is a further simplification than the rest of this section describes, not just an extension: RQ2's `fixture_type_kind` no longer has a pooled fixture-level chi-square table at all (the repo-level version *replaces* it, rather than sitting alongside it as "also tested this way" like RQ1's `fixture_type`/RQ3's `has_mock` still do), and the setup-to-teardown ratio and no-teardown-repo rate metrics (both described in the "Per-language reporting" bullet above) were dropped from the paper's reported output entirely, not just de-pooled. The table's one effect-size/p-value column pair per row is the `setup` category's own repo-level test standing in for the whole `setup`/`teardown`/`other` distribution (they're not independent -- all three sum to 100% per repo) -- labeled "V" for consistency with the paper's other effect-size columns, but the number is Cliff's delta from that Mann-Whitney test, not literally Cramér's V; see `rq2.py`'s module docstring for the full reasoning.
- **RQ2 split into two tables (2026-08-22):** the single median-proportion table above was itself replaced by two narrower tables. Table 1 (fixture counts) is purely descriptive -- raw setup-classified/teardown-classified fixture counts per language, no statistical test at all, "other" excluded. Table 2 (teardown coverage) is the inferential table: per repo, a binary indicator (does it have >=1 teardown-classified fixture, yes/no), compared between datasets via Mann-Whitney U + Cliff's δ on that 0/1 indicator (`compute_continuous_balance()` directly, not `compare_categorical_repo_level()` -- there's only one category being tested, not a set of mutually exclusive ones) -- the mean of the 0/1 values doubles as "% of repos with >=1 teardown fixture" for the table's Coverage A/C (%) columns. Same repo-declustering principle as every other fix in this section (one observation per repo, not per fixture), same BH-FDR-per-language-family convention. Motivation for the further split: a continuous per-repo proportion and a binary "has any at all" coverage rate answer different questions, and the paper wanted both surfaced separately rather than compressed into one proportion-medians table. The dip test (Python `teardown_pct` unimodality) and the `setup_pct`/`teardown_pct`-proportion computation it depends on are both still computed by `rq2.py`, just moved to a clearly separate "Supplementary Analyses" section, not part of either main table -- kept since they may still be cited in prose. See `rq2.py`'s module docstring for the full reasoning.
- **RQ3 collapsed to one mocking coverage + intensity table (2026-08-22):** the three previously-reported RQ3 tables (fixture-level `has_mock` chi-square, `framework` descriptive table, `category` per-language repo-level test) were replaced by one table with two repo-level metrics, both A vs C via `compute_continuous_balance()` directly on a per-repo value (same "binary indicator's mean is the percentage" trick as RQ2's teardown-coverage table): **Coverage** (does a repo have >=1 fixture with a mock at all?) and **Intensity** (among repos where Coverage=1 only, the median mock-call count across that repo's own mocking fixtures -- non-mocking repos are excluded from Intensity entirely, not counted as 0, so its true population is a strict subset of Coverage's; the table's one `n_A`/`n_C` per row is Coverage's population size, stated explicitly in the table's own intro text). Coverage directly supersedes what used to be `has_mock`'s repo-level test (same statistic -- a two-category proportion test on a binary variable is mathematically the mean-of-the-0/1-indicator test this table uses, just computed via `compute_continuous_balance()` now instead of `compare_categorical_repo_level()`). **Both metrics' per-language tests are BH-FDR corrected together as one combined 8-test family (4 languages × 2 metrics), not two separate 4-test families** -- an explicit, deliberate departure from every other per-language family in this section (which are always one metric's own 4 languages), since both metrics are reported in the same table. `framework`/`category` lost their tables entirely (not just their pooled versions, see the bullet above) -- their raw data is still on `DatasetMetrics` but no longer rendered. `has_mock`'s fixture-level chi-square (pooled + per-language, already "not used in the paper" before this change) is kept, moved to a "Legacy" section for transparency only. `num_mocks`/`num_interactions_configured`'s existing continuous Mann-Whitney tables are unaffected. See `rq3.py`'s module docstring for the full reasoning.

