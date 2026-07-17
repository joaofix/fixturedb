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

### All 6 FPs are the same root cause: `devin`/`cline` name collisions

Every false positive is a real human author whose name, surname, or employer
email domain happens to collide with the bare word `devin` or `cline`, with
**no trailer of any kind** in the commit message to disambiguate:

| `validation_id` | Repo | Claimed | Why it's FP |
|---|---|---|---|
| `agent-commits-dataset-a-0124` | foldkit/foldkit | devin | Author is human "Devin Jameson" (repo owner), not `devin-ai-integration[bot]` |
| `agent-commits-dataset-a-0157` | CyberStrikeus/CyberStrike | cline | Author is human "Aiden **Cline**" (surname collision) |
| `agent-commits-dataset-a-0211` | saoudrizwan/claude-dev | cline | Author is a **Cline-company employee** (`@cline.bot` work email) committing to Cline's own original repo |
| `agent-commits-dataset-a-0225` | NVIDIA/nv-ingest | devin | Author is human "**Devin** Robison", not the bot |
| `agent-commits-dataset-a-0246` | Yeachan-Heo/oh-my-claude-sisyphus | codex | Author `codex-review@example.com` — a placeholder/reserved domain, not a real OpenAI Codex identity |
| `agent-commits-dataset-a-0260` | foldkit/foldkit | devin | Same repo/author as row 0124, a second commit from the same human |

This is a real, fixable detection bug, not a data-drift issue like the
companion `agent-repos` review's FPs. Investigated in full — see
[Agent Detection § Known Limitations](../../docs/architecture/agent-detection.md#known-limitations)
for the fix (root patterns removed from `agent_authors.csv`, not
case-by-case allowlisted), the evidence behind it (Cline's official docs and
the real corpus data confirming the safe `devin-ai-integration` pattern
already covers every genuine Devin AI commit), and the measured
population-wide impact (3,467 `devin`-tagged and 2,102 `cline`-tagged
commits in the existing, uncorrected `datasets/a/commits/*.csv`, 357 fixtures
in `datasets/a/fixtures/*.csv`). Fixed forward-looking only, per
[Limitations § Agent-Identity Name Collisions](../../docs/reference/limitations.md) —
the existing Dataset A corpus is not retroactively patched.

Every other sampled `devin`/`cline` commit not listed above — and every
sampled commit for every other agent type — carried a genuine, verifiable
signal: a real `Co-authored-by`/`Assisted-by`/`Generated-by` trailer, or the
commit's own author identity matching a real, known bot account (e.g.
`cursoragent@cursor.com`, `copilot-swe-agent[bot]`,
`devin-ai-integration[bot]`, `gemini-code-assist[bot]`).
