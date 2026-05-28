# Pseudocode vs Implementation Analysis

## Executive Summary

The current **paired within-repository** design is **methodologically superior** to the pseudocode's two-corpus split, but the pseudocode contains several critical **data collection and validation practices** we should adopt.

---

## 1. Methodological Superiority: Paired vs Split Design

### Current Implementation (Paired Within-Repo) ✅ BETTER

**Strengths:**
- Compares agent commits against non-agent commits **in the same repository**
- Controls for project-specific confounds (domain, language, team conventions, codebase maturity)
- Statistical validity via paired tests (paired t-test, paired Wilcoxon, Cliff's delta)
- Addresses the core question: "Do fixtures change when agents write them?"

**Why split design is weaker:**
- Pseudocode tries to compare two disjoint populations (human repos vs agent repos)
- Inherent confounding: repos with agent activity differ systematically from pre-agent repos
  - Recency: agent repos are newer (2025+) → different testing practices
  - Selection bias: repos that adopt agents may differ in quality/maturity
  - Domain drift: different project types may adopt agents at different rates
- Requires extensive covariate control (domain, stars, age, contributors) to be even remotely valid
- Still cannot control for unmeasured confounds (team skill, development culture, etc.)

**Paired design avoids all of this.** Within the same repo, you control for project confounds automatically.

---

## 2. Critical Gaps: Improvements to Adopt from Pseudocode

### Gap 1: Control Variables Collection (Phase 3)

**Current state:** Not systematically implemented.

**Pseudocode requirement:**
```
repo.domain          = classify_domain(repo.topics, repo.description)
repo.star_tier       = "core" IF repo.stars >= 500 ELSE "extended"
repo.repo_age        = (collection_date - repo.created_at).years
repo.contributors    = github_api.get_contributor_count(repo)
```

**Why it matters for paired design:**
- Even in paired comparisons, **report these by repository**
- Example output: "Repository X (Python, domain=web, stars=2500, age=8yr, 150 contributors)"
- If patterns differ by domain/tier/age within pairs, **note it for readers**
- Helps interpret whether findings generalize across project types

**Action:**
- ✅ Add control variable collection to `paired_collection.py`
- Store domain, star_tier, repo_age, contributor_count in `commit_observations` table
- Include in paired-study summary JSON

---

### Gap 2: Explicit Quality Filters (MIN_COMMITS, MIN_TEST_FILES)

**Current state:** Repository discovery happens via SEART, but no explicit validation that sampled repos meet quality thresholds.

**Pseudocode requirement:**
```
MIN_COMMITS     = 100
MIN_TEST_FILES  = 5

IF count_commits(repo) < MIN_COMMITS     → mark SKIPPED, continue
IF count_test_files(repo) < MIN_TEST_FILES → mark SKIPPED, continue
```

**Why it matters:**
- Ensures repos are "real projects," not toy repos or stubs
- Excludes small tutorial repos or abandoned projects
- Makes the dataset reproducible and defendable

**Action:**
- ✅ Add quality checks to `paired_collection.py` before sampling commits
- Count total commits and test files during repository scan
- Skip repositories that don't meet thresholds
- Report counts in paired-study summary (N repos total, N repos passing QC, skip reasons)

---

### Gap 3: Statistical Balance Checking (Phase 4)

**Current state:** No formal statistical testing for balance.

**Pseudocode requirement:**
```
FOR each dimension IN [language, domain, star_tier]:
    human_dist = distribution(human_repos, dimension)
    agent_dist = distribution(agent_repos, dimension)
    p_value    = chi_square_test(human_dist, agent_dist)
    
    IF p_value < 0.05:
        LOG "Imbalance detected on {dimension} — report as limitation"
```

**Adapted to paired design:**
- Compare distributions of **agent commits vs non-agent commits** per language and domain
- Example: "Are agent fixtures equally distributed across Python and Java?"
- Example: "Do web-domain repos have more agent fixtures than systems-domain repos?"
- If imbalanced, document it and note as limitation

**Action:**
- ✅ Add balance checking to `paired_collection.py` post-collection
- Compute chi-square test: language, domain distributions (agent vs non-agent commits)
- Report p-values in paired-study summary
- Mark dimensions with p < 0.05 as requiring interpretation care

---

### Gap 4: Agent Detection Precision (Multiple Signals)

**Current state:** Uses GitHub API pre-filtering for config files + commit message/co-author parsing.

**Pseudocode requirement:**
```
AGENT_SIGNATURES = ["claude", "cursor", "copilot", "co-authored-by"]
AGENT_CONFIG_FILES = ["CLAUDE.md", ".claude/", ".cursor/",
                      "copilot-instructions.md", ".cursorrules"]

FUNCTION has_agent_signature(commit):
    message_lower = commit.message.lower()
    FOR each sig IN AGENT_SIGNATURES:
        IF sig IN message_lower: RETURN true
    FOR each author IN commit.co_authors:
        IF any(sig IN author.name.lower() FOR sig IN ["claude","cursor","copilot"]):
            RETURN true
    RETURN false
```

**Current vs pseudocode:**
| Signal | Current | Pseudocode |
|--------|---------|-----------|
| Commit message signatures | ✅ Yes | ✅ Yes |
| Co-author parsing | ✅ Yes | ✅ Yes |
| Config file presence (pre-filter) | ✅ Yes (API) | ✅ Yes |
| Config file presence (repo-level check) | ❓ Partial | ✅ Yes |

**Action:**
- ✅ Ensure `agent_detector.py` checks **all** AGENT_CONFIG_FILES
- Current list: CLAUDE.md, .claude/, .cursor/, copilot-instructions.md, .cursorrules
- Add any missing: .aider/, .devin/, .openhands/ (if emerging)
- Document which signals each commit matched in the observation

---

### Gap 5: Diff-Level Fixture Extraction Precision

**Current state:** Extracts fixtures from commit, but unclear if attribution is limited to added lines.

**Pseudocode requirement:**
```
added_lines = get_added_lines(modified_file)
new_fixtures = detect_fixtures_in_diff(
    added_lines,
    full_file_after = modified_file.source_code_after,
    language = language
)
RETURN [f FOR f IN all_fixtures IF f.start_line IN new_line_nums]
```

**Why it matters:**
- A commit that modifies an existing fixture should **not** be attributed entirely to the agent
- Only fixtures whose **start line appears in the diff** should be counted
- Avoids misattribution of inherited/pre-existing fixtures

**Current implementation:**
- `fixture_extractor.py` calls `extract_fixtures()` at a commit snapshot
- Check if it filters by added lines only, or includes pre-existing fixtures

**Action:**
- ✅ Verify `extract_fixtures_at_commit()` uses diff-level precision
- When extracting at commit SHA, cross-reference added lines from `git diff`
- Only count fixtures whose start_line is in the set of added lines
- Add `is_newly_added` flag to fixture record for transparency

---

### Gap 6: Agent Type Breakdown and Reporting

**Current state:** Labels fixtures by tier (1/2) but not by agent type (claude/copilot/cursor/other).

**Pseudocode requirement:**
```
FUNCTION detect_agent_name(commit):
    IF "claude"  IN commit.message.lower(): RETURN "claude"
    IF "cursor"  IN commit.message.lower(): RETURN "cursor"
    IF "copilot" IN commit.message.lower(): RETURN "copilot"
    RETURN "other"

fixture.agent_name = detect_agent_name(commit)
```

**Why it matters:**
- Different agents may produce different fixture patterns
- Enables sub-analyses: "Do Claude fixtures differ from Copilot fixtures?"
- Readers want to know which agent generated what

**Action:**
- ✅ Extend `agent_detector.py` to label commits by agent type
- Parse commit message and co-author names
- Store agent_type (claude/copilot/cursor/aider/github-copilot/other) in fixtures
- Report agent-type distribution in paired-study summary

---

### Gap 7: Comprehensive Reporting & Transparency

**Current state:** Paired-study summary exists but may lack granular breakdowns.

**Pseudocode requirement (Phase 4):**
```
REPORT:
    human_corpus:  N repos, M fixture definitions, per-language breakdown
    agent_corpus:  N repos, M fixture definitions, per-language breakdown
    imbalanced_on: [list of dimensions requiring covariate control]
```

**Adapted to paired design, the summary should include:**

```json
{
  "summary": {
    "total_repos_sampled": 50,
    "repos_passing_qc": 48,
    "skipped_repos": 2,
    "skip_reasons": {
      "insufficient_commits": 1,
      "insufficient_test_files": 1
    },
    "total_commit_pairs": 240
  },
  "by_language": {
    "python": {
      "repos": 10,
      "agent_commits": 45,
      "non_agent_commits": 145,
      "agent_fixtures": 320,
      "non_agent_fixtures": 890
    },
    ...
  },
  "by_domain": {
    "web": {...},
    "systems": {...},
    ...
  },
  "balance_tests": {
    "language_distribution": {
      "chi_square": 1.23,
      "p_value": 0.87,
      "status": "balanced"
    },
    "domain_distribution": {
      "chi_square": 3.45,
      "p_value": 0.18,
      "status": "balanced"
    }
  },
  "agent_type_breakdown": {
    "claude": 125,
    "copilot": 98,
    "cursor": 32,
    "other": 15
  },
  "control_variables": {
    "mean_repo_age_years": 6.2,
    "mean_contributors": 87,
    "star_tier_distribution": {
      "core": 35,
      "extended": 13
    }
  }
}
```

**Action:**
- ✅ Enhance `paired_study_summary_*.json` to include all above fields
- Makes the study fully transparent and defensible

---

## 3. Summary of Recommended Improvements

| Aspect | Current | Gap | Priority | Action |
|--------|---------|-----|----------|--------|
| **Design** | Paired | None | ✅ | Keep—superior to split |
| **Control vars** | Missing | Major | 🔴 HIGH | Collect domain, star_tier, age, contributors |
| **Quality filters** | Implicit | Major | 🔴 HIGH | Explicit MIN_COMMITS=100, MIN_TEST_FILES=5 |
| **Balance testing** | Missing | Major | 🔴 HIGH | Chi-square tests on language, domain |
| **Agent detection** | Good | Minor | 🟡 MED | Ensure all config files checked; label agent type |
| **Diff precision** | Unclear | Medium | 🟡 MED | Verify added-lines-only attribution |
| **Reporting** | Basic | Major | 🔴 HIGH | Full granular breakdown + balance stats |

---

## 4. Implementation Roadmap

1. **Phase A (Immediate):** Control variables + quality filters
   - Add `collect_controls()` equivalent in `paired_collection.py`
   - Add quality-gate checks before commit sampling
   - Update summary JSON schema

2. **Phase B (Short-term):** Balance checking & agent type labeling
   - Implement chi-square tests in summary generation
   - Extend agent detection to label agent type
   - Update fixtures table to include agent_name

3. **Phase C (Documentation):** Reporting & transparency
   - Rewrite paired-study summary with all recommended fields
   - Document methodology assumptions & limitations
   - Include balance test results in output

---

## Conclusion

The current **paired design is methodologically sound and superior** to the pseudocode's split approach. However, adopting the pseudocode's **data collection rigor, quality filters, statistical testing, and comprehensive reporting** will make the study much stronger, more defensible, and easier for readers to trust.

The improvements are not about changing the core design—they're about **transparency and statistical rigor**.
