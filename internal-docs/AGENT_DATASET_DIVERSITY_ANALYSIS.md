# Agent Dataset Diversity Analysis & Improvement Strategies

**Date**: May 20, 2026  
**Analysis Focus**: Why the toy agent dataset is heavily skewed (96.5% from 1 repo) and how to improve diversity

---

## Executive Summary

The **toy agent dataset suffers from severe diversity problems** due to:

1. **Limited discovery scope** (only 7 repos found in GitHub API search)
2. **Very restrictive agent detection** (Tier 1: only co-authored-by trailers)
3. **Many repos with agent configs but NO agent commits** (4 of 7 repos failed QC)

| Metric | Value | Impact |
|--------|-------|--------|
| **Repos scanned** | 7 | Too few to ensure diversity |
| **Repos passed QC** | 3 | Only 3 repos had agent commits |
| **Repos failed QC** | 4 | Had agent config files but NO co-authored-by commits |
| **Fixtures collected** | 74* | From only 3 repos |
| **Concentration** | 96.5% from 1 repo (sonarjs) | Extreme skew |
| **Language diversity** | 1 language (TypeScript only) | No Python/Java/Go |
| **Agent type diversity** | 96.7% Claude (66/68 commits) | No copilot/cursor diversity |

*Note: 1606 fixtures in database but only 74 in agent_dataset (see "Toy Dataset" specification below)

---

## Current State: Repos in Agent Dataset

| Repo | Fixtures | Commits | Agent Type | Domain | Language |
|------|----------|---------|-----------|--------|----------|
| **sonarsource/sonarjs** | 70 | 66 | Claude | Other | TypeScript |
| **reactivestack/cookies** | 3 | 1 | Claude | Web | TypeScript |
| **eclipse/che** | 1 | 1 | Claude | Other | TypeScript |
| **TOTAL** | **74** | **68** | — | — | **TypeScript only** |

### Failed QC (Had Agent Configs but NO Agent Commits)

| Repo | Reason | Language |
|------|--------|----------|
| reactnativecn/react-native-pushy | No co-authored-by commits after 2023-06-01 | TypeScript |
| theotherp/nzbhydra2 | No co-authored-by commits after 2023-06-01 | Java |
| martin-majlis/wikipedia-api | No co-authored-by commits after 2023-06-01 | Python |
| liferay/liferay-portal | No co-authored-by commits after 2023-06-01 | Java |

---

## Root Cause Analysis

### Problem 1: Discovery Scope (7 Repos Found)

**Why so few?**

The GitHub code search endpoint searches for 4 specific agent config filenames:
```
.cursorrules
.claude
.cursor
copilot-instructions.md
```

**Issues:**
1. **These are rare in public repos** - Most developers don't commit agent config files
2. **Many agent-using repos have agent configs in `.gitignore`** (for privacy/security)
3. **Not all agent-using repos create explicit config files** - Some use IDE settings instead

**Example**: If a repo uses Claude via IDE plugins but never creates `.claude` file → invisible to search

### Problem 2: Tier 1 Detection Too Restrictive (4 Repos Rejected)

**Filtering Logic:**
```python
co-authored-by Trailer Detection:
  ✓ Requires exact co-authored-by line in commit message
  ✓ Pattern: Co-authored-by: Agent Name <agent@example.com>
  ✓ Only counts commits AFTER 2023-06-01
```

**Why repos were rejected:**
- **reactnativecn/react-native-pushy**: Has `.cursorrules` file (found in search) BUT no commits with co-authored-by trailers
  - Likely reason: Cursor IDE doesn't always auto-add co-authored-by trailers
- **theotherp/nzbhydra2**: Similar pattern (Java repo with agent configs but no trailers)
- **martin-majlis/wikipedia-api**: Python repo, same issue
- **liferay/liferay-portal**: Large Java repo, same issue

**Problem**: Tier 1 detection misses repos where:
- Developers disabled co-authored-by trailers in agent IDE settings
- Agents wrote code but developers removed/modified commit messages
- Agent-assisted code was squashed into commits without preservation of co-authored-by

### Problem 3: Language Imbalance (TypeScript Only)

The search found repos in multiple languages but:
- TypeScript: 7 repos (scanned), 3 passed QC
- Java: 2 repos (scanned), 0 passed QC
- Python: 1 repo (scanned), 0 passed QC

**Why Java/Python repos failed**: No co-authored-by commits in those repos despite having agent config files

---

## Improvement Strategy #1: Expand Agent Config File List

### Current Config Files (Very Limited)
```python
AGENT_CONFIG_FILES = [
    ".cursorrules",      # Cursor-specific
    ".claude",           # Claude (unofficial convention)
    ".cursor",           # Cursor (alternative)
    "copilot-instructions.md",  # Copilot-specific
]
```

### Recommended Additions
```python
# IDE Settings & Config Files (often in .git-ignored .vscode/.cursor directories)
".vscode/settings.json"  # VS Code with Copilot extension settings
".idea/workspace.xml"    # IntelliJ with Copilot extension
".vscode/extensions.json"  # Lists VS Code extensions (Copilot detection)

# Agent-generated markers (often commit hooks or config)
".aider.conf"            # Aider configuration
"aider.history"          # Aider session history
".github/workflows/aider*"  # GitHub Actions workflows with Aider

# Generic AI Assistant Configs
"claude.json"            # Alternative Claude config
"cursor-config.json"     # Alternative Cursor config
"ai-config.json"         # Generic AI config

# Fallback: Search by dependency instead
# (See Strategy #3 below)
```

**Estimated impact**: Could find 2-3x more repos with agent configs

---

## Improvement Strategy #2: Relax Tier 1 Detection (Infer Agent Usage)

### Current: Strict Co-Authored-By Trailers Only
```
co-authored-by: Claude <claude@anthropic.com>
```

### Proposed Tier 1b: Commit Message Pattern Matching

If co-authored-by trailer not found, check for agent attribution patterns:

```python
AGENT_SIGNATURE_PATTERNS = {
    "claude": [
        r"(?i)(written with|using|generated by)\s+(claude|anthropic)",
        r"(?i)claude-assisted",
        r"(?i)with copilot",
    ],
    "copilot": [
        r"(?i)(copilot|GitHub Copilot)\s+(generated|suggested)",
        r"(?i)copilot-assisted",
        r"(?i)with copilot",
    ],
    "cursor": [
        r"(?i)(cursor|cursor-ai)\s+(generated|suggested)",
        r"(?i)using cursor",
    ],
    "aider": [
        r"(?i)aider:\s+",
        r"(?i)aider-generated",
    ],
}
```

**Estimated impact**: Could recover 30-50% of rejected repos (e.g., reactnativecn/react-native-pushy)

---

## Improvement Strategy #3: Reverse Engineer via Dependencies

### Idea: Search for Agent SDK Dependencies in package.json/pyproject.toml

**For repos WITHOUT explicit agent config files**, detect agent usage via:

1. **Python/Node.js**: Agent library imports in requirements/package.json
   ```python
   # pyproject.toml
   dependencies = ["anthropic==...", "openai==...", "aider==..."]
   
   # package.json
   dependencies: {"@anthropic-ai/sdk": "...", "@openai/sdk": "..."}
   ```

2. **GitHub Actions**: Workflows that call agent APIs
   ```yaml
   # .github/workflows/ai-assisted-*.yml
   run: aider --check
   ```

3. **Environment Variables in Commits**: Detect API key references
   ```bash
   # In commit diffs
   +export ANTHROPIC_API_KEY="..."
   ```

**Estimated impact**: Could find 5-10x more repos with agent-assisted code

**Challenges:**
- Higher false positive rate (repos with agent SDK but not for test fixtures)
- Requires code analysis beyond filenames
- May take longer (need to clone & parse files)

---

## Improvement Strategy #4: Explicit Agent-Assisted Repositories Lists

### Create Curated Lists of Known Agent-Using Projects

1. **Research community**: Search academic papers/papers for agent-assisted code repos
2. **Company repositories**: Anthropic, OpenAI, Cursor official repos + partners
3. **GitHub Topics**: Search repos tagged with ["ai-generated", "cursor-ai", "claude-generated"]
4. **Reddit/HN**: Mine discussions about "agent-assisted code" projects

**Example queries**:
```
language:python topic:claude-generated
language:typescript topic:cursor-ai
language:java topic:ai-assisted-tests
organization:anthropic
organization:openai
```

**Estimated impact**: Could find 20-50 additional high-quality repos with explicit agent usage

---

## Improvement Strategy #5: Decoupled Agent Detection Tiers

Instead of failing repos that have agent configs but no co-authored-by trailers, create TIERED acceptance:

### Proposed Tier System

```python
class AgentDetectionTier(Enum):
    TIER_1_EXPLICIT = "co-authored-by_trailer"          # Most confident
    TIER_1B_INFERRED = "commit_message_pattern"         # High confidence
    TIER_2_CONFIG = "agent_config_present"              # Medium confidence
    TIER_3_DEPENDENCY = "agent_sdk_dependency"          # Low-medium confidence
    TIER_4_HEURISTIC = "commit_author_+_test_changes"   # Low confidence
```

**For toy dataset**: Mix tiers to improve diversity:
- **Tier 1 (2-3 repos)**: High-confidence agent commits (sonarjs, cookies, che)
- **Tier 1b (1-2 repos)**: Inferred from message patterns (reactnativecn, nzbhydra2)
- **Tier 2 (2-3 repos)**: Config file present, manually inspected (martin-majlis, liferay)

**Benefit**: Maintains confidence hierarchy while expanding diversity

---

## Improvement Strategy #6: Stratified Sampling

Instead of taking "first N per language," stratify by:

1. **Agent Type Distribution**
   ```python
   # Current: 96.7% Claude
   # Target: 50% Claude, 25% Copilot, 15% Cursor, 10% Aider
   ```

2. **Repo Size**
   ```python
   # Current: 1 large repo (sonarjs ~500 commits)
   # Target: 1 large, 3-4 medium, 2-3 small
   ```

3. **Language Diversity**
   ```python
   # Current: TypeScript only
   # Target: 40% TypeScript, 30% Python, 20% Java, 10% Go
   ```

4. **Domain Diversity**
   ```python
   # Current: Mostly "other"
   # Target: 40% web, 30% other, 20% data/ml, 10% devops
   ```

**Implementation**:
```python
def stratified_sample_agent_repos(
    repos: List[Dict],
    target_size: int = 50,
    agent_type_weights: Dict[str, float] = None,
    language_weights: Dict[str, float] = None,
) -> List[Dict]:
    """Sample repos ensuring diversity across dimensions."""
```

---

## Recommended Action Plan (Priority Order)

### Phase 1: Quick Wins (1-2 hours)
1. **Add 5-10 new config file patterns** (Strategy #1)
   - `.vscode/extensions.json`, `aider.conf`, `claude.json`
   - Rerun GitHub API search
   - Expected: Find 10-20 additional repos

2. **Implement co-authored-by pattern fallback** (Strategy #2)
   - Check for "Claude-assisted", "with Copilot" in commit messages
   - Recover rejected repos like reactnativecn/react-native-pushy
   - Expected: 2-4 additional repos pass QC

### Phase 2: Medium Effort (3-4 hours)
3. **Implement dependency-based detection** (Strategy #3)
   - Parse package.json for @anthropic-ai/sdk, @openai/sdk
   - Parse requirements.txt for anthropic, openai packages
   - Expected: 5-10x more repos discovered

4. **Implement tiered acceptance** (Strategy #5)
   - Allow TIER_1b and TIER_2 repos in toy dataset
   - Filter by quality/agent confidence
   - Expected: Better diversity without sacrificing confidence

### Phase 3: Long-term (1-2 days)
5. **Curated repository lists** (Strategy #4)
   - Search academic papers, GitHub topics
   - Manual validation of promising repos
   - Expected: 20-50 high-quality repos

6. **Stratified sampling** (Strategy #6)
   - Balance agent types, languages, domains
   - Build improved toy dataset with diversity constraints
   - Expected: Balanced representation across all dimensions

---

## Quantified Impact Projections

### Current Toy Dataset
- **Scanned**: 7 repos
- **Passed QC**: 3 repos  
- **Fixtures**: 74
- **Concentration**: 96.5% from 1 repo
- **Languages**: 1 (TypeScript only)
- **Agent Types**: 1 (96.7% Claude)

### After Strategy #1 + #2 (Quick Wins)
- **Scanned**: ~15-20 repos
- **Passed QC**: ~8-12 repos
- **Fixtures**: ~200-300 (3-4x increase)
- **Concentration**: ~30-40% from sonarjs (much better)
- **Languages**: 2-3 (TypeScript + Python + Java)
- **Agent Types**: 2-3 (Mix of Claude/Copilot/Cursor)

### After Full Implementation (Strategies #1-6)
- **Scanned**: ~50-100 repos (full stratification)
- **Passed QC**: ~40-60 repos
- **Fixtures**: ~500-1000 (6-13x increase)
- **Concentration**: <20% from any single repo
- **Languages**: All 4 (Python, TypeScript, Java, Go equally represented)
- **Agent Types**: Balanced across Claude, Copilot, Cursor, Aider
- **Domains**: Balanced across web, other, data/ml, devops

---

## Key Questions for Next Steps

1. **What's the PRIMARY goal for the toy dataset?**
   - Maximize diversity for research? → Implement Strategies #1-6
   - Quick demo with highest-quality agent code? → Implement Strategies #1-2 only
   - Understand agent behavior across types? → Implement Strategies #1-5

2. **How confident do we want to be in "agent" attribution?**
   - High confidence (Tier 1 co-authored-by only)? → Keep current, add #1-2
   - Medium confidence (allow Tier 1b inference)? → Add #2, #5
   - Exploratory (include Tier 2-3 with caveats)? → Add #5

3. **What's the TIME constraint?**
   - <4 hours? → Do Phase 1 (Strategies #1-2)
   - 1-2 days? → Do Phases 1-2 (Strategies #1-5)
   - 1 week? → Do all phases (Strategies #1-6)

---

## Files to Modify

1. **collection/config.py**
   - Expand `AGENT_CONFIG_FILES` (Strategy #1)
   - Add `AGENT_SIGNATURE_PATTERNS` (Strategy #2)

2. **collection/agent_corpus.py**
   - Modify `detect_agent_type()` to accept Tier 1b patterns (Strategy #2)
   - Add tier-based acceptance logic (Strategy #5)

3. **collection/github_api_search.py**
   - Add dependency-based search function (Strategy #3)
   - Implement curated list search (Strategy #4)

4. **collection/fixture_extractor.py**
   - Add stratified sampling function (Strategy #6)

---

## Summary

**The toy agent dataset is NOT broken, but severely limited by:**
- Narrow discovery scope (config filenames only)
- Strict agent detection (co-authored-by trailers only)
- Single-repo dominance (sonarjs = 96.5%)

**Quick wins (#1-2) can 3-4x the dataset diversity in 1-2 hours.**  
**Full implementation (#1-6) can 6-13x the dataset and balance across all dimensions in 1-2 days.**

**Recommendation**: Start with Strategies #1-2 (quick) to prove concept, then evaluate whether #3-6 are needed based on research goals.
