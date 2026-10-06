"""Helpers for identifying test commits from git diffs."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Iterable

from pydriller import Repository
from pydriller.domain.commit import ModificationType

from .config import LANGUAGE_CONFIGS, NON_CODE_EXTENSIONS
from .csv_adapter import get_adapter
from .logging_utils import get_logger

logger = get_logger(__name__)


def is_test_file_path(relative_path: str, language: str) -> bool:
    """Return True when a path matches the configured test-file heuristics."""
    config = LANGUAGE_CONFIGS.get(language)
    if config is None:
        return False

    rel = relative_path.replace("\\", "/").strip()
    if not rel:
        return False

    name = Path(rel).name
    name_lower = name.lower()

    if "." not in name:
        return False

    if any(name_lower.endswith(ext) for ext in NON_CODE_EXTENSIONS):
        return False

    matched = False

    for pattern in config.test_file_suffixes:
        pattern_lower = pattern.lower()
        if pattern_lower.startswith("test_"):
            if name_lower.startswith("test_") and name_lower.endswith(
                pattern_lower.split("test_")[1]
            ):
                matched = True
                break
        elif pattern_lower == "conftest.py":
            if name_lower == "conftest.py":
                matched = True
                break
        elif pattern[:1] in (".", "_", "-"):
            # Pattern already embeds its own left boundary (e.g. ".test.js"),
            # so a plain suffix match can't false-positive on an unrelated
            # word that merely ends the same way.
            if name_lower.endswith(pattern_lower):
                matched = True
                break
        elif pattern[:1].isupper():
            # PascalCase suffix convention (e.g. "WidgetTest.java",
            # "WidgetIT.java"). Match case-sensitively so a short/generic
            # suffix like "IT" only matches its capitalized form, not a
            # coincidental lowercase substring inside an unrelated word
            # (e.g. "Deposit.java", "Credit.java").
            if name.endswith(pattern):
                matched = True
                break
        else:
            # Bare lowercase suffix with no built-in separator (e.g.
            # "test.js"). Require it to be the whole name or preceded by a
            # separator, so it doesn't match an unrelated word that merely
            # ends the same way (e.g. "latest.js", "contest.js").
            if name_lower == pattern_lower or any(
                name_lower.endswith(f"{sep}{pattern_lower}") for sep in (".", "_", "-")
            ):
                matched = True
                break

    if not matched:
        rel_parts = rel.lower().split("/")
        for pattern in config.test_path_patterns:
            dir_pattern = pattern.lower().rstrip("/")
            if dir_pattern in rel_parts:
                matched = True
                break

    return matched


def collect_test_files_for_commit(
    repo_path: Path, commit_sha: str, language: str
) -> list[str]:
    """Return the test files touched by a commit."""
    try:
        commits = list(Repository(str(repo_path), single=commit_sha).traverse_commits())
    except Exception:
        logger.debug(
            "Failed to traverse commit %s in %s", commit_sha, repo_path, exc_info=True
        )
        return []

    if not commits:
        return []

    commit = commits[0]
    test_files: list[str] = []
    seen: set[str] = set()

    # commit.modified_files is a property that computes the diff (a `git
    # diff-tree` subprocess call) the moment it's accessed here -- not
    # lazily per-item, so this needs its own try/except, separate from
    # traverse_commits()'s above. A partial clone (--filter=blob:limit=10m)
    # can fail to fetch one blob for a single commit's diff. That failure must
    # not stop the whole extract-fixtures run, as traverse_commits() also
    # guarantees.
    try:
        modified_files = commit.modified_files
    except Exception:
        logger.debug(
            "Failed to diff commit %s in %s", commit_sha, repo_path, exc_info=True
        )
        return []

    for modified_file in modified_files:
        if modified_file.change_type == ModificationType.DELETE:
            continue

        path = modified_file.new_path or modified_file.old_path or ""
        if not path:
            continue

        if path not in seen and is_test_file_path(path, language):
            seen.add(path)
            test_files.append(path)

    return test_files


def _build_commit_github_url(repo_name: str, commit_sha: str) -> str:
    """Build a GitHub URL pointing at the commit itself (not a specific
    file) -- a test-commit row covers potentially several files
    (test_file_paths), so a single-file blob link (corpus_utils.py's
    _build_github_url(), used for individual fixtures) doesn't apply
    here."""
    if not repo_name or not commit_sha:
        return ""
    sha = commit_sha.strip()
    if not sha:
        return ""
    return f"https://github.com/{repo_name}/commit/{sha}"


def write_test_commits_csv(records: Iterable[dict], output_path: Path) -> Path:
    """Write test commit records to CSV for standalone runs."""
    adapter = get_adapter()
    rows = list(records)
    # Ensure test_file_paths is serialised to JSON string for CSV output
    for row in rows:
        tf = row.get("test_file_paths", [])
        if not isinstance(tf, str):
            row["test_file_paths"] = json.dumps(tf, ensure_ascii=False)
        row["github_url"] = _build_commit_github_url(
            row.get("repo_name", ""), row.get("commit_sha", "")
        )

    fieldnames = [
        "repo_name",
        "language",
        "commit_sha",
        "commit_role",
        "agent_type",
        "commit_date",
        "test_file_count",
        "test_file_paths",
        "github_url",
    ]

    return adapter.write_dicts(Path(output_path), rows, fieldnames)


# git must not fetch a missing object from a partial clone's remote during these
# checks: they only ask what this clone holds (GIT_NO_LAZY_FETCH is git's switch).
_NO_LAZY_FETCH_ENV = dict(os.environ, GIT_NO_LAZY_FETCH="1")


def _present_commit_shas(repo_path: Path, shas: list[str]) -> list[str]:
    """The SHAs that exist as commits in this repository. A commit missing from a
    shallow clone, or a SHA that is not a commit, is left out."""
    if not shas:
        return []
    proc = subprocess.run(
        ["git", "-C", str(repo_path), "cat-file", "--batch-check"],
        input="\n".join(shas) + "\n",
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="surrogateescape",
        env=_NO_LAZY_FETCH_ENV,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git cat-file failed in {repo_path}: {proc.stderr.strip()[:200]}")
    present = []
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[1] == "commit":
            present.append(parts[0])
    return present


def _shallow_boundary_commits(repo_path: Path) -> set[str]:
    """The commits git records as shallow boundaries (the cut points of the clone)."""
    shallow_file = Path(repo_path) / ".git" / "shallow"
    if not shallow_file.exists():
        return set()
    return set(shallow_file.read_text().split())


def _commits_with_missing_parents(repo_path: Path, shas: list[str]) -> set[str]:
    """The commits (of `shas`) that git sees as roots only because of the clone's cut.

    A shallow clone hides a boundary commit's parents from `git log`, so git would
    treat it as a root and list every file as added. Such a commit is recorded in
    `.git/shallow`, and its raw object still names the parent. Both are checked, and
    no object is fetched on demand (`--no-lazy-fetch`), so a partial clone is not
    changed by this check.
    """
    if not shas:
        return set()
    boundary = _shallow_boundary_commits(repo_path)
    proc = subprocess.run(
        ["git", "-C", str(repo_path), "cat-file", "--batch"],
        input=("\n".join(shas) + "\n").encode(),
        capture_output=True,
        env=_NO_LAZY_FETCH_ENV,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git cat-file failed in {repo_path}: {proc.stderr.decode()[:200]}")
    data = proc.stdout
    pos = 0
    parents_of: dict[str, list[str]] = {}
    for sha in shas:
        newline = data.index(b"\n", pos)
        header = data[pos:newline].split()
        pos = newline + 1
        if len(header) != 3 or header[1] != b"commit":
            continue  # "<sha> missing" or another object type
        size = int(header[2])
        body = data[pos:pos + size]
        pos += size + 1
        fields = body.split(b"\n\n", 1)[0]
        parents_of[sha] = [
            line[len(b"parent "):].decode()
            for line in fields.split(b"\n")
            if line.startswith(b"parent ")
        ]
    all_parents = sorted({parent for parents in parents_of.values() for parent in parents})
    present_parents = set(_present_commit_shas(repo_path, all_parents))
    return {
        sha
        for sha, parents in parents_of.items()
        if parents and (sha in boundary or any(parent not in present_parents for parent in parents))
    }


def collect_test_files_by_commit(
    repo_path: Path, commit_shas: Iterable[str], language: str
) -> dict[str, list[str]]:
    """Test files touched by each commit, from one `git log --name-status` call.

    The same answer as `collect_test_files_for_commit`, for every commit at once,
    with the same rules: a deleted file is skipped, a renamed file counts under its
    new path, and each path is listed once in git's order. It reads paths only, so
    a blobless clone is enough. A commit that is missing from the clone maps to [],
    and so does a commit whose parent is missing (a shallow boundary), as with
    PyDriller. A true root commit lists every file it adds.
    """
    shas = list(dict.fromkeys(sha.strip() for sha in commit_shas if sha and sha.strip()))
    result: dict[str, list[str]] = {sha: [] for sha in shas}
    present = _present_commit_shas(repo_path, shas)
    boundary = _commits_with_missing_parents(repo_path, present)
    present = [sha for sha in present if sha not in boundary]
    if not present:
        return result

    proc = subprocess.run(
        [
            "git", "-C", str(repo_path), "log", "--no-walk=unsorted", "--stdin",
            "--root", "-M", "--name-status", "-z", "--format=%x01%H",
        ],
        input="\n".join(present) + "\n",
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="surrogateescape",
        env=_NO_LAZY_FETCH_ENV,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git log failed in {repo_path}: {proc.stderr.strip()[:200]}")

    seen: dict[str, set[str]] = {}
    current: str | None = None
    tokens = proc.stdout.split("\0")
    i = 0
    while i < len(tokens):
        token = tokens[i].lstrip("\n")
        i += 1
        if not token:
            continue
        if token.startswith("\x01"):
            current = token[1:]
            seen.setdefault(current, set())
            continue
        status = token
        if status[0] in "RC":
            path = tokens[i + 1]
            i += 2
        else:
            path = tokens[i]
            i += 1
        if status[0] == "D" or current is None:
            continue
        if path and path not in seen[current] and is_test_file_path(path, language):
            seen[current].add(path)
            if current in result:
                result[current].append(path)
    return result

