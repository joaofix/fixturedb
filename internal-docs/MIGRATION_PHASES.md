# Phase Scripts Migration

The phase orchestration scripts for the human vs agent fixture collection pipeline have been reorganized for better project structure.

## What Changed

All `phase_*.py` scripts have been moved from the root directory to the `human_vs_agent/` folder.

### Old Location (Deprecated)
```
/home/joao/icsme-nier-2026/phase_1a_scan_agent_commits.py
/home/joao/icsme-nier-2026/phase_1b_verify_agent_commits.py
/home/joao/icsme-nier-2026/phase_1c_assess_tier1_yield.py
/home/joao/icsme-nier-2026/phase_1d_discover_matched_repos.py
/home/joao/icsme-nier-2026/phase_2_extract_pre_2021.py
/home/joao/icsme-nier-2026/phase_3_extract_llm.py
/home/joao/icsme-nier-2026/phase_4_analyze_distribution.py
/home/joao/icsme-nier-2026/phase_5_stratified_sample.py
/home/joao/icsme-nier-2026/phase_6_7_export_and_document.py
/home/joao/icsme-nier-2026/phase_8_final_validation.py
```

### New Location
```
/home/joao/icsme-nier-2026/human_vs_agent/phase_1a_scan_agent_commits.py
/home/joao/icsme-nier-2026/human_vs_agent/phase_1b_verify_agent_commits.py
/home/joao/icsme-nier-2026/human_vs_agent/phase_1c_assess_tier1_yield.py
/home/joao/icsme-nier-2026/human_vs_agent/phase_1d_discover_matched_repos.py
/home/joao/icsme-nier-2026/human_vs_agent/phase_2_extract_pre_2021.py
/home/joao/icsme-nier-2026/human_vs_agent/phase_3_extract_llm.py
/home/joao/icsme-nier-2026/human_vs_agent/phase_4_analyze_distribution.py
/home/joao/icsme-nier-2026/human_vs_agent/phase_5_stratified_sample.py
/home/joao/icsme-nier-2026/human_vs_agent/phase_6_7_export_and_document.py
/home/joao/icsme-nier-2026/human_vs_agent/phase_8_final_validation.py
```

## How to Run

Instead of:
```bash
python phase_1a_scan_agent_commits.py
```

Use:
```bash
python -m human_vs_agent.phase_1a_scan_agent_commits
```

Or directly:
```bash
python human_vs_agent/phase_1a_scan_agent_commits.py
```

## Why?

1. **Cleaner root directory** - Phase scripts don't clutter the project root
2. **Better organization** - All orchestration scripts are grouped together
3. **Clear separation of concerns** - `collection/` contains reusable modules, `human_vs_agent/` contains orchestration
4. **Descriptive folder name** - `human_vs_agent/` clearly indicates the purpose (comparing human vs agent fixtures)

## Documentation

See [human_vs_agent/README.md](human_vs_agent/README.md) for:
- Detailed phase documentation
- Two-tier methodology explanation
- Quick start guide
- Configuration options
