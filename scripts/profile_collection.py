"""Simple profiler script for a small collection workflow.

Usage (example):

    python scripts/profile_collection.py /path/to/sample/repo python

This will run `extract_fixtures` on all test files under the given repo and
print timing/profile statistics. Intended as a lightweight hotspot finder.
"""

import cProfile
import pstats
import sys
from pathlib import Path

from collection.detector import extract_fixtures


def run_profile(repo_path: Path, language: str):
    test_files = (
        list(Path(repo_path).rglob("test*.py"))
        if language == "python"
        else list(Path(repo_path).rglob("*"))
    )
    pr = cProfile.Profile()
    pr.enable()
    for tf in test_files:
        try:
            extract_fixtures(tf, language)
        except Exception:
            pass
    pr.disable()
    ps = pstats.Stats(pr).sort_stats("cumtime")
    ps.print_stats(30)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python scripts/profile_collection.py /path/to/repo language")
        sys.exit(2)
    repo = Path(sys.argv[1])
    lang = sys.argv[2]
    run_profile(repo, lang)
