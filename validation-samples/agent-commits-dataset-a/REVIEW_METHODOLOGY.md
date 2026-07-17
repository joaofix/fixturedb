# Manual review methodology: agent-commits-dataset-a

Full 384-row sample (Cochran 95%/5%, seed=42, stratified by (language,
agent_type), N=358,429 agent-attributed commits), reviewed 2026-07-17. This
is the paper's core attribution claim — that a specific commit was authored
or co-authored by a named AI coding agent — so this review was treated as the
highest-priority target in
[Manual-Validation Sampling § Reduced validation set](../../docs/usage/validation-sampling.md#reduced-validation-set).

## Method

Evidence here is thinner than a fixture-content review by design:
`evidence` is `agent_type; commit_date; author` — not the commit message or
diff (see `validation-sampling.md`'s documented gap). Genuine verification
means opening the real commit on GitHub and reading its actual message and
author identity.

8 batches of 48 rows, each independently reviewed by a parallel agent via
live GitHub checks (the commit's `.patch`/rendered page, not the CSV's own
claim). Judged TP if the commit message contains a real
`Co-authored-by`/`Assisted-by`/`Generated-by` trailer naming the claimed
agent, **or** the commit's own author identity is a known, verified bot
account for that agent; FP if neither signal is present, or a real signal
names a *different* agent than claimed; 404 if the commit is unreachable
(deleted, force-pushed away, or the repo went private).

## Result: 377 / 384 TP — 98.2% precision, 6 FP, 1 404

The 404: `CodePhiliaX/youclaw` (renamed to `OtterMind/youclaw`) — the specific
commit SHA isn't present at the new location either.

### All 6 FPs are name/identity collisions on bare-word catalog entries

Every false positive is a real author (human, or in one case a repo-internal
placeholder bot) whose identity happens to collide with a bare agent keyword,
with **no trailer of any kind** in the commit message to disambiguate. Two
different root causes, both traced to their source and fixed:

**5 rows — `devin`/`cline` name collisions** (root patterns removed from
`agent_authors.csv` entirely, not case-by-case allowlisted):

| `validation_id` | Repo | Claimed | Why it's FP |
|---|---|---|---|
| `agent-commits-dataset-a-0124` | foldkit/foldkit | devin | Author is human "Devin Jameson" (repo owner), not `devin-ai-integration[bot]` |
| `agent-commits-dataset-a-0157` | CyberStrikeus/CyberStrike | cline | Author is human "Aiden **Cline**" (surname collision) |
| `agent-commits-dataset-a-0211` | saoudrizwan/claude-dev | cline | Author is a **Cline-company employee** (`@cline.bot` work email) committing to Cline's own original repo |
| `agent-commits-dataset-a-0225` | NVIDIA/nv-ingest | devin | Author is human "**Devin** Robison", not the bot |
| `agent-commits-dataset-a-0260` | foldkit/foldkit | devin | Same repo/author as row 0124, a second commit from the same human |

**1 row — `codex` placeholder-identity collision** (the specific bad identity
added to `known_human_collisions.csv`, since the bare `codex` pattern itself
is still needed elsewhere for genuine trailer-based detection and couldn't be
removed the way `devin`/`cline` were):

| `validation_id` | Repo | Claimed | Why it's FP |
|---|---|---|---|
| `agent-commits-dataset-a-0246` | Yeachan-Heo/oh-my-claude-sisyphus | codex | Author `codex-review@example.com` — a placeholder/reserved domain, not a real OpenAI Codex identity |

Both are real, fixable detection bugs, not a data-drift issue like the
companion `agent-repos` review's FPs. Investigated in full — see
[Agent Detection § Known Limitations](../../docs/architecture/agent-detection.md#known-limitations)
for both fixes, the evidence behind each (Cline's official docs and the real
corpus data confirming the safe `devin-ai-integration` pattern already
covers every genuine Devin AI commit; the corpus data showing most real
`codex` commits are trailer-based and don't contain "codex" in the author
field at all), and the measured population-wide impact (3,467 `devin`-tagged
and 2,102 `cline`-tagged commits, plus 226 `codex-review@example.com`
commits / 204 fixtures, in the existing, uncorrected
`datasets/a/commits/*.csv` and `datasets/a/fixtures/*.csv`). Both fixed
forward-looking only, per
[Limitations § Agent-Identity Name Collisions](../../docs/reference/limitations.md) —
the existing Dataset A corpus is not retroactively patched.

Every other sampled `devin`/`cline`/`codex` commit not listed above — and
every sampled commit for every other agent type — carried a genuine,
verifiable signal: a real `Co-authored-by`/`Assisted-by`/`Generated-by`
trailer, or the commit's own author identity matching a real, known bot
account (e.g. `cursoragent@cursor.com`, `copilot-swe-agent[bot]`,
`devin-ai-integration[bot]`, `gemini-code-assist[bot]`).

### Two more bare-word clusters checked, confirmed genuine (not false positives)

The same corpus check that found the `codex-review@example.com` collision
also flagged two other bare-word additions (`gemini`, `windsurf`) with real
collision *potential*, worth individually verifying rather than assuming
either way:

- **`Neo Gemini <neo-gemini-3-1-pro@neomjs.com>` (325 commits)**: live-checked
  a real commit (`neomjs/neo`) — authored directly by the bot, building the
  project's own AI-agent-messaging infrastructure. `neomjs/neo`'s own README
  explicitly documents `@neo-gemini-pro` as an AI maintainer literally
  running "Google Gemini 3.1 Pro," part of a self-described multi-agent
  swarm ("Claude, Gemini, GPT" from "rival labs" cross-reviewing each
  other). Genuine, self-documented Gemini-model authorship under a
  project-specific bot identity — not one of the named commercial products
  this catalog otherwise tracks, but real AI-agent-generated code
  nonetheless. No fix applied.
- **`Cascade <cascade@windsurf.dev>` (13 commits)**: live-checked a real
  commit (`MervinPraison/PraisonAI`) — authored directly by the bot, no
  trailer, routine AI-assistant-style reasoning in the message. The domain
  (`windsurf.dev`) isn't in upstream's specific pattern (`cascade@windsurf.ai`)
  — the bare `windsurf` fallback correctly catching a real case the narrow
  pattern misses. No fix applied.
