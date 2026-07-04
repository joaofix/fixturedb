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
    assert data["file_based"]["codex"] == ["AGENTS.md"]
    assert data["file_based"]["windsurf"] == [".windsurfrules"]
    assert data["file_based"]["roo_code"] == [".roorules"]


def test_cursorrules_only_under_cursor_not_claude():
    """Regression: .cursorrules was previously copy-pasted into claude's list too."""
    data = load_agent_heuristics()
    assert ".cursorrules" not in data["file_based"]["claude"]
    assert ".cursorrules" in data["file_based"]["cursor"]
