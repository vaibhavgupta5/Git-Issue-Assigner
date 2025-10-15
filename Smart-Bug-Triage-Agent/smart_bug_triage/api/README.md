# API Integration Layer

This module provides a comprehensive API integration layer for the Smart Bug Triage system, enabling seamless communication with external services like GitHub, Jira, and webhook receivers.

## Features

- **Rate Limiting**: Token bucket algorithm with configurable limits
- **Circuit Breaker**: Automatic failure detection and recovery
- **Retry Logic**: Exponential backoff for transient failures
- **Authentication**: Secure token-based authentication
- **Webhook Support**: Real-time event processing
- **Comprehensive Testing**: Full unit test coverage

## Components

### Base API Client (`base.py`)

Provides common functionality for all API clients:

- **RateLimiter**: Token bucket rate limiting
- **CircuitBreaker**: Fault tolerance pattern
- **BaseAPIClient**: Abstract base class with retry logic

```python
from smart_bug_triage.api.base import BaseAPIClient, RateLimitConfig, CircuitBreakerConfig

# Configure rate limiting and circuit breaker
rate_config = RateLimitConfig(requests_per_window=100, window_seconds=3600)
circuit_config = CircuitBreakerConfig(failure_threshold=5, recovery_timeout=60)

class MyAPIClient(BaseAPIClient):
    def authenticate(self):
        return {"Authorization": "Bearer token"}

client = MyAPIClient("https://api.example.com", rate_config, circuit_config)
```

### GitHub API Client (`github_client.py`)

Full-featured GitHub API integration:

```python
from smart_bug_triage.api.github_client import GitHubAPIClient

# Create client
client = GitHubAPIClient(token="your_github_token")

# Test connection
if client.test_connection():
    # Get issues
    issues = client.get_issues("owner", "repo", state="open")
    
    # Assign issue
    client.assign_issue("owner", "repo", 123, ["developer1"])
    
    # Add labels
    client.add_labels("owner", "repo", 123, ["bug", "priority-high"])
    
    # Create webhook
    client.create_webhook("owner", "repo", "https://your-server.com/webhook")
```

**Features:**
- Issue management (get, assign, label, comment)
- Repository contributor discovery
- User assigned issues search
- Webhook creation and management
- Rate limit monitoring
- Pull request filtering

### Jira API Client (`jira_client.py`)

Comprehensive Jira integration with fallback support:

```python
from smart_bug_triage.api.jira_client import JiraAPIClient

# Create client
client = JiraAPIClient(
    server_url="https://company.atlassian.net",
    username="user@company.com",
    api_token="your_api_token"
)

# Test connection
if client.test_connection():
    # Get projects
    projects = client.get_projects()
    
    # Get issues
    issues = client.get_issues("PROJECT_KEY")
    
    # Assign issue
    client.assign_issue("ISSUE-123", "user_account_id")
    
    # Search users
    users = client.search_users("john")
```

**Features:**
- Project and issue management
- User search and assignment
- Label and comment management
- JQL query support
- Dual API support (JIRA library + REST API fallback)

### Webhook Receiver (`webhook_receiver.py`)

Real-time event processing with FastAPI:

```python
from smart_bug_triage.api.webhook_receiver import create_webhook_receiver_with_handlers

def process_bug(bug_report):
    print(f"New bug: {bug_report.title}")

# Create receiver with handlers
receiver = create_webhook_receiver_with_handlers(
    github_secret="webhook_secret",
    jira_secret="webhook_secret",
    bug_processor=process_bug
)

# Start server
receiver.start()  # Runs on http://localhost:8080
```

**Features:**
- GitHub and Jira webhook support
- Signature verification for security
- Automatic bug report extraction
- Background event processing
- Health check endpoint
- Configurable event handlers

### API Client Factory (`factory.py`)

Centralized client creation and configuration:

```python
from smart_bug_triage.config.settings import SystemConfig
from smart_bug_triage.api.factory import APIClientFactory

# Load configuration
config = SystemConfig.from_env()

# Create factory
factory = APIClientFactory(config)

# Create all available clients
clients = factory.create_all_clients()

# Or create specific clients
github_client = factory.create_github_client()
jira_client = factory.create_jira_client()
webhook_receiver = factory.create_webhook_receiver()
```

## Configuration

Configure API clients through environment variables or configuration files:

```bash
# GitHub configuration
export GITHUB_TOKEN="your_github_token"

# Jira configuration
export JIRA_URL="https://company.atlassian.net"
export JIRA_USERNAME="user@company.com"
export JIRA_TOKEN="your_jira_token"

# Rate limiting
export RATE_LIMIT_REQUESTS="100"
export RATE_LIMIT_WINDOW="3600"
```

## Error Handling

The API layer includes comprehensive error handling:

### Rate Limiting
- Automatic token bucket rate limiting
- Configurable requests per window
- Automatic waiting when limits exceeded

### Circuit Breaker
- Automatic failure detection
- Configurable failure threshold
- Recovery timeout with half-open state

### Retry Logic
- Exponential backoff for transient failures
- Configurable retry attempts
- HTTP status code-based retry decisions

### Example Error Handling

```python
try:
    issues = github_client.get_issues("owner", "repo")
except requests.RequestException as e:
    # Handle API errors
    print(f"API request failed: {e}")
except Exception as e:
    # Handle circuit breaker or other errors
    print(f"Service unavailable: {e}")
```

## Testing

Run the comprehensive test suite:

```bash
# Run all API tests
python -m pytest tests/test_api/ -v

# Run specific test files
python -m pytest tests/test_api/test_github_client.py -v
python -m pytest tests/test_api/test_jira_client.py -v
python -m pytest tests/test_api/test_webhook_receiver.py -v
```

## Demo

Run the demo script to see the API integration in action:

```bash
# Set up environment variables first
export GITHUB_TOKEN="your_token"

# Run demo
python examples/api_integration_demo.py
```

## Security Considerations

- **Token Security**: Store API tokens securely, never in code
- **Webhook Signatures**: Always verify webhook signatures
- **Rate Limiting**: Respect API rate limits to avoid blocking
- **HTTPS**: Use HTTPS for all API communications
- **Secrets Management**: Use environment variables or secret managers

## Performance Optimization

- **Connection Pooling**: Automatic HTTP connection reuse
- **Rate Limiting**: Prevents API quota exhaustion
- **Circuit Breaker**: Fails fast during outages
- **Async Support**: Webhook receiver uses async processing
- **Caching**: Consider implementing response caching for frequently accessed data

## Integration with Bug Triage System

The API layer integrates with other system components:

1. **Listener Agent**: Uses webhook receiver for real-time notifications
2. **Assignment Agent**: Uses GitHub/Jira clients for issue assignment
3. **Developer Agents**: Use API clients to monitor developer workload
4. **Configuration**: Centralized configuration management

## Extending the API Layer

To add support for new services:

1. Create a new client class inheriting from `BaseAPIClient`
2. Implement the `authenticate()` method
3. Add service-specific methods
4. Update the factory to create the new client
5. Add comprehensive tests

Example:

```python
class SlackAPIClient(BaseAPIClient):
    def authenticate(self):
        return {"Authorization": f"Bearer {self.token}"}
    
    def send_message(self, channel, message):
        return self.post("/chat.postMessage", json_data={
            "channel": channel,
            "text": message
        })
```

## Troubleshooting

### Common Issues

1. **Authentication Failures**
   - Verify API tokens are correct and not expired
   - Check token permissions and scopes

2. **Rate Limiting**
   - Monitor rate limit status
   - Adjust rate limit configuration
   - Implement backoff strategies

3. **Network Issues**
   - Check internet connectivity
   - Verify API endpoints are accessible
   - Review firewall and proxy settings

4. **Webhook Issues**
   - Verify webhook URLs are accessible
   - Check webhook secrets match
   - Review webhook event configuration

### Debug Mode

Enable debug logging for detailed API interaction logs:

```python
import logging
logging.getLogger('smart_bug_triage.api').setLevel(logging.DEBUG)
```

## API Documentation

- [GitHub API Documentation](https://docs.github.com/en/rest)
- [Jira REST API Documentation](https://developer.atlassian.com/cloud/jira/platform/rest/v3/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)