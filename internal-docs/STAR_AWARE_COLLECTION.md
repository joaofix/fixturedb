# Star-Aware Collection Strategy

## Overview

The corpus collection now supports prioritizing **500+ star repositories** (Hamster's "core" tier) over lower-star repos (100-499, "extended" tier). This ensures your final corpus is maximally composed of established, mature projects while still being pragmatic about language-specific availability.

## Why This Matters

- **500+ star** repos are directly comparable to Hamster (arXiv:2509.26204)
- **100-500 star** repos add diversity but are lower quality (less maintenance, fewer tests)
- Some languages (Python) have plenty of 500+ repos; others (C#, Go) have fewer
- The pipeline should **maximize 500+ repos first**, then fill remainder if needed

## Current Status

From `analyze_star_distribution.py`:

```
Python:    300/300 analyzed, 100.0% are 500+ stars  OPTIMAL
Java:      293/300 analyzed, 98.0% are 500+ stars  EXCELLENT
Others:    Not yet collected
```

**Goal for remaining languages**: Target 90%+ of repos from 500+ star pool

## Usage

### 1. Star Distribution Analysis

Before collecting a language, check what's available on GitHub:

```bash
# Show current corpus star distribution
python analyze_star_distribution.py

# With recommendations
python analyze_star_distribution.py --recommend
```

Output shows:
- How many repos at each stage (discovered, cloned, analyzed) are 500+ vs 100-499
- Estimated GitHub availability (from your discoveries so far)
- Gaps that need filling

### 2. Two-Phase Collection (Manual)

**Phase 1: Collect only 500+ star repos**

```bash
# Search specifically for 500+ star repos first
# (using the modified search with min_stars parameter)
python pipeline.py search --language go --max 400
python pipeline.py clone
python pipeline.py extract
```

**Phase 2: Fill remaining with 100-500 repos** (if target not met)

```bash
# Standard search includes all 100+ stars
python pipeline.py search --language go --max 300
python pipeline.py clone
python pipeline.py extract
```

### 3. Automatic Two-Phase (Future)

```bash
# Planned: Automatic star-tier aware collection
python collect_with_star_priority.py --language go --target 300
```

This would:
1. Discover and extract 500+ repos until target or supply exhausted
2. Automatically switch to 100-500 repos if needed
3. Report final 500+ vs 100-500 distribution

## Implementation Details

### Search Query Modification

The `_build_query()` function now accepts `min_stars` parameter:

```python
# Standard (includes 100+ stars)
base_query = _build_query(config)  
# → "language:Go stars:>=100 fork:false is:public"

# High-tier only (500+ stars)
base_query = _build_query(config, min_stars=500)  
# → "language:Go stars:>=500 fork:false is:public"
```

### Star Tier Definition

From `config.py`:
```python
STAR_TIER_CORE_THRESHOLD = 500  # 'core' tier — comparable to Hamster

def star_tier(stars: int) -> str:
    return "core" if stars >= STAR_TIER_CORE_THRESHOLD else "extended"
```

### Collection Functions

All collection functions now support `min_stars`:

```python
# Search with 500+ star filter
collected = collect_repos_for_language(
    "go",
    max_repos=300,
    stratified=True,
    min_stars=500  # NEW: filter to 500+ only
)

# Standard (100+)
collected = collect_repos_for_language(
    "go",
    max_repos=300,
    stratified=True
    # min_stars defaults to config.min_stars (100)
)
```

## Strategy for Each Language

| Language | Availability | Strategy |
|----------|--------------|----------|
| **Python** |  Plenty 500+ | DONE: 100% 500+ (300/300) |
| **Java** |  Good 500+ | DONE: 98.2% 500+ (287/300), need 7-13 more |
| **Go** | ? Unknown | Phase 1: Search 500+, estimate ~15-20% success |
| **C#** | ? Unknown | Phase 1: Search 500+, may need Phase 2 |
| **JS/TS** |  Scarce 500+ | Expect 50%+ will be 100-499 (frontend heavy) |

## Expected Survival Rates by Tier

500+ star repos typically have:
- **Higher fixture count** (more mature testing practices)
- **Better code quality** (more maintained)
- **Higher extraction survival** (~12-15% vs 7-9% for 100-499)

This is reflected in `LANGUAGE_SURVIVAL_RATES`:
```python
# 500+ repos estimated to have 12% survival
# 100-499 repos estimated to have 8% survival
```

## Monitoring

Track progress with:

```bash
# After each iteration
python update_survival_rates.py

# By language
python analyze_star_distribution.py --recommend
```

Look for:
-  Increasing % of 500+ repos in "analyzed" stage
-  Balanced temporal distribution (no year skew despite star tier filtering)
-  If 500+ repos scarce for a language, Phase 2 with 100-500 is acceptable

## Recommendations

1. **Collect in this order** (500+ availability descending):
   - Python (DONE)
   - Java (DONE)
   -Go
   - C#
   - JavaScript
   - TypeScript

2. **For each language**:
   - Phase 1: Use `min_stars=500` search
   - Check: Run `analyze_star_distribution.py`
   - If < 60% of target met: Phase 2 with 100-500
   - If > 80% of target from 500+: Keep Phase 1 only

3. **Document findings**:
   - Record actual survival rates in `LANGUAGE_SURVIVAL_RATES`
   - Update `analyze_star_distribution.py` after each complete collection
   - Note any language-specific quality issues

## Files Modified

- `collection/search.py` — Added `min_stars` parameter to collection functions
- `collection/config.py` — Documented STAR_TIER_CORE_THRESHOLD and star tier concept
- `analyze_star_distribution.py` — NEW: Shows star distribution by pipeline stage
- `collect_with_star_priority.py` — NEW: Planned two-phase automatic collection
- `update_survival_rates.py` — Existing script, already supports tier tracking
