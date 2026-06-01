import json
from pathlib import Path
from collection.human_corpus import _load_inter_checkpoint, _save_inter_checkpoint, _write_inter_progress


def test_checkpoint_io(tmp_path):
    ck = tmp_path / "human_inter_checkpoint.json"
    prog = tmp_path / "between_human_inter_progress.json"

    completed = {"a/b"}
    counts = {"repos_persisted": 1, "fixtures_persisted": 2}
    _save_inter_checkpoint(ck, completed, counts)

    c2, counts2 = _load_inter_checkpoint(ck)
    assert list(c2) == ["a/b"]
    assert counts2["repos_persisted"] == 1

    _write_inter_progress(prog, c2, counts2)
    data = json.loads(prog.read_text(encoding='utf-8'))
    assert data["repos_persisted"] == 1
    assert data["fixtures_persisted"] == 2
    assert data["completed_repos_count"] == 1
