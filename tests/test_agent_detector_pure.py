import subprocess
from pathlib import Path

from collection.tiered_agent_corpus_scanner import (
    _BOT,
    Tier1RepositoryScanner,
    _is_test_file_path,
)
from collection.utils import AGENT_TRAILER_RE


def test_is_test_file_path_python_cases():
    # typical test paths
    assert _is_test_file_path("tests/test_foo.py", "python")
    assert _is_test_file_path("test_utils.py", "python")
    assert _is_test_file_path("conftest.py", "python")
    assert _is_test_file_path("some/dir/tests/test_bar.py", "python")

    # non-test files
    assert not _is_test_file_path("src/main.py", "python")
    assert not _is_test_file_path("", "python")


def test_is_test_file_path_delegates_to_shared_boundary_fix():
    """is_test_file_path delegates to the shared implementation in test_commit_utils,
    so the same boundary cases hold here."""
    assert not _is_test_file_path("src/main/java/com/example/Deposit.java", "java")
    assert not _is_test_file_path("src/main/java/com/example/Credit.java", "java")
    assert not _is_test_file_path("src/latest.js", "javascript")
    assert not _is_test_file_path("src/contest.js", "javascript")
    assert _is_test_file_path(
        "src/main/java/com/example/OrderServiceIT.java", "java"
    )


def test_detect_agent_in_commit_author_and_coauthor():
    scanner = Tier1RepositoryScanner(Path("/tmp"))

    # author email containing keyword
    # Uses one of the catalog's specific upstream Claude Code service
    # addresses (not a bare "anthropic" domain match -- that project-added
    # pattern was removed after it caused a real false positive on an
    # Anthropic employee's personal commit; see
    # test_bare_anthropic_domain_no_longer_matches_claude).
    agent = scanner._detect_agent_in_commit("Alice", "claude@anthropic.com", "")
    assert agent == "claude"

    # author name containing keyword
    agent2 = scanner._detect_agent_in_commit("GitHub Copilot", "bot@example.com", "")
    assert agent2 == "copilot"

    # co-authored-by trailer detection
    body = "Some message\nCo-authored-by: GitHub Copilot <copilot@github.com>\n"
    matches = AGENT_TRAILER_RE.findall(body)
    assert any("copilot" in m.lower() for m in matches)
    agent3 = scanner._detect_agent_in_commit("Someone", "someone@example.com", body)
    assert agent3 == "copilot"

    # assisted-by trailer detection
    body2 = "Some message\nAssisted-by: Claude <claude@anthropic.com>\n"
    matches2 = AGENT_TRAILER_RE.findall(body2)
    assert any("claude" in m.lower() for m in matches2)
    agent4 = scanner._detect_agent_in_commit("Someone", "someone@example.com", body2)
    assert agent4 == "claude"

    # generated-by trailer detection
    body3 = "Some message\nGenerated-by: Cursor <cursor@anysoftware.io>\n"
    matches3 = AGENT_TRAILER_RE.findall(body3)
    assert any("cursor" in m.lower() for m in matches3)
    agent5 = scanner._detect_agent_in_commit("Someone", "someone@example.com", body3)
    assert agent5 == "cursor"


def test_detect_agent_no_match():
    scanner = Tier1RepositoryScanner(Path("/tmp"))
    assert (
        scanner._detect_agent_in_commit("Bob", "bob@example.com", "no agents here")
        is None
    )


def test_detect_codex_and_roo_code_via_commit_signatures():
    """codex and roo_code have commit signatures, so they are detected from author
    identity and trailers, not only from the repository's file tree."""
    scanner = Tier1RepositoryScanner(Path("/tmp"))

    assert scanner._detect_agent_in_commit("Someone", "codex@openai.com", "") == "codex"

    body = "Fix bug\n\nCo-authored-by: Roo Code <roomote@roocode.com>"
    assert (
        scanner._detect_agent_in_commit("Someone", "someone@example.com", body)
        == "roo_code"
    )


def test_detect_agent_word_boundary_rejects_compound_word_collision():
    """A keyword does not match inside a longer word or a surname. For example,
    "gemini" does not match "McGeminicorp". Exact whole-word collisions with common
    first names are handled by known_human_collisions.csv."""
    scanner = Tier1RepositoryScanner(Path("/tmp"))
    assert (
        scanner._detect_agent_in_commit(
            "Gina McGeminicorp", "gmcgeminicorp@example.com", ""
        )
        is None
    )


def test_devin_cline_exact_name_collision_is_fixed():
    """The bare "devin" and "cline" patterns are not in the catalog. A person named
    Devin, or a Cline employee using a @cline.bot address, is not classified as an
    agent. The Devin bot identity "devin-ai-integration" is still matched."""
    scanner = Tier1RepositoryScanner(Path("/tmp"))
    assert (
        scanner._detect_agent_in_commit("Devin Smith", "devin.smith@gmail.com", "")
        is None
    )
    assert (
        scanner._detect_agent_in_commit("Aiden Cline", "aidenpcline@gmail.com", "")
        is None
    )
    # The real bot identity still matches -- this fix removes the collision-
    # prone bare "devin" pattern, not the safe, specific one.
    assert (
        scanner._detect_agent_in_commit(
            "devin-ai-integration[bot]",
            "158243242+devin-ai-integration[bot]@users.noreply.github.com",
            "",
        )
        == "devin"
    )


def test_detect_agent_trailer_overrides_author_name_collision():
    """A commit trailer is checked before the author name. A human whose name matches
    an agent keyword is not classified as that agent when the commit carries a
    trailer for a different agent."""
    scanner = Tier1RepositoryScanner(Path("/tmp"))
    body = "Fix bug\n\nCo-authored-by: Claude <claude@anthropic.com>"
    assert (
        scanner._detect_agent_in_commit("Devin Smith", "devin.smith@gmail.com", body)
        == "claude"
    )


def test_detect_agent_bot_status_overrides_coincidental_trailer():
    """A bot-authored commit whose message happens to contain an
    agent-style trailer (e.g. templated tooling stamping a "Generated-by:"
    line onto a dependency-bump commit) must still be excluded as bot, not
    misattributed to that agent. Bot status is checked before the trailer
    for exactly this reason."""
    scanner = Tier1RepositoryScanner(Path("/tmp"))
    body = "Bump lodash from 1.0 to 2.0\n\nGenerated-by: Claude <claude@anthropic.com>"
    assert (
        scanner._detect_agent_in_commit(
            "dependabot[bot]", "dependabot@users.noreply.github.com", body
        )
        is _BOT
    )


def test_agent_trailer_re_tolerates_missing_hyphens():
    """The trailer pattern matches "Co-authored-by", "Coauthored-by", "Co-authoredby"
    and "Coauthoredby"."""
    for trailer in (
        "Co-authored-by",
        "Coauthored-by",
        "Co-authoredby",
        "Coauthoredby",
    ):
        body = f"Fix bug\n\n{trailer}: Claude <claude@anthropic.com>"
        matches = AGENT_TRAILER_RE.findall(body)
        assert matches == ["Claude <claude@anthropic.com>"], trailer


def test_detect_agent_tolerates_missing_hyphens_in_trailer():
    """Same regression, exercised end-to-end through Tier1RepositoryScanner."""
    body = "Fix bug\n\nCoauthoredby: Claude <claude@anthropic.com>"

    scanner = Tier1RepositoryScanner(Path("/tmp"))
    assert scanner._detect_agent_in_commit("Someone", "someone@example.com", body) == "claude"


def test_detect_agent_bot_authors_are_excluded():
    scanner = Tier1RepositoryScanner(Path("/tmp"))

    # swe-agent bot: author name contains [bot] and also contains copilot keyword
    assert (
        scanner._detect_agent_in_commit(
            "copilot-swe-agent[bot]", "198982749+Copilot@users.noreply.github.com", ""
        )
        is _BOT
    )

    # anthropic-code-agent bot
    assert (
        scanner._detect_agent_in_commit(
            "anthropic-code-agent[bot]", "242468646+Claude@users.noreply.github.com", ""
        )
        is _BOT
    )

    # github-actions bot
    assert (
        scanner._detect_agent_in_commit(
            "github-actions[bot]", "github-actions[bot]@users.noreply.github.com", ""
        )
        is _BOT
    )

    # Regular author with bot-like email but no [bot] in name should still be checked
    # Uses one of the catalog's specific upstream Claude Code service
    # addresses (not a bare "anthropic" domain match -- that project-added
    # pattern was removed after it caused a real false positive on an
    # Anthropic employee's personal commit; see
    # test_bare_anthropic_domain_no_longer_matches_claude).
    agent = scanner._detect_agent_in_commit("Alice", "claude@anthropic.com", "")
    assert agent == "claude"

    # Bot name without agent keyword should also be excluded
    assert (
        scanner._detect_agent_in_commit(
            "dependabot[bot]", "dependabot@users.noreply.github.com", ""
        )
        is _BOT
    )

    # But non-bot with copilot keyword should still match
    agent2 = scanner._detect_agent_in_commit("GitHub Copilot", "copilot@github.com", "")
    assert agent2 == "copilot"


def test_detect_agent_multiple_coauthors():
    scanner = Tier1RepositoryScanner(Path("/tmp"))
    body = (
        "Fixes\nCo-authored-by: GitHub Copilot <copilot@github.com>\n"
        "Co-authored-by: Anthropic Claude <claude@anthropic.com>\n"
    )
    # Should detect the first matching agent in coauthor scanning order
    agent = scanner._detect_agent_in_commit("Someone", "someone@example.com", body)
    assert agent in {"copilot", "claude"}


def test_scan_repo_commit_roles_parses_multiline_git_log(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "-b", "main", str(repo)], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "Alice <alice@example.com>"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "Alice"],
        check=True,
        capture_output=True,
    )
    (repo / "a.txt").write_text("hello\n")
    subprocess.run(
        ["git", "-C", str(repo), "add", "a.txt"], check=True, capture_output=True
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "commit",
            "-m",
            "Fix pipes | in body\nSecond line\nCo-authored-by: Claude <claude@example.com>",
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "Bob <bob@example.com>"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "Bob"],
        check=True,
        capture_output=True,
    )
    (repo / "b.txt").write_text("world\n")
    subprocess.run(
        ["git", "-C", str(repo), "add", "b.txt"], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "Regular commit"],
        check=True,
        capture_output=True,
    )

    scanner = Tier1RepositoryScanner(Path("/tmp"))
    commits = scanner.scan_repo_commit_roles(repo, start_date="2020-01-01")

    assert len(commits) == 2
    assert commits[0].commit_sha != commits[1].commit_sha
    assert commits[0].author_name == "Alice"
    assert commits[1].author_name == "Bob"
    assert commits[0].agent_type == "claude"
    assert commits[1].agent_type is None


def test_scan_repo_commit_roles_excludes_bot_authors(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "-b", "main", str(repo)], check=True, capture_output=True
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "config",
            "user.email",
            "dependabot[bot]@users.noreply.github.com",
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "dependabot[bot]"],
        check=True,
        capture_output=True,
    )
    (repo / "test_foo.py").write_text("def test_foo(): pass\n")
    subprocess.run(
        ["git", "-C", str(repo), "add", "test_foo.py"], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "chore: update pytest"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "config",
            "user.email",
            "alice@example.com",
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "Alice"],
        check=True,
        capture_output=True,
    )
    (repo / "test_bar.py").write_text("def test_bar(): pass\n")
    subprocess.run(
        ["git", "-C", str(repo), "add", "test_bar.py"], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "test: add test_bar"],
        check=True,
        capture_output=True,
    )

    scanner = Tier1RepositoryScanner(Path("/tmp"))
    commits = scanner.scan_repo_commit_roles(
        repo, start_date="2020-01-01", language="python", detect_test_files=True
    )

    assert len(commits) == 1
    assert commits[0].author_name == "Alice"
    assert commits[0].commit_role == "human"
    assert commits[0].is_test_commit is True


def test_is_test_file_path_javascript():
    assert _is_test_file_path("__tests__/my.test.js", "javascript")
    assert _is_test_file_path("spec/my.spec.js", "javascript")
    assert not _is_test_file_path("lib/foo.js", "javascript")


def test_known_human_collision_excludes_author_identity_match():
    """A named human in known_human_collisions.csv is not matched by the author-name
    check, even when the name equals an agent keyword."""
    from collection.utils import detect_agent_in_commit

    assert (
        detect_agent_in_commit("Claude Paroz", "claude@2xlibre.net", "Fix a bug")
        is None
    )


def test_known_human_collision_does_not_override_a_real_trailer():
    """A known human collision only suppresses author-identity matching
    (steps 3/4) -- a genuine trailer on one of their commits is a
    deliberate, structured signal and still counts."""
    from collection.utils import detect_agent_in_commit

    body = "Fix a bug\n\nCo-authored-by: GitHub Copilot <copilot@github.com>"
    assert (
        detect_agent_in_commit("Claude Paroz", "claude@2xlibre.net", body)
        == "copilot"
    )


def test_known_human_collision_excludes_placeholder_bot_identity():
    """The placeholder identity codex-review@example.com is not matched as Codex by
    the author-name check. Real Codex commits carry a trailer, so they still match."""
    from collection.utils import detect_agent_in_commit

    assert (
        detect_agent_in_commit(
            "Codex Review", "codex-review@example.com", "Automated review pass"
        )
        is None
    )


def test_known_human_collision_placeholder_bot_does_not_override_a_real_trailer():
    """Same as test_known_human_collision_does_not_override_a_real_trailer,
    for the codex-review@example.com exclusion."""
    from collection.utils import detect_agent_in_commit

    body = "Automated review pass\n\nCo-authored-by: Claude <claude@anthropic.com>"
    assert (
        detect_agent_in_commit("Codex Review", "codex-review@example.com", body)
        == "claude"
    )


def test_bare_anthropic_domain_no_longer_matches_claude():
    """The author catalog has no bare "anthropic" pattern. Specific service addresses
    such as claude@anthropic.com still match."""
    from collection.utils import detect_agent_in_commit

    assert (
        detect_agent_in_commit("Ashwin Bhat", "ashwin@anthropic.com", "Fix a bug")
        is None
    )
    assert (
        detect_agent_in_commit("Someone", "claude@anthropic.com", "") == "claude"
    )
