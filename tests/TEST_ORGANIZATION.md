# Test Organization

The test suite has been reorganized to match the project structure:

```
tests/
├── __init__.py              # Root test initialization
├── conftest.py              # Shared pytest configuration and fixtures
├── TEST_PLAN.md             # Test planning documentation
├── fixtures/                # Shared test data (sample code, metadata)
│
├── collection/              # Tests for collection modules
│   ├── __init__.py
│   ├── test_detector_edge_cases.py
│   ├── test_extractor_coverage.py
│   ├── test_framework_detection.py
│   ├── test_framework_gaps.md
│   ├── test_github_search_loader.py
│   ├── test_test_file_discovery.py
│   ├── test_extractor_edge_cases/
│   ├── test_extractor_metadata/
│   ├── test_extractor_unit/
│   ├── test_mock_detection/
│   ├── test_integration/       # Integration tests with realistic fixtures
│   └── test_export/            # Export functionality tests
│
└── human_vs_agent/          # Tests for human_vs_agent phases
    ├── __init__.py
    ├── test_agent_detection_end_to_end.py
    ├── test_split_agent_detector.py
    ├── test_split_dataset_exporter.py
    ├── test_split_dataset_sampler.py
    ├── test_split_fixture_extractor.py
    └── test_split_integration.py
```

## Test Organization Rationale

- **`tests/collection/`** - Tests for core fixture detection, extraction, and export modules
  - Unit tests for individual components (detector, extractor, framework detection)
  - Edge case and error handling tests
  - Integration tests with realistic fixture data
  - CSV/ZIP export functionality tests

- **`tests/human_vs_agent/`** - Tests for human vs agent fixture comparison pipeline
  - Agent commit detection and verification
  - Dataset splitting and export for human vs LLM comparison
  - Stratified sampling logic
  - Pipeline integration tests

- **`tests/`** - Shared configuration and test data
  - `conftest.py` - Pytest fixtures and configuration accessible to all tests
  - `fixtures/` - Shared test data used across both test suites
  - `TEST_PLAN.md` - Overall test strategy and coverage

## Running Tests

```bash
# Run all tests
pytest tests/

# Run only collection tests
pytest tests/collection/

# Run only human_vs_agent tests
pytest tests/human_vs_agent/

# Run specific test file
pytest tests/collection/test_detector_edge_cases.py

# Run with verbose output and coverage
pytest tests/ -v --cov=collection --cov=human_vs_agent
```

## Import Conventions

All test files use absolute imports from the package root:
```python
from collection.detector import extract_fixtures
from collection.agent_detector import AgentFileScanner
from human_vs_agent.phase_1a_scan_agent_commits import load_corpus_repos
```

This works because pytest runs from the workspace root and adds it to `sys.path`.
