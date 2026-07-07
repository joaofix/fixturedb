# Agent Detection Methodology

Identifying AI coding agent involvement in commits for the between-group study.

**Module layering**: `collection/agent_patterns.py` holds the shared, low-level
matching primitives (`match_agent_keyword()`, `path_matches_pattern()`,
`repo_contains_patterns()`) and loads the agent catalog from
[`collection/heuristics/agent_heuristics.yaml`](../../collection/heuristics/agent_heuristics.yaml).
`collection/agent_signal_primitives.py` builds single-repo detection blocks on
top of those primitives (config-file scanning, commit-trailer verification).
`collection/tiered_agent_corpus_scanner.py` is the corpus-scale orchestrator
and the actual pipeline entry point for both tiers below.

---

## Tier 1: Author Metadata + Co-authored-by Trailers (primary method)

Used for Dataset A (the between-group study's main agent corpus). Checked in order, first match wins:

1. **Author metadata** — the commit's `Author` name + email checked against the `commit_signatures` catalog (some tools set themselves as the primary author).
2. **Co-authored-by trailers** — the commit body is scanned for `Co-authored-by:`, `Assisted-by:`, `Generated-by:` lines (case-insensitive); the trailer value is checked the same way.

Matching is **word-boundary-based** (`agent_patterns.py::match_agent_keyword()`), not a bare substring check — this rules out a keyword matching inside an unrelated compound word (e.g. "cline" no longer matches inside "McLine"). It does **not** rule out an exact whole-word collision with a common name (see "Known Limitations" below).

Implementation: `Tier1RepositoryScanner._detect_agent_in_commit()` in `tiered_agent_corpus_scanner.py`.

### Why this design

The study prioritizes precision over recall for the main analysis: a false positive (classifying human code as agent-assisted) threatens validity more than a false negative (an uncredited agent commit just reduces statistical power). Explicit `Co-authored-by` trailers and matched author identity are the most constrained, deliberate signal available; free-text commit-message scanning is deliberately **not** used for this reason (see "Known Limitations").

### Pure-Addition Filter for Test Files

Identifying an agent-authored commit isn't sufficient on its own — a commit could still mix agent-added fixtures with human-edited test code. The pipeline additionally requires that a fixture's own diff span be **100% newly added**, never modified, via two gates:

- **Commit-level**: if any test file in the commit has a deletion, rename, or copy, the whole commit is rejected.
- **File-level**: within an accepted commit, each fixture's own line span (preferring an AST-node-precise check, falling back to a line-range check) must consist exclusively of added lines.

Implementation: `collection/diff_purity.py` (`_raw_diff_commit_is_pure_addition()`, `_raw_diff_file_is_pure_addition()`), `collection/agent_fixture_extractor.py` (`_is_fixture_completely_added()`, `_build_diff_line_maps()`). Tests: `tests/collection/test_fixture_extractor_partial_detection.py`, `tests/test_fixture_extractor_small.py`.

**Example — accepted (pure addition):**
```diff
diff --git a/tests/test_new_feature.py b/tests/test_new_feature.py
new file mode 100644
--- /dev/null
+++ b/tests/test_new_feature.py
@@ -0,0 +1,5 @@
+import pytest
+
+@pytest.fixture
+def new_feature_fixture():
+    return "agent_generated"
```

**Example — rejected (contains a deletion):**
```diff
diff --git a/tests/test_existing.py b/tests/test_existing.py
--- a/tests/test_existing.py
+++ b/tests/test_existing.py
@@ -3,7 +3,7 @@
 import pytest

 @pytest.fixture
-def old_fixture():
+def renamed_fixture():
     return 42
```

---

## Tier 2: Repository Discovery via Config Files (supplementary)

Used to discover *additional* candidate repositories beyond Dataset A's existing corpus, for sensitivity analysis — not part of the main between-group comparison.

1. **GitHub API pre-filter** (`GitHubAgentFileChecker`) — cheap Contents-API check for known agent config files/directories (`CLAUDE.md`, `.cursorrules`, `.claude/`, etc.), before cloning anything.
2. **Local file scan** (`AgentFileScanner`) — after cloning a candidate, re-confirms agent config files are present in the actual working tree, walking the tree with `os.walk` while pruning `.git/`, `node_modules/`, `vendor/`, `build/`, `dist/`, and similar dependency/artifact directories (both to avoid false positives from a vendored dependency's own config file, and to avoid the wasted I/O of walking `.git`'s internal objects).
3. **Commit verification** (`AgentCommitVerifier`) — once a repo passes both file checks, its commits are checked the same way as Tier 1 (word-boundary match against author identity and trailers — **not** the free-text commit message body; see "Known Limitations").

Implementation: `Tier2RepoMatcher` in `tiered_agent_corpus_scanner.py`, delegating to `GitHubAgentFileChecker`/`AgentFileScanner`/`AgentCommitVerifier` in `agent_signal_primitives.py`.

The full, current catalog of recognized agents and their config-file/commit-signature patterns lives in [`collection/heuristics/agent_heuristics.yaml`](../../collection/heuristics/agent_heuristics.yaml), not duplicated here — the catalog of coding agents grows faster than any doc can track, so the YAML is the single source of truth. Adding or updating an agent is a data change, not a code change.

---

## Exclusions

**Merge commits** are excluded everywhere — they're version-control artifacts (PR merges, branch integration), not individual developer or agent activity. All `git log` invocations in this pipeline use `--no-merges`.

**Bot accounts** (author name containing `[bot]`, e.g. `copilot-swe-agent[bot]`) are classified separately (`"bot"`), not attributed to a specific coding agent — a repo's own CI/automation bots are a different thing from an interactive coding assistant.

---

## Known Limitations

**Name/word collisions in author-identity matching.** Several agent signatures (`devin`, `jules`, `claude`, `cline`, `cursor`, `gemini`, `windsurf`) are also common human first names or ordinary English words. Word-boundary matching (added after an audit this session) rules out a keyword matching inside an unrelated compound word or surname (e.g. "cline" no longer matches inside "McLine"), but it cannot rule out an exact whole-word collision — a commit author literally named "Devin Smith" is still misattributed to the Devin agent. This is a fundamental limit of text-only heuristics on a freely-editable author-name field, not something a smarter regex closes; there's no verified, universal bot-email-domain convention across these tools to fall back on instead. If false-positive rate matters for a specific analysis, prefer commits verified via the `Co-authored-by` trailer path over bare author-name matches, or manually spot-check via `collection/validation_sampling.py`. (Documented in `agent_heuristics.yaml`'s module comment too.)

**Free-text commit messages are not scanned.** Only structured fields (author name/email, trailer lines) are checked. An audit this session found that scanning the full commit-message body for agent keywords produced real false positives — e.g. "Revert a bad Claude suggestion" (prose mention, no real attribution) and "Fix cursor blinking bug" (an unrelated UI element, not the Cursor agent) — so this path was removed rather than kept as a broader-recall option.

**Explicit attribution required.** An agent-assisted commit with no trailer and no agent-identity author is not detected at all (Tier 1) — this is a deliberate false-negative tradeoff for precision, not a bug. Tier 2's file-presence check is a coarser, supplementary signal for exactly this reason and is not used for the main comparison.

**Date cutoff (`AGENT_CORPUS_START_DATE`, 2025-01-01).** Chosen as a window where all catalogued agents are assumed mature enough to detect; commits before this date are excluded from Dataset A regardless of any agent signal they might carry.

---

## Reproducibility

Detection is fully deterministic given a pinned commit SHA: the same repository state, pattern catalog, and date cutoff always produce the same classification. The only non-deterministic inputs are external — repository state changing over time (new commits), and live GitHub API availability during Tier 2 discovery.

---

## See Also

- [Fixture Detection Logic](detection.md) — how fixtures themselves are found and measured (a separate concern from *who* authored the commit)
- [Manual-Validation Sampling](../usage/validation-sampling.md) — drawing a review sample to spot-check detection precision on a specific collection run
- `tests/test_agent_detector_pure.py`, `tests/collection/test_two_tier_agent_collection.py`, `tests/collection/test_agent_file_scanner.py`, `tests/collection/test_agent_patterns_extra.py`, `tests/collection/test_agent_patterns_thorough.py` — the real, current test coverage for everything described above
