# Analyzing the FixtureDB Split Datasets

The FixtureDB Split project provides two separate datasets optimized for human vs AGENT research:

- **fixturedb-human.db** — Pre-2021 fixtures (baseline human testing patterns)
- **fixturedb-agent.db** — 2021+ fixtures with agent attribution (AGENT-era patterns)

This guide shows how to query and analyze both datasets.

---

## Two Main Analysis Approaches

### **Approach 1: SQLite Database Queries**

**Best for:** Complex queries, joins, reproducibility, agent-specific analysis
**Tools:** `sqlite3` CLI, Python, R, SQL IDE (DBeaver, SQLiteStudio)
**Advantages:**
- Powerful joins across fixtures, test files, repositories
- Filter by multiple criteria (framework, scope, complexity, agent)
- Verify extraction decisions with full source code access
- No data loss—all fields available

### **Approach 2: CSV Exports**

**Best for:** Quick analysis, Excel workflows, non-SQL users, papers
**Tools:** Excel, Google Sheets, Python (pandas), R
**Advantages:**
- Works in any spreadsheet application
- No SQL knowledge required
- Cross-language data with filtering
- Quantitative metrics pre-computed

See [CSV User Guide](../data/csv-user-guide.md) for details.

---

## Approach 1: SQLite Queries

### Example 1: Complexity Comparison (Human vs AGENT)

```python
import sqlite3
import pandas as pd

# Load both datasets
human_conn = sqlite3.connect("fixturedb-human.db")
llm_conn = sqlite3.connect("fixturedb-agent.db")

# Compare average complexity
human_stats = pd.read_sql("""
    SELECT 
        COUNT(*) as fixture_count,
        ROUND(AVG(loc), 2) as avg_loc,
        ROUND(AVG(cyclomatic_complexity), 2) as avg_complexity,
        ROUND(MAX(cyclomatic_complexity), 2) as max_complexity
    FROM fixtures
""", human_conn)

llm_stats = pd.read_sql("""
    SELECT 
        COUNT(*) as fixture_count,
        ROUND(AVG(loc), 2) as avg_loc,
        ROUND(AVG(cyclomatic_complexity), 2) as avg_complexity,
        ROUND(MAX(cyclomatic_complexity), 2) as max_complexity
    FROM fixtures
""", llm_conn)

print("Human Fixtures (Pre-2021):")
print(human_stats)
print("\nLLM Fixtures (2021+):")
print(llm_stats)

# Visualization
import matplotlib.pyplot as plt
fig, axes = plt.subplots(1, 2, figsize=(12, 5))
axes[0].bar(['Human', 'AGENT'], [human_stats['avg_loc'].iloc[0], llm_stats['avg_loc'].iloc[0]])
axes[0].set_title('Average Lines of Code')
axes[1].bar(['Human', 'AGENT'], [human_stats['avg_complexity'].iloc[0], llm_stats['avg_complexity'].iloc[0]])
axes[1].set_title('Average Cyclomatic Complexity')
plt.tight_layout()
plt.show()
```

### Example 2: Agent-Specific Analysis (AGENT Only)

```python
import sqlite3
import pandas as pd

llm_conn = sqlite3.connect("fixturedb-agent.db")

# Compare complexity by agent type
agent_comparison = pd.read_sql("""
    SELECT 
        agent_type,
        COUNT(*) as fixture_count,
        ROUND(AVG(loc), 2) as avg_loc,
        ROUND(AVG(cyclomatic_complexity), 2) as avg_complexity,
        ROUND(AVG(num_parameters), 2) as avg_parameters,
        ROUND(SUM(CASE WHEN has_teardown_pair = 1 THEN 1 ELSE 0 END) * 100.0 
              / COUNT(*), 1) as teardown_adoption_pct
    FROM fixtures
    WHERE agent_type IS NOT NULL
    GROUP BY agent_type
    ORDER BY fixture_count DESC
""", llm_conn)

print("Fixture metrics by AI agent:")
print(agent_comparison)

# Which agent produces simpler fixtures?
simpler = agent_comparison[agent_comparison['avg_complexity'] == agent_comparison['avg_complexity'].min()]
print(f"\nAgent with simplest fixtures: {simpler['agent_type'].iloc[0]}")
```

### Example 3: Framework Adoption by Era

```python
import sqlite3
import pandas as pd

human_conn = sqlite3.connect("fixturedb-human.db")
llm_conn = sqlite3.connect("fixturedb-agent.db")

# Framework usage in human era
human_frameworks = pd.read_sql("""
    SELECT 
        framework,
        COUNT(*) as count,
        ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM fixtures), 1) as pct
    FROM fixtures
    WHERE framework IS NOT NULL
    GROUP BY framework
    ORDER BY count DESC
""", human_conn)

# Framework usage in AGENT era
llm_frameworks = pd.read_sql("""
    SELECT 
        framework,
        COUNT(*) as count,
        ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM fixtures), 1) as pct
    FROM fixtures
    WHERE framework IS NOT NULL
    GROUP BY framework
    ORDER BY count DESC
""", llm_conn)

print("Framework usage - Pre-2021 (Human):")
print(human_frameworks)
print("\nFramework usage - 2021+ (AGENT):")
print(llm_frameworks)
```

### Example 4: Scope Distribution (Per-Test vs Per-Class)

```python
import sqlite3
import pandas as pd

conn_human = sqlite3.connect("fixturedb-human.db")
conn_llm = sqlite3.connect("fixturedb-agent.db")

# Scope patterns
scope_human = pd.read_sql("""
    SELECT scope, COUNT(*) as count
    FROM fixtures
    GROUP BY scope
    ORDER BY count DESC
""", conn_human)

scope_llm = pd.read_sql("""
    SELECT scope, COUNT(*) as count
    FROM fixtures
    GROUP BY scope
    ORDER BY count DESC
""", conn_llm)

print("Scope distribution - Human:")
print(scope_human)
print("\nScope distribution - AGENT:")
print(scope_llm)

# Insight: Do AGENT tools prefer different scopes?
```

### Example 5: Mock Framework Usage

```python
import sqlite3
import pandas as pd

human_conn = sqlite3.connect("fixturedb-human.db")
llm_conn = sqlite3.connect("fixturedb-agent.db")

# How many fixtures have external calls (indicating mocking)?
human_with_external = pd.read_sql("""
    SELECT 
        COUNT(CASE WHEN num_external_calls > 0 THEN 1 END) as fixtures_with_external_calls,
        COUNT(*) as total_fixtures,
        ROUND(100.0 * 
            COUNT(CASE WHEN num_external_calls > 0 THEN 1 END) / 
            COUNT(*), 1) as pct
    FROM fixtures
""", human_conn).iloc[0]

llm_with_external = pd.read_sql("""
    SELECT 
        COUNT(CASE WHEN num_external_calls > 0 THEN 1 END) as fixtures_with_external_calls,
        COUNT(*) as total_fixtures,
        ROUND(100.0 * 
            COUNT(CASE WHEN num_external_calls > 0 THEN 1 END) / 
            COUNT(*), 1) as pct
    FROM fixtures
""", llm_conn).iloc[0]

print(f"Human fixtures with external calls: {human_with_external['pct']}%")
print(f"AGENT fixtures with external calls: {llm_with_external['pct']}%")
```

### Example 6: Multi-Agent Comparison (Advanced)

```python
import sqlite3
import pandas as pd

llm_conn = sqlite3.connect("fixturedb-agent.db")

# Detailed agent comparison
detailed = pd.read_sql("""
    SELECT 
        agent_type,
        COUNT(*) as fixture_count,
        ROUND(AVG(loc), 2) as avg_loc,
        ROUND(MIN(loc), 2) as min_loc,
        ROUND(MAX(loc), 2) as max_loc,
        ROUND(AVG(cyclomatic_complexity), 2) as avg_cc,
        COUNT(CASE WHEN num_external_calls > 0 THEN 1 END) as with_externals,
        COUNT(CASE WHEN has_teardown_pair = 1 THEN 1 END) as with_teardown
    FROM fixtures
    WHERE agent_type IS NOT NULL
    GROUP BY agent_type
    ORDER BY fixture_count DESC
""", llm_conn)

print("\nDetailed Agent Comparison:")
print(detailed.to_string(index=False))

# Statistical analysis
for agent in detailed['agent_type']:
    agent_data = pd.read_sql(f"""
        SELECT loc, cyclomatic_complexity FROM fixtures 
        WHERE agent_type = '{agent}'
    """, llm_conn)
    
    print(f"\n{agent.upper()}:")
    print(f"  LOC distribution: {agent_data['loc'].describe()}")
```

---

## Approach 2: CSV Exports

### Quick Analysis in Pandas

```python
import pandas as pd

# Load both datasets
human = pd.read_csv("fixturedb-human/fixtures.csv")
agent = pd.read_csv("fixturedb-agent/fixtures.csv")

# Basic statistics
print(f"Human fixtures: {len(human)}")
print(f"AGENT fixtures: {len(agent)}")

# Complexity distribution
print("\nAverage LOC:")
print(f"  Human: {human['loc'].mean():.2f}")
print(f"  AGENT: {agent['loc'].mean():.2f}")

# Agent breakdown
print("\nLLM agent breakdown:")
print(agent['agent_type'].value_counts())
```

### Statistical Comparison

```python
import pandas as pd
from scipy import stats

human = pd.read_csv("fixturedb-human/fixtures.csv")
agent = pd.read_csv("fixturedb-agent/fixtures.csv")

# T-test for complexity difference
t_stat, p_value = stats.ttest_ind(
    human['cyclomatic_complexity'].dropna(),
    agent['cyclomatic_complexity'].dropna()
)

print(f"Complexity comparison (t-test):")
print(f"  t-statistic: {t_stat:.4f}")
print(f"  p-value: {p_value:.6f}")
print(f"  Significant difference: {p_value < 0.05}")
```

---

## Query Cheatsheet

### Common SQLite Queries

```sql
-- Count fixtures by language
SELECT language, COUNT(*) FROM fixtures GROUP BY language;

-- Average LOC by scope
SELECT scope, AVG(loc) FROM fixtures GROUP BY scope;

-- Find most complex fixtures
SELECT name, cyclomatic_complexity FROM fixtures 
ORDER BY cyclomatic_complexity DESC LIMIT 10;

-- Fixture types with most external calls
SELECT fixture_type, AVG(num_external_calls) as avg_external_calls
FROM fixtures GROUP BY fixture_type ORDER BY avg_external_calls DESC;

-- Repository contribution (which repos have most fixtures)
SELECT r.full_name, COUNT(f.id) as fixture_count
FROM fixtures f
JOIN repositories r ON f.repo_id = r.id
GROUP BY r.full_name ORDER BY fixture_count DESC LIMIT 10;
```

### Common Pandas Operations

```python
# Group by and aggregate
df.groupby('framework')['loc'].agg(['mean', 'std', 'count'])

# Filter
df[df['cyclomatic_complexity'] > 5]

# Cross-tabulation
pd.crosstab(df['framework'], df['scope'], margins=True)

# Correlation
df[['loc', 'cyclomatic_complexity', 'num_parameters']].corr()
```

---

## For Papers & Publications

When writing papers using the split datasets, please:

1. **Cite both datasets** if comparing human vs AGENT
2. **Mention agent types** detected (Claude, Copilot, Cursor, etc.)
3. **Note verification method** (100% precision via manual validation)
4. **Include sample sizes:** Human (32,895), AGENT (87,432)
5. **Link to public resources:** GitHub, Zenodo deposit

Example citation:
```
"Analysis of test fixtures from FixtureDB Split (human era: 32,895 pre-2021 
fixtures; AGENT era: 87,432 agent-generated fixtures, 2021+) showing..."
```

---

## See Also

- [CSV User Guide](../data/csv-user-guide.md) — CSV format reference
- [Data Models](../split/DATA_MODELS.md) — Complete schema documentation
- [Agent Detection](../architecture/agent-detection.md) — Agent detection methodology
- [Database Schema](../architecture/database-schema.md) — Schema reference
