"""
GitHub client for recent code changes context.

This module provides integration with GitHub API for retrieving
recent commits and changes that might be related to incidents.
"""

import asyncio
from typing import Any, Dict, List, Optional
from github import Github
from github.GithubException import GithubException
from models.context import ContextSource


class GitHubClient:
    """Client for interacting with GitHub API."""
    
    def __init__(
        self, 
        token: Optional[str] = None,
        repo_owner: Optional[str] = None,
        repo_name: Optional[str] = None
    ):
        self.token = token
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.github = None
        
        if token:
            self.github = Github(token)
    
    async def get_recent_commits(
        self, 
        service_name: str, 
        hours_back: int = 24,
        max_commits: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get recent commits that might be related to a service incident.
        
        Args:
            service_name: Name of the service
            hours_back: How many hours back to look for commits
            max_commits: Maximum number of commits to return
            
        Returns:
            List of recent commits
        """
        if not self.github or not self.repo_owner or not self.repo_name:
            print("GitHub: No GitHub configuration available")
            return []
        
        try:
            # Get repository
            repo = self.github.get_repo(f"{self.repo_owner}/{self.repo_name}")
            
            # Calculate time range
            import datetime
            since_time = datetime.datetime.now() - datetime.timedelta(hours=hours_back)
            
            # Get commits from the main branch
            commits = repo.get_commits(since=since_time)
            
            recent_commits = []
            commit_count = 0
            
            for commit in commits:
                if commit_count >= max_commits:
                    break
                
                # Check if commit is related to the service
                if self._is_commit_related_to_service(commit, service_name):
                    commit_data = {
                        'sha': commit.sha,
                        'message': commit.commit.message,
                        'author': commit.commit.author.name if commit.commit.author else 'Unknown',
                        'timestamp': commit.commit.author.date.isoformat() if commit.commit.author else None,
                        'url': commit.html_url,
                        'files_changed': len(commit.files) if commit.files else 0,
                        'service_relevance': self._calculate_service_relevance(commit, service_name)
                    }
                    recent_commits.append(commit_data)
                    commit_count += 1
            
            print(f"GitHub: Retrieved {len(recent_commits)} recent commits for service {service_name}")
            return recent_commits
            
        except GithubException as e:
            print(f"GitHub: API error fetching commits: {e}")
            return []
        except Exception as e:
            print(f"GitHub: Error fetching commits for {service_name}: {e}")
            return []
    
    def _is_commit_related_to_service(self, commit, service_name: str) -> bool:
        """Check if a commit is related to a specific service."""
        try:
            # Check commit message
            message = commit.commit.message.lower()
            service_lower = service_name.lower()
            
            # Check if service name appears in commit message
            if service_lower in message:
                return True
            
            # Check if any files changed are related to the service
            if commit.files:
                for file in commit.files:
                    filename = file.filename.lower()
                    if service_lower in filename:
                        return True
            
            return False
            
        except Exception:
            return False
    
    def _calculate_service_relevance(self, commit, service_name: str) -> float:
        """Calculate how relevant a commit is to a service (0.0 to 1.0)."""
        try:
            relevance = 0.0
            service_lower = service_name.lower()
            
            # Check commit message relevance
            message = commit.commit.message.lower()
            if service_lower in message:
                relevance += 0.5
            
            # Check file path relevance
            if commit.files:
                service_files = 0
                total_files = len(commit.files)
                
                for file in commit.files:
                    if service_lower in file.filename.lower():
                        service_files += 1
                
                if total_files > 0:
                    relevance += 0.5 * (service_files / total_files)
            
            return min(relevance, 1.0)
            
        except Exception:
            return 0.0
    
    async def get_service_deployment_history(
        self, 
        service_name: str, 
        days_back: int = 7
    ) -> List[Dict[str, Any]]:
        """
        Get deployment-related commits for a service.
        
        Args:
            service_name: Name of the service
            days_back: How many days back to look
            
        Returns:
            List of deployment-related commits
        """
        if not self.github or not self.repo_owner or not self.repo_name:
            return []
        
        try:
            repo = self.github.get_repo(f"{self.repo_owner}/{self.repo_name}")
            
            import datetime
            since_time = datetime.datetime.now() - datetime.timedelta(days=days_back)
            
            # Look for deployment-related commits
            deployment_keywords = ['deploy', 'release', 'version', 'config', 'helm', 'k8s', 'kubernetes']
            
            commits = repo.get_commits(since=since_time)
            deployment_commits = []
            
            for commit in commits:
                message = commit.commit.message.lower()
                
                # Check if commit is deployment-related
                if any(keyword in message for keyword in deployment_keywords):
                    if self._is_commit_related_to_service(commit, service_name):
                        commit_data = {
                            'sha': commit.sha,
                            'message': commit.commit.message,
                            'author': commit.commit.author.name if commit.commit.author else 'Unknown',
                            'timestamp': commit.commit.author.date.isoformat() if commit.commit.author else None,
                            'url': commit.html_url,
                            'deployment_type': self._identify_deployment_type(commit)
                        }
                        deployment_commits.append(commit_data)
            
            print(f"GitHub: Found {len(deployment_commits)} deployment commits for {service_name}")
            return deployment_commits
            
        except Exception as e:
            print(f"GitHub: Error fetching deployment history for {service_name}: {e}")
            return []
    
    def _identify_deployment_type(self, commit) -> str:
        """Identify the type of deployment from commit message."""
        message = commit.commit.message.lower()
        
        if 'helm' in message or 'chart' in message:
            return 'helm'
        elif 'k8s' in message or 'kubernetes' in message:
            return 'kubernetes'
        elif 'docker' in message or 'container' in message:
            return 'container'
        elif 'config' in message or 'env' in message:
            return 'configuration'
        else:
            return 'general'
