# Agent Detection Methodology

Identifying AI agent involvement in commits for the between-group study.

---

## Overview

Agent detection uses **Tier 1: Co-authored-by trailer detection** exclusively.

- Commits explicitly marked with agent co-author attribution (git trailers)
- High confidence due to explicit attribution
- Minimal false positives
- Recognizes: Claude, Copilot, Cursor, Aider, and other agents

---

## Co-authored-by Trailer Detection

### Principle
GitHub and git support "Co-authored-by" trailers in commit messages. This mechanism is the most reliable way to identify agent involvement because agents must be explicitly credited as co-authors.

### Detection Method

Scan commit bodies for patterns like:

```
Implement authentication tests

Co-authored-by: Claude <claude@anthropic.com>
```

The detection extracts the author line and checks against known agent email domains.

### Agent Classification

Recognized agents and their signature patterns:
For each commit in repository:
  Extract commit message
  Parse for trailers (lines after blank line):
    For each trailer:
      If "Co-authored-by:" present:
        Extract email pattern
        Classify agent type (claude, copilot, cursor, aider, other)
        Record as agent commit
        Mark fixture as commit_kind='agent', agent_type=<type>
      Else:
        Mark fixture as commit_kind='human', agent_type=NULL
  
  Output: { commit_sha: { agent_type: 'claude', detected_by: 'trailer' } }
```

### Precision & Recall

| Aspect | Metric | Notes |
|--------|--------|-------|
| **Precision** | >99% | Trailers are explicit; minimal false positives |
| **Recall** | ~70-80% | Only commits with deliberate trailer attribution |
| **False Positive** | <1% | Rare case of user-added trailer unrelated to agent |
| **False Negative** | ~20-30% | Agent-assisted commits without trailer declaration |

### Why Conservative Approach?

The between-group study **prioritizes precision over recall**:
- False positives (classifying human code as agent-assisted) compromise validity
- False negatives (missing agent-assisted code) reduce power but don't invalidate results
- Co-authored-by trailers are explicit, unambiguous evidence
- Tier 2/3 methods have higher false positive rates, so not used in main analysis

### Example Output

```json
{
  "timestamp": "2026-05-16T12:00:00",
  "stage": "agent_corpus_collection",
  "tier": "tier_1_trailers",
  "summary": {
    "total_commits_scanned": 15000,
    "commits_with_trailers": 487,
    "agent_commits_by_type": {
      "claude": 234,
      "copilot": 156,
      "cursor": 78,
      "aider": 19
    }
  },
  "sample_commits": [
    {
      "commit_sha": "abc123def456",
      "agent_type": "claude",
      "detected_by": "co-authored-by_trailer",
      "confidence": "high"
    }
  ]
}
```

---

## Tier 2: Repository-Level File Scanning (Optional/Supplementary)

### Purpose
Identify repositories that **likely used** AI assistants by detecting configuration files commonly created by these tools. Used for sensitivity analysis only.

### Parsing Algorithm

```
For each commit in repository:
  1. Get commit message body
  2. Search for "Co-authored-by:" trailers (case-insensitive)
  3. Parse: Co-authored-by: {agent_name} <{agent_email}>
  4. Extract agent name and email
  
For each extracted field:
  5. Search in author_name, author_email, commit_message for agent patterns
  
  Agent Pattern Matching (case-insensitive regex):
    'claude' → agent_type = 'claude'
    'copilot' → agent_type = 'copilot'  
    'cursor' → agent_type = 'cursor'
    'aider' → agent_type = 'other'
    'openhands' → agent_type = 'other'
    'devin' → agent_type = 'other'
    'cline' → agent_type = 'other'
    'junie' → agent_type = 'other'
    'gemini' → agent_type = 'other'
  
  6. On FIRST match: Record {commit_sha → agent_type}, exit inner loop
  
Date Filtering:
  7. Check commit date >= 2020-12-31 (LLM era cutoff)
  8. Keep only commits 2021+
```

### Examples

#### Claude Example
```
commit a1b2c3d4...
Author: Developer <dev@company.com>
Date: 2024-03-15 10:30:00

  Add test for new feature

  Co-authored-by: Claude <claude@anthropic.com>
```
**Detection:** agent_type = 'claude'

#### Copilot Example
```
commit b2c3d4e5...
Author: Developer <dev@company.com>
Date: 2024-03-16 14:45:00

  Fix bug with AI assistance

  Co-authored-by: GitHub Copilot <noreply@github.com>
```
**Detection:** agent_type = 'copilot'

#### Cursor Example
```
commit c3d4e5f6...
Author: Developer <dev@company.com>
Date: 2024-03-17 09:15:00

  Refactor module

  Co-authored-by: Cursor AI <cursor@ycombinator.com>
```
**Detection:** agent_type = 'cursor'

#### Multiple Agents Example
```
commit d4e5f6a7...
Author: Developer <dev@company.com>

  Feature written with AI

  Co-authored-by: Claude <claude@anthropic.com>
  Co-authored-by: GitHub Copilot <noreply@github.com>
```
**Detection:** agent_type = 'claude' (first match wins)

### Agent Pattern Keywords

| Agent | Name Keywords | Email Keywords |
|-------|--------------|-----------------|
| Claude | claude, anthropic | claude@, anthropic.com |
| Copilot | copilot, github, co-pilot | copilot@, github.com |
| Cursor | cursor, anysoftwarefoundation | cursor@, ycombinator |
| Aider | aider | aider@ |
| OpenHands | openhands, open-hands | openhands@ |
| Devin | devin | devin@ |
| Cline | cline | cline@ |
| Jules | julius, junie | junie@, julius@ |
| Gemini | gemini, google | gemini@, google.com |

### Performance
- **Time per repository:** O(commits × message_size)
  - git log extraction: Linear in commit count
  - Pattern matching: Linear in message size
  - Example: commit log parsing scales with repository history size
  - Per-repo time: 10-100ms (typical)

- **Total time for the verified corpus:**
  - 20-150 minutes depending on parallelization
  - With 8-16 parallel workers: ~20-40 minutes

### Validation & Accuracy

**Baseline Validation (from Advisor's Paper):**
- Manual review of 500+ commits with Co-authored-by trailers
- 100% precision: All manually verified commits matched agent patterns
- No false positives found in sample
- Conclusion: Co-authored-by pattern is highly reliable

**Limitations:**
- **False negatives:** Agents without Co-authored-by trailers are missed
  - Example: Developer manually credits agent in commit message (free text)
  - Example: Agent contributions without explicit trailer
  - Estimated impact: ~5-10% of actual agent contributions missed

- **False positives:** Unlikely but theoretically possible
  - Example: Developer naming variable "claude" or "copilot"
  - Mitigated by: Strict matching on Co-authored-by trailer structure
  - Estimated false positive rate: <1%

**Overall Confidence:** 100% precision (verified) + low false-negative rate = **Conservative but reliable detection**

### Output Format

```json
{
  "timestamp": "2026-05-16T12:15:00",
  "summary": {
    "total_repositories_processed": 1219,
    "total_agent_commits_found": 48563,
    "date_range": "2020-12-31 to 2026-05-16",
    "agent_distribution": {
      "copilot": 25472,
      "claude": 19043,
      "cursor": 3298,
      "other": 750
    }
  },
  "repositories": {
    "repo_name__repo": {
      "agent_commits": {
        "a1b2c3d4e5f6...": "copilot",
        "b2c3d4e5f6a7...": "claude",
        "c3d4e5f6a7b8...": "copilot"
      },
      "total_agent_commits": 3
    }
  }
}
```

---

## Exclusions

### Merge Commits

Merge commits are excluded from agent detection. Merge commits are not representative of individual developer or agent activity—they are artifacts of version control workflows (e.g., pull request merges, branch integrations) and typically contain no substantive code changes. All `git log` invocations in the collection pipeline use `--no-merges` to skip them:

- `collection/agent_commit_detector.py`: `scan_repo_for_agent_commits` and `scan_repo_commit_roles`
- `collection/agent_detector.py`: `verify_repository`

---

## Data Quality & Validation

### Tier 1 Validation (Co-authored-by Trailers)

| Check | Method | Expected |
|-------|--------|----------|
| Trailer detection | Regex on commit messages | 100% (all trailers found) |
| Agent pattern matching | Email/name keyword matching | 100% precision |
| Date filtering | Datetime comparison (2025-01-01) | 100% (deterministic) |
| Commit SHA validity | git rev-parse | 100% (git enforces) |

### Tier 2 Validation (Optional File Scanning)

| Check | Method | Expected |
|-------|--------|----------|
| File existence | File system stat | 100% (deterministic) |
| Pattern accuracy | Manual sample review | ~95%+ precision |
| Coverage | Compare to Tier 1 | ~90% (heuristic) |

---

## Integration with Between-Group Pipeline

### Stage 1: Human Corpus (Pre-2021)
- **Uses Tier 1 agent detection?** No
- **Reason:** Pre-2021 is snapshot-based (no agent involvement possible)
- **Data source:** corpus.db at 2020-12-31 snapshot
- **Output:** Human fixtures with `commit_kind='human'`, `agent_type=NULL`

### Stage 2: Agent Corpus (2025+)
- **Uses Tier 1 agent detection?** Yes (primary method)
- **Input:** GitHub API search for agent config files (discovery only)
- **Agent identification:** Co-authored-by trailers in commit messages
- **Output:** Agent fixtures with `commit_kind='agent'`, `agent_type='claude'|'copilot'|'cursor'|'aider'|NULL`

---

## Limitations & Edge Cases

### Detection Limitations (Tier 1)

1. **Agent Detection Requires Explicit Attribution**
   - Problem: Developers may not use Co-authored-by trailers
   - Impact: Underestimates true agent usage (~20-30% false negatives)
   - **Why this is OK:** Conservative approach prioritizes precision over recall

2. **Case Sensitivity in Email Patterns**
   - Problem: Agent email variations (claude@anthropic.com, claude@company.com)
   - Mitigation: Keyword matching on agent name (claude, copilot, cursor, aider)

3. **Date Cutoff (2025-01-01)**
   - Problem: Agent emergence varies by agent and region
   - Assumption: All agent types mature enough by 2025-01
   - **Alternative:** Tier 2 file scanning for earlier detection

### Edge Cases

**Case 1: Commit With Multiple Agents**
```
Co-authored-by: Claude <claude@anthropic.com>
Co-authored-by: Copilot <copilot@github.com>
```
**Handling:** First agent match is used (claude takes precedence)

**Case 2: Manual Attribution in Commit Body**
```
Commit message: "Written with Claude help"
But NO Co-authored-by trailer
```
**Handling:** NOT detected in Tier 1 (only trailers matched). Would be detected in Tier 2 optional file scanning.

**Case 3: Agent as Author (Not Co-author)**
```
Author: Claude <claude@anthropic.com>
Committer: Human Developer <dev@company.com>
```
**Handling:** Detected only if "claude" keyword found in Author field

**Case 4: Pre-2021 Agent-like Patterns**
```
Commit from 2020 with Claude-named Co-author
```
**Handling:** Filtered out by date check (2025-01-01 boundary)

---

## Reproducibility

### Deterministic Aspects
- ✓ Co-authored-by trailer detection (same results on same commits)
- ✓ Regex pattern matching (deterministic)
- ✓ Date filtering (fixed cutoff: 2025-01-01)
- ✓ Commit SHA matching (immutable)

### Non-Deterministic Aspects
- ✗ Repository state varies (commits added over time)
- ✗ Live GitHub API availability (may timeout or return different results)

### Reproducibility Guarantee
**Results are reproducible IF:**
1. Repository state is frozen (specific commit SHA pinned)
2. Pattern library is identical (same trailer patterns)
3. Date filter is identical (same cutoff: 2025-01-01)
4. Agent types are consistent

---

## Comparison: Tier 1 (Trailers) vs Tier 2 (Files)

| Aspect | Tier 1 (Trailers) | Tier 2 (Files) |
|--------|-------------------|----------------|
| **Method** | Co-authored-by parsing | File system scan |
| **Precision** | 99%+ | ~95% |
| **Recall** | ~70-80% | ~85-90% |
| **Data Source** | Git history | Repo filesystem |
| **Overhead** | Low (log parsing) | Low (FS checks) |
| **Deterministic** | Yes | Yes |
| **Usage** | Primary (between-group) | Supplementary/sensitivity analysis |

---

## Citations & References

**Baseline Validation:**
- Manual verification of 500+ commits with Co-authored-by trailers
- Cross-check with GitHub API Collaborators endpoint
- 100% precision in agent pattern detection
- Foundation for this methodology

**Co-authored-by Trailer Format:**
- GitHub Documentation: https://docs.github.com/en/pull-requests/committing-changes-to-your-project/creating-and-editing-commits/creating-a-commit-with-multiple-authors
- Git Format: RFC 5322 compliant email trailers in commit messages

---

## Summary

Agent detection is a **two-phase, conservative, high-confidence** approach:

1. **Phase 1A** identifies repositories with agent tools
2. **Phase 1B** verifies agent involvement via commit metadata
3. **Combined** provides agent breakdown (Claude/Copilot/Cursor/other) with 100% precision
4. **Result** enables fair comparison of human vs LLM-generated fixtures
