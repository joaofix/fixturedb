"""Repository selection for Dataset B (human, within-repo matched control).

Pure CSV/DB querying with no fixture-extraction logic -- split out of
human_corpus.py so that module can focus on the actual collection pipeline.
"""

import csv
import sqlite3
from pathlib import Path
from typing import Optional

from .config import AGENT_CORPUS_START_DATE, LANGUAGE_CONFIGS
from .utils import build_repo_row


def select_human_corpus_repositories(
    repo_qc_dir: Path,
    repos_per_language: Optional[int] = None,
    language: Optional[str] = None,
    require_fixture_repo_list: bool = False,
) -> list[dict]:
    """
    Select agent-enabled repositories for human corpus collection.

    Queries the repo-QC CSV exports for repositories with agent config files.

    Args:
        repo_qc_dir: Directory containing already-resolved *_repo.csv files
            (default: datasets/b/repos/, see collection.repo_resolve)
        repos_per_language: Optional per-language cap. None means include all rows.
        language: Optional filter to single language
        require_fixture_repo_list: If True, raise if repo_qc_dir has no *_repo.csv
            files rather than silently returning an empty selection.

    Returns:
        List of repository dicts with required metadata
    """
    # Backwards-compatible behaviour: if a SQLite corpus DB path is provided,
    # query the `repositories` table for pre-2021 repos. Otherwise fall back to
    # reading repo-QC CSV exports in `repo_qc_dir`.
    repo_path = Path(repo_qc_dir)
    selected: list[dict] = []

    if repo_path.exists() and repo_path.is_file():
        # Treat as corpus DB
        conn = sqlite3.connect(str(repo_path))
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, github_id, full_name, language, stars, forks, description,
                   topics, created_at, pushed_at, clone_url, status, num_contributors, num_test_files
            FROM repositories
            WHERE created_at >= ? AND status IN ('analysed', 'cloned')
            ORDER BY language ASC, created_at ASC
            """,
            (AGENT_CORPUS_START_DATE,),  # Use agent temporal window (post-2025)
        )
        rows = cur.fetchall()
        conn.close()

        grouped: dict[str, list[dict]] = {}
        for row in rows:
            (
                _id,
                github_id,
                full_name,
                lang,
                stars,
                forks,
                description,
                topics,
                created_at,
                pushed_at,
                clone_url,
                status,
                num_contributors,
                num_test_files,
            ) = row

            lang = (lang or "unknown").strip().lower()
            if language and lang != language:
                continue
            if lang not in LANGUAGE_CONFIGS:
                continue

            repo_row = {
                "id": _id,
                "github_id": github_id,
                "full_name": full_name,
                "language": lang,
                "stars": stars,
                "forks": forks,
                "description": description or "",
                "topics": topics or "[]",
                "created_at": created_at or "",
                "pushed_at": pushed_at or "",
                "clone_url": clone_url or f"https://github.com/{full_name}.git",
                "num_contributors": num_contributors or 0,
                "status": status,
            }
            grouped.setdefault(lang, [])
            grouped[lang].append(repo_row)

        for lang in [language] if language else list(LANGUAGE_CONFIGS.keys()):
            if not lang:
                continue
            lang_repos = grouped.get(lang, [])
            selected.extend(
                lang_repos
                if repos_per_language is None
                else lang_repos[:repos_per_language]
            )

        return selected

    # `repo_qc_dir` is a directory of already-resolved `*_repo.csv` files
    # (default: datasets/b/repos/, written by `discover-repos --dataset b` /
    # collection.repo_resolve.resolve_dataset_b_repos()). Resolution across
    # Dataset A's several possible source directories happens once, upstream,
    # in that step -- this function no longer guesses between them.
    if require_fixture_repo_list and not any(Path(repo_qc_dir).glob("*_repo.csv")):
        raise ValueError(
            f"No *_repo.csv files found under {repo_qc_dir}; run "
            "`python -m collection discover-repos --dataset b` first"
        )

    grouped_csv: dict[str, list[dict]] = {}
    for csv_path in sorted(Path(repo_qc_dir).glob("*_repo.csv"), key=lambda p: p.name):
        with csv_path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                if str(row.get("has_agent_config") or "").strip().lower() not in {
                    "1",
                    "true",
                }:
                    continue

                repo_name = (row.get("repo_name") or row.get("full_name") or "").strip()
                lang = (row.get("language") or "unknown").strip().lower()
                if not repo_name or "/" not in repo_name:
                    continue
                if language and lang != language:
                    continue

                repo_row = build_repo_row(
                    repo_name,
                    lang,
                    stars=row.get("stars") or 0,
                    clone_url=row.get("clone_url") or "",
                    num_contributors=row.get("num_contributors") or 0,
                    created_at=row.get("created_at") or "",
                    topics=row.get("topics") or "[]",
                )
                grouped_csv.setdefault(lang, [])
                if repo_name not in {r["full_name"] for r in grouped_csv[lang]}:
                    grouped_csv[lang].append(repo_row)

    for lang in [language] if language else list(LANGUAGE_CONFIGS.keys()):
        if not lang:
            continue
        lang_repos = grouped_csv.get(lang, [])
        selected.extend(
            lang_repos
            if repos_per_language is None
            else lang_repos[:repos_per_language]
        )

    return selected
