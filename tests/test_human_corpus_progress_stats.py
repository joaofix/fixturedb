import threading

import collection.human_corpus as human_corpus
from collection.db import initialise_db
from collection.human_corpus import HumanCorpusCollector, HumanCorpusStats


def _repo_data(name: str, language: str) -> dict:
    return {
        "github_id": name,
        "full_name": name,
        "language": language,
        "stars": 100,
        "forks": 10,
        "description": "",
        "topics": "",
        "created_at": "2020-01-01",
        "pushed_at": "2020-01-01",
        "clone_url": f"https://github.com/{name}.git",
        "domain": "other",
        "star_tier": "extended",
        "repo_age_years": 1.0,
        "num_contributors": 5,
    }


def _fake_result(repo_name: str, language: str, num_fixtures: int) -> dict:
    return {
        "status": "ok",
        "repo_name": repo_name,
        "domain": "other",
        "star_tier": "extended",
        "repo_age": 1.0,
        "num_contributors": 5,
        "repo_data": _repo_data(repo_name, language),
        "test_commit_rows": [],
        "fixtures": [{"name": f"f{i}"} for i in range(num_fixtures)],
    }


def test_avg_fixtures_per_repo_is_not_contaminated_by_prior_language(
    tmp_path, monkeypatch
):
    """Regression: avg_fixtures_per_repo divided a run-wide cumulative
    fixtures_collected counter by a per-language repo count. Once more than
    one language had been processed sequentially, every later language's
    average was inflated by however much fixture volume preceded it."""
    out_db = tmp_path / "out.db"
    initialise_db(out_db)

    collector = HumanCorpusCollector(
        corpus_db_path=tmp_path / "corpus.db",
        clones_dir=tmp_path / "clones",
        output_db=out_db,
        repo_qc_dir=tmp_path,
        fixtures_output_dir=tmp_path,
    )

    # persist_repository_and_fixtures is monkeypatched to avoid touching real
    # CSV/mock-handling machinery -- only its return value (fixture count)
    # matters for this test.
    monkeypatch.setattr(
        human_corpus,
        "persist_repository_and_fixtures",
        lambda output_db, repo_data, fixtures_list, out_path=None, handle_mocks=True: len(
            fixtures_list
        ),
    )

    stats = HumanCorpusStats()
    language_progress: dict[str, dict] = {
        "python": {"total_repos": 2, "completed": 0, "avg_fixtures_per_repo": 0},
        "javascript": {"total_repos": 1, "completed": 0, "avg_fixtures_per_repo": 0},
    }
    progress_lock = threading.Lock()

    def run_language(current_lang: str, repos: list[dict], results: list[dict]):
        results_iter = iter(results)
        monkeypatch.setattr(
            collector,
            "_process_human_repository",
            lambda repo: next(results_iter),
        )
        collector._process_human_within_language(
            current_lang=current_lang,
            lang_repos=repos,
            workers=1,
            only_write_test_commits=False,
            stats=stats,
            progress_lock=progress_lock,
            language_progress=language_progress,
            repo_ages=[],
            repo_contributors=[],
            all_test_commit_rows=[],
            test_commit_rows_by_language={current_lang: []},
            progress_file=tmp_path / "progress.json",
        )

    # Python: 2 repos, 50 fixtures total -> avg should be 25.
    run_language(
        "python",
        [{"repo_name": "owner/py1"}, {"repo_name": "owner/py2"}],
        [
            _fake_result("owner/py1", "python", 30),
            _fake_result("owner/py2", "python", 20),
        ],
    )
    assert language_progress["python"]["avg_fixtures_per_repo"] == 25

    # JavaScript: 1 repo, 20 fixtures -> avg should be 20, NOT
    # (50 + 20) / 1 = 70 (the bug: dividing the run-wide cumulative total by
    # this language's own repo count).
    run_language(
        "javascript",
        [{"repo_name": "owner/js1"}],
        [_fake_result("owner/js1", "javascript", 20)],
    )
    assert language_progress["javascript"]["avg_fixtures_per_repo"] == 20
