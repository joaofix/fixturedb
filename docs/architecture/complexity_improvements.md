# Complexity Analysis Improvements (profiling notes)

This document summarizes profiling findings and proposed improvements to the complexity/fixture-analysis pipeline. No heuristics or behavioral changes have been applied to the analysis: the implementation remains academically rigorous (Lizard is used for all complexity metrics).

## Profiling summary

- The profiler run over the test corpus identified the following hotspots:
  - `collection.detector.extract_fixtures` — top-level caller across files.
  - Lizard internals (`analyze_source_code`, `token_counter`, `line_counter`, `comment_counter`) account for the bulk of CPU time when run across many files.
  - Repeated parsing (`tree-sitter.Parser.parse`) also contributes but less than Lizard.
  - Detector visitor logic and reuse-count calculations are noticeable but secondary.

## Root causes

- Lizard performs full tokenization and function-level analysis per file; when run across large numbers of files this becomes the dominant cost.
- Re-parsing identical file contents across repeated runs exacerbates cost.
- Running Lizard on non-source blobs (large generated files, documentation) wastes CPU and can skew metrics.

## Proposed improvements (non-heuristic, reproducible, academically sound)

1. File-type filtering (conservative)
   - Only pass files with recognized source extensions to Lizard (e.g., `.py`, `.java`, `.js`, `.ts`, `.go`, `.c`, `.cpp`).
   - This is not a heuristic about "importance"; it's a safe restriction to avoid non-source files.

2. Lizard result caching (recommended)
   - Cache Lizard results keyed by file-content SHA1. Cache entries store the parsed `function_list` and a timestamp.
   - Cache can be in-memory for short runs and optionally persisted to disk (JSON or sqlite) between runs to accelerate repeated analyses of the same corpus.
   - This preserves exact Lizard outputs while avoiding rework.

3. AST parse cache (already present)
   - Reuse the `tree-sitter` parse results across detector passes by keying on content SHA1. This reduces tree-sitter overhead without altering analysis semantics.

4. Batch or asynchronous complexity collection
   - Separate collection of complexity metrics into a batched worker that consumes file paths and writes cached results. Ensures test detection remains single-threaded and deterministic while complexity metrics are attached when available.

5. Instrumentation & profiling harness
   - Save `cProfile` output (`profile.out`) for representative runs and use `snakeviz` or `gprof2dot` to visualize call graphs. This helps set optimization targets and measure improvements quantitatively.

6. Parallelism with care
   - If CPU-bound after caching, parallelize file-level Lizard runs across worker processes (not threads) to avoid GIL limits, while ensuring thread/process-local parser instances for `tree-sitter`.

7. Configurable knobs
   - Expose conservative defaults (e.g., `CACHE_LIZARD_RESULTS=true`, `LIZARD_CACHE_DIR`, `LIZARD_PERSIST=true`) so experiments can be reproduced and revertible.

## Why avoid heuristics

- Heuristics that change analysis results (e.g., skipping analysis on small functions or estimating parameters) violate academic reproducibility and comparability across experiments.
- All proposed changes above preserve Lizard's authoritative outputs or only affect whether we run Lizard at all for files that are clearly non-source, which is a safe optimization.

## Suggested next steps (implementation plan)

1. Implement file-extension whitelist before invoking Lizard (`collection/complexity_provider.py` and callers).
2. Add a content-hash keyed Lizard cache (in-memory + optional disk persistence).
3. Persist `tree-sitter` AST cache to disk for multi-run speedups.
4. Add a `scripts/profile_collection.py --dump profile.out` option and a CI job that stores `profile.out` artifacts for regression tracking.

If you'd like, I can implement step (1) now (file-extension whitelist), followed by (2) a simple in-repo Lizard cache that writes JSON to `.cache/lizard/` keyed by SHA1. These will not change any metric values — they only avoid re-running Lizard when results are identical.
