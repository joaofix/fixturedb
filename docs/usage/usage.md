# Analyzing the FixtureDB Datasets

FixtureDB collects three datasets — Dataset A (agent-authored fixtures, 2025+),
Dataset B (human-authored fixtures, within-repo control, same repos as A), and
Dataset C (human-authored fixtures, cross-repo baseline, independent pre-2021 repo
pool) — each in its own SQLite database (`db/a.db`, `db/b.db`, `db/c.db`; see
[Database Schema](../architecture/database-schema.md)). This guide shows how to
query one dataset and how to compare across two.

---

## Study Design Overview

- **Dataset A vs Dataset B ("within-repo"):** same agent-enabled repositories,
  agent-authored vs human-authored fixtures, same 2025+ temporal window.
- **Dataset A vs Dataset C ("cross-repo"):** Dataset C is an independent, non-agent
  repo pool from a pre-2021 window — a different baseline with different residual
  risk (see [Limitations § Differential False-Negative Risk](../reference/limitations.md#differential-false-negative-risk-dataset-b-vs-dataset-c)).
- **Agent identification:** Tier 1 only (co-authored-by trailers, author signatures).
- **Control variables:** language, domain, repository age — computed at
  each dataset's own temporal snapshot.
- **Statistical approach:** unpaired tests (Mann-Whitney U for continuous variables,
  chi-square for categorical), since A/B/C are separate databases rather than paired
  observations within one table.

Treat A-vs-B and A-vs-C as testing related but distinct questions — don't pool all
three into one undifferentiated "agent vs. human" number.

---

## Querying a single dataset

### Fixture complexity summary

```python
import sqlite3
import pandas as pd

conn = sqlite3.connect("db/a.db")

summary = pd.read_sql("""
    SELECT
        COUNT(DISTINCT f.id) as fixture_count,
        ROUND(AVG(f.loc), 2) as avg_loc,
        ROUND(AVG(f.cyclomatic_complexity), 2) as avg_complexity,
        ROUND(AVG(f.max_nesting_depth), 2) as avg_nesting,
        ROUND(AVG(f.num_parameters), 2) as avg_parameters
    FROM fixtures f
""", conn)

print(summary)
```

### Agent type breakdown (Dataset A only)

```python
import sqlite3
import pandas as pd

conn = sqlite3.connect("db/a.db")

agent_breakdown = pd.read_sql("""
    SELECT
        f.agent_type,
        COUNT(DISTINCT f.commit_sha) as commits,
        COUNT(DISTINCT f.id) as fixtures,
        ROUND(AVG(f.loc), 2) as avg_loc,
        ROUND(SUM(CASE WHEN f.has_teardown_pair = 1 THEN 1 ELSE 0 END) * 100.0
              / COUNT(DISTINCT f.id), 1) as teardown_adoption_pct
    FROM fixtures f
    WHERE f.agent_type IS NOT NULL
    GROUP BY f.agent_type
    ORDER BY commits DESC
""", conn)

print(agent_breakdown)
```

### Framework adoption within a dataset

```python
import sqlite3
import pandas as pd

conn = sqlite3.connect("db/a.db")

framework_adoption = pd.read_sql("""
    SELECT
        f.framework,
        COUNT(*) as fixture_count,
        ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) as pct
    FROM fixtures f
    WHERE f.framework IS NOT NULL
    GROUP BY f.framework
    ORDER BY fixture_count DESC
""", conn)

print(framework_adoption)
```

---

## Comparing two datasets

Each dataset is a separate database file, so a comparison loads both and
concatenates in pandas — see
[Database Schema § Cross-dataset query pattern](../architecture/database-schema.md#cross-dataset-compare-a-vs-b-same-repos-agent-vs-human)
for the full pattern. The helper below is reused by every example in this section:

```python
import sqlite3
import pandas as pd

def load_fixtures(dataset: str) -> pd.DataFrame:
    """dataset: 'a', 'b', or 'c'."""
    conn = sqlite3.connect(f"db/{dataset}.db")
    df = pd.read_sql("""
        SELECT f.*, r.language, r.domain, r.repo_age_years
        FROM fixtures f
        JOIN repositories r ON f.repo_id = r.id
    """, conn)
    df["dataset"] = dataset
    return df
```

### Mann-Whitney U (continuous metrics)

```python
from scipy.stats import mannwhitneyu

combined = pd.concat([load_fixtures("a"), load_fixtures("b")], ignore_index=True)

a_complexity = combined[combined["dataset"] == "a"]["cyclomatic_complexity"].dropna()
b_complexity = combined[combined["dataset"] == "b"]["cyclomatic_complexity"].dropna()

stat, p_value = mannwhitneyu(a_complexity, b_complexity, alternative="two-sided")
print(f"A mean: {a_complexity.mean():.2f}, B mean: {b_complexity.mean():.2f}")
print(f"U statistic: {stat:.2f}, p-value: {p_value:.4f}")
print(f"Significant (p<0.05): {p_value < 0.05}")
```

### Chi-square (categorical control variables)

```python
from scipy.stats import chi2_contingency

combined = pd.concat([load_fixtures("a"), load_fixtures("b")], ignore_index=True)

domain_dist = combined[combined["domain"].notna()].groupby(
    ["domain", "dataset"]
).size().reset_index(name="count")

contingency = domain_dist.pivot(index="domain", columns="dataset", values="count").fillna(0)
chi2, p_value, dof, expected = chi2_contingency(contingency.values)
print(f"Chi-square: {chi2:.2f}, p-value: {p_value:.4f}, df: {dof}")
print(f"Balanced (p>=0.05): {p_value >= 0.05}")
```

### Control variable balance check

```python
combined = pd.concat([load_fixtures("a"), load_fixtures("b")], ignore_index=True)

balance = combined.groupby("dataset").agg(
    most_common_language=("language", lambda x: x.value_counts().index[0]),
    most_common_domain=("domain", lambda x: x.value_counts().index[0]),
    mean_repo_age_years=("repo_age_years", "mean"),
    median_repo_age_years=("repo_age_years", "median"),
)
print(balance)
```

### Regression with control variables

```python
from sklearn.preprocessing import LabelEncoder
from sklearn.linear_model import LinearRegression

combined = pd.concat([load_fixtures("a"), load_fixtures("b")], ignore_index=True)
df = combined[combined["cyclomatic_complexity"].notna()].copy()

for col, default in [("language", "unknown"), ("domain", "other")]:
    df[col] = df[col].fillna(default)
    df[col] = LabelEncoder().fit_transform(df[col])
df["dataset_code"] = LabelEncoder().fit_transform(df["dataset"])  # a=0, b=1

X = df[["dataset_code", "language", "domain", "repo_age_years"]]
y = df["cyclomatic_complexity"]

model = LinearRegression()
model.fit(X, y)

print(f"Regression R^2: {model.score(X, y):.4f}")
print(f"Dataset coefficient: {model.coef_[0]:.4f}")
```

---

## Query cheatsheet

```sql
-- Fixture count for one dataset
SELECT COUNT(*) as fixture_count FROM fixtures;

-- Agent type breakdown (Dataset A only)
SELECT agent_type, COUNT(*) as count
FROM fixtures
WHERE agent_type IS NOT NULL
GROUP BY agent_type;

-- Language distribution within a dataset
SELECT r.language, COUNT(*) as count
FROM fixtures f
JOIN repositories r ON f.repo_id = r.id
GROUP BY r.language
ORDER BY count DESC;

-- Fixture complexity summary
SELECT COUNT(*), AVG(cyclomatic_complexity), MIN(cyclomatic_complexity), MAX(cyclomatic_complexity)
FROM fixtures;
```

Run the same query against `db/a.db`, `db/b.db`, or `db/c.db` and combine the
results in pandas (see [Comparing two datasets](#comparing-two-datasets)) rather
than trying to express a cross-dataset `GROUP BY` in SQL — there is no single
database that contains all three.

---

## For Papers & Publications

When writing papers using this dataset:

1. **State which comparison you ran**: A-vs-B (within-repo) and A-vs-C (cross-repo)
   test related but distinct questions — say which one, don't conflate them.
2. **Document control variable balance**: report the balance-test results (chi-square
   for categorical, Mann-Whitney U for continuous) for the specific pair compared.
3. **Note agent detection method**: Tier 1 (co-authored-by trailers, author
   signatures) only — see [Agent Detection](../architecture/agent-detection.md).
4. **Report per-dataset fixture counts**: from `datasets/{dataset}/summary.yaml`
   (`python -m collection summarize --dataset {a,b,c}`), not estimated.
5. **Acknowledge temporal confounding for A-vs-C**: Dataset C's window
   (pre-2021) predates Dataset A/B's (2025+); framework/practice changes across that
   gap are a threat to validity — see [Limitations](../reference/limitations.md).

---

## See Also

- [Database Schema](../architecture/database-schema.md) — schema reference, per-dataset differences, query pattern this guide builds on
- [Agent Detection](../architecture/agent-detection.md) — Tier 1 vs Tier 2/3 detection methods
- [Limitations](../reference/limitations.md) — threats to validity, including the A-vs-B/A-vs-C distinction
- [Reproducing Results](reproducing.md) — how to reproduce collection for a given dataset
