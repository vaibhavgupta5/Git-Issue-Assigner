"""Configuration settings and environment management."""

import os
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
import json
import logging


@dataclass
class DatabaseConfig:
    """Database connection configuration."""
    host: str = "localhost"
    port: int = 5432
    database: str = "smart_bug_triage"
    username: str = "postgres"
    password: str = ""
    pool_size: int = 10
    max_overflow: int = 20


@dataclass
class APIConfig:
    """External API configuration."""
    github_token: str = ""
    jira_url: str = ""
    jira_username: str = ""
    jira_token: str = ""
    slack_token: str = ""
    slack_webhook_url: str = ""
    rate_limit_requests: int = 100
    rate_limit_window: int = 3600  # seconds


@dataclass
class MessageQueueConfig:
    """Message queue configuration."""
    host: str = "localhost"
    port: int = 5672
    username: str = "guest"
    password: str = "guest"
    virtual_host: str = "/"
    exchange_name: str = "bug_triage"
    queue_names: Dict[str, str] = field(default_factory=lambda: {
        "new_bugs": "new_bugs_queue",
        "triaged_bugs": "triaged_bugs_queue",
        "assignments": "assignments_queue",
        "notifications": "notifications_queue"
    })


@dataclass
class AgentConfig:
    """Agent-specific configuration."""
    listener_poll_interval: int = 30  # seconds
    triage_batch_size: int = 10
    developer_status_update_interval: int = 900  # 15 minutes
    developer_agent_update_interval: int = 900  # 15 minutes
    developer_agent_max_retries: int = 3
    developer_agent_retry_delay: int = 60  # 1 minute
    developer_agent_health_check_interval: int = 300  # 5 minutes
    assignment_timeout: int = 300  # 5 minutes
    max_retries: int = 3
    retry_backoff_factor: float = 2.0


@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    file_path: Optional[str] = None
    max_file_size: int = 10485760  # 10MB
    backup_count: int = 5


@dataclass
class PerformanceConfig:
    """Performance tracking configuration."""
    enabled: bool = True
    lookback_days: int = 90
    skill_confidence_lookback_days: int = 180


@dataclass
class CalendarConfig:
    """Calendar integration configuration."""
    enabled: bool = True
    provider: str = "google"  # "google" or "outlook"
    google_credentials_path: str = ""
    outlook_client_id: str = ""
    outlook_client_secret: str = ""
    outlook_tenant_id: str = ""


@dataclass
class DeveloperDiscoveryConfig:
    """Developer discovery configuration."""
    enabled: bool = True
    discovery_interval: int = 86400  # 24 hours
    min_contributions: int = 5
    lookback_months: int = 6
    github_organization: str = ""
    github_repositories: List[str] = field(default_factory=list)
    github_repo_pattern: str = ""
    jira_projects: List[str] = field(default_factory=list)
    jira_project_pattern: str = ""


@dataclass
class NotificationConfig:
    """Notification system configuration."""
    enabled: bool = True
    max_retries: int = 3
    retry_delay: int = 60  # seconds
    batch_size: int = 10
    
    # Email configuration
    email_enabled: bool = True
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    email_from_address: str = ""
    email_from_name: str = "Smart Bug Triage System"
    
    # Slack configuration
    slack_enabled: bool = True
    slack_bot_token: str = ""
    slack_webhook_url: str = ""
    slack_default_channel: str = "#bug-triage"
    slack_mention_users: bool = True
    
    # Notification preferences
    quiet_hours_enabled: bool = True
    default_quiet_hours_start: str = "22:00"
    default_quiet_hours_end: str = "08:00"
    default_timezone: str = "UTC"
    
    # Delivery confirmation
    delivery_confirmation_enabled: bool = True
    confirmation_timeout: int = 300  # 5 minutes


@dataclass
class SystemConfig:
    """Main system configuration."""
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    api: APIConfig = field(default_factory=APIConfig)
    message_queue: MessageQueueConfig = field(default_factory=MessageQueueConfig)
    agents: AgentConfig = field(default_factory=AgentConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    performance: PerformanceConfig = field(default_factory=PerformanceConfig)
    calendar: CalendarConfig = field(default_factory=CalendarConfig)
    developer_discovery: DeveloperDiscoveryConfig = field(default_factory=DeveloperDiscoveryConfig)
    notifications: NotificationConfig = field(default_factory=NotificationConfig)
    
    @classmethod
    def from_env(cls) -> 'SystemConfig':
        """Create configuration from environment variables."""
        config = cls()
        
        # Database configuration
        config.database.host = os.getenv('DB_HOST', config.database.host)
        config.database.port = int(os.getenv('DB_PORT', str(config.database.port)))
        config.database.database = os.getenv('DB_NAME', config.database.database)
        config.database.username = os.getenv('DB_USERNAME', config.database.username)
        config.database.password = os.getenv('DB_PASSWORD', config.database.password)
        
        # API configuration
        config.api.github_token = os.getenv('GITHUB_TOKEN', config.api.github_token)
        config.api.jira_url = os.getenv('JIRA_URL', config.api.jira_url)
        config.api.jira_username = os.getenv('JIRA_USERNAME', config.api.jira_username)
        config.api.jira_token = os.getenv('JIRA_TOKEN', config.api.jira_token)
        config.api.slack_token = os.getenv('SLACK_TOKEN', config.api.slack_token)
        config.api.slack_webhook_url = os.getenv('SLACK_WEBHOOK_URL', config.api.slack_webhook_url)
        
        # Notification configuration
        config.notifications.enabled = os.getenv('NOTIFICATIONS_ENABLED', 'true').lower() == 'true'
        config.notifications.email_enabled = os.getenv('EMAIL_NOTIFICATIONS_ENABLED', 'true').lower() == 'true'
        config.notifications.smtp_host = os.getenv('SMTP_HOST', config.notifications.smtp_host)
        config.notifications.smtp_port = int(os.getenv('SMTP_PORT', str(config.notifications.smtp_port)))
        config.notifications.smtp_username = os.getenv('SMTP_USERNAME', config.notifications.smtp_username)
        config.notifications.smtp_password = os.getenv('SMTP_PASSWORD', config.notifications.smtp_password)
        config.notifications.email_from_address = os.getenv('EMAIL_FROM_ADDRESS', config.notifications.email_from_address)
        config.notifications.slack_enabled = os.getenv('SLACK_NOTIFICATIONS_ENABLED', 'true').lower() == 'true'
        config.notifications.slack_bot_token = os.getenv('SLACK_BOT_TOKEN', config.notifications.slack_bot_token)
        config.notifications.slack_webhook_url = os.getenv('SLACK_WEBHOOK_URL', config.notifications.slack_webhook_url)
        config.notifications.slack_default_channel = os.getenv('SLACK_DEFAULT_CHANNEL', config.notifications.slack_default_channel)
        
        # Message queue configuration
        config.message_queue.host = os.getenv('RABBITMQ_HOST', config.message_queue.host)
        config.message_queue.port = int(os.getenv('RABBITMQ_PORT', str(config.message_queue.port)))
        config.message_queue.username = os.getenv('RABBITMQ_USERNAME', config.message_queue.username)
        config.message_queue.password = os.getenv('RABBITMQ_PASSWORD', config.message_queue.password)
        
        # Logging configuration
        config.logging.level = os.getenv('LOG_LEVEL', config.logging.level)
        config.logging.file_path = os.getenv('LOG_FILE_PATH', config.logging.file_path)
        
        # Agent configuration
        config.agents.developer_agent_update_interval = int(os.getenv('DEVELOPER_AGENT_UPDATE_INTERVAL', str(config.agents.developer_agent_update_interval)))
        config.agents.developer_agent_max_retries = int(os.getenv('DEVELOPER_AGENT_MAX_RETRIES', str(config.agents.developer_agent_max_retries)))
        config.agents.developer_agent_retry_delay = int(os.getenv('DEVELOPER_AGENT_RETRY_DELAY', str(config.agents.developer_agent_retry_delay)))
        config.agents.developer_agent_health_check_interval = int(os.getenv('DEVELOPER_AGENT_HEALTH_CHECK_INTERVAL', str(config.agents.developer_agent_health_check_interval)))
        
        # Performance tracking configuration
        config.performance.enabled = os.getenv('PERFORMANCE_TRACKING_ENABLED', 'true').lower() == 'true'
        config.performance.lookback_days = int(os.getenv('PERFORMANCE_LOOKBACK_DAYS', str(config.performance.lookback_days)))
        config.performance.skill_confidence_lookback_days = int(os.getenv('SKILL_CONFIDENCE_LOOKBACK_DAYS', str(config.performance.skill_confidence_lookback_days)))
        
        # Calendar integration configuration
        config.calendar.enabled = os.getenv('CALENDAR_INTEGRATION_ENABLED', 'true').lower() == 'true'
        config.calendar.provider = os.getenv('CALENDAR_PROVIDER', config.calendar.provider)
        config.calendar.google_credentials_path = os.getenv('GOOGLE_CALENDAR_CREDENTIALS_PATH', config.calendar.google_credentials_path)
        config.calendar.outlook_client_id = os.getenv('OUTLOOK_CLIENT_ID', config.calendar.outlook_client_id)
        config.calendar.outlook_client_secret = os.getenv('OUTLOOK_CLIENT_SECRET', config.calendar.outlook_client_secret)
        config.calendar.outlook_tenant_id = os.getenv('OUTLOOK_TENANT_ID', config.calendar.outlook_tenant_id)
        
        # Developer discovery configuration
        config.developer_discovery.enabled = os.getenv('DEVELOPER_DISCOVERY_ENABLED', 'true').lower() == 'true'
        config.developer_discovery.discovery_interval = int(os.getenv('DEVELOPER_DISCOVERY_INTERVAL', str(config.developer_discovery.discovery_interval)))
        config.developer_discovery.min_contributions = int(os.getenv('DEVELOPER_MIN_CONTRIBUTIONS', str(config.developer_discovery.min_contributions)))
        config.developer_discovery.lookback_months = int(os.getenv('DEVELOPER_LOOKBACK_MONTHS', str(config.developer_discovery.lookback_months)))
        config.developer_discovery.github_organization = os.getenv('GITHUB_ORGANIZATION', config.developer_discovery.github_organization)
        config.developer_discovery.github_repo_pattern = os.getenv('GITHUB_REPO_PATTERN', config.developer_discovery.github_repo_pattern)
        config.developer_discovery.jira_project_pattern = os.getenv('JIRA_PROJECT_PATTERN', config.developer_discovery.jira_project_pattern)
        
        # Parse comma-separated lists
        github_repos = os.getenv('GITHUB_REPOSITORIES', '')
        if github_repos:
            config.developer_discovery.github_repositories = [repo.strip() for repo in github_repos.split(',')]
        
        jira_projects = os.getenv('JIRA_PROJECTS', '')
        if jira_projects:
            config.developer_discovery.jira_projects = [project.strip() for project in jira_projects.split(',')]
        
        return config
    
    @classmethod
    def from_file(cls, config_path: str) -> 'SystemConfig':
        """Load configuration from JSON file."""
        try:
            with open(config_path, 'r') as f:
                config_data = json.load(f)
            
            config = cls()
            
            # Update configuration with file data
            if 'database' in config_data:
                for key, value in config_data['database'].items():
                    if hasattr(config.database, key):
                        setattr(config.database, key, value)
            
            if 'api' in config_data:
                for key, value in config_data['api'].items():
                    if hasattr(config.api, key):
                        setattr(config.api, key, value)
            
            if 'message_queue' in config_data:
                for key, value in config_data['message_queue'].items():
                    if hasattr(config.message_queue, key):
                        setattr(config.message_queue, key, value)
            
            if 'agents' in config_data:
                for key, value in config_data['agents'].items():
                    if hasattr(config.agents, key):
                        setattr(config.agents, key, value)
            
            if 'logging' in config_data:
                for key, value in config_data['logging'].items():
                    if hasattr(config.logging, key):
                        setattr(config.logging, key, value)
            
            return config
            
        except FileNotFoundError:
            logging.warning(f"Configuration file {config_path} not found, using defaults")
            return cls.from_env()
        except json.JSONDecodeError as e:
            logging.error(f"Invalid JSON in configuration file {config_path}: {e}")
            return cls.from_env()
    
    def validate(self) -> bool:
        """Validate configuration settings."""
        errors = []
        
        # Validate required API tokens
        if not self.api.github_token:
            errors.append("GitHub token is required")
        
        # Validate database settings
        if not self.database.host:
            errors.append("Database host is required")
        
        if not self.database.database:
            errors.append("Database name is required")
        
        # Validate message queue settings
        if not self.message_queue.host:
            errors.append("Message queue host is required")
        
        if errors:
            for error in errors:
                logging.error(f"Configuration validation error: {error}")
            return False
        
        return True


class Settings:
    """Main settings class for the application."""
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize settings.
        
        Args:
            config_path: Optional path to configuration file
        """
        if config_path and os.path.exists(config_path):
            self.config = SystemConfig.from_file(config_path)
        else:
            self.config = SystemConfig.from_env()
        
        # Set up config directory
        self.config_dir = os.path.join(os.getcwd(), '.config')
        os.makedirs(self.config_dir, exist_ok=True)
    
    @property
    def database_config(self) -> DatabaseConfig:
        """Get database configuration."""
        return self.config.database
    
    @property
    def api_config(self) -> APIConfig:
        """Get API configuration."""
        return self.config.api
    
    @property
    def message_queue_config(self) -> MessageQueueConfig:
        """Get message queue configuration."""
        return self.config.message_queue
    
    @property
    def agent_config(self) -> AgentConfig:
        """Get agent configuration."""
        return self.config.agents
    
    @property
    def logging_config(self) -> LoggingConfig:
        """Get logging configuration."""
        return self.config.logging
    
    @property
    def developer_agent_update_interval(self) -> int:
        """Get developer agent update interval."""
        return self.config.agents.developer_agent_update_interval
    
    @property
    def performance_config(self) -> PerformanceConfig:
        """Get performance configuration."""
        return self.config.performance
    
    @property
    def calendar_config(self) -> CalendarConfig:
        """Get calendar configuration."""
        return self.config.calendar
    
    @property
    def developer_discovery_config(self) -> DeveloperDiscoveryConfig:
        """Get developer discovery configuration."""
        return self.config.developer_discovery
    
    @property
    def notification_config(self) -> NotificationConfig:
        """Get notification configuration."""
        return self.config.notifications
    
    def validate(self) -> bool:
        """Validate all configuration settings."""
        return self.config.validate()