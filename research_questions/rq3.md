# RQ3 -- Mocking

> How do agent-generated and human-written fixtures differ in mock usage -- prevalence, framework selection, and interaction depth?

Generated: 2026-08-21 00:06:39 UTC

See [docs/research-questions.md](../docs/research-questions.md) for the full RQ3 definition.

## Per-dataset summary

### Dataset A (agent-authored) -- 47,208 fixtures, 10,510 mock usages

Mock prevalence: 3,924/47,208 fixtures (8.3%)

**Continuous metrics**

| Metric | n | median | mean | min | max | stdev |
|---|---|---|---|---|---|---|
| num_mocks | 47,208 | 0.00 | 0.22 | 0 | 45 | 1.21 |
| num_interactions_configured | 10,510 | 0.00 | 0.27 | 0 | 5 | 0.65 |

**has_mock distribution**

| Value | Count | % |
|---|---|---|
| no_mock | 43,284 | 91.7% |
| has_mock | 3,924 | 8.3% |

**framework distribution**

| Value | Count | % |
|---|---|---|
| unittest_mock | 3,137 | 29.8% |
| vitest | 2,868 | 27.3% |
| pytest_monkeypatch | 2,087 | 19.9% |
| jest | 1,891 | 18.0% |
| mockito | 262 | 2.5% |
| sinon | 152 | 1.4% |
| pytest_mock | 113 | 1.1% |

**category distribution**

| Value | Count | % |
|---|---|---|
| mock | 7,955 | 75.7% |
| stub | 1,032 | 9.8% |
| spy | 793 | 7.5% |
| fake | 679 | 6.5% |
| dummy | 51 | 0.5% |

**Mock prevalence by language**

| Language | Fixtures | With >=1 mock | Rate |
|---|---|---|---|
| java | 1,398 | 98 | 7.0% |
| javascript | 4,174 | 154 | 3.7% |
| python | 11,035 | 2,214 | 20.1% |
| typescript | 30,601 | 1,458 | 4.8% |

**Framework distribution by language**

| Language | Framework | Count |
|---|---|---|
| java | mockito | 262 |
| javascript | vitest | 275 |
| javascript | jest | 186 |
| javascript | sinon | 54 |
| python | unittest_mock | 3,136 |
| python | pytest_monkeypatch | 2,087 |
| python | pytest_mock | 113 |
| typescript | vitest | 2,593 |
| typescript | jest | 1,705 |
| typescript | sinon | 98 |
| typescript | unittest_mock | 1 |

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

3,561/47,208 fixtures (7.54%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 1,429 | 111 | 7.77% | typescript=83, python=27, javascript=1 |
| javascript | 3,385 | 962 | 28.42% | typescript=797, python=142, java=23 |
| python | 11,000 | 492 | 4.47% | typescript=323, javascript=144, java=25 |
| typescript | 31,394 | 1,996 | 6.36% | javascript=1,606, python=358, java=32 |

### Dataset C (human-authored, pre-LLM) -- 47,208 fixtures, 6,134 mock usages

Mock prevalence: 2,882/47,208 fixtures (6.1%)

**Continuous metrics**

| Metric | n | median | mean | min | max | stdev |
|---|---|---|---|---|---|---|
| num_mocks | 47,208 | 0.00 | 0.13 | 0 | 31 | 0.76 |
| num_interactions_configured | 6,134 | 0.00 | 0.13 | 0 | 5 | 0.47 |

**has_mock distribution**

| Value | Count | % |
|---|---|---|
| no_mock | 44,326 | 93.9% |
| has_mock | 2,882 | 6.1% |

**framework distribution**

| Value | Count | % |
|---|---|---|
| jest | 2,581 | 42.1% |
| sinon | 2,200 | 35.9% |
| unittest_mock | 993 | 16.2% |
| mockito | 137 | 2.2% |
| pytest_monkeypatch | 130 | 2.1% |
| pytest_mock | 93 | 1.5% |

**category distribution**

| Value | Count | % |
|---|---|---|
| mock | 2,594 | 42.3% |
| stub | 2,029 | 33.1% |
| spy | 1,282 | 20.9% |
| fake | 198 | 3.2% |
| dummy | 31 | 0.5% |

**Mock prevalence by language**

| Language | Fixtures | With >=1 mock | Rate |
|---|---|---|---|
| java | 1,398 | 43 | 3.1% |
| javascript | 4,174 | 281 | 6.7% |
| python | 11,035 | 586 | 5.3% |
| typescript | 30,601 | 1,972 | 6.4% |

**Framework distribution by language**

| Language | Framework | Count |
|---|---|---|
| java | mockito | 137 |
| javascript | jest | 368 |
| javascript | sinon | 241 |
| javascript | unittest_mock | 1 |
| python | unittest_mock | 990 |
| python | pytest_monkeypatch | 130 |
| python | pytest_mock | 93 |
| typescript | jest | 2,213 |
| typescript | sinon | 1,959 |
| typescript | unittest_mock | 2 |

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

4,318/47,208 fixtures (9.15%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 2,541 | 1,168 | 45.97% | typescript=684, python=428, javascript=56 |
| javascript | 4,454 | 1,385 | 31.10% | typescript=1,223, python=156, java=6 |
| python | 11,119 | 758 | 6.82% | typescript=607, javascript=135, java=16 |
| typescript | 29,094 | 1,007 | 3.46% | javascript=914, python=90, java=3 |

## A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)

**Continuous metrics (Mann-Whitney U, two-sided)** -- num_mocks/ num_interactions_configured have no per-language family (not one of the metrics the paper review named), so both render Overall-only, shown at both the fixture-level (every fixture/mock as an observation) and repo-level (one mean value per repo) basis. Effect size is Cliff's delta (thresholds: negligible <0.147, small <0.33, medium <0.474, else large).

### num_mocks

**Fixture-level**

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 47208 | 47208 | U=1089316348.0 | -0.022 | negligible | <.001 | -- |

**Repo-level** (one mean value per repo)

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 1354 | 2325 | U=1247171.5 | -0.208 | small | <.001 | -- |

### num_interactions_configured

**Fixture-level**

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 10510 | 6134 | U=29235790.5 | -0.093 | negligible | <.001 | -- |

**Repo-level** (one mean value per repo)

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 574 | 530 | U=137644.0 | -0.095 | negligible | <.001 | -- |

**has_mock (chi-square)** -- an "Overall" row (single pooled test, not BH-corrected) plus one BH-corrected row per language (one family, 4 languages -- see render_comparison_table()'s docstring in _shared.py). Effect size is Cramer's V (thresholds: negligible <0.1, small <0.3, medium <0.5, else large). framework/category are shown further below instead -- see this module's docstring for why they don't get a chi-square table.

### has_mock

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 1354 | 2325 | chi2=171.6 (df=1) | 0.043 | negligible | <.001 | -- |
| java | 97 | 267 | chi2=21.8 (df=1) | 0.088 | negligible | <.001 | <.001 |
| javascript | 115 | 557 | chi2=38.5 (df=1) | 0.068 | negligible | <.001 | <.001 |
| python | 531 | 944 | chi2=1082.8 (df=1) | 0.221 | small | <.001 | <.001 |
| typescript | 749 | 735 | chi2=81.3 (df=1) | 0.036 | negligible | <.001 | <.001 |

> **`has_mock`'s result above is not used in the paper.** It's a pooled/per-language fixture-level chi-square, which treats fixtures clustered within a repo as independent observations and inflates both chi2 and Cramer's V (see [Limitations § Categorical Pseudo-Replication](../docs/reference/limitations.md#categorical-pseudo-replication)). The paper reports the repo-level `has_mock` proportion test in "Repo-level aggregates" below instead.

**Mocking framework distribution (descriptive, per language)** -- no statistical test or effect size: framework names are language-specific by construction (`unittest.mock` is Python-only, Sinon is JS-only, Mockito is Java-only), so a pooled cross-language comparison would just reflect each dataset's language mix (Dataset A is TypeScript-heavy, Dataset C skews Python/JavaScript), not an authorship-era effect. Top 3 frameworks per language per dataset (union of both sides' top 3), as a percentage of that language's own mock usages.

| Language | Framework | Dataset A (agent-authored) (%) | Dataset C (human-authored, pre-LLM) (%) |
|---|---|---|---|
| java | mockito | 100.0% | 100.0% |
| javascript | vitest | 53.4% | 0.0% |
| javascript | jest | 36.1% | 60.3% |
| javascript | sinon | 10.5% | 39.5% |
| javascript | unittest_mock | 0.0% | 0.2% |
| python | unittest_mock | 58.8% | 81.6% |
| python | pytest_monkeypatch | 39.1% | 10.7% |
| python | pytest_mock | 2.1% | 7.7% |
| typescript | vitest | 59.0% | 0.0% |
| typescript | jest | 38.8% | 53.0% |
| typescript | sinon | 2.2% | 46.9% |
| typescript | unittest_mock | 0.0% | 0.0% |

**Test-double category distribution, per language (Mann-Whitney U on per-repo category proportions, two-sided)** -- category naming conventions also vary systematically by language/ecosystem (Sinon's explicit `.spy()`/`.stub()` API vs Python's monolithic `Mock`/`MagicMock`), so this is computed once per language instead of pooled, reusing the same repo-level-proportion approach used elsewhere in this script. Each language's own category family (up to 5: dummy/fake/mock/spy/stub) is BH-FDR corrected independently of every other language's. Positive δ means the comparison dataset tends to have a larger proportion than A.

| Language | Category | Dataset A (agent-authored) (median %) | Dataset C (human-authored, pre-LLM) (median %) | δ (A vs C) | p (BH) |
|---|---|---|---|---|---|
| java | dummy | 0.0% | 0.0% | -0.071 | 0.383 |
| java | fake | 0.0% | 0.0% | -0.001 | 1.000 |
| java | mock | 100.0% | 100.0% | -0.096 | 0.508 |
| java | spy | 0.0% | 0.0% | 0.132 | 0.383 |
| java | stub | 0.0% | 0.0% | -0.070 | 0.507 |
| javascript | fake | 0.0% | 0.0% | -0.085 | 0.215 |
| javascript | mock | 55.6% | 50.0% | 0.064 | 0.648 |
| javascript | spy | 0.0% | 0.0% | 0.049 | 0.648 |
| javascript | stub | 0.0% | 0.0% | -0.163 | 0.215 |
| python | dummy | 0.0% | 0.0% | -0.002 | 0.914 |
| python | fake | 0.0% | 0.0% | -0.191 | <.001 |
| python | mock | 100.0% | 100.0% | 0.216 | <.001 |
| python | spy | 0.0% | 0.0% | -0.011 | 0.391 |
| python | stub | 0.0% | 0.0% | -0.167 | <.001 |
| typescript | dummy | 0.0% | 0.0% | 0.026 | 0.013 |
| typescript | fake | 0.0% | 0.0% | -0.081 | 0.010 |
| typescript | mock | 84.9% | 27.3% | -0.205 | <.001 |
| typescript | spy | 0.0% | 5.9% | 0.223 | <.001 |
| typescript | stub | 0.0% | 0.0% | -0.052 | 0.210 |

**Aggregate category distribution (descriptive only -- not used for inference)** -- pooled across all languages and repos, shown for reference only; the per-language table above is the real A-vs-C comparison.

| Category | Dataset A (agent-authored) (%) | Dataset C (human-authored, pre-LLM) (%) |
|---|---|---|
| dummy | 0.5% | 0.5% |
| fake | 6.5% | 3.2% |
| mock | 75.7% | 42.3% |
| spy | 7.5% | 20.9% |
| stub | 9.8% | 33.1% |

## Repo-level aggregates

has_mock re-tested with one *proportion-per-repo* value instead of pooled/per-language fixture-level chi-square, so each repo counts once regardless of how many fixtures it contributed. (num_mocks/num_interactions_configured already have their own repo-level Overall row above, in the main comparison section; framework/category are handled entirely in the main comparison section too -- see this module's docstring.)

### A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)

**has_mock, repo-level (Mann-Whitney U on per-repo category proportions, two-sided)** -- the chi-square table above treats every fixture as an independent observation, but fixtures cluster within repos (shared framework choice, project convention), which inflates chi2 and partially corrupts Cramer's V. This instead compares, per repo, what fraction of its fixtures have >=1 mock -- so each repo counts once regardless of how many fixtures it contributed. **This is the `has_mock` result reported in the paper.** (framework's per-language descriptive table and category's per-language repo-level proportion table are both in the main comparison section above instead -- neither gets a pooled-across-languages view here, see this module's docstring for why.)

| Category | A median | A mean | C median | C mean | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|---|---|---|
| has_mock | 0.0% | 11.7% | 0.0% | 6.2% | 1354 | 2325 | U=1261489.5 | -0.199 | small | <.001 | <.001 |
| no_mock | 100.0% | 88.3% | 100.0% | 93.8% | 1354 | 2325 | U=1886560.5 | 0.199 | small | <.001 | <.001 |

**has_mock, repo-level, per language** -- the pooled Overall row above can still partly reflect each dataset's own language mix (Dataset A skews TypeScript, Dataset C skews Python/JavaScript) rather than a within-language authorship-era effect, so this reruns the same repo-level-proportion Mann-Whitney U + Cliff's delta test once per language (own repos, own denominator, languages with data on both sides only). Only `has_mock`'s own test is shown per language -- `no_mock` is its exact complement -- BH-FDR corrected across this variable's own per-language family, independent of the Overall row above.

| Language | Dataset A (agent-authored) (median %) | Dataset C (human-authored, pre-LLM) (median %) | δ (A vs C) | p (BH) |
|---|---|---|---|---|
| java | 0.0% | 0.0% | -0.170 | <.001 |
| javascript | 0.0% | 0.0% | 0.010 | 0.819 |
| python | 10.0% | 0.0% | -0.401 | <.001 |
| typescript | 0.0% | 0.0% | -0.007 | 0.819 |
