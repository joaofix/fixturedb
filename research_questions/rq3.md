# RQ3 -- Mocking

> How do agent-generated and human-written fixtures differ in mock usage -- prevalence, framework selection, and interaction depth?

Generated: 2026-08-16 02:34:18 UTC

See [docs/research-questions.md](../docs/research-questions.md) for the full RQ3 definition.

## Per-dataset summary

### Dataset A (agent-authored) -- 39,088 fixtures, 14,405 mock usages

Mock prevalence: 3,385/39,088 fixtures (8.7%)

**Continuous metrics**

| Metric | n | median | mean | min | max | stdev |
|---|---|---|---|---|---|---|
| num_mocks | 39,088 | 0.00 | 0.22 | 0 | 45 | 1.14 |
| num_interactions_configured | 14,405 | 0.00 | 0.37 | 0 | 5 | 0.74 |

**has_mock distribution**

| Value | Count | % |
|---|---|---|
| no_mock | 35,703 | 91.3% |
| has_mock | 3,385 | 8.7% |

**framework distribution**

| Value | Count | % |
|---|---|---|
| unittest_mock | 6,264 | 43.5% |
| pytest_monkeypatch | 4,514 | 31.3% |
| vitest | 2,105 | 14.6% |
| jest | 1,029 | 7.1% |
| mockito | 279 | 1.9% |
| pytest_mock | 143 | 1.0% |
| sinon | 71 | 0.5% |

**category distribution**

| Value | Count | % |
|---|---|---|
| mock | 10,963 | 76.1% |
| stub | 1,528 | 10.6% |
| fake | 1,182 | 8.2% |
| spy | 599 | 4.2% |
| dummy | 133 | 0.9% |

**Mock prevalence by language**

| Language | Fixtures | With >=1 mock | Rate |
|---|---|---|---|
| java | 1,209 | 110 | 9.1% |
| javascript | 2,575 | 95 | 3.7% |
| python | 11,712 | 2,252 | 19.2% |
| typescript | 23,592 | 928 | 3.9% |

**Framework distribution by language**

| Language | Framework | Count |
|---|---|---|
| java | mockito | 279 |
| javascript | vitest | 159 |
| javascript | jest | 115 |
| javascript | sinon | 67 |
| python | unittest_mock | 6,264 |
| python | pytest_monkeypatch | 4,514 |
| python | pytest_mock | 143 |
| typescript | vitest | 1,946 |
| typescript | jest | 914 |
| typescript | sinon | 4 |

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

2,559/39,088 fixtures (6.55%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 1,320 | 198 | 15.00% | typescript=122, python=75, javascript=1 |
| javascript | 1,684 | 332 | 19.71% | typescript=190, python=119, java=23 |
| python | 11,798 | 614 | 5.20% | typescript=409, javascript=149, java=56 |
| typescript | 24,286 | 1,415 | 5.83% | javascript=1,073, python=334, java=8 |

### Dataset C (human-authored, pre-LLM) -- 211,384 fixtures, 23,186 mock usages

Mock prevalence: 10,614/211,384 fixtures (5.0%)

**Continuous metrics**

| Metric | n | median | mean | min | max | stdev |
|---|---|---|---|---|---|---|
| num_mocks | 211,384 | 0.00 | 0.11 | 0 | 32 | 0.69 |
| num_interactions_configured | 23,186 | 0.00 | 0.19 | 0 | 5 | 0.55 |

**has_mock distribution**

| Value | Count | % |
|---|---|---|
| no_mock | 200,770 | 95.0% |
| has_mock | 10,614 | 5.0% |

**framework distribution**

| Value | Count | % |
|---|---|---|
| jest | 7,866 | 33.9% |
| sinon | 5,846 | 25.2% |
| mockito | 5,145 | 22.2% |
| unittest_mock | 3,515 | 15.2% |
| pytest_monkeypatch | 492 | 2.1% |
| pytest_mock | 318 | 1.4% |
| easymock | 4 | 0.0% |

**category distribution**

| Value | Count | % |
|---|---|---|
| mock | 12,540 | 54.1% |
| stub | 5,897 | 25.4% |
| spy | 3,949 | 17.0% |
| fake | 584 | 2.5% |
| dummy | 216 | 0.9% |

**Mock prevalence by language**

| Language | Fixtures | With >=1 mock | Rate |
|---|---|---|---|
| java | 76,557 | 2,189 | 2.9% |
| javascript | 38,997 | 2,814 | 7.2% |
| python | 39,662 | 2,141 | 5.4% |
| typescript | 56,168 | 3,470 | 6.2% |

**Framework distribution by language**

| Language | Framework | Count |
|---|---|---|
| java | mockito | 5,145 |
| java | easymock | 4 |
| javascript | jest | 3,736 |
| javascript | sinon | 2,636 |
| javascript | unittest_mock | 9 |
| python | unittest_mock | 3,492 |
| python | pytest_monkeypatch | 492 |
| python | pytest_mock | 318 |
| typescript | jest | 4,130 |
| typescript | sinon | 3,210 |
| typescript | unittest_mock | 14 |

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

18,660/211,384 fixtures (8.83%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 79,738 | 4,044 | 5.07% | python=1,818, typescript=1,164, javascript=1,062 |
| javascript | 30,836 | 2,862 | 9.28% | typescript=2,150, python=388, java=324 |
| python | 38,962 | 1,895 | 4.86% | typescript=865, javascript=689, java=341 |
| typescript | 61,848 | 9,859 | 15.94% | javascript=9,272, python=389, java=198 |

## A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)

**Continuous metrics (Mann-Whitney U, two-sided)** -- num_mocks/ num_interactions_configured have no per-language family (not one of the metrics the paper review named), so both render Overall-only, shown at both the fixture-level (every fixture/mock as an observation) and repo-level (one mean value per repo) basis. Effect size is Cliff's delta (thresholds: negligible <0.147, small <0.33, medium <0.474, else large).

### num_mocks

**Fixture-level**

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 39088 | 211384 | U=3980247559.5 | -0.037 | negligible | <.001 | -- |

**Repo-level** (one mean value per repo)

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 1044 | 3244 | U=1394379.0 | -0.177 | small | <.001 | -- |

### num_interactions_configured

**Fixture-level**

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 14405 | 23186 | U=148612505.5 | -0.110 | negligible | <.001 | -- |

**Repo-level** (one mean value per repo)

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 466 | 1032 | U=228546.0 | -0.050 | negligible | 0.060 | -- |

**has_mock (chi-square)** -- an "Overall" row (single pooled test, not BH-corrected) plus one BH-corrected row per language (one family, 4 languages -- see render_comparison_table()'s docstring in _shared.py). Effect size is Cramer's V (thresholds: negligible <0.1, small <0.3, medium <0.5, else large). framework/category are shown further below instead -- see this module's docstring for why they don't get a chi-square table.

### has_mock

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 1044 | 3244 | chi2=827.1 (df=1) | 0.057 | negligible | <.001 | -- |
| java | 84 | 702 | chi2=159.3 (df=1) | 0.045 | negligible | <.001 | <.001 |
| javascript | 88 | 834 | chi2=45.6 (df=1) | 0.033 | negligible | <.001 | <.001 |
| python | 490 | 1155 | chi2=2209.9 (df=1) | 0.207 | small | <.001 | <.001 |
| typescript | 502 | 859 | chi2=160.2 (df=1) | 0.045 | negligible | <.001 | <.001 |

> **`has_mock`'s result above is not used in the paper.** It's a pooled/per-language fixture-level chi-square, which treats fixtures clustered within a repo as independent observations and inflates both chi2 and Cramer's V (see [Limitations § Categorical Pseudo-Replication](../docs/reference/limitations.md#categorical-pseudo-replication)). The paper reports the repo-level `has_mock` proportion test in "Repo-level aggregates" below instead.

**Mocking framework distribution (descriptive, per language)** -- no statistical test or effect size: framework names are language-specific by construction (`unittest.mock` is Python-only, Sinon is JS-only, Mockito is Java-only), so a pooled cross-language comparison would just reflect each dataset's language mix (Dataset A is TypeScript-heavy, Dataset C skews Python/JavaScript), not an authorship-era effect. Top 3 frameworks per language per dataset (union of both sides' top 3), as a percentage of that language's own mock usages.

| Language | Framework | Dataset A (agent-authored) (%) | Dataset C (human-authored, pre-LLM) (%) |
|---|---|---|---|
| java | mockito | 100.0% | 99.9% |
| java | easymock | 0.0% | 0.1% |
| javascript | vitest | 46.6% | 0.0% |
| javascript | jest | 33.7% | 58.5% |
| javascript | sinon | 19.6% | 41.3% |
| javascript | unittest_mock | 0.0% | 0.1% |
| python | unittest_mock | 57.4% | 81.2% |
| python | pytest_monkeypatch | 41.3% | 11.4% |
| python | pytest_mock | 1.3% | 7.4% |
| typescript | vitest | 67.9% | 0.0% |
| typescript | jest | 31.9% | 56.2% |
| typescript | sinon | 0.1% | 43.6% |
| typescript | unittest_mock | 0.0% | 0.2% |

**Test-double category distribution, per language (Mann-Whitney U on per-repo category proportions, two-sided)** -- category naming conventions also vary systematically by language/ecosystem (Sinon's explicit `.spy()`/`.stub()` API vs Python's monolithic `Mock`/`MagicMock`), so this is computed once per language instead of pooled, reusing the same repo-level-proportion approach used elsewhere in this script. Each language's own category family (up to 5: dummy/fake/mock/spy/stub) is BH-FDR corrected independently of every other language's. Positive δ means the comparison dataset tends to have a larger proportion than A.

| Language | Category | Dataset A (agent-authored) (median %) | Dataset C (human-authored, pre-LLM) (median %) | δ (A vs C) | p (BH) |
|---|---|---|---|---|---|
| java | dummy | 0.0% | 0.0% | -0.043 | 0.583 |
| java | fake | 0.0% | 0.0% | 0.011 | 0.852 |
| java | mock | 100.0% | 100.0% | -0.085 | 0.583 |
| java | spy | 0.0% | 0.0% | 0.206 | 0.151 |
| java | stub | 0.0% | 0.0% | -0.082 | 0.451 |
| javascript | dummy | 0.0% | 0.0% | 0.011 | 0.786 |
| javascript | fake | 0.0% | 0.0% | -0.015 | 0.810 |
| javascript | mock | 0.0% | 33.3% | 0.244 | 0.122 |
| javascript | spy | 0.0% | 1.0% | 0.149 | 0.370 |
| javascript | stub | 19.1% | 0.0% | -0.345 | 0.006 |
| python | dummy | 0.0% | 0.0% | 0.041 | 0.060 |
| python | fake | 0.0% | 0.0% | -0.184 | <.001 |
| python | mock | 100.0% | 100.0% | 0.168 | <.001 |
| python | spy | 0.0% | 0.0% | -0.001 | 0.921 |
| python | stub | 0.0% | 0.0% | -0.155 | <.001 |
| typescript | dummy | 0.0% | 0.0% | 0.027 | 0.052 |
| typescript | fake | 0.0% | 0.0% | -0.082 | 0.010 |
| typescript | mock | 86.1% | 37.0% | -0.200 | <.001 |
| typescript | spy | 0.0% | 4.6% | 0.220 | <.001 |
| typescript | stub | 0.0% | 0.0% | -0.047 | 0.282 |

**Aggregate category distribution (descriptive only -- not used for inference)** -- pooled across all languages and repos, shown for reference only; the per-language table above is the real A-vs-C comparison.

| Category | Dataset A (agent-authored) (%) | Dataset C (human-authored, pre-LLM) (%) |
|---|---|---|
| dummy | 0.9% | 0.9% |
| fake | 8.2% | 2.5% |
| mock | 76.1% | 54.1% |
| spy | 4.2% | 17.0% |
| stub | 10.6% | 25.4% |

## Repo-level aggregates

has_mock re-tested with one *proportion-per-repo* value instead of pooled/per-language fixture-level chi-square, so each repo counts once regardless of how many fixtures it contributed. (num_mocks/num_interactions_configured already have their own repo-level Overall row above, in the main comparison section; framework/category are handled entirely in the main comparison section too -- see this module's docstring.)

### A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)

**has_mock, repo-level (Mann-Whitney U on per-repo category proportions, two-sided)** -- the chi-square table above treats every fixture as an independent observation, but fixtures cluster within repos (shared framework choice, project convention), which inflates chi2 and partially corrupts Cramer's V. This instead compares, per repo, what fraction of its fixtures have >=1 mock -- so each repo counts once regardless of how many fixtures it contributed. **This is the `has_mock` result reported in the paper.** (framework's per-language descriptive table and category's per-language repo-level proportion table are both in the main comparison section above instead -- neither gets a pooled-across-languages view here, see this module's docstring for why.)

| Category | A median | A mean | C median | C mean | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|---|---|---|
| has_mock | 0.0% | 12.9% | 0.0% | 5.6% | 1044 | 3244 | U=1405183.5 | -0.170 | small | <.001 | <.001 |
| no_mock | 100.0% | 87.1% | 100.0% | 94.4% | 1044 | 3244 | U=1981552.5 | 0.170 | small | <.001 | <.001 |

**has_mock, repo-level, per language** -- the pooled Overall row above can still partly reflect each dataset's own language mix (Dataset A skews TypeScript, Dataset C skews Python/JavaScript) rather than a within-language authorship-era effect, so this reruns the same repo-level-proportion Mann-Whitney U + Cliff's delta test once per language (own repos, own denominator, languages with data on both sides only). Only `has_mock`'s own test is shown per language -- `no_mock` is its exact complement -- BH-FDR corrected across this variable's own per-language family, independent of the Overall row above.

| Language | Dataset A (agent-authored) (median %) | Dataset C (human-authored, pre-LLM) (median %) | δ (A vs C) | p (BH) |
|---|---|---|---|---|
| java | 0.0% | 0.0% | -0.040 | 0.453 |
| javascript | 0.0% | 0.0% | 0.082 | 0.162 |
| python | 11.3% | 0.0% | -0.394 | <.001 |
| typescript | 0.0% | 0.0% | 0.052 | 0.113 |
