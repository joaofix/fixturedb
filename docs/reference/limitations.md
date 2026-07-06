# Limitations and Threats to Validity - FixtureDB Between-Group Study

## Between-Group Study Design

The between-group methodology collects human and agent corpora at different time periods to avoid temporal confounding. However, this design introduces its own limitations:

### Temporal Separation Confounding
- **Human corpus:** Pre-2021 repositories (fixture collection snapshot at 2020-12-31)
- **Agent corpus:** 2025+ repositories with agent commits (fixture collection snapshot at 2025-01-01)
- **Confound:** Changes in Python/JavaScript frameworks, testing best practices, and hardware between 2021 and 2025 may affect fixture patterns independently of agent involvement

**Mitigation:** Control variables (language, domain, star_tier, repo_age_years) are balanced across corpora using statistical tests (chi-square, Mann-Whitney U). Balance report generated after Stage 3 confirms no significant differences (p ≥ 0.05).

### Agent Detection Conservatism
- **Tier 1 detection only:** Agents identified via `co-authored-by` commit trailers only
- **False negatives:** Agents without proper trailers are classified as human
- **Impact:** True agent detection rate may be higher than reported

**Mitigation:** Use conservative Tier 1 estimates. Tier 2/3 (heuristic-based) detection documented in [Agent Detection Methodology](../architecture/agent-detection.md).

### Repository Availability
- **Human corpus:** Assumes pre-2021 repositories are still publicly available
- **Agent corpus:** Depends on GitHub API availability and rate limits
- **Impact:** Extinct or private repositories cannot be collected

**Mitigation:** Stage 1 uses corpus.db (pre-curated); Stage 2 queries live GitHub API with error handling.

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

Parametrized test functions are counted as **single test functions**, not multiplied by parameter set count. Impact:
- `reuse_count`: Fixture used by parametrized test with 10 parameter sets = reuse=1
- Test-to-fixture ratio may under-represent reuse in projects with heavy parametrization

To assess: Query `test_files` for parametrized patterns (regex: `parametrize|ParameterizedTest|test.each`), then adjust `reuse_count` estimates by observed parameter count.

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
for each) is `collection/config_data/fixture_definitions.yaml` — it is both
the executable pattern table the detector is built from and the audit trail
a reviewer can check against without reading `detector_python.py` /
`detector_java.py` / `detector_javascript.py` directly.

**Mitigation:** `raw_source` column in SQLite allows manual audit. Draw a manual-review sample with `collection/validation_sampling.py` (Cochran's formula, 95% confidence / 5% margin of error by default — see [Manual-Validation Sampling](../usage/validation-sampling.md)) rather than an arbitrary fixed count, to calculate project-specific recall.

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

40+ framework patterns detected (`unittest.mock`, `pytest-mock`, Mockito, Jest, Sinon, Vitest). Coverage excludes niche frameworks and non-standard APIs. Detects mocks within fixtures only, not test bodies. Treat `num_mocks=0` as reliable; use `num_mocks>0` as presence indicator, not exact count.

---

## Control Variable Balance

The between-group study balances control variables (language, domain, star_tier, repo_age_years) across human and agent corpora. Balance is verified using:

- **Chi-square test:** Categorical controls (p ≥ 0.05 indicates balance)
- **Mann-Whitney U test:** Continuous controls (p ≥ 0.05 indicates balance)

**Limitation:** Balance testing only checks for differences in distributions; unmeasured confounds (e.g., framework version changes, testing best practices evolution) may still exist.

**Mitigation:** Statistical tests reported in between_group_comparison_*.json. Inspect balance report before drawing conclusions.

