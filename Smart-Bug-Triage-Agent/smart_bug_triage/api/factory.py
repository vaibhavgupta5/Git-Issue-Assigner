"""API client factory for creating configured clients."""

import logging
from typing import Optional

from ..config.settings import SystemConfig
from .github_client import GitHubAPIClient
from .jira_client import JiraAPIClient
from .webhook_receiver import WebhookReceiver


class APIClientFactory:
    """Factory for creating configured API clients."""
    
    def __init__(self, config: SystemConfig):
        """Initialize factory with system configuration."""
        self.config = config
        self.logger = logging.getLogger(__name__)
    
    def create_github_client(self) -> Optional[GitHubAPIClient]:
        """Create GitHub API client."""
        if not self.config.api.github_token:
            self.logger.warning("GitHub token not configured, GitHub client unavailable")
            return None
        
        try:
            client = GitHubAPIClient(
                token=self.config.api.github_token,
                rate_limit_requests=self.config.api.rate_limit_requests,
                rate_limit_window=self.config.api.rate_limit_window
            )
            
            # Test connection
            if client.test_connection():
                self.logger.info("GitHub API client created successfully")
                return client
            else:
                self.logger.error("GitHub API client connection test failed")
                return None
                
        except Exception as e:
            self.logger.error(f"Failed to create GitHub API client: {e}")
            return None
    
    def create_jira_client(self) -> Optional[JiraAPIClient]:
        """Create Jira API client."""
        if not self.config.api.jira_url or not self.config.api.jira_username or not self.config.api.jira_token:
            self.logger.warning("Jira configuration incomplete, Jira client unavailable")
            return None
        
        try:
            client = JiraAPIClient(
                server_url=self.config.api.jira_url,
                username=self.config.api.jira_username,
                api_token=self.config.api.jira_token,
                rate_limit_requests=self.config.api.rate_limit_requests,
                rate_limit_window=self.config.api.rate_limit_window
            )
            
            # Test connection
            if client.test_connection():
                self.logger.info("Jira API client created successfully")
                return client
            else:
                self.logger.error("Jira API client connection test failed")
                return None
                
        except Exception as e:
            self.logger.error(f"Failed to create Jira API client: {e}")
            return None
    
    def create_webhook_receiver(
        self,
        github_secret: Optional[str] = None,
        jira_secret: Optional[str] = None,
        port: int = 8080,
        host: str = "0.0.0.0"
    ) -> WebhookReceiver:
        """Create webhook receiver."""
        try:
            receiver = WebhookReceiver(
                github_secret=github_secret,
                jira_secret=jira_secret,
                port=port,
                host=host
            )
            
            self.logger.info(f"Webhook receiver created for {host}:{port}")
            return receiver
            
        except Exception as e:
            self.logger.error(f"Failed to create webhook receiver: {e}")
            raise
    
    def create_all_clients(self) -> dict:
        """Create all available API clients."""
        clients = {}
        
        # Create GitHub client
        github_client = self.create_github_client()
        if github_client:
            clients['github'] = github_client
        
        # Create Jira client
        jira_client = self.create_jira_client()
        if jira_client:
            clients['jira'] = jira_client
        
        self.logger.info(f"Created {len(clients)} API clients: {list(clients.keys())}")
        return clients