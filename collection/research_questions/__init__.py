"""Scripts that compute paper results directly from the collected data
(`db/{a,b,c}.db` and/or `datasets/{a,b,c}/`) and write a findings report.

`rqN.py` files answer a specific research question (see
docs/research-questions.md); other scripts here (e.g.
`language_contamination.py`) are data-quality/validation checks that don't
map to one specific RQ. Every script is runnable standalone:
`python -m collection.research_questions.<module>`. Reports are written to
`research_questions/` at the repo root (gitignored, regenerated on demand --
not a collection-pipeline artifact).
"""
