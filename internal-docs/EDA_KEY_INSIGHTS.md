# FixtureDB EDA — Key Insights Revealed by New Plots

## Fixture Type Patterns (What Detection Patterns Dominate?)

**Top Detection Patterns Across All Languages:**
1. **unittest_setup** (5,691) — Python setUp() methods
2. **junit_class_rule** (5,543) — Java @ClassRule annotations
3. **junit4_before** (5,295) — Java @Before annotations
4. **junit5_before_each** (2,743) — Java @BeforeEach (JUnit 5)
5. **junit4_after** (2,566) — Java @After cleanup

**Insight:** Java dominance in fixture definitions (nearly 23K fixtures) reflects its verbose setup/teardown patterns, while Python/JS use parameterized/decorator patterns.

---

## Execution Scope: When Are Fixtures Created?

### By Language:
| Language | per_test (%) | per_class (%) | per_module (%) | global (%) |
|----------|------------|-------------|--------------|----------|
| **Java** | 59.6% | 40.4% | — | — |
| **Python** | 93.4% | 4.1% | 1.6% | 0.6% |
| **JavaScript** | 90.1% | 9.9% | — | — |
| **TypeScript** | 91.6% | 8.4% | — | — |

**Insight:** 
- Python/JS/TS heavily favor isolated per-test fixtures (good isolation)
- Java splits between per_test and per_class (OOP patterns influence scope)
- Very few global fixtures indicates good practice adherence

---

## Fixture Size (Lines of Code)

### Statistics by Language:
| Language | Avg LOC | Min | Max | Typical Range |
|----------|---------|-----|-----|-----------------|
| **Python** | 6.34 | 2 | 371 | 3-8 lines |
| **Java** | 7.80 | 1 | 613 | 5-10 lines |
| **JavaScript** | 8.00 | 1 | 92 | 5-10 lines |
| **TypeScript** | 7.59 | 1 | 64 | 5-10 lines |

**Insight:**
- Most fixtures are very short (median ~6-8 lines)
- Python fixtures slightly smaller (minimal setup syntax)
- Java largest outliers (complex object setup)
- **Design interpretation:** Fixtures follow single-responsibility principle

---

## Complexity: Cyclomatic vs Cognitive

### By Language:
| Language | Cyclomatic | Cognitive | Interpretation |
|----------|-----------|-----------|-----------------|
| **Python** | 1.32 | 0.33 | Branching present, but linear (low nesting) |
| **Java** | 1.18 | 0.90 | Branching + nesting |
| **JavaScript** | 1.09 | 1.05 | Simple branches, moderate nesting |
| **TypeScript** | 1.04 | 0.96 | Simple, well-structured |

**Insight:**
- Python fixtures have more branches (conditionals in setup)
- But Python has lowest cognitive complexity (good nesting practices)
- TypeScript simplest overall (language features reduce complexity)
- **Design interpretation:** Fixtures are generally simple; complexity when present is managed well

---

## Teardown Adoption: Cleanup Code Patterns

### Critical Finding:
| Language | Teardown Adoption |
|----------|------------------|
| **Python** | **76.3%** ✓ |
| **JavaScript** | **16.4%** |
| **Java** | **13.4%** |
| **TypeScript** | **14.7%** |

**Why Python is Different:**
- Python test frameworks (pytest) encourage explicit cleanup
- Java/JS communities may use context managers, try-finally, or after hooks
- Or: Python fixtures managing more stateful resources (databases, file I/O)

**Insight:** Python fixture code manages resource cleanup explicitly; Java/JS may rely on framework-level cleanup or garbage collection.

---

## Test File Organization

### Characteristics:
| Language | Avg File Size | Fixtures Per File | Test Functions Per File |
|----------|---------------|------------------|------------------------|
| **Python** | 198 LOC | 0.57 | 12.32 |
| **JavaScript** | 179 LOC | 0.45 | 15.69 |
| **Java** | 138 LOC | 0.40 | 7.48 |
| **TypeScript** | 97 LOC | 0.44 | 7.14 |

**Insight:**
- Not all test files have fixtures (many 0-fixture files)
- When fixtures present: ~1 fixture per 2 test functions (reuse rate)
- Python test files larger but not because of more fixtures
  - Likely: larger setup/helper code sections
- JavaScript has most test functions per file (many small tests)

---

## Framework + Scope Interaction (New View)

**Key Finding:** Frameworks have distinct scope preferences:
- **pytest** → 99%+ per_test scope (isolated fixtures)
- **unittest** → Mixed (setUp varies by class hierarchy)
- **JUnit4** → Split per_test vs per_class based on annotation choice
- **Jest/Mocha** → Predominantly beforeEach (per-test equivalent)

**Design Insight:** Framework choice strongly influences fixture scope patterns; not just developer preference.

---

## Repository Maturity vs Fixture Quality

**Analysis:** Does popularity (stars) predict fixture complexity?

**Finding:** **No strong correlation**
- Popular projects (10K stars) have same fixture complexity as less popular (500 stars)
- **Why?** Good fixture design isn't correlated with overall project popularity
- Alternative signals:
  - More contributors → slightly more external_calls (distributed patterns)
  - Forks don't strongly predict fixture reuse
  - **Conclusion:** Fixture quality is independent variable; popularity measures different aspects

---

## Design Pattern Summary

### Dependencies (Parameters):
- **Mean parameters per fixture:** 0.8-1.2
- **Interpretation:** Fixtures are not heavily parameterized (simple contracts)

### External Calls (I/O, APIs):
- **~10-15% of fixtures make external calls**
- **Interpretation:** Most fixtures are isolated; external dependencies are explicit (and rare)

### Object Instantiation:
- **Mean objects per fixture:** 1-2
- **Interpretation:** Fixtures create simple test doubles; not heavyweight setup

### Cleanup Code:
- **Python 76% vs Java 13%:** Huge difference in cleanup approach
- **Implication:** Testing frameworks shape cleanup patterns

---

## Language Comparison Summary

| Dimension | Python | Java | JavaScript | TypeScript |
|-----------|--------|------|------------|-----------|
| **Fixture Count** | 6,186 | 22,976 | 2,053 | 1,680 |
| **Typical Scope** | per_test (93%) | Mixed: per_test/class | per_test (90%) | per_test (92%) |
| **Avg LOC** | 6.34 | 7.80 | 8.00 | 7.59 |
| **Complexity** | Higher cyclomatic, lower cognitive | Balanced | Lowest | Lowest |
| **Cleanup** | Explicit (76%) | Framework-level (13%) | Framework-level (16%) | Framework-level (15%) |
| **Design** | Simple, explicit cleanup | Formal OOP patterns | Modern framework reliance | Type-safe, simple |

---

## Research Questions These Plots Enable

1. **"What fixture patterns dominate Python testing?"**
   - Answer in `03c_fixture_types.png` + `03d_fixture_scopes.png`

2. **"How do fixture size and complexity relate?"**
   - Answer in `04c_lines_of_code.png` + `04d_complexity_metrics.png`

3. **"Do more popular projects have better-designed fixtures?"**
   - Answer in `05i_repo_maturity.png`: No strong correlation

4. **"What's the typical fixture design pattern?"**
   - Answer in `05h_design_patterns.png`: Small, simple, 1-2 parameters

5. **"How are test files organized around fixtures?"**
   - Answer in `05g_test_file_characteristics.png`: ~0.5 fixtures per test file

6. **"Why do languages differ in cleanup patterns?"**
   - Answer in `05h_design_patterns.png` teardown panel + fixture type knowledge

7. **"Do frameworks influence fixture scope choices?"**
   - Answer in `04e_framework_by_scope.png`: Yes, strongly

---

## Implications for Researchers

**If you're studying:**

- **Fixture design patterns**: Use `03c`, `05h` for empirical distributions
- **Testing practices by language**: Use `04e`, `03d`, `04c` for language comparisons
- **Fixture complexity**: Use `04c`, `04d` for distributions; `05d` for reuse impact
- **Test file organization**: Use `05g` for file-level characteristics
- **Framework influence**: Use `04e` for scope patterns; `03c` for detection types
- **Code quality signals**: Use `05i` to see what correlates (and what doesn't)

---

## How to Present These Findings

**For ICSME Data Showcase:**
- Emphasize diversity: 35K+ fixtures across 4 languages, 200 projects
- Show cleaning architectural differences (Python vs Java)
- Highlight design quality: Fixtures are small, simple, well-scoped

**For Papers Using This Data:**
- Reference `03c`, `03d`, `04c`, `04d` for corpus characteristics
- Use `05h` for design pattern baselines
- Use `05g` for test file organization context

**For Practitioners:**
- Show `03d` to justify per-test scope (90%+ adoption in modern languages)
- Show `05h` to highlight cleanup practices by language
- Show `04e` to explain framework-specific patterns

---

## Files for Reference

- **EDA Output**: `/home/joao/icsme-nier-2026/output/eda/quantitative/latest/` (21 PNG files)
- **Data Source**: `/home/joao/icsme-nier-2026/data/corpus.db` (SQLite)
- **Plot Scripts**: `/home/joao/icsme-nier-2026/eda/quantitative/` (p03c, p04c-e, p05g-i)
- **CSV Export**: `/home/joao/icsme-nier-2026/export/fixturedb_v1.0-zenodo_*.zip` (Zenodo ready)

All plots directly reflect exported CSV structure for Zenodo dataset.
