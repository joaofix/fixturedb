════════════════════════════════════════════════════════════════
ALGORITHM: FixtureDB Human vs Agent Corpus Construction
════════════════════════════════════════════════════════════════

CONSTANTS:
    HUMAN_CUTOFF_DATE      = 2021-01-01
    AGENT_START_DATE       = 2025-01-01   # post-Copilot-GA, post-ChatGPT
    MIN_STARS              = 100
    MIN_COMMITS            = 100
    MIN_TEST_FILES         = 5
    AGENT_SIGNATURES       = ["claude", "cursor", "copilot", "co-authored-by"]
    AGENT_CONFIG_FILES     = ["CLAUDE.md", ".claude/", ".cursor/",
                               "copilot-instructions.md", ".cursorrules"]
    TARGET_REPOS_PER_LANG  = 500
    LANGUAGES              = [python, java, javascript, typescript, go, csharp]

════════════════════════════════════════════════════════════════
PHASE 1 — HUMAN CORPUS (pre-2021)
════════════════════════════════════════════════════════════════

FUNCTION collect_human_corpus():

    FOR each language IN LANGUAGES:

        # 1a. Search GitHub for candidate repos
        candidates = github_search(
            language     = language,
            min_stars    = MIN_STARS,
            not_fork     = true,
            created_before = HUMAN_CUTOFF_DATE,
            has_test_dir = true
        )
        candidates = filter_exclusion_keywords(candidates)

        FOR each repo IN candidates UNTIL target_reached:

            clone_shallow(repo)

            # 1b. Quality filters
            IF count_commits(repo) < MIN_COMMITS     → mark SKIPPED, continue
            IF count_test_files(repo) < MIN_TEST_FILES → mark SKIPPED, continue

            # 1c. Diff-level fixture extraction — pre-2021 commits only
            fixtures_found = []

            FOR each commit IN repo.commits WHERE commit.date < HUMAN_CUTOFF_DATE:

                # Sanity check: confirm no agent signature exists
                # (belt-and-suspenders — pre-2021 should have none)
                IF has_agent_signature(commit) → skip commit

                FOR each modified_file IN commit.added_or_modified_files:
                    IF NOT is_test_file(modified_file) → skip

                    added_lines = get_added_lines(modified_file)
                    new_fixtures = detect_fixtures_in_diff(
                        added_lines,
                        full_file_after = modified_file.source_code_after,
                        language = language
                    )

                    FOR each fixture IN new_fixtures:
                        fixture.commit_sha  = commit.hash
                        fixture.commit_date = commit.date
                        fixture.author_type = "human"
                        fixture.repo_id     = repo.id
                        fixtures_found.append(fixture)

            IF len(fixtures_found) == 0 → mark SKIPPED, continue

            # 1d. Compute metrics for each extracted fixture
            FOR each fixture IN fixtures_found:
                fixture.metrics = compute_metrics(fixture.raw_source, language)
                # metrics: loc, cyclomatic_complexity, cognitive_complexity,
                #          nesting_depth, num_parameters, num_objects_instantiated,
                #          num_external_calls, has_teardown_pair, mock_usages

            write_to_db(repo, fixtures_found, corpus="human")
            delete_clone(repo)


════════════════════════════════════════════════════════════════
PHASE 2 — AGENT CORPUS (2023-present)
════════════════════════════════════════════════════════════════

FUNCTION collect_agent_corpus():

    FOR each language IN LANGUAGES:

        # 2a. Search for repos with agent configuration files
        # (mirrors Andre's methodology — presence of config = active agent use)
        candidates = github_search(
            language        = language,
            min_stars       = MIN_STARS,
            not_fork        = true,
            has_agent_config = AGENT_CONFIG_FILES,  # file existence filter
            pushed_after    = AGENT_START_DATE
        )
        candidates = filter_exclusion_keywords(candidates)

        FOR each repo IN candidates UNTIL target_reached:

            clone_full(repo)   # full history needed for commit walking

            # 2b. Quality filters (same thresholds as human corpus)
            IF count_commits(repo) < MIN_COMMITS     → mark SKIPPED, continue
            IF count_test_files(repo) < MIN_TEST_FILES → mark SKIPPED, continue

            # 2c. Find agent commits
            agent_commits = []
            FOR each commit IN repo.commits WHERE commit.date >= AGENT_START_DATE:
                IF has_agent_signature(commit):
                    agent_commits.append(commit)

            IF len(agent_commits) == 0 → mark SKIPPED, continue

            # 2d. Diff-level fixture extraction — agent commits only
            fixtures_found = []

            FOR each commit IN agent_commits:
                FOR each modified_file IN commit.added_or_modified_files:
                    IF NOT is_test_file(modified_file) → skip

                    added_lines = get_added_lines(modified_file)
                    new_fixtures = detect_fixtures_in_diff(
                        added_lines,
                        full_file_after = modified_file.source_code_after,
                        language = language
                    )

                    FOR each fixture IN new_fixtures:
                        fixture.commit_sha   = commit.hash
                        fixture.commit_date  = commit.date
                        fixture.author_type  = "agent"
                        fixture.agent_name   = detect_agent_name(commit)
                        # agent_name: claude | copilot | cursor | other
                        fixture.repo_id      = repo.id
                        fixtures_found.append(fixture)

            IF len(fixtures_found) == 0 → mark SKIPPED, continue

            # 2e. Compute same metrics as human corpus
            FOR each fixture IN fixtures_found:
                fixture.metrics = compute_metrics(fixture.raw_source, language)

            write_to_db(repo, fixtures_found, corpus="agent")
            delete_clone(repo)


════════════════════════════════════════════════════════════════
PHASE 3 — CONTROL VARIABLE COLLECTION
(needed for between-group statistical comparison)
════════════════════════════════════════════════════════════════

FUNCTION collect_controls():

    FOR each repo IN db WHERE status = "analysed":
        repo.domain       = classify_domain(repo.topics, repo.description)
        repo.star_tier    = "core" IF repo.stars >= 500 ELSE "extended"
        repo.repo_age     = (collection_date - repo.created_at).years
        repo.contributors = github_api.get_contributor_count(repo)

    # These columns allow post-hoc statistical controls:
    # language, domain, star_tier, repo_age, contributors
    # If the two corpora differ significantly on any of these,
    # include them as covariates in the regression models.


════════════════════════════════════════════════════════════════
PHASE 4 — BALANCE CHECK AND REPORTING
════════════════════════════════════════════════════════════════

FUNCTION check_corpus_balance():

    human_repos  = db.query("SELECT * FROM repositories WHERE corpus='human'")
    agent_repos  = db.query("SELECT * FROM repositories WHERE corpus='agent'")

    FOR each dimension IN [language, domain, star_tier]:
        human_dist = distribution(human_repos, dimension)
        agent_dist = distribution(agent_repos, dimension)
        p_value    = chi_square_test(human_dist, agent_dist)

        IF p_value < 0.05:
            LOG "Imbalance detected on {dimension} — report as limitation,
                 include as covariate in regression"
        ELSE:
            LOG "Balanced on {dimension} — between-group comparison valid"

    REPORT:
        human_corpus:  N repos, M fixture definitions, per-language breakdown
        agent_corpus:  N repos, M fixture definitions, per-language breakdown
        imbalanced_on: [list of dimensions requiring covariate control]


════════════════════════════════════════════════════════════════
HELPER FUNCTIONS
════════════════════════════════════════════════════════════════

FUNCTION has_agent_signature(commit):
    message_lower = commit.message.lower()
    FOR each sig IN AGENT_SIGNATURES:
        IF sig IN message_lower:
            RETURN true
    FOR each author IN commit.co_authors:
        IF any(sig IN author.name.lower() FOR sig IN ["claude","cursor","copilot"]):
            RETURN true
    RETURN false

FUNCTION detect_agent_name(commit):
    IF "claude"  IN commit.message.lower(): RETURN "claude"
    IF "cursor"  IN commit.message.lower(): RETURN "cursor"
    IF "copilot" IN commit.message.lower(): RETURN "copilot"
    RETURN "other"

FUNCTION detect_fixtures_in_diff(added_lines, full_file_after, language):
    # added_lines gives us line numbers of new code in this commit
    # full_file_after gives us the complete parseable file
    # Strategy: parse full_file_after with Tree-sitter,
    #           keep only fixtures whose start_line appears in added_lines
    all_fixtures  = tree_sitter_detect(full_file_after, language)
    new_line_nums = {line.number FOR line IN added_lines}
    RETURN [f FOR f IN all_fixtures IF f.start_line IN new_line_nums]