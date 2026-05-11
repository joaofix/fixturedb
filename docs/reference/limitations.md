# Limitations and Threats to Validity

## Sampling bias

The corpus is drawn from repositories with ≥500 GitHub stars. Popular,
actively maintained projects may exhibit higher test discipline than typical
open-source software. This is a known limitation in empirical software
engineering studies (Hamster study by Pan et al., 2025) which also used
star-based sampling to ensure sufficient test coverage. To mitigate this bias
and improve generalizability, we collected all available open-source repositories
with ≥500 stars across 4 programming languages.

## Language coverage

FixtureDB covers four languages: Python, Java, JavaScript, and TypeScript.
Other languages such as Ruby (RSpec), Kotlin, Scala, Rust, C#, and Go are not included.

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

**Mitigation:** `raw_source` column in SQLite allows manual audit. Sample 100–200 test files per language to calculate project-specific recall.

---

## Advanced Metrics Limitations

| Metric | Limitation | Mitigation |
|--------|-----------|-----------|
| `has_teardown_pair` | Heuristic detection; implicit cleanup (connection pooling, auto-cleanup) not detected. Ambiguous in JavaScript/TypeScript. | Use `raw_source` for manual verification on important fixtures. |
| `num_contributors` | GitHub API page limit (~30 per page); repos with >100 contributors may be under-counted. | For precise counts, query GitHub API or web interface directly. |
| `max_nesting_depth` | May over-estimate when counting lambda/closure nesting vs. control flow nesting. | Use `cyclomatic_complexity` for cross-validation of structural complexity. |

---

## Validation Status

**Status:** Heuristic-based detection. No inter-rater reliability metrics (Cohen's kappa) available. For critical research, manually inspect 50–100 fixtures per language to establish project-specific precision and recall.

**Language-Specific Confidence:**

| Language | Status | Notes |
|----------|--------|-------|
| Python | High | Decorator-based detection is unambiguous. |
| Java | High | Annotation-based detection is unambiguous. |
| JavaScript | Medium | Framework conventions vary; helper detection relies on naming. |
| TypeScript | Medium | Same as JavaScript. |
| Go | **Incomplete** | Helper function detection validated but classification incomplete. |

**Known gaps:** Parametrized test detection edge cases, false-positive rates (~5–15% for `num_objects_instantiated`).

---

## Mock Detection

40+ framework patterns detected (`unittest.mock`, `pytest-mock`, Mockito, Jest, Sinon, Vitest). Coverage excludes niche frameworks and non-standard APIs. Detects mocks within fixtures only, not test bodies. Treat `num_mocks=0` as reliable; use `num_mocks>0` as presence indicator, not exact count.
