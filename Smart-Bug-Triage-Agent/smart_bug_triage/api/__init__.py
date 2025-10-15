"""API integration layer for external services."""

from .base import BaseAPIClient, RateLimitConfig, CircuitBreakerConfig
from .github_client import GitHubAPIClient, GitHubIssue, GitHubUser
from .jira_client import JiraAPIClient, JiraIssue, JiraUser
from .webhook_receiver import WebhookReceiver, WebhookEvent, create_webhook_receiver_with_handlers
from .factory import APIClientFactory
from .feedback_api import FeedbackAPI, create_feedback_api

__all__ = [
    'BaseAPIClient',
    'RateLimitConfig', 
    'CircuitBreakerConfig',
    'GitHubAPIClient',
    'GitHubIssue',
    'GitHubUser',
    'JiraAPIClient',
    'JiraIssue',
    'JiraUser',
    'WebhookReceiver',
    'WebhookEvent',
    'create_webhook_receiver_with_handlers',
    'APIClientFactory',
    'FeedbackAPI',
    'create_feedback_api'
]