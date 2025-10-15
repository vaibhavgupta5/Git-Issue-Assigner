"""GitHub API client for bug report management."""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime
import requests
from github import Github, GithubException
from github.Issue import Issue
from github.Repository import Repository

from .base import BaseAPIClient, RateLimitConfig, CircuitBreakerConfig


@dataclass
class GitHubIssue:
    """GitHub issue data model."""
    id: int
    number: int
    title: str
    body: str
    state: str
    labels: List[str]
    assignees: List[str]
    created_at: datetime
    updated_at: datetime
    html_url: str
    repository: str
    author: str


@dataclass
class GitHubUser:
    """GitHub user data model."""
    id: int
    login: str
    name: Optional[str]
    email: Optional[str]
    avatar_url: str
    html_url: str


class GitHubAPIClient(BaseAPIClient):
    """GitHub API client with authentication and rate limiting."""
    
    def __init__(self, token: str, rate_limit_requests: int = 5000, rate_limit_window: int = 3600):
        """Initialize GitHub API client.
        
        Args:
            token: GitHub personal access token
            rate_limit_requests: Requests per window (GitHub allows 5000/hour)
            rate_limit_window: Rate limit window in seconds
        """
        self.token = token
        
        # GitHub API rate limits
        rate_limit_config = RateLimitConfig(
            requests_per_window=rate_limit_requests,
            window_seconds=rate_limit_window,
            burst_limit=100
        )
        
        # Circuit breaker for GitHub API
        circuit_breaker_config = CircuitBreakerConfig(
            failure_threshold=5,
            recovery_timeout=300,  # 5 minutes
            expected_exception=requests.RequestException
        )
        
        super().__init__(
            base_url="https://api.github.com",
            rate_limit_config=rate_limit_config,
            circuit_breaker_config=circuit_breaker_config,
            timeout=30
        )
        
        # Initialize PyGithub client for convenience methods
        self.github = Github(token)
        self.logger = logging.getLogger(__name__)
    
    def authenticate(self) -> Dict[str, str]:
        """Return GitHub authentication headers."""
        return {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "smart-bug-triage/1.0"
        }
    
    def test_connection(self) -> bool:
        """Test GitHub API connection and authentication."""
        try:
            response = self.get("/user")
            user_data = response.json()
            self.logger.info(f"Connected to GitHub as: {user_data.get('login')}")
            return True
        except Exception as e:
            self.logger.error(f"GitHub connection test failed: {e}")
            return False
    
    def get_repository(self, owner: str, repo: str) -> Repository:
        """Get repository object."""
        try:
            return self.github.get_repo(f"{owner}/{repo}")
        except GithubException as e:
            self.logger.error(f"Failed to get repository {owner}/{repo}: {e}")
            raise
    
    def get_issues(
        self,
        owner: str,
        repo: str,
        state: str = "open",
        labels: Optional[List[str]] = None,
        since: Optional[datetime] = None,
        per_page: int = 100
    ) -> List[GitHubIssue]:
        """Get issues from a repository.
        
        Args:
            owner: Repository owner
            repo: Repository name
            state: Issue state (open, closed, all)
            labels: Filter by labels
            since: Only issues updated after this date
            per_page: Number of issues per page
        """
        try:
            repository = self.get_repository(owner, repo)
            
            # Build parameters
            kwargs = {
                "state": state,
                "sort": "updated",
                "direction": "desc"
            }
            
            if labels:
                kwargs["labels"] = labels
            
            if since:
                kwargs["since"] = since
            
            # Get issues using PyGithub
            issues = repository.get_issues(**kwargs)
            
            # Convert to our data model
            result = []
            for issue in issues:
                # Skip pull requests (they appear as issues in GitHub API)
                if issue.pull_request:
                    continue
                
                github_issue = GitHubIssue(
                    id=issue.id,
                    number=issue.number,
                    title=issue.title,
                    body=issue.body or "",
                    state=issue.state,
                    labels=[label.name for label in issue.labels],
                    assignees=[assignee.login for assignee in issue.assignees],
                    created_at=issue.created_at,
                    updated_at=issue.updated_at,
                    html_url=issue.html_url,
                    repository=f"{owner}/{repo}",
                    author=issue.user.login
                )
                result.append(github_issue)
                
                # Limit results to avoid memory issues
                if len(result) >= per_page:
                    break
            
            self.logger.info(f"Retrieved {len(result)} issues from {owner}/{repo}")
            return result
            
        except GithubException as e:
            self.logger.error(f"Failed to get issues from {owner}/{repo}: {e}")
            raise
    
    def get_issue(self, owner: str, repo: str, issue_number: int) -> GitHubIssue:
        """Get a specific issue."""
        try:
            repository = self.get_repository(owner, repo)
            issue = repository.get_issue(issue_number)
            
            return GitHubIssue(
                id=issue.id,
                number=issue.number,
                title=issue.title,
                body=issue.body or "",
                state=issue.state,
                labels=[label.name for label in issue.labels],
                assignees=[assignee.login for assignee in issue.assignees],
                created_at=issue.created_at,
                updated_at=issue.updated_at,
                html_url=issue.html_url,
                repository=f"{owner}/{repo}",
                author=issue.user.login
            )
            
        except GithubException as e:
            self.logger.error(f"Failed to get issue {owner}/{repo}#{issue_number}: {e}")
            raise
    
    def assign_issue(self, owner: str, repo: str, issue_number: int, assignees: List[str]) -> bool:
        """Assign issue to developers.
        
        Args:
            owner: Repository owner
            repo: Repository name
            issue_number: Issue number
            assignees: List of GitHub usernames to assign
        """
        try:
            repository = self.get_repository(owner, repo)
            issue = repository.get_issue(issue_number)
            
            # Add assignees
            issue.add_to_assignees(*assignees)
            
            self.logger.info(f"Assigned issue {owner}/{repo}#{issue_number} to {assignees}")
            return True
            
        except GithubException as e:
            self.logger.error(f"Failed to assign issue {owner}/{repo}#{issue_number}: {e}")
            return False
    
    def add_labels(self, owner: str, repo: str, issue_number: int, labels: List[str]) -> bool:
        """Add labels to an issue."""
        try:
            repository = self.get_repository(owner, repo)
            issue = repository.get_issue(issue_number)
            
            # Add labels
            issue.add_to_labels(*labels)
            
            self.logger.info(f"Added labels {labels} to issue {owner}/{repo}#{issue_number}")
            return True
            
        except GithubException as e:
            self.logger.error(f"Failed to add labels to issue {owner}/{repo}#{issue_number}: {e}")
            return False
    
    def add_comment(self, owner: str, repo: str, issue_number: int, comment: str) -> bool:
        """Add comment to an issue."""
        try:
            repository = self.get_repository(owner, repo)
            issue = repository.get_issue(issue_number)
            
            # Add comment
            issue.create_comment(comment)
            
            self.logger.info(f"Added comment to issue {owner}/{repo}#{issue_number}")
            return True
            
        except GithubException as e:
            self.logger.error(f"Failed to add comment to issue {owner}/{repo}#{issue_number}: {e}")
            return False
    
    def get_repository_contributors(self, owner: str, repo: str) -> List[GitHubUser]:
        """Get repository contributors."""
        try:
            repository = self.get_repository(owner, repo)
            contributors = repository.get_contributors()
            
            result = []
            for contributor in contributors:
                github_user = GitHubUser(
                    id=contributor.id,
                    login=contributor.login,
                    name=contributor.name,
                    email=contributor.email,
                    avatar_url=contributor.avatar_url,
                    html_url=contributor.html_url
                )
                result.append(github_user)
            
            self.logger.info(f"Retrieved {len(result)} contributors from {owner}/{repo}")
            return result
            
        except GithubException as e:
            self.logger.error(f"Failed to get contributors from {owner}/{repo}: {e}")
            raise
    
    def get_user_assigned_issues(self, username: str, state: str = "open") -> List[GitHubIssue]:
        """Get issues assigned to a specific user across all repositories."""
        try:
            # Use GitHub search API to find assigned issues
            query = f"assignee:{username} is:issue state:{state}"
            
            response = self.get("/search/issues", params={
                "q": query,
                "sort": "updated",
                "order": "desc",
                "per_page": 100
            })
            
            search_results = response.json()
            
            result = []
            for item in search_results.get("items", []):
                # Extract repository info from URL
                repo_url = item["repository_url"]
                repo_parts = repo_url.split("/")
                owner = repo_parts[-2]
                repo = repo_parts[-1]
                
                github_issue = GitHubIssue(
                    id=item["id"],
                    number=item["number"],
                    title=item["title"],
                    body=item.get("body", ""),
                    state=item["state"],
                    labels=[label["name"] for label in item.get("labels", [])],
                    assignees=[assignee["login"] for assignee in item.get("assignees", [])],
                    created_at=datetime.fromisoformat(item["created_at"].replace("Z", "+00:00")),
                    updated_at=datetime.fromisoformat(item["updated_at"].replace("Z", "+00:00")),
                    html_url=item["html_url"],
                    repository=f"{owner}/{repo}",
                    author=item["user"]["login"]
                )
                result.append(github_issue)
            
            self.logger.info(f"Retrieved {len(result)} assigned issues for user {username}")
            return result
            
        except Exception as e:
            self.logger.error(f"Failed to get assigned issues for user {username}: {e}")
            raise
    
    def create_webhook(
        self,
        owner: str,
        repo: str,
        webhook_url: str,
        events: List[str] = None,
        secret: Optional[str] = None
    ) -> bool:
        """Create a webhook for the repository.
        
        Args:
            owner: Repository owner
            repo: Repository name
            webhook_url: URL to send webhook events to
            events: List of events to subscribe to
            secret: Optional webhook secret for verification
        """
        if events is None:
            events = ["issues", "issue_comment"]
        
        try:
            repository = self.get_repository(owner, repo)
            
            config = {
                "url": webhook_url,
                "content_type": "json"
            }
            
            if secret:
                config["secret"] = secret
            
            # Create webhook
            webhook = repository.create_hook(
                name="web",
                config=config,
                events=events,
                active=True
            )
            
            self.logger.info(f"Created webhook for {owner}/{repo} -> {webhook_url}")
            return True
            
        except GithubException as e:
            self.logger.error(f"Failed to create webhook for {owner}/{repo}: {e}")
            return False
    
    def get_rate_limit_status(self) -> Dict[str, Any]:
        """Get current rate limit status."""
        try:
            rate_limit = self.github.get_rate_limit()
            
            return {
                "core": {
                    "limit": rate_limit.core.limit,
                    "remaining": rate_limit.core.remaining,
                    "reset": rate_limit.core.reset,
                    "used": rate_limit.core.used
                },
                "search": {
                    "limit": rate_limit.search.limit,
                    "remaining": rate_limit.search.remaining,
                    "reset": rate_limit.search.reset,
                    "used": rate_limit.search.used
                }
            }
            
        except GithubException as e:
            self.logger.error(f"Failed to get rate limit status: {e}")
            return {}