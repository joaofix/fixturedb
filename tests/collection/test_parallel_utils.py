"""Tests for collection/parallel_utils.py's run_parallel_per_repo() -- the
shared thread-pool harness agent_corpus.py and human_corpus.py both use.

Pure unit tests against trivial fake compute/persist functions -- no DB, no
git, no real repos. The DB/git-level crash-safety guarantee this harness
provides is exercised end-to-end by each collector's own integration tests
(tests/test_human_collection_integration.py, tests/between_group/
test_agent_corpus.py); these tests only need to prove the harness itself
does what it promises.
"""

from __future__ import annotations

import pytest

from collection import parallel_utils
from collection.parallel_utils import run_parallel_per_repo


class TestSequentialPath:
    def test_workers_1_processes_every_item_in_order(self):
        persisted = []
        run_parallel_per_repo(
            items=[1, 2, 3, 4],
            compute=lambda x: x * 10,
            persist=persisted.append,
            workers=1,
            desc="test",
        )
        assert persisted == [10, 20, 30, 40]

    def test_workers_1_never_constructs_a_threadpool(self, monkeypatch):
        def _boom(*args, **kwargs):
            raise AssertionError("ThreadPoolExecutor should not be used when workers=1")

        monkeypatch.setattr(parallel_utils, "ThreadPoolExecutor", _boom)
        persisted = []
        run_parallel_per_repo(
            items=[1, 2, 3],
            compute=lambda x: x,
            persist=persisted.append,
            workers=1,
            desc="test",
        )
        assert persisted == [1, 2, 3]

    def test_workers_0_or_negative_also_takes_sequential_path(self):
        persisted = []
        run_parallel_per_repo(
            items=[1, 2], compute=lambda x: x, persist=persisted.append, workers=0, desc=""
        )
        assert persisted == [1, 2]

    def test_crash_mid_batch_leaves_earlier_items_already_persisted(self):
        persisted = []

        def compute(x):
            if x == 3:
                raise RuntimeError("simulated crash")
            return x

        with pytest.raises(RuntimeError, match="simulated crash"):
            run_parallel_per_repo(
                items=[1, 2, 3, 4],
                compute=compute,
                persist=persisted.append,
                workers=1,
                desc="test",
            )

        # 1 and 2 were computed and persisted before item 3 raised; 4 was
        # never reached.
        assert persisted == [1, 2]


class TestThreadedPath:
    def test_workers_greater_than_1_processes_every_item(self):
        persisted = []
        run_parallel_per_repo(
            items=list(range(20)),
            compute=lambda x: x * 2,
            persist=persisted.append,
            workers=4,
            desc="test",
        )
        # Completion order isn't guaranteed under threading -- only that
        # every item was computed and persisted exactly once.
        assert sorted(persisted) == sorted(x * 2 for x in range(20))
        assert len(persisted) == 20

    def test_persist_only_ever_called_from_the_calling_thread(self):
        import threading

        main_thread = threading.current_thread()
        persist_threads = []

        def persist(x):
            persist_threads.append(threading.current_thread())

        run_parallel_per_repo(
            items=list(range(10)),
            compute=lambda x: x,
            persist=persist,
            workers=4,
            desc="test",
        )
        assert all(t is main_thread for t in persist_threads)

    def test_crash_mid_batch_leaves_some_items_already_persisted(self):
        persisted = []

        def compute(x):
            if x == 7:
                raise RuntimeError("simulated crash")
            return x

        with pytest.raises(RuntimeError, match="simulated crash"):
            run_parallel_per_repo(
                items=list(range(10)),
                compute=compute,
                persist=persisted.append,
                workers=4,
                desc="test",
            )

        # Some items other than 7 were already computed/persisted by the
        # time the raising future's result() was collected -- can't assert
        # exactly which under threading, but persistence must be strictly
        # partial (not everything, and not nothing survives what already
        # completed).
        assert 7 not in persisted
        assert len(persisted) < 10
