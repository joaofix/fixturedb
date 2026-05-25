# DEPRECATED: Paired Study Documentation (Legacy)

⚠️ **This documentation describes an older methodology that has been superseded by the between-group study design.** 

The paired within-repository approach has been replaced with a more methodologically sound between-group comparison design. See [FixtureDB Between-Group Study](../getting-started/intro.md) for current methodology.

---

## Why This Documentation Is Archived

The paired study had methodological limitations:
- **Temporal confounding:** Comparing 2021 and 2023+ in the same repo conflates agent effects with framework evolution
- **Selection bias:** Repositories with agents in 2023+ differ systematically from 2021 baselines
- **Power issues:** Limited paired observations per repository

The **between-group design** resolves these by:
- Temporally separating populations (pre-2021 human vs 2023+ agent)
- Balancing control variables across corpora
- Improving statistical power with larger independent samples

---

## Legacy Documentation

This directory contains archived documentation for the paired study approach. It is kept for reference and historical documentation purposes.

The key change was methodological: the project moved from a human-vs-agent repository split to a **between-group temporal comparison**.

## Old Study Design (For Reference)

- repository was the pairing container
- commit was the unit of comparison
- agent commits were compared to non-agent commits from the same project
- output was paired study data, not two independent corpora

## Historical Structure

- [Overview](OVERVIEW.md) - old paired study design
- [Execution Guide](EXECUTION_GUIDE.md) - old pipeline stages  
- [Phases](PHASES.md) - old collection phases

