"""Shared thread-pool harness for "process N repos, persist each result
immediately" -- the shape Dataset A's and Dataset B's extract-fixtures steps
both need.

Extracted from human_corpus.py's original inline `if workers <= 1: ... else:
ThreadPoolExecutor ...` block (added when human_corpus.py was made
crash-safe: persisting every repo's result immediately as it completes,
rather than batching until a whole language finishes, so a crash mid-batch
only loses whatever's still in flight). agent_corpus.py adopts the same
pattern via this module instead of a second, hand-written copy.

Deliberately NOT used by dataset_c.py: that collector's global stratified
sampling step needs every candidate gathered before it can decide what to
keep, so persistence can't happen per-item as each one completes without
first restructuring that sampling step -- a separate piece of work.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, TypeVar

from tqdm import tqdm

T = TypeVar("T")
R = TypeVar("R")


def run_parallel_per_repo(
    items: list[T],
    compute: Callable[[T], R],
    persist: Callable[[R], None],
    workers: int,
    desc: str = "",
) -> None:
    """Run `compute(item)` for each item -- across `workers` threads if >1,
    else sequentially -- and `persist(result)` for each completed item
    immediately in the calling thread, never batched.

    A crash mid-batch (killed process, dead battery, ...) then only loses
    whatever's still in flight, never anything already persisted.
    `compute()` must not touch any shared DB connection or other
    non-thread-safe resource -- it runs in worker threads when `workers >
    1`. `persist()` always runs only in the calling thread (sequentially,
    one at a time), which is where all such access must happen.
    """
    if workers <= 1:
        for item in tqdm(items, desc=desc, unit="repo"):
            persist(compute(item))
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(compute, item): item for item in items}
            for future in tqdm(
                as_completed(futures), total=len(futures), desc=desc, unit="repo"
            ):
                persist(future.result())
