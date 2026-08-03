# Dataset Findings (outside RQ1-3)

> Descriptive statistics about the datasets themselves -- collection process, composition -- that support paper claims but don't belong to any single RQ1-3 comparison. See this module's docstring for what each section below covers and why it lives here instead of its own script.

Generated: 2026-08-03 21:07:57 UTC

## Diff-Purity Gate (Dataset A)

Of Dataset A's agent commits that touched >=1 test file, how many were rejected for mixing test-file additions with edits/deletions, vs accepted as pure additions?

### Overall

2,323/3,944 repos had >=1 agent commit touching a test file.

| Touching tests | Accepted (pure addition) | Rejected (mixed diff) | Unclassified (extraction error) | Rejection rate |
|---|---|---|---|---|
| 140,370 | 68,595 | 71,003 | 772 | 50.58% |

### By language

**Rejection rate by repo language**

| Group | Repos | Touching tests | Rejected | Rejection rate |
|---|---|---|---|---|
| typescript | 2,009 | 82,176 | 42,442 | 51.65% |
| python | 1,233 | 43,804 | 21,993 | 50.21% |
| java | 332 | 7,622 | 3,441 | 45.15% |
| javascript | 370 | 6,768 | 3,127 | 46.20% |

### By agent adoption intensity

**Rejection rate by agent_adoption_intensity**

| Group | Repos | Touching tests | Rejected | Rejection rate |
|---|---|---|---|---|
| consistent | 554 | 56,659 | 28,434 | 50.18% |
| pervasive | 156 | 48,744 | 24,578 | 50.42% |
| limited | 842 | 29,978 | 15,400 | 51.37% |
| experimental | 771 | 4,989 | 2,591 | 51.93% |
| no_commits | 1,621 | 0 | 0 | -- |

### Per-repo distribution

**Per-repo rejection-rate distribution** (one rate per repo with >=1 test-touching commit -- each repo counted once, not weighted by its commit volume)

| N repos | Mean | Median | Stdev | Min | Max | Repos at 0% rejected | Repos at 100% rejected |
|---|---|---|---|---|---|---|---|
| 2,323 | 0.496 | 0.500 | 0.281 | 0.000 | 1.000 | 259 | 247 |

## Agent Adoption Intensity (Dataset A repo pool)

How Dataset A's whole repo pool splits across agent_adoption_intensity buckets -- bucket *membership*, not the rejection-rate-by-bucket view above. See this module's docstring for the known limitation (bucket label only, no underlying numeric ratio persisted).

### Overall

| Bucket | Repos | % of Dataset A repos |
|---|---|---|
| no_commits | 1,621 | 41.10% |
| experimental | 771 | 19.55% |
| limited | 842 | 21.35% |
| consistent | 554 | 14.05% |
| pervasive | 156 | 3.96% |

### Funnel and adoption intensity by language

Config -> No commits -> adoption tiers, per language -- the exact shape used for the paper's funnel/adoption table. See this function's docstring for exactly what Config/Total mean and how the percentages are computed.

| Language | Agent Configuration Present | No commits | Experimental | Limited | Consistent | Pervasive | Agent Active Total |
|---|---|---|---|---|---|---|---|
| Java | 332 | 150 (45.18%) | 77 (23.19%) | 65 (19.58%) | 33 (9.94%) | 7 (2.11%) | 182 |
| JavaScript | 370 | 184 (49.73%) | 55 (14.86%) | 77 (20.81%) | 44 (11.89%) | 10 (2.70%) | 186 |
| Python | 1,233 | 427 (34.63%) | 217 (17.60%) | 307 (24.90%) | 218 (17.68%) | 64 (5.19%) | 806 |
| TypeScript | 2,009 | 860 (42.81%) | 422 (21.01%) | 393 (19.56%) | 259 (12.89%) | 75 (3.73%) | 1,149 |
| **Total (All Languages)** | 3,944 | 1,621 (41.10%) | 771 (19.55%) | 842 (21.35%) | 554 (14.05%) | 156 (3.96%) | 2,323 |
