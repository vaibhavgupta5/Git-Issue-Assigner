"""Listener Agent for monitoring bug tracking systems."""

import asyncio
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Set
from dataclasses import dataclass

from .base import Agent
from ..api.github_client import GitHubAPIClient, GitHubIssue
from ..api.jira_client import JiraAPIClient, JiraIssue
from ..api.webhook_receiver import WebhookReceiver, WebhookEvent
from ..message_queue.connection import MessageQueueConnection
from ..message_queue.publisher import MessagePublisher
from ..models.common import BugReport
from ..config.settings import SystemConfig


@dataclass
class MonitoredRepository:
    """Configuration for a monitored repository."""
    platform: str  # github, jira
    owner: str
    repo: str
    last_check: Optional[datetime] = None
    webhook_configured: bool = False


class ListenerAgent(Agent):
    """Agent that monitors bug tracking systems for new bug reports."""
    
    def __init__(self, agent_id: str, config: SystemConfig):
        """Initialize Listener Agent.
        
        Args:
            agent_id: Unique identifier for this agent instance
            config: System configuration
        """
        super().__init__(agent_id, config.agents.__dict__)
        self.system_config = config
        
        # API clients
        self.github_client: Optional[GitHubAPIClient] = None
        self.jira_client: Optional[JiraAPIClient] = None
        
        # Message queue components
        self.mq_connection: Optional[MessageQueueConnection] = None
        self.publisher: Optional[MessagePublisher] = None
        
        # Webhook receiver
        self.webhook_receiver: Optional[WebhookReceiver] = None
        self.webhook_thread: Optional[threading.Thread] = None
        
        # Monitoring state
        self.monitored_repos: List[MonitoredRepository] = []
        self.processed_bugs: Set[str] = set()  # Track processed bug IDs
        self.is_running = False
        self.polling_thread: Optional[threading.Thread] = None
        
        # Statistics
        self.stats = {
            'bugs_detected': 0,
            'bugs_published': 0,
            'webhook_events_received': 0,
            'polling_cycles': 0,
            'last_activity': None,
            'errors': 0
        }
    
    def start(self) -> bool:
        """Start the Listener Agent."""
        try:
            self.log_info("Starting Listener Agent...")
            
            # Initialize API clients
            if not self._initialize_api_clients():
                return False
            
            # Initialize message queue
            if not self._initialize_message_queue():
                return False
            
            # Set up webhook receiver
            if not self._setup_webhook_receiver():
                return False
            
            # Load monitored repositories configuration
            self._load_monitored_repositories()
            
            # Set up webhooks for repositories
            self._setup_repository_webhooks()
            
            # Start webhook receiver in separate thread
            self._start_webhook_receiver()
            
            # Start polling mechanism
            self._start_polling()
            
            self.status = "running"
            self.is_running = True
            self.log_info("Listener Agent started successfully")
            return True
            
        except Exception as e:
            self.log_error("Failed to start Listener Agent", e)
            self.status = "error"
            return False
    
    def stop(self) -> bool:
        """Stop the Listener Agent gracefully."""
        try:
            self.log_info("Stopping Listener Agent...")
            self.is_running = False
            
            # Stop polling thread
            if self.polling_thread and self.polling_thread.is_alive():
                self.polling_thread.join(timeout=10)
            
            # Stop webhook receiver
            if self.webhook_thread and self.webhook_thread.is_alive():
                self.webhook_thread.join(timeout=10)
            
            # Close message queue connection
            if self.mq_connection:
                self.mq_connection.disconnect()
            
            self.status = "stopped"
            self.log_info("Listener Agent stopped successfully")
            return True
            
        except Exception as e:
            self.log_error("Error stopping Listener Agent", e)
            return False
    
    def get_status(self) -> Dict[str, Any]:
        """Get current agent status and statistics."""
        return {
            'agent_id': self.agent_id,
            'status': self.status,
            'is_running': self.is_running,
            'last_heartbeat': self.last_heartbeat.isoformat(),
            'monitored_repositories': len(self.monitored_repos),
            'webhook_configured_repos': sum(1 for repo in self.monitored_repos if repo.webhook_configured),
            'statistics': self.stats.copy(),
            'api_clients': {
                'github': self.github_client is not None,
                'jira': self.jira_client is not None
            },
            'message_queue_connected': self.mq_connection.is_connected() if self.mq_connection else False
        }
    
    def _initialize_api_clients(self) -> bool:
        """Initialize API clients for external services."""
        try:
            # Initialize GitHub client
            if self.system_config.api.github_token:
                self.github_client = GitHubAPIClient(
                    token=self.system_config.api.github_token,
                    rate_limit_requests=self.system_config.api.rate_limit_requests,
                    rate_limit_window=self.system_config.api.rate_limit_window
                )
                
                if not self.github_client.test_connection():
                    self.log_error("GitHub API connection test failed")
                    return False
                
                self.log_info("GitHub API client initialized successfully")
            
            # Initialize Jira client
            if self.system_config.api.jira_url and self.system_config.api.jira_token:
                self.jira_client = JiraAPIClient(
                    server_url=self.system_config.api.jira_url,
                    username=self.system_config.api.jira_username,
                    api_token=self.system_config.api.jira_token
                )
                
                if not self.jira_client.test_connection():
                    self.log_error("Jira API connection test failed")
                    return False
                
                self.log_info("Jira API client initialized successfully")
            
            return True
            
        except Exception as e:
            self.log_error("Failed to initialize API clients", e)
            return False
    
    def _initialize_message_queue(self) -> bool:
        """Initialize message queue connection and publisher."""
        try:
            self.mq_connection = MessageQueueConnection(self.system_config.message_queue)
            
            if not self.mq_connection.connect():
                self.log_error("Failed to connect to message queue")
                return False
            
            self.publisher = MessagePublisher(self.mq_connection)
            self.log_info("Message queue initialized successfully")
            return True
            
        except Exception as e:
            self.log_error("Failed to initialize message queue", e)
            return False
    
    def _setup_webhook_receiver(self) -> bool:
        """Set up webhook receiver for real-time notifications."""
        try:
            # Get webhook secrets from environment or config
            github_secret = getattr(self.system_config.api, 'github_webhook_secret', None)
            jira_secret = getattr(self.system_config.api, 'jira_webhook_secret', None)
            
            self.webhook_receiver = WebhookReceiver(
                github_secret=github_secret,
                jira_secret=jira_secret,
                port=getattr(self.system_config.api, 'webhook_port', 8080),
                host=getattr(self.system_config.api, 'webhook_host', '0.0.0.0')
            )
            
            # Register event handlers
            self.webhook_receiver.register_handler(
                "github.issues.opened",
                self._handle_github_issue_webhook
            )
            self.webhook_receiver.register_handler(
                "github.issues.reopened",
                self._handle_github_issue_webhook
            )
            self.webhook_receiver.register_handler(
                "jira.issue_created",
                self._handle_jira_issue_webhook
            )
            
            self.log_info("Webhook receiver configured successfully")
            return True
            
        except Exception as e:
            self.log_error("Failed to setup webhook receiver", e)
            return False
    
    def _load_monitored_repositories(self):
        """Load configuration for repositories to monitor."""
        # This would typically load from configuration file or database
        # For now, we'll use a simple configuration approach
        
        # Example configuration - in production this would come from config
        default_repos = [
            MonitoredRepository(
                platform="github",
                owner="your-org",
                repo="your-repo"
            )
        ]
        
        # Load from config if available
        if hasattr(self.system_config, 'monitored_repositories'):
            for repo_config in self.system_config.monitored_repositories:
                self.monitored_repos.append(MonitoredRepository(**repo_config))
        else:
            self.monitored_repos = default_repos
        
        self.log_info(f"Loaded {len(self.monitored_repos)} repositories to monitor")
    
    def _setup_repository_webhooks(self):
        """Set up webhooks for monitored repositories."""
        if not self.github_client:
            return
        
        webhook_url = getattr(self.system_config.api, 'webhook_base_url', 'http://localhost:8080')
        
        for repo in self.monitored_repos:
            if repo.platform == "github":
                try:
                    success = self.github_client.create_webhook(
                        owner=repo.owner,
                        repo=repo.repo,
                        webhook_url=f"{webhook_url}/webhooks/github",
                        events=["issues", "issue_comment"]
                    )
                    repo.webhook_configured = success
                    
                    if success:
                        self.log_info(f"Webhook configured for {repo.owner}/{repo.repo}")
                    else:
                        self.log_error(f"Failed to configure webhook for {repo.owner}/{repo.repo}")
                        
                except Exception as e:
                    self.log_error(f"Error setting up webhook for {repo.owner}/{repo.repo}", e)
    
    def _start_webhook_receiver(self):
        """Start webhook receiver in separate thread."""
        if not self.webhook_receiver:
            return
        
        def run_webhook_server():
            try:
                self.webhook_receiver.start()
            except Exception as e:
                self.log_error("Webhook receiver error", e)
        
        self.webhook_thread = threading.Thread(
            target=run_webhook_server,
            name=f"WebhookReceiver-{self.agent_id}",
            daemon=True
        )
        self.webhook_thread.start()
        self.log_info("Webhook receiver started")
    
    def _start_polling(self):
        """Start polling mechanism for fallback bug detection."""
        def polling_loop():
            while self.is_running:
                try:
                    self._poll_for_new_bugs()
                    self.stats['polling_cycles'] += 1
                    self.heartbeat()
                    
                    # Sleep for configured interval
                    poll_interval = self.system_config.agents.listener_poll_interval
                    time.sleep(poll_interval)
                    
                except Exception as e:
                    self.log_error("Error in polling loop", e)
                    self.stats['errors'] += 1
                    time.sleep(30)  # Brief pause on error
        
        self.polling_thread = threading.Thread(
            target=polling_loop,
            name=f"PollingLoop-{self.agent_id}",
            daemon=True
        )
        self.polling_thread.start()
        self.log_info("Polling mechanism started")
    
    def _poll_for_new_bugs(self):
        """Poll repositories for new bug reports."""
        for repo in self.monitored_repos:
            try:
                if repo.platform == "github" and self.github_client:
                    self._poll_github_repository(repo)
                elif repo.platform == "jira" and self.jira_client:
                    self._poll_jira_project(repo)
                    
            except Exception as e:
                self.log_error(f"Error polling {repo.platform} {repo.owner}/{repo.repo}", e)
                self.stats['errors'] += 1
    
    def _poll_github_repository(self, repo: MonitoredRepository):
        """Poll a GitHub repository for new issues."""
        try:
            # Determine since timestamp
            since = repo.last_check or (datetime.utcnow() - timedelta(hours=1))
            
            # Get issues since last check
            issues = self.github_client.get_issues(
                owner=repo.owner,
                repo=repo.repo,
                state="open",
                since=since,
                per_page=50
            )
            
            # Process each issue
            for issue in issues:
                bug_report = self._convert_github_issue_to_bug_report(issue, repo)
                if bug_report and self._should_process_bug(bug_report):
                    self._process_new_bug(bug_report)
            
            # Update last check timestamp
            repo.last_check = datetime.utcnow()
            
        except Exception as e:
            self.log_error(f"Error polling GitHub repository {repo.owner}/{repo.repo}", e)
            raise
    
    def _poll_jira_project(self, repo: MonitoredRepository):
        """Poll a Jira project for new issues."""
        try:
            # Determine JQL filter for recent issues
            since = repo.last_check or (datetime.utcnow() - timedelta(hours=1))
            since_str = since.strftime('%Y-%m-%d %H:%M')
            
            # Build JQL filter for bug-type issues created/updated since last check
            jql_filter = f"updated >= '{since_str}' AND type in (Bug, Defect, 'Bug Report')"
            
            # Get issues from project
            issues = self.jira_client.get_issues(
                project_key=repo.repo,  # In Jira context, repo is the project key
                jql_filter=jql_filter,
                max_results=50
            )
            
            # Process each issue
            for issue in issues:
                bug_report = self._convert_jira_issue_to_bug_report(issue, repo)
                if bug_report and self._should_process_bug(bug_report):
                    self._process_new_bug(bug_report)
            
            # Update last check timestamp
            repo.last_check = datetime.utcnow()
            
        except Exception as e:
            self.log_error(f"Error polling Jira project {repo.owner}/{repo.repo}", e)
            raise
    
    def _handle_github_issue_webhook(self, event: WebhookEvent):
        """Handle GitHub issue webhook event."""
        try:
            self.stats['webhook_events_received'] += 1
            
            # Extract bug report from webhook event
            bug_report = self.webhook_receiver.extract_bug_report_from_github(event)
            
            if bug_report and self._should_process_bug(bug_report):
                self._process_new_bug(bug_report)
                self.log_info(f"Processed GitHub webhook for bug: {bug_report.id}")
            
        except Exception as e:
            self.log_error("Error handling GitHub webhook", e)
            self.stats['errors'] += 1
    
    def _handle_jira_issue_webhook(self, event: WebhookEvent):
        """Handle Jira issue webhook event."""
        try:
            self.stats['webhook_events_received'] += 1
            
            # Extract bug report from webhook event
            bug_report = self.webhook_receiver.extract_bug_report_from_jira(event)
            
            if bug_report and self._should_process_bug(bug_report):
                self._process_new_bug(bug_report)
                self.log_info(f"Processed Jira webhook for bug: {bug_report.id}")
            
        except Exception as e:
            self.log_error("Error handling Jira webhook", e)
            self.stats['errors'] += 1
    
    def _convert_github_issue_to_bug_report(
        self,
        issue: GitHubIssue,
        repo: MonitoredRepository
    ) -> Optional[BugReport]:
        """Convert GitHub issue to standardized bug report."""
        try:
            # Check if issue is actually a bug (has bug labels or keywords)
            is_bug = self._is_github_issue_bug(issue)
            if not is_bug:
                return None
            
            bug_report = BugReport(
                id=f"github_{issue.id}",
                title=issue.title,
                description=issue.body,
                reporter=issue.author,
                created_at=issue.created_at,
                platform="github",
                url=issue.html_url,
                labels=issue.labels,
                raw_data={
                    'issue_number': issue.number,
                    'repository': issue.repository,
                    'state': issue.state,
                    'assignees': issue.assignees,
                    'updated_at': issue.updated_at.isoformat()
                }
            )
            
            return bug_report
            
        except Exception as e:
            self.log_error(f"Error converting GitHub issue {issue.id} to bug report", e)
            return None
    
    def _is_github_issue_bug(self, issue: GitHubIssue) -> bool:
        """Determine if GitHub issue is a bug report."""
        # Check for bug-related labels
        bug_labels = {'bug', 'defect', 'error', 'issue', 'problem', 'fix'}
        issue_labels = {label.lower() for label in issue.labels}
        
        if bug_labels.intersection(issue_labels):
            return True
        
        # Check for bug-related keywords in title
        bug_keywords = {'bug', 'error', 'crash', 'broken', 'fail', 'issue', 'problem'}
        title_words = {word.lower() for word in issue.title.split()}
        
        if bug_keywords.intersection(title_words):
            return True
        
        # Default to treating all issues as potential bugs for comprehensive monitoring
        return True
    
    def _convert_jira_issue_to_bug_report(
        self,
        issue: JiraIssue,
        repo: MonitoredRepository
    ) -> Optional[BugReport]:
        """Convert Jira issue to standardized bug report."""
        try:
            # Check if issue is actually a bug
            is_bug = self._is_jira_issue_bug(issue)
            if not is_bug:
                return None
            
            bug_report = BugReport(
                id=f"jira_{issue.id}",
                title=issue.summary,
                description=issue.description,
                reporter=issue.reporter,
                created_at=issue.created,
                platform="jira",
                url=issue.url,
                labels=issue.labels,
                raw_data={
                    'key': issue.key,
                    'project_key': issue.project_key,
                    'status': issue.status,
                    'priority': issue.priority,
                    'issue_type': issue.issue_type,
                    'assignee': issue.assignee,
                    'updated': issue.updated.isoformat()
                }
            )
            
            return bug_report
            
        except Exception as e:
            self.log_error(f"Error converting Jira issue {issue.id} to bug report", e)
            return None
    
    def _is_jira_issue_bug(self, issue: JiraIssue) -> bool:
        """Determine if Jira issue is a bug report."""
        # Check issue type
        bug_types = {'bug', 'defect', 'error', 'issue', 'problem', 'bug report'}
        if issue.issue_type.lower() in bug_types:
            return True
        
        # Check labels
        bug_labels = {'bug', 'defect', 'error', 'issue', 'problem', 'fix'}
        issue_labels = {label.lower() for label in issue.labels}
        
        if bug_labels.intersection(issue_labels):
            return True
        
        # Check for bug-related keywords in summary
        bug_keywords = {'bug', 'error', 'crash', 'broken', 'fail', 'issue', 'problem'}
        summary_words = {word.lower() for word in issue.summary.split()}
        
        if bug_keywords.intersection(summary_words):
            return True
        
        return False
    
    def _should_process_bug(self, bug_report: BugReport) -> bool:
        """Determine if bug should be processed (avoid duplicates)."""
        if bug_report.id in self.processed_bugs:
            return False
        
        # Add to processed set
        self.processed_bugs.add(bug_report.id)
        
        # Limit processed bugs set size to prevent memory issues
        if len(self.processed_bugs) > 10000:
            # Remove oldest entries (simple approach)
            oldest_bugs = list(self.processed_bugs)[:5000]
            for bug_id in oldest_bugs:
                self.processed_bugs.discard(bug_id)
        
        return True
    
    def _process_new_bug(self, bug_report: BugReport):
        """Process a newly detected bug report."""
        try:
            # Validate bug report
            if not self._validate_bug_report(bug_report):
                self.log_error(f"Invalid bug report: {bug_report.id}")
                return
            
            # Publish to message queue
            if self.publisher and self.publisher.publish_bug_report(bug_report):
                self.stats['bugs_published'] += 1
                self.stats['last_activity'] = datetime.utcnow().isoformat()
                self.log_info(f"Published bug report: {bug_report.id} - {bug_report.title}")
            else:
                self.log_error(f"Failed to publish bug report: {bug_report.id}")
                self.stats['errors'] += 1
            
            self.stats['bugs_detected'] += 1
            
        except Exception as e:
            self.log_error(f"Error processing bug report {bug_report.id}", e)
            self.stats['errors'] += 1
    
    def _validate_bug_report(self, bug_report: BugReport) -> bool:
        """Validate bug report data."""
        if not bug_report.id:
            return False
        
        if not bug_report.title or not bug_report.title.strip():
            return False
        
        if not bug_report.platform:
            return False
        
        if not bug_report.created_at:
            return False
        
        return True
    
    def add_monitored_repository(
        self,
        platform: str,
        owner: str,
        repo: str,
        setup_webhook: bool = True
    ) -> bool:
        """Add a new repository to monitor.
        
        Args:
            platform: Platform type (github, jira)
            owner: Repository owner/organization
            repo: Repository name
            setup_webhook: Whether to set up webhook for real-time monitoring
            
        Returns:
            True if repository added successfully, False otherwise
        """
        try:
            # Check if repository already monitored
            for existing_repo in self.monitored_repos:
                if (existing_repo.platform == platform and 
                    existing_repo.owner == owner and 
                    existing_repo.repo == repo):
                    self.log_info(f"Repository {platform}:{owner}/{repo} already monitored")
                    return True
            
            # Create new monitored repository
            new_repo = MonitoredRepository(
                platform=platform,
                owner=owner,
                repo=repo
            )
            
            # Set up webhook if requested and GitHub client available
            if setup_webhook and platform == "github" and self.github_client:
                webhook_url = getattr(self.system_config.api, 'webhook_base_url', 'http://localhost:8080')
                success = self.github_client.create_webhook(
                    owner=owner,
                    repo=repo,
                    webhook_url=f"{webhook_url}/webhooks/github",
                    events=["issues", "issue_comment"]
                )
                new_repo.webhook_configured = success
            
            self.monitored_repos.append(new_repo)
            self.log_info(f"Added repository to monitor: {platform}:{owner}/{repo}")
            return True
            
        except Exception as e:
            self.log_error(f"Error adding monitored repository {platform}:{owner}/{repo}", e)
            return False
    
    def remove_monitored_repository(self, platform: str, owner: str, repo: str) -> bool:
        """Remove a repository from monitoring.
        
        Args:
            platform: Platform type (github, jira)
            owner: Repository owner/organization
            repo: Repository name
            
        Returns:
            True if repository removed successfully, False otherwise
        """
        try:
            # Find and remove repository
            for i, existing_repo in enumerate(self.monitored_repos):
                if (existing_repo.platform == platform and 
                    existing_repo.owner == owner and 
                    existing_repo.repo == repo):
                    
                    del self.monitored_repos[i]
                    self.log_info(f"Removed repository from monitoring: {platform}:{owner}/{repo}")
                    return True
            
            self.log_info(f"Repository not found in monitoring list: {platform}:{owner}/{repo}")
            return False
            
        except Exception as e:
            self.log_error(f"Error removing monitored repository {platform}:{owner}/{repo}", e)
            return False
    
    def get_monitored_repositories(self) -> List[Dict[str, Any]]:
        """Get list of currently monitored repositories.
        
        Returns:
            List of repository information dictionaries
        """
        return [
            {
                'platform': repo.platform,
                'owner': repo.owner,
                'repo': repo.repo,
                'last_check': repo.last_check.isoformat() if repo.last_check else None,
                'webhook_configured': repo.webhook_configured
            }
            for repo in self.monitored_repos
        ]