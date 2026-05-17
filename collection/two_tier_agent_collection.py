"""
Two-tier methodology for agent fixture collection.

Tier 1: Search existing corpus repos for agent commits (within-repo comparison)
Tier 2: Discover matched repos via SEART (between-repo comparison, if Tier 1 insufficient)

This module provides utilities for orchestrating the two-tier collection workflow.
"""

import json
import logging
import re
import subprocess
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from datetime import datetime

from .config import (
    AGENT_SIGNATURES,
    AGENT_DATASET_START_DATE,
    TIER1_MINIMUM_REPOS_WITH_AGENT,
    TIER1_MINIMUM_AGENT_COMMITS,
    TIER2_MATCHING_MIN_STARS,
    TIER2_MATCHING_MAX_STARS,
    TIER2_MATCHING_STAR_TOLERANCE,
    TIER2_MIN_COMMITS,
    TIER2_MIN_TEST_FILES,
    TIER2_MUST_HAVE_AGENT_CONFIGS,
)

logger = logging.getLogger(__name__)


@dataclass
class AgentCommitInfo:
    """Information about a single agent commit."""
    commit_sha: str
    agent_type: str
    commit_date: str
    author_name: str
    author_email: str


@dataclass
class Tier1Assessment:
    """Results of Tier 1 (corpus repos) assessment."""
    repos_with_agent: int = 0
    total_agent_commits: int = 0
    agent_commits_in_test_files: int = 0
    repos_by_agent: Dict[str, int] = field(default_factory=dict)
    sufficient: bool = False  # True if Tier 1 meets minimum thresholds
    tier2_recommended: bool = False  # True if Tier 2 should be triggered
    summary: str = ""
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


class Tier1RepositoryScanner:
    """Scan corpus repositories for agent commits (Tier 1)."""
    
    def __init__(self, corpus_db_path: Path):
        """
        Initialize Tier 1 scanner.
        
        Args:
            corpus_db_path: Path to corpus.db containing repository list
        """
        self.corpus_db_path = Path(corpus_db_path)
        self.agent_signatures = AGENT_SIGNATURES
    
    def scan_repo_for_agent_commits(
        self,
        repo_path: Path,
        start_date: str = AGENT_DATASET_START_DATE
    ) -> List[AgentCommitInfo]:
        """
        Scan a single repository for agent commits (Co-authored-by trailers).
        
        Args:
            repo_path: Path to repository on disk
            start_date: Only include commits after this date (ISO format)
        
        Returns:
            List of AgentCommitInfo for agent commits found
        """
        if not repo_path.is_dir():
            return []
        
        commits = []
        
        try:
            # Get commit log with agent keywords
            cmd = [
                'git', 'log', '--all',
                f'--since={start_date}',
                '--format=%H|%an|%ae|%aI|%b'
            ]
            result = subprocess.run(
                cmd,
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                logger.warning(f"Failed to get git log for {repo_path.name}")
                return []
            
            # Parse commits
            for line in result.stdout.strip().split('\n'):
                if not line.strip():
                    continue
                
                parts = line.split('|', 4)
                if len(parts) < 5:
                    continue
                
                commit_sha, author_name, author_email, commit_date, body = parts
                
                # Search for agent signatures in commit message
                agent_type = self._detect_agent_in_commit(
                    author_name, author_email, body
                )
                
                if agent_type:
                    commits.append(AgentCommitInfo(
                        commit_sha=commit_sha,
                        agent_type=agent_type,
                        commit_date=commit_date,
                        author_name=author_name,
                        author_email=author_email,
                    ))
        
        except subprocess.TimeoutExpired:
            logger.warning(f"Timeout scanning {repo_path.name}")
        except Exception as e:
            logger.error(f"Error scanning {repo_path.name}: {e}")
        
        return commits
    
    def _detect_agent_in_commit(
        self,
        author_name: str,
        author_email: str,
        body: str
    ) -> Optional[str]:
        """
        Detect agent type from commit metadata.
        
        Args:
            author_name: Commit author name
            author_email: Commit author email
            body: Commit message body (for Co-authored-by parsing)
        
        Returns:
            Agent type (claude/cursor/copilot/other) or None
        """
        # Search body for Co-authored-by trailers
        # Case-insensitive search for agent signatures
        search_text = f"{author_name} {author_email} {body}".lower()
        
        # Check agent signatures
        for agent_type, keywords in self.agent_signatures.items():
            for keyword in keywords:
                if keyword.lower() in search_text:
                    return agent_type
        
        return None
    
    def assess_tier1(self, corpus_repos: List[Dict]) -> Tier1Assessment:
        """
        Assess Tier 1 yield from corpus repositories.
        
        Args:
            corpus_repos: List of repo metadata from corpus.db
                         Should include: name, path
        
        Returns:
            Tier1Assessment with results and recommendations
        """
        assessment = Tier1Assessment()
        repos_scanned = 0
        repos_with_agent = {}  # {repo_name: [AgentCommitInfo]}
        
        logger.info(f"Scanning {len(corpus_repos)} corpus repositories for agent commits...")
        
        for repo_meta in corpus_repos:
            repos_scanned += 1
            repo_name = repo_meta.get('name', 'unknown')
            repo_path = Path(repo_meta.get('path', f'/tmp/not_found/{repo_name}'))
            
            if not repo_path.exists():
                # Try to find in clones
                repo_path = Path('/tmp') / 'clones' / repo_name
                if not repo_path.exists():
                    logger.debug(f"Repo not found: {repo_name}")
                    continue
            
            commits = self.scan_repo_for_agent_commits(repo_path)
            
            if commits:
                repos_with_agent[repo_name] = commits
                assessment.repos_with_agent += 1
                assessment.total_agent_commits += len(commits)
                
                # Count by agent type
                for commit in commits:
                    agent = commit.agent_type
                    assessment.repos_by_agent[agent] = \
                        assessment.repos_by_agent.get(agent, 0) + 1
        
        # Assess if sufficient
        assessment.sufficient = (
            assessment.repos_with_agent >= TIER1_MINIMUM_REPOS_WITH_AGENT and
            assessment.total_agent_commits >= TIER1_MINIMUM_AGENT_COMMITS
        )
        
        assessment.tier2_recommended = not assessment.sufficient
        
        # Generate summary
        assessment.summary = self._generate_summary(assessment)
        
        return assessment
    
    def _generate_summary(self, assessment: Tier1Assessment) -> str:
        """Generate human-readable summary of Tier 1 assessment."""
        lines = [
            f"Tier 1 Assessment Results:",
            f"  Repos with agent commits: {assessment.repos_with_agent}",
            f"  Total agent commits: {assessment.total_agent_commits}",
            f"  Agent distribution: {assessment.repos_by_agent}",
        ]
        
        if assessment.sufficient:
            lines.append(f"  ✓ SUFFICIENT for statistical power (Tier 2 not needed)")
        else:
            lines.append(f"  ⚠ INSUFFICIENT (Tier 2 matching recommended)")
            lines.append(f"    - Need at least {TIER1_MINIMUM_REPOS_WITH_AGENT} repos, found {assessment.repos_with_agent}")
            lines.append(f"    - Need at least {TIER1_MINIMUM_AGENT_COMMITS} commits, found {assessment.total_agent_commits}")
        
        return "\n".join(lines)


class Tier2RepoMatcher:
    """Discover supplementary repositories via agent activity signals (Tier 2)."""
    
    def __init__(self):
        """Initialize Tier 2 matcher."""
        pass
    
    def find_matched_repos(
        self,
        target_count: int = 50,
        language: str = "python",
        domain_labels: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        Find supplementary repositories for Tier 2.
        
        Uses SEART API to search for repos with:
        - Agent configuration files (CLAUDE.md, .cursorrules, etc.)
        - Similar star count to corpus
        - Same language
        - Similar domain labels (if provided)
        
        Args:
            target_count: Target number of repos to find
            language: Programming language filter
            domain_labels: Optional domain labels to match (from corpus classifier)
        
        Returns:
            List of repo metadata dictionaries suitable for Tier 2 collection
        
        Note:
            This is a placeholder implementation. Real implementation would:
            1. Call SEART API with appropriate search filters
            2. Parse results for agent activity signals
            3. Filter by star count, commits, test files
            4. Verify agent config files exist
        """
        logger.info(f"Placeholder: Would search for {target_count} {language} repos with agent activity")
        logger.info(f"  Using SEART engine for: {language}")
        if domain_labels:
            logger.info(f"  Preferring domains: {domain_labels}")
        logger.info(f"  With Tier 2 matching criteria:")
        logger.info(f"    - Star range: {TIER2_MATCHING_MIN_STARS}-{TIER2_MATCHING_MAX_STARS}")
        logger.info(f"    - Min commits: {TIER2_MIN_COMMITS}")
        logger.info(f"    - Min test files: {TIER2_MIN_TEST_FILES}")
        logger.info(f"    - Must have agent config files: {TIER2_MUST_HAVE_AGENT_CONFIGS}")
        
        return []  # Placeholder
