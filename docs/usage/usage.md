# Analyzing the Between-Group Dataset

The FixtureDB between-group dataset contains fixtures from agent-enabled repositories, with each fixture labeled as agent-authored or human-authored. This guide shows how to query and analyze the between-group.db database.

---

## Study Design Overview

The between-group study compares agent and human fixtures within repositories:
- **Repository basis:** Agent-enabled repositories (containing agent config files)
- **Temporal window:** 2023-06-01 onwards for both agent and human fixtures
- **Agent identification:** Tier 1 only (co-authored-by trailers, author signatures)
- **Control variables:** Language, domain, star tier, repository age (computed at temporal snapshot)
- **Analysis:** Within-repository paired comparisons

This design enables direct observation of agent adoption effects within codebases.

---

## Analysis with SQLite

### Example 1: Fixture Complexity by Corpus

Compare average fixture complexity between human and agent-authored fixtures:

```python
import sqlite3
import pandas as pd

conn = sqlite3.connect("between-group.db")

complexity_by_corpus = pd.read_sql("""
    SELECT 
        f.commit_kind as corpus,
        COUNT(DISTINCT f.id) as fixture_count,
        ROUND(AVG(f.loc), 2) as avg_loc,
        ROUND(AVG(f.cyclomatic_complexity), 2) as avg_complexity,
        ROUND(AVG(f.max_nesting_depth), 2) as avg_nesting,
        ROUND(AVG(f.num_parameters), 2) as avg_parameters
    FROM fixtures f
    GROUP BY f.commit_kind
""", conn)

print(complexity_by_corpus)
```

### Example 2: Agent Type Breakdown

Analyze which agents produce fixtures and their characteristics:

```python
import sqlite3
import pandas as pd

conn = sqlite3.connect("between-group.db")

agent_comparison = pd.read_sql("""
    SELECT 
        COALESCE(f.agent_type, 'human') as author,
        COUNT(DISTINCT f.commit_sha) as commits,
        COUNT(DISTINCT f.id) as fixtures,
        ROUND(AVG(f.loc), 2) as avg_loc,
        ROUND(AVG(f.cyclomatic_complexity), 2) as avg_complexity,
        ROUND(SUM(CASE WHEN f.has_teardown_pair = 1 THEN 1 ELSE 0 END) * 100.0 
              / COUNT(DISTINCT f.id), 1) as teardown_adoption_pct
    FROM fixtures f
    GROUP BY COALESCE(f.agent_type, 'human')
    ORDER BY commits DESC
""", conn)

print(agent_comparison)
```

### Example 3: Framework Adoption Across Corpora

Identify which testing frameworks are used by agent vs human fixtures:

```python
import sqlite3
import pandas as pd

conn = sqlite3.connect("between-group.db")

framework_adoption = pd.read_sql("""
    SELECT 
        f.framework,
        f.commit_kind,
        COUNT(*) as fixture_count,
        ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY f.commit_kind), 1) as pct_within_corpus
    FROM fixtures f
    WHERE f.framework IS NOT NULL
    GROUP BY f.framework, f.commit_kind
    ORDER BY f.commit_kind, fixture_count DESC
""", conn)

print(framework_adoption)
```

### Example 4: Statistical Testing (Mann-Whitney U)

Compare fixture complexity distributions using Mann-Whitney U test:

```python
import sqlite3
import numpy as np
from scipy.stats import mannwhitneyu

conn = sqlite3.connect("between-group.db")

# Get complexity values by corpus
human = [row[0] for row in conn.execute(
    "SELECT cyclomatic_complexity FROM fixtures WHERE commit_kind = 'human' AND cyclomatic_complexity IS NOT NULL"
).fetchall()]

agent = [row[0] for row in conn.execute(
    "SELECT cyclomatic_complexity FROM fixtures WHERE commit_kind = 'agent' AND cyclomatic_complexity IS NOT NULL"
).fetchall()]

# Mann-Whitney U test
statistic, p_value = mannwhitneyu(human, agent, alternative='two-sided')
print(f"Mann-Whitney U test for cyclomatic complexity:")
print(f"  Human mean: {np.mean(human):.2f}, Agent mean: {np.mean(agent):.2f}")
print(f"  U statistic: {statistic:.2f}, p-value: {p_value:.4f}")
print(f"  Significant (p<0.05): {p_value < 0.05}")
```

### Example 5: Chi-Square Test for Categorical Variables

Test if domain distribution is balanced across corpora:

```python
import sqlite3
from scipy.stats import chi2_contingency

conn = sqlite3.connect("between-group.db")

# Domain distribution by corpus
domain_dist = pd.read_sql("""
    SELECT 
        r.domain,
        f.commit_kind,
        COUNT(DISTINCT f.id) as count
    FROM fixtures f
    JOIN repositories r ON f.repo_id = r.id
    WHERE r.domain IS NOT NULL
    GROUP BY r.domain, f.commit_kind
""", conn)

# Pivot to contingency table
contingency = pd.pivot_table(domain_dist, values='count', index='domain', columns='commit_kind', fill_value=0)

# Chi-square test
chi2, p_value, dof, expected = chi2_contingency(contingency.values)
print(f"Chi-square test for domain distribution:")
print(f"  Chi-square: {chi2:.2f}, p-value: {p_value:.4f}, df: {dof}")
print(f"  Balanced (p>=0.05): {p_value >= 0.05}")
```

### Example 6: Control Variable Balance Checking

Verify that control variables are balanced across corpora:

```python
import sqlite3
import pandas as pd

conn = sqlite3.connect("between-group.db")

# Get control variables by corpus
control_vars = pd.read_sql("""
    SELECT 
        f.commit_kind as corpus,
        r.language,
        r.domain,
        r.star_tier,
        ROUND(r.repo_age_years, 2) as repo_age_years
    FROM fixtures f
    JOIN repositories r ON f.repo_id = r.id
""", conn)

# Summary by corpus
summary = control_vars.groupby('corpus').agg({
    'language': lambda x: x.value_counts().index[0],  # Most common
    'domain': lambda x: x.value_counts().index[0],
    'star_tier': lambda x: x.value_counts().index[0],
    'repo_age_years': ['mean', 'median', 'std']
})

print("Control variable summary:")
print(summary)
```

### Example 7: Regression with Control Variables

Use a regression model to account for control variables when comparing fixture complexity:

```python
import sqlite3
import pandas as pd
from sklearn.preprocessing import LabelEncoder
from sklearn.linear_model import LinearRegression

conn = sqlite3.connect("between-group.db")

# Get data with control variables
df = pd.read_sql("""
    SELECT 
        f.loc,
        f.cyclomatic_complexity,
        f.commit_kind,
        r.language,
        r.domain,
        r.star_tier,
        r.repo_age_years
    FROM fixtures f
    JOIN repositories r ON f.repo_id = r.id
    WHERE f.cyclomatic_complexity IS NOT NULL
""", conn)

# Encode categorical variables
le_corpus = LabelEncoder()
le_lang = LabelEncoder()
le_domain = LabelEncoder()
le_tier = LabelEncoder()

df['corpus'] = le_corpus.fit_transform(df['commit_kind'])
df['language'] = le_lang.fit_transform(df['language'].fillna('unknown'))
df['domain'] = le_domain.fit_transform(df['domain'].fillna('other'))
df['star_tier'] = le_tier.fit_transform(df['star_tier'].fillna('extended'))

# Fit regression model
X = df[['corpus', 'language', 'domain', 'star_tier', 'repo_age_years']]
y = df['cyclomatic_complexity']

model = LinearRegression()
model.fit(X, y)

print(f"Regression model R²: {model.score(X, y):.4f}")
print(f"Corpus coefficient (agent=1): {model.coef_[0]:.4f}")
print(f"  Interpretation: Agent fixtures have {model.coef_[0]:.4f} {'higher' if model.coef_[0] > 0 else 'lower'} complexity")
```


### Example 4: Compare Fixture Distributions Across Corpora

Compare fixture characteristics between human and agent corpora:

```python
import sqlite3
import pandas as pd

conn = sqlite3.connect("data/between-group.db")

# Fixture statistics by commit_kind
distribution = pd.read_sql("""
    SELECT 
        f.commit_kind,
        COUNT(f.id) as total_fixtures,
        ROUND(AVG(f.cyclomatic_complexity), 2) as avg_complexity,
        ROUND(AVG(f.loc), 1) as avg_loc,
        COUNT(DISTINCT CASE WHEN f.mock_usage > 0 THEN f.id END) as fixtures_with_mocks,
        ROUND(100.0 * COUNT(DISTINCT CASE WHEN f.mock_usage > 0 THEN f.id END) 
              / COUNT(f.id), 1) as mock_adoption_pct
    FROM fixtures f
    GROUP BY f.commit_kind
""", conn)

print("Fixture Distribution Comparison:")
print(distribution)
```

### Example 5: Control Variable Balance Testing

Verify balance of control variables across corpora (required for between-group validity):

```python
import sqlite3
import pandas as pd
from scipy.stats import chi2_contingency, mannwhitneyu

conn = sqlite3.connect("data/between-group.db")

# Language distribution
language_dist = pd.read_sql("""
    SELECT 
        r.language,
        f.commit_kind,
        COUNT(f.id) as fixture_count
    FROM fixtures f
    JOIN test_files tf ON f.test_file_id = tf.id
    JOIN repositories r ON tf.repo_id = r.id
    GROUP BY r.language, f.commit_kind
""", conn)

print("Language Balance Check:")
print(language_dist)

# Domain distribution 
domain_dist = pd.read_sql("""
    SELECT 
        r.domain,
        f.commit_kind,
        COUNT(f.id) as fixture_count
    FROM fixtures f
    JOIN test_files tf ON f.test_file_id = tf.id
    JOIN repositories r ON tf.repo_id = r.id
    WHERE r.domain IS NOT NULL
    GROUP BY r.domain, f.commit_kind
    ORDER BY r.domain
""", conn)

print("\nDomain Balance Check:")
print(domain_dist)
```

### Example 6: Agent Type Breakdown

Analyze fixture characteristics by agent type (Tier 1 detection only):

```python
import sqlite3
import pandas as pd

conn = sqlite3.connect("data/between-group.db")

agent_breakdown = pd.read_sql("""
    SELECT 
        f.agent_type,
        COUNT(f.id) as total_fixtures,
        ROUND(AVG(f.cyclomatic_complexity), 2) as avg_complexity,
        ROUND(AVG(f.loc), 1) as avg_loc,
        COUNT(DISTINCT tf.repo_id) as unique_repos
    FROM fixtures f
    LEFT JOIN test_files tf ON f.test_file_id = tf.id
    WHERE f.commit_kind = 'agent'
    GROUP BY f.agent_type
    ORDER BY total_fixtures DESC
""", conn)

print("Fixtures by Agent Type:")
print(agent_breakdown)
```

---

## Between-Group Statistical Analysis

### Compare Continuous Metrics (Mann-Whitney U)

For unpaired continuous metrics (complexity, LOC), use Mann-Whitney U test:

```python
import sqlite3
import pandas as pd
from scipy.stats import mannwhitneyu

conn = sqlite3.connect("data/between-group.db")

# Load complexity by corpus
complexity = pd.read_sql("""
    SELECT 
        f.commit_kind,
        f.cyclomatic_complexity
    FROM fixtures f
    WHERE f.cyclomatic_complexity IS NOT NULL
""", conn)

human = complexity[complexity['commit_kind'] == 'human']['cyclomatic_complexity'].values
agent = complexity[complexity['commit_kind'] == 'agent']['cyclomatic_complexity'].values

# Mann-Whitney U test (unpaired)
stat, p_value = mannwhitneyu(human, agent)
print(f"Mann-Whitney U test (complexity): statistic={stat:.2f}, p_value={p_value:.6f}")
print(f"Interpretation: {'Significant difference' if p_value < 0.05 else 'No significant difference'} (p={'<' if p_value < 0.05 else '≥'}0.05)")
```

### Compare Categorical Variables (Chi-Square)

For categorical control variables (language, domain, star_tier), use chi-square test:

```python
import sqlite3
import pandas as pd
from scipy.stats import chi2_contingency

conn = sqlite3.connect("data/between-group.db")

# Language distribution table
lang_dist = pd.read_sql("""
    SELECT 
        r.language,
        f.commit_kind,
        COUNT(f.id) as count
    FROM fixtures f
    JOIN test_files tf ON f.test_file_id = tf.id
    JOIN repositories r ON tf.repo_id = r.id
    GROUP BY r.language, f.commit_kind
""", conn)

# Pivot to contingency table
contingency = lang_dist.pivot(index='language', columns='commit_kind', values='count').fillna(0)

# Chi-square test
chi2, p_value, dof, expected = chi2_contingency(contingency)
print(f"Chi-square test (language): chi2={chi2:.2f}, p_value={p_value:.6f}")
print(f"Interpretation: {'Balance problem' if p_value < 0.05 else 'Balanced'} (p={'<' if p_value < 0.05 else '≥'}0.05)")
print(f"\nContingency table:\n{contingency}")
```

---

## Query Cheatsheet

### Common Between-Group Queries

```sql
-- Compare fixture counts
SELECT commit_kind, COUNT(*) as fixture_count 
FROM fixtures 
GROUP BY commit_kind;

-- Agent type breakdown
SELECT agent_type, COUNT(*) as count 
FROM fixtures 
WHERE commit_kind = 'agent'
GROUP BY agent_type;

-- Language distribution check
SELECT r.language, f.commit_kind, COUNT(*) as count
FROM fixtures f
JOIN test_files tf ON f.test_file_id = tf.id
JOIN repositories r ON tf.repo_id = r.id
GROUP BY r.language, f.commit_kind
ORDER BY r.language, f.commit_kind;

-- Control variable comparison (star tier)
SELECT r.star_tier, f.commit_kind, COUNT(*) as count
FROM fixtures f
JOIN test_files tf ON f.test_file_id = tf.id
JOIN repositories r ON tf.repo_id = r.id
GROUP BY r.star_tier, f.commit_kind;

-- Fixture complexity by corpus
SELECT f.commit_kind, COUNT(*), AVG(cyclomatic_complexity), STDDEV(cyclomatic_complexity)
FROM fixtures f
GROUP BY f.commit_kind;
```

### Common Pandas Operations

```python
# Load all data
df = pd.read_sql("""
    SELECT f.*, r.language, r.domain, r.star_tier
    FROM fixtures f
    JOIN test_files tf ON f.test_file_id = tf.id
    JOIN repositories r ON tf.repo_id = r.id
""", conn)

# Split by corpus
human_df = df[df['commit_kind'] == 'human']
agent_df = df[df['commit_kind'] == 'agent']

# Compare means
print(f"Human avg complexity: {human_df['cyclomatic_complexity'].mean():.2f}")
print(f"Agent avg complexity: {agent_df['cyclomatic_complexity'].mean():.2f}")

# Group by agent type
agent_df[agent_df['agent_type'].notna()].groupby('agent_type')['cyclomatic_complexity'].describe()
```

---

## For Papers & Publications

When writing papers using the between-group dataset, please:

1. **Clarify the design**: Explain the between-group design with temporal separation (pre-2021 vs 2023+)
2. **Document control variable balance**: Reference the balance test results from Stage 3
3. **Note agent detection method**: Specify Tier 1 (co-authored-by trailers) detection only
4. **Mention agent types detected**: Claude, Copilot, Cursor, Aider, or other (Tier 1)
5. **Use unpaired statistical tests**: Mann-Whitney U for continuous, chi-square for categorical
6. **Discuss temporal confounding**: Acknowledge framework/practice changes between 2021 and 2023

Example methodology section:
```
"We analyzed test fixtures using a between-group comparison design, 
comparing pre-2021 human-authored fixtures (N=3,500) with 2023+ agent-assisted 
fixtures (N=4,500) across Python, Java, JavaScript, and TypeScript. 
Agent involvement was identified using Tier 1 detection (co-authored-by git trailers) 
to ensure high precision. Control variables (language, domain, star tier, repository age) 
were balanced across corpora using chi-square tests (categorical) and Mann-Whitney U tests 
(continuous). All statistical comparisons used unpaired tests appropriate for the 
between-group design."
```

---

## See Also

- [Database Schema](../architecture/database-schema.md) — Schema reference and control variables
- [Agent Detection](../architecture/agent-detection.md) — Tier 1 vs Tier 2/3 detection methods
- [Reproducing Results](./reproducing.md) — How to reproduce the between-group collection
