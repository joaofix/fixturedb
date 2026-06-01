# Inter-repo Human Sampling Implementation TODO

This file lists remaining tasks for the inter-repo human sampling work.

- [ ] Add pipeline `--mode` plumbing (`within|inter|both`) in `pipeline.py` and dispatch to `HumanCorpusCollector.collect_inter_human` for `inter` mode.
- [ ] Add CLI arguments and examples in docs/usage for running inter-repo sampling.
- [ ] Add unit tests for `collection/sampling.py` (deterministic sampling behavior).
- [ ] Add integration test that performs a dry-run using small sample CSVs and an in-memory DB, asserting rows in `human_inter_fixtures`.
- [ ] Add provenance metadata: `sample_batch`, `seed`, `sample_reason` saved in `human_inter_fixtures` and sample summary table.
- [ ] Add summarization and export utilities for `human_inter_fixtures` (e.g., per-language CSV exporters).
- [ ] Implement fallback strategies (pool expansion, target reduction) if per-language targets cannot be met.
- [ ] Wire `human_within_fixtures` insertion path (currently helper exists, but upstream code path to use it should be verified/added).
- [ ] Update docs to include examples of querying `human_inter_fixtures` and `human_within_fixtures`.
- [ ] Run full pipeline on staging data and validate sample sizes and provenance metadata.

Notes:
- Fallback strategies are intentionally deferred until we observe actual pool sizes.
- Current implementation persists candidate fixtures to the primary `fixtures` table and then copies references into `human_inter_fixtures` for analysis convenience.
