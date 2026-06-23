# Code Review / Merge Checklist

Use this checklist before merging any pull request to `main` or `master`.

- [ ] Tests: All new and existing tests pass locally (`pytest -q`).
- [ ] CI: The CI job passes on this branch (checks green).
- [ ] Coverage: New behavior has tests; consider updating or noting coverage impact.
- [ ] Lint/Format: Code is formatted and linted consistently (project conventions).
- [ ] Docs: Public APIs and user-facing changes are documented (`docs/` updated).
- [ ] Changelog: Add an entry if the change affects users or reproducibility.
- [ ] Backwards compatibility: Confirm no breaking changes without a migration plan.
- [ ] Secrets: No credentials, tokens, or secrets in the diff.
- [ ] Performance: Any performance-sensitive changes include basic benchmarks or rationale.
- [ ] Security: No obvious security issues (e.g., command injection, unsafe file writes).
- [ ] Reviewers: Add at least one reviewer familiar with the affected module(s).
- [ ] Issue: Link to the related issue or task in the PR description.
- [ ] Small PRs: Prefer small, focused PRs; split large changes if possible.

Optional:

- [ ] CI caching: Ensure caching keys are stable and do not leak environment-specific data.
- [ ] Database migrations: Include migration scripts and migration tests if schema changes.

Follow-up actions post-merge:

- [ ] Tag release if applicable.
- [ ] Monitor CI for regressions and address failures promptly.
