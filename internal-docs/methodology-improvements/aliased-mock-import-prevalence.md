# Aliased mock imports: near-zero real exposure, and the DB-only check can't see the real risk anyway

**Date**: 2026-08-15
**Context**: calibrating a proposed "aliased mock import" limitation for
the paper -- how often does code alias `Mock`/`MagicMock`/`AsyncMock`/
`patch` (or the `unittest.mock` module itself) in a way that could make
`num_mocks`/the mocks list under-count? Investigation only, no code
changes.

---

## 1-2. The literal DB search, as specified

```sql
SELECT COUNT(*) FROM fixtures f JOIN test_files tf ON f.file_id=tf.id
WHERE tf.language='python' AND (
  raw_source LIKE '%import patch as%' OR
  raw_source LIKE '%import Mock as%' OR
  raw_source LIKE '%import MagicMock as%'
);
```

| Dataset | Python fixtures (total) | Matches |
|---|---|---|
| A | 11,712 | **0** |
| C sampled | 16,745 | **0** |

0/0 in both. `'%from unittest.mock import%'` anywhere in `raw_source`
(no `as` requirement) does appear -- 14 fixtures in A, 2 in C -- but all
16 are **local, in-function imports** (`def fixture(): from unittest.mock
import Mock; ...`, a real, if uncommon, Python idiom of importing inside
a function body rather than at module top). Inspected all 16 directly:
every one imports `Mock`/`MagicMock`/`AsyncMock`/`patch` by its literal
name, zero use `as`.

## 3. Does `raw_source` include the file's import section? No.

Confirmed directly in code: `_build_result()` (`detector_shared.py`)
sets `src_text = _source(func_node, src_bytes)`, and both `raw_source`
and the mock scan (`_extract_mocks(func_node, ...)`, same node) operate
on that exact text. For Python, `func_node` is the bare
`function_definition` node (decorator deliberately excluded, per this
project's own convention) -- so `raw_source` is **function-body-only**.
A module-top `from unittest.mock import patch as p` sits outside every
fixture's own AST subtree and can never appear in `raw_source`, aliased
or not. This makes item 1's DB search **structurally near-tautological**:
it can only ever find an alias declared *inside* a fixture body (the 16
local-import cases above), never the far more common top-of-file form --
so a 0-hit or low-hit DB search doesn't by itself mean aliasing is rare
in these codebases, only that it's invisible from this angle. Confirms
the request's own suspicion in item 3: **the limitation needs to be
described differently, and calibrated against real file content, not
`raw_source`.**

## 4. Calibrating against real files instead

Sampled 40 distinct Python test files per dataset (fetched at each
file's own recorded `commit_sha`) and searched the **whole file**, not
just the extracted fixture body, for two distinct patterns:

- **Narrow / actually risky**: `from unittest.mock import ... (Mock|
  MagicMock|AsyncMock|patch) ... as ...` -- aliasing the class/function
  itself, which *would* break the regex-based mock detector (see below).
- **Broad**: `import unittest.mock as ...` -- aliasing the *module*
  (typically to `mock`, matching the old standalone `mock` PyPI
  package's import style).

| Dataset | Files sampled | Mention "mock" at all | Module-level alias (`import unittest.mock as X`) | Class/function-level alias (the risky one) |
|---|---|---|---|---|
| A | 40 | 14 | 0 | **0** |
| C sampled | 40 | 8 | 1 (`forseti-security/forseti-security`) | **0** |

**0/80 (0%) sampled files use the risky form.** The one hit
(`forseti-security`'s `import unittest.mock as mock`) is the harmless
module-alias form.

## 5. Why the module-alias form (the one actually found) isn't a detection risk

Traced the one real example: `import unittest.mock as mock`, then
`location_rules_engine.LOGGER = mock.MagicMock()`. Tested the actual
patterns (`feature_extraction_patterns.yaml`'s `mock_patterns`) against
synthetic call sites with varying module aliases:

| Call site | Detected? |
|---|---|
| `mock.MagicMock()` (stdlib-idiom module alias) | matched |
| `um.MagicMock()` (arbitrary module alias) | matched |
| `um.patch("target")` (arbitrary module alias) | matched |
| `p("target")` (function itself aliased: `import patch as p`) | **not matched** |
| `MM()` (class itself aliased: `import MagicMock as MM`) | **not matched** |

The patterns (`MagicMock\s*\(`/`\bMock\s*\(`/`AsyncMock\s*\(`, and
`\bpatch\s*\(` with a lookbehind only excluding an immediately-preceding
`mock.`/`mocker.`) match on the bare class/function token with a plain
word-boundary check -- **any** prefix before it, `mock.`, `um.`,
`self.m.`, whatever, still matches, because the module name itself
never appears in the pattern. Aliasing the *module* (by far the more
common real-world pattern -- it's literally how `unittest.mock` was
written to be imported before it existed, mirroring the old third-party
`mock` package) is therefore **not a detection gap at all**. Only
aliasing the *class or function name itself* -- a much rarer style,
0/80 in this sample -- would actually cause under-counting.

## 6. Assessment

- **Prevalence in these corpora, as best calibrated**: effectively zero
  at the sample sizes checked -- 0/16 in-body local imports, 0/80 real
  sampled files, for the pattern that would actually matter (class/
  function-level aliasing). A 0/80 result gives roughly a <5% upper
  bound at typical confidence levels (rule of three, ~3.7/80) on the
  true file-level rate -- small, not provably zero, but not a material
  exposure either.
- **The DB-only check the request specified (item 1) will always read
  as ~0 regardless of true prevalence**, since `raw_source` never
  contains a file's own top-level imports -- this isn't evidence of
  low prevalence on its own, just a blind spot of that particular
  check. The file-level check in §4 is what actually calibrates the
  claim.
- **Recommended framing for the paper**: don't describe this as "aliased
  mock imports could cause under-detection" as a blanket caveat --
  narrow it to "aliasing `Mock`/`MagicMock`/`AsyncMock`/`patch`
  *themselves* (not the `unittest.mock` module, which is detected
  correctly regardless of its alias) could cause under-detection; found
  in 0/80 sampled files, an estimated low-single-digit-percent exposure
  at most." This is both more accurate and a weaker (more honest, less
  overstated) limitation than the unqualified version.

**Now tracked live**: `dataset_findings.py`'s "Aliased Mock Import
Detection (Python)" section (`_fetch_aliased_mock_import_counts()`) reruns
the §1-2 DB-only search on every re-collection (0/11,712 in Dataset A,
0/16,745 in Dataset C sampled, as of this writing) -- still subject to
the same blind spot as §3 above (in-body aliases only), documented
directly in that section's own text so a future 0 doesn't get
over-read as "confirmed rare" without the file-level caveat.
