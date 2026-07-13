"""Loader for the AI coding agent detection heuristics catalog.

paper_scope lives in agent_heuristics.yaml, next to this file -- this
project's own catalog, not sourced from anywhere upstream, so it stays at
this package's root. file_based, commit_signatures, and bot_patterns each
live in their own CSV under agent-mining/, a dedicated subfolder that
deliberately mirrors labri-progress/agent-mining's own data files
(github.com/labri-progress/agent-mining/tree/main/patterns) schema and
content, so a paper reviewer can compare the files directly -- kept
separate from this project's own YAML so what's upstream-sourced vs.
project-authored is a directory boundary, not just a comment:

- agent-mining/agent_files.csv: flat `pattern,tool,start_date,end_date`
  table (mirrors files.csv). First 95 data rows are that file's content
  verbatim, in its original order; everything after a `#`-prefixed
  boundary comment line is this project's own addition -- a single pattern
  (`.cursorignore`) individually confirmed against Cursor's official docs.
  Ten other candidate additions were considered and dropped after failing
  that same verification: each was either undocumented or already covered
  by an upstream directory-marker pattern (`.claude/`, `.cursor/`,
  `.openhands/`, `.devin/`, `.cline/` already match regardless of what's
  inside them).
- agent-mining/agent_authors.csv: flat `pattern,tool,start_date,end_date`
  table (mirrors authors.csv). First 80 data rows are that file's content
  verbatim, in its original order; everything after a `#`-prefixed boundary
  comment line is this project's own additions.
- agent-mining/bots.csv: flat `pattern,tool` table (mirrors bots.csv).
  First 84 data rows are that file's content verbatim, in its original
  order; everything after the boundary comment is this project's own
  additions -- deliberately a short list of specific, individually-verified
  real bot accounts seen in this project's own corpus but missing from the
  upstream list (e.g. copilot-swe-agent[bot]), NOT a generic catch-all
  pattern. A bot name that is neither in upstream's list nor in this
  project's short addition is simply not detected; see
  docs/architecture/agent-detection.md's Known Limitations for that
  deliberate tradeoff (verified-list precision over a broader, unverified
  catch-all).

This module is the only place that reads any of these files;
collection/agent_patterns.py consumes the merged result and derives the
shapes existing call sites expect.
"""

import csv
import re
from pathlib import Path
from typing import Any, Dict, List

import yaml

_HEURISTICS_PATH = Path(__file__).parent / "agent_heuristics.yaml"
_AGENT_MINING_DIR = Path(__file__).parent / "agent-mining"
_FILES_CSV_PATH = _AGENT_MINING_DIR / "agent_files.csv"
_AUTHORS_CSV_PATH = _AGENT_MINING_DIR / "agent_authors.csv"
_BOTS_CSV_PATH = _AGENT_MINING_DIR / "bots.csv"

# Maps agent_files.csv/agent_authors.csv's "tool" column (a display name,
# matching labri-progress/agent-mining's own naming) to this project's
# internal agent_type key -- the short lowercase identifier used everywhere
# else in collection/ (file_based's/commit_signatures' keys, paper_scope's
# entries, DB columns, CSV outputs). Shared across both CSVs so the same
# tool (e.g. "Claude Code") always maps to the same agent_type regardless of
# which file it was read from. Every distinct "tool" value in either CSV
# must have an entry here; _load_file_based_patterns()/_load_commit_
# signatures() raise a plain KeyError at import time otherwise, so a new
# tool added to either CSV without a mapping fails loudly, not silently.
_TOOL_TO_AGENT_TYPE: Dict[str, str] = {
    "Aider": "aider",
    "Claude Code": "claude",
    "Copilot": "copilot",
    "OpenHands": "openhands",
    "Devin": "devin",
    "Jules": "jules",
    "Cline": "cline",
    "Junie": "junie",
    "Gru": "gru",
    "Cursor": "cursor",
    "Gemini": "gemini",
    "Sweep": "sweep",
    "Coderabbit": "coderabbit",
    "Sourcery": "sourcery",
    "Deepsource": "deepsource",
    "GPT-Engineer": "gpt_engineer",
    "Codegen": "codegen",
    "Sketch": "sketch",
    "Windsurf": "windsurf",
    "Fly": "fly",
    "ChatGPT": "chatgpt",
    "Roo Code": "roo_code",
    "Amp": "amp",
    "Opencode": "opencode",
    "Kilo Code": "kilo_code",
    "Crush": "crush",
    "Codex": "codex",
    "Qwen Coder": "qwen_coder",
    "Langchain Open SWE": "langchain_open_swe",
    "Warp": "warp",
    "Ona": "ona",
    "Generic": "generic",
    "Sentry Seer": "sentry_seer",
    "Abacus": "abacus",
    "Mistral Vibe": "mistral_vibe",
    "Letta Code": "letta_code",
    "Factory Droid": "factory_droid",
    "Kiro": "kiro",
    "Microsoft Amplifier": "microsoft_amplifier",
    "Verdent": "verdent",
    "Paperclip": "paperclip",
    # New tools introduced by agent_files.csv (not present in agent_authors.csv):
    "Augment Code": "augment_code",
    "Taskmaster": "taskmaster",
    "SpecKit": "speckit",
    "Trae": "trae",
    "Goose": "goose",
    "Plandex": "plandex",
    "Continue": "continue",
    "Brokk": "brokk",
    "Amazon Q": "amazon_q",
    "Codebuddy": "codebuddy",
    "Baidu Comate": "baidu_comate",
    "Alibaba Lingma": "alibaba_lingma",
    "Tessl": "tessl",
    "Serena": "serena",
    "Rulesync": "rulesync",
    "Qodo": "qodo",
    "Charlie": "charlie",
    "Kimi Code": "kimi_code",
    "Pi": "pi",
    "Atlassian Rovodev": "atlassian_rovodev",
    "SpecStory": "specstory",
    "Superpowers": "superpowers",
}

# Collapses a single-letter case-class like the CSV's "AI [Aa]ssistant" (row
# copied verbatim from labri-progress/agent-mining) down to its lowercase
# letter. Our own matching (agent_patterns.match_agent_keyword) is already
# fully case-insensitive, so the character class -- presumably meaningful in
# whatever tool produced the source file -- is redundant noise for us and
# would otherwise be treated as literal bracket characters via re.escape.
_CASE_CLASS_RE = re.compile(r"\[([A-Za-z])[A-Za-z]\]")


def _non_comment_lines(fh):
    """Filter out '#'-prefixed comment lines and blank lines from a CSV file
    handle before csv.reader sees them. csv itself has no comment syntax, so
    agent_authors.csv/bots.csv both use a plain '#' line to mark the boundary
    between upstream's verbatim content and this project's own additions --
    this is what lets that line coexist with real parsing instead of being
    read as a malformed data row.
    """
    for line in fh:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            yield line


def _load_file_based_patterns(path: Path = _FILES_CSV_PATH) -> Dict[str, List[str]]:
    """Group agent_files.csv's flat pattern rows by internal agent_type key.

    The first 95 rows are labri-progress/agent-mining's files.csv content
    verbatim, in its original order; this project's own single addition
    after the boundary comment (`.cursorignore`) was individually confirmed
    against Cursor's official docs before being added. Ten other candidate
    additions carried over from this project's pre-migration detection
    logic (bare ".devin"/".openhands"/".cline", "*.config" variants, etc.)
    were checked the same way and dropped: none were documented, and each
    was already redundant with an upstream directory-marker pattern
    (".claude/", ".cursor/", ".openhands/", ".devin/", ".cline/" match
    regardless of what's inside them).

    start_date/end_date are read from the file but deliberately unused
    here, same as agent_authors.csv -- see that loader's docstring.
    """
    patterns: Dict[str, List[str]] = {}
    with path.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(_non_comment_lines(fh)):
            agent_type = _TOOL_TO_AGENT_TYPE[row["tool"]]
            patterns.setdefault(agent_type, []).append(row["pattern"])
    return patterns


def _load_commit_signatures(path: Path = _AUTHORS_CSV_PATH) -> Dict[str, List[str]]:
    """Group agent_authors.csv's flat pattern rows by internal agent_type key.

    start_date/end_date are read from the file (kept for schema/citation
    fidelity with labri-progress/agent-mining's authors.csv) but deliberately
    unused here -- this project detects agent patterns independent of time
    period, not as validity windows, so those two columns are always empty
    and intentionally ignored, not a gap to fill in later.
    """
    signatures: Dict[str, List[str]] = {}
    with path.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(_non_comment_lines(fh)):
            agent_type = _TOOL_TO_AGENT_TYPE[row["tool"]]
            pattern = _CASE_CLASS_RE.sub(lambda m: m.group(1).lower(), row["pattern"])
            signatures.setdefault(agent_type, []).append(pattern)
    return signatures


def _load_bot_patterns(path: Path = _BOTS_CSV_PATH) -> List[str]:
    """Read bots.csv's flat pattern column, in file order.

    The first 84 rows are labri-progress/agent-mining's bots.csv content
    verbatim; this project's own additions after the boundary comment are
    deliberately a short, specific list of individually-verified real bot
    accounts seen in this project's own corpus but missing upstream (e.g.
    copilot-swe-agent[bot]) -- not a generic catch-all pattern. A bot name
    in neither list is simply not detected, a deliberate precision-over-
    coverage tradeoff; see docs/architecture/agent-detection.md's Known
    Limitations.

    The pattern values are already regex-ready as copied from upstream
    (e.g. "dependabot\\[bot\\]" has its brackets pre-escaped by the source
    file itself) rather than plain literal text -- see agent_patterns.py's
    is_bot_author() for how they're compiled directly as regexes, with no
    re.escape() step. The "tool" column (a coarse bot-vendor label:
    dependabot/renovate/microsoft/snyk/azure/dotnet/github actions/generic
    "Bot") is kept in the file for schema fidelity with the upstream source
    but is not currently consumed -- bot classification here is a flat
    yes/no, with no downstream use of which specific bot vendor matched.
    """
    patterns: List[str] = []
    with path.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(_non_comment_lines(fh)):
            patterns.append(row["pattern"])
    return patterns


def load_agent_heuristics(path: Path = _HEURISTICS_PATH) -> Dict[str, Any]:
    """Parse and return the agent heuristics catalog (file_based,
    commit_signatures, bot_patterns, paper_scope).

    paper_scope comes from agent_heuristics.yaml; file_based comes from
    agent_files.csv, commit_signatures comes from agent_authors.csv, and
    bot_patterns comes from bots.csv (see this module's docstring for why
    they're separate CSVs).
    """
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    data["file_based"] = _load_file_based_patterns()
    data["commit_signatures"] = _load_commit_signatures()
    data["bot_patterns"] = _load_bot_patterns()
    return data
