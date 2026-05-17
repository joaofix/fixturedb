# References

This document lists scientific papers referenced in FixtureDB. These works inform our dataset design, collection strategy, and metrics.

---

## Academic Foundation

**Dataset Selection & Sampling**

Pan, R., Stennett, T., Pavuluri, R., Levin, N., Orso, A., & Sinha, S. (2025).  
*Hamster: A Large-Scale Study and Characterization of Developer-Written Tests.* arXiv:2509.26204 [cs.SE]  
→ Establishes 500-star threshold for mature projects; provides comparative context for fixture usage patterns.

**Test Quality & Mocking Challenges**

Ahmed, M., Islam Opu, M. N., Roy, C., Islam Suhi, S., & Chowdhury, S. (2025).  
*Exploring Challenges in Test Mocking: Developer Questions and Insights from StackOverflow.* arXiv:2505.08300 [cs.SE]  
→ Empirical evidence of mock design pain points; justifies fixture characterization focus.

**Test Complexity Metrics**

Ouédraogo, W. C., Li, Y., Dang, X., Zhou, X., Koyuncu, A., Klein, J., Lo, D., & Bissyandé, T. F. (2025).  
*Rethinking Cognitive Complexity for Unit Tests: Toward a Readability-Aware Metric.* ICSME 2025 (NIER Track). arXiv:2506.06764 [cs.SE]  
→ Proposes CCTR metric for test-aware complexity; directly informs our fixture complexity methodology.

---

## Related Work

**Test Fixture Characterization**

Li, M., & Fazzini, M. (2024).  
*Automatically Removing Unnecessary Stubbings from Test Suites.* arXiv:2407.20924 [cs.SE]  
→ Addresses fixture maintenance through automated over-stubbing detection.

**AI-Generated Tests & Mocking**

Hora, A., & Robbes, R. (2026).  
*Are Coding Agents Generating Over-Mocked Tests? An Empirical Study.* MSR 2026.  
→ Examines differences between human and AI-generated fixture patterns.

**Code Evolution Analysis**

Hora, A. (2026). *GitEvo: Code Evolution Analysis for Git Repositories.* MSR 2026.  
→ Infrastructure for analyzing longitudinal test and fixture evolution.

---

## How to Cite FixtureDB

```bibtex
@inproceedings{Almeida2026,
  author = {Almeida, João and Hora, Andre},
  title = {FixtureDB: A Multi-Language Dataset of Test Fixture Definitions from Open-Source Software},
  booktitle = {Proceedings of the 2026 IEEE/ACM International Conference on Software Maintenance and Evolution (ICSME 2026)},
  year = {2026},
  note = {Tool Demonstration and Data Showcase Track}
}
```

---

## Methodology Grounding

Our design decisions are rooted in empirical practices:
- **Star thresholds** (500/100): From Hamster study of mature projects with established test culture
- **Quality filters** (MIN_TEST_FILES=5): Based on empirical observations of test project characteristics
- **Metrics selection:** Grounded in academic complexity metrics and large-scale characterization studies

