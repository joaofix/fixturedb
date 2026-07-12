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

1. **Bot status** — the commit's `Author` name + email checked against `bots.csv`'s catalog. Never overridden by a later signal: a bot-authored commit whose message happens to contain an agent-style trailer (e.g. templated tooling stamping a `Generated-by:` line onto a dependency-bump commit) must still be excluded as bot, not misattributed to that agent.
2. **Co-authored-by trailers** — the commit body is scanned for `Co-authored-by:`, `Assisted-by:`, `Generated-by:` lines (case-insensitive, and hyphen-tolerant on "co-authored-by" specifically — `Coauthored-by`/`Co-authoredby`/`Coauthoredby` all match too, a real variant some agents emit, not just the canonical spelling); the trailer value is checked the same way. Both Tier 1 (`Tier1RepositoryScanner`) and Tier 2 (`AgentCommitVerifier`) share the exact same trailer regex (`AGENT_TRAILER_RE` in `collection/utils.py`) — they used to have two independently-maintained patterns that drifted (Tier 2's didn't tolerate the hyphen variants and didn't recognize `Assisted-by`/`Generated-by` at all). Checked before author metadata because it's the less collision-prone signal — a deliberate, structured convention only agents/tooling emit, unlike a freely-editable author-name field a human can also happen to share (see "Known Limitations" below).
3. **Author metadata** — the commit's `Author` name + email checked against the `commit_signatures` catalog (some tools set themselves as the primary author, similarly to how CI bots operate).

Matching is **word-boundary-based** (`agent_patterns.py::match_agent_keyword()`), not a bare substring check — this rules out a keyword matching inside an unrelated compound word (e.g. "cline" no longer matches inside "McLine"). It does **not** rule out an exact whole-word collision with a common name when no trailer is present to disambiguate (see "Known Limitations" below).

Implementation: `Tier1RepositoryScanner._detect_agent_in_commit()` in `tiered_agent_corpus_scanner.py`.

### Why this design

The study prioritizes precision over recall for the main analysis: a false positive (classifying human code as agent-assisted) threatens validity more than a false negative (an uncredited agent commit just reduces statistical power). Explicit `Co-authored-by` trailers and matched author identity are the most constrained, deliberate signal available; free-text commit-message scanning is deliberately **not** used for this reason (see "Known Limitations").

### Pure-Addition Filter for Test Files

Identifying an agent-authored commit isn't sufficient on its own — a commit could still mix agent-added fixtures with human-edited test code. The pipeline additionally requires that a fixture's own diff span be **100% newly added**, never modified, via two gates:

- **Commit-level**: if any test file in the commit has a deletion, rename, or copy, the whole commit is rejected.
- **File-level**: within an accepted commit, each fixture's own line span (preferring an AST-node-precise check, falling back to a line-range check) must consist exclusively of added lines.

Implementation: `collection/diff_purity.py` (`commit_is_pure_addition()`, `is_pure_addition()`, PyDriller-`Commit`-based), `collection/agent_fixture_extractor.py` (`_is_fixture_completely_added()`, `_build_diff_line_maps()`, both built from PyDriller's `ModifiedFile.diff_parsed`/`.change_type` directly rather than hand-parsed diff text). `diff_purity.py` also has raw-unified-diff-text equivalents (`_raw_diff_commit_is_pure_addition()`, `_raw_diff_file_is_pure_addition()`) for callers without a PyDriller `Commit` object in hand; the agent-corpus pipeline itself always has one, so it uses the `Commit`-based versions. Tests: `tests/collection/test_fixture_extractor_partial_detection.py`, `tests/test_fixture_extractor_small.py`.

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

The full, current catalog of recognized agents lives in four data files, not duplicated here — the catalog of coding agents grows faster than any doc can track, so these are the single source of truth. Adding or updating an agent is a data change, not a code change.
- [`collection/heuristics/agent_heuristics.yaml`](../../collection/heuristics/agent_heuristics.yaml) — only the paper's strict-scope subset (`paper_scope`) now; `file_based`/`commit_signatures`/`bot_patterns` all moved out to their own CSVs (below).
- [`collection/heuristics/agent_files.csv`](../../collection/heuristics/agent_files.csv) — config-file/directory patterns (`file_based`), as a flat `pattern,tool,start_date,end_date` table. This deliberately mirrors [labri-progress/agent-mining](https://github.com/labri-progress/agent-mining)'s own `files.csv` schema and content: the file's first 95 data rows are that file's content verbatim in its original order, with this project's own addition appended after a `#`-prefixed comment line marking the boundary. That single addition, `.cursorignore`, was individually confirmed against [Cursor's official docs](https://cursor.com/docs/reference/ignore-file) before being added. Ten other candidates carried over from this project's pre-migration detection logic (bare `.devin`/`.openhands`/`.cline`, `claude.config`/`cursor.config`, `.copilot-instructions.md`, `.devin.config`/`.openhands.config`/`.cline.config`) were checked the same way and dropped: none were documented, and each was already redundant with an upstream directory-marker pattern (`.claude/`, `.cursor/`, `.openhands/`, `.devin/`, `.cline/` match regardless of what's inside them). Entries ending in `/` match a directory name anywhere in the path; others may use fnmatch globs (see `collection/agent_patterns.py:path_matches_pattern`).
- [`collection/heuristics/agent_authors.csv`](../../collection/heuristics/agent_authors.csv) — commit author/trailer signatures (`commit_signatures`), as a flat `pattern,tool,start_date,end_date` table. This deliberately mirrors [labri-progress/agent-mining](https://github.com/labri-progress/agent-mining)'s own `authors.csv` schema and content: the file's first 80 data rows are that file's content verbatim in its original order, with this project's own additions appended after a `#`-prefixed comment line marking the boundary (plain CSV has no comment syntax, so `collection/heuristics/__init__.py`'s `_non_comment_lines()` strips it before parsing). Loaded and grouped by internal agent_type via that module's `_TOOL_TO_AGENT_TYPE` mapping — shared across `agent_files.csv` and `agent_authors.csv`, so the same tool name always maps to the same agent_type regardless of which file it came from. `start_date`/`end_date` are always empty and intentionally unused — this project matches agent patterns independent of time period, not as validity windows; the columns are kept only for schema parity with the source file.
- [`collection/heuristics/bots.csv`](../../collection/heuristics/bots.csv) — CI/automation bot account patterns (`bot_patterns`), as a flat `pattern,tool` table mirroring [labri-progress/agent-mining](https://github.com/labri-progress/agent-mining)'s own `bots.csv` (no `start_date`/`end_date` in this one — the upstream file doesn't have them either). Same verbatim-then-boundary-comment-then-additions structure as `agent_authors.csv`: the first 84 data rows are upstream's content unmodified, followed by a short list of this project's own additions — specific, individually-verified real bot accounts observed in this project's own corpus but missing from upstream (currently `copilot-swe-agent[bot]` and `anthropic-code-agent[bot]`), **not** a generic `[bot]`-suffix catch-all (see Known Limitations below for why that tradeoff was made deliberately). This file's `pattern` column is already regex-ready as copied from upstream (brackets pre-escaped, e.g. `dependabot\[bot\]`) rather than plain literal text, so `agent_patterns.py`'s `is_bot_author()` compiles patterns directly instead of `re.escape()`-ing them first (see that function's docstring for why re-escaping would break every bracketed pattern). This replaced a bare `"[bot]" in author_name` substring check this project used before adopting the upstream catalog, which caught any bracket-suffixed name regardless of whether it was individually verified.

---

## Exclusions

**Merge commits** are excluded everywhere — they're version-control artifacts (PR merges, branch integration), not individual developer or agent activity. All `git log` invocations in this pipeline use `--no-merges`.

**Bot accounts** (matched against `collection/heuristics/bots.csv`'s catalog — dependabot, renovate, github-actions, and dozens of other CI/automation bots, e.g. `copilot-swe-agent[bot]`) are classified separately (`"bot"`), not attributed to a specific coding agent — a repo's own CI/automation bots are a different thing from an interactive coding assistant. Checked before agent-signature matching, so a bot account whose name happens to contain an agent keyword (e.g. `copilot-swe-agent[bot]`) isn't misattributed to that agent.

---

## Known Limitations

**Name/word collisions in author-identity matching.** Several agent signatures (`devin`, `jules`, `claude`, `cline`, `cursor`, `gemini`, `windsurf`) are also common human first names or ordinary English words. Word-boundary matching (added after an audit this session) rules out a keyword matching inside an unrelated compound word or surname (e.g. "cline" no longer matches inside "McLine"), but it cannot rule out an exact whole-word collision — a commit author literally named "Devin Smith" is still misattributed to the Devin agent *when there's no trailer to disambiguate*. Detection checks the trailer before author identity for exactly this reason (see Tier 1 above): a commit by "Devin Smith" carrying a correct `Co-authored-by: Claude` trailer is now classified `claude`, not `devin`. The residual gap is a commit that both collides on author name *and* has no trailer at all — that case has no signal to fall back on, and is a fundamental limit of text-only heuristics on a freely-editable author-name field, not something a smarter regex closes; there's no verified, universal bot-email-domain convention across these tools to fall back on instead. If false-positive rate matters for a specific analysis, manually spot-check via `collection/validation_sampling.py`. (Documented in `agent_heuristics.yaml`'s module comment too.)

**Free-text commit messages are not scanned.** Only structured fields (author name/email, trailer lines) are checked. An audit this session found that scanning the full commit-message body for agent keywords produced real false positives — e.g. "Revert a bad Claude suggestion" (prose mention, no real attribution) and "Fix cursor blinking bug" (an unrelated UI element, not the Cursor agent) — so this path was removed rather than kept as a broader-recall option.

**Explicit attribution required.** An agent-assisted commit with no trailer and no agent-identity author is not detected at all (Tier 1) — this is a deliberate false-negative tradeoff for precision, not a bug. Tier 2's file-presence check is a coarser, supplementary signal for exactly this reason and is not used for the main comparison.

**Bot detection is a fixed, mostly-upstream list, not a generic pattern.** `bots.csv` is labri-progress/agent-mining's own catalog verbatim, plus a short, deliberately narrow list of this project's own additions — specific bot accounts (currently `copilot-swe-agent[bot]`, `anthropic-code-agent[bot]`) individually confirmed present in this project's corpus and specifically prone to misattribution (their names contain an agent keyword, e.g. "copilot"/"claude", so without an explicit bot check they'd be counted as agent-authored rather than excluded). This project previously used a broader `"[bot]" in author_name` substring check that caught *any* bracket-suffixed bot name, verified or not; that generality was deliberately traded away in favor of an explicit, individually-verified list. The consequence: a CI/automation bot account that is neither in upstream's list nor in this short addition (a newly-created GitHub App not yet catalogued anywhere, for instance) is not detected as a bot, and its commits fall through to being counted as human-authored (or, if its name happens to contain an agent keyword, as agent-authored). Extending the addition list requires the same bar as the two entries already there: a specific, individually-confirmed account, not a speculative pattern.

**Date cutoff (`AGENT_CORPUS_START_DATE`, 2025-01-01).** Chosen as a window where all catalogued agents are assumed mature enough to detect; commits before this date are excluded from Dataset A regardless of any agent signal they might carry.

---

## Reproducibility

Detection is fully deterministic given a pinned commit SHA: the same repository state, pattern catalog, and date cutoff always produce the same classification. The only non-deterministic inputs are external — repository state changing over time (new commits), and live GitHub API availability during Tier 2 discovery.

---

## See Also

- [Fixture Detection Logic](detection.md) — how fixtures themselves are found and measured (a separate concern from *who* authored the commit)
- [Manual-Validation Sampling](../usage/validation-sampling.md) — drawing a review sample to spot-check detection precision on a specific collection run
- `tests/test_agent_detector_pure.py`, `tests/collection/test_two_tier_agent_collection.py`, `tests/collection/test_agent_file_scanner.py`, `tests/collection/test_agent_patterns_extra.py`, `tests/collection/test_agent_patterns_thorough.py` — the real, current test coverage for everything described above
