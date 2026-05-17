# Setup and Requirements - FixtureDB Split

Instructions for setting up the FixtureDB Split environment.

## Prerequisites

### Required
- **Python 3.10+** (tested with 3.12.3)
- **Git** (must be on PATH, required for agent detection)
- **corpus.db** (original FixtureDB database)

### Optional
- **clones/ directory** (for Phases 1, 3: agent detection and AGENT extraction)
  - Without it, you can run Phases 2, 5-8 (pre-2021 extraction only)

## Installation

### 1. Clone Repository
```bash
git clone <repo-url>
cd icsme-nier-2026
```

### 2. Create Virtual Environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Verify Installation
```bash
# Check all phase scripts are importable
python -c "import phase_1a_scan_agent_files; print('✓ Phase 1A')"
python -c "import phase_1b_verify_agent_commits; print('✓ Phase 1B')"
python -c "import phase_2_extract_pre_2021; print('✓ Phase 2')"
```

## Project Structure

```
icsme-nier-2026/
├── phase_1a_scan_agent_files.py      # Agent file scanning
├── phase_1b_verify_agent_commits.py   # Agent commit verification
├── phase_2_extract_pre_2021.py        # Pre-2021 fixture extraction
├── phase_3_extract_llm.py             # AGENT fixture extraction
├── phase_4_analyze_distribution.py    # Distribution analysis
├── phase_5_stratified_sample.py       # Stratified sampling
├── phase_6_7_export_and_document.py   # Export and documentation
├── phase_8_final_validation.py        # Final validation
│
├── collection/                        # Core modules
│   ├── agent_detector.py              # Phase 1A/1B implementation
│   ├── fixture_extractor.py           # Phase 2/3 implementation
│   ├── dataset_sampler.py             # Phase 5 implementation
│   └── dataset_exporter.py            # Phase 6-7 implementation
│
├── corpus.db                          # Original FixtureDB database
├── clones/                            # Git repositories (Phases 1, 3)
│
├── docs/
│   ├── split/                         # Split dataset documentation
│   │   ├── README.md
│   │   ├── OVERVIEW.md
│   │   ├── PHASES.md
│   │   ├── DATA_MODELS.md
│   │   ├── EXECUTION_GUIDE.md
│   │   └── IMPLEMENTATION_STATUS.md
│   └── architecture/
│       ├── agent-detection.md         # Agent detection methodology
│       ├── database-schema.md         # Split database schemas
│       ├── detection.md               # Fixture detection (fixture metrics)
│       └── ...
│
├── tests/                             # Test suite
│   ├── test_split_*.py
│   └── conftest.py
│
└── requirements.txt
```

## Dependencies

### Core
- **sqlite3** — Database operations
- **subprocess** — Git operations
- **pathlib, os** — File system operations
- **json, csv, zipfile** — Data formats

### Testing
- **pytest** — Test framework
- **pytest-cov** — Coverage reporting

### Optional
- **pandas** — For CSV analysis (analysis phase, not collection)

## Quick Start

### Minimal Setup (Phases 2, 5-8 only)
```bash
# Extract pre-2021 fixtures (no clones needed)
python -m collection phase-2

# Continue with sampling and export
python -m collection phase-5
python -m collection phase-6-7
python -m collection phase-8
```

### Full Setup (All Phases)
1. Populate clones/ directory with 200 repositories
2. Run all 8 phases in order (see [Execution Guide](../split/EXECUTION_GUIDE.md))

## Configuration

No configuration files needed. All parameters are hardcoded in phase scripts:

- **Pinned commits:** stored in fixture extraction code
- **Date cutoffs:** 2021-01-01 for AGENT era
- **Agent patterns:** defined in agent_detector.py
- **Sample size:** 32,895 (fixtures per dataset)

To modify, edit the phase script directly.

## Database Setup

The corpus.db should already be present in the root directory. Verify:

```bash
sqlite3 corpus.db "SELECT COUNT(*) as fixture_count FROM fixtures;"
```

Expected output: `35169` (approximately)

## Running Tests

```bash
# Run all tests
pytest tests/

# Run with coverage
pytest tests/ --cov=collection --cov-report=html

# Run specific test
pytest tests/test_split_agent_detector.py -v
```

All tests should pass. Current status: **19/19 passing**.

## Troubleshooting

### ImportError: No module named 'collection'
**Solution:** Ensure you're in the project root directory:
```bash
cd icsme-nier-2026
python -m collection phase-2
```

### sqlite3.OperationalError: no such table
**Solution:** Verify corpus.db exists and is valid:
```bash
sqlite3 corpus.db ".tables"  # Should show: fixtures repositories test_files
```

### Phase scripts fail with AttributeError
**Solution:** Check Python version:
```bash
python --version  # Should be 3.10+
```

## Next Steps

1. **Understand the approach:** Read [OVERVIEW](../split/OVERVIEW.md)
2. **Run the pipeline:** Follow [Execution Guide](../split/EXECUTION_GUIDE.md)
3. **Explore the data:** Use [Usage Guide](../usage/usage.md) for SQL examples
4. **Review results:** Check [Implementation Status](../split/IMPLEMENTATION_STATUS.md)
