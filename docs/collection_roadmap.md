# Collection Module Roadmap

This document lists improvements and follow-ups to raise the quality, performance, and maintainability of the `collection/` module.

Priority: High
- Bulk inter-table insert: use `executemany()` to reduce round-trips and speed up `human_inter_fixtures` writes.
- Add unit test for inter-insert path (conflict handling & provenance fields).
- Add synthetic benchmark script (`bench/bench_inter_inserts.py`) to measure single-row vs bulk performance at scale (100, 1k, 10k rows).

Priority: Medium
- Add DB write profiling/logging in `persist_repository_and_fixtures()` and `collect_inter_human()` (per-repo timing, slow-repo alerts).
- Document `PRAGMA` settings in `collection/db.py` and rationale for `WAL` and `busy_timeout`.
- Add an integration scale test that creates synthetic repos+fixtures and measures end-to-end throughput.

Priority: Low
- CI: Add a GitHub Actions job that runs tests and optionally the benchmark on a scheduled cadence.
- Observability: emit simple CSV or JSON write-performance reports for long runs.
- Checklist: create a pre-merge checklist (tests, performance bench, docs, changelog).

Notes
- Changes should be backwards-compatible; keep existing conflict-safe semantics (ON CONFLICT DO NOTHING) so re-running the pipeline does not duplicate data.
- Start with bulk insert and a small benchmark to ensure measurable gains before wider refactors.
