# Manual Validation Precision Report

Precision computed only over clearly-labeled TP/FP items; `Unsure` is reported separately (`unsure_rate`), never folded into precision. `404` rows (source no longer accessible) are excluded from `effective_n` entirely, not counted as FP.

| Component | n sampled | 404 excluded | Effective n | TP | FP | Unsure | Precision | Unsure rate |
|---|---|---|---|---|---|---|---|---|
| Mock detection | 376 | 0 | 376 | 375 | 1 | 0 | 99.7% | 0.0% |
| Pytest lifecycle heuristic | 380 | 0 | 380 | 380 | 0 | 0 | 100.0% | 0.0% |

## Paper-ready text

mock detection (99.7%, 0 items unsure)
the pytest lifecycle heuristic (100.0%, 0 items unsure)

