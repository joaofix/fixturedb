"""
Dataset Exporter Module

Creates standalone, self-contained datasets as SQLite databases and CSV exports.
Ensures both fixturedb-human and fixturedb-agent are completely independent
and usable without cross-references or the original corpus.db.
"""

import csv
import json
import logging
import shutil
import sqlite3
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ExportResult:
    """Result of dataset export operation."""
    db_path: Path
    csv_files: List[Path]
    documentation_files: List[Path]
    zip_path: Path
    total_size_mb: float = 0.0
    fixture_count: int = 0
    repository_count: int = 0


class DatasetExporter:
    """Base class for exporting datasets."""

    def __init__(self, source_db: Path, output_dir: Path):
        """
        Initialize exporter.

        Args:
            source_db: Source database to export from
            output_dir: Directory to save exports
        """
        self.source_db = Path(source_db)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export_table_to_csv(
        self,
        table_name: str,
        query: Optional[str] = None,
        extra_columns: Optional[Dict[str, str]] = None,
    ) -> Path:
        """
        Export a database table to CSV.

        Args:
            table_name: Name of table to export
            query: Optional custom query (instead of SELECT * FROM table)
            extra_columns: Optional dict of column_name: default_value to add

        Returns:
            Path to CSV file
        """
        csv_path = self.output_dir / f"{table_name}.csv"

        try:
            conn = sqlite3.connect(self.source_db)
            conn.row_factory = sqlite3.Row

            # Get rows
            if query:
                rows = conn.execute(query).fetchall()
            else:
                rows = conn.execute(f"SELECT * FROM {table_name}").fetchall()

            if not rows:
                logger.warning(f"No rows found in {table_name}")
                return csv_path

            # Convert to dicts
            data = [dict(row) for row in rows]

            # Add extra columns if provided
            if extra_columns:
                for row in data:
                    for col_name, default_value in extra_columns.items():
                        if col_name not in row:
                            row[col_name] = default_value

            # Write CSV
            if data:
                fieldnames = list(data[0].keys())
                with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(data)

                logger.info(f"Exported {len(data)} rows to {csv_path.name}")

            conn.close()

        except Exception as e:
            logger.error(f"Failed to export {table_name}: {e}")

        return csv_path

    def _get_table_count(self, table_name: str) -> int:
        """Get row count from table."""
        try:
            conn = sqlite3.connect(self.source_db)
            cursor = conn.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cursor.fetchone()[0]
            conn.close()
            return count
        except Exception as e:
            logger.warning(f"Failed to count {table_name}: {e}")
            return 0


class HumanDatasetExporter(DatasetExporter):
    """Export fixturedb-human.db with sampled fixtures."""

    def export(
        self,
        sampled_fixture_ids: List[int],
        version: str = "1.0",
    ) -> ExportResult:
        """
        Export human dataset with sampled fixtures only.

        Args:
            sampled_fixture_ids: List of fixture IDs to include
            version: Dataset version

        Returns:
            ExportResult with paths to all exported files
        """
        logger.info("Exporting human dataset...")

        # Export CSVs with filters
        csv_files = []

        # Repositories (all)
        csv_files.append(self.export_table_to_csv('repositories'))

        # Test files (only those with sampled fixtures)
        query = f"""
            SELECT DISTINCT tf.* FROM test_files tf
            WHERE tf.id IN (
                SELECT DISTINCT file_id FROM fixtures WHERE id IN ({','.join(map(str, sampled_fixture_ids))})
            )
        """
        csv_files.append(self.export_table_to_csv('test_files', query=query))

        # Fixtures (only sampled)
        query = f"""
            SELECT * FROM fixtures
            WHERE id IN ({','.join(map(str, sampled_fixture_ids))})
        """
        csv_files.append(self.export_table_to_csv('fixtures', query=query))

        # Mocks (for fixtures in sample)
        query = f"""
            SELECT DISTINCT mu.* FROM mock_usages mu
            WHERE mu.fixture_id IN ({','.join(map(str, sampled_fixture_ids))})
        """
        csv_files.append(self.export_table_to_csv('mock_usages', query=query))

        # Generate documentation
        doc_files = self._generate_documentation(
            sampled_fixture_ids,
            version,
            dataset_type='human',
        )

        # Create ZIP archive
        zip_path = self._create_zip_archive(csv_files + doc_files, 'human', version)

        # Calculate total size
        total_size = sum(f.stat().st_size for f in csv_files + doc_files) / (1024 * 1024)

        result = ExportResult(
            db_path=self.source_db,
            csv_files=csv_files,
            documentation_files=doc_files,
            zip_path=zip_path,
            total_size_mb=total_size,
            fixture_count=len(sampled_fixture_ids),
            repository_count=self._get_table_count('repositories'),
        )

        return result

    def _generate_documentation(
        self,
        sampled_ids: List[int],
        version: str,
        dataset_type: str,
    ) -> List[Path]:
        """Generate README and SCHEMA documentation."""
        doc_files = []

        # README
        readme_path = self.output_dir / 'README.md'
        readme_content = f"""# FixtureDB Human Dataset v{version}

## Overview

This dataset contains {len(sampled_ids)} human-created test fixtures extracted from repositories before 2021.
It represents the pre-AI-assistant era and serves as a baseline for comparison with AI-generated fixtures.

## Contents

- `repositories.csv` — Repository metadata (owner, language, stars, etc.)
- `test_files.csv` — Test file metadata (path, language, number of fixtures, etc.)
- `fixtures.csv` — Fixture definitions (name, type, scope, complexity metrics, etc.)
- `mock_usages.csv` — Mock framework usage within fixtures

## Schema

See SCHEMA.md for detailed table definitions and column descriptions.

## Sampling

Fixtures were sampled stratified by fixture_type to maintain distribution:
- Random seed: 42 (reproducible)
- Total available: calculated from extraction phase
- Sampled: {len(sampled_ids)}

## Usage

### Load into SQLite

```bash
sqlite3 fixturedb-human.db
.mode csv
.import repositories.csv repositories
.import test_files.csv test_files
.import fixtures.csv fixtures
.import mock_usages.csv mock_usages
```

### Analyze Fixtures

```sql
-- Count by type
SELECT fixture_type, COUNT(*) FROM fixtures GROUP BY fixture_type;

-- Find complex fixtures
SELECT name, loc, cyclomatic_complexity FROM fixtures WHERE cyclomatic_complexity > 10;

-- Fixtures with mocks
SELECT f.name, COUNT(m.id) as mock_count
FROM fixtures f
LEFT JOIN mock_usages m ON f.id = m.fixture_id
GROUP BY f.id
HAVING mock_count > 0;
```

## Citation

If you use this dataset in your research, please cite:
- Original corpus: [ICSME NIER 2026]
- Dataset version: {version}
- Generation date: [see export timestamp]

## License

See LICENSE file in the archive.

## FAQ

**Q: Can I use this dataset without corpus.db?**
A: Yes. This is a completely standalone dataset with all required metadata.

**Q: How were fixtures extracted?**
A: Using snapshot-based extraction at each repository's pinned commit before 2021.

**Q: Why sampled instead of all fixtures?**
A: To match AGENT dataset size for fair statistical comparison.
"""

        with open(readme_path, 'w') as f:
            f.write(readme_content)
        doc_files.append(readme_path)
        logger.info(f"Generated README: {readme_path.name}")

        # SCHEMA.md
        schema_path = self.output_dir / 'SCHEMA.md'
        schema_content = """# Database Schema

## repositories

Contains repository metadata.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Unique identifier |
| github_id | INTEGER | GitHub API ID |
| full_name | TEXT | Owner/repo |
| language | TEXT | Primary programming language |
| stars | INTEGER | GitHub stars |
| forks | INTEGER | GitHub forks |
| description | TEXT | Repository description |
| topics | JSON | GitHub topics |
| created_at | TEXT | Creation date (ISO) |
| pushed_at | TEXT | Last push date (ISO) |
| clone_url | TEXT | HTTPS clone URL |
| pinned_commit | TEXT | Commit SHA used for extraction |
| domain | TEXT | Inferred domain (web/data/cli/infra/library/other) |
| status | TEXT | Processing status |
| num_test_files | INTEGER | Number of test files analyzed |
| num_fixtures | INTEGER | Total fixtures extracted |

## test_files

Contains test file metadata.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Unique identifier |
| repo_id | INTEGER | Foreign key to repositories |
| relative_path | TEXT | Path relative to repo root |
| language | TEXT | Programming language |
| file_loc | INTEGER | Lines of code |
| num_test_funcs | INTEGER | Number of test functions |
| num_fixtures | INTEGER | Number of fixtures in file |
| total_fixture_loc | INTEGER | Total fixture code lines |

## fixtures

Contains fixture definitions.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Unique identifier |
| file_id | INTEGER | Foreign key to test_files |
| repo_id | INTEGER | Foreign key to repositories |
| name | TEXT | Fixture name |
| fixture_type | TEXT | pytest/unittest/other |
| scope | TEXT | function/class/module/session |
| start_line | INTEGER | Start line in file |
| end_line | INTEGER | End line in file |
| loc | INTEGER | Lines of code |
| cyclomatic_complexity | INTEGER | McCabe complexity |
| max_nesting_depth | INTEGER | Maximum nesting depth |
| num_objects_instantiated | INTEGER | Objects created |
| num_external_calls | INTEGER | External function calls |
| num_parameters | INTEGER | Number of parameters |
| reuse_count | INTEGER | Number of test functions using this fixture |
| has_teardown_pair | BOOLEAN | Has teardown/cleanup |
| raw_source | TEXT | Complete fixture source code |
| category | TEXT | RQ1 taxonomy category |
| framework | TEXT | Mock framework used (if any) |
| num_mocks | INTEGER | Number of mocks configured |

## mock_usages

Contains mock framework usage.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Unique identifier |
| fixture_id | INTEGER | Foreign key to fixtures |
| repo_id | INTEGER | Foreign key to repositories |
| framework | TEXT | Mock framework (unittest.mock, pytest-mock, etc.) |
| target_identifier | TEXT | What is being mocked |
| num_interactions_configured | INTEGER | Number of interactions/assertions |
| raw_snippet | TEXT | Mock configuration code |
"""

        with open(schema_path, 'w') as f:
            f.write(schema_content)
        doc_files.append(schema_path)
        logger.info(f"Generated SCHEMA: {schema_path.name}")

        return doc_files

    def _create_zip_archive(
        self,
        files: List[Path],
        dataset_type: str,
        version: str,
    ) -> Path:
        """Create ZIP archive with all files."""
        zip_path = self.output_dir / f"fixturedb-{dataset_type}_v{version}_export.zip"

        try:
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for file_path in files:
                    zf.write(file_path, arcname=file_path.name)

            logger.info(f"Created ZIP archive: {zip_path.name}")

        except Exception as e:
            logger.error(f"Failed to create ZIP archive: {e}")

        return zip_path


class LLMDatasetExporter(HumanDatasetExporter):
    """Export fixturedb-agent.db with agent metadata."""

    def export(
        self,
        sampled_fixture_ids: List[int],
        version: str = "1.0",
    ) -> ExportResult:
        """
        Export AGENT dataset with sampled fixtures and agent tracking.

        Args:
            sampled_fixture_ids: List of fixture IDs to include
            version: Dataset version

        Returns:
            ExportResult with paths to all exported files
        """
        logger.info("Exporting AGENT dataset...")

        # Export CSVs with filters (same as human)
        csv_files = []

        csv_files.append(self.export_table_to_csv('repositories'))

        query = f"""
            SELECT DISTINCT tf.* FROM test_files tf
            WHERE tf.id IN (
                SELECT DISTINCT file_id FROM fixtures WHERE id IN ({','.join(map(str, sampled_fixture_ids))})
            )
        """
        csv_files.append(self.export_table_to_csv('test_files', query=query))

        query = f"""
            SELECT * FROM fixtures
            WHERE id IN ({','.join(map(str, sampled_fixture_ids))})
        """
        csv_files.append(self.export_table_to_csv('fixtures', query=query))

        query = f"""
            SELECT DISTINCT mu.* FROM mock_usages mu
            WHERE mu.fixture_id IN ({','.join(map(str, sampled_fixture_ids))})
        """
        csv_files.append(self.export_table_to_csv('mock_usages', query=query))

        # Generate documentation (includes AGENTS.md for AGENT)
        doc_files = self._generate_llm_documentation(
            sampled_fixture_ids,
            version,
        )

        # Create ZIP archive
        zip_path = self._create_zip_archive(csv_files + doc_files, 'agent', version)

        total_size = sum(f.stat().st_size for f in csv_files + doc_files) / (1024 * 1024)

        result = ExportResult(
            db_path=self.source_db,
            csv_files=csv_files,
            documentation_files=doc_files,
            zip_path=zip_path,
            total_size_mb=total_size,
            fixture_count=len(sampled_fixture_ids),
            repository_count=self._get_table_count('repositories'),
        )

        return result

    def _generate_llm_documentation(
        self,
        sampled_ids: List[int],
        version: str,
    ) -> List[Path]:
        """Generate README, SCHEMA, and AGENTS documentation."""
        doc_files = []

        # README (similar to human but with AGENT context)
        readme_path = self.output_dir / 'README.md'
        readme_content = f"""# FixtureDB AGENT Dataset v{version}

## Overview

This dataset contains {len(sampled_ids)} test fixtures extracted from commits authored/co-authored by AI agents.
Coverage: 2021-present (from agent adoption onwards).
This serves as a comparison dataset to the human-created fixtures from the pre-2021 era.

## Contents

- `repositories.csv` — Repository metadata (owner, language, stars, etc.)
- `test_files.csv` — Test file metadata (path, language, number of fixtures, etc.)
- `fixtures.csv` — Fixture definitions (name, type, scope, complexity, agent_type, commit_sha)
- `mock_usages.csv` — Mock framework usage within fixtures
- `AGENTS.md` — Agent detection methodology and validation approach

## Schema

See SCHEMA.md for detailed table definitions and column descriptions.
See AGENTS.md for agent detection methodology.

## Sampling

Fixtures were sampled stratified by fixture_type to match human dataset:
- Random seed: 42 (reproducible)
- Total available: calculated from extraction phase
- Sampled: {len(sampled_ids)}

## Agent Detection

### Phase 1A: File Pattern Scanning
Repositories were scanned for agent configuration files (e.g., .cursorrules, .aider).

### Phase 1B: Commit Verification
Agent commits were verified by parsing Co-authored-by trailers and author metadata.

### Phase 3: Fixture Validation
Fixtures were validated to ensure they were completely added (not refactored) in single commits.

## Supported Agents

- Claude (Anthropic)
- Copilot (GitHub/OpenAI)
- Cursor (IDE)
- Aider (CLI)
- OpenHands (Autonomous)
- Devin (Autonomous)
- Cline (VS Code)
- Junie (Autonomous)
- Gemini (Google)
- CodeRabbit (Code Review)
- Windsurf (IDE)

## Usage

### Load into SQLite

```bash
sqlite3 fixturedb-agent.db
.mode csv
.import repositories.csv repositories
.import test_files.csv test_files
.import fixtures.csv fixtures
.import mock_usages.csv mock_usages
```

### Analyze by Agent

```sql
-- Fixtures by agent
SELECT agent_type, COUNT(*) FROM fixtures GROUP BY agent_type;

-- Average complexity by agent
SELECT agent_type, AVG(cyclomatic_complexity) as avg_complexity
FROM fixtures
GROUP BY agent_type
ORDER BY avg_complexity DESC;
```

## Citation

If you use this dataset in your research, please cite:
- Original corpus: [ICSME NIER 2026]
- Dataset version: {version}
- Agent detection methodology: [Advisor's paper reference]

## License

See LICENSE file in the archive.

## FAQ

**Q: What agents are included?**
A: All agents detected via Co-authored-by trailers and author patterns (2021+).

**Q: How complete are the extracted fixtures?**
A: 100% - each fixture was completely added in a single commit (no refactoring).

**Q: Can I use this without corpus.db?**
A: Yes. This is a completely standalone dataset.
"""

        with open(readme_path, 'w') as f:
            f.write(readme_content)
        doc_files.append(readme_path)

        # SCHEMA.md (same as human)
        schema_path = self.output_dir / 'SCHEMA.md'
        schema_content = """# Database Schema

## (See human dataset for fixtures, test_files, repositories, mock_usages tables)

### fixtures (AGENT-specific columns)

Additional columns in AGENT dataset:
| Column | Type | Description |
|--------|------|-------------|
| commit_sha | TEXT | Git commit SHA where fixture was added |
| agent_type | TEXT | Agent type (claude, copilot, cursor, etc.) |
| is_complete_addition | BOOLEAN | True if 100% added in this commit |
"""

        with open(schema_path, 'w') as f:
            f.write(schema_content)
        doc_files.append(schema_path)

        # AGENTS.md
        agents_path = self.output_dir / 'AGENTS.md'
        agents_content = """# Agent Detection Methodology

## Overview

This document describes how AI agent-generated fixtures were identified and verified.

## Phase 1A: File Pattern Scanning

Configuration files and dotfiles were scanned in each repository to identify agent presence.

### Supported File Patterns

| Agent | Patterns |
|-------|----------|
| Claude | .cursorrules, .cursorignore, .cursor, claude.config |
| Cursor | .cursor, .cursorrules, .cursorignore, cursor.config |
| Copilot | .copilot, .copilot.config, .copilot-config |
| Aider | .aider.conf, .aider-config, aider.config |
| OpenHands | .openhands.config, .openhands |
| Devin | .devin.config, .devin |
| Cline | .cline.config, .cline |
| Other | .junie, .gemini, .julius, agent.config |

## Phase 1B: Commit Verification

Agent commits were identified using multiple signals:

1. **Co-Authored-By trailer** (highest confidence)
   Pattern: `Co-Authored-By: <agent_name> <email>`
   Case-insensitive matching for agent keywords

2. **Author metadata**
   - Author name containing agent keywords
   - Author email patterns

3. **Commit message**
   - Commit body mentioning agent names
   - Generated commit messages

## Phase 3: Fixture Validation

### Completeness Validation

Only fixtures completely added in a single commit are included.
This excludes:
- Fixtures modified after initial addition (refactoring)
- Fixtures added across multiple commits
- Partially generated fixtures

### Validation Method

For each fixture:
1. Check that all lines in diff are additions (no deletions)
2. Verify fixture did not exist in parent commit
3. Confirm fixture fully defined in single commit

## Results

### Agent Distribution

See fixture counts by agent_type in the fixtures.csv file.

### Confidence Levels

- High confidence: Co-authored-by trailer + file patterns
- Medium confidence: Co-authored-by trailer only
- Low confidence: File patterns only (not included in this dataset)

## Limitations

1. **Co-authored-by not universal** — Not all agent tools use Co-authored-by trailers
2. **Name variations** — Different agents may use different naming conventions
3. **False positives** — Some names may match human authors
4. **Coverage** — Only 2021+ commits (when agents became prevalent)

## References

- [Advisor's paper on agent detection]
- GitHub's Co-Authored-By documentation
- Individual agent documentation and conventions
"""

        with open(agents_path, 'w') as f:
            f.write(agents_content)
        doc_files.append(agents_path)
        logger.info(f"Generated AGENTS: {agents_path.name}")

        return doc_files
