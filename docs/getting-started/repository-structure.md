# Repository structure

## Top level

| Folder | Contents |
|--------|----------|
| `collection/` | The pipeline code. Run it with `python -m collection`. |
| `tests/` | The test suite. |
| `docs/` | This documentation. |
| `internal-docs/` | Working notes and the run recipe, `RUN_COMMANDS.md`. |
| `github-search-raw/` | The SEART repository list. This is the input. |
| `datasets/` | Stage CSVs, one folder per dataset. Created by the pipeline. |
| `db/` | SQLite databases, one per dataset. Created by the pipeline. |
| `export/` | Export bundles, one zip per dataset. |
| `research_questions/` | The generated RQ reports (Markdown). |
| `toy-dataset/` | Output of the toy runs. Git-ignored. |

## The pipeline code

**Entry point**

- `__main__.py`: the CLI. Each verb is one function.
- `paths.py`: every default input and output path.
- `config.py`: constants loaded from `study_parameters/` and `heuristics/`.

**Dataset A (agent)**

- `repository_quality_control/agent_repository_counter.py`: `discover-repos --dataset a`.
- `repository_quality_control/agent_commit_counter.py`: `discover-commits --dataset a`.
- `tiered_agent_corpus_scanner.py`: agent commit classification.
- `test_commit_filter.py`: `filter-test-commits --dataset a`.
- `agent_corpus.py`: `extract-fixtures --dataset a`.
- `diff_purity.py`: the pure-addition filter.
- `dedupe_commits_by_sha.py`: removes duplicate commits.

**Dataset C (human, pre-LLM)**

- `select_dataset_c_repos.py`: `discover-repos --dataset c`.
- `dedupe_dataset_c_repos.py`: removes duplicate repositories.
- `dataset_c.py`: `extract-fixtures --dataset c`.

**Fixture detection**

- `detector.py`: the entry point, `extract_fixtures()`.
- `detector_python.py`, `detector_java.py`, `detector_javascript.py`: one per language.
- `detector_shared.py`: shared types and mock detection.

**Catalogs (data, not code)**

- `heuristics/`: agent catalogs, fixture patterns, mock patterns and exclusions.
- `study_parameters/`: framework registry, language settings, study constants.

**Outputs and checks**

- `dataset_pipeline.py`: `analyze-distribution`, `sample`, `export`, `validate`.
- `dataset_summary.py`: `summarize`.
- `dataset_exporter.py`, `dataset_validator.py`: export bundles and their checks.
- `validation_sampling.py`: manual review samples.
- `toy.py`: the toy runs.
- `db.py`, `db_schema.py`: database access and schema.

**Research questions**

- `research_questions/rq1.py` to `rq5.py`: one report per question.
- `rq1_prevalence_scan.py`: the RQ1 scan, which clones repositories.
- `rq5_agent_file_scan.py`: the RQ5 scan, which uses the GitHub API.
- `research_questions/balance.py`: control-variable balance checks.

## Where to look for what

| You want to change | Look at |
|--------------------|---------|
| Which agents are detected | `heuristics/agent-mining/*.csv` |
| Which fixtures are detected | `heuristics/fixture_definitions.yaml` |
| Which mocks are detected | `heuristics/feature_extraction_patterns.yaml` |
| Study dates and thresholds | `study_parameters/study_parameters.yaml` |
| The CLI | `__main__.py`, or `python -m collection <verb> --help` |

## Ignored folders

Folders such as `clones/`, `venv/`, `htmlcov/` and the `past-*` archives are
not in git. Their contents are local.
