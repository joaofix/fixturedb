from pathlib import Path
from collection.db import (
    initialise_db,
    mark_checkpoint,
    is_checkpoint_completed,
    db_session,
)


def test_checkpoints(tmp_path: Path):
    db_path = tmp_path / "cp.db"
    initialise_db(db_path)

    with db_session(db_path) as conn:
        # initially no checkpoint
        assert not is_checkpoint_completed(conn, 1, "persist")
        mark_checkpoint(conn, 1, "persist")
        assert is_checkpoint_completed(conn, 1, "persist")
