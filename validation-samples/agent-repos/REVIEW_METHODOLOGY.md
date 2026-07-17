# Manual review methodology: agent-repos

Full 350-row sample (Cochran 95%/5%, seed=42, stratified by language, N=3,836
`has_agent_config=1` repos), reviewed 2026-07-17.

## Method

Unlike the fixture-detection reviews (`human-fixtures-dataset-b`/`-c`), this
sample's evidence is thin by design — `detection_signal`/`evidence` is just
the claimed config filename (e.g. `CLAUDE.md`), not its content (see
`validation-sampling.md`'s documented evidence gap). Judging a row for real
requires opening the actual repo on GitHub, so this review used live
verification for every row, not a raw-source read:

7 batches of 50 rows, each independently reviewed by a parallel agent via
live GitHub checks (`raw.githubusercontent.com`/tree pages/redirects, not the
CSV's own claim) against the actual repo at its current default branch.
Judged TP if the claimed file/directory genuinely exists and its content is a
real AI-coding-agent configuration (not a coincidental namesake or empty
placeholder); FP if it doesn't exist or is unrelated; 404 if the repo itself
is gone/private.

## Result: 327 / 350 TP — 93.4% precision, 23 FP, 0 Unsure, 0 404

Every one of the 23 FPs is the same class: **the claimed config file/directory
no longer exists at the repo's current HEAD.** Spot examples: `CLAUDE.md`
removed since the scan (`tolgee/tolgee-platform`, `frappe/frappe`,
`run-llama/llama_cloud_services`, and 15 others), a repo renamed without the
file surviving the move (`eclipse/che` → `eclipse-che/che`), and a few
`.cursorrules`/`.cursor/`/`.claude/` directory claims that don't exist at any
path checked (`slopus/happy`, `nottelabs/notte`,
`agentclientprotocol/claude-agent-acp`).

This is **scan-time-vs-now data drift, not a detector logic bug** — the
pattern-matching itself (checking a known catalog of real agent-config
filenames) is sound; repos and files simply change after the crawl that fed
`datasets/a/repos/*.csv`. No fix implemented as part of this review — a
`has_agent_config=1` flag's job is to describe the repo *at scan time*, and
re-verifying it live on every use isn't part of this project's methodology
(same reasoning as `CURSOR.md`'s own re-scan note in
[Agent Detection § Known Limitations](../../docs/architecture/agent-detection.md#known-limitations),
which found the same class of drift at a smaller scale).

Several genuine TPs were worth documenting since they could easily look like
FPs on a shallower check: symlinked `CLAUDE.md` files pointing to a canonical
`AGENTS.md` (verified by following the symlink and confirming real content:
`devlikeapro/waha`, `tmux-python/libtmux`, `davidkpiano/xstate`, others), and
one-line "pointer" `CLAUDE.md`/`copilot-instructions.md` files whose entire
content is just `AGENTS.md` or `@AGENTS.md` — Claude Code's documented
import-pointer convention, a deliberate functioning config, not an empty
placeholder.

## See also

[Agent Detection § Known Limitations](../../docs/architecture/agent-detection.md#known-limitations)
for the `devin`/`cline` author-identity collision found via the companion
`agent-commits-dataset-a` review — a different, code-level bug, not present
in this repo-level sample.
