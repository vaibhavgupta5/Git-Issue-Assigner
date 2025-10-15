"""Jira API client for issue management."""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime
import requests
from jira import JIRA, JIRAError

from .base import BaseAPIClient, RateLimitConfig, CircuitBreakerConfig


@dataclass
class JiraIssue:
    """Jira issue data model."""
    id: str
    key: str
    summary: str
    description: str
    status: str
    priority: str
    issue_type: str
    labels: List[str]
    assignee: Optional[str]
    reporter: str
    created: datetime
    updated: datetime
    project_key: str
    url: str


@dataclass
class JiraUser:
    """Jira user data model."""
    account_id: str
    display_name: str
    email_address: Optional[str]
    active: bool


class JiraAPIClient(BaseAPIClient):
    """Jira API client with authentication and rate limiting."""
    
    def __init__(
        self,
        server_url: str,
        username: str,
        api_token: str,
        rate_limit_requests: int = 100,
        rate_limit_window: int = 3600
    ):
        """Initialize Jira API client.
        
        Args:
            server_url: Jira server URL (e.g., https://company.atlassian.net)
            username: Jira username/email
            api_token: Jira API token
            rate_limit_requests: Requests per window
            rate_limit_window: Rate limit window in seconds
        """
        self.server_url = server_url.rstrip('/')
        self.username = username
        self.api_token = api_token
        
        # Jira API rate limits (conservative defaults)
        rate_limit_config = RateLimitConfig(
            requests_per_window=rate_limit_requests,
            window_seconds=rate_limit_window,
            burst_limit=20
        )
        
        # Circuit breaker for Jira API
        circuit_breaker_config = CircuitBreakerConfig(
            failure_threshold=3,
            recovery_timeout=180,  # 3 minutes
            expected_exception=requests.RequestException
        )
        
        super().__init__(
            base_url=f"{self.server_url}/rest/api/3",
            rate_limit_config=rate_limit_config,
            circuit_breaker_config=circuit_breaker_config,
            timeout=30
        )
        
        # Initialize JIRA client for convenience methods
        try:
            self.jira = JIRA(
                server=self.server_url,
                basic_auth=(username, api_token),
                options={'verify': True}
            )
        except Exception as e:
            self.logger.error(f"Failed to initialize Jira client: {e}")
            self.jira = None
        
        self.logger = logging.getLogger(__name__)
    
    def authenticate(self) -> Dict[str, str]:
        """Return Jira authentication headers."""
        import base64
        
        credentials = f"{self.username}:{self.api_token}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        return {
            "Authorization": f"Basic {encoded_credentials}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
    
    def test_connection(self) -> bool:
        """Test Jira API connection and authentication."""
        try:
            if self.jira:
                user = self.jira.current_user()
                self.logger.info(f"Connected to Jira as: {user}")
                return True
            else:
                # Fallback to direct API call
                response = self.get("/myself")
                user_data = response.json()
                self.logger.info(f"Connected to Jira as: {user_data.get('displayName')}")
                return True
        except Exception as e:
            self.logger.error(f"Jira connection test failed: {e}")
            return False
    
    def get_projects(self) -> List[Dict[str, Any]]:
        """Get all accessible projects."""
        try:
            if self.jira:
                projects = self.jira.projects()
                return [{"key": p.key, "name": p.name, "id": p.id} for p in projects]
            else:
                response = self.get("/project")
                return response.json()
        except Exception as e:
            self.logger.error(f"Failed to get projects: {e}")
            return []
    
    def get_issues(
        self,
        project_key: str,
        jql_filter: Optional[str] = None,
        max_results: int = 100
    ) -> List[JiraIssue]:
        """Get issues from a project.
        
        Args:
            project_key: Jira project key
            jql_filter: Additional JQL filter
            max_results: Maximum number of results
        """
        try:
            # Build JQL query
            jql = f"project = {project_key}"
            if jql_filter:
                jql += f" AND {jql_filter}"
            
            jql += " ORDER BY updated DESC"
            
            if self.jira:
                issues = self.jira.search_issues(
                    jql,
                    maxResults=max_results,
                    expand='changelog'
                )
                
                result = []
                for issue in issues:
                    jira_issue = self._convert_jira_issue(issue)
                    result.append(jira_issue)
                
                self.logger.info(f"Retrieved {len(result)} issues from project {project_key}")
                return result
            else:
                # Fallback to direct API call
                response = self.post("/search", json_data={
                    "jql": jql,
                    "maxResults": max_results,
                    "fields": ["*all"]
                })
                
                search_results = response.json()
                result = []
                
                for issue_data in search_results.get("issues", []):
                    jira_issue = self._convert_api_issue(issue_data)
                    result.append(jira_issue)
                
                self.logger.info(f"Retrieved {len(result)} issues from project {project_key}")
                return result
                
        except Exception as e:
            self.logger.error(f"Failed to get issues from project {project_key}: {e}")
            raise
    
    def get_issue(self, issue_key: str) -> JiraIssue:
        """Get a specific issue."""
        try:
            if self.jira:
                issue = self.jira.issue(issue_key)
                return self._convert_jira_issue(issue)
            else:
                response = self.get(f"/issue/{issue_key}")
                issue_data = response.json()
                return self._convert_api_issue(issue_data)
                
        except Exception as e:
            self.logger.error(f"Failed to get issue {issue_key}: {e}")
            raise
    
    def assign_issue(self, issue_key: str, assignee_account_id: str) -> bool:
        """Assign issue to a user.
        
        Args:
            issue_key: Jira issue key
            assignee_account_id: Account ID of the assignee
        """
        try:
            if self.jira:
                issue = self.jira.issue(issue_key)
                issue.update(assignee={'accountId': assignee_account_id})
            else:
                self.put(f"/issue/{issue_key}/assignee", json_data={
                    "accountId": assignee_account_id
                })
            
            self.logger.info(f"Assigned issue {issue_key} to {assignee_account_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to assign issue {issue_key}: {e}")
            return False
    
    def add_labels(self, issue_key: str, labels: List[str]) -> bool:
        """Add labels to an issue."""
        try:
            if self.jira:
                issue = self.jira.issue(issue_key)
                current_labels = [label for label in issue.fields.labels]
                new_labels = list(set(current_labels + labels))
                issue.update(labels=new_labels)
            else:
                # Get current labels first
                response = self.get(f"/issue/{issue_key}")
                issue_data = response.json()
                current_labels = issue_data["fields"].get("labels", [])
                new_labels = list(set(current_labels + labels))
                
                self.put(f"/issue/{issue_key}", json_data={
                    "fields": {"labels": new_labels}
                })
            
            self.logger.info(f"Added labels {labels} to issue {issue_key}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to add labels to issue {issue_key}: {e}")
            return False
    
    def add_comment(self, issue_key: str, comment: str) -> bool:
        """Add comment to an issue."""
        try:
            if self.jira:
                self.jira.add_comment(issue_key, comment)
            else:
                self.post(f"/issue/{issue_key}/comment", json_data={
                    "body": {
                        "type": "doc",
                        "version": 1,
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": comment
                                    }
                                ]
                            }
                        ]
                    }
                })
            
            self.logger.info(f"Added comment to issue {issue_key}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to add comment to issue {issue_key}: {e}")
            return False
    
    def get_user_assigned_issues(self, account_id: str) -> List[JiraIssue]:
        """Get issues assigned to a specific user."""
        try:
            jql = f"assignee = {account_id} AND status != Done ORDER BY updated DESC"
            
            if self.jira:
                issues = self.jira.search_issues(jql, maxResults=100)
                result = []
                for issue in issues:
                    jira_issue = self._convert_jira_issue(issue)
                    result.append(jira_issue)
            else:
                response = self.post("/search", json_data={
                    "jql": jql,
                    "maxResults": 100,
                    "fields": ["*all"]
                })
                
                search_results = response.json()
                result = []
                
                for issue_data in search_results.get("issues", []):
                    jira_issue = self._convert_api_issue(issue_data)
                    result.append(jira_issue)
            
            self.logger.info(f"Retrieved {len(result)} assigned issues for user {account_id}")
            return result
            
        except Exception as e:
            self.logger.error(f"Failed to get assigned issues for user {account_id}: {e}")
            raise
    
    def search_users(self, query: str, max_results: int = 50) -> List[JiraUser]:
        """Search for users."""
        try:
            if self.jira:
                users = self.jira.search_users(query, maxResults=max_results)
                result = []
                for user in users:
                    jira_user = JiraUser(
                        account_id=user.accountId,
                        display_name=user.displayName,
                        email_address=getattr(user, 'emailAddress', None),
                        active=user.active
                    )
                    result.append(jira_user)
            else:
                response = self.get("/user/search", params={
                    "query": query,
                    "maxResults": max_results
                })
                
                users_data = response.json()
                result = []
                
                for user_data in users_data:
                    jira_user = JiraUser(
                        account_id=user_data["accountId"],
                        display_name=user_data["displayName"],
                        email_address=user_data.get("emailAddress"),
                        active=user_data["active"]
                    )
                    result.append(jira_user)
            
            self.logger.info(f"Found {len(result)} users matching query: {query}")
            return result
            
        except Exception as e:
            self.logger.error(f"Failed to search users with query {query}: {e}")
            return []
    
    def _convert_jira_issue(self, issue) -> JiraIssue:
        """Convert JIRA library issue to our data model."""
        return JiraIssue(
            id=issue.id,
            key=issue.key,
            summary=issue.fields.summary,
            description=getattr(issue.fields, 'description', '') or '',
            status=issue.fields.status.name,
            priority=issue.fields.priority.name if issue.fields.priority else 'None',
            issue_type=issue.fields.issuetype.name,
            labels=list(issue.fields.labels) if issue.fields.labels else [],
            assignee=issue.fields.assignee.accountId if issue.fields.assignee else None,
            reporter=issue.fields.reporter.accountId if issue.fields.reporter else '',
            created=datetime.fromisoformat(issue.fields.created.replace('Z', '+00:00')),
            updated=datetime.fromisoformat(issue.fields.updated.replace('Z', '+00:00')),
            project_key=issue.fields.project.key,
            url=f"{self.server_url}/browse/{issue.key}"
        )
    
    def _convert_api_issue(self, issue_data: Dict[str, Any]) -> JiraIssue:
        """Convert API response issue to our data model."""
        fields = issue_data["fields"]
        
        return JiraIssue(
            id=issue_data["id"],
            key=issue_data["key"],
            summary=fields["summary"],
            description=fields.get("description", "") or "",
            status=fields["status"]["name"],
            priority=fields["priority"]["name"] if fields.get("priority") else "None",
            issue_type=fields["issuetype"]["name"],
            labels=fields.get("labels", []),
            assignee=fields["assignee"]["accountId"] if fields.get("assignee") else None,
            reporter=fields["reporter"]["accountId"] if fields.get("reporter") else "",
            created=datetime.fromisoformat(fields["created"].replace('Z', '+00:00')),
            updated=datetime.fromisoformat(fields["updated"].replace('Z', '+00:00')),
            project_key=fields["project"]["key"],
            url=f"{self.server_url}/browse/{issue_data['key']}"
        )