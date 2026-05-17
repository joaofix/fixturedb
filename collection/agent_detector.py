"""
Phase 1A: Scan repositories for AI agent configuration files.

Identifies repositories that may have been worked on with AI assistants
by detecting configuration files commonly created by these tools.

Supported agents: Claude, Cursor, Copilot, Aider, OpenHands, Devin, Jules, Cline, Junie, Gemini
"""

import json
import logging
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .config import AGENT_DATASET_START_DATE

logger = logging.getLogger(__name__)


@dataclass
class AgentFileDetectionResult:
    """Result of scanning a single repository for agent files."""
    repo_name: str
    agents_found: Dict[str, List[str]] = field(default_factory=dict)
    total_agent_files: int = 0
    
    def __post_init__(self):
        """Calculate total agent files found."""
        self.total_agent_files = sum(len(files) for files in self.agents_found.values())


class AgentFileScanner:
    """Phase 1A: Scan repositories for agent configuration files."""
    
    # Agent configuration file patterns (case-insensitive)
    AGENT_FILE_PATTERNS = {
        'claude': {
            'file_names': [
                '.cursorrules',  # Common for Claude in Cursor editor
                '.cursorignore',
                '.cursor',
                'claude.config',
            ],
            'patterns': [r'\.cursorrules?$', r'claude\.config$'],
        },
        'cursor': {
            'file_names': [
                '.cursor',
                '.cursorrules',
                '.cursorignore',
                'cursor.config',
            ],
            'patterns': [r'\.cursor(rules|ignore)?$', r'cursor\.config$'],
        },
        'copilot': {
            'file_names': [
                '.copilot',
                '.copilot.config',
                '.copilot-config',
                'copilot.config',
            ],
            'patterns': [r'\.copilot', r'copilot\.config'],
        },
        'aider': {
            'file_names': [
                '.aider.conf',
                '.aider.conf.json',
                '.aider-config',
                'aider.config',
            ],
            'patterns': [r'\.aider', r'aider\.config', r'aider\.conf'],
        },
        'openhands': {
            'file_names': [
                '.openhands.config',
                '.openhands',
                'openhands.config',
            ],
            'patterns': [r'\.openhands', r'openhands\.config'],
        },
        'devin': {
            'file_names': [
                '.devin.config',
                '.devin',
                'devin.config',
            ],
            'patterns': [r'\.devin', r'devin\.config'],
        },
        'cline': {
            'file_names': [
                '.cline.config',
                '.cline',
                'cline.config',
            ],
            'patterns': [r'\.cline', r'cline\.config'],
        },
        'other_agents': {
            'file_names': [
                '.junie.config',
                '.gemini.config',
                '.julius.config',
                'agent.config',
            ],
            'patterns': [r'\.junie', r'\.gemini', r'\.julius', r'agent\.config'],
        },
    }
    
    def __init__(self, clones_dir: Path = None):
        """
        Initialize the agent file scanner.
        
        Args:
            clones_dir: Path to directory containing cloned repositories.
                       Defaults to current working directory + clones/.
        """
        if clones_dir is None:
            clones_dir = Path.cwd() / 'clones'
        
        self.clones_dir = Path(clones_dir)
        
        if not self.clones_dir.exists():
            raise ValueError(f"Clones directory not found: {self.clones_dir}")
    
    def scan_repository(self, repo_name: str) -> AgentFileDetectionResult:
        """
        Scan a single repository for agent configuration files.
        
        Args:
            repo_name: Name of repository subdirectory in clones_dir
        
        Returns:
            AgentFileDetectionResult with agents and files found
        
        Raises:
            ValueError: If repository directory not found
        """
        repo_path = self.clones_dir / repo_name
        
        if not repo_path.exists():
            raise ValueError(f"Repository not found: {repo_path}")
        
        if not repo_path.is_dir():
            raise ValueError(f"Not a directory: {repo_path}")
        
        result = AgentFileDetectionResult(repo_name=repo_name)
        
        # Scan for each agent type
        for agent_name, patterns in self.AGENT_FILE_PATTERNS.items():
            files_found = self._find_agent_files(repo_path, patterns)
            
            if files_found:
                result.agents_found[agent_name] = files_found
        
        return result
    
    def _find_agent_files(
        self,
        repo_path: Path,
        patterns: Dict[str, List]
    ) -> List[str]:
        """
        Find agent configuration files matching patterns.
        
        Args:
            repo_path: Path to repository
            patterns: Dict with 'file_names' and 'patterns' lists
        
        Returns:
            List of relative paths to found files
        """
        found_files = []
        file_names = patterns.get('file_names', [])
        regex_patterns = patterns.get('patterns', [])
        
        # Search by exact filename (case-insensitive)
        for file_name in file_names:
            for found_path in repo_path.rglob(file_name):
                rel_path = found_path.relative_to(repo_path)
                found_files.append(str(rel_path))
        
        # Search by regex pattern (case-insensitive)
        for pattern in regex_patterns:
            compiled = re.compile(pattern, re.IGNORECASE)
            for found_path in repo_path.rglob('*'):
                if compiled.search(found_path.name):
                    rel_path = found_path.relative_to(repo_path)
                    found_files.append(str(rel_path))
        
        # Remove duplicates while preserving order
        return list(dict.fromkeys(found_files))
    
    def scan_all(self, show_progress: bool = True) -> Dict[str, AgentFileDetectionResult]:
        """
        Scan all repositories in clones directory.
        
        Args:
            show_progress: Whether to log progress for each repository
        
        Returns:
            Dict mapping repo_name to AgentFileDetectionResult
            (Only includes repositories with agent files found)
        """
        results = {}
        repo_dirs = [d for d in self.clones_dir.iterdir() if d.is_dir()]
        total = len(repo_dirs)
        
        logger.info(f"Scanning {total} repositories for agent files")
        
        for idx, repo_dir in enumerate(repo_dirs, 1):
            repo_name = repo_dir.name
            
            try:
                result = self.scan_repository(repo_name)
                
                if result.total_agent_files > 0:
                    results[repo_name] = result
                    if show_progress:
                        agent_list = ', '.join(result.agents_found.keys())
                        logger.info(
                            f"[{idx}/{total}] {repo_name}: Found agents: {agent_list} "
                            f"({result.total_agent_files} files)"
                        )
                else:
                    if show_progress and idx % 50 == 0:
                        logger.info(f"[{idx}/{total}] Scanned {idx} repos, "
                                   f"{len(results)} with agent files so far")
            
            except Exception as e:
                logger.warning(f"Failed to scan {repo_name}: {e}")
        
        logger.info(f"Scan complete: Found agent files in {len(results)}/{total} repositories")
        
        return results
    
    def get_summary(self, scan_results: Dict[str, AgentFileDetectionResult]) -> Dict:
        """
        Generate summary statistics from scan results.
        
        Args:
            scan_results: Dict from scan_all()
        
        Returns:
            Dict with summary statistics
        """
        agent_counts = {}
        total_files = 0
        repo_with_multiple_agents = 0
        
        for result in scan_results.values():
            total_files += result.total_agent_files
            
            if len(result.agents_found) > 1:
                repo_with_multiple_agents += 1
            
            for agent_name in result.agents_found.keys():
                agent_counts[agent_name] = agent_counts.get(agent_name, 0) + 1
        
        return {
            'total_repositories_with_agents': len(scan_results),
            'total_agent_files_found': total_files,
            'repositories_with_multiple_agents': repo_with_multiple_agents,
            'agent_counts': agent_counts,
        }


def scan_for_agents(
    clones_dir: Path = None,
    show_progress: bool = True
) -> Tuple[Dict[str, AgentFileDetectionResult], Dict]:
    """
    Convenience function to scan all repositories for agent files.
    
    Args:
        clones_dir: Path to clones directory (defaults to ./clones)
        show_progress: Whether to log progress information
    
    Returns:
        Tuple of (results_dict, summary_dict)
    """
    scanner = AgentFileScanner(clones_dir)
    results = scanner.scan_all(show_progress=show_progress)
    summary = scanner.get_summary(results)
    
    return results, summary


# ============================================================================
# PHASE 1B: Commit Verification via Co-authored-by Trailers
# ============================================================================


@dataclass
class AgentCommitVerificationResult:
    """Result of verifying agent commits in a single repository."""
    repo_name: str
    agent_commits: Dict[str, str] = field(default_factory=dict)  # {commit_sha: agent_type}
    total_agent_commits: int = 0
    verification_method: str = 'co-authored-by'  # Method used for detection
    
    def __post_init__(self):
        """Calculate total agent commits found."""
        self.total_agent_commits = len(self.agent_commits)


class AgentCommitVerifier:
    """Phase 1B: Verify agent commits via Co-authored-by trailer parsing."""
    
    # Case-insensitive keywords for agent detection in commit messages
    AGENT_KEYWORDS = {
        'claude': ['claude'],
        'copilot': ['copilot'],
        'cursor': ['cursor'],
        'aider': ['aider'],
        'openhands': ['openhands'],
        'devin': ['devin'],
        'cline': ['cline'],
        'junie': ['junie'],
        'gemini': ['gemini'],
        'coderabbit': ['coderabbit'],
        'windsurf': ['windsurf'],
    }
    
    def __init__(self, clones_dir: Path = None):
        """
        Initialize the commit verifier.
        
        Args:
            clones_dir: Path to directory containing cloned repositories.
                       Defaults to current working directory + clones/.
        """
        if clones_dir is None:
            clones_dir = Path.cwd() / 'clones'
        
        self.clones_dir = Path(clones_dir)
    
    def verify_repository(
        self,
        repo_name: str,
        start_date: str = AGENT_DATASET_START_DATE
    ) -> AgentCommitVerificationResult:
        """
        Verify agent commits in a single repository.
        
        Args:
            repo_name: Repository directory name
            start_date: Filter commits after this date (ISO format YYYY-MM-DD)
        
        Returns:
            AgentCommitVerificationResult with commits found
        
        Raises:
            RuntimeError: If git operations fail
        """
        repo_path = self.clones_dir / repo_name
        
        if not repo_path.exists():
            raise RuntimeError(f"Repository not found: {repo_path}")
        
        if not repo_path.is_dir():
            raise RuntimeError(f"Not a directory: {repo_path}")
        
        agent_commits = {}
        
        try:
            # Get all commits with full metadata and message
            result = subprocess.run(
                [
                    'git',
                    'log',
                    '--all',
                    '--pretty=format:%H%n%ai%n%an%n%ae%n%B%n---END_COMMIT---',
                    '--',
                ],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )
            
            if result.returncode != 0 and not result.stdout:
                logger.warning(f"Git log failed for {repo_name}: {result.stderr[:200]}")
                return AgentCommitVerificationResult(repo_name=repo_name)
        
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Git log timeout for {repo_name}")
        except Exception as e:
            raise RuntimeError(f"Git operation failed for {repo_name}: {e}")
        
        # Parse commits
        commits = self._parse_commits(result.stdout)
        
        # Detect agents in commits after start_date
        for commit_data in commits:
            if commit_data['date'] >= start_date:
                agent_type = self._detect_agent_in_commit(commit_data)
                if agent_type:
                    agent_commits[commit_data['sha']] = agent_type
        
        result = AgentCommitVerificationResult(
            repo_name=repo_name,
            agent_commits=agent_commits
        )
        
        return result
    
    def verify_all(
        self,
        repo_names: List[str],
        start_date: str = AGENT_DATASET_START_DATE,
        show_progress: bool = True
    ) -> Dict[str, AgentCommitVerificationResult]:
        """
        Verify agents in multiple repositories.
        
        Args:
            repo_names: List of repository names to verify
            start_date: Filter commits after this date (ISO format)
            show_progress: Whether to log progress for each repository
        
        Returns:
            Dict mapping repo_name to AgentCommitVerificationResult
            (Only includes repositories with agent commits)
        """
        results = {}
        total = len(repo_names)
        
        logger.info(f"Verifying {total} repositories for agent commits")
        
        for idx, repo_name in enumerate(repo_names, 1):
            try:
                result = self.verify_repository(repo_name, start_date)
                
                if result.total_agent_commits > 0:
                    results[repo_name] = result
                    if show_progress:
                        logger.info(
                            f"[{idx}/{total}] {repo_name}: "
                            f"Found {result.total_agent_commits} agent commits"
                        )
                else:
                    if show_progress and idx % 20 == 0:
                        logger.info(f"[{idx}/{total}] Verified {idx} repos, "
                                   f"{len(results)} with agent commits so far")
            
            except Exception as e:
                logger.warning(f"Failed to verify {repo_name}: {e}")
        
        logger.info(f"Verification complete: {len(results)}/{total} repositories have agent commits")
        
        return results
    
    def _parse_commits(self, git_output: str) -> List[Dict]:
        """
        Parse git log output into structured commit data.
        
        Args:
            git_output: Raw output from git log
        
        Returns:
            List of dicts with keys: sha, date, author_name, author_email, message
        """
        commits = []
        
        if not git_output.strip():
            return commits
        
        for block in git_output.split('---END_COMMIT---'):
            lines = block.strip().split('\n', 4)
            
            if len(lines) < 5:
                continue
            
            try:
                sha = lines[0].strip()
                timestamp = lines[1].strip()  # Format: "2021-05-12 14:30:45 +0000"
                author_name = lines[2].strip()
                author_email = lines[3].strip()
                message = lines[4].strip() if len(lines) > 4 else ''
                
                # Extract ISO date
                date_iso = timestamp.split(' ')[0]
                
                commits.append({
                    'sha': sha,
                    'date': date_iso,
                    'author_name': author_name,
                    'author_email': author_email,
                    'message': message,
                })
            
            except (IndexError, ValueError) as e:
                logger.debug(f"Failed to parse commit block: {e}")
                continue
        
        return commits
    
    def _detect_agent_in_commit(self, commit_data: Dict) -> Optional[str]:
        """
        Detect agent type from commit metadata.
        
        Checks in order:
        1. Co-Authored-By trailer (highest confidence)
        2. Author name for agent keywords
        3. Commit message for agent keywords
        
        Args:
            commit_data: Dict with sha, date, author_name, author_email, message
        
        Returns:
            Agent type (claude|copilot|cursor|etc) or None if no match
        
        Note:
            Matching is case-insensitive. First match wins.
        """
        message = commit_data['message']
        author_name = commit_data['author_name']
        author_email = commit_data['author_email']
        
        # Check Co-Authored-By trailers (highest confidence)
        for match in re.finditer(
            r'co-authored-by:\s*([^<]+)<[^>]+>',
            message,
            re.IGNORECASE
        ):
            co_author = match.group(1).strip().lower()
            agent_type = self._match_agent_keywords(co_author)
            if agent_type:
                return agent_type
        
        # Check author name
        agent_type = self._match_agent_keywords(author_name.lower())
        if agent_type:
            return agent_type
        
        # Check author email
        agent_type = self._match_agent_keywords(author_email.lower())
        if agent_type:
            return agent_type
        
        # Check commit message
        agent_type = self._match_agent_keywords(message.lower())
        if agent_type:
            return agent_type
        
        return None
    
    def _match_agent_keywords(self, text: str) -> Optional[str]:
        """
        Match agent keywords in text.
        
        Args:
            text: Text to search (should already be lowercase)
        
        Returns:
            Agent type if matched, None otherwise
        """
        for agent_name, keywords in self.AGENT_KEYWORDS.items():
            for keyword in keywords:
                if keyword.lower() in text:
                    return agent_name
        
        return None
    
    def get_verification_summary(
        self,
        verification_results: Dict[str, AgentCommitVerificationResult]
    ) -> Dict:
        """
        Generate summary statistics from verification results.
        
        Args:
            verification_results: Dict from verify_all()
        
        Returns:
            Dict with summary statistics
        """
        agent_commit_counts = {}
        total_agent_commits = 0
        total_repos = len(verification_results)
        
        for result in verification_results.values():
            total_agent_commits += result.total_agent_commits
            
            for agent_type in result.agent_commits.values():
                agent_commit_counts[agent_type] = agent_commit_counts.get(agent_type, 0) + 1
        
        return {
            'total_repositories_verified': total_repos,
            'total_agent_commits_found': total_agent_commits,
            'agent_commit_counts': agent_commit_counts,
            'average_commits_per_repo': (
                total_agent_commits / total_repos if total_repos > 0 else 0
            ),
        }
