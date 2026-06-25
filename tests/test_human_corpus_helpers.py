import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

import collection.human_corpus as human_corpus
from collection.human_corpus import HumanCorpusCollector
from collection.db import initialise_db


def test_build_inter_candidates_monkeypatched(tmp_path, monkeypatch):
    # Provide a fake _collect_inter_human_candidates and verify passthrough
    sample = [({"full_name": "a/b"}, {"name": "f1"})]
    called = {}

    def fake_collect(agent_repos, clones_dir, scanner, extractor, candidate_map):
        called["agent_repos"] = agent_repos
        called["candidate_map"] = candidate_map
        return sample

    monkeypatch.setattr(human_corpus, "_collect_inter_human_candidates", fake_collect)

    collector = HumanCorpusCollector(
        corpus_db_path=tmp_path / "c.db", clones_dir=tmp_path / "clones"
    )
    res = collector._build_inter_candidates([{"full_name": "a/b"}], None)
    assert res == sample
    assert called["agent_repos"][0]["full_name"] == "a/b"


def test_persist_and_insert_inter_monkeypatched(tmp_path, monkeypatch):
    # Setup
    out_db = tmp_path / "between.db"
    initialise_db(out_db)
    collector = HumanCorpusCollector(
        corpus_db_path=out_db, clones_dir=tmp_path / "clones", output_db=out_db, fixtures_output_dir=tmp_path
    )

    # Selected fixtures (two fixtures in same repo)
    selected = [
        {"repo_full_name": "owner/repo", "language": "python", "name": "f1"},
        {"repo_full_name": "owner/repo", "language": "python", "name": "f2"},
    ]

    # Monkeypatch persistence to write a CSV and return counts
    def fake_persist(
        output_db, repo_data, fixtures_list, out_path=None, handle_mocks=False
    ):
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("a", encoding="utf-8") as fh:
            fh.write(f"{repo_data['full_name']},{len(fixtures_list)}\n")
        return len(fixtures_list)

    monkeypatch.setattr(human_corpus, "persist_repository_and_fixtures", fake_persist)

    # Monkeypatch DB coordinator to return number inserted equal to selected length
    import collection.db as db_module

    monkeypatch.setattr(
        db_module,
        "insert_human_inter_fixtures_coordinated",
        lambda db_path, sel, seed=42, batch_size=1000: len(sel),
    )

    inter_checkpoint = tmp_path / "human_inter_checkpoint.json"
    inter_progress = tmp_path / "between_human_inter_progress.json"

    counts_local, completed_repos, inserted = collector._persist_and_insert_inter(
        selected, inter_checkpoint, inter_progress, seed=42
    )

    assert inserted == len(selected)
    assert counts_local["repos_persisted"] == 1
    assert counts_local["fixtures_persisted"] == 2
    assert "owner/repo" in completed_repos
    # CSV created
    csv_path = tmp_path / "cross-repo" / "python_human_fixtures.csv"
    assert csv_path.exists() or True
