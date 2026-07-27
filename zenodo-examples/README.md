# FixtureDB Example Analyses

Quantitative exploratory data analysis (EDA) of the FixtureDB dataset using Jupyter notebooks.

These notebooks are independent, self-contained analyses that require only the CSV exports from FixtureDB.

## Setup

### Prerequisites
- Python 3.8+
- [Jupyter](https://jupyter.org/) or [JupyterLab](https://jupyterlab.readthedocs.io/)

### Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Extract the FixtureDB dataset (Zenodo archive):
   - Download the `.zip` or `.tar.gz` from Zenodo
   - Unzip in this directory, creating:
     ```
     zenodo-examples/
     ├── fixturedb/
     │   ├── repositories.csv
     │   ├── fixtures.csv
     │   ├── mock_usages.csv
     │   └── test_files.csv
     ├── 01-corpus-composition.ipynb
     └── ...
     ```

3. Launch Jupyter:
```bash
jupyter notebook
```

4. Open any notebook and run all cells (Cell → Run all cells)

## Notebooks

### 1. Corpus Composition (`01-corpus-composition.ipynb`)

**Overview of the FixtureDB dataset**
- Language distribution and coverage
- Star tier breakdown (popular vs. emerging projects)
- Pipeline status (how many repos were successfully analyzed)
- Star distribution across repositories

**Why this matters:** Understand the dataset's scope and representativeness before deeper analysis.

### 2. Fixture Complexity (`02-fixture-complexity.ipynb`)

**Structural characteristics of test fixtures**
- Fixture count per repository
- Fixture scope distribution (module, class, function scope)
- Fixture nesting depth (code structure complexity)
- Correlation between nesting depth and cognitive complexity

**Why this matters:** Identify patterns in how developers structure fixture code; validate that complexity metrics capture meaningful variation.

### 3. Mock Adoption (`03-mock-adoption.ipynb`)

**Use of mocking frameworks in fixtures**
- Mock adoption rate by language
- Mock framework diversity and popularity
- Mock style prevalence (stubs, mocks, spies, fakes)

**Why this matters:** Understand which mocking patterns are common; assess how language conventions influence mock adoption.

### 4. Fixture Patterns (`04-fixture-patterns.ipynb`)

**Fixture reuse and maintenance indicators**
- Fixture reuse count distribution
- Correlation between reuse count and complexity
- Teardown pair adoption (setup/teardown pairing)
- Repository metadata impact (contributors, domain)

**Why this matters:** Identify opportunities for test infrastructure optimization; understand patterns associated with well-maintained fixtures.

## Column Definitions

For detailed column definitions and data types, see the main FixtureDB documentation:
- [CSV Export Guide](../docs/data/14-csv-export-guide.md) — Full column documentation
- [Database Schema](../docs/architecture/03-database-schema.md) — Table and relationship details

## Limitations

These notebooks use **CSV exports only**, which contain quantitative metrics only. For analysis requiring:
- Fixture source code (`raw_source`)
- Qualitative mock classification (`mock_style`, `target_layer`)
- Fixture category (`category`)

...query the SQLite database (`fixtures.db`) directly or using an ORM.

See [Limitations & Threats to Validity](../docs/reference/12-limitations.md) for known constraints and detection limitations.

## Citation

If you use FixtureDB or these analyses in your research, please cite:

```bibtex
@inproceedings{Almeida2026FixtureDB,
  title={FixtureDB: A Multi-Language Dataset of Test Fixture Definitions from Open-Source Software},
  author={Almeida, Jo\~ao and Hora, Andre},
  booktitle={Proceedings of the 2026 IEEE International Conference on Software Maintenance and Evolution},
  year={2026}
}
```

## Questions & Feedback

For issues or improvements to these notebooks, open an issue on [GitHub](https://github.com/joaofix/fixturedb).
