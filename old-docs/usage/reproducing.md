# Reproducing the Paper Corpus

**For reproducibility verification**  — This section uses the SQLite database to confirm exact extraction state. For analysis, use CSV exports or the full database (see [Using the Dataset for Research](../usage/usage.md)).

The exact state of every repository analysed in the paper is reproducible
via the `pinned_commit` SHA stored in the `repositories` table.

```bash
# Query the pinned commit for a specific repo
sqlite3 data/corpus.db \
  "SELECT full_name, clone_url, pinned_commit FROM repositories
   WHERE full_name = 'pytest-dev/pytest';"

# Re-clone at the exact state used in the paper
git clone <clone_url>
cd <repo>
git fetch --depth 1 origin <pinned_commit>
git checkout <pinned_commit>
```

## Full replication from scratch

To fully replicate the corpus from scratch:

1. Clone this repository
2. Set up your GitHub token
3. Run `python pipeline.py run`

Note that GitHub repositories may be deleted or made private after the paper
was published. The Zenodo deposit includes the SQLite database with all
extracted data, so the analytical corpus remains available regardless.
