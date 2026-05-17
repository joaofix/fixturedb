# ICSME 2026 Data Showcase Track — Reviewer Critique

**Reviewer**: Academic Program Committee (simulated)  
**Date**: April 5, 2026  
**Track**: Data Showcase  
**Submission**: FixtureDB: A Multi-Language Dataset of Test Fixture Definitions from Open-Source Software

---

## Overall Assessment

**Contribution Strength**: STRONG — FixtureDB (v2, 4-language dataset) addresses a genuine gap in empirical software engineering research.

**Presentation Quality**: GOOD — Well-organized documentation with clear scope boundaries.

**Suitability for Track**: EXCELLENT — Meets core data showcase requirements (novel dataset, clear methodology, reproducible).

**Critical Issues**: 1 gap remaining (Go validation eliminated by v2 dataset exclusion).

---

## Criterion-by-Criterion Analysis

### 1. Fall Under ICSME 2026 Research Track Topics
**Status**: PASS

**Evidence**:
- Test automation and quality practices 
- Cross-language empirical studies 
- Software repository mining 
- Open-source software characterization 

**Notes**: 
- Clearly aligned with ICSME's focus on software maintenance, evolution, and testing practices
- Fixtures are understudied in the testing/SE literature despite their practical importance

---

### 2. Dataset NOT Previously Published as a Dataset Paper
**Status**: PASS

**Evidence**:
- Your README states this is the "first cross-language resource treating the fixture as its primary unit of analysis"
- Related work (TestHound, TestEvoHound) focused on **test cases**, not **fixtures** specifically
- Cross-language fixture datasets do not exist in published literature

**Minor caveat**:
- Your comparison to "Hamster" (arXiv:2509.26204) — confirm this hasn't been published as a data paper yet, or adjust positioning

---

### 3. Relevance to ICSME Community  
**Status**: PASS with MISSING DISCUSSION

**Your strength**: Fixtures are foundational to test maintenance and evolution. Understanding fixture patterns is relevant to:
- Developers maintaining large test suites
- Researchers studying test quality
- Tool builders automating fixture generation/refactoring
- Researchers understanding mock usage patterns (infrastructure, testing methodology)

**Gap**: Your paper currently **doesn't articulate research questions** that motivate the dataset. 

**RECOMMENDED ACTION**:
```
"FixtureDB enables research questions such as:
- How do fixture complexity and scope patterns vary across languages?
- What is the relationship between fixture size and mock framework adoption?
- How do fixture patterns correlate with repository maturity (star tier)?
- Do different testing frameworks impose different fixture structures?"
```

---

### 4. Motivation, Usage Scenarios, Target Users
**Status**: PARTIAL — Discussion is thin

**What you have**: Good intro explaining "what is a fixture" and "prior work is Java-only"

**What's missing**:
1. **Explicit target users**: Who will use this dataset and why?
   - Researchers studying testing practices?  Not mentioned
   - Practitioners interested in fixture metrics?  Not mentioned
   - Tool developers building refactoring tools?  Not mentioned

2. **Usage scenarios**: Specific use cases beyond abstract motivation
   - "Analyze how fixture complexity relates to test maintenance effort"
   - "Study mock adoption across languages and frameworks"
   - "Build ML models to predict fixture quality issues"
   - "Compare fixture patterns between early and mature projects"

3. **Practical impact**: Why should practitioners care?

**RECOMMENDED ACTION** — Add a "Typical Use Cases" section:
```markdown
## Typical Use Cases

### Academic Research
- Cross-language testing practice studies
- Empirical characterization of fixture complexity
- Mock framework adoption patterns
- Correlation between fixture metrics and code quality

### Industry Tools
- Linting/code review: flag overly complex fixtures
- Refactoring: suggest fixture scope or modularity improvements
- Testing frameworks: optimize fixture lifecycle management

### Education
- Understanding fixture patterns across testing frameworks
- Comparative framework analysis
- Test quality metrics
```

---

### 5. Originality & Relation to Existing Datasets
**Status**: PASS

**Originality**: 
-  First cross-language fixture-centric dataset
-  Cover 5+ languages (Python, Java, JS, TS, Go)
-  Includes structural metrics (complexity, scope, nesting)
-  Includes mock framework usage patterns

**Relation to existing work**:
You mention TestHound, TestEvoHound, Hamster, etc. but could be more explicit.

**RECOMMENDED TABLE**:
```markdown
| Dataset | Focus | Languages | Fixture-Centric | Mock Support | Scale |
|---------|-------|-----------|-----------------|--------------|-------|
| TestHound | Test quality | Java | No (test cases) | No | ~13K tests |
| Hamster | Code-test alignment | Python | No | Limited | 195 repos |
| FixtureDB | **Fixture structure** | 5 langs | **Yes** | **Yes** | **200 repos, 41K fixtures** |
```

---

### 6. Data Source & Collection Methodology
**Status**: EXCELLENT

**What you have**:
-  Clear GitHub sampling strategy (star-based + optional stratified)
-  Five-phase pipeline documented in detail (Search → Clone → Extract → Classify → Export)
-  Quality filters (≥50 commits, ≥5 test files)
-  Tree-sitter AST parsing with community-vetted grammars
-  Framework detection with syntax-based signals (decorators, annotations)
-  Provenance tracked (pinned commits, collection timestamps)
-  Tools documented (Tree-sitter, Lizard, cognitive-complexity library)

**Minimal gaps**:
1. **Collection date**: When was the corpus collected? (Add to README)
2. **API rate limiting**: How was GitHub API rate-limiting handled? (Minor detail, but good for reproducibility)
3. **False positive/negative rates**: 
   - Go helper heuristic: You note "TODO: insert false-positive rate from manual validation once completed"
   - This TODO must be resolved before publication
   - Provide manual validation results on ≥50 fixtures per language (see Issue #12)

**ACTION REQUIRED**:
- [ ] Complete Go helper manual validation (from CODEBASE_REVIEW Issue #12)
- [ ] Report inter-rater reliability if multiple validators
- [ ] Add collection timestamp to repository metadata

---

### 7. Data Format, Storage, Schema
**Status**: EXCELLENT

**What you have**:
-  Two-tier distribution: SQLite + CSV exports
-  Detailed schema documentation (ERD, table descriptions)
-  CSV export strategy clearly articulated:
  - Quantitative metrics only (LOC, complexity, scope, type, mock counts)
  - Excludes qualitative classifications (category, mock_style, target_layer)
-  Language-specific CSVs for accessibility
-  Foreign keys enforced for data integrity
-  WAL mode for safe concurrent read/write
-  Access documented with SQL query examples
-  **Comprehensive CSV user guide** ([docs/15-csv-user-guide.md](docs/15-csv-user-guide.md)) with:
  - Column-by-column reference for all tables
  - Complexity metrics explained
  - Import examples (Excel, pandas, R)
  - Common analysis patterns
  - Missing value policy

**Status Update**: CSV schema documentation is now complete and exceeds expectations.

---

###  8. Large-Scale Empirical Validation & Use Cases
**Status**: WEAK — This is your primary weakness

**What you have**:
- References to "prior studies that have used it" — but this is a NEW dataset
- Basic EDA plots (quantitative corpus composition)
- Some examples in documentation

**What's missing**:
The ICSME guidelines state: "NOT necessarily include large-scale empirical validation, BUT provide examples of **use cases, analyses, or research questions** the dataset enables"

**You currently show**:
- Histogram: fixture count by language
- Distribution: star tier composition
- Basics: LOC ranges, complexity ranges

**You should add**:
1. **Example RQ-driven analyses**: 
   ```
   RQ1: How does fixture complexity vary by scope (per_test vs per_class vs per_module)?
   → Show a table with mean/median complexity by scope × language
   
   RQ2: What fraction of fixtures use mocking? Does this vary by language?
   → Show percentages and distributions
   
   RQ3: Is fixture complexity correlated with repository maturity?
   → Show scatter plot: repository stars vs fixture complexity (aggregate)
   ```

2. **SQL query templates** researchers can adapt:
   ```sql
   -- Find complex fixtures that might benefit from refactoring
   SELECT language, COUNT(*) as count
   FROM fixtures
   WHERE cyclomatic_complexity >= 10
   GROUP BY language;
   
   -- Analyze mock adoption by framework
   SELECT language, framework, COUNT(*) as count
   FROM mock_usages
   GROUP BY language, framework;
   ```

3. **Research directions enabled**:
   - "The dataset enables studying fixture modularity (reuse_count metric)"
   - "Researchers can analyze fixture scope patterns and their relationship to test isolation"
   - "Mock framework adoption can be studied cross-linguistically for the first time"

**CRITICAL ACTION REQUIRED**:
- [ ] Add 3–5 example research questions with minimum analysis (table or plot)
- [ ] Add 5–10 SQL query templates
- [ ] Add a "Future Research Directions" section

---

### 9. Limitations, Challenges, Ethical Considerations
**Status**: GOOD — Well-articulated

**What you have**:
-  Sampling bias (stars-based over-represents web frameworks)
-  Go heuristic precision gap (TODO on validation)
-  Snapshot nature (no longitudinal data)
-  Language coverage gaps (Ruby, Kotlin, Rust, etc.)
-  Mock detection completeness issues (regex-based, version-dependent)
-  Suggestions for analysis mitigation (stratify by star_tier, include raw_source in DB)

**What's missing**:
1. **Ethical considerations**: 
   - Data sourced from public GitHub repos ( no private data)
   - License compliance: "The dataset is available under CC BY 4.0" — confirm this is appropriate for derived work under various open-source licenses (MIT, Apache, GPL, etc.)
   - Recommendation: Add note clarifying that researchers using the dataset should respect original repository licenses

2. **Reproducibility threats**:
   - GitHub API changes → could affect replication of search phase
   - Tree-sitter grammar updates → could affect fixture detection
   - Repository deletion → affects data availability
   - Recommendation: Suggest Zenodo archival of both code + frozen dataset

3. **Potential improvements**:
   You list Go, Ruby, Kotlin as future coverage. Good. Also mention:
   - Parametrized fixtures (advanced pytest feature not yet detected)
   - Fixture dependencies beyond simple parameter injection
   - Async/coroutine fixtures (modern testing feature)

---

### 10. Literature Review
**Status**: PARTIAL — Good but incomplete

**What you cite**:
- TestHound, TestEvoHound (fixture-adjacent, Java-centric prior work)
- Hamster (code-test alignment)
- Mostafa & Wang, Spadini et al., Chaker et al. (mocking studies)
- Standard testing frameworks (pytest, JUnit, Jest, Vitest, Testify)

**What's missing**:
1. **Test fixture foundations** — cite classic testing literature:
   - Martin Fowler's "Arrange-Act-Assert" pattern
   - xUnit architecture
   - Paul Duvall's continuous integration work (touches fixture lifecycle)

2. **Static complexity metrics** — you use cyclomatic and cognitive complexity:
   - McCabe (1976)
   - Shao/Wang cognitive complexity formulation
   - SonarQube standards

3. **Mock-related empirical work**:
   - Polman & Jiang on mocking effectiveness
   - Spadini et al. on test code quality

4. **Cross-language empirical studies**:
   - Prior multi-language datasets (e.g., Amann et al.'s ManySStuBs4J)
   - Comparative observations on testing practices across linguages

**ACTION REQUIRED**:
- [ ] Add 10-15 citations to testing foundations, complexity metrics, and cross-language studies
- [ ] Organize literature via: (1) fixture & test infrastructure, (2) empirical testing studies, (3) mocking practices, (4) cross-language comparisons

---

## Presentation Quality Assessment

### Organization: EXCELLENT
- Clear README with quick-start instructions
- Comprehensive docs/ folder with 16 linked documents
- Logical progression: intro → architecture → usage → limitations
- Schema ERD diagram would strengthen this (consider adding to docs/03-database-schema.md)

### Clarity: GOOD
- Quantitative vs qualitative scope is now clearly delineated
- CSV export strategy is explicit
- Terminology is consistent and defined

### Reproducibility: EXCELLENT
- Pinned commits for exact corpus replication
- Complete extraction pipeline with configurable parameters
- Raw source in SQLite for verification
- Docker/environment setup documented

### Accessibility:  PARTIAL
- Documentation is thorough but dense
- No visual ERD (just text tables)
- No example analyses for non-Python researchers

---

## Summary of Critical Issues

###  High Priority (Must fix before publication)

**ISSUE 1**: Go helper false-positive validation incomplete
- **Status**: Documented as "TODO" in [docs/12-limitations.md](docs/12-limitations.md)
- **Fix**: Complete manual validation on ≥50 Go helper fixtures, report precision/recall
- **Deadline**: Before Zenodo deposit

**ISSUE 2**: Missing example use cases & research questions
- **Status**: Documentation lacks 3–5 concrete analyses enabling the dataset
- **Fix**: Add example RQ-driven analyses (3–5 tables/plots) + 10 SQL templates
- **Deadline**: Before submission

**ISSUE 3**: Incomplete literature review
- **Status**: Missing foundational testing/complexity/cross-language citations
- **Fix**: Add 10–15 citations to testing fundamentals, complexity metrics, empirical studies
- **Deadline**: Before submission

---

###  Medium Priority (Should address)

**ISSUE 4**: Target users and concrete scenarios not explicit
- **Status**: Motivation discusses problem but not audiences
- **Fix**: Add "Target Users" and "Typical Use Cases" sections
- **Timeline**: Before submission

**ISSUE 5**: Collection timestamp and ethical permissions
- **Status**: When was corpus collected? License compliance considerations?
- **Fix**: Add collection date to metadata; clarify CC BY 4.0 + derived work licensing
- **Timeline**: Before Zenodo deposit

**ISSUE 6**: CSV schema documentation for non-database researchers (COMPLETE)
- **Status**: Resolved with comprehensive [docs/15-csv-user-guide.md](docs/15-csv-user-guide.md)
- **Deliverable**: 
  - Column-by-column reference for fixtures.csv, mock_usages.csv, repositories.csv, test_files.csv
  - Complexity metrics explained (McCabe, cognitive, nesting depth)
  - Import examples for Excel, pandas, R
  - Common query patterns
  - Missing value policy
- **Timeline**: Complete

---

###  Low Priority (Nice to have)

**ISSUE 7**: Add visual ERD diagram
- **Fix**: Including visual schema diagram in docs/03-database-schema.md
- **Timeline**: Optional; low impact if omitted

**ISSUE 8**: Expand reproducibility discussion
- **Fix**: Document GitHub API stability, Tree-sitter versioning, Zenodo archival strategy
- **Timeline**: Optional for initial publication

---

## Final Reviewer Recommendation

### Verdict: **ACCEPT — with Author Revisions**

**Strengths**:
- Genuine novelty (first cross-language fixture-centric dataset)
- Excellent methodology and reproducibility
- Clear scope and comprehensive documentation
- Well-organized codebase and schema
- Comprehensive CSV user guide for accessibility

**Remaining Weaknesses**:
- Go validation incomplete (blocking issue)
- Missing concrete use cases and analyses
- Literature review needs expansion
- Target users not explicitly defined

**Path Forward**:
1. **Complete Go helper validation** (manual review of ≥50 fixtures)
2. **Add 3–5 example RQ-driven analyses** with tables/plots
3. **Expand literature review** with foundational citations
4. **Clarify target users** and concrete scenarios
5. **Resolve Zenodo deposit** metadata and licensing

**Expected Impact**: Once remaining issues are addressed, this dataset will be a valuable resource for the ICSME community and a strong data showcase contribution.

---

## Appendix: Specific Recommendations for Paper Structure

If you write a formal data showcase paper (beyond this replication package), organize it as:

```
1. INTRODUCTION (½ page)
   - Problem: Fixtures are understudied, prior work is Java-only
   - Contribution: First cross-language fixture dataset
   
2. MOTIVATION & SCOPE (½ page)
   - Why fixtures matter for testing
   - Target users (researchers, practitioners, tool builders)
   - Typical use cases (3–5 concrete examples)
   
3. DATASET DESIGN (1 page)
   - Collection methodology (5-phase pipeline)
   - Sampling strategy & quality filters
   - Framework detection approach
   - Metric definitions
   
4. DATASET CHARACTERISTICS (1 page)
   - Corpus composition table (languages, repos, fixtures, mocks)
   - Star tier distribution
   - Example statistics (complexity ranges, mock adoption rates)
   
5. EXAMPLE ANALYSES (1–2 pages)
   - 3–5 RQ-driven minimal analyses (tables/plots)
   - SQL query templates for researchers
   - Data accessibility & format
   
6. LIMITATIONS & FUTURE WORK (½ page)
   - Known limitations (sampling bias, Go heuristic, coverage gaps)
   - Suggestions for mitigation
   - Planned improvements (more languages, longitudinal tracking)
   
7. CONCLUSION (¼ page)
   - Encouragement for community use
   - Zenodo/GitHub access information

TOTAL: 5–6 pages (typical for data showcase)
```

---

## Conclusion

FixtureDB is a well-executed contribution filling a genuine research gap. With revisions addressing the three critical issues (Go validation, use cases, literature review), this dataset will serve the ICSME community for years to come.

**Recommended next steps**:
1. Schedule Go helper validation (can be parallelized)
2. Draft 3–5 example RQ-driven analyses
3. Expand related work section by 20–30%
4. Prepare Zenodo submission package
5. Plan companion paper (if pursuing full research publication beyond data showcase)
