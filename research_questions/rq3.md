# RQ3 -- Mocking

> How do agent-generated and human-written fixtures differ in mock usage -- prevalence, framework selection, and interaction depth?

Generated: 2026-08-19 15:56:59 UTC

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

### Dataset C (human-authored, pre-LLM) -- 191,883 fixtures, 21,919 mock usages

Mock prevalence: 10,174/191,883 fixtures (5.3%)

**Continuous metrics**

| Metric | n | median | mean | min | max | stdev |
|---|---|---|---|---|---|---|
| num_mocks | 191,883 | 0.00 | 0.11 | 0 | 32 | 0.70 |
| num_interactions_configured | 21,919 | 0.00 | 0.19 | 0 | 5 | 0.55 |

**has_mock distribution**

| Value | Count | % |
|---|---|---|
| no_mock | 181,709 | 94.7% |
| has_mock | 10,174 | 5.3% |

**framework distribution**

| Value | Count | % |
|---|---|---|
| jest | 7,429 | 33.9% |
| sinon | 5,772 | 26.3% |
| mockito | 4,195 | 19.1% |
| unittest_mock | 3,625 | 16.5% |
| pytest_monkeypatch | 505 | 2.3% |
| pytest_mock | 389 | 1.8% |
| easymock | 4 | 0.0% |

**category distribution**

| Value | Count | % |
|---|---|---|
| mock | 11,979 | 54.7% |
| stub | 5,408 | 24.7% |
| spy | 3,774 | 17.2% |
| fake | 593 | 2.7% |
| dummy | 165 | 0.8% |

**Mock prevalence by language**

| Language | Fixtures | With >=1 mock | Rate |
|---|---|---|---|
| java | 55,610 | 1,755 | 3.2% |
| javascript | 41,318 | 2,868 | 6.9% |
| python | 43,707 | 2,289 | 5.2% |
| typescript | 51,248 | 3,262 | 6.4% |

**Framework distribution by language**

| Language | Framework | Count |
|---|---|---|
| java | mockito | 4,195 |
| java | easymock | 4 |
| javascript | jest | 3,979 |
| javascript | sinon | 2,518 |
| javascript | unittest_mock | 9 |
| python | unittest_mock | 3,612 |
| python | pytest_monkeypatch | 505 |
| python | pytest_mock | 389 |
| typescript | jest | 3,450 |
| typescript | sinon | 3,254 |
| typescript | unittest_mock | 4 |

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

19,090/191,883 fixtures (9.95%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 58,262 | 3,612 | 6.20% | python=1,677, typescript=1,147, javascript=788 |
| javascript | 33,157 | 3,058 | 9.22% | typescript=2,081, python=662, java=315 |
| python | 44,044 | 3,012 | 6.84% | javascript=1,557, typescript=1,008, java=447 |
| typescript | 56,420 | 9,408 | 16.67% | javascript=8,874, python=336, java=198 |

## A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)

**Continuous metrics (Mann-Whitney U, two-sided)** -- num_mocks/ num_interactions_configured have no per-language family (not one of the metrics the paper review named), so both render Overall-only, shown at both the fixture-level (every fixture/mock as an observation) and repo-level (one mean value per repo) basis. Effect size is Cliff's delta (thresholds: negligible <0.147, small <0.33, medium <0.474, else large).

### num_mocks

**Fixture-level**

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 47208 | 191883 | U=4391566762.5 | -0.030 | negligible | <.001 | -- |

**Repo-level** (one mean value per repo)

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 1354 | 3005 | U=1728673.0 | -0.150 | small | <.001 | -- |

### num_interactions_configured

**Fixture-level**

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 10510 | 21919 | U=109751727.0 | -0.047 | negligible | <.001 | -- |

**Repo-level** (one mean value per repo)

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 574 | 948 | U=273832.5 | 0.006 | negligible | 0.791 | -- |

**has_mock (chi-square)** -- an "Overall" row (single pooled test, not BH-corrected) plus one BH-corrected row per language (one family, 4 languages -- see render_comparison_table()'s docstring in _shared.py). Effect size is Cramer's V (thresholds: negligible <0.1, small <0.3, medium <0.5, else large). framework/category are shown further below instead -- see this module's docstring for why they don't get a chi-square table.

### has_mock

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 1354 | 3005 | chi2=618.1 (df=1) | 0.051 | negligible | <.001 | -- |
| java | 97 | 608 | chi2=63.2 (df=1) | 0.033 | negligible | <.001 | <.001 |
| javascript | 115 | 822 | chi2=64.1 (df=1) | 0.038 | negligible | <.001 | <.001 |
| python | 531 | 1120 | chi2=2563.5 (df=1) | 0.216 | small | <.001 | <.001 |
| typescript | 749 | 762 | chi2=90.0 (df=1) | 0.033 | negligible | <.001 | <.001 |

> **`has_mock`'s result above is not used in the paper.** It's a pooled/per-language fixture-level chi-square, which treats fixtures clustered within a repo as independent observations and inflates both chi2 and Cramer's V (see [Limitations § Categorical Pseudo-Replication](../docs/reference/limitations.md#categorical-pseudo-replication)). The paper reports the repo-level `has_mock` proportion test in "Repo-level aggregates" below instead.

**Mocking framework distribution (descriptive, per language)** -- no statistical test or effect size: framework names are language-specific by construction (`unittest.mock` is Python-only, Sinon is JS-only, Mockito is Java-only), so a pooled cross-language comparison would just reflect each dataset's language mix (Dataset A is TypeScript-heavy, Dataset C skews Python/JavaScript), not an authorship-era effect. Top 3 frameworks per language per dataset (union of both sides' top 3), as a percentage of that language's own mock usages.

| Language | Framework | Dataset A (agent-authored) (%) | Dataset C (human-authored, pre-LLM) (%) |
|---|---|---|---|
| java | mockito | 100.0% | 99.9% |
| java | easymock | 0.0% | 0.1% |
| javascript | vitest | 53.4% | 0.0% |
| javascript | jest | 36.1% | 61.2% |
| javascript | sinon | 10.5% | 38.7% |
| javascript | unittest_mock | 0.0% | 0.1% |
| python | unittest_mock | 58.8% | 80.2% |
| python | pytest_monkeypatch | 39.1% | 11.2% |
| python | pytest_mock | 2.1% | 8.6% |
| typescript | vitest | 59.0% | 0.0% |
| typescript | jest | 38.8% | 51.4% |
| typescript | sinon | 2.2% | 48.5% |
| typescript | unittest_mock | 0.0% | 0.1% |

**Test-double category distribution, per language (Mann-Whitney U on per-repo category proportions, two-sided)** -- category naming conventions also vary systematically by language/ecosystem (Sinon's explicit `.spy()`/`.stub()` API vs Python's monolithic `Mock`/`MagicMock`), so this is computed once per language instead of pooled, reusing the same repo-level-proportion approach used elsewhere in this script. Each language's own category family (up to 5: dummy/fake/mock/spy/stub) is BH-FDR corrected independently of every other language's. Positive δ means the comparison dataset tends to have a larger proportion than A.

| Language | Category | Dataset A (agent-authored) (median %) | Dataset C (human-authored, pre-LLM) (median %) | δ (A vs C) | p (BH) |
|---|---|---|---|---|---|
| java | dummy | 0.0% | 0.0% | 0.011 | 0.848 |
| java | fake | 0.0% | 0.0% | 0.038 | 0.582 |
| java | mock | 100.0% | 100.0% | -0.148 | 0.337 |
| java | spy | 0.0% | 0.0% | 0.204 | 0.111 |
| java | stub | 0.0% | 0.0% | -0.043 | 0.582 |
| javascript | dummy | 0.0% | 0.0% | 0.016 | 0.669 |
| javascript | fake | 0.0% | 0.0% | -0.051 | 0.603 |
| javascript | mock | 55.6% | 35.6% | 0.014 | 0.903 |
| javascript | spy | 0.0% | 3.3% | 0.205 | 0.259 |
| javascript | stub | 0.0% | 0.0% | -0.158 | 0.259 |
| python | dummy | 0.0% | 0.0% | 0.033 | 0.109 |
| python | fake | 0.0% | 0.0% | -0.143 | <.001 |
| python | mock | 100.0% | 100.0% | 0.152 | <.001 |
| python | spy | 0.0% | 0.0% | 0.007 | 0.565 |
| python | stub | 0.0% | 0.0% | -0.155 | <.001 |
| typescript | dummy | 0.0% | 0.0% | 0.026 | 0.013 |
| typescript | fake | 0.0% | 0.0% | -0.077 | 0.011 |
| typescript | mock | 84.9% | 37.5% | -0.193 | <.001 |
| typescript | spy | 0.0% | 5.9% | 0.231 | <.001 |
| typescript | stub | 0.0% | 0.0% | -0.062 | 0.117 |

**Aggregate category distribution (descriptive only -- not used for inference)** -- pooled across all languages and repos, shown for reference only; the per-language table above is the real A-vs-C comparison.

| Category | Dataset A (agent-authored) (%) | Dataset C (human-authored, pre-LLM) (%) |
|---|---|---|
| dummy | 0.5% | 0.8% |
| fake | 6.5% | 2.7% |
| mock | 75.7% | 54.7% |
| spy | 7.5% | 17.2% |
| stub | 9.8% | 24.7% |

## Repo-level aggregates

has_mock re-tested with one *proportion-per-repo* value instead of pooled/per-language fixture-level chi-square, so each repo counts once regardless of how many fixtures it contributed. (num_mocks/num_interactions_configured already have their own repo-level Overall row above, in the main comparison section; framework/category are handled entirely in the main comparison section too -- see this module's docstring.)

### A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)

**has_mock, repo-level (Mann-Whitney U on per-repo category proportions, two-sided)** -- the chi-square table above treats every fixture as an independent observation, but fixtures cluster within repos (shared framework choice, project convention), which inflates chi2 and partially corrupts Cramer's V. This instead compares, per repo, what fraction of its fixtures have >=1 mock -- so each repo counts once regardless of how many fixtures it contributed. **This is the `has_mock` result reported in the paper.** (framework's per-language descriptive table and category's per-language repo-level proportion table are both in the main comparison section above instead -- neither gets a pooled-across-languages view here, see this module's docstring for why.)

| Category | A median | A mean | C median | C mean | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|---|---|---|
| has_mock | 0.0% | 11.7% | 0.0% | 5.6% | 1354 | 3005 | U=1743125.5 | -0.143 | negligible | <.001 | <.001 |
| no_mock | 100.0% | 88.3% | 100.0% | 94.4% | 1354 | 3005 | U=2325644.5 | 0.143 | negligible | <.001 | <.001 |

**has_mock, repo-level, per language** -- the pooled Overall row above can still partly reflect each dataset's own language mix (Dataset A skews TypeScript, Dataset C skews Python/JavaScript) rather than a within-language authorship-era effect, so this reruns the same repo-level-proportion Mann-Whitney U + Cliff's delta test once per language (own repos, own denominator, languages with data on both sides only). Only `has_mock`'s own test is shown per language -- `no_mock` is its exact complement -- BH-FDR corrected across this variable's own per-language family, independent of the Overall row above.

| Language | Dataset A (agent-authored) (median %) | Dataset C (human-authored, pre-LLM) (median %) | δ (A vs C) | p (BH) |
|---|---|---|---|---|
| java | 0.0% | 0.0% | -0.040 | 0.433 |
| javascript | 0.0% | 0.0% | 0.098 | 0.072 |
| python | 10.0% | 0.0% | -0.366 | <.001 |
| typescript | 0.0% | 0.0% | 0.025 | 0.425 |
