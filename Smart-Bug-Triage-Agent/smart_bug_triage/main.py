"""Main entry point for the Smart Bug Triage system."""

import sys
import signal
import asyncio
import threading
from typing import Optional
from smart_bug_triage.config.settings import SystemConfig
from smart_bug_triage.utils.logging import setup_logging, get_logger
from smart_bug_triage.health import HealthServer, DatabaseHealthCheck, MessageQueueHealthCheck


class SmartBugTriageSystem:
    """Main system orchestrator."""
    
    def __init__(self, config_path: Optional[str] = None):
        # Load configuration
        if config_path:
            self.config = SystemConfig.from_file(config_path)
        else:
            self.config = SystemConfig.from_env()
        
        # Validate configuration
        if not self.config.validate():
            raise ValueError("Invalid configuration")
        
        # Setup logging
        setup_logging(self.config.logging)
        self.logger = get_logger(__name__)
        
        # Initialize system components
        self.agents = {}
        self.running = False
        self.health_server = None
        self.health_thread = None
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        self.logger.info(f"Received signal {signum}, shutting down...")
        self.stop()
    
    def start(self) -> None:
        """Start the smart bug triage system."""
        self.logger.info("Starting Smart Bug Triage System...")
        
        try:
            # Start health check server
            self._start_health_server()
            
            # TODO: Initialize and start agents
            # This will be implemented in subsequent tasks
            
            self.running = True
            self.logger.info("Smart Bug Triage System started successfully")
            
            # Keep the main thread alive
            while self.running:
                import time
                time.sleep(1)
                
        except Exception as e:
            self.logger.error(f"Failed to start system: {str(e)}")
            raise
    
    def stop(self) -> None:
        """Stop the smart bug triage system."""
        self.logger.info("Stopping Smart Bug Triage System...")
        
        self.running = False
        
        # Stop health server
        if self.health_server:
            self.logger.info("Stopping health check server...")
        
        # TODO: Stop all agents gracefully
        # This will be implemented in subsequent tasks
        
        self.logger.info("Smart Bug Triage System stopped")
    
    def _start_health_server(self):
        """Start the health check server in a separate thread."""
        try:
            self.health_server = HealthServer(port=8000)
            
            # Add basic health checks
            # TODO: Add actual database and message queue managers when available
            # self.health_server.add_health_check("database", DatabaseHealthCheck(db_manager))
            # self.health_server.add_health_check("message_queue", MessageQueueHealthCheck(mq_manager))
            
            # Start health server in separate thread
            self.health_thread = threading.Thread(
                target=self.health_server.run,
                daemon=True,
                name="HealthServer"
            )
            self.health_thread.start()
            self.logger.info("Health check server started on port 8000")
            
        except Exception as e:
            self.logger.error(f"Failed to start health server: {e}")
    
    def get_system_status(self) -> dict:
        """Get current system status."""
        return {
            "running": self.running,
            "agents": {agent_id: agent.get_status() for agent_id, agent in self.agents.items()},
            "config_valid": self.config.validate(),
            "health_server_running": self.health_server is not None
        }


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Smart Bug Triage System")
    parser.add_argument("--config", help="Path to configuration file")
    args = parser.parse_args()
    
    try:
        system = SmartBugTriageSystem(args.config)
        system.start()
    except KeyboardInterrupt:
        print("\nShutdown requested by user")
    except Exception as e:
        print(f"System error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()