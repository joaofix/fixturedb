"""Loader for the AI coding agent detection heuristics catalog.

- agent_heuristics.yaml (this package's root): paper_scope, this project's
  own data.
- agent-mining/agent_files.csv, agent_authors.csv, bots.csv: file_based,
  commit_signatures, bot_patterns respectively -- flat CSVs mirroring
  labri-progress/agent-mining's own data files so a reviewer can diff them
  directly. Each has upstream's rows verbatim, followed by this project's
  own additions after a `#`-prefixed boundary comment line (CSV has no
  native comment syntax).

Full schema, row-provenance, and rationale: docs/architecture/agent-detection.md.
collection/agent_patterns.py consumes this module's merged output.
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

# Maps each CSV's "tool" display name to this project's internal agent_type
# key. Every "tool" value in either CSV must have an entry here -- a
# missing one raises KeyError at import time, so a new tool added without
# a mapping fails loudly.
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

# Collapses a case-class like "AI [Aa]ssistant" (copied verbatim from
# upstream) to its lowercase letter -- our matching is already
# case-insensitive, so the bracket class is redundant and would otherwise
# be treated as literal characters.
_CASE_CLASS_RE = re.compile(r"\[([A-Za-z])[A-Za-z]\]")


def _non_comment_lines(fh):
    """Filter out '#'-prefixed comment lines and blank lines from a CSV
    file handle before csv.reader sees them (marks the upstream/project
    boundary; see this module's docstring)."""
    for line in fh:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            yield line


def _load_file_based_patterns(path: Path = _FILES_CSV_PATH) -> Dict[str, List[str]]:
    """Group agent_files.csv's flat pattern rows by internal agent_type key."""
    patterns: Dict[str, List[str]] = {}
    with path.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(_non_comment_lines(fh)):
            agent_type = _TOOL_TO_AGENT_TYPE[row["tool"]]
            patterns.setdefault(agent_type, []).append(row["pattern"])
    return patterns


def _load_commit_signatures(path: Path = _AUTHORS_CSV_PATH) -> Dict[str, List[str]]:
    """Group agent_authors.csv's flat pattern rows by internal agent_type key."""
    signatures: Dict[str, List[str]] = {}
    with path.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(_non_comment_lines(fh)):
            agent_type = _TOOL_TO_AGENT_TYPE[row["tool"]]
            pattern = _CASE_CLASS_RE.sub(lambda m: m.group(1).lower(), row["pattern"])
            signatures.setdefault(agent_type, []).append(pattern)
    return signatures


def _load_bot_patterns(path: Path = _BOTS_CSV_PATH) -> List[str]:
    """Read bots.csv's flat pattern column, in file order. Patterns are
    already regex-ready as copied from upstream (brackets pre-escaped), so
    callers must not re.escape() them -- see agent_patterns.py's
    is_bot_author()."""
    patterns: List[str] = []
    with path.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(_non_comment_lines(fh)):
            patterns.append(row["pattern"])
    return patterns


def load_agent_heuristics(path: Path = _HEURISTICS_PATH) -> Dict[str, Any]:
    """Parse and return the agent heuristics catalog (file_based,
    commit_signatures, bot_patterns, paper_scope) -- see this module's
    docstring for where each piece comes from."""
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    data["file_based"] = _load_file_based_patterns()
    data["commit_signatures"] = _load_commit_signatures()
    data["bot_patterns"] = _load_bot_patterns()
    return data
