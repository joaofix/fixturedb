import subprocess
from pathlib import Path

from collection.agent_signal_primitives import AgentCommitVerifier
from collection.tiered_agent_corpus_scanner import (
    _BOT,
    AGENT_TRAILER_RE,
    Tier1RepositoryScanner,
    _is_test_file_path,
)


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
    """Regression: this module used to have its own independent copy of
    is_test_file_path that drifted from test_commit_utils.py's version --
    a false-positive fix there (bare suffixes like "IT.java"/"test.js"
    matching unrelated files) was never applied here. Now it delegates, so
    the same boundary cases must hold true here too."""
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
    agent = scanner._detect_agent_in_commit("Alice", "alice@anthropic.com", "")
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
    """Regression test: codex/roo_code previously had zero commit_signatures
    entries (file_based only), so they could never be detected via author
    identity or trailers -- only by scanning the repo's file tree."""
    scanner = Tier1RepositoryScanner(Path("/tmp"))

    assert scanner._detect_agent_in_commit("Someone", "codex@openai.com", "") == "codex"

    body = "Fix bug\n\nCo-authored-by: Roo Code <roomote@roocode.com>"
    assert (
        scanner._detect_agent_in_commit("Someone", "someone@example.com", body)
        == "roo_code"
    )


def test_detect_agent_word_boundary_rejects_compound_word_collision():
    """Regression test: a bare substring check on author name/email
    incorrectly matched the "cline"/"devin" agent keywords inside unrelated
    compound words/surnames (e.g. "McLine"). Word-boundary matching fixes
    this class of false positive (though not the case of an exact common
    first name -- see test_detect_agent_exact_name_collision_is_a_known_limitation)."""
    scanner = Tier1RepositoryScanner(Path("/tmp"))
    assert (
        scanner._detect_agent_in_commit("Sean McLine", "smcline@example.com", "")
        is None
    )


def test_detect_agent_exact_name_collision_is_a_known_limitation():
    """Documents a known, inherent limitation (not something this fix
    resolves): a human author whose name is an exact match for an agent's
    bare-word signature (e.g. "Devin") is still misattributed when there's
    no trailer to disambiguate, since word boundaries only rule out
    partial/compound-word matches, not whole-word name collisions. See
    agent_heuristics.yaml's module comment. When a trailer IS present, see
    test_detect_agent_trailer_overrides_author_name_collision below --
    that case is resolved."""
    scanner = Tier1RepositoryScanner(Path("/tmp"))
    assert (
        scanner._detect_agent_in_commit("Devin Smith", "devin.smith@gmail.com", "")
        == "devin"
    )


def test_detect_agent_trailer_overrides_author_name_collision():
    """Regression: _detect_agent_in_commit used to check author identity
    before the commit trailer, so a human author whose name collides with
    an agent keyword (e.g. "Devin Smith") was misattributed to that agent
    even when the commit carried a correct, unambiguous trailer crediting a
    *different* real agent. Trailer is now checked before author identity
    specifically because it's the less collision-prone signal -- a
    deliberate, structured convention only agents/tooling emit, unlike a
    freely-editable author-name field a human can also happen to share."""
    scanner = Tier1RepositoryScanner(Path("/tmp"))
    body = "Fix bug\n\nCo-authored-by: Claude <claude@anthropic.com>"
    assert (
        scanner._detect_agent_in_commit("Devin Smith", "devin.smith@gmail.com", body)
        == "claude"
    )


def test_agent_commit_verifier_trailer_overrides_author_name_collision():
    """Same regression as test_detect_agent_trailer_overrides_author_name_collision,
    exercised through AgentCommitVerifier (Tier 2). This path already
    checked trailer before author identity prior to this fix -- kept here
    as an explicit lock-in test alongside Tier 1's, so both detectors are
    covered for the same scenario."""
    from collection.agent_signal_primitives import AgentCommitVerifier

    verifier = AgentCommitVerifier(clones_dir=Path("/tmp"))
    result = verifier._detect_agent_in_commit(
        {
            "sha": "abc123",
            "author_name": "Devin Smith",
            "author_email": "devin.smith@gmail.com",
            "message": "Fix bug\n\nCo-authored-by: Claude <claude@anthropic.com>",
        }
    )
    assert result == "claude"


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


def test_agent_commit_verifier_bot_status_overrides_coincidental_trailer():
    """Regression: AgentCommitVerifier._detect_agent_in_commit (Tier 2)
    used to check the trailer before bot status, so a bot-authored commit
    whose message happened to contain an agent-style trailer was
    misattributed to that agent instead of being excluded as bot -- verified
    by direct reproduction before this fix (dependabot[bot] + a
    "Generated-by: Claude" line in the body returned "claude", not None).
    Bot status is now checked first, matching Tier 1's already-correct
    behavior for the same scenario."""
    from collection.agent_signal_primitives import AgentCommitVerifier

    verifier = AgentCommitVerifier(clones_dir=Path("/tmp"))
    result = verifier._detect_agent_in_commit(
        {
            "sha": "abc123",
            "author_name": "dependabot[bot]",
            "author_email": "dependabot@users.noreply.github.com",
            "message": "Bump lodash from 1.0 to 2.0\n\nGenerated-by: Claude <claude@anthropic.com>",
        }
    )
    assert result is None


def test_agent_trailer_re_tolerates_missing_hyphens():
    """Regression test: some agents emit "Coauthored-by"/"Co-authoredby"/
    "Coauthoredby" trailers with a hyphen missing on either side of "by" --
    a real, empirically observed variant (see labri-progress/agent-mining's
    _iter_coauthors(), which uses the same co-?authored-?by pattern). The
    previous regex required the literal "co-authored-by" and silently
    missed all three variants."""
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
    """Same regression, exercised end-to-end through both detection paths
    (Tier1RepositoryScanner and AgentCommitVerifier)."""
    from collection.agent_signal_primitives import AgentCommitVerifier

    body = "Fix bug\n\nCoauthoredby: Claude <claude@anthropic.com>"

    scanner = Tier1RepositoryScanner(Path("/tmp"))
    assert scanner._detect_agent_in_commit("Someone", "someone@example.com", body) == "claude"

    verifier = AgentCommitVerifier(clones_dir=Path("/tmp"))
    assert (
        verifier._detect_agent_in_commit(
            {
                "sha": "abc123",
                "author_name": "Someone",
                "author_email": "someone@example.com",
                "message": body,
            }
        )
        == "claude"
    )


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
    agent = scanner._detect_agent_in_commit("Alice", "alice@anthropic.com", "")
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


def test_agent_commit_verifier_ignores_prose_mentions_in_commit_message():
    """Regression test: AgentCommitVerifier._detect_agent_in_commit used to
    fall back to scanning the entire free-text commit message body, so a
    prose mention of an agent's name with no real trailer (or an unrelated
    word coinciding with an agent's keyword) was misattributed as agent
    authorship. Only the trailer/author-identity fields are legitimate
    signal."""
    verifier = AgentCommitVerifier(clones_dir=Path("/tmp"))

    assert (
        verifier._detect_agent_in_commit(
            {
                "sha": "abc123",
                "author_name": "Alice Human",
                "author_email": "alice@example.com",
                "message": (
                    "Revert a bad Claude suggestion from last week's PR\n\n"
                    "This undoes the regression."
                ),
            }
        )
        is None
    )

    assert (
        verifier._detect_agent_in_commit(
            {
                "sha": "def456",
                "author_name": "Bob Human",
                "author_email": "bob@example.com",
                "message": "Fix cursor blinking bug in the text editor widget",
            }
        )
        is None
    )


def test_agent_commit_verifier_word_boundary_rejects_compound_word_collision():
    """Regression test: same word-boundary fix as Tier1RepositoryScanner,
    applied to AgentCommitVerifier's author name/email check."""
    verifier = AgentCommitVerifier(clones_dir=Path("/tmp"))
    assert (
        verifier._detect_agent_in_commit(
            {
                "sha": "abc123",
                "author_name": "Sean McLine",
                "author_email": "smcline@example.com",
                "message": "Refactor build script",
            }
        )
        is None
    )


def test_agent_commit_verifier_detects_trailers(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "-b", "main", str(repo)], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "a@b.com"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "A"],
        check=True,
        capture_output=True,
    )
    (repo / "f.py").write_text("x = 1\n")
    subprocess.run(
        ["git", "-C", str(repo), "add", "f.py"], check=True, capture_output=True
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "commit",
            "-m",
            "feat\n\nCo-authored-by: Claude <claude@anthropic.com>",
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "b@b.com"],
        check=True,
        capture_output=True,
    )
    (repo / "g.py").write_text("y = 2\n")
    subprocess.run(
        ["git", "-C", str(repo), "add", "g.py"], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "fix"],
        check=True,
        capture_output=True,
    )

    verifier = AgentCommitVerifier(clones_dir=tmp_path)
    result = verifier.verify_repository(str(repo.name), start_date="2020-01-01")

    assert result.total_agent_commits == 1
    assert result.repo_name == repo.name
    assert list(result.agent_commits.values()) == ["claude"]
