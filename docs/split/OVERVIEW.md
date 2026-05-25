# Overview

The paired FixtureDB study uses repositories as matching containers and commits as the comparison unit.

## Method

1. Select repositories that contain both human and agent commit histories.
2. Identify commits with agent activity and matching non-agent commits in the same repository.
3. Extract fixtures at the commit level.
4. Record commit observations in one study database.
5. Analyze the result with paired statistics.

## Why Pair Within a Repository

The earlier split approach tried to build two separate populations. That overstates the methodological separation and loses context. The paired design keeps the comparison local to each repository, which controls for project-specific effects such as domain, language, and team conventions.

## Analysis Framing

The natural analysis is paired rather than independent-samples. That means the repository contributes matched observations and the comparison asks how fixture characteristics differ between agent and non-agent commits within the same project.
