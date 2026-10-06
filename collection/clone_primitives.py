"""Lowest-level clone primitive: subprocess `git clone` into a fresh tempdir.

No DB, no throttling, no config — just clone-to-tempdir plus credential-gated
(private repo) failure detection. Two other modules build on this:
`ephemeral_clone.py` wraps it with throttling/disk-safety/cleanup context
managers for transient inspection, and `persistent_clone.py` is an independent,
DB-tracked workflow for the durable corpus clone directory.

`clone_repo_for_commit_scan` accepts an optional `shallow_since` date to bound
the fetched history (`--shallow-since=`) for callers that only need commits
from some date onward. This module stays config-free -- callers compute the
actual date (e.g. via `collection.config.shallow_clone_since`) and pass it in.
A shallow clone is verified locally (`_shallow_clone_is_truncated`) before
being trusted, falling back to a full clone if the shallow boundary would
have silently cut off in-window history.
"""

from __future__ import annotations

import base64
import os
import re
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path


class CloneUnavailable(Exception):
    """Raised by `clone_to_tempdir` when a repo could not be cloned after
    retrying, for a reason that is NOT a confirmed permanent condition
    (private/deleted repo, detected via `_output_requests_credentials` --
    that case still returns `(None, None)`, unchanged). A network blip, DNS
    failure, or a sustained outage all raise this instead of returning
    `(None, None)`, so a caller can tell "we don't actually know if this
    repo is cloneable" apart from "confirmed: it isn't" -- callers must
    not treat the two the same way (e.g. checkpointing a repo as
    permanently done because of a transient failure silently hides it from
    every future run; see test_commit_filter.py
    for where this bit a real Dataset B collection when the network dropped
    mid-run)."""


CREDENTIAL_PROMPT_PATTERNS = [
    re.compile(r"Username.*:", re.IGNORECASE),
    re.compile(r"Password.*:", re.IGNORECASE),
    re.compile(r"Personal access token.*:", re.IGNORECASE),
    re.compile(r"repository.*not found", re.IGNORECASE),
    re.compile(r"does not exist", re.IGNORECASE),
    re.compile(r"remote: Repository not found", re.IGNORECASE),
    re.compile(r"fatal: could not read Username", re.IGNORECASE),
    re.compile(r"Authentication failed", re.IGNORECASE),
    re.compile(r"PERMISSION_DENIED", re.IGNORECASE),
]


# git's stderr when GitHub throttles or blocks an anonymous clone (HTTP 429, or a
# secondary/abuse limit). A throttled clone is transient: it is retried, and it is
# never a permanent refusal, even when the same output also contains a credential
# prompt, which git prints when the server refuses the request.
# Patterns are specific on purpose: a bare "429" or "abuse" could be part of a
# repository name in the URL, which would make a deleted repository look transient.
THROTTLE_PATTERNS = [
    re.compile(r"returned error: 429", re.IGNORECASE),
    re.compile(r"\bHTTP/[\d.]+ 429\b"),
    re.compile(r"too many requests", re.IGNORECASE),
    re.compile(r"secondary rate limit", re.IGNORECASE),
    re.compile(r"rate limit exceeded", re.IGNORECASE),
    re.compile(r"abuse detection", re.IGNORECASE),
]


def _output_is_throttled(stderr: str) -> bool:
    """True if stderr says GitHub throttled the request (retry, do not give up)."""
    return any(pattern.search(stderr) for pattern in THROTTLE_PATTERNS)


def _output_requests_credentials(stderr: str) -> bool:
    """Check if stderr output indicates a credential prompt or private repo error."""
    for pattern in CREDENTIAL_PROMPT_PATTERNS:
        if pattern.search(stderr):
            return True
    return False


def _no_prompt_env() -> dict[str, str]:
    """Env for any git subprocess that talks to a remote (clone/fetch/
    ls-remote) -- makes git fail immediately on a private/deleted/renamed
    repo instead of blocking on an interactive Username/Password prompt.
    GIT_TERMINAL_PROMPT=0 is git's own documented switch for this; its
    failure message ("fatal: could not read Username...") is already one of
    CREDENTIAL_PROMPT_PATTERNS above, so existing detection fires quickly.
    Without this, a blocked repo would use up to timeout*(retries+1), about 20
    minutes, before clone_to_tempdir() gave up. GIT_ASKPASS=echo is defense in
    depth against a configured credential.helper trying some other prompt
    channel. Reads os.environ fresh (not module-level) so tests can
    monkeypatch it, and so PATH/etc. stay intact -- git still needs to be
    findable."""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "echo"}
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        # Authenticated clones. Anonymous git-over-HTTPS requests are rejected
        # under load ("could not read Username"), which the credential check
        # below reads as a permanently private or deleted repository. The header
        # goes in the environment, not argv, same as rq1_prevalence_scan's
        # github_auth_env().
        basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        env.update(
            {
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "http.extraHeader",
                "GIT_CONFIG_VALUE_0": f"Authorization: Basic {basic}",
            }
        )
    return env


def run_git_no_prompt(
    args: list[str], *, extra_env: dict[str, str] | None = None, **kwargs
) -> subprocess.CompletedProcess:
    """subprocess.run() for a git command that touches a remote (clone/
    fetch/ls-remote) -- never blocks on a credential prompt. `stdin=DEVNULL`
    is belt-and-suspenders alongside `_no_prompt_env()`'s env vars: even if
    something still tried to prompt, there's no input to read. `kwargs`
    forwards timeout=/cwd=/capture_output=/text=/check= as each call site
    already passes them. Local-only git commands (cat-file, rev-list, plain
    checkout) never contact a remote and don't need this -- only
    clone/fetch/ls-remote do.

    `extra_env`, when given, is merged on top of `_no_prompt_env()` --
    e.g. an authenticated caller's `GIT_CONFIG_COUNT`/`GIT_CONFIG_KEY_0`/
    `GIT_CONFIG_VALUE_0` trio injecting an `Authorization` header (see
    `rq1_prevalence_scan.py`'s `_github_auth_env()`). Deliberately an env
    var, not a `-c http.extraHeader=...` CLI flag or a token embedded in
    the URL -- either of those would land in this process's argv, visible
    to any other user on a shared server via a plain `ps aux`/`ps -ef`;
    environment variables aren't."""
    env = _no_prompt_env()
    if extra_env:
        env.update(extra_env)
    return subprocess.run(args, env=env, stdin=subprocess.DEVNULL, **kwargs)


def clone_to_tempdir(
    repo_full_name: str,
    clone_url: str,
    clone_args: list[str],
    *,
    timeout: int,
    prefix: str,
    retries: int = 2,
    backoff_base: float = 3.0,
) -> tuple[Path | None, Path | None]:
    """Clone a repo into a temporary directory and return (repo_path, temp_root).

    The caller is responsible for removing `temp_root` with `cleanup_tempdir()`.

    A credential prompt (private/deleted repo -- see
    `_output_requests_credentials`) is a confirmed, permanent condition and
    returns `(None, None)` immediately, no retry. A throttling response from
    GitHub (see `_output_is_throttled`) is never treated as that: it is
    transient, even when git also prints a credential prompt. Any other failure (network
    error, timeout, transient GitHub 5xx) is retried up to `retries` times
    with exponential backoff; if every attempt fails, raises
    `CloneUnavailable` instead of returning `(None, None)` -- a generic
    "confirmed None" here would be indistinguishable from a repo genuinely
    having nothing to clone, and a caller that checkpoints on that basis
    would silently and permanently miscategorize a repo that was never
    actually reached (see `CloneUnavailable`'s docstring). `retries` only
    defends against a brief blip within one call -- it will not survive a
    sustained outage; recovering from that is the checkpoint layer's job.

    The raised `CloneUnavailable` carries the last attempt's failure reason
    (stderr, timeout or exception text), so the cause is visible.
    """
    owner, name = repo_full_name.split("/")
    last_error = "unknown error"

    for attempt in range(retries + 1):
        temp_root = Path(tempfile.mkdtemp(prefix=prefix))
        repo_path = temp_root / f"{owner}__{name}"

        try:
            result = run_git_no_prompt(
                ["git", "clone", *clone_args, clone_url, str(repo_path)],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode == 0:
                return repo_path, temp_root
            if not _output_is_throttled(result.stderr) and _output_requests_credentials(result.stderr):
                cleanup_tempdir(temp_root)
                return None, None
            last_error = (result.stderr or "").strip()[-500:] or f"git exited {result.returncode}"
        except KeyboardInterrupt:
            cleanup_tempdir(temp_root)
            raise
        except subprocess.TimeoutExpired:
            last_error = f"timed out after {timeout}s"
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"

        cleanup_tempdir(temp_root)
        if attempt < retries:
            time.sleep(backoff_base * (2**attempt))

    raise CloneUnavailable(
        f"clone failed after {retries + 1} attempt(s): {repo_full_name} -- "
        f"last error: {last_error}"
    )


def cleanup_tempdir(temp_root: Path | None) -> None:
    """Delete the temporary clone root directory if it exists."""
    if temp_root is not None:
        shutil.rmtree(temp_root, ignore_errors=True)


def _true_parents(repo_dir: Path, sha: str) -> list[str]:
    """Parent SHAs of `sha` read from the raw commit object via `cat-file -p`.

    This survives a shallow graft: git's traversal (`log`, `rev-list`, ...)
    treats a `.git/shallow`-listed commit as having no parents, but the raw
    object it points to still has the real `parent` line(s).
    """
    result = subprocess.run(
        ["git", "-C", str(repo_dir), "cat-file", "-p", sha],
        capture_output=True,
        text=True,
    )
    parents = []
    for line in result.stdout.splitlines():
        if line.startswith("parent "):
            parents.append(line.split()[1])
        elif line.startswith("tree "):
            continue
        else:
            break
    return parents


def _object_present_locally(repo_dir: Path, sha: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(repo_dir), "cat-file", "-e", sha],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _commit_committer_date(repo_dir: Path, sha: str) -> datetime | None:
    result = subprocess.run(
        ["git", "-C", str(repo_dir), "show", "--no-patch", "--format=%cI", sha],
        capture_output=True,
        text=True,
    )
    raw = result.stdout.strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _shallow_clone_is_truncated(target_dir: Path, since_date: str) -> bool:
    """True if a `--shallow-since=since_date` clone silently cut off history
    that was actually inside the requested window.

    Git's shallow-boundary negotiation can turn a commit *inside* the
    requested window into a grafted shallow root, hiding its own parent
    (also in-window) even though the parent's object is still physically
    present locally (kept for the boundary commit's own diff). Checked
    100% locally, no network calls: for each `.git/shallow` boundary commit,
    read its true parent(s) via `_true_parents` (bypasses the graft) and
    check each parent's committer date. If a parent is unresolvable locally,
    or its date is on/after `since_date`, treat the clone as untrustworthy
    (conservative -- "can't verify" counts as "don't trust it").

    Validated empirically against a 24-repo stratified real-world sample:
    0 false positives, 0 false negatives.
    """
    shallow_file = target_dir / ".git" / "shallow"
    if not shallow_file.exists():
        return False

    since_dt = datetime.fromisoformat(since_date).replace(tzinfo=timezone.utc)

    for sha in shallow_file.read_text().split():
        for parent_sha in _true_parents(target_dir, sha):
            if not _object_present_locally(target_dir, parent_sha):
                return True
            parent_date = _commit_committer_date(target_dir, parent_sha)
            if parent_date is not None and parent_date >= since_dt:
                return True
    return False


def clone_repo_for_commit_scan(
    clone_url: str,
    target_dir: Path,
    *,
    shallow_since: str | None = None,
    extra_env: dict[str, str] | None = None,
) -> bool:
    """
    Clone a repository with commit history but without downloading large blobs.

    This is the history used for agent-commit detection and fixture extraction.
    Returns False if the repo requires credentials (private/removed repo).

    When `shallow_since` is given, bounds the fetched history to
    `--shallow-since=<shallow_since>` (faster, smaller clone), then verifies
    locally that the shallow boundary didn't truncate in-window history (see
    `_shallow_clone_is_truncated`). If it did, the clone is discarded and
    retried once with full history (`shallow_since=None`) -- callers always
    get a correct clone, just faster when it's safe to be.

    `extra_env` is forwarded to `run_git_no_prompt()` (and to the internal
    truncation retry, unchanged) -- see that function's docstring for why
    an authenticated caller passes credentials this way rather than via
    the URL or a `-c` flag.
    """
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        args = [
            "git",
            "clone",
            "--filter=blob:limit=10m",
            "--single-branch",
            "--no-tags",
        ]
        if shallow_since is not None:
            args.append(f"--shallow-since={shallow_since}")
        args += [clone_url, str(target_dir)]

        result = run_git_no_prompt(args, capture_output=True, text=True, timeout=300, extra_env=extra_env)
        if _output_requests_credentials(result.stderr):
            return False
        ok = bool(
            result.returncode == 0
            and target_dir.exists()
            and (list(target_dir.glob(".git")) or list(target_dir.iterdir()))
        )
        if ok and shallow_since is not None and _shallow_clone_is_truncated(target_dir, shallow_since):
            shutil.rmtree(target_dir, ignore_errors=True)
            return clone_repo_for_commit_scan(
                clone_url, target_dir, shallow_since=None, extra_env=extra_env
            )
        return ok
    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return False


def shallow_clone_repo(clone_url: str, target_dir: Path) -> bool:
    """
    Shallow-clone a repository (depth 1) for quick agent config detection.

    Returns False if the repo requires credentials (private/removed repo).
    """
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        result = run_git_no_prompt(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--single-branch",
                "--no-tags",
                clone_url,
                str(target_dir),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if _output_requests_credentials(result.stderr):
            return False
        return result.returncode == 0 and target_dir.exists()
    except Exception:
        return False


def list_tree_entries(repo_path: Path) -> list[tuple[str, bool]]:
    """Every path in HEAD's tree as (path, is_dir). Reads tree objects only, so a
    blobless clone is enough. An empty list when the repository has no HEAD (no
    commits yet). Raises RuntimeError if git cannot list the tree."""
    head = subprocess.run(
        ["git", "-C", str(repo_path), "rev-parse", "--verify", "-q", "HEAD"],
        capture_output=True,
        text=True,
    )
    if head.returncode != 0:
        return []
    listing = subprocess.run(
        ["git", "-C", str(repo_path), "ls-tree", "-r", "-t", "-z", "HEAD"],
        capture_output=True,
        text=True,
    )
    if listing.returncode != 0:
        raise RuntimeError(f"git ls-tree failed in {repo_path}: {listing.stderr.strip()[:200]}")
    entries = []
    for record in listing.stdout.split("\0"):
        if not record:
            continue
        meta, path = record.split("\t", 1)
        _, kind, _ = meta.split()
        entries.append((path, kind == "tree"))
    return entries

