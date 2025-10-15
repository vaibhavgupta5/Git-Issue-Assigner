#!/usr/bin/env python
"""Script to manage developer agents."""

import sys
import os
import argparse
import logging
import time
import signal
from typing import Optional

# Add the project root to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from smart_bug_triage.agents.developer_agent import DeveloperAgentManager
from smart_bug_triage.api.github_client import GitHubAPIClient
from smart_bug_triage.api.jira_client import JiraAPIClient
from smart_bug_triage.database.connection import DatabaseManager
from smart_bug_triage.config.settings import Settings


def setup_logging(level: str = "INFO"):
    """Set up logging configuration."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('developer_agents.log')
        ]
    )


class AgentManagerRunner:
    """Runner for the developer agent manager."""
    
    def __init__(self, manager: DeveloperAgentManager):
        """Initialize the runner.
        
        Args:
            manager: Developer agent manager instance
        """
        self.manager = manager
        self.logger = logging.getLogger(__name__)
        self._running = False
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        self.logger.info(f"Received signal {signum}, shutting down...")
        self._running = False
    
    def run(self):
        """Run the agent manager."""
        try:
            self.logger.info("Starting developer agent manager...")
            
            if not self.manager.start():
                self.logger.error("Failed to start agent manager")
                return 1
            
            self._running = True
            self.logger.info("Developer agent manager started successfully")
            
            # Main loop
            while self._running:
                try:
                    # Display status every 60 seconds
                    self._display_status()
                    
                    # Sleep for a short time to allow for graceful shutdown
                    for _ in range(60):  # 60 seconds total
                        if not self._running:
                            break
                        time.sleep(1)
                        
                except KeyboardInterrupt:
                    break
            
            self.logger.info("Shutting down agent manager...")
            self.manager.stop()
            self.logger.info("Agent manager stopped")
            return 0
            
        except Exception as e:
            self.logger.error(f"Agent manager failed: {e}", exc_info=True)
            return 1
    
    def _display_status(self):
        """Display current status of all agents."""
        try:
            health_status = self.manager.get_agent_health_status()
            developer_statuses = self.manager.get_all_developer_statuses()
            
            print(f"\n--- Agent Status ({time.strftime('%Y-%m-%d %H:%M:%S')}) ---")
            print(f"Total Agents: {len(health_status)}")
            
            # Count agents by status
            running_count = sum(1 for status in health_status.values() if status.get('running', False))
            error_count = sum(1 for status in health_status.values() if status.get('error_count', 0) > 0)
            
            print(f"Running: {running_count}, Errors: {error_count}")
            
            # Display developer workload summary
            if developer_statuses:
                total_workload = sum(status.current_workload for status in developer_statuses)
                avg_workload = total_workload / len(developer_statuses)
                
                available_count = sum(1 for status in developer_statuses if status.availability.value == 'available')
                busy_count = sum(1 for status in developer_statuses if status.availability.value == 'busy')
                unavailable_count = sum(1 for status in developer_statuses if status.availability.value == 'unavailable')
                
                print(f"Developer Summary:")
                print(f"  Total Issues: {total_workload}")
                print(f"  Average Workload: {avg_workload:.1f}")
                print(f"  Available: {available_count}, Busy: {busy_count}, Unavailable: {unavailable_count}")
            
            # Display individual agent details if there are errors
            if error_count > 0:
                print("\nAgents with Errors:")
                for agent_id, status in health_status.items():
                    if status.get('error_count', 0) > 0:
                        print(f"  {agent_id}: {status.get('error_count')} errors, "
                              f"last update: {status.get('last_successful_update', 'Never')}")
            
        except Exception as e:
            self.logger.error(f"Failed to display status: {e}")


def list_developers(db_manager: DatabaseManager):
    """List all developers in the database."""
    try:
        from smart_bug_triage.models.database import Developer, DeveloperStatus
        
        with db_manager.get_session() as session:
            developers = session.query(Developer).all()
            
            if not developers:
                print("No developers found in database")
                return
            
            print(f"\n--- Developers ({len(developers)} total) ---")
            
            for dev in developers:
                # Get current status
                status = session.query(DeveloperStatus).filter_by(developer_id=dev.id).first()
                
                print(f"\nID: {dev.id}")
                print(f"Name: {dev.name}")
                print(f"GitHub: {dev.github_username}")
                print(f"Email: {dev.email}")
                print(f"Experience: {dev.experience_level}")
                print(f"Max Capacity: {dev.max_capacity}")
                print(f"Skills: {', '.join(dev.skills[:3])}{'...' if len(dev.skills) > 3 else ''}")
                
                if status:
                    print(f"Current Workload: {status.current_workload}")
                    print(f"Availability: {status.availability}")
                    print(f"Last Updated: {status.last_updated}")
                else:
                    print("Status: No status record")
                    
    except Exception as e:
        logging.error(f"Failed to list developers: {e}")


def show_agent_status(manager: DeveloperAgentManager):
    """Show detailed agent status."""
    try:
        health_status = manager.get_agent_health_status()
        developer_statuses = manager.get_all_developer_statuses()
        
        print(f"\n--- Detailed Agent Status ---")
        
        if not health_status:
            print("No agents are currently running")
            return
        
        # Create a mapping of developer_id to status
        status_map = {status.developer_id: status for status in developer_statuses}
        
        for agent_id, agent_status in health_status.items():
            print(f"\nAgent: {agent_id}")
            print(f"  Running: {agent_status.get('running', False)}")
            print(f"  Developer ID: {agent_status.get('developer_id', 'Unknown')}")
            print(f"  GitHub Username: {agent_status.get('github_username', 'Unknown')}")
            print(f"  Error Count: {agent_status.get('error_count', 0)}")
            print(f"  Last Update: {agent_status.get('last_successful_update', 'Never')}")
            print(f"  Next Update: {agent_status.get('next_update', 'Unknown')}")
            
            # Show developer status if available
            dev_id = agent_status.get('developer_id')
            if dev_id and dev_id in status_map:
                dev_status = status_map[dev_id]
                print(f"  Developer Status:")
                print(f"    Workload: {dev_status.current_workload}")
                print(f"    Open Issues: {dev_status.open_issues_count}")
                print(f"    Complexity Score: {dev_status.complexity_score:.1f}")
                print(f"    Availability: {dev_status.availability.value}")
                print(f"    Calendar Free: {dev_status.calendar_free}")
                print(f"    Focus Time: {dev_status.focus_time_active}")
                
    except Exception as e:
        logging.error(f"Failed to show agent status: {e}")


def main():
    """Main function."""
    parser = argparse.ArgumentParser(description='Manage developer agents')
    parser.add_argument('command', choices=['run', 'list', 'status'], 
                       help='Command to execute')
    parser.add_argument('--github-token', help='GitHub personal access token')
    parser.add_argument('--jira-url', help='Jira server URL')
    parser.add_argument('--jira-username', help='Jira username')
    parser.add_argument('--jira-token', help='Jira API token')
    parser.add_argument('--config', help='Path to configuration file')
    parser.add_argument('--log-level', default='INFO', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       help='Logging level')
    
    args = parser.parse_args()
    
    # Set up logging
    setup_logging(args.log_level)
    logger = logging.getLogger(__name__)
    
    try:
        # Load settings
        settings = Settings(args.config)
        
        # Initialize database
        logger.info("Initializing database connection...")
        db_manager = DatabaseManager(settings.database_config)
        
        if not db_manager.test_connection():
            logger.error("Failed to connect to database")
            return 1
        
        # Handle list command (doesn't need API clients)
        if args.command == 'list':
            list_developers(db_manager)
            return 0
        
        # Get API credentials
        github_token = args.github_token or os.getenv('GITHUB_TOKEN') or settings.api_config.github_token
        if not github_token:
            logger.error("GitHub token is required. Set GITHUB_TOKEN environment variable or use --github-token")
            return 1
        
        # Initialize GitHub client
        logger.info("Initializing GitHub client...")
        github_client = GitHubAPIClient(github_token)
        
        if not github_client.test_connection():
            logger.error("Failed to connect to GitHub API")
            return 1
        
        # Initialize Jira client (optional)
        jira_client = None
        jira_url = args.jira_url or os.getenv('JIRA_URL') or settings.api_config.jira_url
        jira_username = args.jira_username or os.getenv('JIRA_USERNAME') or settings.api_config.jira_username
        jira_token = args.jira_token or os.getenv('JIRA_TOKEN') or settings.api_config.jira_token
        
        if jira_url and jira_username and jira_token:
            logger.info("Initializing Jira client...")
            try:
                jira_client = JiraAPIClient(jira_url, jira_username, jira_token)
                if jira_client.test_connection():
                    logger.info("Jira client initialized successfully")
                else:
                    logger.warning("Jira connection test failed, continuing without Jira integration")
                    jira_client = None
            except Exception as e:
                logger.warning(f"Failed to initialize Jira client: {e}")
                jira_client = None
        else:
            logger.info("Jira credentials not provided, continuing without Jira integration")
        
        # Initialize agent manager
        logger.info("Initializing developer agent manager...")
        manager = DeveloperAgentManager(
            github_client=github_client,
            jira_client=jira_client,
            db_manager=db_manager,
            settings=settings
        )
        
        # Execute command
        if args.command == 'run':
            runner = AgentManagerRunner(manager)
            return runner.run()
        
        elif args.command == 'status':
            # For status command, we need to start the manager briefly
            if manager.start():
                show_agent_status(manager)
                manager.stop()
                return 0
            else:
                logger.error("Failed to start agent manager")
                return 1
        
        return 0
        
    except KeyboardInterrupt:
        logger.info("Operation interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Operation failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())