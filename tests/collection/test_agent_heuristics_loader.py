"""Guardrail tests for the agent heuristics YAML catalog and its loader.

These exist to catch a malformed future edit to agent_heuristics.yaml
(typo, empty list, missing key) -- not to test detection logic itself,
which is covered by test_agent_patterns_extra.py / test_agent_patterns_thorough.py.
"""

from collection.heuristics import load_agent_heuristics


def test_loader_returns_expected_top_level_keys():
    data = load_agent_heuristics()
    assert set(data.keys()) == {"file_based", "commit_signatures", "paper_scope"}


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
