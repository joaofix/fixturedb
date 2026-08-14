# RQ3 -- Mocking

> How do agent-generated and human-written fixtures differ in mock usage -- prevalence, framework selection, and interaction depth?

Generated: 2026-08-14 19:20:49 UTC

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

### Dataset C (human-authored, pre-LLM) -- 39,377 fixtures, 5,993 mock usages

Mock prevalence: 2,777/39,377 fixtures (7.1%)

**Continuous metrics**

| Metric | n | median | mean | min | max | stdev |
|---|---|---|---|---|---|---|
| num_mocks | 39,377 | 0.00 | 0.15 | 0 | 21 | 0.72 |
| num_interactions_configured | 5,993 | 0.00 | 0.20 | 0 | 4 | 0.55 |

**has_mock distribution**

| Value | Count | % |
|---|---|---|
| no_mock | 36,600 | 92.9% |
| has_mock | 2,777 | 7.1% |

**framework distribution**

| Value | Count | % |
|---|---|---|
| sinon | 1,993 | 33.3% |
| unittest_mock | 1,844 | 30.8% |
| jest | 1,634 | 27.3% |
| pytest_monkeypatch | 271 | 4.5% |
| mockito | 137 | 2.3% |
| pytest_mock | 114 | 1.9% |

**category distribution**

| Value | Count | % |
|---|---|---|
| mock | 3,369 | 56.2% |
| stub | 1,536 | 25.6% |
| spy | 858 | 14.3% |
| fake | 156 | 2.6% |
| dummy | 74 | 1.2% |

**Mock prevalence by language**

| Language | Fixtures | With >=1 mock | Rate |
|---|---|---|---|
| java | 3,492 | 76 | 2.2% |
| javascript | 5,184 | 437 | 8.4% |
| python | 16,745 | 1,023 | 6.1% |
| typescript | 13,956 | 1,241 | 8.9% |

**Framework distribution by language**

| Language | Framework | Count |
|---|---|---|
| java | mockito | 137 |
| javascript | jest | 965 |
| javascript | sinon | 259 |
| python | unittest_mock | 1,843 |
| python | pytest_monkeypatch | 271 |
| python | pytest_mock | 114 |
| typescript | sinon | 1,734 |
| typescript | jest | 669 |
| typescript | unittest_mock | 1 |

**Cross-language fixture leakage** (a fixture's own detected language differs from its repo's tagged language -- see [Limitations § Cross-Language Fixture Leakage](../docs/reference/limitations.md#cross-language-fixture-leakage))

3,900/39,377 fixtures (9.90%) leaked.

| Repo language | Total fixtures | Leaked | Leaked % | Leaked into |
|---|---|---|---|---|
| java | 3,233 | 20 | 0.62% | python=16, javascript=4 |
| javascript | 2,528 | 297 | 11.75% | typescript=125, python=119, java=53 |
| python | 17,111 | 615 | 3.59% | typescript=294, java=188, javascript=133 |
| typescript | 16,505 | 2,968 | 17.98% | javascript=2,816, python=114, java=38 |

## A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)

**Continuous metrics (Mann-Whitney U, two-sided)** -- num_mocks/ num_interactions_configured have no per-language family (not one of the metrics the paper review named), so both render Overall-only, shown at both the fixture-level (every fixture/mock as an observation) and repo-level (one mean value per repo) basis. Effect size is Cliff's delta (thresholds: negligible <0.147, small <0.33, medium <0.474, else large).

### num_mocks

**Fixture-level**

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 39088 | 39377 | U=757281406.5 | -0.016 | negligible | <.001 | -- |

**Repo-level** (one mean value per repo)

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 1044 | 851 | U=368836.5 | -0.170 | small | <.001 | -- |

### num_interactions_configured

**Fixture-level**

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 14405 | 5993 | U=38498785.5 | -0.108 | negligible | <.001 | -- |

**Repo-level** (one mean value per repo)

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 466 | 267 | U=60027.5 | -0.035 | negligible | 0.345 | -- |

**has_mock (chi-square)** -- an "Overall" row (single pooled test, not BH-corrected) plus one BH-corrected row per language (one family, 4 languages -- see render_comparison_table()'s docstring in _shared.py). Effect size is Cramer's V (thresholds: negligible <0.1, small <0.3, medium <0.5, else large). framework/category are shown further below instead -- see this module's docstring for why they don't get a chi-square table.

### has_mock

| Language | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| Overall | 1044 | 851 | chi2=69.8 (df=1) | 0.030 | negligible | <.001 | -- |
| java | 84 | 40 | chi2=111.4 (df=1) | 0.154 | small | <.001 | <.001 |
| javascript | 88 | 144 | chi2=59.8 (df=1) | 0.088 | negligible | <.001 | <.001 |
| python | 490 | 558 | chi2=1163.4 (df=1) | 0.202 | small | <.001 | <.001 |
| typescript | 502 | 177 | chi2=395.2 (df=1) | 0.103 | small | <.001 | <.001 |

> **`has_mock`'s result above is not used in the paper.** It's a pooled/per-language fixture-level chi-square, which treats fixtures clustered within a repo as independent observations and inflates both chi2 and Cramer's V (see [Limitations § Categorical Pseudo-Replication](../docs/reference/limitations.md#categorical-pseudo-replication)). The paper reports the repo-level `has_mock` proportion test in "Repo-level aggregates" below instead.

**Mocking framework distribution (descriptive, per language)** -- no statistical test or effect size: framework names are language-specific by construction (`unittest.mock` is Python-only, Sinon is JS-only, Mockito is Java-only), so a pooled cross-language comparison would just reflect each dataset's language mix (Dataset A is TypeScript-heavy, Dataset C skews Python/JavaScript), not an authorship-era effect. Top 3 frameworks per language per dataset (union of both sides' top 3), as a percentage of that language's own mock usages.

| Language | Framework | Dataset A (agent-authored) (%) | Dataset C (human-authored, pre-LLM) (%) |
|---|---|---|---|
| java | mockito | 100.0% | 100.0% |
| javascript | vitest | 46.6% | 0.0% |
| javascript | jest | 33.7% | 78.8% |
| javascript | sinon | 19.6% | 21.2% |
| python | unittest_mock | 57.4% | 82.7% |
| python | pytest_monkeypatch | 41.3% | 12.2% |
| python | pytest_mock | 1.3% | 5.1% |
| typescript | vitest | 67.9% | 0.0% |
| typescript | jest | 31.9% | 27.8% |
| typescript | sinon | 0.1% | 72.1% |
| typescript | unittest_mock | 0.0% | 0.0% |

**Test-double category distribution, per language (Mann-Whitney U on per-repo category proportions, two-sided)** -- category naming conventions also vary systematically by language/ecosystem (Sinon's explicit `.spy()`/`.stub()` API vs Python's monolithic `Mock`/`MagicMock`), so this is computed once per language instead of pooled, reusing the same repo-level-proportion approach used elsewhere in this script. Each language's own category family (up to 5: dummy/fake/mock/spy/stub) is BH-FDR corrected independently of every other language's. Positive δ means the comparison dataset tends to have a larger proportion than A.

| Language | Category | Dataset A (agent-authored) (median %) | Dataset C (human-authored, pre-LLM) (median %) | δ (A vs C) | p (BH) |
|---|---|---|---|---|---|
| java | dummy | 0.0% | 0.0% | -0.120 | 0.352 |
| java | fake | 0.0% | 0.0% | 0.062 | 0.668 |
| java | mock | 100.0% | 100.0% | -0.074 | 0.668 |
| java | spy | 0.0% | 0.0% | 0.154 | 0.352 |
| java | stub | 0.0% | 0.0% | -0.160 | 0.352 |
| javascript | fake | 0.0% | 0.0% | 0.005 | 0.960 |
| javascript | mock | 0.0% | 66.7% | 0.332 | 0.043 |
| javascript | spy | 0.0% | 0.0% | 0.069 | 0.813 |
| javascript | stub | 19.1% | 0.0% | -0.379 | 0.014 |
| python | dummy | 0.0% | 0.0% | 0.041 | 0.096 |
| python | fake | 0.0% | 0.0% | -0.188 | <.001 |
| python | mock | 100.0% | 100.0% | 0.185 | <.001 |
| python | spy | 0.0% | 0.0% | -0.021 | 0.096 |
| python | stub | 0.0% | 0.0% | -0.162 | <.001 |
| typescript | dummy | 0.0% | 0.0% | 0.031 | 0.038 |
| typescript | fake | 0.0% | 0.0% | -0.143 | 0.006 |
| typescript | mock | 86.1% | 0.0% | -0.221 | 0.012 |
| typescript | spy | 0.0% | 9.9% | 0.288 | <.001 |
| typescript | stub | 0.0% | 0.0% | -0.043 | 0.519 |

**Aggregate category distribution (descriptive only -- not used for inference)** -- pooled across all languages and repos, shown for reference only; the per-language table above is the real A-vs-C comparison.

| Category | Dataset A (agent-authored) (%) | Dataset C (human-authored, pre-LLM) (%) |
|---|---|---|
| dummy | 0.9% | 1.2% |
| fake | 8.2% | 2.6% |
| mock | 76.1% | 56.2% |
| spy | 4.2% | 14.3% |
| stub | 10.6% | 25.6% |

## Repo-level aggregates

has_mock re-tested with one *proportion-per-repo* value instead of pooled/per-language fixture-level chi-square, so each repo counts once regardless of how many fixtures it contributed. (num_mocks/num_interactions_configured already have their own repo-level Overall row above, in the main comparison section; framework/category are handled entirely in the main comparison section too -- see this module's docstring.)

### A vs C: Dataset A (agent-authored) vs Dataset C (human-authored, pre-LLM)

**has_mock, repo-level (Mann-Whitney U on per-repo category proportions, two-sided)** -- the chi-square table above treats every fixture as an independent observation, but fixtures cluster within repos (shared framework choice, project convention), which inflates chi2 and partially corrupts Cramer's V. This instead compares, per repo, what fraction of its fixtures have >=1 mock -- so each repo counts once regardless of how many fixtures it contributed. **This is the `has_mock` result reported in the paper.** (framework's per-language descriptive table and category's per-language repo-level proportion table are both in the main comparison section above instead -- neither gets a pooled-across-languages view here, see this module's docstring for why.)

| Category | A median | A mean | C median | C mean | n_A | n_C | Statistic | Effect size value | Magnitude | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|---|---|---|
| has_mock | 0.0% | 12.9% | 0.0% | 6.4% | 1044 | 851 | U=371462.0 | -0.164 | small | <.001 | <.001 |
| no_mock | 100.0% | 87.1% | 100.0% | 93.6% | 1044 | 851 | U=516982.0 | 0.164 | small | <.001 | <.001 |
