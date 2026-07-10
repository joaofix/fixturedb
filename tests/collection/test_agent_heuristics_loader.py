"""Guardrail tests for the agent heuristics catalog (YAML + CSVs) and its loader.

These exist to catch a malformed future edit to agent_heuristics.yaml,
agent_files.csv, agent_authors.csv, or bots.csv (typo, empty list, missing
key, unmapped tool) -- not to test detection logic itself, which is covered
by test_agent_patterns_extra.py / test_agent_patterns_thorough.py.
"""

import csv

from collection.heuristics import (
    _AUTHORS_CSV_PATH,
    _BOTS_CSV_PATH,
    _FILES_CSV_PATH,
    _TOOL_TO_AGENT_TYPE,
    _non_comment_lines,
    load_agent_heuristics,
)


def test_loader_returns_expected_top_level_keys():
    data = load_agent_heuristics()
    assert set(data.keys()) == {
        "file_based",
        "commit_signatures",
        "bot_patterns",
        "paper_scope",
    }


def test_paper_scope_agents_all_have_file_based_patterns():
    data = load_agent_heuristics()
    for agent in data["paper_scope"]:
        assert agent in data["file_based"], f"{agent} in paper_scope but not file_based"


def test_every_catalog_entry_is_a_non_empty_list_of_non_empty_strings():
    data = load_agent_heuristics()
    for section in ("file_based", "commit_signatures"):
        for agent, patterns in data[section].items():
            assert isinstance(patterns, list) and patterns, (
                f"{section}.{agent} must be a non-empty list"
            )
            for pattern in patterns:
                assert isinstance(pattern, str) and pattern.strip(), (
                    f"{section}.{agent} contains an empty/non-string pattern: {pattern!r}"
                )


def test_new_agents_present_with_expected_patterns():
    data = load_agent_heuristics()
    # AGENTS.md was previously (incorrectly) attributed to codex alone; it's
    # actually a cross-agent/tool-agnostic convention (confirmed against
    # labri-progress/agent-mining's data, where it's classified "Generic",
    # not codex-specific), so it's no longer in codex's own list here.
    # .codex/ is codex's real, agent-specific marker.
    assert data["file_based"]["codex"] == [".codex/"]
    assert ".windsurfrules" in data["file_based"]["windsurf"]
    assert ".windsurf/" in data["file_based"]["windsurf"]
    assert ".roorules" in data["file_based"]["roo_code"]
    assert ".roo/" in data["file_based"]["roo_code"]


def test_cursorrules_only_under_cursor_not_claude():
    """Regression: .cursorrules was previously copy-pasted into claude's list too."""
    data = load_agent_heuristics()
    assert ".cursorrules" not in data["file_based"]["claude"]
    assert ".cursorrules" in data["file_based"]["cursor"]


def test_agents_md_not_attributed_to_codex():
    """Regression: AGENTS.md was previously listed as codex's own marker,
    but it's a cross-agent/tool-agnostic convention (used by many agents,
    not codex-specific) -- confirmed against labri-progress/agent-mining's
    empirically-verified catalog, which classifies it "Generic". Attributing
    it to codex specifically was a real misclassification risk: any repo
    using the generic AGENTS.md convention with some other agent would have
    been misattributed to codex."""
    data = load_agent_heuristics()
    assert "AGENTS.md" not in data["file_based"]["codex"]


def test_claude_anthropic_pattern_is_dotfile():
    """Regression: claude's file_based list had a bare "anthropic/" dir
    marker, which matches ANY directory named "anthropic" anywhere in the
    repo tree (e.g. a vendored SDK folder unrelated to actual Claude usage).
    The real convention is the dotfile ".anthropic/"."""
    data = load_agent_heuristics()
    assert ".anthropic/" in data["file_based"]["claude"]
    assert "anthropic/" not in data["file_based"]["claude"]


def test_aider_file_patterns_match_real_convention():
    """Regression: aider's file_based list previously had .aider.conf (no
    extension), .aider-config, aider.config -- none of which match aider's
    actual documented config filename (.aider.conf.yml / .aider.conf.yaml,
    confirmed against labri-progress/agent-mining's GitHub-code-search-
    verified data). The old patterns likely never matched a single real
    aider repo."""
    data = load_agent_heuristics()
    aider_patterns = data["file_based"]["aider"]
    assert ".aider.conf.yml" in aider_patterns
    assert ".aider.conf.yaml" in aider_patterns
    assert ".aider.conf" not in aider_patterns
    assert ".aider-config" not in aider_patterns
    assert "aider.config" not in aider_patterns


def test_jules_junie_gemini_have_file_based_patterns():
    """Regression: jules/junie/gemini were previously only detectable via
    commit_signatures (author/trailer), with no file_based coverage at all,
    despite being agents this project already tracks."""
    data = load_agent_heuristics()
    assert data["file_based"]["jules"] == [".jules/"]
    assert ".junie/" in data["file_based"]["junie"]
    assert "GEMINI.md" in data["file_based"]["gemini"]
    assert ".gemini/" in data["file_based"]["gemini"]


def test_codex_roo_code_have_commit_signatures():
    """Regression: codex/roo_code were previously only detectable via
    file_based patterns, with no commit_signatures coverage at all, despite
    being agents this project already tracks."""
    data = load_agent_heuristics()
    assert "codex" in data["commit_signatures"]
    assert "roo_code" in data["commit_signatures"]
    assert "roomote" in data["commit_signatures"]["roo_code"]


def _read_authors_csv_rows():
    with _AUTHORS_CSV_PATH.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(_non_comment_lines(fh)))


def test_authors_csv_has_boundary_comment_line():
    """A plain '#'-prefixed line marks where labri-progress/agent-mining's
    upstream content ends and this project's own additions begin -- this
    must exist in the raw file (for a human reading it directly) and must
    NOT show up as a parsed data row (covered by the row-count assertions
    in the two tests below, which would fail if it leaked through)."""
    with _AUTHORS_CSV_PATH.open("r", encoding="utf-8") as fh:
        raw_lines = fh.readlines()
    comment_lines = [line for line in raw_lines if line.lstrip().startswith("#")]
    assert len(comment_lines) == 1
    assert "own additions" in comment_lines[0]
    # The snapshot date makes the upstream copy independently reproducible
    # (agent-mining/authors.csv is itself actively maintained and can drift
    # from what's copied here) -- a future edit that drops it should fail
    # loudly rather than silently lose that provenance.
    assert "snapshotted verbatim on" in comment_lines[0]


def test_authors_csv_schema_matches_upstream():
    """agent_authors.csv deliberately mirrors labri-progress/agent-mining's
    own authors.csv column schema, so a reviewer can diff the two files
    directly -- a header drift here breaks that citation link."""
    with _AUTHORS_CSV_PATH.open("r", encoding="utf-8", newline="") as fh:
        header = next(csv.reader(fh))
    assert header == ["pattern", "tool", "start_date", "end_date"]


def test_authors_csv_every_tool_has_agent_type_mapping():
    rows = _read_authors_csv_rows()
    assert rows, "agent_authors.csv must have at least one data row"
    for row in rows:
        assert row["tool"] in _TOOL_TO_AGENT_TYPE, (
            f"tool {row['tool']!r} (pattern {row['pattern']!r}) has no "
            "_TOOL_TO_AGENT_TYPE mapping in collection/heuristics/__init__.py"
        )


def test_authors_csv_first_80_rows_are_upstream_verbatim():
    """The file's first 80 data rows must be labri-progress/agent-mining's
    authors.csv content, unmodified and in its original order -- this is
    the whole point of the CSV (a reviewer-checkable citation), not just a
    convenient format. Spot-checks a sample spanning the full file rather
    than asserting all 80 rows verbatim, so the test doesn't itself become
    an unreadable copy of the source file."""
    rows = _read_authors_csv_rows()
    upstream_rows = rows[:80]
    assert len(upstream_rows) == 80
    expected_samples = [
        {"pattern": "aider", "tool": "Aider"},
        {"pattern": "Claude", "tool": "Claude Code"},
        {"pattern": "AI [Aa]ssistant", "tool": "Generic"},
        {"pattern": "factory-droid[bot]", "tool": "Factory Droid"},
        {"pattern": "Codex (gpt-5.2-codex)", "tool": "Codex"},
        {"pattern": "noreply@paperclip.ing", "tool": "Paperclip"},
    ]
    for expected in expected_samples:
        assert any(
            row["pattern"] == expected["pattern"] and row["tool"] == expected["tool"]
            for row in upstream_rows
        ), f"upstream row {expected} not found verbatim in the first 80 rows"
    # Last upstream row (line 81 of the source file) must be the final row
    # of the 80-row block, proving the appended rows come strictly after it.
    assert upstream_rows[-1] == {
        "pattern": "noreply@paperclip.ing",
        "tool": "Paperclip",
        "start_date": "",
        "end_date": "",
    }


def test_authors_csv_our_additions_are_appended_after_upstream_block():
    rows = _read_authors_csv_rows()
    our_additions = rows[80:]
    added_patterns = {row["pattern"] for row in our_additions}
    assert added_patterns == {
        "anthropic",
        "openhands",
        "devin ai",
        "devin",
        "google jules",
        "jules",
        "gemini",
        "windsurf",
        "codex",
        "github.com/apps/github-copilot",
        "github copilot",
    }


def test_case_class_pattern_normalized_for_matching():
    """The upstream "AI [Aa]ssistant" row is kept verbatim in the CSV, but
    our own matching is already fully case-insensitive, so the loader must
    collapse it to a plain literal ("AI assistant") rather than let it be
    treated as literal bracket characters via re.escape."""
    data = load_agent_heuristics()
    assert "AI assistant" in data["commit_signatures"]["generic"]
    assert "AI [Aa]ssistant" not in data["commit_signatures"]["generic"]


def _read_bots_csv_rows():
    with _BOTS_CSV_PATH.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(_non_comment_lines(fh)))


def test_bots_csv_schema_matches_upstream():
    """bots.csv deliberately mirrors labri-progress/agent-mining's own
    bots.csv column schema (no start_date/end_date here, unlike
    authors.csv), so a reviewer can diff the two files directly."""
    with _BOTS_CSV_PATH.open("r", encoding="utf-8", newline="") as fh:
        header = next(csv.reader(fh))
    assert header == ["pattern", "tool"]


def test_bots_csv_has_boundary_comment_line():
    """A plain '#'-prefixed line marks where labri-progress/agent-mining's
    upstream content ends and this project's own (short, individually-
    verified) additions begin -- must not show up as a parsed data row
    (covered by the row-count assertions in the tests below)."""
    with _BOTS_CSV_PATH.open("r", encoding="utf-8") as fh:
        raw_lines = fh.readlines()
    comment_lines = [line for line in raw_lines if line.lstrip().startswith("#")]
    assert len(comment_lines) == 1
    assert "own additions" in comment_lines[0]
    assert "snapshotted verbatim on" in comment_lines[0]


def test_bots_csv_first_84_rows_are_upstream_verbatim():
    """The file's first 84 data rows must be labri-progress/agent-mining's
    bots.csv content, unmodified and in its original order. Spot-checks a
    sample spanning the full file (including its real, verbatim-preserved
    duplicate/inconsistent-tool rows) rather than asserting all 84 rows,
    so the test doesn't itself become an unreadable copy of the source
    file."""
    rows = _read_bots_csv_rows()
    upstream_rows = rows[:84]
    assert len(upstream_rows) == 84
    expected_samples = [
        {"pattern": "dependabot\\[bot\\]", "tool": "dependabot"},
        {"pattern": "Microsoft Open Source", "tool": "Bot"},
        {"pattern": "gh-action-bump-version@users.noreply.github.com", "tool": "github actions"},
        {"pattern": "sentry-autofix\\[bot\\]", "tool": "Bot"},
    ]
    for expected in expected_samples:
        assert any(
            row["pattern"] == expected["pattern"] and row["tool"] == expected["tool"]
            for row in upstream_rows
        ), f"upstream row {expected} not found verbatim in the first 84 rows"
    # Exact duplicate rows in the upstream source (e.g. dotnet-maestro\[bot\]
    # appears twice, pytorchbot appears twice with the same tool,
    # microsoft-github-policy-service\[bot\] appears twice with *different*
    # tool values) are kept verbatim rather than deduplicated -- citation
    # fidelity to the messy real source, not a cleaned-up derivative.
    assert [r["pattern"] for r in upstream_rows].count("dotnet-maestro\\[bot\\]") == 2
    assert [r["pattern"] for r in upstream_rows].count("pytorchbot") == 2
    policy_service_tools = {
        r["tool"]
        for r in upstream_rows
        if r["pattern"] == "microsoft-github-policy-service\\[bot\\]"
    }
    assert policy_service_tools == {"microsoft", "Bot"}
    # Last upstream row (line 85 of the source file) must be the final row
    # of the 84-row block, proving the appended rows come strictly after it.
    assert upstream_rows[-1] == {"pattern": "sentry-autofix\\[bot\\]", "tool": "Bot"}


def test_bots_csv_our_additions_are_appended_after_upstream_block():
    """This project's own bot-pattern additions must be a short, explicit
    list of individually-verified real accounts, not a generic catch-all
    (e.g. NOT a bare "\\[bot\\]" wildcard) -- see agent-detection.md's Known
    Limitations for why that tradeoff was deliberately made."""
    rows = _read_bots_csv_rows()
    our_additions = rows[84:]
    assert our_additions == [
        {"pattern": "copilot-swe-agent\\[bot\\]", "tool": "Bot"},
        {"pattern": "anthropic-code-agent\\[bot\\]", "tool": "Bot"},
    ]


def test_bot_patterns_loaded_as_flat_list_in_original_order():
    data = load_agent_heuristics()
    bot_patterns = data["bot_patterns"]
    assert isinstance(bot_patterns, list) and bot_patterns
    assert bot_patterns[0] == "dependabot\\[bot\\]"
    assert bot_patterns[-1] == "anthropic-code-agent\\[bot\\]"
    assert len(bot_patterns) == 86


def _read_files_csv_rows():
    with _FILES_CSV_PATH.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(_non_comment_lines(fh)))


def test_files_csv_schema_matches_upstream():
    """agent_files.csv deliberately mirrors labri-progress/agent-mining's
    own files.csv column schema, so a reviewer can diff the two files
    directly."""
    with _FILES_CSV_PATH.open("r", encoding="utf-8", newline="") as fh:
        header = next(csv.reader(fh))
    assert header == ["pattern", "tool", "start_date", "end_date"]


def test_files_csv_has_boundary_comment_line():
    with _FILES_CSV_PATH.open("r", encoding="utf-8") as fh:
        raw_lines = fh.readlines()
    comment_lines = [line for line in raw_lines if line.lstrip().startswith("#")]
    assert len(comment_lines) == 1
    assert "own additions" in comment_lines[0]
    assert "snapshotted verbatim on" in comment_lines[0]


def test_files_csv_first_95_rows_are_upstream_verbatim():
    """The file's first 95 data rows must be labri-progress/agent-mining's
    files.csv content, unmodified and in its original order -- this is the
    whole point of the CSV (a reviewer-checkable citation), not just a
    convenient format. Spot-checks a sample spanning the full file rather
    than asserting all 95 rows verbatim, so the test doesn't itself become
    an unreadable copy of the source file."""
    rows = _read_files_csv_rows()
    upstream_rows = rows[:95]
    assert len(upstream_rows) == 95
    expected_samples = [
        {"pattern": "CLAUDE.md", "tool": "Claude Code"},
        {"pattern": "AGENTS.md", "tool": "Generic"},
        {"pattern": ".copilot-*.md", "tool": "Copilot"},
        {"pattern": ".superpowers/", "tool": "Superpowers"},
    ]
    for expected in expected_samples:
        assert any(
            row["pattern"] == expected["pattern"] and row["tool"] == expected["tool"]
            for row in upstream_rows
        ), f"upstream row {expected} not found verbatim in the first 95 rows"
    # Last upstream row (line 96 of the source file) must be the final row
    # of the 95-row block, proving the appended rows come strictly after it.
    assert upstream_rows[-1] == {
        "pattern": ".superpowers/",
        "tool": "Superpowers",
        "start_date": "",
        "end_date": "",
    }


def test_files_csv_our_additions_are_appended_after_upstream_block():
    rows = _read_files_csv_rows()
    our_additions = rows[95:]
    added_patterns = {row["pattern"] for row in our_additions}
    assert added_patterns == {
        "claude.config",
        ".cursor",
        ".cursorignore",
        "cursor.config",
        ".copilot-instructions.md",
        ".openhands.config",
        ".openhands",
        ".devin.config",
        ".devin",
        ".cline.config",
        ".cline",
    }


def test_files_csv_every_tool_has_agent_type_mapping():
    rows = _read_files_csv_rows()
    assert rows, "agent_files.csv must have at least one data row"
    for row in rows:
        assert row["tool"] in _TOOL_TO_AGENT_TYPE, (
            f"tool {row['tool']!r} (pattern {row['pattern']!r}) has no "
            "_TOOL_TO_AGENT_TYPE mapping in collection/heuristics/__init__.py"
        )


def test_file_based_loaded_covers_new_upstream_only_agents():
    """Sanity check that agents introduced solely by agent_files.csv (never
    present in agent_authors.csv/bots.csv) actually make it into the merged
    file_based dict, not just parsed and discarded."""
    data = load_agent_heuristics()
    assert data["file_based"]["augment_code"] == [
        ".augment/",
        ".augmentignore",
        ".augment-guidelines",
    ]
    assert ".superpowers/" in data["file_based"]["superpowers"]
