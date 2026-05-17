# EDA Color Coherence Audit & Updates

**Date**: April 5, 2026  
**Status**:  Complete

---

## Problem Statement

Quantitative EDA plots were using inconsistent color schemes:
- **Language-categorized plots** (p01, p03a, p04a):  Correctly used `LANG_PALETTE`
- **Ordinal/sequential plots** (p02, p05a):  Used custom, vibrant color gradients (green→orange→red→purple→dark) that were inconsistent and visually cluttered
- **Semantic categorical plots** (p04c mock styles, p07 mock styles): ️ Used custom hardcoded color dicts, not centralized

---

## Solution: Centralized Color Palettes

### Updated `eda/eda_common.py`

Added three semantic palettes to serve as single source of truth:

#### 1. **SEQUENTIAL_PALETTE** (for ordinal categories)
```python
SEQUENTIAL_PALETTE = ["#D0D0D0", "#A0A0A0", "#707070", "#404040", "#1A1A1A"]  # light to dark gray
```
- **Use case**: Star tier distributions, nesting depth categories
- **Principle**: Subtle grayscale progression for clarity without visual distraction
- **Benefit**: Minimal visual vocabulary (single hue, ordinal semantics)

#### 2. **MOCK_STYLE_PALETTE** (for mock testing techniques)
```python
MOCK_STYLE_PALETTE = {
    "mock": "#E74C3C",   # Red for actual mocks
    "stub": "#3498DB",   # Blue for stubs  
    "spy": "#F39C12",    # Orange for spies
    "fake": "#2ECC71",   # Green for fakes
}
```
- **Use case**: p04c_mock_styles.py, p07_mock_prevalence.py
- **Principle**: Semantic colors (red=mocks, blue=stubs, etc.) with high saturation for clarity
- **Benefit**: Categorical distinction, memorable associations

---

## Files Updated

### 1. **eda/eda_common.py**
 Added `SEQUENTIAL_PALETTE` and `MOCK_STYLE_PALETTE` constants

### 2. **eda/quantitative/p02_star_distribution.py**
**Before**: Custom `tier_colors = ["#2ecc71", "#f39c12", "#e74c3c", "#9b59b6", "#34495e"]`  
**After**: Uses `SEQUENTIAL_PALETTE[i]` from eda_common  
**Impact**: Subtle grayscale for 5 star tiers (0–100  through 5k+ )

### 3. **eda/quantitative/p05a_nesting_depth.py**
**Before**: Custom `depth_colors = ["#2ecc71", "#f39c12", "#e74c3c", "#9b59b6", "#34495e"]`  
**After**: Uses `SEQUENTIAL_PALETTE[i]` from eda_common  
**Impact**: Subtle grayscale for 5 nesting depth categories (Flat through Very Deep)

### 4. **eda/quantitative/p04c_mock_styles.py**
**Before**: Local `style_colors = {"mock": "#FF6B6B", "stub": "#4ECDC4", ...}`  
**After**: Uses `MOCK_STYLE_PALETTE.get(style, "#CCCCCC")` from eda_common  
**Impact**: Centralized, semantic color management for 4 mock styles

### 5. **eda/quantitative/p07_mock_prevalence.py**
**Before**: Local `style_colors = {"mock": "#FF6B6B", "stub": "#4ECDC4", ...}`  
**After**: Uses `MOCK_STYLE_PALETTE.get(style, "#CCCCCC")` from eda_common  
**Impact**: Consistent mock style colors across all multi-plot visualizations

---

## Color Scheme Philosophy

| Plot Type | Color Source | Purpose | Example Files |
|-----------|--------------|---------|----------------|
| **Language-categorized** | `LANG_PALETTE` (4 distinct colors) | Identify Python vs Java vs JS vs TS | p01, p03a, p04a, p05b, p05f, p06, p07 (ax1) |
| **Ordinal/sequential** | `SEQUENTIAL_PALETTE` (5 grays, light→dark) | Show progression without distraction | p02 (star tiers), p05a (nesting depths) |
| **Semantic categorical** | `MOCK_STYLE_PALETTE` (4 meaningful colors) | Represent mock, stub, spy, fake distinctly | p04c, p07 (ax3) |

---

## Benefits

 **Minimal visual vocabulary**: Max 5 distinct colors per chart (down from unlimited)  
 **Semantic coherence**: Colors match meaning (red=mocks, blue=stubs, etc.)  
 **Single source of truth**: All palettes in `eda_common.py`  
 **Consistency**: Same mock style colors across all plots  
 **Accessibility**: Grayscale progression easier to understand than rainbow gradients  
 **Professional appearance**: Subtle, intentional color choices improve publication readiness  

---

## Testing Recommendations

Run each updated plot to verify visual clarity:
```bash
python -m eda.quantitative.p02_star_distribution --out=output/eda/quantitative --show
python -m eda.quantitative.p05a_nesting_depth --out=output/eda/quantitative --show
python -m eda.quantitative.p04c_mock_styles --out=output/eda/quantitative --show
python -m eda.quantitative.p07_mock_prevalence --out=output/eda/quantitative --show
```

All plots should now use centralized, coherent color schemes.
