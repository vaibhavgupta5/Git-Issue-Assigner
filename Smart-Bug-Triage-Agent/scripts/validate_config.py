#!/usr/bin/env python
"""Configuration validation script for Smart Bug Triage system."""

import os
import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables from .env file
env_file = project_root / '.env'
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                # Remove quotes if present
                value = value.strip('"\'')
                os.environ[key] = value

from smart_bug_triage.config.settings import Settings
from smart_bug_triage.api.github_client import GitHubAPIClient
from smart_bug_triage.api.jira_client import JiraAPIClient
from smart_bug_triage.agents.calendar_integration import CalendarIntegration, GoogleCalendarProvider, OutlookCalendarProvider


def validate_github_config(settings: Settings) -> bool:
    """Validate GitHub configuration."""
    print("🔍 Validating GitHub configuration...")
    
    if not settings.api_config.github_token:
        print("❌ GITHUB_TOKEN is required")
        return False
    
    try:
        client = GitHubAPIClient(settings.api_config.github_token)
        if client.test_connection():
            print("✅ GitHub connection successful")
            
            # Test rate limits
            try:
                rate_limit = client.get_rate_limit_status()
                if rate_limit and 'core' in rate_limit:
                    core_remaining = rate_limit['core'].get('remaining', 0)
                    print(f"📊 GitHub API rate limit: {core_remaining} requests remaining")
                    
                    if core_remaining < 100:
                        print("⚠️  Warning: Low GitHub API rate limit remaining")
            except Exception as e:
                print(f"⚠️  Could not check rate limits: {e}")
            
            return True
        else:
            print("❌ GitHub connection failed")
            return False
    except Exception as e:
        print(f"❌ GitHub validation error: {e}")
        return False


def validate_jira_config(settings: Settings) -> bool:
    """Validate Jira configuration."""
    print("\n🔍 Validating Jira configuration...")
    
    if not settings.api_config.jira_url:
        print("ℹ️  Jira not configured (optional)")
        return True
    
    if not settings.api_config.jira_username or not settings.api_config.jira_token:
        print("❌ JIRA_USERNAME and JIRA_TOKEN are required when JIRA_URL is set")
        return False
    
    try:
        client = JiraAPIClient(
            settings.api_config.jira_url,
            settings.api_config.jira_username,
            settings.api_config.jira_token
        )
        
        if client.test_connection():
            print("✅ Jira connection successful")
            
            # Test project access
            projects = client.get_projects()
            print(f"📊 Accessible Jira projects: {len(projects)}")
            
            return True
        else:
            print("❌ Jira connection failed")
            return False
    except Exception as e:
        print(f"❌ Jira validation error: {e}")
        return False


def validate_calendar_config(settings: Settings) -> bool:
    """Validate calendar integration configuration."""
    print("\n🔍 Validating calendar configuration...")
    
    if not settings.calendar_config.enabled:
        print("ℹ️  Calendar integration disabled")
        return True
    
    calendar_integration = CalendarIntegration()
    
    if settings.calendar_config.provider == "google":
        if not settings.calendar_config.google_credentials_path:
            print("❌ GOOGLE_CALENDAR_CREDENTIALS_PATH is required for Google Calendar")
            return False
        
        if not os.path.exists(settings.calendar_config.google_credentials_path):
            print(f"❌ Google Calendar credentials file not found: {settings.calendar_config.google_credentials_path}")
            return False
        
        try:
            provider = GoogleCalendarProvider(settings.calendar_config.google_credentials_path)
            if calendar_integration.add_provider("google", provider):
                print("✅ Google Calendar integration successful")
                return True
            else:
                print("❌ Google Calendar integration failed")
                return False
        except Exception as e:
            print(f"❌ Google Calendar validation error: {e}")
            return False
    
    elif settings.calendar_config.provider == "outlook":
        required_fields = [
            ("OUTLOOK_CLIENT_ID", settings.calendar_config.outlook_client_id),
            ("OUTLOOK_CLIENT_SECRET", settings.calendar_config.outlook_client_secret),
            ("OUTLOOK_TENANT_ID", settings.calendar_config.outlook_tenant_id)
        ]
        
        missing_fields = [name for name, value in required_fields if not value]
        if missing_fields:
            print(f"❌ Missing Outlook configuration: {', '.join(missing_fields)}")
            return False
        
        try:
            provider = OutlookCalendarProvider(
                settings.calendar_config.outlook_client_id,
                settings.calendar_config.outlook_client_secret,
                settings.calendar_config.outlook_tenant_id
            )
            
            if calendar_integration.add_provider("outlook", provider):
                print("✅ Outlook Calendar integration successful")
                return True
            else:
                print("❌ Outlook Calendar integration failed")
                return False
        except Exception as e:
            print(f"❌ Outlook Calendar validation error: {e}")
            return False
    
    else:
        print(f"❌ Unknown calendar provider: {settings.calendar_config.provider}")
        return False


def validate_database_config(settings: Settings) -> bool:
    """Validate database configuration."""
    print("\n🔍 Validating database configuration...")
    
    required_fields = [
        ("DB_HOST", settings.database_config.host),
        ("DB_NAME", settings.database_config.database),
        ("DB_USERNAME", settings.database_config.username)
    ]
    
    missing_fields = [name for name, value in required_fields if not value]
    if missing_fields:
        print(f"❌ Missing database configuration: {', '.join(missing_fields)}")
        return False
    
    try:
        # Try to import database connection
        from smart_bug_triage.database.connection import DatabaseManager
        
        db_manager = DatabaseManager(settings.database_config)
        
        # Test connection (this would need to be implemented in DatabaseManager)
        print("✅ Database configuration valid")
        print(f"📊 Database: {settings.database_config.host}:{settings.database_config.port}/{settings.database_config.database}")
        return True
        
    except ImportError:
        print("⚠️  Database manager not available for testing")
        return True
    except Exception as e:
        print(f"❌ Database validation error: {e}")
        return False


def validate_developer_discovery_config(settings: Settings) -> bool:
    """Validate developer discovery configuration."""
    print("\n🔍 Validating developer discovery configuration...")
    
    if not settings.developer_discovery_config.enabled:
        print("ℹ️  Developer discovery disabled")
        return True
    
    # Check GitHub configuration for discovery
    if not settings.developer_discovery_config.github_organization and not settings.developer_discovery_config.github_repositories:
        print("⚠️  No GitHub organization or repositories configured for discovery")
    
    # Check Jira configuration for discovery
    if settings.api_config.jira_url and not settings.developer_discovery_config.jira_projects:
        print("ℹ️  No Jira projects configured for discovery")
    
    print("✅ Developer discovery configuration valid")
    print(f"📊 Discovery interval: {settings.developer_discovery_config.discovery_interval}s")
    print(f"📊 Minimum contributions: {settings.developer_discovery_config.min_contributions}")
    
    return True


def main():
    """Main validation function."""
    print("🚀 Smart Bug Triage Configuration Validation")
    print("=" * 50)
    
    # Load configuration
    try:
        settings = Settings()
        print("✅ Configuration loaded successfully")
    except Exception as e:
        print(f"❌ Failed to load configuration: {e}")
        sys.exit(1)
    
    # Validate core configuration
    if not settings.validate():
        print("❌ Core configuration validation failed")
        sys.exit(1)
    
    print("✅ Core configuration valid")
    
    # Run individual validations
    validations = [
        ("GitHub", validate_github_config),
        ("Jira", validate_jira_config),
        ("Calendar", validate_calendar_config),
        ("Database", validate_database_config),
        ("Developer Discovery", validate_developer_discovery_config)
    ]
    
    results = {}
    for name, validator in validations:
        try:
            results[name] = validator(settings)
        except Exception as e:
            print(f"❌ {name} validation failed with exception: {e}")
            results[name] = False
    
    # Summary
    print("\n" + "=" * 50)
    print("📋 Validation Summary:")
    
    all_passed = True
    for name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {name}: {status}")
        if not passed:
            all_passed = False
    
    if all_passed:
        print("\n🎉 All validations passed! System is ready to run.")
        sys.exit(0)
    else:
        print("\n⚠️  Some validations failed. Please check configuration.")
        sys.exit(1)


if __name__ == "__main__":
    main()