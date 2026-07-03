# Commit Noise Filtering — Gaps & Improvements

**Date**: 2026-07-03
**Context**: Advisor review identified that our commit filtering is less complete than the reference paper's methodology. This document captures the current state, gaps, and proposed improvements.

---

## 1. Current filtering (what we have)

| Filter | Mechanism | Location |
|--------|-----------|----------|
| Merge commits | `only_no_merge=True` in PyDriller `Repository()` call | `agent_commit_detector.py` lines 180, 229; `agent_detector.py` line 531 |
| Bot commits | `"[bot]" in author_name.lower()` → returns `"bot"` → skipped in caller | `agent_commit_detector.py` line 283 (`_detect_agent_in_commit`); `agent_corpus.py` line 114 (`detect_agent_in_commit`) |

Both `scan_repo_for_agent_commits()` and `scan_repo_commit_roles()` in `agent_commit_detector.py` apply these filters during PyDriller traversal.

---

## 2. Gaps identified

### 2.1 Bump-version release commits (advisor's main concern)

**Problem**: Automated commits that increment version numbers (e.g., `bump version to 2.1.0`) are often authored by CI bots — sometimes *without* `[bot]` in the author name. They can touch test files (updating version strings in assertions like `assert version == "1.2.3"`) and look like fixture modifications to our extractor, but are actually just mechanical version string updates.

**No filtering currently exists for these.**

#### Proposed detection patterns

All checks against the first line (subject) of the commit message, case-insensitive:

| Pattern | Regex / heuristic | Example matches |
|---------|-------------------|-----------------|
| `bump version` | `r"^bump\s+(version\s+)?v?\d"` | `bump version to 2.1.0`, `bump v2.1.0`, `bump 2.1.0` |
| `chore(release)` | `r"^chore\(release\)"` | `chore(release): v1.2.3`, `chore(release): prepare 2.0.0` |
| `release v` | `r"^release\s+v?\d"` | `release v1.0.0`, `release 1.0.0` |
| `prepare release` | `r"^prepare\s+release"` | `prepare release v2.0`, `prepare release 2.0.0` |
| Version-only subject | `r"^v?\d+\.\d+\.\d+$"` | `v1.2.3`, `1.2.3` |
| `chore: bump` | `r"^chore:\s*bump"` | `chore: bump version`, `chore: bump` |
| `[release]` | `r"\[release\]"` | `[release] v1.0.0`, `[release] 2.0` |
| `chore(version)` | `r"^chore\(version\)"` | `chore(version): bump to 1.0.0` |

#### Implementation approach

Add `is_bump_commit(commit_message: str) -> bool` in `agent_commit_detector.py`. Check the first line of the commit message against a compiled regex. Skip in both `scan_repo_for_agent_commits()` and `scan_repo_commit_roles()` — same pattern as bot commit skipping.

#### Open questions

1. **Scope**: Skip bump commits from agent detection only, or from human classification too? Recommendation: both — a bump commit isn't a meaningful human fixture source either.
2. **File-based heuristics**: Should we also check that the commit *only* touches version/config files (e.g., `package.json`, `setup.cfg`, `pyproject.toml`, `CHANGELOG.md`)? Message-only is simpler and catches the vast majority. File-based would be more precise but adds complexity and requires repo access during filtering.
3. **False positive risk**: A commit with subject `bump version to 2.1.0` that also contains real fixture changes would be incorrectly skipped. How common is this? Unknown — would need empirical sampling.

---

### 2.2 Revert commits (advisor mentioned we filter these — we don't)

**Problem**: The advisor's reference paper explicitly filters revert commits. Git revert commits have the standard format `Revert "original commit message"`. These are mechanical undo operations that don't represent meaningful new code.

**No filtering currently exists for these.**

#### Proposed detection

```python
_REVERT_RE = re.compile(r'^Revert\s+"', re.IGNORECASE)
```

Check the first line of the commit subject. Standard git revert format always starts with `Revert "`.

#### Implementation

Same approach as bump commits — add `is_revert_commit()` and skip in both scan methods.

---

### 2.3 Other housekeeping commits (stretch goal)

The advisor mentioned "other housekeeping changes." Beyond bumps and reverts, potential categories:

| Type | Pattern | Risk |
|------|---------|------|
| `chore(deps)` | `chore(deps): update ...` | Dependabot/Renovate — usually already caught by `[bot]` check |
| `ci:` / `ci(` | `ci: update workflow` | CI config changes, unlikely to touch test fixtures |
| `docs:` / `docs(` | `docs: update README` | Documentation only, very low risk |
| `style:` / `style(` | `style: format with black` | Formatting-only changes |

These are lower priority — they rarely touch test fixtures in ways that would confuse our extractor. The `[bot]` check already catches most dependabot/renovate commits.

---

## 3. Where filtering happens (all locations)

| File | Method | What it does |
|------|--------|-------------|
| `collection/agent_commit_detector.py` | `scan_repo_for_agent_commits()` | PyDriller traversal, finds agent commits only |
| `collection/agent_commit_detector.py` | `scan_repo_commit_roles()` | PyDriller traversal, classifies ALL commits as agent/human |
| `collection/agent_commit_detector.py` | `_detect_agent_in_commit()` | Bot check + agent signature matching |
| `collection/agent_corpus.py` | `detect_agent_in_commit()` | Standalone version of agent detection (duplicated logic) |
| `collection/agent_detector.py` | `AgentCommitVerifier.verify_repository()` | Another PyDriller traversal for verification |
| `collection/agent_detector.py` | `AgentCommitVerifier._detect_agent_in_commit()` | Bot check + agent signature matching (third copy) |

**Note**: There are three separate implementations of agent detection logic across the codebase. Any new filter needs to be added to all of them, or the logic should be consolidated first.

---

## 4. Recommended implementation order

1. **Consolidate commit filtering** into a single module (e.g., `collection/commit_filter.py`) with functions:
   - `is_bot_commit(author_name) -> bool`
   - `is_bump_commit(message) -> bool`
   - `is_revert_commit(message) -> bool`
   - `is_noise_commit(author_name, message) -> bool` (combines all three)

2. **Add bump commit detection** with the regex patterns above.

3. **Add revert commit detection**.

4. **Update all three traversal sites** to use the consolidated filter.

5. **Unit tests** for each filter function with real-world examples.

6. **Empirical validation**: Run on a sample of repos, count how many commits each filter catches, manually inspect a random sample to estimate false positive rate.

---

## 5. Related files

| File | Relevance |
|------|-----------|
| `collection/agent_commit_detector.py` | Main commit scanning — `scan_repo_for_agent_commits`, `scan_repo_commit_roles`, `_detect_agent_in_commit` |
| `collection/agent_corpus.py` | `detect_agent_in_commit` (duplicate), `get_agent_commits` |
| `collection/agent_detector.py` | `AgentCommitVerifier.verify_repository`, `_detect_agent_in_commit` (third copy) |
| `collection/utils.py` | `AGENT_TRAILER_RE` — the agent trailer regex |
| `collection/config.py` | `AGENT_CORPUS_START_DATE`, `AGENT_SIGNATURES` |
| `tests/test_agent_detector_pure.py` | Existing tests for agent detection |
| `tests/collection/test_two_tier_agent_collection.py` | Existing tests for two-tier agent collection |