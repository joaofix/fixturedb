# Methodological Baseline Evaluation
## Your Collection Module vs. "Are Coding Agents Generating Over-Mocked Tests?" (Hora & Robbes, MSR '26)

**Evaluation Date:** May 25, 2026  
**Purpose:** Assess academic rigor alignment for conference submission  
**Scope:** Collection module design against MSR '26 baseline

---

## Executive Summary

Your collection module is **well-structured for a rigorous empirical study** but focuses on **different research objectives** than the baseline paper. The baseline investigates **mock prevalence in agent-generated tests**, while your module collects **fixture-level data for agent vs. human comparison**. The key evaluation points:

- ✅ **Strong alignment:** Agent detection methodology, repository selection, statistical framework
- ⚠️ **Moderate gaps:** Mock identification, test double classification, within-repo analysis rigor
- ❌ **Critical gaps:** Threats to validity documentation, effect size reporting, configuration file analysis

**Overall Assessment:** Your module is **academically sound but incomplete** for the specific research questions around mock usage that would make it comparable to the baseline paper at a top-tier venue.

---

## Section 1: Shared Strengths ✅

### 1.1 Agent Detection Methodology - **STRONG ALIGNMENT**

**Baseline Approach:**
- Co-authored-by commit trailers (case-insensitive)
- Pattern matching on author/email for claude, cursor, copilot, aider, etc.
- Manual validation: 500 commits, 100% precision
- Multiple agent types supported (10+ agents)
- Repository-level filtering via agent configuration files (CLAUDE.md, CURSOR.md, copilot-instructions.md)

**Your Implementation:**
```python
# agent_corpus.py - detect_agent_type()
- Matches AGENT_SIGNATURES for claude, copilot, cursor, aider
- COAUTHOR_TRAILER_RE pattern for co-authored-by trailers
- PAPER_AGENT_CONFIG_PATTERNS for repository filtering
```
✅ **Identical approach** - Case-insensitive matching, multiple agent types, co-author trailers

**Academic Rigor Score:** 9/10  
**Notes:** Your implementation directly mirrors the baseline. Missing explicit precision validation (500 manual commits) but pattern source aligns.

---

### 1.2 Repository Selection - **STRONG ALIGNMENT**

**Baseline Criteria:**
- 2,168 repositories across Python, TypeScript, JavaScript
- Filtered for agent configuration files initially (CLAUDE.md, CURSOR.md, copilot-instructions.md)
- Then filtered for actual agent commits (1,219 repos)
- Data from 2025 only
- Includes SEART-quality filtering (100+ commits, 500+ stars)

**Your Implementation:**
```python
# paired_collection.py
- Language configs for Python, TypeScript, JavaScript ✅
- select_paired_repositories() with SEART-filtered repos
- repos_per_language parameter
- Status filter: 'analysed' or 'cloned' ✅
```

✅ **Strong alignment on language/scope** - Same three languages, similar filtering

**Gaps:**
- Your module doesn't explicitly document repository quality criteria (100 commits, 500 stars)
- No explicit filtering on agent configuration files mentioned in code

**Academic Rigor Score:** 7/10

---

### 1.3 Statistical Rigor - **MODERATE ALIGNMENT**

**Baseline Statistical Tests:**
- Chi-squared test of independence (RQ1, RQ2 commit-level)
- Paired Wilcoxon test (RQ2 repository-level within-repo comparison)
- Cliff's delta for effect size
- Contingency tables with standardized residuals

**Your Implementation:**
```python
# paired_collection.py - _compute_chi_square_balance()
- Chi-square contingency test ✅
- p_value and status computation ✅
- Stores in balance_tests dict
```

✅ **Chi-square implemented** - Shows awareness of statistical requirements

**Gaps:**
- No Wilcoxon test implementation (required for paired repository-level analysis)
- No effect size computation (Cliff's delta)
- No contingency table visualization
- No standardized residuals reporting
- No multiple comparison correction (Bonferroni)

**Academic Rigor Score:** 5/10

---

## Section 2: Critical Methodological Gaps

### 2.1 Mock Identification - **SIGNIFICANT GAP** ❌

**Baseline Methodology:**
- Identifies "mock commits" = commits that add/modify mocks in test files
- Mock patterns searched:
  - Python: `mock`, `Mock()`, `patch()`, `MagicMock()`, `monkeypatch`, `pytest-mock`
  - TypeScript/JavaScript: `spy()`, `jest.mock()`, `sinon.stub()`, `jasmine.spyOn()`
  - Test double types classified: dummy, stub, spy, mock, fake
- Example detection shown with code diffs
- Precision/recall not explicitly reported but methodology is grounded in established frameworks (xUnit patterns)

**Your Implementation:**
```python
# detector.py (inferred from fixture_extractor.py)
- Extracts "fixtures" from test files
- No explicit mock identifier in code review
- Searches for fixture patterns but unclear if these include mock classifications
```

❌ **CRITICAL GAP:** Your module does NOT implement mock identification. It extracts fixtures but doesn't classify mock usage.

**What's Missing:**
```python
# You need to add something like:
MOCK_PATTERNS = {
    'python': [
        r'\bmock\b', r'Mock\(\)', r'patch\(', r'MagicMock\(',
        r'monkeypatch', r'pytest.mock', r'unittest.mock'
    ],
    'javascript': [
        r'jest\.mock\(', r'sinon\.stub\(', r'spy\(', r'jasmine\.spyOn\('
    ],
    'typescript': [
        r'jest\.mock\(', r'sinon\.stub\(', r'spy\(', r'jasmine\.spyOn\('
    ]
}

# Mock types classification (per Meszaros 2007)
MOCK_TYPES = ['dummy', 'stub', 'spy', 'mock', 'fake']
```

**Academic Impact:** Without mock detection, your findings cannot address the key question: "Are agents generating more mocks?" This is essential for conference-grade rigor.

**Academic Rigor Score:** 1/10 (if mock analysis is a research question)

---

### 2.2 Test Commit Detection - **MODERATE ALIGNMENT**

**Baseline Methodology:**
- Test files identified by pattern matching
- Python: `test_*.py` or `*_test.py` (Pytest/unittest conventions)
- TypeScript: `*test.ts` or `*spec.ts` (Jest/Mocha)
- JavaScript: `*test.js` or `*spec.js`
- Directories: `test/`, `__tests__/`, `e2e_tests/`, `spec/`

**Your Implementation:**
```python
# From collection/detector.py (inferred)
# Likely implements similar pattern matching
```

✅ **Likely aligned** but not explicitly verified in code review

**Academic Rigor Score:** 7/10

---

### 2.3 Research Questions Definition - **SIGNIFICANT GAP** ❌

**Baseline Paper (3 RQs with statistical framing):**

| RQ | Framing | Statistical Test |
|---|---|---|
| RQ1: Frequency of agent test generation? | Chi-squared independence test on all 1.2M commits | χ² = 3,683.06, p < 0.001 |
| RQ2a: Commit-level mock generation? | Chi-squared on 169K test commits | Stratified by commit |
| RQ2b: Repository-level mocking? | Paired Wilcoxon test within same repo | Cliff's delta effect size |
| RQ3: Mock type diversity? | Frequency analysis of 5 test double types | Comparison of mock types |

**Your Implementation:**
```python
# paired_collection.py
# Implicit RQs:
# - Do agents and humans differ in fixture patterns within repos? (unstated)
# - What distributions of fixtures, domains, etc.? (descriptive only)
```

❌ **CRITICAL GAP:** No explicit research questions document. Your module collects paired data but doesn't specify what hypotheses you're testing.

**What's Missing:**
```markdown
## Research Questions

**RQ1:** Do coding agents generate more mocks in test code compared to human developers?
- Hypothesis: Agent mock ratio > human mock ratio
- Statistical test: Chi-squared + paired Wilcoxon
- Null hypothesis: No difference in mock generation

**RQ2:** What types of test doubles do agents prefer?
- Hypothesis: Agents show less diversity in test double types
- Statistical test: Frequency analysis + effect size
- Baseline comparison: human distribution

**RQ3:** Within the same repository, do agent-generated tests have different mock characteristics?
- Hypothesis: Agent commits have higher mock density
- Statistical test: Paired t-test or Wilcoxon (controlling for repo)
```

**Academic Impact:** Lack of explicit RQs makes it impossible to evaluate whether your statistical tests are appropriate or if your data collection is complete.

**Academic Rigor Score:** 2/10

---

### 2.4 Within-Repository Paired Analysis - **MODERATE ALIGNMENT**

**Baseline Approach:**
- Analyzes all repositories (no per-language caps)
- Compares agent vs. non-agent commits within SAME repository
- Stratified by agentic activity level (10-49 commits vs. 50+ commits)
- Paired statistical tests to control for repo characteristics

**Your Implementation:**
```python
# paired_collection.py - paired study structure
- Selects repos with both agent AND human commits ✅
- Stores at repository level (repo_path)
- _compute_chi_square_balance() suggests paired analysis
- class PairedStudyCollector suggests within-repo design ✅
```

✅ **Conceptually aligned** - Paired within-repo comparison

**Gaps:**
- No explicit stratification by agentic activity level
- No clear documentation of pairing strategy (how are agent/human commits paired?)
- Sample size calculation not documented
- Minimum sample requirements not specified

**Academic Rigor Score:** 6/10

---

### 2.5 Threats to Validity - **CRITICAL GAP** ❌

**Baseline Paper Threats Section (Section 5):**

| Threat | Mitigation |
|--------|-----------|
| Detection of test/mock commits | Based on official documentation; established solutions minimize false positives |
| Detection of agent commits | Multiple agent types; case-insensitive matching; manual precision validation (500 commits, 100%) |
| Agent co-authors ambiguity | Multiple views of data (Tables 5, 8); Co-authored-by trailer analysis |
| Generalization limits | 3 languages only; 2025 data only; specific agent tools only; cannot generalize to other languages |

**Your Implementation:**
```python
# No threats section in collection module code
# No documented validity threats
# No precision/recall analysis
```

❌ **CRITICAL GAP:** No threats to validity discussion. This is essential for academic credibility.

**What's Missing:**
```markdown
## Threats to Validity

### Internal Validity
- **Agent detection precision:** How often do our patterns correctly identify agents? 
  Mitigation: Manual validation of 500 commits (per baseline)
- **Mock detection precision:** Do our patterns correctly identify mocks?
  Mitigation: Pattern grounding in official test framework docs

### External Validity
- **Language generalization:** Results from Python/TS/JS may not apply to other languages
  Mitigation: Explicit statement that findings are language-specific
- **Time period:** Data from 2025 only - may not reflect future practices
  Mitigation: Note as temporal limitation
- **Agent tool scope:** Only analyzing Claude/Copilot/Cursor
  Mitigation: Document excluded agents

### Construct Validity
- **Fixture extraction accuracy:** Do extracted fixtures represent actual test behavior?
  Mitigation: Cross-validation with manual inspection of sample
- **Pairing strategy:** Are agent/human commits truly comparable?
  Mitigation: Control variables (domain, star tier, repo age)
```

**Academic Impact:** Omitting threats section significantly reduces credibility at peer review. Major conferences expect explicit validity discussion.

**Academic Rigor Score:** 0/10 (if absent)

---

## Section 3: Data Collection & Reporting Gaps

### 3.1 Dataset Overview - **MODERATE GAP**

**Baseline Reporting (Table 3):**
```
Commits:           TS: 835,781   JS: 98,389   Python: 320,708   Total: 1,254,878
Agent commits:     TS: 32,728    JS: 3,892    Python: 11,943    Total: 48,563
Test commits:      TS: 94,747    JS: 6,428    Python: 68,186    Total: 169,361
Mock commits:      TS: 23,838    JS: 1,561    Python: 19,501    Total: 44,900

Repositories:
With agent files:  TS: 1,392     JS: 242      Python: 534       Total: 2,168
With agent commits: TS: 773      JS: 117      Python: 329       Total: 1,219
With test commits: TS: 1,149     JS: 143      Python: 487       Total: 1,779
With mock commits: TS: 890       JS: 89       Python: 402       Total: 1,381
```

**Your Implementation:**
```python
# paired_collection.py - PairedStudyStats
@dataclass
class PairedStudyStats:
    repos_scanned: int = 0
    repos_with_pairs: int = 0
    agent_commits: int = 0
    human_commits: int = 0
    repos_by_language: Dict[str, int] = ...
    language_distribution: Dict[str, int] = ...
```

✅ **Captures key metrics** but missing:
- Per-language breakdown of test/mock commits
- Distinction between repositories with configuration files vs. actual agent commits
- Repository stratification by agentic activity level (10-49 vs. 50+)

**Academic Rigor Score:** 6/10

---

### 3.2 Configuration File Analysis - **MISSING** ❌

**Baseline Finding (Table 12):**
The paper analyzes **coding agent configuration files** to understand mock guidance:
```
CLAUDE.md:             112k files, 102k with "test", 13k with "mock"
copilot-instructions.md: 44k files, 27k with "test", 7k with "mock"
CURSOR.md:             4.8k files, 1.3k with "test", 200 with "mock"

Key Insight: Test instructions common, mock instructions rare
```

**Your Implementation:**
```python
# agent_patterns.py
PAPER_AGENT_CONFIG_PATTERNS = [...]  # Lists patterns
repo_contains_patterns()  # Checks if patterns present

# But NO analysis of what's IN those files
```

❌ **MISSING:** Content analysis of agent configuration files. The baseline paper argues this is critical for understanding agent-generated test quality.

**What's Missing:**
```python
def analyze_agent_config_files(repo_path: Path) -> dict:
    """Extract guidance on testing and mocking from agent config files."""
    config_files = [
        'CLAUDE.md', 'copilot-instructions.md', 'CURSOR.md',
        '.claudeignore', '.cursorrules', 'AGENTS.md'
    ]
    
    for config_file in config_files:
        file_path = repo_path / config_file
        if file_path.exists():
            content = file_path.read_text()
            # Extract test-related guidance
            # Extract mock-related guidance
            # Cross-reference with actual agent-generated tests
```

**Academic Impact:** Configuration file analysis is a novel contribution in the baseline paper. Including this would significantly strengthen your work.

**Academic Rigor Score:** 0/10 (if this is your focus)

---

## Section 4: Required Methodological Components for Conference Submission

### Critical Components (Must Have) ❌❌❌

| Component | Baseline | Your Module | Status |
|-----------|----------|-------------|--------|
| Explicit research questions | ✅ 3 RQs stated | ❌ Implicit | **MISSING** |
| Mock identification patterns | ✅ Defined per language | ❌ Not in code | **MISSING** |
| Threats to validity | ✅ 4 sections | ❌ No section | **MISSING** |
| Statistical power analysis | ✅ Sample sizes reported | ❌ Not documented | **MISSING** |
| Effect size reporting | ✅ Cliff's delta, standardized residuals | ❌ Only p-values | **MISSING** |
| Paired analysis framework | ✅ Explicit stratification | ⚠️ Implicit | **INCOMPLETE** |

### Important Components (Should Have) ⚠️⚠️⚠️

| Component | Baseline | Your Module | Status |
|-----------|----------|-------------|--------|
| Precision validation | ✅ 500 commits (100%) | ❌ Not documented | **MISSING** |
| Configuration file analysis | ✅ Table 12 analysis | ❌ No analysis | **MISSING** |
| Related work section | ✅ 6.1 Coding Agents, 6.2 Test Doubles | ❌ Not in module | **MISSING** |
| Reproducibility statement | ✅ "Scripts available at: zenodo.17427638" | ❌ No statement | **MISSING** |
| Qualitative examples | ✅ Figures 1-2 with code examples | ❌ Fixture examples not shown | **WEAK** |

---

## Section 5: Strengths of Your Module (Comparative Advantage)

### 5.1 Within-Repository Pairing ✅

**Your Innovation:** Explicitly paired analysis at commit level within same repository
- Baseline uses repository as context but doesn't pair individual commits
- Your approach: agent commit → human commit within same repo
- **Academic Value:** Controls for repository-specific factors (domain, complexity, team size)

**Recommendation:** Leverage this as novel contribution. Baseline doesn't do commit-level pairing within repos.

---

### 5.2 Fixture Extraction ✅

**Your Focus:** Detailed fixture-level analysis (setup, assertions, mocking scope)
- Baseline: Counts commits with mocks (binary)
- Your approach: Analyzes fixture structure, dependencies, complexity
- **Academic Value:** Provides deeper understanding than prevalence counting

**Recommendation:** Position this as advancing beyond mock counting to mock characterization.

---

### 5.3 Comprehensive Test Suite ✅

**Your Implementation:** 461 tests, 100% pass rate (per memory)
- Baseline: No explicit test suite mentioned
- Your approach: Regression-tested pipelines
- **Academic Value:** Reproducibility and confidence

**Recommendation:** Document this in reproducibility section.

---

## Section 6: Priority Remediation Plan for Conference Rigor

### Priority 1 (CRITICAL - Week 1) ⚠️⚠️⚠️

**1.1 Explicit Research Questions Document**
- [ ] Write 2-3 clear RQs with hypotheses
- [ ] Specify statistical tests for each
- [ ] Document null hypotheses
- **Location:** Create `docs/methodology/research-questions.md`

**1.2 Mock Identification Implementation**
- [ ] Define mock patterns per language (or justify why not analyzing mocks)
- [ ] Implement mock detection in `detector.py` or `fixture_extractor.py`
- [ ] Add test detection for mock types (dummy, stub, spy, mock, fake)
- [ ] Document precision if possible (manual validation sample)
- **Effort:** 4-6 hours

**1.3 Threats to Validity Document**
- [ ] Create `docs/methodology/threats-to-validity.md`
- [ ] Sections: Internal, External, Construct, Statistical validity
- [ ] For each threat: description + mitigation strategy
- [ ] Document exclusions (languages, agent types, time period)
- **Effort:** 2 hours

### Priority 2 (HIGH - Week 2)

**2.1 Effect Size & Statistical Reporting**
- [ ] Implement Cliff's delta computation
- [ ] Add Wilcoxon test for paired repository analysis
- [ ] Report contingency tables with standardized residuals
- [ ] Multiple comparison correction if multiple RQs

**2.2 Precision Validation**
- [ ] Manual inspection of 500 commits for agent detection accuracy
- [ ] Document precision/recall/F1-score
- [ ] Mock detection precision (sample of 100-200 commits)

**2.3 Reproducibility Statement**
- [ ] Document dataset location/availability
- [ ] Zenodo upload of code + anonymized data sample
- [ ] Reproduction instructions in README

### Priority 3 (MEDIUM - Week 3)

**3.1 Configuration File Analysis**
- [ ] Extract + analyze agent configuration files
- [ ] Keyword frequency (test, mock, fixture, assert, etc.)
- [ ] Cross-reference guidance with actual agent-generated tests
- [ ] Table showing prevalence of mock guidance

**3.2 Qualitative Examples**
- [ ] Show code examples of agent vs. human test differences
- [ ] Highlight mock usage patterns
- [ ] Demonstrate fixture-level differences

---

## Section 7: Specific Code Recommendations

### Recommendation 1: Add Research Questions Module

```python
# collection/research_questions.py
"""Formal research questions and statistical framework."""

from dataclasses import dataclass
from enum import Enum
from typing import Callable

class StatisticalTest(Enum):
    CHI_SQUARED = "chi_squared"
    WILCOXON = "wilcoxon_paired"
    T_TEST = "independent_t_test"
    MANN_WHITNEY = "mann_whitney"

@dataclass
class ResearchQuestion:
    id: str
    question: str
    null_hypothesis: str
    alternative_hypothesis: str
    statistical_test: StatisticalTest
    primary_variables: list[str]
    control_variables: list[str]
    expected_effect_size: float  # 0.2=small, 0.5=medium, 0.8=large
    
RQ1 = ResearchQuestion(
    id="RQ1",
    question="Do coding agents generate tests more frequently than human developers?",
    null_hypothesis="No difference in test commit ratio between agents and humans",
    alternative_hypothesis="Agents have higher test commit ratio",
    statistical_test=StatisticalTest.CHI_SQUARED,
    primary_variables=["agent_status", "test_commit"],
    control_variables=["language", "repo_domain"],
    expected_effect_size=0.5  # Based on baseline: 23% vs 13%
)

RQ2 = ResearchQuestion(
    id="RQ2",
    question="Within the same repository, do agents generate more mocks in tests?",
    null_hypothesis="No difference in mock usage between agents and humans",
    alternative_hypothesis="Agents use more mocks in tests",
    statistical_test=StatisticalTest.WILCOXON,
    primary_variables=["agent_status", "mock_count"],
    control_variables=["repository", "test_file"],
    expected_effect_size=0.6  # Based on baseline: 36% vs 26%
)

RQ3 = ResearchQuestion(
    id="RQ3",
    question="Do agents show less diversity in test double types compared to humans?",
    null_hypothesis="No difference in test double type distribution",
    alternative_hypothesis="Agents prefer specific test double types",
    statistical_test=StatisticalTest.CHI_SQUARED,
    primary_variables=["agent_status", "test_double_type"],
    control_variables=["repository"],
    expected_effect_size=0.4
)
```

**Location:** `collection/research_questions.py`  
**Effort:** 2 hours

---

### Recommendation 2: Add Mock Detection

```python
# collection/mock_detector.py
"""Detect mock usage in test files."""

import re
from pathlib import Path
from typing import Dict, List, Set

MOCK_PATTERNS = {
    'python': {
        'mock': [
            r'\bfrom\s+unittest\.mock\s+import',
            r'\bfrom\s+unittest\s+import\s+mock',
            r'\bfrom\s+pytest[-_]mock\s+import',
            r'Mock\s*\(',
            r'MagicMock\s*\(',
            r'patch\s*\(',
            r'@patch\(',
            r'monkeypatch\b',
        ],
        'stub': [r'\.return_value\s*=', r'\.side_effect\s*='],
        'spy': [r'spy\(', r'assert_called'],
        'dummy': [r'lambda\s*:', r'None\b'],  # Incomplete
        'fake': [r'FakeDB\|FakeClient|FakeServer'],
    },
    'javascript': {
        'mock': [
            r'jest\.mock\s*\(',
            r'jest\.spyOn\s*\(',
            r'sinon\.mock\s*\(',
        ],
        'spy': [
            r'sinon\.spy\s*\(',
            r'jest\.spyOn\s*\(',
            r'jasmine\.spyOn\s*\(',
        ],
        'stub': [
            r'sinon\.stub\s*\(',
            r'\.stub\s*\(',
        ],
    },
    'typescript': {  # Same as JavaScript
        'mock': [...],
        'spy': [...],
        'stub': [...],
    },
}

def detect_mock_type(test_code: str, language: str) -> Dict[str, int]:
    """Detect mock types in test code."""
    counts = {mock_type: 0 for mock_type in ['mock', 'stub', 'spy', 'dummy', 'fake']}
    
    patterns = MOCK_PATTERNS.get(language, {})
    for mock_type, regexes in patterns.items():
        for regex in regexes:
            matches = re.findall(regex, test_code, re.IGNORECASE)
            counts[mock_type] += len(matches)
    
    return counts

def has_mock_commit(changed_files: List[Dict]) -> bool:
    """Check if commit adds/modifies mocks in test files."""
    for file_info in changed_files:
        if file_info['is_test_file']:
            # Check if diff contains mock patterns
            if 'mock' in file_info.get('additions', '').lower():
                return True
    return False
```

**Location:** `collection/mock_detector.py`  
**Effort:** 3 hours

---

### Recommendation 3: Add Validity Threats Document

```markdown
# docs/methodology/threats-to-validity.md

## Threats to Validity

### Internal Validity

#### Agent Detection False Positives/Negatives
- **Threat:** Co-authored-by metadata may be manually added by developers (not agent-generated)
- **Mitigation:** Manual validation of 500 commits; measure precision
- **Evidence:** Baseline achieved 100% precision on manual sample
- **Impact:** High

#### Mock Detection False Positives
- **Threat:** Patterns like "mock" in comments/strings detected as actual mock code
- **Mitigation:** Pattern refinement; require syntactic context (imports, function calls)
- **Impact:** Medium

### External Validity

#### Language Generalization
- **Threat:** Python/TypeScript/JavaScript patterns may not apply to Java, C++, Go
- **Mitigation:** Analysis explicitly scoped to three languages; findings labeled language-specific
- **Stated Limitation:** "Findings cannot be generalized to other programming languages"
- **Impact:** Medium

#### Time Period (2025 Only)
- **Threat:** Agent behaviors may evolve; 2025 may not represent future usage
- **Mitigation:** Longitudinal study planned for future work
- **Stated Limitation:** "Data reflects agent behavior in 2025 only"
- **Impact:** Medium

#### Agent Tool Scope
- **Threat:** Only analyzing Claude/Copilot/Cursor; missing emerging agents (Devin, Replit, etc.)
- **Mitigation:** Included 10+ agent types in detection; not exhaustive but comprehensive
- **Stated Limitation:** "Agent scope limited to major tools in 2025"
- **Impact:** Low

### Construct Validity

#### Repository Pairing Strategy
- **Threat:** Agent and human commits within same repository may not be comparable (different features, complexity)
- **Mitigation:** Control variables: repository domain, star tier, repository age, contributor count
- **Impact:** Medium

#### Fixture Extraction Accuracy
- **Threat:** Automated fixture extraction may miss context-dependent mocks
- **Mitigation:** Spot-check 50 fixtures manually; compare automated vs. manual classification
- **Impact:** Medium

### Statistical Validity

#### Multiple Comparisons
- **Threat:** Multiple RQs without correction increase Type I error
- **Mitigation:** Bonferroni correction for multiple tests; report adjusted α
- **Impact:** Low (if controlled)

#### Confounding Variables
- **Threat:** Repository characteristics (age, size, domain) correlate with both agent usage and mocking
- **Mitigation:** Include as control variables in paired tests
- **Impact:** High
```

**Location:** `docs/methodology/threats-to-validity.md`  
**Effort:** 2 hours

---

## Section 8: Alignment Summary Table

| Research Aspect | Baseline | Your Module | Gap | Priority |
|---|---|---|---|---|
| **Scope** |
| Languages | Python, TS, JS | Python, TS, JS | ✅ Aligned | — |
| Time period | 2025 | 2025 | ✅ Aligned | — |
| Agent detection | Co-author trailers | Co-author trailers | ✅ Aligned | — |
| **Methodology** |
| Research questions | 3 explicit RQs | Implicit | ❌ Critical | P1 |
| Mock identification | Explicit patterns | Not in code | ❌ Critical | P1 |
| Test commit detection | Pattern-based | Likely present | ⚠️ Unknown | P1 |
| Statistical tests | Chi-square, Wilcoxon | Chi-square only | ❌ High | P2 |
| **Rigor** |
| Threats to validity | Documented (Section 5) | Not documented | ❌ Critical | P1 |
| Precision validation | 100% (500 commits) | Not reported | ❌ High | P2 |
| Effect sizes | Cliff's delta | None | ❌ High | P2 |
| **Analysis** |
| Within-repo pairing | ✅ Yes | ✅ Yes | ✅ Aligned | — |
| Configuration file analysis | Table 12 | Not done | ❌ High | P3 |
| Mock type classification | 5 types | Not implemented | ❌ Medium | P2 |
| **Reporting** |
| Dataset summary table | Table 3 (detailed) | Partial | ⚠️ Medium | P2 |
| Reproducibility | Zenodo DOI | Not stated | ❌ Medium | P2 |
| Code availability | Public repo | Not stated | ⚠️ Medium | P2 |

---

## Section 9: Positioning Your Work for Conference Success

### Framing Your Contribution

**Baseline Paper Contribution:**
"First study to investigate mock prevalence in agent-generated tests using empirical mining of 1.2M commits"

**Your Potential Contribution:**
Choose ONE of these angles:

**Option A: Fixture-Level Analysis**
"First study to characterize fixture-level differences in agent vs. human test code through paired within-repository commit analysis"
- Focus: Mock type diversity, fixture setup complexity, assertion patterns
- Advantage: Deeper than prevalence counting
- Requirement: Implement mock detection + type classification

**Option B: Configuration-Guided Analysis**
"Evaluating alignment between agent configuration guidance and actual test generation practices"
- Focus: Do CLAUDE.md mock instructions match actual agent behavior?
- Advantage: Novel angle (baseline mentions but doesn't analyze deeply)
- Requirement: Configuration file content analysis + cross-reference

**Option C: Temporal Evolution**
"How have agent testing patterns evolved as coding agents matured through 2025?"
- Focus: Agent behavior change over time
- Advantage: Longitudinal perspective
- Requirement: Monthly/quarterly trend analysis

---

## Section 10: Final Recommendations

### If Goal = Publish at Top Venue (MSR, ICSE, FSE)

**Required Additions:**
1. ✅ Explicit mock detection implementation
2. ✅ Formal research questions + hypotheses
3. ✅ Threats to validity section (2-3 pages)
4. ✅ Effect size + statistical power reporting
5. ✅ Precision validation (manual sample)
6. ✅ Configuration file analysis OR novel angle (see Section 9)

**Timeline:** 3-4 weeks of focused effort

**Estimated Word Count Increase:** +4,000-5,000 words for methodology section

---

### If Goal = Complete Your Study First

**Immediate Next Steps:**
1. Define 2-3 explicit research questions
2. Implement mock detection
3. Run statistical tests (add Wilcoxon)
4. Document threats to validity
5. Validate precision on samples

**Then Evaluate:** Whether to pursue publication or continue internal development

---

## Appendix: Cross-Reference Matrix

### Baseline Methods → Your Code

| Baseline Section | Baseline Approach | Your Implementation | File/Status |
|---|---|---|---|
| 2.3 Agent Config | Search for CLAUDE.md, copilot-instructions.md | agent_patterns.py | ✅ Present |
| 2.4 Agent Commits | Co-author-by + signature matching | agent_commit_detector.py | ✅ Present |
| 2.5 Test Commits | Pattern: `test_*.py`, `*test.ts`, etc. | detector.py | ⚠️ Likely present |
| 2.6 Mock Commits | Search for: dummy, stub, spy, mock, fake | ❌ Not found | ❌ Missing |
| 2.8.1 RQ1 Stat | Chi-squared independence test | paired_collection.py | ✅ Present |
| 2.8.2 RQ2 Stat | Wilcoxon + Cliff's delta | ❌ Not found | ❌ Missing |
| 2.8.3 RQ3 Analysis | Mock type frequency | ❌ Not implemented | ❌ Missing |
| 5 Threats | 4-part validity framework | ❌ Not documented | ❌ Missing |

---

## Conclusion

Your collection module has **solid foundational structure** for a rigorous empirical study. It correctly implements agent detection, repository pairing, and basic statistical testing. However, to meet the **academic rigor expected at top-tier conferences** (MSR, ICSE, FSE), you need to:

### Critical (Must Fix):
1. ✅ Add explicit research questions
2. ✅ Implement mock detection
3. ✅ Document threats to validity

### Important (Should Fix):
4. ✅ Add effect size reporting
5. ✅ Validate precision with manual samples
6. ✅ Implement configuration file analysis

### Nice to Have:
7. ✅ Add qualitative examples
8. ✅ Create reproducibility statement

**Estimated Effort:** 3-4 weeks for all critical + important items

**Recommendation:** Start with Priority 1 items while continuing data collection. This allows you to refine methodology during the collection phase rather than after.

---

*Evaluation completed: May 25, 2026*  
*Baseline Reference: "Are Coding Agents Generating Over-Mocked Tests?" Hora & Robbes, MSR '26*

